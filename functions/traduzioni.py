import streamlit as st
import re
import json
import asyncio
import time
import os
import io
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator
from openai import AsyncOpenAI
import openai

from functions.gsheet import get_sheet

AVAILABLE_LANGS = ["en", "fr", "de", "es"]
OPENAI_MODEL = "gpt-4o-mini"
SAVE_TRANSLATE_EVERY = 25  # batch size consigliato

MANUAL_TRANSLATIONS = {
    "strappo": {
        "es": "cierre adherente",
        "fr": "scratch",
        "en": "strap",
        "de": "klettverschluss"
    }
}
MANUAL_TRANSLATIONS_PROMPT = """
IMPORTANTE:
Alcune parole devono seguire regole fisse:
- "strappo" -> {"en": "strap", "fr": "scratch", "es": "cierre adherente", "de": "klettverschluss"}
- "sneakers" -> {"en": "sneakers", "fr": "sneakers", "es": "sneakers"}
"""

# Client OpenAI async
client = AsyncOpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def normalize(text: str) -> str:
    return text.strip().lower()

def safe_json_loads(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {lang: text for lang in ["en", "fr", "de", "es"]}

def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"

def vocab_to_rows(vocab):
    rows = []
    for it_key, langs in vocab.items():
        row = [
            it_key,
            langs.get("en", ""),
            langs.get("fr", ""),
            langs.get("de", ""),
            langs.get("es", "")
        ]
        rows.append(row)
    return rows

def append_vocab_rows(ws, rows):
    values = []
    for r in rows:
        values.append([
            r.get("it", ""),
            r.get("en", ""),
            r.get("fr", ""),
            r.get("de", ""),
            r.get("es", ""),
            r.get("source_col", "")
        ])

    if values:
        ws.append_rows(values, value_input_option="RAW")

def worksheet_to_df(ws):
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)

def load_vocab(sheet_id, tab):
    ws = get_sheet(sheet_id, tab)
    df = worksheet_to_df(ws)
    df.columns = [c.strip().lower() for c in df.columns]

    vocab = {}
    if df.empty:
        return vocab, ws

    # Usiamo enumerate o row index per tracciare la posizione esatta sul foglio
    for idx, row in df.iterrows():
        it = str(row["it"]).strip()
        vocab[it] = {
            "translations": {
                lang: row.get(lang)
                for lang in row.index
                if lang != "it" and pd.notna(row.get(lang))
            },
            "row_number": idx + 2  # Salvia mo il numero di riga esatto su Google Sheets
        }

    return vocab, ws

def vocab_to_df(vocab):
    rows = []
    for it, langs in vocab.items():
        row = {"it": it}
        row.update(langs)
        rows.append(row)
    return pd.DataFrame(rows)

async def translate_term(term, target_langs, col_name):
    important_note = ""
    if col_name and "colore" in col_name.lower():
        important_note = (
            "IMPORTANTE: Il termine è un colore o una combinazione di colori, se contiene un trattino, "
            "traduci ciascuna parte separatamente e mantieni il trattino.\n"
        )

    messages = [
        {"role": "user", "content": f"""
        Traduci il seguente testo italiano ESCLUSIVAMENTE nelle seguenti lingue target: {', '.join(target_langs)}.
        IMPORTANTE:
        - Il testo risultante deve essere realmente tradotto.
        - NON lasciare il testo in italiano.
        - Ogni valore JSON deve essere nella lingua corretta.
        - Mantieni maiuscole e punteggiatura come nell'originale.
        - NON usare abbreviazioni, ellissi o forme contratte (es. niente “-sohle”, “-lining”, ecc.)
        
        {important_note}

        Testo da tradurre:
        \"\"\"{term}\"\"\"

        {MANUAL_TRANSLATIONS_PROMPT}

        Rispondi SOLO in JSON valido nel formato richiesto dalla funzione.
        """}
    ]

    # Generazione dinamica dei parametri dello schema JSON in base alle sole lingue mancanti
    functions = [
        {
            "name": "translate_text",
            "description": "Traduci il testo italiano nelle lingue specificate, mantenendo maiuscole, punteggiatura e nomi propri",
            "parameters": {
                "type": "object",
                "properties": {lang: {"type": "string"} for lang in target_langs},
                "required": target_langs
            }
        }
    ]

    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        functions=functions,
        function_call={"name": "translate_text"},
        temperature=0
    )

    message = response.choices[0].message
    func_call = getattr(message, "function_call", None)
    
    if func_call and hasattr(func_call, "arguments"):
        return json.loads(func_call.arguments)

    return {lang: term for lang in target_langs}

