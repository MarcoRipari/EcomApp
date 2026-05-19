import streamlit as st
import traceback
import asyncio
import os
import time
import json
import zipfile
import io
from io import BytesIO
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import dropbox as dbx_lib

from utils import *
from functions.gsheet import get_sheet, append_to_sheet
from functions.dropbox import get_dropbox_access_token, upload_to_dropbox
from functions.traduzioni import (
    download_translation_db_from_github,
    upload_translation_db_to_github,
    translate_column_parallel
)
from functions.descrizioni import (
    build_faiss_index, retrieve_similar, build_unified_prompt,
    generate_all_prompts, calcola_tokens, LANG_LABELS, LANG_NAMES
)

DESC_SHEET_ID = st.secrets.get("DESC_GSHEET_ID")

def append_logs(sheet_id, logs):
    sheet = get_sheet(sheet_id, "logs")
    if not logs:
        return
    rows = []
    for log in logs:
        rows.append([
            log.get("utente", ""),
            log.get("sku", ""),
            log.get("status", ""),
            log.get("prompt", ""),
            log.get("output", ""),
            log.get("timestamp", ""),
            log.get("prompt_tokens", 0),
            log.get("completion_tokens", 0),
            log.get("total_tokens", 0),
            log.get("estimated_cost_usd", 0)
        ])
    sheet.append_rows(rows)

