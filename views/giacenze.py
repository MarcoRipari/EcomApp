import streamlit as st
from streamlit_option_menu import option_menu
import gspread

from utils import *

load_functions_from("functions", globals())

anagrafica_sheet_id = st.secrets["ANAGRAFICA_GSHEET_ID"]
giacenze_sheet_id = st.secrets["GIACENZE_GSHEET_ID"]

def giacenze_importa():
    st.header("Importa giacenze2")

    options = ["Manuale", "UBIC", "PIM"]
    
    selected = option_menu(
        menu_title=None,
        options=["Manuale", "UBIC", "PIM"],
        icons=[" ", " ", " "],
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {
                "padding": "0 10px 0 0!important",
                "background-color": "#f0f0f0",
                "display": "flex",
                "justify-content": "center"
            },
            "nav-link": {
                "font-size": "16px",
                "text-align": "center",
                "margin": "5px",
                "padding": "0px",
                "min-height": "40px",
                "height": "40px",
                "line-height": "normal",
                "display": "flex",
                "align-items": "center",
                "justify-content": "center",
                "box-sizing": "border-box",
                "--hover-color": "#e0e0e0",
                "before": "none"
            },
            "nav-link-selected": {
                "background-color": "#4CAF50",
                "color": "white",
                "border": "2px solid #cccccc",
                "border-radius": "10px",
                "padding": "0px",
                "min-height": "40px",
                "height": "40px",
                "line-height": "normal",
                "display": "flex",
                "align-items": "center",
                "justify-content": "center",
                "box-sizing": "border-box",
                "before": "none"
            },
        }
    )

    st.session_state.selected_option = selected
    nome_file = st.session_state.selected_option

    # --- Reset se cambio file/target ---
    if "downloaded_file_name" not in st.session_state or st.session_state.downloaded_file_name != nome_file:
        st.session_state.df_input = None
        st.session_state.downloaded_file = None
        st.session_state.downloaded_file_metadata = None
        st.session_state.downloaded_file_name = nome_file

    csv_import = None
    file_bytes_for_upload = None
    last_update = None

    dbx = get_dropbox_client()
    folder_path = "/GIACENZE"

    # --- Manuale ---
    if nome_file == "Manuale":
        uploaded_file = st.file_uploader("Carica un file CSV manualmente", type="csv", key="uploader_manual")
        if uploaded_file:
            if ("uploaded_file_name" not in st.session_state) or (st.session_state.uploaded_file_name != uploaded_file.name):
                st.session_state.uploaded_file_name = uploaded_file.name
                st.session_state.df_input = None  # reset DataFrame se file nuovo
                st.session_state.uploaded_file_bytes = uploaded_file.getvalue()
                uploaded_file.seek(0)
                
            csv_import = uploaded_file
            file_bytes_for_upload = st.session_state.uploaded_file_bytes
            manual_nome_file = "GIACENZE.csv"

    # --- UBIC / PIM ---
    else:
        if st.session_state.downloaded_file is None:
            with st.spinner(f"Download {nome_file} da DropBox..."):
                st.session_state.downloaded_file, st.session_state.downloaded_file_metadata = download_csv_from_dropbox(
                    dbx, folder_path, f"{nome_file}.csv")
                st.session_state.downloaded_file_name = nome_file

        latest_file = st.session_state.downloaded_file
        metadata = st.session_state.downloaded_file_metadata
        
        if latest_file:
            csv_import = latest_file
            file_bytes_for_upload = latest_file.getvalue()
            last_update = format_dropbox_date(metadata.client_modified)
            st.info(f"{nome_file} ultimo aggiornamento: {last_update}")
        else:
            st.warning(f"Nessun file trovato su Dropbox, carica manualmente")

    # --- Carico CSV solo se df_input è None ---
    if csv_import and st.session_state.df_input is None:
        with st.spinner("Carico il CSV..."):
            st.session_state.df_input = read_csv_auto_encoding(csv_import, ";")

    df_input = st.session_state.df_input

    default_sheet_id = giacenze_sheet_id
    
    SHEETS = {
        "Foglio FOTO": "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4",
        "Foglio GIACENZE": "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U",
    }
    
    options = list(SHEETS.keys()) + ["Manuale"]

    sheet_option = st.selectbox(
        "Seleziona foglio:",
        options
    )
    
    if sheet_option in SHEETS:
        selected_sheet_id = SHEETS[sheet_option]
    else:
        selected_sheet_id = st.text_input("Inserisci ID del Google Sheet")
    #selected_sheet_id = st.text_input("Inserisci ID del Google Sheet", value=giacenze_sheet_id)
    nome_sheet_tab = st.text_input("Inserisci nome del TAB", value="GIACENZE")

    col1, col2, col3, col4 = st.columns(4)

    if df_input is not None:
        view_df = st.checkbox("Visualizza il dataframe?", value=False)
        if view_df:
            st.write(df_input)

        # --- Colonne numeriche ---
        numeric_cols_info = { "D": "0", "M": "000", "O": "0", "P": "0" }
        for i in range(18, 30):  # Colonne R-AD
            col_letter = gspread.utils.rowcol_to_a1(1, i)[:-1]
            numeric_cols_info[col_letter] = "0"

        def to_number_safe(x):
            try:
                if pd.isna(x) or x == "":
                    return ""
                return float(x)
            except:
                return str(x)

        for col_letter in numeric_cols_info.keys():
            col_idx = gspread.utils.a1_to_rowcol(f"{col_letter}1")[1] - 1
            if df_input.columns.size > col_idx:
                col_name = df_input.columns[col_idx]
                df_input[col_name] = df_input[col_name].apply(to_number_safe)

        target_indices = [gspread.utils.a1_to_rowcol(f"{col}1")[1] - 1 for col in numeric_cols_info.keys()]
        for idx, col_name in enumerate(df_input.columns):
            if idx not in target_indices:
                df_input[col_name] = df_input[col_name].apply(lambda x: "" if pd.isna(x) else str(x))

        
        st.write(df_input)
        data_to_write = [df_input.columns.tolist()] + df_input.values.tolist()
        intestazioni_magazzini = ["060/029","060/018","060/015","060/025","027/001",
              "028/029","139/029","028/001","012/001"]

        data_to_write[0][18:26] = intestazioni_magazzini

        # --- Destinazione GSheet ---       
        with col2:
            if st.button("Importa Giacenze"):
                sheet_upload_tab = get_sheet(selected_sheet_id, nome_sheet_tab)
                
                with st.spinner("Aggiorno giacenze su GSheet..."):
                    sheet_upload_tab.clear()
                    sheet_upload_tab.update("A1", data_to_write)
                            
                    last_row = len(df_input) + 1
    
                    ranges_to_format = [
                        (f"{col_letter}2:{col_letter}{last_row}",
                            CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=pattern)))
                        for col_letter, pattern in numeric_cols_info.items()
                    ]
                    format_cell_ranges(sheet_upload_tab, ranges_to_format)
                    st.success("✅ Giacenze importate con successo!")

                if nome_file == "Manuale" and file_bytes_for_upload:
                    with st.spinner("Carico il file su DropBox..."):
                        upload_csv_to_dropbox(dbx, folder_path, f"{manual_nome_file}", file_bytes_for_upload)
                        
        with col3:
            if st.button("Importa Giacenze & Anagrafica"):
                sheet_upload_tab = get_sheet(selected_sheet_id, nome_sheet_tab)
                sheet_upload_anagrafica = get_sheet(selected_sheet_id, "ANAGRAFICA")
                sheet_anagrafica = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                
                with st.spinner("Aggiorno giacenze e anagrafica su GSheet..."):
                    sheet_upload_tab.clear()
                    sheet_upload_tab.update("A1", data_to_write)
                            
                    last_row = len(df_input) + 1
    
                    ranges_to_format = [
                        (f"{col_letter}2:{col_letter}{last_row}",
                            CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=pattern)))
                        for col_letter, pattern in numeric_cols_info.items()
                    ]
                    format_cell_ranges(sheet_upload_tab, ranges_to_format)

                    sheet_upload_anagrafica.clear()
                    sheet_upload_anagrafica.update("A1", sheet_anagrafica.get_all_values())
                    st.success("✅ Giacenze e anagrafica importate con successo!")
    
                if nome_file == "Manuale" and file_bytes_for_upload:
                    with st.spinner("Carico il file su DropBox..."):
                        upload_csv_to_dropbox(dbx, folder_path, f"{manual_nome_file}", file_bytes_for_upload)


        with col4:
            if nome_file == "Manuale" and file_bytes_for_upload:
                if st.button("Carica su DropBox"):
                    with st.spinner("Carico il file su DropBox..."):
                        upload_csv_to_dropbox(dbx, folder_path, f"{manual_nome_file}", file_bytes_for_upload)

                    
    with col1:
        if st.button("Importa Anagrafica"):
            sheet_upload_anagrafica = get_sheet(selected_sheet_id, "ANAGRAFICA")
            sheet_anagrafica = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
            
            with st.spinner("Aggiorno anagrafica su GSheet..."):
                sheet_upload_anagrafica.clear()
                sheet_upload_anagrafica.update("A1", sheet_anagrafica.get_all_values())
                st.success("✅ Anagrafica importata con successo!")


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
