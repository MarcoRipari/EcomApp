import streamlit as st
from streamlit_option_menu import option_menu
import gspread
import numpy as np
import logging

from utils import *

load_functions_from("functions", globals())

anagrafica_sheet_id = st.secrets["ANAGRAFICA_GSHEET_ID"]
giacenze_sheet_id = st.secrets["GIACENZE_GSHEET_ID"]

sheets_to_import = ['1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4', # FOTO
                    '13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U', # VECCHIA STAGIONE
                    '1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ', # NUOVA STAGIONE
                    '1o8Zir8DNKxW9QERqeZr7G-EEnoTqwRVYlyuOrzQJnhA', # SELE-SALDI-25-2
                    '1mvMi-ybuLdIF3GnAnl2GLqR2Bxic1nBD3Bxt1GQZTec', # Base_Dati_Retag
                    '1eR3ZOE6IzGgYP4mPnyGBfWiDof4Gpv9olOVu_G_k1dg', # SELE-OUTLET-PE26
                    '1wvHZpS8Y45V4MWKgVv_WZx7t98p3Z83EXWc_e9vNFwc'  # LISTA-SKUS-PE26
                   ]

def giacenze_importa():
    st.header("Importa giacenze2")

    # --- Menu di navigazione ---
    options_menu_list = ["Manuale", "UBIC", "PIM"]
    selected = option_menu(
        menu_title=None,
        options=options_menu_list,
        icons=[" ", " ", " "],
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "0 10px 0 0!important", "background-color": "#f0f0f0", "display": "flex", "justify-content": "center"},
            "nav-link": {"font-size": "16px", "text-align": "center", "margin": "5px", "min-height": "40px", "display": "flex", "align-items": "center", "justify-content": "center"},
            "nav-link-selected": {"background-color": "#4CAF50", "color": "white", "border-radius": "10px"},
        }
    )

    st.session_state.selected_option = selected
    nome_file = st.session_state.selected_option

    # --- Reset Sessione ---
    if "downloaded_file_name" not in st.session_state or st.session_state.downloaded_file_name != nome_file:
        st.session_state.df_input = None
        st.session_state.downloaded_file = None
        st.session_state.downloaded_file_metadata = None
        st.session_state.downloaded_file_name = nome_file

    csv_import = None
    file_bytes_for_upload = None
    dbx = get_dropbox_client()
    folder_path = "/GIACENZE"

    # --- Logica Caricamento ---
    if nome_file == "Manuale":
        uploaded_file = st.file_uploader("Carica un file CSV manualmente", type="csv", key="uploader_manual")
        if uploaded_file:
            if ("uploaded_file_name" not in st.session_state) or (st.session_state.uploaded_file_name != uploaded_file.name):
                st.session_state.uploaded_file_name = uploaded_file.name
                st.session_state.df_input = None
                st.session_state.uploaded_file_bytes = uploaded_file.getvalue()
            csv_import = uploaded_file
            file_bytes_for_upload = st.session_state.uploaded_file_bytes
            manual_nome_file = "GIACENZE.csv"
    else:
        if st.session_state.downloaded_file is None:
            with st.spinner(f"Download {nome_file} da DropBox..."):
                st.session_state.downloaded_file, st.session_state.downloaded_file_metadata = download_csv_from_dropbox(dbx, folder_path, f"{nome_file}.csv")
        
        if st.session_state.downloaded_file:
            csv_import = st.session_state.downloaded_file
            file_bytes_for_upload = csv_import.getvalue()

    # --- Caricamento DataFrame ---
    if csv_import and st.session_state.df_input is None:
        with st.spinner("Carico il CSV..."):
            df = read_csv_auto_encoding(csv_import, ";")
            # Forza TAGLIA a stringa per Arrow
            if 'TAGLIA' in df.columns:
                df['TAGLIA'] = df['TAGLIA'].astype(str).str.strip()
            st.session_state.df_input = df

    df_input = st.session_state.df_input

    # --- Configurazione Destinazione ---
    SHEETS = {
        "COMPLETO": sheets_to_import,
        "Foglio FOTO": "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4",
        "Foglio GIACENZE": "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U",
    }
    sheet_option = st.selectbox("Seleziona foglio:", list(SHEETS.keys()) + ["Manuale"])
    selected_sheet_id = SHEETS[sheet_option] if sheet_option in SHEETS else st.text_input("ID GSheet")
    nome_sheet_tab = st.text_input("Nome TAB", value="GIACENZE")

    col1, col2, col3, col4 = st.columns(4)

    if df_input is not None:
        # --- FUNZIONE IMPORTAZIONE CORRETTA ---
        def import_giacenze(sheet_id):
            try:
                sheet_upload_tab = get_sheet(sheet_id, nome_sheet_tab)
                
                with st.spinner(f"Sanificazione e invio a {sheet_id}..."):
                    df_work = df_input.copy()
                    
                    # 1. Definiamo colonne numeriche
                    numeric_cols_info = { "D": "0", "M": "000", "O": "0", "P": "0" }
                    for i in range(18, 30):
                        col_letter = gspread.utils.rowcol_to_a1(1, i)[:-1]
                        numeric_cols_info[col_letter] = "0"

                    # 2. Funzione per rendere il dato "JSON-safe" (Risolve InvalidJSONError)
                    def safe_val(val):
                        if pd.isna(val) or val == "" or val is None:
                            return ""
                        # Se è infinito o NaN (Out of range float)
                        if isinstance(val, (float, np.float64)):
                            if not np.isfinite(val):
                                return ""
                            return float(val)
                        # Se è un tipo numpy int/float
                        if hasattr(val, "item"):
                            return val.item()
                        return str(val)

                    # 3. Preparazione dati
                    headers = df_work.columns.tolist()
                    if len(headers) >= 27:
                        headers[18:27] = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
                    
                    data_to_write = [headers]
                    for row in df_work.values:
                        data_to_write.append([safe_val(c) for c in row])

                    # 4. Scrittura Atomica
                    sheet_upload_tab.clear()
                    sheet_upload_tab.update("A1", data_to_write, value_input_option='USER_ENTERED')
                    
                    # 5. Formattazione
                    last_row = len(data_to_write)
                    ranges = [(f"{col}2:{col}{last_row}", CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=pat)))
                              for col, pat in numeric_cols_info.items()]
                    format_cell_ranges(sheet_upload_tab, ranges)
                
                return True
            except Exception as e:
                st.error(f"Errore su {sheet_id}: {e}")
                return False

        def import_anagrafica(sheet_id):
            try:
                sheet_upload_anagrafica = get_sheet(sheet_id, "ANAGRAFICA")
                sheet_anagrafica = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                sheet_upload_anagrafica.clear()
                sheet_upload_anagrafica.update("A1", sheet_anagrafica.get_all_values())
                st.success(f"✅ {sheet_id} - Anagrafica importata!")
            except Exception as e:
                st.error(f"Errore anagrafica su {sheet_id}: {e}")

        # --- Gestione Pulsanti ---
        with col2:
            if st.button("Importa Giacenze"):
                ids = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                for s_id in ids:
                    if import_giacenze(s_id):
                        st.success(f"✅ {s_id} - Giacenze importate!")
                if nome_file == "Manuale" and file_bytes_for_upload:
                    upload_csv_to_dropbox(dbx, folder_path, "GIACENZE.csv", file_bytes_for_upload)

        with col3:
            if st.button("Importa Giacenze & Anagrafica"):
                ids = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                for s_id in ids:
                    if import_giacenze(s_id):
                        st.success(f"✅ {s_id} - Giacenze importate!")
                        import_anagrafica(s_id)
                if nome_file == "Manuale" and file_bytes_for_upload:
                    upload_csv_to_dropbox(dbx, folder_path, "GIACENZE.csv", file_bytes_for_upload)

    with col1:
        if st.button("Importa Anagrafica"):
            ids = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
            for s_id in ids:
                import_anagrafica(s_id)


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