async def enrich_vocab_with_ui(
    vocab,
    target_langs,
    progress_bar,
    status_text,
    timer_text,
    ws,
    saved_badge,
    df,
    cols_to_translate
):
    start_time = time.time()
    
    st.markdown("### 📋 Log Avanzamento Sincronizzazione")
    log_area = st.empty()
    logs = ["🎬 Avvio allineamento database con logica a specchio..."]
    
    def log_msg(msg):
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        log_area.code("\n".join(logs[-10:]))

    # Mappatura nativa delle colonne su Google Sheets (IT=1, EN=2, FR=3, DE=4, ES=5, Colonna=6)
    COL_MAPPING = {"en": 2, "fr": 3, "de": 4, "es": 5}

    # BUFFER UNIFICATO CONTINUO (Batch size = 25)
    buffer_cell_updates = []  # Struttura: [{'range': '...', 'values': [[...]]}]
    buffer_new_rows = []      # Struttura: [[valori_riga], ...]

    async def flush_all_buffers(fase_label):
        """Invia i dati accumulati nel buffer continuo su Google Sheets"""
        if buffer_cell_updates:
            try:
                log_msg(f"⏳ [{fase_label}] Invio batch di {len(buffer_cell_updates)} celle modificate su Google Sheets...")
                ws.batch_update(buffer_cell_updates, value_input_option="RAW")
                buffer_cell_updates.clear()
                await asyncio.sleep(0.8)  # Pausa di sicurezza anti-quota
            except Exception as e:
                log_msg(f"❌ Errore batch_update [{fase_label}]: {e}")

        if buffer_new_rows:
            try:
                log_msg(f"⏳ [{fase_label}] Inserimento di {len(buffer_new_rows)} nuove righe sul foglio...")
                ws.append_rows(buffer_new_rows, value_input_option="RAW")
                buffer_new_rows.clear()
                await asyncio.sleep(0.8)  # Pausa di sicurezza anti-quota
            except Exception as e:
                log_msg(f"❌ Errore append_rows [{fase_label}]: {e}")

    def clean_val(val):
        if pd.isna(val) or val is None:
            return ""
        s = str(val).strip()
        return "" if s.lower() == "nan" else s

    # ========================================================
    # LOGICA 1 & 2: UNIONE DEGLI INPUT ED ESTRAZIONE TERMINI REALI
    # ========================================================
    log_msg("📂 FASE 1: Riconciliazione e fusione dati (Input vs Google Sheets)...")
    
    file_vocab = {}
    for _, row in df.iterrows():
        for col in cols_to_translate:
            if col in df.columns:
                it_val = clean_val(row[col])
                if not it_val:
                    continue
                
                base = get_base_name(col)
                if it_val not in file_vocab:
                    file_vocab[it_val] = {
                        "translations": {lang: "" for lang in target_langs},
                        "col_name": col
                    }
                
                # Raccoglie le lingue presenti nel file di input
                for lang in target_langs:
                    lang_col = f"{base} ({lang})"
                    if lang_col in df.columns:
                        v_file = clean_val(row[lang_col])
                        if v_file:
                            file_vocab[it_val]["translations"][lang] = v_file

    # ========================================================
    # LOGICA 3 & 4: CONFRONTO CHIRURGICO CELLA PER CELLA
    # ========================================================
    terms_to_translate_ai = {}
    count_file_changes = 0

    for it_val, file_info in file_vocab.items():
        clean_col = re.sub(r'\s*\([^)]*\)', '', str(file_info["col_name"])).strip()
        
        if it_val in vocab:
            # Il termine esiste sul foglio Google
            row_num = vocab[it_val].get("row_number")
            gsheet_langs = vocab[it_val].get("translations", {})
            ai_langs_for_term = []
            
            for lang in target_langs:
                val_file = file_info["translations"].get(lang, "")
                val_gsheet = clean_val(gsheet_langs.get(lang, ""))
                
                # 3. Vuoto nel file di input, ma presente nel foglio -> lo preserviamo in memoria senza toccare il foglio
                if not val_file and val_gsheet:
                    vocab[it_val]["translations"][lang] = val_gsheet
                
                # 4. Presente nel file di input ed è DIVERSO dal foglio -> va nel buffer di aggiornamento immediato
                elif val_file and val_file != val_gsheet:
                    col_idx = COL_MAPPING.get(lang.lower())
                    if col_idx and row_num:
                        col_letter = chr(64 + col_idx)
                        buffer_cell_updates.append({
                            "range": f"{col_letter}{row_num}",
                            "values": [[val_file]]
                        })
                        vocab[it_val]["translations"][lang] = val_file
                        count_file_changes += 1
                
                # 4b. Uguali -> ignoriamo completamente
                elif val_file and val_file == val_gsheet:
                    continue
                
                # 5. Vuoto sia nel file che nel foglio -> lo marchiamo per l'AI
                elif not val_file and not val_gsheet:
                    ai_langs_for_term.append(lang)
            
            if ai_langs_for_term:
                terms_to_translate_ai[it_val] = {
                    "col_name": file_info["col_name"],
                    "langs": ai_langs_for_term
                }
        else:
            # Il termine è completamente nuovo rispetto al foglio Google
            vocab[it_val] = {
                "translations": file_info["translations"].copy(),
                "row_number": None
            }
            ai_langs_for_term = [lang for lang in target_langs if not file_info["translations"].get(lang, "")]
            
            if ai_langs_for_term:
                terms_to_translate_ai[it_val] = {
                    "col_name": file_info["col_name"],
                    "langs": ai_langs_for_term
                }
            else:
                # Se è già completo dall'input, lo carichiamo come riga nuova intera
                t = file_info["translations"]
                buffer_new_rows.append([it_val, t.get("en", ""), t.get("fr", ""), t.get("de", ""), t.get("es", ""), clean_col])
                count_file_changes += 1

        # Scarico intermedio del buffer continuo se raggiunge i 25 elementi già in questa fase
        if (len(buffer_cell_updates) + len(buffer_new_rows)) >= SAVE_TRANSLATE_EVERY:
            await flush_all_buffers("Allineamento File")

    log_msg(f"✅ Riconciliazione completata. Rilevate {count_file_changes} variazioni reali dai file.")

    # ========================================================
    # LOGICA 5 & 6: GENERAZIONE AI SULLO STESSO BUFFER CONTINUO
    # ========================================================
    total_ai = len(terms_to_translate_ai)
    if total_ai > 0:
        log_msg(f"🤖 FASE 2: Avvio traduzione AI per {total_ai} termini veramente orfani...")
        
        for i, (term, info) in enumerate(terms_to_translate_ai.items(), start=1):
            key = term.strip()
            col_name = info["col_name"]
            langs_to_translate = info["langs"]

            elapsed = time.time() - start_time
            avg_time = elapsed / i
            remaining = avg_time * (total_ai - i)

            progress_bar.progress(i / total_ai)
            status_text.text(f"🔤 Traduzione AI: {key[:20]}... ({i}/{total_ai})")
            timer_text.text(f"⏱️ Trascorso: {format_time(elapsed)} | Rimasto: {format_time(remaining)}")

            try:
                log_msg(f"🧠 Chiamata OpenAI ({i}/{total_ai}) per: '{key[:25]}...'")
                translations = await translate_term(term, langs_to_translate, col_name)
                for lang in langs_to_translate:
                    vocab[key]["translations"][lang] = translations.get(lang, "")
            except Exception as e:
                log_msg(f"❌ Errore OpenAI su '{key[:20]}...': {e}")
                continue

            clean_col = re.sub(r'\s*\([^)]*\)', '', col_name).strip()
            t = vocab[key]["translations"]
            row_num = vocab[key].get("row_number")
            
            if row_num is not None:
                # Record esistente: iniettiamo nel buffer solo le singole celle generate dall'AI
                for lang in langs_to_translate:
                    val_ai = t.get(lang, "")
                    col_idx = COL_MAPPING.get(lang.lower())
                    if val_ai and col_idx:
                        col_letter = chr(64 + col_idx)
                        buffer_cell_updates.append({
                            "range": f"{col_letter}{row_num}",
                            "values": [[val_ai]]
                        })
            else:
                # Record nuovo completato dall'AI: va in append_rows come riga intera
                row_data = [key, t.get("en", ""), t.get("fr", ""), t.get("de", ""), t.get("es", ""), clean_col]
                buffer_new_rows.append(row_data)

            # IL BUFFER CONTA IL CUMULATIVO TOTALE: Scatta rigidamente ogni 25 elementi (File + AI)
            if (len(buffer_cell_updates) + len(buffer_new_rows)) >= SAVE_TRANSLATE_EVERY:
                await flush_all_buffers("Blocco Intermedio AI")
                saved_badge.markdown(f"💾 **Traduzioni salvate nel foglio ({i}/{total_ai})**")
    else:
        log_msg("ℹ️ FASE 2: Nessun termine orfano da inviare ad OpenAI (0 mancanti).")
        status_text.text("ℹ️ Nessun termine da tradurre con l'AI.")

    # SVUOTAMENTO FINALE DEI RESIDUI RIMASTI NEL BUFFER CONTINUO
    if buffer_cell_updates or buffer_new_rows:
        await flush_all_buffers("Residui Finali Sincronizzazione")

    log_msg("🏁 Processo concluso con successo.")
    progress_bar.progress(1.0)
    saved_badge.markdown(f"✅ **Sincronizzazione completata!**")
    status_text.text("✅ Google Sheets aggiornato senza sprechi di quota.")

