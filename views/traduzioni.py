import streamlit as st
import asyncio
import io
import zipfile
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import dropbox as dbx_lib

from utils import *

# Carica funzioni di traduzione
from functions.traduzioni import (
    load_vocab, extract_missing_terms, enrich_vocab_with_ui,
    apply_translations, AVAILABLE_LANGS
)
from functions.dropbox import get_dropbox_access_token, upload_to_dropbox
from functions.gsheet import get_sheet

TRANSLATION_SHEET_ID = st.secrets.get('TRANSLATION_SHEET_ID')
TRANSLATION_TAB_NAME = "Traduzioni"

def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.create_task(coro)

def genera_traduzioni():
    st.title("🌍 Genera Traduzioni")
    st.markdown("Carica un file CSV per tradurre le colonne desiderate utilizzando OpenAI e un vocabolario su Google Sheets.")
    
    # Permettiamo il caricamento di più file contemporaneamente
uploaded_files = st.file_uploader(
    "Carica uno o più CSV (1 per lingua)", 
    type="csv", 
    accept_multiple_files=True, 
    key="trad_csv_uploader"
)

if uploaded_files:
    dfs = []
    file_names = []
    
    for f in uploaded_files:
        current_df = read_csv_auto_encoding(f)
        if not current_df.empty:
            dfs.append(current_df)
            file_names.append(f.name)
            
    if dfs:
        # --- VERIFICA STRUTTURA E IDENTICI ELEMENTI NELLA PRIMA COLONNA ---
        base_df = dfs[0]
        first_col_name = base_df.columns[0]  # Di solito "Codice" o simile
        base_series = base_df[first_col_name].astype(str).str.strip().tolist()
        
        all_identical = True
        for idx, next_df in enumerate(dfs[1:], start=1):
            next_col_name = next_df.columns[0]
            next_series = next_df[next_col_name].astype(str).str.strip().tolist()
            
            # Verifichiamo se la lunghezza o gli elementi della prima colonna differiscono
            if base_series != next_series:
                st.error(
                    f"❌ Errore di mismatch: Il file `{file_names[idx]}` non ha gli stessi elementi nella "
                    f"prima colonna rispetto a `{file_names[0]}` (o l'ordine delle righe è differente)."
                )
                all_identical = False
                break
        
        if all_identical:
            # --- CONSOLIDAMENTO DEI FILE CSV ---
            df = base_df.copy()
            if len(dfs) > 1:
                with st.spinner("Consolidamento dei file CSV in corso..."):
                    # Uniamo i file usando come chiavi le colonne di base identificative del record
                    # Se non trova le chiavi classiche, usa la prima colonna per fare il merge esatto
                    common_keys = [c for c in ["Codice", "Var", "Colore"] if c in df.columns]
                    if not common_keys:
                        common_keys = [first_col_name]
                        
                    for next_df in dfs[1:]:
                        # Eseguiamo un outer merge basato sulle chiavi
                        df = pd.merge(df, next_df, on=common_keys, how="outer", suffixes=('', '_drop'))
                        # Rimuoviamo le colonne duplicate create dal merge
                        df = df.loc[:, ~df.columns.str.endswith('_drop')]
            
            st.success(f"📊 Unione completata con successo! Rilevate {len(df)} righe totali.")
            st.dataframe(df.head())
    
        st.subheader("Seleziona colonne da tradurre")
        cols_to_translate = st.multiselect(
            "Colonne (it)",
            df.columns.tolist(),
            default=["Variante (it)", "Colore (it)", "Descrizione (it)", "Descrizione 2 (it)"]
        )
    
        st.subheader("Seleziona lingue")
        target_langs = st.multiselect(
            "Lingue di destinazione",
            AVAILABLE_LANGS,
            default=AVAILABLE_LANGS
        )
    
        if st.button("🚀 Avvia traduzione") and cols_to_translate and target_langs:
            if not TRANSLATION_SHEET_ID:
                st.error("TRANSLATION_SHEET_ID non configurato nei secrets.")
                return

            with st.spinner("Caricamento vocabolario..."):
                vocab, ws = load_vocab(TRANSLATION_SHEET_ID, TRANSLATION_TAB_NAME)
    
            with st.spinner("Analisi termini mancanti..."):
                # Passiamo anche target_langs per controllare se mancano traduzioni parziali
                missing_terms = extract_missing_terms(df, cols_to_translate, vocab, target_langs)
    
            st.info(f"Termini da tradurre: {len(missing_terms)}")
    
            if missing_terms:
                with st.spinner("Traduzione OpenAI in corso..."):
                    progress_bar = st.progress(0)
                    saved_badge = st.empty()
                    status_text = st.empty()
                    timer_text = st.empty()
    
                    task = run_async(
                        enrich_vocab_with_ui(
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
                    status_text.text("✅ Traduzioni completate e salvate su Google Sheets")
                    timer_text.empty()

            with st.spinner("Applicazione traduzioni al CSV..."):
                dfs_by_lang = apply_translations(df, cols_to_translate, target_langs, vocab)
    
            st.success("✅ Generazione file completata")
            
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for lang, df_lang in dfs_by_lang.items():
                    csv_buffer = io.StringIO()
                    df_lang.to_csv(csv_buffer, index=False)
            
                    zipf.writestr(
                        f"traduzioni_{lang}.csv",
                        csv_buffer.getvalue()
                    )
            
            zip_buffer.seek(0)
            
            now = datetime.now(ZoneInfo("Europe/Rome"))
            file_name = f"traduzioni_{now.strftime('%d-%m-%Y_%H-%M-%S')}.zip"

            # Carico il file su dropbox
            try:
                folder_path = "/CATALOGO/TRADUZIONI"
                access_token = get_dropbox_access_token()
                dbx = dbx_lib.Dropbox(access_token)
                upload_to_dropbox(dbx, folder_path, file_name, zip_buffer.getvalue())
            except Exception as e:
                st.error(f"❌ Errore durante l'upload su Dropbox: {e}")
                            
            st.download_button(
                "📦 Scarica ZIP traduzioni",
                data=zip_buffer,
                file_name=file_name,
                mime="application/zip"
            )