def genera_descrizioni():
    st.header("📝 Genera Descrizioni Prodotto")
    st.markdown("Carica un CSV di prodotti per generare descrizioni SEO-oriented in più lingue.")
    
    uploaded = st.file_uploader("Carica un file CSV", type="csv", key="desc_csv_uploader")
    
    if uploaded:
        df_input = read_csv_auto_encoding(uploaded, ";")
        if "skucolore" in df_input.columns:
            df_input["skucolore"] = df_input["skucolore"].astype(str)
        st.session_state["df_input"] = df_input

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

    if "df_input" in st.session_state:
        df_input = st.session_state.df_input
        st.subheader("🧾 Anteprima Dati")
        st.dataframe(df_input.head())

        with st.expander("⚙️ Configura Colonne e Prompt", expanded=True):
            available_cols = [col for col in df_input.columns if col not in ["Description", "Description2"]]

            def_column = ["SKU famille", "Saison", "Silouhette", "sole_material_zalando",
                          "shoe_fastener_zalando", "upper_material_zalando", "futter_zalando", "Sp.feature"]

            trans_def_colum = {"Saison": "Stagione", "Silouhette": "Tipo di calzatura",
                               "sole_material_zalando": "Soletta interna", "shoe_fastener_zalando": "Chiusura",
                               "upper_material_zalando": "Tomaia", "futter_zalando": "Fodera interna",
                               "Sp.feature": "Caratteristica", "SKU famille": "Codice Articolo"}

            def_col_weights = {"SKU famille": 5, "Saison": 4, "Silouhette": 4, "sole_material_zalando": 3,
                               "shoe_fastener_zalando": 1, "upper_material_zalando": 3, "futter_zalando": 3, "Sp.feature": 1}

            st.session_state.selected_cols = st.multiselect("Colonne da includere", options=available_cols, default=[c for c in def_column if c in df_input.columns])
    
            if st.session_state.selected_cols:
                if st.button("▶️ Configura Pesi ed Etichette"):
                    st.session_state.config_ready = True
    
            if st.session_state.get("config_ready"):
                for col in st.session_state.selected_cols:
                    st.session_state.col_weights.setdefault(col, def_col_weights.get(col, 1))
                    st.session_state.col_display_names.setdefault(col, trans_def_colum.get(col, col))
    
                    cols = st.columns([2, 3])
                    with cols[0]:
                        st.session_state.col_weights[col] = st.slider(f"Peso: {col}", 0, 5, st.session_state.col_weights[col], key=f"p_{col}")
                    with cols[1]:
                        st.session_state.col_display_names[col] = st.text_input(f"Etichetta: {col}", value=st.session_state.col_display_names[col], key=f"l_{col}")
    
        with st.expander("🌍 Lingue, Tono e Modello"):
            c1, c2, c3 = st.columns(3)
            with c1:
                marchio = st.radio("Marchio", ["NAT", "FAL", "FM JUNIOR", "WZ BIMBO", "VB", "FM", "WZ", "CC"])
                use_simili = st.checkbox("Usa RAG (descrizioni simili)", value=True)
                k_simili = 5 if use_simili else 0
                use_model = st.selectbox("Modello OpenAI", ["gpt-4o-mini", "gpt-4o", "gpt-5.4-mini", "gpt-3.5-turbo"], index=0)
            with c2:
                selected_labels = st.multiselect("Lingue", options=list(LANG_LABELS.keys()), default=["Italiano"])
                selected_langs = [LANG_LABELS[l] for l in selected_labels]
                #selected_tones = st.multiselect("Tono", ["informale", "professionale", "SEO-optimized", "accattivante"], default=["informale", "SEO-optimized"])
                selected_tones = st.multiselect("Tono", ["informale", "conversazionale", "chiaro e diretto", "professionale", "amichevole", "accattivante", "descrittivo", "tecnico", "ironico", "minimal", "user friendly", "SEO-friendly", "SEO-optimized"], default=["informale", "conversazionale", "chiaro e diretto", "user friendly", "SEO-friendly", "SEO-optimized"])
            with c3:
                desc_lunga_length = st.select_slider("Parole (Lunga)", options=["20", "40", "60", "80", "100"], value="60")
                desc_breve_length = st.select_slider("Parole (Breve)", options=["10", "20", "30", "40", "50"], value="20")

        if st.button("💰 Stima Costi"):
            t, c, p = calcola_tokens(df_input, st.session_state.col_display_names, selected_langs, selected_tones, desc_lunga_length, desc_breve_length, k_simili, marchio, st.session_state.get("faiss_index"), DEBUG=True)
            st.info(f"Token stimati: ~{t} | Costo stimato: ${c:.6f}")

        if st.button("🚀 Avvia Generazione"):
            st.session_state["generate"] = True
            
        if st.session_state.get("generate"):
            logs = []
            try:
                with st.spinner("📚 Preparazione Indice FAISS..."):
                    if marchio == "FM JUNIOR":
                        tab_storico = f"STORICO_FM_JUNIOR"
                    elif marchio == "WZ BIMBO":
                        tab_storico = f"STORICO_WZ_BIMBO"
                    else:
                        tab_storico = f"STORICO_{marchio}"
                        
                    data_sheet = get_sheet(DESC_SHEET_ID, tab_storico)
                    df_storico = pd.DataFrame(data_sheet.get_all_records()).tail(500)
                    index, index_df = build_faiss_index(df_storico, st.session_state.col_weights)
                    st.session_state["faiss_index"] = (index, index_df)

                # ✅ Verifica righe già generate
                st.info("🔄 Verifica righe esistenti...")
                existing_data = {}
                already_generated = {lang: [] for lang in selected_langs}
                rows_to_generate = []

                for lang in selected_langs:
                    try:
                        tab_df = pd.DataFrame(get_sheet(DESC_SHEET_ID, lang).get_all_records())
                        tab_df = tab_df[["SKU", "Description", "Description2"]].dropna(subset=["SKU"])
                        tab_df["SKU"] = tab_df["SKU"].astype(str)
                        existing_data[lang] = tab_df.set_index("SKU")
                    except:
                        existing_data[lang] = pd.DataFrame(columns=["Description", "Description2"])

                prefix_to_output = {lang: {} for lang in selected_langs}
                unique_sku_prefixes = {}

                for i, row in df_input.iterrows():
                    sku = str(row.get("SKU", "")).strip()
                    prefix = sku[:13]
                    
                    found_in_sheets = True
                    for lang in selected_langs:
                        if lang not in existing_data or sku not in existing_data[lang].index:
                            found_in_sheets = False
                            break
                    
                    if found_in_sheets:
                        for lang in selected_langs:
                            desc = existing_data[lang].loc[sku]
                            out_row = row.to_dict()
                            out_row["Description"] = desc["Description"]
                            out_row["Description2"] = desc["Description2"]
                            already_generated[lang].append(out_row)
                    else:
                        if prefix not in unique_sku_prefixes:
                            unique_sku_prefixes[prefix] = i
                            rows_to_generate.append(i)

                df_to_gen = df_input.iloc[rows_to_generate]

                all_prompts = []
                with st.spinner("✍️ Creazione Prompt..."):
                    for _, row in df_to_gen.iterrows():
                        simili = retrieve_similar(row, index_df, index, k=k_simili, col_weights=st.session_state.col_weights) if k_simili > 0 else None
                        prompt = build_unified_prompt(row, st.session_state.col_display_names, selected_langs, selected_tones, desc_lunga_length, desc_breve_length, simili=simili, marchio=marchio)
                        all_prompts.append(prompt)

                with st.spinner(f"🚀 Generazione {len(all_prompts)} prodotti..."):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    results = loop.run_until_complete(generate_all_prompts(all_prompts, use_model, selected_langs))

                # Parsing risultati
                all_outputs = already_generated.copy()
                for i, (idx_in_df, row) in enumerate(df_to_gen.iterrows()):
                    res = results.get(i, {})
                    sku = str(row.get("SKU", "")).strip()
                    prefix = sku[:13]
                    
                    if "error" in res:
                        st.error(f"Errore SKU {sku}: {res['error']}")
                        continue
                    
                    res_data = res.get("result", {})
                    res_data_norm = {k.lower(): v for k, v in res_data.items()}
                    
                    for lang in selected_langs:
                        lang_data = res_data_norm.get(lang.lower(), {})
                        out_row = row.to_dict()
                        out_row["Description"] = lang_data.get("desc_lunga", "")
                        out_row["Description2"] = lang_data.get("desc_breve", "")
                        all_outputs[lang].append(out_row)
                        prefix_to_output[lang][prefix] = out_row

                    logs.append({
                        "utente": st.session_state.user.get("username", "unknown"),
                        "sku": sku,
                        "status": "OK",
                        "prompt": all_prompts[i],
                        "output": json.dumps(res_data, ensure_ascii=False),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        **res.get("usage", {})
                    })

                # Riempimento righe con lo stesso prefisso
                for i, row in df_input.iterrows():
                    sku = str(row.get("SKU", "")).strip()
                    prefix = sku[:13]
                    if i not in rows_to_generate and prefix in prefix_to_output[selected_langs[0]]:
                        for lang in selected_langs:
                            new_row = row.copy().to_dict()
                            cached = prefix_to_output[lang][prefix]
                            new_row["Description"] = cached["Description"]
                            new_row["Description2"] = cached["Description2"]
                            all_outputs[lang].append(new_row)

                # Salvataggio e ZIP
                with st.spinner("📤 Salvataggio e creazione ZIP..."):

                    mem_zip = BytesIO()
                    with zipfile.ZipFile(mem_zip, "w") as zf:
                        for lang in selected_langs:
                            df_out = pd.DataFrame(all_outputs[lang])

                            df_export = pd.DataFrame({
                                "skucolore": df_out.get("skucolore", ""),
                                f"Modello ({lang.lower()})": df_out.get("Short_title", ""),
                                f"Variante ({lang.lower()})": df_out.get("Subtitle", ""),
                                f"Colore ({lang.lower()})": df_out.get("Subtile2", ""),
                                f"Descrizione ({lang.lower()})": df_out.get("Description", ""),
                                f"Descrizione 2 ({lang.lower()})": df_out.get("Description2", "")
                            })
                            zf.writestr(f"descrizioni_{lang}.csv", df_export.to_csv(index=False).encode("utf-8"))

                            # Update Google Sheet
                            try:
                                sheet_df = pd.DataFrame(get_sheet(DESC_SHEET_ID, lang).get_all_records())
                                existing_skus = set(sheet_df["SKU"].astype(str).tolist())
                            except:
                                existing_skus = set()
                            df_new = df_out[~df_out["SKU"].astype(str).isin(existing_skus)]
                            if not df_new.empty:
                                append_to_sheet(DESC_SHEET_ID, lang, df_new)

                    append_logs(DESC_SHEET_ID, logs)
                    
                    mem_zip.seek(0)
                    now = datetime.now(ZoneInfo("Europe/Rome"))
                    file_name = f"descrizioni_{now.strftime('%d-%m-%Y_%H-%M-%S')}.zip"

                    # Dropbox
                    access_token = get_dropbox_access_token()
                    dbx = dbx_lib.Dropbox(access_token)
                    upload_to_dropbox(dbx, "/CATALOGO/DESCRIZIONI", file_name, mem_zip.getvalue())

                st.success("✅ Generazione completata!")
                st.download_button("📥 Scarica ZIP", mem_zip, file_name=file_name)
                st.session_state["generate"] = False

            except Exception as e:
                st.error(f"Errore fatale: {e}")
                st.text(traceback.format_exc())
