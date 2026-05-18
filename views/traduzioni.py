import re


AVAILABLE_LANGS = ["en", "fr", "de", "es"]
OPENAI_MODEL = "gpt-4o-mini"
SAVE_TRANSLATE_EVERY = 25  # batch size consigliato

TRANSLATION_SHEET_ID = "1wS65klpyHNft8UpJAE1x1yIVa1_8ZRLftFnUBgW_f6o"
TRANSLATION_TAB_NAME = "Traduzioni"

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

# =========================
# UTILS
# =========================
def normalize(text: str) -> str:
    return text.strip().lower()
    
def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.create_task(coro)

def safe_json_loads(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # cerca il primo blocco JSON {...}
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        # se non trova JSON valido, fallback con traduzione originale in tutte le lingue
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
    """
    rows = lista di dict {"it": ..., "en": ..., "fr": ..., "de": ..., "es": ...}
    """
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
        
# =========================
# VOCABULARY
# =========================
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


# =========================
# OPENAI TRANSLATION
# =========================
async def translate_term(client, term, target_langs, col_name):
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

    message = response.choices[0].message  # ChatCompletionMessage object

    # Accesso corretto a function_call
    func_call = getattr(message, "function_call", None)
    if func_call and hasattr(func_call, "arguments"):
        return json.loads(func_call.arguments)

    # fallback in caso di errore
    return {lang: term for lang in target_langs}


async def enrich_vocab_with_ui(
    client,
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

    #for i, term in enumerate(missing_terms, start=1):
    for i, (term, col_name) in enumerate(missing_terms.items(), start=1):
        #key = term.strip().lower()  # normalizzazione chiave
        key = term.strip()

        # TIMER E PROGRESS BAR
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

        # OVERRIDE MANUALE
        if key in MANUAL_TRANSLATIONS:
            vocab[key] = {lang: MANUAL_TRANSLATIONS[key].get(lang, term) for lang in target_langs}
            continue

        # CHIAMATA GPT FUNCTION CALL
        try:
            translations = await translate_term(client, term, target_langs, col_name)
            vocab[key] = translations
        except Exception as e:
            st.warning(f"Errore traduzione '{term}': {e}")
            # fallback: testo originale in tutte le lingue
            #vocab[key] = {lang: term for lang in target_langs}
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

# =========================
# CSV TRANSLATION
# =========================
def extract_missing_terms(df, columns, vocab):
    #missing = set()
    missing = {}

    for col in columns:
        for value in df[col].dropna():
            key = str(value).strip()  # ✅ NON più .lower()
            if key not in vocab and key not in MANUAL_TRANSLATIONS:
                missing[key] = col

    return missing

LANG_RE = re.compile(r"\(([^)]+)\)$")

def get_base_name(col):
    # "Variante (it)" -> "Variante"
    return LANG_RE.sub("", col).strip()

def get_lang(col):
    m = LANG_RE.search(col)
    return m.group(1).lower() if m else None

def apply_translations(df, columns, langs, vocab):
    """
    Ritorna dict {lang: df}
    - Esclude righe che nel CSV originale hanno valore popolato nella colonna dopo
      una colonna selezionata (it)
    """
    dfs_by_lang = {}

    # colonne base selezionate (Variante, Colore, ecc.)
    selected_bases = {get_base_name(c) for c in columns}

    # ------------------------
    # TROVA RIGHE DA ESCLUDERE
    # ------------------------
    rows_to_drop = set()
    col_list = list(df.columns)
    for idx, col in enumerate(col_list):
        base = get_base_name(col)
        lang = get_lang(col)

        # solo colonne selezionate (it)
        if base in selected_bases and lang == "it":
            # colonna successiva
            if idx + 1 < len(col_list):
                next_col = col_list[idx + 1]
                next_lang = get_lang(next_col)
                # se la colonna successiva NON-it e popolata → scarta riga
                if next_lang != "it":
                    populated_rows = df[next_col].notna() & (df[next_col].astype(str).str.strip() != "")
                    rows_to_drop.update(df.index[populated_rows])

    # ------------------------
    # CREAZIONE CSV PER OGNI LINGUA
    # ------------------------
    for lang in langs:
        df_lang = df.copy()

        # elimina righe da scartare
        if rows_to_drop:
            df_lang.drop(index=list(rows_to_drop), inplace=True)

        # traduzioni e rinomina colonne
        for col in df_lang.columns:
            col_lang = get_lang(col)
            base = get_base_name(col)

            # colonne senza lingua o colonne (it) → lasciale così
            if not col_lang or col_lang == "it":
                continue

            # colonne selezionate → traduci
            if base in selected_bases:
                it_col = col.replace(f"({col_lang})", "(it)")
                if it_col in df_lang.columns:
                    def translate_cell(val):
                        if pd.isna(val):
                            return ""
                        key = str(val).strip()
                        return vocab.get(key, {}).get(lang, key)
                    df_lang[col] = df_lang[it_col].apply(translate_cell)
                else:
                    df_lang[col] = df_lang[col].fillna("")
            else:
                df_lang[col] = df_lang[col]

            # rinomina colonna con lingua corrente
            new_col = re.sub(LANG_RE, f"({lang})", col)
            df_lang.rename(columns={col: new_col}, inplace=True)

        dfs_by_lang[lang] = df_lang

    return dfs_by_lang


def download_translation_db_from_github():
    """Scarica il file JSON delle traduzioni da GitHub e lo restituisce come oggetto Python"""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("⚠️ Nessun GITHUB_TOKEN trovato tra i secrets.")
        return []

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {github_token}"}

    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            if "content" in data:
                content = base64.b64decode(data["content"]).decode("utf-8")
                print("✅ DB traduzioni caricato da GitHub.")
                return json.loads(content)
            else:
                print("⚠️ Nessun contenuto trovato nel file GitHub.")
                return []
        elif r.status_code == 404:
            print("⚠️ File delle traduzioni non trovato su GitHub. Creerò un nuovo DB.")
            return []
        else:
            print(f"⚠️ Errore scaricando DB da GitHub: {r.status_code} - {r.text}")
            return []
    except Exception as e:
        print(f"❌ Errore durante il download del DB: {e}")
        return []


def upload_translation_db_to_github(db, original_db_json):
    """Carica o aggiorna il file delle traduzioni su GitHub solo se ci sono modifiche"""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("⚠️ Nessun GITHUB_TOKEN trovato tra i secrets. Upload annullato.")
        return

    # 🔍 Confronto con il contenuto originale
    new_db_json = json.dumps(db, ensure_ascii=False, indent=2)
    if new_db_json == original_db_json:
        print("ℹ️ Nessuna nuova traduzione aggiunta: nessun upload necessario.")
        return  # Non aggiorna GitHub se identico

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {github_token}"}

    try:
        content = base64.b64encode(new_db_json.encode("utf-8")).decode("utf-8")

        # Ottieni SHA del file esistente (necessario per aggiornamento)
        sha = None
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            sha = r.json().get("sha")

        message = "Aggiornamento automatico del DB traduzioni"
        data = {
            "message": message,
            "content": content,
            "branch": GITHUB_BRANCH,
        }
        if sha:
            data["sha"] = sha  # necessario se il file esiste già

        r = requests.put(url, headers=headers, json=data)

        if r.status_code in (200, 201):
            print("✅ File delle traduzioni aggiornato su GitHub!")
        else:
            print(f"❌ Errore aggiornando su GitHub: {r.status_code} - {r.text}")

    except Exception as e:
        print(f"❌ Errore durante l'upload su GitHub: {e}")


# =========================================================
# 🧩 FUNZIONI DI GESTIONE DEL DB (IN MEMORIA)
# =========================================================

def find_translation(db, text_it, target_lang):
    """Cerca una traduzione esistente nel DB"""
    text_it = str(text_it).strip().lower()
    for entry in db:
        if entry.get("it", "").strip().lower() == text_it:
            return entry.get(target_lang)
    return None


def add_translation(db, text_it, lang, translated_text):
    """Aggiunge o aggiorna una traduzione nel DB (solo in memoria)"""
    text_it = str(text_it).strip()
    for entry in db:
        if entry.get("it", "").strip().lower() == text_it.lower():
            entry[lang] = translated_text
            break
    else:
        db.append({"it": text_it, lang: translated_text})


# =========================================================
# 🧠 FUNZIONI DI TRADUZIONE
# =========================================================

def create_translator(source, target):
    return GoogleTranslator(source=source, target=target)


def safe_translate(text, translator, db):
    """Traduci testo con gestione errori e uso del DB GitHub"""
    time.sleep(0.1)
    try:
        if not text or str(text).strip() == "":
            return ""

        text_it = str(text).strip()
        target_lang = translator.target

        # 1️⃣ Controlla se esiste già nel DB
        cached = find_translation(db, text_it, target_lang)
        if cached:
            return cached

        # 2️⃣ Se non esiste → traduci e aggiungi
        translated = translator.translate(text_it)
        add_translation(db, text_it, target_lang, translated)
        return translated

    except Exception as e:
        print(f"❌ Errore durante la traduzione: {e}")
        return str(text)


def translate_column_parallel(col_values, source, target, db, max_workers=5):
    """Traduci una colonna mantenendo l'ordine originale"""
    translator = create_translator(source, target)
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
  

def genera_traduzioni():
    st.title("🌍 CSV Translator Async2")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])
    
    if uploaded_file:
        df = read_csv_auto_encoding(uploaded_file)
    
        st.subheader("Seleziona colonne da tradurre")
        cols_to_translate = st.multiselect(
            "Colonne",
            df.columns.tolist()
        )
    
        st.subheader("Seleziona lingue")
        target_langs = st.multiselect(
            "Lingue",
            AVAILABLE_LANGS,
            default=AVAILABLE_LANGS
        )
    
        if st.button("🚀 Avvia traduzione") and cols_to_translate and target_langs:
            with st.spinner("Caricamento vocabolario..."):
                vocab, vocab_df = load_vocab(TRANSLATION_SHEET_ID, TRANSLATION_TAB_NAME)
    
            with st.spinner("Analisi termini mancanti..."):
                missing_terms = extract_missing_terms(df, cols_to_translate, vocab)
    
            st.info(f"Termini da tradurre: {len(missing_terms)}")
    
            if missing_terms:
                with st.spinner("Traduzione OpenAI in corso..."):
                    ws = get_sheet(TRANSLATION_SHEET_ID, TRANSLATION_TAB_NAME)
                    progress_bar = st.progress(0)
                    saved_badge = st.empty()
                    status_text = st.empty()
                    timer_text = st.empty()
    
                    task = run_async(
                        enrich_vocab_with_ui(
                            client,
                            vocab,
                            missing_terms,
                            target_langs,
                            progress_bar,
                            status_text,
                            timer_text,
                            ws,
                            saved_badge
                        )
                    )
                    
                    if asyncio.isfuture(task):
                        asyncio.get_event_loop().run_until_complete(task)
                    progress_bar.progress(1.0)
                    status_text.text("✅ Traduzione completata")
                    timer_text.text("")
            with st.spinner("Applicazione traduzioni al CSV..."):
                dfs_by_lang = apply_translations(df, cols_to_translate, target_langs, vocab)
    
                
            st.success("✅ Traduzione completata")
            
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for lang, df_lang in dfs_by_lang.items():
                    csv_buffer = io.StringIO()
                    df_lang.to_csv(csv_buffer, index=False)
            
                    zipf.writestr(
                        f"descrizioni_{lang}.csv",
                        csv_buffer.getvalue()
                    )
            
            zip_buffer.seek(0)
            
            #csv_buffer = io.StringIO()
            #df_out.to_csv(csv_buffer, index=False)
            #csv_bytes = csv_buffer.getvalue().encode("utf-8")
            
            now = datetime.now(ZoneInfo("Europe/Rome"))
            file_name = f"traduzioni_{now.strftime('%d-%m-%Y_%H-%M-%S')}.zip"
            # Carico il file su dropbox
            try:
                folder_path = "/CATALOGO/TRADUZIONI"  # cartella su Dropbox
                access_token = get_dropbox_access_token()
                dbx = dropbox.Dropbox(access_token)
                upload_to_dropbox(dbx, folder_path, file_name, zip_buffer.getvalue())
            except Exception as e:
                st.error(f"❌ Errore durante l'upload su Dropbox: {e}")
                            
            st.download_button(
                "📦 Scarica ZIP traduzioni",
                data=zip_buffer,
                file_name=file_name,
                mime="application/zip"
            )
