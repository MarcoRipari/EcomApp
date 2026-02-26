import streamlit as st
from streamlit_option_menu import option_menu
import gspread
import numpy as np
import logging
import time
from io import BytesIO

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

    # --- 1. STATO PERSISTENTE ---
    if "df_input" not in st.session_state:
        st.session_state.df_input = None
    if "file_bytes_for_upload" not in st.session_state:
        st.session_state.file_bytes_for_upload = None
    if "import_in_corso" not in st.session_state:
        st.session_state.import_in_corso = False
    if "target_rimanenti" not in st.session_state:
        st.session_state.target_rimanenti = []
    if "import_logs" not in st.session_state:
        st.session_state.import_logs = []

    dbx = get_dropbox_client()
    folder_path = "/GIACENZE"
    manual_nome_file = "GIACENZE.csv"

    # --- 2. CARICAMENTO FILE ---
    uploaded_file = st.file_uploader("Carica un file CSV", type="csv", key="uploader_manual")
    if uploaded_file:
        content = uploaded_file.getvalue()
        if st.session_state.file_bytes_for_upload != content:
            st.session_state.file_bytes_for_upload = content
            st.session_state.df_input = None
            st.session_state.import_logs = [] # Reset log se cambio file

    if st.session_state.file_bytes_for_upload and st.session_state.df_input is None:
        buffer = BytesIO(st.session_state.file_bytes_for_upload)
        st.session_state.df_input = read_csv_auto_encoding(buffer, ";")

    df_input = st.session_state.df_input

    # --- 3. CONFIGURAZIONE TARGET ---
    SHEETS = {
        "COMPLETO": sheets_to_import, 
        "Foglio FOTO": "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4",
        "Foglio GIACENZE": "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U",
    }
    
    options = list(SHEETS.keys()) + ["Manuale"]
    sheet_option = st.selectbox("Seleziona target:", options)
    selected_sheet_id = SHEETS[sheet_option] if sheet_option in SHEETS else st.text_input("ID Manuale")
    nome_sheet_tab = st.text_input("Nome TAB", value="GIACENZE")

    # --- 4. LOGICA DI ELABORAZIONE (Dati pronti) ---
    if df_input is not None:
        df_proc = df_input.copy()
        # (Preprocessing numerico identico a prima...)
        numeric_cols_info = { "D": "0", "M": "000", "O": "0", "P": "0" }
        for i in range(18, 30):
            col_letter = gspread.utils.rowcol_to_a1(1, i)[:-1]
            numeric_cols_info[col_letter] = "0"

        def to_number_safe(x):
            try:
                if pd.isna(x) or x == "": return ""
                return float(str(x).replace(',', '.'))
            except: return str(x)

        for col_letter in numeric_cols_info.keys():
            col_idx = gspread.utils.a1_to_rowcol(f"{col_letter}1")[1] - 1
            if df_proc.columns.size > col_idx:
                col_name = df_proc.columns[col_idx]
                df_proc[col_name] = df_proc[col_name].apply(to_number_safe)

        data_to_write = [df_proc.columns.tolist()] + df_proc.fillna("").values.tolist()
        intestazioni_magazzini = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
        if len(data_to_write[0]) >= 27:
            data_to_write[0][18:27] = intestazioni_magazzini

        # --- 5. SISTEMA DI CONTROLLO LOOP ---
        col1, col2, col3, col4 = st.columns(4)

        # Bottone di avvio
        if col2.button("Avvia Importazione"):
            st.session_state.target_rimanenti = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
            st.session_state.import_in_corso = True
            st.session_state.import_logs = []
            st.rerun()

        # Esecuzione del loop (uno alla volta)
        if st.session_state.import_in_corso and st.session_state.target_rimanenti:
            current_target = st.session_state.target_rimanenti.pop(0)
            
            with st.status(f"Elaborazione {current_target}...") as status:
                try:
                    # Esecuzione fisica
                    sh = get_sheet(current_target, nome_sheet_tab)
                    sh.clear()
                    sh.update("A1", data_to_write)
                    
                    # Formattazione
                    last_row = len(df_proc) + 1
                    ranges = [(f"{c}2:{c}{last_row}", CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=p))) 
                              for c, p in numeric_cols_info.items()]
                    format_cell_ranges(sh, ranges)
                    
                    st.session_state.import_logs.append(f"✅ {current_target}: Successo")
                except Exception as e:
                    st.session_state.import_logs.append(f"❌ {current_target}: Errore {str(e)}")
                
                status.update(label="Completato!", state="complete")
            
            # Forza il rerun per passare al prossimo target
            st.rerun()

        # Fine lavori
        if st.session_state.import_in_corso and not st.session_state.target_rimanenti:
            st.session_state.import_in_corso = False
            if st.session_state.file_bytes_for_upload:
                upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
            st.success("Tutte le operazioni sono terminate!")

        # Mostra i log accumulati
        for log in st.session_state.import_logs:
            st.write(log)

    with col1:
        if st.button("Anagrafica"):
            # Logica semplice (non a loop) per test
            targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
            for s in targets:
                sh_dest = get_sheet(s, "ANAGRAFICA")
                sh_src = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                sh_dest.clear()
                sh_dest.update("A1", sh_src.get_all_values())
                st.toast(f"Anagrafica OK: {s}")


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
