import streamlit as st
from streamlit_option_menu import option_menu
import gspread
import numpy as np
import logging
import time

from utils import *

load_functions_from("functions", globals())

anagrafica_sheet_id = st.secrets["ANAGRAFICA_GSHEET_ID"]
giacenze_sheet_id = st.secrets["GIACENZE_GSHEET_ID"]


sheets_to_import_test = ['1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4', # FOTO
                    '13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U', # VECCHIA STAGIONE
                    '1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ', # NUOVA STAGIONE
                    '1o8Zir8DNKxW9QERqeZr7G-EEnoTqwRVYlyuOrzQJnhA', # SELE-SALDI-25-2
                    '1mvMi-ybuLdIF3GnAnl2GLqR2Bxic1nBD3Bxt1GQZTec', # Base_Dati_Retag
                    '1eR3ZOE6IzGgYP4mPnyGBfWiDof4Gpv9olOVu_G_k1dg', # SELE-OUTLET-PE26
                    '1wvHZpS8Y45V4MWKgVv_WZx7t98p3Z83EXWc_e9vNFwc'  # LISTA-SKUS-PE26
                   ]

sheets_to_import = ['1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4', # FOTO
                    '13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U', # VECCHIA STAGIONE
                    '1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ' # NUOVA STAGIONE
                   ]

def giacenze_importa():
    st.header("Importa giacenze")

    # 1. INIZIALIZZAZIONE SESSION STATE
    if "df_input" not in st.session_state:
        st.session_state.df_input = None
    if "file_bytes_for_upload" not in st.session_state:
        st.session_state.file_bytes_for_upload = None

    dbx = get_dropbox_client()
    folder_path = "/GIACENZE"
    manual_nome_file = "GIACENZE.csv"

    # 2. CARICAMENTO FILE
    uploaded_file = st.file_uploader("Carica un file CSV manualmente", type="csv", key="uploader_manual")

    if uploaded_file:
        file_content = uploaded_file.getvalue()
        # Se il contenuto è diverso da quello in memoria, resetta il dataframe
        if st.session_state.file_bytes_for_upload != file_content:
            st.session_state.file_bytes_for_upload = file_content
            st.session_state.df_input = None  # Forza ricaricamento dataframe

    # 3. LETTURA CSV (Solo se necessario)
    if st.session_state.file_bytes_for_upload and st.session_state.df_input is None:
        with st.spinner("Carico e analizzo il CSV..."):
            # Leggiamo dai bytes salvati nello stato
            buffer = BytesIO(st.session_state.file_bytes_for_upload)
            st.session_state.df_input = read_csv_auto_encoding(buffer, ";")

    # Variabile di comodo
    df_input = st.session_state.df_input

    # 4. CONFIGURAZIONE GSHEET
    SHEETS = {
        "COMPLETO": sheets_to_import, # Assicurati che sia una lista di ID
        "Foglio FOTO": "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4",
        "Foglio GIACENZE": "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U",
    }
    
    options = list(SHEETS.keys()) + ["Manuale"]
    sheet_option = st.selectbox("Seleziona foglio:", options)
    
    if sheet_option in SHEETS:
        selected_sheet_id = SHEETS[sheet_option]
    else:
        selected_sheet_id = st.text_input("Inserisci ID del Google Sheet")

    nome_sheet_tab = st.text_input("Inserisci nome del TAB", value="GIACENZE")

    # Container per messaggi di stato
    upd_container = st.empty()
    res_container = st.container() # Usiamo container fisso invece di empty per accumulare i successi
    
    col1, col2, col3, col4 = st.columns(4)

    if df_input is not None:
        if st.checkbox("Visualizza dati caricate", value=False):
            st.dataframe(df_input.head(10))

        # --- PREPARAZIONE DATI ---
        # Creiamo data_to_write una sola volta fuori dai loop
        df_proc = df_input.copy()
        
        # Formattazione numerica colonne specifiche
        numeric_cols_info = { "D": "0", "M": "000", "O": "0", "P": "0" }
        for i in range(18, 30):
            col_letter = gspread.utils.rowcol_to_a1(1, i)[:-1]
            numeric_cols_info[col_letter] = "0"

        def to_number_safe(x):
            try:
                if pd.isna(x) or x == "": return ""
                return float(str(x).replace(',', '.'))
            except:
                return str(x)

        for col_letter in numeric_cols_info.keys():
            col_idx = gspread.utils.a1_to_rowcol(f"{col_letter}1")[1] - 1
            if df_proc.columns.size > col_idx:
                col_name = df_proc.columns[col_idx]
                df_proc[col_name] = df_proc[col_name].apply(to_number_safe)

        # Trasformazione finale in lista di liste
        data_to_write = [df_proc.columns.tolist()] + df_proc.fillna("").values.tolist()
        
        # Fix intestazioni magazzini
        intestazioni_magazzini = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
        if len(data_to_write[0]) >= 27:
            data_to_write[0][18:27] = intestazioni_magazzini

        # --- FUNZIONI CORE ---
        def run_import_giacenze(s_id):
            try:
                upd_container.info(f"⏳ Elaborazione: {s_id}...")
                sh = get_sheet(s_id, nome_sheet_tab)
                sh.clear()
                sh.update("A1", data_to_write)
                
                # Formattazione GSheet
                last_row = len(df_proc) + 1
                ranges = [
                    (f"{col}2:{col}{last_row}", 
                     CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=pat)))
                    for col, pat in numeric_cols_info.items()
                ]
                format_cell_ranges(sh, ranges)
                return True
            except Exception as e:
                return str(e)

        def run_import_anagrafica(s_id):
            try:
                sh_dest = get_sheet(s_id, "ANAGRAFICA")
                sh_src = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                sh_dest.clear()
                sh_dest.update("A1", sh_src.get_all_values())
                return True
            except Exception as e:
                return str(e)

        # --- AZIONI ---
        with col2:
            if st.button("Importa Giacenze"):
                targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                for i, s in enumerate(targets):
                    res = run_import_giacenze(s)
                    with res_container:
                        if res is True:
                            st.success(f"✅ {i+1}/{len(targets)} - {s} completato")
                        else:
                            st.error(f"❌ Errore su {s}: {res}")
                
                # Dropbox alla fine del loop
                if st.session_state.file_bytes_for_upload:
                    upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
                upd_container.empty()

        with col3:
            if st.button("Importa Tutto"):
                targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                for i, s in enumerate(targets):
                    res_g = run_import_giacenze(s)
                    res_a = run_import_anagrafica(s)
                    with res_container:
                        if res_g is True and res_a is True:
                            st.success(f"✅ {i+1}/{len(targets)} - {s} (Giacenze + Anagrafica) OK")
                        else:
                            st.error(f"❌ Errore su {s}")
                
                if st.session_state.file_bytes_for_upload:
                    upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
                upd_container.empty()

        with col4:
            if st.button("Carica Dropbox"):
                if st.session_state.file_bytes_for_upload:
                    upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
                    st.toast("File caricato su Dropbox!")

    with col1:
        if st.button("Anagrafica"):
            targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
            for s in targets:
                if run_import_anagrafica(s) is True:
                    st.toast(f"Anagrafica OK: {s}")


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