def extract_missing_terms(df, columns, vocab, target_langs):
    """
    Analizza le colonne (it). Se nel df sono presenti le colonne delle lingue estere,
    recupera le traduzioni esistenti. Se mancano o sono vuote, controlla su Google Sheets.
    Se mancano ovunque, le passa all'AI.
    """
    missing = {}
    
    for col in columns:
        if col in df.columns:
            # Estraiamo il nome pulito senza la dicitura " (it)"
            base_col_name = col.replace(" (it)", "").strip()
            
            for idx, row in df.iterrows():
                if pd.isna(row[col]):
                    continue
                
                key = str(row[col]).strip()
                if key == "" or key in MANUAL_TRANSLATIONS:
                    continue

                # Se il termine non è presente nel vocabolario, lo inizializziamo
                if key not in vocab:
                    vocab[key] = {
                        "translations": {lang: "" for lang in target_langs},
                        "row_number": None
                    }

                langs_to_translate = []
                
                for lang in target_langs:
                    csv_lang_col = f"{base_col_name} ({lang})"
                    csv_translation = ""
                    
                    # 1. Controlliamo se la colonna della lingua esiste ed è popolata nel CSV
                    if csv_lang_col in df.columns and pd.notna(row[csv_lang_col]):
                        csv_translation = str(row[csv_lang_col]).strip()

                    # 2. Se c'è una traduzione nel CSV, la importiamo in memoria e saltiamo l'AI
                    if csv_translation != "":
                        vocab[key]["translations"][lang] = csv_translation
                        continue

                    # 3. Se la colonna non esiste nel CSV o la cella è vuota, guardiamo Google Sheets
                    saved_langs = vocab[key]["translations"]
                    if lang not in saved_langs or pd.isna(saved_langs[lang]) or str(saved_langs[lang]).strip() == "":
                        # Manca ovunque: segnamo come da tradurre con AI
                        langs_to_translate.append(lang)

                # Se ci sono lingue scoperte per questa stringa, la passiamo alla coda dei mancanti
                if langs_to_translate:
                    if key in missing:
                        missing[key]["langs"] = list(set(missing[key]["langs"] + langs_to_translate))
                    else:
                        missing[key] = {
                            "col_name": col,
                            "langs": langs_to_translate
                        }
                        
    return missing

