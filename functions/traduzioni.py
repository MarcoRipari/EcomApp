import streamlit as st
import re
import json
import asyncio
import time
import os
import io
import pandas as pd
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

    for _, row in df.iterrows():
        it = str(row["it"]).strip()
        vocab[it] = {
            lang: row.get(lang)
            for lang in row.index
            if lang != "it" and pd.notna(row.get(lang))
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
        Traduci questo testo italiano nelle lingue: {', '.join(target_langs)}.
        Mantieni maiuscole e punteggiatura come nell'originale.
        NON usare abbreviazioni, ellissi o forme contratte (es. niente “-sohle”, “-lining”, ecc.)
        {important_note}

        Testo da tradurre:
        \"\"\"{term}\"\"\"

        {MANUAL_TRANSLATIONS_PROMPT}

        Rispondi SOLO in JSON valido nel formato:
        {{
          "en": "...",
          "fr": "...",
          "de": "...",
          "es": "..."
        }}
        """}
    ]

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
    st.write(messages)
    st.write(response)

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
    buffer = []
    saved_count = 0

    for i, (term, col_name) in enumerate(missing_terms.items(), start=1):
        key = term.strip()

        elapsed = time.time() - start_time
        avg_time = elapsed / i
        remaining = avg_time * (total - i)

        progress_bar.progress(i / total)
        saved_badge.markdown(f"💾 **Salvate su Google:** {saved_count}")
        status_text.text(f"🔤 Traduzione: {term} ({i}/{total})")
        timer_text.text(
            f"⏱️ Trascorso: {format_time(elapsed)} | "
            f"Stimato: {format_time(remaining)}"
        )

        if key in MANUAL_TRANSLATIONS:
            vocab[key] = {lang: MANUAL_TRANSLATIONS[key].get(lang, term) for lang in target_langs}
        else:
            try:
                translations = await translate_term(term, target_langs, col_name)
                st.write(translations)
                vocab[key] = translations
            except Exception as e:
                st.warning(f"Errore traduzione '{term}': {e}")
                vocab[key] = {lang: "" for lang in target_langs}

        buffer.append({
            "it": key,
            **vocab[key],
            "source_col": col_name
        })

        if len(buffer) >= SAVE_TRANSLATE_EVERY:
            append_vocab_rows(ws, buffer)
            saved_count += len(buffer)
            saved_badge.markdown(f"💾 **Salvate su Google:** {saved_count}")
            buffer.clear()

    if buffer:
        append_vocab_rows(ws, buffer)
        saved_count += len(buffer)
        saved_badge.markdown(f"💾 **Salvate su Google:** {saved_count}")

def extract_missing_terms(df, columns, vocab):
    missing = {}
    for col in columns:
        if col in df.columns:
            for value in df[col].dropna():
                key = str(value).strip()
                if key not in vocab and key not in MANUAL_TRANSLATIONS:
                    missing[key] = col
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
    """
    Prende le colonne italiane selezionate, genera le rispettive colonne 
    tradotte per ogni lingua e rimuove la vecchia colonna italiana dal file finale.
    """
    dfs_by_lang = {}
    
    # Puliamo i nomi delle colonne selezionate per ottenere la base (es. "Variante")
    selected_bases = {get_base_name(c) for c in columns}

    for lang in langs:
        # Creiamo una copia pulita del DataFrame originale per questa specifica lingua
        df_lang = df.copy()
        cols_to_drop = []

        for col in df.columns:
            base = get_base_name(col)
            col_lang = get_lang(col)

            # Processiamo solo le colonne che l'utente ha selezionato e che sono in italiano
            if base in selected_bases and col_lang == "it":
                new_col_name = f"{base} ({lang})"
                
                # Funzione interna per tradurre la singola cella usando il vocab
                def translate_cell(val):
                    if pd.isna(val):
                        return ""
                    key = str(val).strip()
                    
                    # Cerca nel dizionario; se non trova la lingua, rimette l'italiano come fallback
                    return vocab.get(key, {}).get(lang, key)
                
                # Applichiamo la traduzione sulla nuova colonna (es. "Variante (en)")
                df_lang[new_col_name] = df_lang[col].apply(translate_cell)
                
                # Memorizziamo la colonna italiana corrente per rimuoverla alla fine
                cols_to_drop.append(col)
        
        # Rimuoviamo dal foglio finale le colonne in italiano per non avere doppioni
        df_lang.drop(columns=cols_to_drop, errors='ignore', inplace=True)
        
        # Salva il dataframe tradotto nel dizionario
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
