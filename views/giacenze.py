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

    # --- Inizializzazione Session State per persistenza ---
    if "df_input" not in st.session_state:
        st.session_state.df_input = None
    if "file_bytes" not in st.session_state:
        st.session_state.file_bytes = None
    if "manual_filename" not in st.session_state:
        st.session_state.manual_filename = "GIACENZE.csv"

    dbx = get_dropbox_client()
    folder_path = "/GIACENZE"

    # --- Caricamento File ---
    uploaded_file = st.file_uploader("Carica un file CSV manualmente", type="csv", key="uploader_manual")

    if uploaded_file:
        # Se il file è nuovo o diverso, resettiamo il dataframe in memoria
        if st.session_state.file_bytes != uploaded_file.getvalue():
            st.session_state.file_bytes = uploaded_file.getvalue()
            st.session_state.df_input = None 

    # --- Lettura CSV (Eseguita solo se necessario) ---
    if st.session_state.file_bytes and st.session_state.df_input is None:
        with st.spinner("Carico il CSV..."):
            # Usiamo un BytesIO per leggere i bytes salvati nello stato
            from io import BytesIO
            csv_buffer = BytesIO(st.session_state.file_bytes)
            st.session_state.df_input = read_csv_auto_encoding(csv_buffer, ";")

    # Scorciatoia per comodità
    df_input = st.session_state.df_input

    # --- Configurazione Destinazione ---
    SHEETS = {
        "COMPLETO": sheets_to_import, # Questa deve essere una lista di ID
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

    # Container per messaggi dinamici
    upd_container = st.empty()
    res_container = st.empty()
    
    col1, col2, col3, col4 = st.columns(4)

    if df_input is not None:
        if st.checkbox("Visualizza il dataframe?", value=False):
            st.write(df_input)

        # --- Elaborazione Dati (Numeric formatting) ---
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

        # Applichiamo le trasformazioni su una copia per non sporcare il session_state ad ogni giro
        df_proc = df_input.copy()
        for col_letter in numeric_cols_info.keys():
            col_idx = gspread.utils.a1_to_rowcol(f"{col_letter}1")[1] - 1
            if df_proc.columns.size > col_idx:
                col_name = df_proc.columns[col_idx]
                df_proc[col_name] = df_proc[col_name].apply(to_number_safe)

        # Riempimento NaN per compatibilità GSheet
        data_to_write = [df_proc.columns.tolist()] + df_proc.fillna("").values.tolist()
        
        # Intestazioni magazzini fisse
        intestazioni_magazzini = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
        if len(data_to_write[0]) >= 27:
            data_to_write[0][18:27] = intestazioni_magazzini

        # --- Funzioni di Import Interno ---
        def import_giacenze_core(sheet_id, tab, dtw):
            try:
                with upd_container.container():
                    st.info(f"⏳ Aggiornamento in corso: {sheet_id}")
                
                sheet_target = get_sheet(sheet_id, tab)
                sheet_target.clear()
                sheet_target.update("A1", dtw)
                
                # Applichiamo formattazione numerica
                last_row = len(df_proc) + 1
                ranges_to_format = [
                    (f"{col_letter}2:{col_letter}{last_row}", 
                     CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=pattern)))
                    for col_letter, pattern in numeric_cols_info.items()
                ]
                format_cell_ranges(sheet_target, ranges_to_format)
                return True
            except Exception as e:
                return str(e)

        def import_anagrafica_core(sheet_id):
            try:
                sheet_upload_anag = get_sheet(sheet_id, "ANAGRAFICA")
                sheet_source_anag = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                sheet_upload_anag.clear()
                sheet_upload_anag.update("A1", sheet_source_anag.get_all_values())
                return True
            except Exception as e:
                st.error(f"Errore Anagrafica su {sheet_id}: {e}")
                return False

        # --- LOGICA PULSANTI ---
        
        with col2:
            if st.button("Importa Giacenze"):
                targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                tot = len(targets)
                
                for i, s in enumerate(targets):
                    res = import_giacenze_core(s, nome_sheet_tab, data_to_write)
                    with res_container.container():
                        if res is True:
                            st.success(f"✅ {i+1}/{tot} - Foglio {s} aggiornato!")
                        else:
                            st.error(f"❌ Errore su {s}: {res}")
                
                with st.spinner("Backup su Dropbox..."):
                    upload_csv_to_dropbox(dbx, folder_path, st.session_state.manual_filename, st.session_state.file_bytes)
                upd_container.empty()

        with col3:
            if st.button("Importa Giacenze & Anagrafica"):
                targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                tot = len(targets)
                
                for i, s in enumerate(targets):
                    res_g = import_giacenze_core(s, nome_sheet_tab, data_to_write)
                    import_anagrafica_core(s)
                    with res_container.container():
                        if res_g is True:
                            st.success(f"✅ {i+1}/{tot} - Giacenze + Anagrafica OK ({s})")
                        else:
                            st.error(f"❌ Errore Giacenze su {s}: {res_g}")
                
                with st.spinner("Backup su Dropbox..."):
                    upload_csv_to_dropbox(dbx, folder_path, st.session_state.manual_filename, st.session_state.file_bytes)
                upd_container.empty()

        with col4:
            if st.button("Carica su DropBox"):
                with st.spinner("Carico su Dropbox..."):
                    upload_csv_to_dropbox(dbx, folder_path, st.session_state.manual_filename, st.session_state.file_bytes)
                    st.success("✅ File CSV caricato con successo!")

    with col1:
        if st.button("Importa Anagrafica"):
            targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
            for s in targets:
                if import_anagrafica_core(s):
                    st.success(f"✅ Anagrafica importata su {s}")


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