LANG_RE = re.compile(r"\(([^)]+)\)$")

def get_base_name(col):
    return LANG_RE.sub("", col).strip()

def get_lang(col):
    m = LANG_RE.search(col)
    return m.group(1).lower() if m else None

#def apply_translations(df, columns, langs, vocab):
#    dfs_by_lang = {}
#    selected_bases = {get_base_name(c) for c in columns}
#
#    rows_to_drop = set()
#    col_list = list(df.columns)
#    for idx, col in enumerate(col_list):
#        base = get_base_name(col)
#        lang = get_lang(col)
#
#        if base in selected_bases and lang == "it":
#            if idx + 1 < len(col_list):
#                next_col = col_list[idx + 1]
#                next_lang = get_lang(next_col)
#                if next_lang != "it":
#                    populated_rows = df[next_col].notna() & (df[next_col].astype(str).str.strip() != "")
#                    rows_to_drop.update(df.index[populated_rows])
#
#    for lang in langs:
#        df_lang = df.copy()
#        if rows_to_drop:
#            df_lang.drop(index=list(rows_to_drop), inplace=True)
#
#        for col in df_lang.columns:
#            col_lang = get_lang(col)
#            base = get_base_name(col)
#
#            if not col_lang or col_lang == "it":
#                continue
#
#            if base in selected_bases:
#                it_col = col.replace(f"({col_lang})", "(it)")
#                if it_col in df_lang.columns:
#                    def translate_cell(val):
#                        if pd.isna(val):
#                            return ""
#                        key = str(val).strip()
#                        return vocab.get(key, {}).get(lang, key)
#                    df_lang[col] = df_lang[it_col].apply(translate_cell)
#                else:
#                    df_lang[col] = df_lang[col].fillna("")
#
#            new_col = re.sub(LANG_RE, f"({lang})", col)
#            df_lang.rename(columns={col: new_col}, inplace=True)
#
#        dfs_by_lang[lang] = df_lang
#
#    return dfs_by_lang

