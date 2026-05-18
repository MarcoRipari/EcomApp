import streamlit as st
import traceback
import asyncio
import os
import time
import json
import pickle
import logging
import hashlib
from typing import List, Dict
import streamlit as st
import pandas as pd
import numpy as np
import requests
from PIL import Image
import openai
from openai import AsyncOpenAI
import faiss
import zipfile

from utils import *

load_functions_from("functions", globals())

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
        df_input = read_csv_auto_encoding(uploaded, ";")
        df_input["skucolore"] = df_input["skucolore"].astype(str)
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
    
            def_column = ["SKU famille", "Saison",
                          "Silouhette",
                          "sole_material_zalando",
                          "shoe_fastener_zalando",
                          "upper_material_zalando",
                          "futter_zalando",
                          "Sp.feature"
                         ]
            trans_def_colum = {"Saison": "Stagione",
                               "Silouhette": "Tipo di calzatura",
                               "sole_material_zalando": "Soletta interna",
                               "shoe_fastener_zalando": "Chiusura",
                               "upper_material_zalando": "Tomaia",
                               "futter_zalando": "Fodera interna",
                               "Sp.feature": "Caratteristica",
                               "SKU famille": "Codice Articolo"
                              }
            def_col_weights = {"SKU famille": 5,
                               "Saison": 4,
                               "Silouhette": 4,
                               "sole_material_zalando": 3,
                               "shoe_fastener_zalando": 1,
                               "upper_material_zalando": 3,
                               "futter_zalando": 3,
                               "Sp.feature": 1
                              }
    
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
                    st.session_state.col_weights.setdefault(col, def_col_weights[col])
                    st.session_state.col_display_names.setdefault(col, col)
    
                    cols = st.columns([2, 3])
                    with cols[0]:
                        st.session_state.col_weights[col] = st.slider(
                            f"Peso: {col}", 0, 5, st.session_state.col_weights[col], key=f"peso_{col}"
                        )
                    with cols[1]:
                        st.session_state.col_display_names[col] = st.text_input(
                            #f"Etichetta: {col}", value=st.session_state.col_display_names[col], key=f"label_{col}"
                            f"Etichetta: {col}", value=trans_def_colum[col], key=f"label_{col}"
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
                
                use_model = st.radio("Seleziona modello GPT", ["gpt-4o-mini", "gpt-4o", "gpt-5", "gpt-3.5-turbo", "gpt-4.1-nano", "gpt-5-nano"], index=1, horizontal = True)
    
            with settings_col2:
                selected_labels = st.multiselect(
                    "Lingue di output",
                    options=list(LANG_LABELS.keys()),
                    default=["Italiano", "Inglese", "Francese", "Tedesco", "Spagnolo"]
                )
                selected_langs = [LANG_LABELS[label] for label in selected_labels]
                
                selected_tones = st.multiselect(
                    "Tono desiderato",
                    ["informale", "conversazionale", "chiaro e diretto", "professionale", "amichevole", "accattivante", "descrittivo", "tecnico", "ironico", "minimal", "user friendly", "SEO-friendly", "SEO-optimized"],
                    default=["informale", "conversazionale", "chiaro e diretto", "user friendly", "SEO-friendly", "SEO-optimized"]
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
                marchio=marchio,
                faiss_index=st.session_state.get("faiss_index"),
                DEBUG=True
            )
            if token_est:
                st.info(f"""
                📊 Token totali: ~{token_est}
                💸 Costo stimato: ${cost_est:.6f}
                """)
    
        # 🪄 Generazione descrizioni
        openai_check, openai_check_msg = check_openai_key()
        if not openai_check:
            st.error("❌ La chiave OpenAI non è valida o mancante. Inserisci una chiave valida prima di generare descrizioni.")
            st.error(openai_check_msg)
        else:
            if st.button("🚀 Genera Descrizioni"):
                st.session_state["generate"] = True
            
            if st.session_state.get("generate"):
                logs = []
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

                    unique_sku_prefixes = {}
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
                            # ✅ SKU già presente in tutti i fogli
                            for lang in selected_langs:
                                desc = existing_data[lang].loc[sku]
                                output_row = row.to_dict()
                                output_row["Description"] = desc["Description"]
                                output_row["Description2"] = desc["Description2"]
                                already_generated[lang].append(output_row)
                        else:
                            prefix = sku[:13]
                    
                            # 🔍 Cerca se esiste già una SKU con questo prefisso in existing_data
                            found_existing = False
                            for lang in selected_langs:
                                df_lang = existing_data.get(lang)
                                if df_lang is not None:
                                    # Controlla se esiste uno SKU con lo stesso prefisso
                                    match = [s for s in df_lang.index if s.startswith(prefix)]
                                    if match:
                                        desc = df_lang.loc[match[0]]
                                        output_row = row.to_dict()
                                        output_row["Description"] = desc["Description"]
                                        output_row["Description2"] = desc["Description2"]
                                        already_generated[lang].append(output_row)
                                        found_existing = True
                    
                            # Se nessuna SKU con quel prefisso è già presente → generala ora
                            if not found_existing:
                                if prefix not in unique_sku_prefixes:
                                    unique_sku_prefixes[prefix] = i
                                    rows_to_generate.append(i)
            
                    df_input_to_generate = df_input.iloc[rows_to_generate]
            
                    # Costruzione dei prompt
                    all_prompts = []
                    with st.spinner("✍️ Costruisco i prompt..."):
                        for _, row in df_input_to_generate.iterrows():
                            simili = retrieve_similar(row, index_df, index, k=k_simili, col_weights=st.session_state.col_weights) if k_simili > 0 else pd.DataFrame([])
                            prompt = build_unified_prompt(row, st.session_state.col_display_names, selected_langs, simili=simili, marchio=marchio)
                            all_prompts.append(prompt)
            
                    with st.spinner("🚀 Generazione asincrona in corso..."):
                        results = asyncio.run(generate_all_prompts(all_prompts, use_model, selected_langs))
                    
                    # Parsing risultati
                    all_outputs = already_generated.copy()
                    prefix_to_output = {lang: {} for lang in selected_langs}
                    
                    for i, (_, row) in enumerate(df_input_to_generate.iterrows()):
                        result = results.get(i, {})

                        if "Continuativo" in result:
                            continue
                            
                        sku = str(row.get("SKU", "")).strip()
                        prefix = sku[:13]
                        if "error" in result:
                            logs.append({
                                "utente": st.session_state.user["username"],
                                "sku": row.get("SKU", ""),
                                "status": f"Errore: {result['error']}",
                                "prompt": all_prompts[i],
                                "output": "",
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            })
                            continue
                        
                        sku_generate_lista = []
                        result_data = result.get("result", {})
                        result_data_norm = {k.lower(): v for k, v in result_data.items()}
                        
                        for lang in selected_langs:
                            output_row = row.to_dict()
                            lang_data = result_data_norm.get(lang.lower(), {})
                            descr_lunga = lang_data.get("desc_lunga", "").strip()
                            descr_breve = lang_data.get("desc_breve", "").strip()
                            output_row["Description"] = descr_lunga
                            output_row["Description2"] = descr_breve
                            all_outputs[lang].append(output_row)
                            prefix_to_output[lang][prefix] = output_row
            
                        log_entry = {
                            "utente": st.session_state.user["username"],
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
                    for i, row in df_input.iterrows():
                        sku = str(row.get("SKU", "")).strip()
                        prefix = sku[:13]
                        if prefix in prefix_to_output[selected_langs[0]] and i not in rows_to_generate:
                            for lang in selected_langs:
                                copied_row = prefix_to_output[lang][prefix].copy()
                                new_row = row.copy()
                                #copied_row["SKU"] = sku  # sostituisci con lo SKU corrente
                                new_row["Description"] = copied_row.get("Description", "")
                                new_row["Description2"] = copied_row.get("Description2", "")
                                all_outputs[lang].append(new_row)
                                #all_outputs[lang].append(copied_row)
                                

                    # 🔄 Salvataggio solo dei nuovi risultati
                    with st.spinner("📤 Salvataggio nuovi dati..."):
                        try:
                            for lang in selected_langs:
                                df_out = pd.DataFrame(all_outputs[lang])
                                
                                #df_new = df_out[df_out["SKU"].isin(df_input_to_generate["SKU"].astype(str))]
                                # Recupera gli SKU già presenti nello sheet
                                try:
                                    sheet_df = pd.DataFrame(get_sheet(desc_sheet_id, lang).get_all_records())
                                    sheet_df["SKU"] = sheet_df["SKU"].astype(str)
                                    existing_skus = set(sheet_df["SKU"].tolist())
                                except:
                                    existing_skus = set()

                                df_new = df_out[~df_out["SKU"].astype(str).isin(existing_skus)]
        
                                if not df_new.empty:
                                    append_to_sheet(desc_sheet_id, lang, df_new)

                            append_logs(desc_sheet_id, logs)
                        except Exception as e:
                            st.warning(f"Errore: {e}")

                    
                    # 📦 ZIP finale
                    with st.spinner("📦 Generazione ZIP..."):
                        translation_db = download_translation_db_from_github()
                        original_db_json = json.dumps(translation_db, ensure_ascii=False, indent=2)
                        
                        mem_zip = BytesIO()
                        with zipfile.ZipFile(mem_zip, "w") as zf:
                            for lang in selected_langs:
                                df_out = pd.DataFrame(all_outputs[lang])
                                df_out["Code langue"] = lang.lower()
                                df_out['Subtitle_trad'] = translate_column_parallel(df_out['Subtitle'].fillna("").tolist(),source='it', target=lang.lower(), db=translation_db, max_workers=5)
                                df_out['Subtile2_trad'] = translate_column_parallel(df_out['Subtile2'].fillna("").tolist(),source='it', target=lang.lower(), db=translation_db, max_workers=5)

                                df_export = pd.DataFrame({
                                    "skucolore": df_out.get("skucolore", ""),
                                    f"Modello ({lang.lower()})": df_out.get("Short_title", ""),
                                    f"Variante ({lang.lower()})": df_out.get("Subtitle_trad", ""),
                                    f"Colore ({lang.lower()})": df_out.get("Subtile2_trad", ""),
                                    f"Descrizione ({lang.lower()})": df_out.get("Description", ""),
                                    f"Descrizione 2 ({lang.lower()})": df_out.get("Description2", "")
                                })
                                zf.writestr(f"descrizioni_{lang}.csv", df_export.to_csv(index=False).encode("utf-8"))
                        mem_zip.seek(0)

                        # Aggiorno il file della traduzioni
                        upload_translation_db_to_github(translation_db, original_db_json)

                        now = datetime.now(ZoneInfo("Europe/Rome"))
                        file_name = f"descrizioni_{now.strftime('%d-%m-%Y_%H-%M-%S')}.zip"
                        # Carico il file su dropbox
                        try:
                            file_bytes = mem_zip.getvalue()
                            folder_path = "/CATALOGO/DESCRIZIONI"  # cartella su Dropbox
                            access_token = get_dropbox_access_token()
                            dbx = dropbox.Dropbox(access_token)
                            upload_to_dropbox(dbx, folder_path, file_name, file_bytes)
                        except Exception as e:
                            st.error(f"❌ Errore durante l'upload su Dropbox: {e}")
                            
                    st.success("✅ Tutto fatto!")
                    st.download_button("📥 Scarica descrizioni (ZIP)", mem_zip, file_name=file_name)
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
                            
                        prompt_preview = build_unified_prompt(test_row, st.session_state.col_display_names, selected_langs, simili=simili, marchio=marchio)
                        st.expander("📄 Prompt generato").code(prompt_preview, language="markdown")
                    except Exception as e:
                        st.error(f"Errore: {str(e)}")
    
            if st.button("🧪 Esegui Benchmark FAISS"):
                with st.spinner("In corso..."):
                    benchmark_faiss(df_input, st.session_state.col_weights)
