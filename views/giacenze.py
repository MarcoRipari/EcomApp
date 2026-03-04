import streamlit as st
from streamlit_option_menu import option_menu
import gspread
from gspread_formatting import *
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
                    '14f6UkpgH-hoU12c81wpaXb-Sb9a9R3G_Myujxvk7zm0', # Base_Dati_Rtm_27.02.26
                    '1eR3ZOE6IzGgYP4mPnyGBfWiDof4Gpv9olOVu_G_k1dg', # SELE-OUTLET-PE26
                    '1wvHZpS8Y45V4MWKgVv_WZx7t98p3Z83EXWc_e9vNFwc'  # LISTA-SKUS-PE26
                   ]

sheets_to_import = ['1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4', # FOTO
                    '13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U', # VECCHIA STAGIONE
                    '1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ' # NUOVA STAGIONE
                   ]

def giacenze_importa():
    st.header("Importa giacenze")

    # --- 1. CONFIGURAZIONE CENTRALIZZATA ---
    # Inserisci qui tutti i fogli: "Nome Visualizzato": "ID_GSHEET"
    SHEETS_CONFIG_backup = {
        "FOTO": "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4",
        "VECCHIA STAGIONE": "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U",
        "NUOVA STAGIONE": "1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ",
        "SELE-SALDI-25-2": "1o8Zir8DNKxW9QERqeZr7G-EEnoTqwRVYlyuOrzQJnhA",
        "Base_Dati_Retag": "1mvMi-ybuLdIF3GnAnl2GLqR2Bxic1nBD3Bxt1GQZTec",
        "Base_Dati_Rtm_27.02.26": "14f6UkpgH-hoU12c81wpaXb-Sb9a9R3G_Myujxvk7zm0",
        "SELE-OUTLET-PE26": "1eR3ZOE6IzGgYP4mPnyGBfWiDof4Gpv9olOVu_G_k1dg",
        "LISTA-SKUS-PE26": "1wvHZpS8Y45V4MWKgVv_WZx7t98p3Z83EXWc_e9vNFwc"
    }

    SHEETS_CONFIG = {
        "FOTO": "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4",
        "VECCHIA STAGIONE": "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U",
        "NUOVA STAGIONE": "1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ"
    }

    # --- 2. STATO PERSISTENTE (Inizializzazione sicura) ---
    if "df_input" not in st.session_state:
        st.session_state.df_input = None
    if "file_bytes_for_upload" not in st.session_state:
        st.session_state.file_bytes_for_upload = None
    if "import_in_corso" not in st.session_state:
        st.session_state.import_in_corso = False
    if "target_rimanenti" not in st.session_state:
        st.session_state.target_rimanenti = []
    if "import_logs" not in st.session_state:
        st.session_state.import_logs = {} # Dizionario persistente
    if "total_to_import" not in st.session_state:
        st.session_state.total_to_import = 0

    dbx = get_dropbox_client()
    folder_path = "/GIACENZE"
    manual_nome_file = "GIACENZE.csv"

    # --- 3. CARICAMENTO FILE ---
    uploaded_file = st.file_uploader("Carica un file CSV", type="csv", key="uploader_manual")
    if uploaded_file:
        content = uploaded_file.getvalue()
        if st.session_state.file_bytes_for_upload != content:
            st.session_state.file_bytes_for_upload = content
            st.session_state.df_input = None
            st.session_state.import_logs = {} # Resetta i log solo al cambio file

    if st.session_state.file_bytes_for_upload and st.session_state.df_input is None:
        buffer = BytesIO(st.session_state.file_bytes_for_upload)
        st.session_state.df_input = read_csv_auto_encoding(buffer, ";")

    df_input = st.session_state.df_input

    # --- 4. SELEZIONE TARGET ---
    options = ["COMPLETO"] + list(SHEETS_CONFIG.keys()) + ["Manuale"]
    sheet_selection = st.selectbox("Seleziona target:", options)
    
    # Determiniamo i target selezionati
    if sheet_selection == "COMPLETO":
        targets_da_usare = list(SHEETS_CONFIG.values())
    elif sheet_selection == "Manuale":
        manual_id = st.text_input("Inserisci ID Google Sheet manuale")
        targets_da_usare = [manual_id] if manual_id else []
    else:
        targets_da_usare = [SHEETS_CONFIG[sheet_selection]]

    nome_sheet_tab = st.text_input("Nome del TAB", value="GIACENZE")

    # --- 5. PREPARAZIONE DATI ---
    data_to_write = []
    df_proc = None
    numeric_cols_info = {}

    if df_input is not None:
        df_proc = df_input.copy()
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

    # --- 6. PULSANTI ---
    col1, col2, col3, col4 = st.columns(4)

    def start_import(tipo):
        st.session_state.target_rimanenti = targets_da_usare.copy()
        st.session_state.total_to_import = len(targets_da_usare)
        st.session_state.import_in_corso = tipo
        st.session_state.import_logs = {} # Pulisci log vecchi
        st.rerun()

    if col1.button("Anagrafica", use_container_width=True): start_import("ANAGRAFICA")
    if col2.button("Giacenze", use_container_width=True): start_import("GIACENZE")
    if col3.button("Tutto", use_container_width=True): start_import("TOTALE")
    if col4.button("Dropbox", use_container_width=True):
        if st.session_state.file_bytes_for_upload:
            with st.spinner("Backup..."):
                upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
            st.success("OK!")

    # --- 7. RIEPILOGO (Sempre visibile e reattivo) ---
    if st.session_state.import_logs:
        st.divider()
        st.subheader("📊 Stato Avanzamento", divider="green")
        # Trasformiamo il dizionario in DataFrame per la visualizzazione
        log_data = [{"Foglio": k, "Stato": v} for k, v in st.session_state.import_logs.items()]
        st.table(log_data) # 'table' è più stabile di 'dataframe' durante i rerun

    # --- 8. LOGICA DI ESECUZIONE ---
    if st.session_state.import_in_corso and st.session_state.target_rimanenti:
        # Prendi il prossimo foglio
        current_id = st.session_state.target_rimanenti.pop(0)
        nome_leggibile = next((k for k, v in SHEETS_CONFIG.items() if v == current_id), f"ID: {current_id[:5]}")
        
        # Indica subito che stiamo lavorando
        st.session_state.import_logs[nome_leggibile] = "⏳ In corso..."
        
        with st.status(f"Lavoro su: {nome_leggibile}...", expanded=True) as status:
            try:
                # Esecuzione Anagrafica (se richiesto)
                if st.session_state.import_in_corso in ["ANAGRAFICA", "TOTALE"]:
                    sh_dest = get_sheet(current_id, "ANAGRAFICA")
                    sh_src = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                    sh_dest.clear()
                    sh_dest.update("A1", sh_src.get_all_values())
                
                # Esecuzione Giacenze (se richiesto)
                if st.session_state.import_in_corso in ["GIACENZE", "TOTALE"]:
                    sh = get_sheet(current_id, nome_sheet_tab)
                    sh.clear()
                    sh.update("A1", data_to_write)
                    # Formattazione
                    last_row = len(df_proc) + 1
                    ranges = [(f"{c}2:{c}{last_row}", CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=p))) 
                              for c, p in numeric_cols_info.items()]
                    format_cell_ranges(sh, ranges)

                # Se arriviamo qui, è andata bene
                st.session_state.import_logs[nome_leggibile] = "✅ Completato"
                status.update(label=f"Fatto: {nome_leggibile}", state="complete")

            except Exception as e:
                st.session_state.import_logs[nome_leggibile] = f"❌ Errore: {str(e)[:30]}"
                status.update(label=f"Errore su {nome_leggibile}", state="error")
        
        # Controllo fine lavori
        if not st.session_state.target_rimanenti:
            if st.session_state.import_in_corso != "ANAGRAFICA":
                upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
            st.session_state.import_in_corso = False
            st.balloons()
        
        # Rilancia lo script per il prossimo foglio (o per mostrare i palloncini)
        st.rerun()


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