def apply_translations(df, columns, langs, vocab):
    dfs_by_lang = {}
    selected_bases = {get_base_name(c) for c in columns}

    for lang in langs:
        df_lang = df.copy()
        
        # 1. Identifichiamo tutte le colonne delle ALTRE lingue estere nate dal merge dei 4 file
        # Se stiamo creando il file per 'de', vogliamo eliminare 'en', 'fr', 'es' per non sporcare l'output
        other_langs_cols = [
            col for col in df_lang.columns 
            if any(col.endswith(f"({l})") for l in AVAILABLE_LANGS if l != lang)
        ]
        df_lang.drop(columns=other_langs_cols, errors='ignore', inplace=True)

        # 2. Cancelliamo la colonna target (es. '(de)') se era già presente, per rigenerarla pulita
        cols_already_present = [col for col in df_lang.columns if col.endswith(f"({lang})")]
        df_lang.drop(columns=cols_already_present, errors='ignore', inplace=True)

        # 3. Rigeneriamo la colonna della lingua partendo dall'italiano
        cols_to_drop = []
        for col in df.columns:
            base = get_base_name(col)
            col_lang = get_lang(col)

            if base in selected_bases and col_lang == "it":
                new_col_name = f"{base} ({lang})"
                
                def translate_cell(val):
                    if pd.isna(val):
                        return ""
                    key = str(val).strip()
                    if key in vocab:
                        res = vocab[key]["translations"].get(lang, "")
                        return res if res != "" else key
                    return key
              
                df_lang[new_col_name] = df_lang[col].apply(translate_cell)
                cols_to_drop.append(col)
        
        # Elimina le colonne (it) se l'output finale deve contenere solo la lingua target, 
        # oppure commenta questa riga se vuoi mantenere sia (it) che (lingua_target) nel file finale
        df_lang.drop(columns=cols_to_drop, errors='ignore', inplace=True)
        
        dfs_by_lang[lang] = df_lang

    return dfs_by_lang

