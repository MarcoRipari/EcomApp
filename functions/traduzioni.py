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
    saved_badge
):
    total = len(missing_terms)
    start_time = time.time()
    
    # Buffer per la gestione a blocchi (batch)
    buffer_updates = {}       # { row_number: [valori_riga] } per righe esistenti
    buffer_new_rows = []      # [ [valori_riga], ... ] per nuovi record
    
    processed_in_batch = 0    # Contatore per far scattare il salvataggio ogni 25 iterazioni

    # 1. SEMAFORO: Limita a 15 le chiamate OpenAI concorrenti simultanee (evita errori 429)
    sem = asyncio.Semaphore(15)

    # 2. WORKER INTERNO: Avvolge la chiamata e restituisce i metadati insieme al risultato
    async def worker(term_key, term_info):
        async with sem:
            t_term = term_key.strip()
            t_col_name = term_info["col_name"]
            t_langs = term_info["langs"]
            try:
                translations = await translate_term(term_key, t_langs, t_col_name)
                return term_key, term_info, translations
            except Exception as e:
                return term_key, term_info, e

    # 3. CREAZIONE DEI TASK: Lanciamo tutte le traduzioni nello stesso istante
    tasks = [worker(term, info) for term, info in missing_terms.items()]

    # 4. LOOP CONCORRENTE: Intercettiamo i risultati nell'esatto momento in cui completano
    for i, future in enumerate(asyncio.as_completed(tasks), start=1):
        term, info, result = await future
        key = term.strip()
        col_name = info["col_name"]
        langs_to_translate = info["langs"]

        # Calcolo tempi ed aggiornamento UI (sarà fluidissimo perché i dati arrivano a raffiche)
        elapsed = time.time() - start_time
        avg_time = elapsed / i
        remaining = avg_time * (total - i)

        progress_bar.progress(i / total)
        status_text.text(f"🔤 Traduzione: {term} ({i}/{total})")
        timer_text.text(f"⏱️ Trascorso: {format_time(elapsed)} | Stimato: {format_time(remaining)}")

        # Inizializzazione della struttura in memoria se il termine è nuovo
        if key not in vocab:
            vocab[key] = {
                "translations": {lang: "" for lang in target_langs},
                "row_number": None
            }

        # Gestione dei risultati o degli errori del worker
        if isinstance(result, Exception):
            st.warning(f"Errore traduzione '{term}': {result}")
        else:
            for lang in langs_to_translate:
                vocab[key]["translations"][lang] = result.get(lang, "")

        # Prepariamo l'array dei dati per la riga del foglio Google
        t = vocab[key]["translations"]
        row_data = [
            key,
            t.get("en", ""),
            t.get("fr", ""),
            t.get("de", ""),
            t.get("es", ""),
            col_name if vocab[key]["row_number"] is None else col_name + " (aggiornato)"
        ]

        # Assegnazione al rispettivo buffer di blocco
        if vocab[key]["row_number"] is not None:
            buffer_updates[vocab[key]["row_number"]] = row_data
        else:
            buffer_new_rows.append(row_data)

        processed_in_batch += 1

        # ========================================================
        # SALVATAGGIO A BLOCCHI (ANTI-CRASH) - OGNI 25 ELEMENTI COMPLETATI
        # ========================================================
        if processed_in_batch >= SAVE_TRANSLATE_EVERY:
            status_text.text("💾 Salvataggio blocco su Google Sheets...")
            
            # 1. Svuota il batch delle righe modificate
            if buffer_updates:
                try:
                    batch_data = [
                        {"range": f"A{row_num}:F{row_num}", "values": [values]}
                        for row_num, values in buffer_updates.items()
                    ]
                    ws.batch_update(batch_data, value_input_option="RAW")
                    buffer_updates.clear()
                except Exception as e:
                    st.error(f"Errore salvataggio blocco aggiornamenti: {e}")

            # 2. Svuota il batch dei nuovi record
            if buffer_new_rows:
                try:
                    ws.append_rows(buffer_new_rows, value_input_option="RAW")
                    buffer_new_rows.clear()
                except Exception as e:
                    st.error(f"Errore salvataggio blocco nuovi record: {e}")

            saved_badge.markdown(f"💾 **Salvataggi intermedi completati alla riga {i}/{total}**")
            processed_in_batch = 0  # Resetta il contatore del blocco

    # ========================================================
    # SALVATAGGIO FINALE PER I RESIDUI RIMASTI FUORI DAL BLOCCO
    # ========================================================
    if buffer_updates or buffer_new_rows:
        status_text.text("💾 Salvataggio ultimi record rimasti...")
        
        if buffer_updates:
            try:
                batch_data = [
                    {"range": f"A{row_num}:F{row_num}", "values": [values]}
                    for row_num, values in buffer_updates.items()
                ]
                ws.batch_update(batch_data, value_input_option="RAW")
            except Exception as e:
                print(f"Errore nel batch finale: {e}")

        if buffer_new_rows:
            try:
                ws.append_rows(buffer_new_rows, value_input_option="RAW")
            except Exception as e:
                print(f"Errore nell'append finale: {e}")

    saved_badge.markdown(f"✅ **Sincronizzazione completata con successo!**")
    status_text.text("✅ Google Sheets aggiornato.")

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
