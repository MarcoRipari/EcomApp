import streamlit as st

from utils import *

LANG_NAMES = {
    "IT": "italiano",
    "EN": "inglese",
    "FR": "francese",
    "DE": "tedesco"
}
LANG_LABELS = {v.capitalize(): k for k, v in LANG_NAMES.items()}

desc_sheet_id = st.secrets["DESC_GSHEET_ID"]

def genera_descrizioni():
    st.header("📥 Caricamento CSV dei prodotti")
    
    uploaded = st.file_uploader("Carica un file CSV", type="csv")
    
    if uploaded:
        df_input = read_csv(uploaded)
        st.session_state["df_input"] = df_input
         # ✅ Inizializza variabili di stato se non esistono
        if "col_weights" not in st.session_state:
            st.session_state.col_weights = {}
        if "col_display_names" not in st.session_state:
            st.session_state.col_display_names = {}
        if "selected_cols" not in st.session_state:
            st.session_state.selected_cols = []
        if "config_ready" not in st.session_state:
            st.session_state.config_ready = False
        if "generate" not in st.session_state:
            st.session_state.generate = False
        st.success("✅ File caricato con successo!")

    # 📊 Anteprima dati
    if "df_input" in st.session_state:
        df_input = st.session_state.df_input
        st.subheader("🧾 Anteprima CSV")
        st.dataframe(df_input.head())

        # 🧩 Configurazione colonne
        with st.expander("⚙️ Configura colonne per il prompt", expanded=True):
            st.markdown("### 1. Seleziona colonne")
            available_cols = [col for col in df_input.columns if col not in ["Description", "Description2"]]
    
            def_column = ["skuarticolo",
                          "Classification",
                          "Matiere", "Sexe",
                          "Saison", "Silouhette",
                          "shoe_toecap_zalando",
                          "shoe_detail_zalando",
                          "heel_height_zalando",
                          "heel_form_zalando",
                          "sole_material_zalando",
                          "shoe_fastener_zalando",
                          "pattern_zalando",
                          "upper_material_zalando",
                          "futter_zalando",
                          "Subtile2",
                          "Concept",
                          "Sp.feature"
                         ]
    
            missing = not_in_array(df_input.columns, def_column)
            if missing:
                def_column = []
                
            st.session_state.selected_cols = st.multiselect("Colonne da includere nel prompt", options=available_cols, default=def_column)
    
            if st.session_state.selected_cols:
                if st.button("▶️ Procedi alla configurazione colonne"):
                    st.session_state.config_ready = True
    
            if st.session_state.get("config_ready"):
                st.markdown("### 2. Configura pesi ed etichette")
                for col in st.session_state.selected_cols:
                    st.session_state.col_weights.setdefault(col, 1)
                    st.session_state.col_display_names.setdefault(col, col)
    
                    cols = st.columns([2, 3])
                    with cols[0]:
                        st.session_state.col_weights[col] = st.slider(
                            f"Peso: {col}", 0, 5, st.session_state.col_weights[col], key=f"peso_{col}"
                        )
                    with cols[1]:
                        st.session_state.col_display_names[col] = st.text_input(
                            f"Etichetta: {col}", value=st.session_state.col_display_names[col], key=f"label_{col}"
                        )
    
        # 🌍 Lingue e parametri
        with st.expander("🌍 Selezione Lingue & Parametri"):
            settings_col1, settings_col2, settings_col3 = st.columns(3)
            with settings_col1:
                marchio = st.radio(
                    "Seleziona il marchio",
                    ["NAT", "FAL", "VB", "FM", "WZ", "CC"],
                    horizontal = False
                )
                use_simili = st.checkbox("Usa descrizioni simili (RAG)", value=True)
                k_simili = 2 if use_simili else 0
                
                use_image = st.checkbox("Usa immagine per descrizioni accurate", value=True)
    
            with settings_col2:
                selected_labels = st.multiselect(
                    "Lingue di output",
                    options=list(LANG_LABELS.keys()),
                    default=["Italiano", "Inglese", "Francese", "Tedesco"]
                )
                selected_langs = [LANG_LABELS[label] for label in selected_labels]
                
                selected_tones = st.multiselect(
                    "Tono desiderato",
                    ["professionale", "amichevole", "accattivante", "descrittivo", "tecnico", "ironico", "minimal", "user friendly", "SEO-friendly"],
                    default=["professionale", "user friendly", "SEO-friendly"]
                )
    
            with settings_col3:
                desc_lunga_length = st.selectbox("Lunghezza descrizione lunga", ["10", "20", "30", "40", "50", "60", "70", "80", "90", "100"], index=5)
                desc_breve_length = st.selectbox("Lunghezza descrizione breve", ["10", "20", "30", "40", "50", "60", "70", "80", "90", "100"], index=1)
    
        # 💵 Stima costi
        if st.button("💰 Stima costi generazione"):
            token_est, cost_est, prompt = calcola_tokens(
                df_input=df_input,
                col_display_names=st.session_state.col_display_names,
                selected_langs=selected_langs,
                selected_tones=selected_tones,
                desc_lunga_length=desc_lunga_length,
                desc_breve_length=desc_breve_length,
                k_simili=k_simili,
                use_image=use_image,
                faiss_index=st.session_state.get("faiss_index"),
                DEBUG=True
            )
            if token_est:
                st.info(f"""
                📊 Token totali: ~{token_est}
                💸 Costo stimato: ${cost_est:.6f}
                """)
    
        # 🪄 Generazione descrizioni
        if not check_openai_key():
            st.error("❌ La chiave OpenAI non è valida o mancante. Inserisci una chiave valida prima di generare descrizioni.")
        else:
            if st.button("🚀 Genera Descrizioni"):
                st.session_state["generate"] = True
            
            if st.session_state.get("generate"):
    
                    
                try:
                    with st.spinner("📚 Carico storico e indice FAISS..."):
                        tab_storico = f"STORICO_{marchio}"
                        data_sheet = get_sheet(desc_sheet_id, tab_storico)
                        df_storico = pd.DataFrame(data_sheet.get_all_records()).tail(500)
            
                        if "faiss_index" not in st.session_state:
                            index, index_df = build_faiss_index(df_storico, st.session_state.col_weights)
                            st.session_state["faiss_index"] = (index, index_df)
                        else:
                            index, index_df = st.session_state["faiss_index"]
            
                    # ✅ Recupera descrizioni già esistenti su GSheet
                    st.info("🔄 Verifico se alcune righe sono già state generate...")
                    existing_data = {}
                    already_generated = {lang: [] for lang in selected_langs}
                    rows_to_generate = []
            
                    for lang in selected_langs:
                        try:
                            tab_df = pd.DataFrame(get_sheet(desc_sheet_id, lang).get_all_records())
                            tab_df = tab_df[["SKU", "Description", "Description2"]].dropna(subset=["SKU"])
                            tab_df["SKU"] = tab_df["SKU"].astype(str)
                            existing_data[lang] = tab_df.set_index("SKU")
                        except:
                            existing_data[lang] = pd.DataFrame(columns=["Description", "Description2"])
            
                    for i, row in df_input.iterrows():
                        sku = str(row.get("SKU", "")).strip()
                        if not sku:
                            rows_to_generate.append(i)
                            continue
            
                        all_present = True
                        for lang in selected_langs:
                            df_lang = existing_data.get(lang)
                            if df_lang is None or sku not in df_lang.index:
                                all_present = False
                                break
                            desc = df_lang.loc[sku]
                            if not desc["Description"] or not desc["Description2"]:
                                all_present = False
                                break
            
                        if all_present:
                            for lang in selected_langs:
                                desc = existing_data[lang].loc[sku]
                                output_row = row.to_dict()
                                output_row["Description"] = desc["Description"]
                                output_row["Description2"] = desc["Description2"]
                                already_generated[lang].append(output_row)
                        else:
                            rows_to_generate.append(i)
            
                    df_input_to_generate = df_input.iloc[rows_to_generate]
            
                    # Costruzione dei prompt
                    all_prompts = []
                    with st.spinner("✍️ Costruisco i prompt..."):
                        for _, row in df_input_to_generate.iterrows():
                            simili = retrieve_similar(row, index_df, index, k=k_simili, col_weights=st.session_state.col_weights) if k_simili > 0 else pd.DataFrame([])
                            caption = get_blip_caption(row.get("Image 1", "")) if use_image and row.get("Image 1", "") else None
                            prompt = build_unified_prompt(row, st.session_state.col_display_names, selected_langs, image_caption=caption, simili=simili)
                            all_prompts.append(prompt)
            
                    with st.spinner("🚀 Generazione asincrona in corso..."):
                        results = asyncio.run(generate_all_prompts(all_prompts))
            
                    # Parsing risultati
                    all_outputs = already_generated.copy()
                    logs = []
            
                    for i, (_, row) in enumerate(df_input_to_generate.iterrows()):
                        result = results.get(i, {})
                        if "error" in result:
                            logs.append({
                                "sku": row.get("SKU", ""),
                                "status": f"Errore: {result['error']}",
                                "prompt": all_prompts[i],
                                "output": "",
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            })
                            continue
            
                        for lang in selected_langs:
                            lang_data = result.get("result", {}).get(lang.lower(), {})
                            descr_lunga = lang_data.get("desc_lunga", "").strip()
                            descr_breve = lang_data.get("desc_breve", "").strip()
            
                            output_row = row.to_dict()
                            output_row["Description"] = descr_lunga
                            output_row["Description2"] = descr_breve
                            all_outputs[lang].append(output_row)
            
                        log_entry = {
                            "sku": row.get("SKU", ""),
                            "status": "OK",
                            "prompt": all_prompts[i],
                            "output": json.dumps(result["result"], ensure_ascii=False),
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        if "usage" in result:
                            usage = result["usage"]
                            log_entry.update({
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                                "estimated_cost_usd": round(usage.get("total_tokens", 0) / 1000 * 0.001, 6)
                            })
                        logs.append(log_entry)
            
                    # 🔄 Salvataggio solo dei nuovi risultati
                    with st.spinner("📤 Salvataggio nuovi dati..."):
                        for lang in selected_langs:
                            df_out = pd.DataFrame(all_outputs[lang])
                            df_new = df_out[df_out["SKU"].isin(df_input_to_generate["SKU"].astype(str))]
                            if not df_new.empty:
                                append_to_sheet(desc_sheet_id, lang, df_new)
                        for log in logs:
                            append_log(desc_sheet_id, log)
            
                    # 📦 ZIP finale
                    with st.spinner("📦 Generazione ZIP..."):
                        mem_zip = BytesIO()
                        with zipfile.ZipFile(mem_zip, "w") as zf:
                            for lang in selected_langs:
                                df_out = pd.DataFrame(all_outputs[lang])
                                df_export = pd.DataFrame({
                                    "SKU": df_out.get("SKU", ""),
                                    "Descrizione lunga": df_out.get("Description", ""),
                                    "Descrizione breve": df_out.get("Description2", "")
                                })
                                zf.writestr(f"descrizioni_{lang}.csv", df_export.to_csv(index=False).encode("utf-8"))
                        mem_zip.seek(0)
            
                    st.success("✅ Tutto fatto!")
                    st.download_button("📥 Scarica descrizioni (ZIP)", mem_zip, file_name="descrizioni.zip")
                    st.session_state["generate"] = False
            
                except Exception as e:
                    st.error(f"Errore durante la generazione: {str(e)}")
                    st.text(traceback.format_exc())
    
        # 🔍 Prompt Preview & Benchmark
        with st.expander("🔍 Strumenti di debug & Anteprima"):
            row_index = st.number_input("Indice riga per anteprima", 0, len(df_input) - 1, 0)
            test_row = df_input.iloc[row_index]
    
            if st.button("💬 Mostra Prompt di Anteprima"):
                with st.spinner("Generazione..."):
                    try:
                        if desc_sheet_id:
                            tab_storico = f"STORICO_{marchio}"
                            data_sheet = get_sheet(desc_sheet_id, tab_storico)
                            df_storico = pd.DataFrame(data_sheet.get_all_records()).tail(500)
                            if "faiss_index" not in st.session_state:
                                index, index_df = build_faiss_index(df_storico, st.session_state.col_weights)
                                st.session_state["faiss_index"] = (index, index_df)
                            else:
                                index, index_df = st.session_state["faiss_index"]
                            simili = (
                                retrieve_similar(test_row, index_df, index, k=k_simili, col_weights=st.session_state.col_weights)
                                if k_simili > 0 else pd.DataFrame([])
                            )
                        else:
                            simili = pd.DataFrame([])
    
                        image_url = test_row.get("Image 1", "")
                        if use_image:
                            caption = get_blip_caption(image_url) if image_url else None
                        else:
                            caption = None
                        prompt_preview = build_unified_prompt(test_row, st.session_state.col_display_names, selected_langs, image_caption=caption, simili=simili)
                        st.expander("📄 Prompt generato").code(prompt_preview, language="markdown")
                    except Exception as e:
                        st.error(f"Errore: {str(e)}")
    
            if st.button("🧪 Esegui Benchmark FAISS"):
                with st.spinner("In corso..."):
                    benchmark_faiss(df_input, st.session_state.col_weights)