# =========================================================
# Google Translator logic (originally from descrizioni)
# =========================================================

def find_translation(db, text_it, target_lang):
    text_it = str(text_it).strip().lower()
    for entry in db:
        if entry.get("it", "").strip().lower() == text_it:
            return entry.get(target_lang)
    return None

def add_translation(db, text_it, lang, translated_text):
    text_it = str(text_it).strip()
    for entry in db:
        if entry.get("it", "").strip().lower() == text_it.lower():
            entry[lang] = translated_text
            break
    else:
        db.append({"it": text_it, lang: translated_text})

def safe_translate(text, translator, db):
    time.sleep(0.1)
    try:
        if not text or str(text).strip() == "":
            return ""

        text_it = str(text).strip()
        target_lang = translator.target

        cached = find_translation(db, text_it, target_lang)
        if cached:
            return cached

        translated = translator.translate(text_it)
        add_translation(db, text_it, target_lang, translated)
        return translated

    except Exception as e:
        print(f"❌ Errore durante la traduzione: {e}")
        return str(text)

def translate_column_parallel(col_values, source, target, db, max_workers=5):
    translator = GoogleTranslator(source=source, target=target)
    results = [None] * len(col_values)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(safe_translate, text, translator, db): i for i, text in enumerate(col_values)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"Errore riga {idx}: {e}")
                results[idx] = str(col_values[idx])

    return results

def download_translation_db_from_github():
    github_token = st.secrets.get("GITHUB_TOKEN")
    if not github_token:
        return []

    GITHUB_REPO = "MarcoRipari/Gestione-Ecom"
    GITHUB_PATH = "data/translations_db.json"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {github_token}"}

    try:
        import base64
        import requests
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            if "content" in data:
                content = base64.b64decode(data["content"]).decode("utf-8")
                return json.loads(content)
        return []
    except Exception:
        return []

def upload_translation_db_to_github(db, original_db_json):
    github_token = st.secrets.get("GITHUB_TOKEN")
    if not github_token:
        return

    GITHUB_REPO = "MarcoRipari/Gestione-Ecom"
    GITHUB_PATH = "data/translations_db.json"
    GITHUB_BRANCH = "main"

    new_db_json = json.dumps(db, ensure_ascii=False, indent=2)
    if new_db_json == original_db_json:
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {github_token}"}

    try:
        import base64
        import requests
        content = base64.b64encode(new_db_json.encode("utf-8")).decode("utf-8")

        sha = None
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            sha = r.json().get("sha")

        data = {
            "message": "Aggiornamento automatico del DB traduzioni",
            "content": content,
            "branch": GITHUB_BRANCH,
        }
        if sha:
            data["sha"] = sha

        requests.put(url, headers=headers, json=data)
    except Exception:
        pass

def update_gspread_cell(ws, term, lang, translation):
    """
    Cerca la riga del termine italiano e aggiorna la colonna della lingua specifica.
    """
    try:
        # Trova la cella del termine italiano
        cell = ws.find(term)
        if cell:
            row = cell.row
            # Mappa delle colonne (IT=1, EN=2, FR=3, DE=4, ES=5 basato su vocab_to_rows)
            col_mapping = {"en": 2, "fr": 3, "de": 4, "es": 5}
            col = col_mapping.get(lang.lower())
            
            if col:
                ws.update_cell(row, col, translation)
    except Exception as e:
        print(f"Errore durante l'aggiornamento della cella per {term}: {e}")
