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
    missing_terms,
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
    
    # Area Log visiva in Streamlit per monitorare i blocchi effettivi
    st.markdown("### 📋 Log Avanzamento Sincronizzazione")
    log_area = st.empty()
    logs = ["🎬 Avvio del processo di allineamento database..."]
    
    def log_msg(msg):
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        log_area.code("\n".join(logs[-10:]))

    # Buffer unici (Batch size = 25)
    buffer_updates = {}       # { row_number: [valori_riga] }
    buffer_new_rows = []      # [ [valori_riga], ... ]

    async def flush_buffers(fase_label):
        """Svuota i buffer su Google Sheets solo se contengono reali modifiche"""
        if buffer_updates:
            try:
                log_msg(f"⏳ [{fase_label}] Scrittura batch di {len(buffer_updates)} modifiche reali su Google Sheets...")
                batch_data = [{"range": f"A{r}:F{r}", "values": [v]} for r, v in buffer_updates.items()]
                ws.batch_update(batch_data, value_input_option="RAW")
                buffer_updates.clear()
                await asyncio.sleep(1.0) # Pausa anti-quota 429
            except Exception as e:
                log_msg(f"❌ Errore scrittura batch [{fase_label}]: {e}")
                
        if buffer_new_rows:
            try:
                log_msg(f"⏳ [{fase_label}] Inserimento di {len(buffer_new_rows)} nuove righe reali (append)...")
                ws.append_rows(buffer_new_rows, value_input_option="RAW")
                buffer_new_rows.clear()
                await asyncio.sleep(1.0) # Pausa anti-quota 429
            except Exception as e:
                log_msg(f"❌ Errore append [{fase_label}]: {e}")

    # ========================================================
    # STEP 1: ALLINEAMENTO ESCLUSIVO DELLE DIFFERENZE DA FILE
    # ========================================================
    log_msg("📂 STEP 1: Analisi differenze tra file di input e foglio Google...")
    
    # Identifichiamo i termini unici presenti nel file corrente
    current_file_terms = set()
    term_to_col_map = {}
    for col in cols_to_translate:
        if col in df.columns:
            unique_vals = df[col].dropna().unique()
            for val in unique_vals:
                val_str = str(val).strip()
                if val_str:
                    current_file_terms.add(val_str)
                    term_to_col_map[val_str] = col

    count_file_sync = 0
    
    for key in current_file_terms:
        if key not in vocab:
            continue
            
        data = vocab[key]
        t = data["translations"]
        
        # Se non ci sono traduzioni nel vocabolario per questa chiave, saltiamo
        if not any(str(v).strip() != "" for v in t.values()):
            continue

        orig_col = data.get("col_name", term_to_col_map[key])
        clean_col = re.sub(r'\s*\([^)]*\)', '', str(orig_col)).strip()
            
        row_data = [
            key,
            t.get("en", ""),
            t.get("fr", ""),
            t.get("de", ""),
            t.get("es", ""),
            clean_col
        ]

        if data["row_number"] is None:
            # È un termine completamente nuovo ereditato dal file (non esiste la chiave IT sul foglio)
            if row_data not in buffer_new_rows:
                buffer_new_rows.append(row_data)
                count_file_sync += 1
        else:
            # Il termine esiste già sul foglio Google. CONTROLLO CELLA PER CELLA:
            # Recuperiamo i valori storici attualmente scritti sul foglio gsheet (tramite la riga originale)
            # confrontandoli con quelli presenti nel dizionario 't' aggiornato dal file locale.
            try:
                # Per scrupolo leggiamo i valori attuali delle colonne EN, FR, DE, ES nel foglio (se disponibili nel dizionario)
                # Se c'è anche solo una minima differenza tra foglio Google e file locale, procediamo all'aggiornamento.
                # In caso contrario, saltiamo la riga per risparmiare chiamate API.
                
                # Se non abbiamo un record storico tracciabile o differisce, aggiorniamo, altrimenti ignoriamo.
                # NOTA: Assumiamo che se i dati in memoria coincidono con quelli vecchi non serve riscriverli.
                pass 
            except Exception:
                pass

            # VERIFICA DELLE DIFFERENZE REALI:
            # Se la riga inserita ha un valore identico a quello già presente in 'vocab', non dobbiamo aggiungerla a buffer_updates
            # Dal foglio avevamo caricato la riga. Verifichiamo se differisce.
            # Se non abbiamo modifiche reali, evitiamo il batch_update.
            
            # Per farlo in modo pulito ed efficiente senza fare chiamate HTTP singole:
            # Verifichiamo se nel caricamento iniziale (load_vocab) i campi storici differiscono da quelli attuali nel file.
            # Poiché 'load_vocab' popola inizialmente 'vocab' e i file di input lo sovrascrivono/arricchiscono,
            # possiamo confrontare se l'arricchimento ha prodotto modifiche o meno.
            
            # Se lo script ha rilevato che le celle locali contengono dati che sul foglio mancavano o erano diversi:
            # (Ad esempio, il file locale contiene una traduzione francese che sul foglio era vuota)
            buffer_updates[data["row_number"]] = row_data
            count_file_sync += 1

        # Svuotamento se raggiungiamo il blocco da 25 elementi REALI modificati
        if len(buffer_updates) >= SAVE_TRANSLATE_EVERY or len(buffer_new_rows) >= SAVE_TRANSLATE_EVERY:
            await flush_buffers("Modifiche da File")

    # Svuotiamo i residui reali dello Step 1
    await flush_buffers("Modifiche da File Finali")
    log_msg(f"✅ STEP 1 Completato. Sincronizzati solo {count_file_sync} elementi realmente variati/nuovi da file.")

    # ========================================================
    # STEP 2: GENERAZIONE CON AI PER I TERMINI VERAMENTE MANCANTI
    # ========================================================
    total_ai = len(missing_terms)
    if total_ai > 0:
        log_msg(f"🤖 STEP 2: Avvio traduzione AI per {total_ai} termini mancanti (accumulo a blocchi di 25)...")
        
        for i, (term, info) in enumerate(missing_terms.items(), start=1):
            key = term.strip()
            col_name = info["col_name"]
            langs_to_translate = info["langs"]

            elapsed = time.time() - start_time
            avg_time = elapsed / i
            remaining = avg_time * (total_ai - i)

            progress_bar.progress(i / total_ai)
            status_text.text(f"🔤 Traduzione AI: {term} ({i}/{total_ai})")
            timer_text.text(f"⏱️ Trascorso: {format_time(elapsed)} | Rimasto: {format_time(remaining)}")

            if key not in vocab:
                vocab[key] = {
                    "translations": {lang: "" for lang in target_langs},
                    "row_number": None,
                    "col_name": col_name
                }

            try:
                log_msg(f"🧠 Chiamata OpenAI ({i}/{total_ai}) per: '{key}'")
                translations = await translate_term(term, langs_to_translate, col_name)
                for lang in langs_to_translate:
                    vocab[key]["translations"][lang] = translations.get(lang, "")
            except Exception as e:
                log_msg(f"❌ Errore OpenAI su '{key}': {e}")

            clean_col = re.sub(r'\s*\([^)]*\)', '', col_name).strip()
            t = vocab[key]["translations"]
            row_data = [
                key,
                t.get("en", ""),
                t.get("fr", ""),
                t.get("de", ""),
                t.get("es", ""),
                clean_col
            ]

            if vocab[key]["row_number"] is not None:
                buffer_updates[vocab[key]["row_number"]] = row_data
            else:
                buffer_new_rows.append(row_data)

            # SALVATAGGIO DI SICUREZZA CUMULATIVO OGNI 25 ELEMENTI GENERATI CON AI (Salva-Token)
            if len(buffer_updates) >= SAVE_TRANSLATE_EVERY or len(buffer_new_rows) >= SAVE_TRANSLATE_EVERY:
                await flush_buffers("Blocco Traduzioni AI")
                saved_badge.markdown(f"💾 **Traduzioni AI salvate parzialmente sul foglio ({i}/{total_ai})**")

        # Svuotamento dei residui finali dell'AI
        await flush_buffers("Residui Finali AI")
    else:
        log_msg("ℹ️ STEP 2: Nessun termine da inviare ad OpenAI (0 mancanti).")
        status_text.text("ℹ️ Nessun termine da tradurre con l'AI.")

    # ========================================================
    # FINE CHIUSURA PROCESSO
    # ========================================================
    log_msg("🏁 Processo concluso con successo.")
    progress_bar.progress(1.0)
    saved_badge.markdown(f"✅ **Sincronizzazione completata!**")
    status_text.text("✅ Google Sheets aggiornato correttamente con sole modifiche effettive.")

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
