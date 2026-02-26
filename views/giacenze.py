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

    # --- 1. STATO PERSISTENTE (Per evitare reset durante il loop) ---
    if "df_input" not in st.session_state:
        st.session_state.df_input = None
    if "file_bytes_for_upload" not in st.session_state:
        st.session_state.file_bytes_for_upload = None
    if "import_in_corso" not in st.session_state:
        st.session_state.import_in_corso = False
    if "target_rimanenti" not in st.session_state:
        st.session_state.target_rimanenti = []
    if "import_logs" not in st.session_state:
        st.session_state.import_logs = {}

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
            st.session_state.import_logs = {} # Reset log se il file cambia

    # Lettura automatica se il file è presente ma il DF è vuoto
    if st.session_state.file_bytes_for_upload and st.session_state.df_input is None:
        with st.spinner("Analisi dei dati in corso..."):
            buffer = BytesIO(st.session_state.file_bytes_for_upload)
            st.session_state.df_input = read_csv_auto_encoding(buffer, ";")

    df_input = st.session_state.df_input

    # --- 3. CONFIGURAZIONE TARGET E MAPPATURA NOMI ---
    # Recuperiamo gli ID dalla tua variabile globale sheets_to_import
    # (Assumo che sheets_to_import sia definita altrove nel tuo codice)
    
    SHEETS_MAP = {
        "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4": "Foglio FOTO",
        "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U": "Foglio GIACENZE"
    }
    
    # Integriamo dinamicamente i nomi per il set COMPLETO
    if 'sheets_to_import' in globals() and isinstance(sheets_to_import, list):
        for s_id in sheets_to_import:
            if s_id not in SHEETS_MAP:
                SHEETS_MAP[s_id] = f"Target Completo ({s_id[:6]})"

    SHEETS_OPTIONS = {
        "COMPLETO": sheets_to_import if 'sheets_to_import' in globals() else [], 
        "Foglio FOTO": "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4",
        "Foglio GIACENZE": "13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U",
    }
    
    options = list(SHEETS_OPTIONS.keys()) + ["Manuale"]
    sheet_option = st.selectbox("Seleziona target:", options)
    
    if sheet_option in SHEETS_OPTIONS:
        selected_sheet_id = SHEETS_OPTIONS[sheet_option]
    else:
        selected_sheet_id = st.text_input("ID Google Sheet manuale")

    nome_sheet_tab = st.text_input("Nome del TAB", value="GIACENZE")

    # --- 4. LOGICA DI PREPARAZIONE DATI ---
    if df_input is not None:
        # Checkbox per visualizzazione (sobria)
        if st.checkbox("Visualizza anteprima dati", value=False):
            st.dataframe(df_input.head(10), use_container_width=True)

        # Preprocessing numerico
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

        # Conversione in lista per GSheets
        data_to_write = [df_proc.columns.tolist()] + df_proc.fillna("").values.tolist()
        
        # Intestazioni magazzini fisse
        intestazioni_magazzini = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
        if len(data_to_write[0]) >= 27:
            data_to_write[0][18:27] = intestazioni_magazzini

        # --- 5. AZIONI (COLONNE) ---
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("Importa Anagrafica", use_container_width=True):
                targets = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                for s in targets:
                    with st.spinner(f"Anagrafica -> {SHEETS_MAP.get(s, s)}"):
                        sh_dest = get_sheet(s, "ANAGRAFICA")
                        sh_src = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                        sh_dest.clear()
                        sh_dest.update("A1", sh_src.get_all_values())
                st.toast("Anagrafiche aggiornate!")

        with col2:
            if st.button("Importa Giacenze", use_container_width=True):
                st.session_state.target_rimanenti = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                st.session_state.import_in_corso = "GIACENZE"
                st.session_state.import_logs = {}
                st.rerun()

        with col3:
            if st.button("Giacenze + Anagrafica", use_container_width=True):
                st.session_state.target_rimanenti = selected_sheet_id if isinstance(selected_sheet_id, list) else [selected_sheet_id]
                st.session_state.import_in_corso = "TOTALE"
                st.session_state.import_logs = {}
                st.rerun()

        with col4:
            if st.button("Backup Dropbox", use_container_width=True):
                if st.session_state.file_bytes_for_upload:
                    with st.spinner("Caricamento..."):
                        upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
                    st.success("Sincronizzato!")

        # --- 6. CORE LOOP (Auto-eseguito dopo il rerun) ---
        if st.session_state.import_in_corso and st.session_state.target_rimanenti:
            current_target = st.session_state.target_rimanenti.pop(0)
            nome_leggibile = SHEETS_MAP.get(current_target, current_target)
            modalita = st.session_state.import_in_corso
            
            with st.status(f"Elaborazione: **{nome_leggibile}**...", expanded=False) as status:
                try:
                    # Parte 1: Giacenze
                    sh = get_sheet(current_target, nome_sheet_tab)
                    sh.clear()
                    sh.update("A1", data_to_write)
                    
                    # Formattazione
                    last_row = len(df_proc) + 1
                    ranges = [(f"{c}2:{c}{last_row}", CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern=p))) 
                              for c, p in numeric_cols_info.items()]
                    format_cell_ranges(sh, ranges)
                    
                    # Parte 2: Anagrafica (se modalità TOTALE)
                    if modalita == "TOTALE":
                        sh_dest = get_sheet(current_target, "ANAGRAFICA")
                        sh_src = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                        sh_dest.clear()
                        sh_dest.update("A1", sh_src.get_all_values())

                    st.session_state.import_logs[nome_leggibile] = "✅ OK"
                except Exception as e:
                    st.session_state.import_logs[nome_leggibile] = f"❌ Errore: {str(e)[:40]}..."
                
                status.update(label=f"Completato: {nome_leggibile}", state="complete")
            
            st.rerun()

        # --- 7. FINE E RIEPILOGO ---
        if st.session_state.import_logs:
            if not st.session_state.target_rimanenti and st.session_state.import_in_corso:
                # Abbiamo appena finito l'ultimo
                st.session_state.import_in_corso = False
                if st.session_state.file_bytes_for_upload:
                    upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
                st.balloons()

            # Tabella riepilogativa finale
            st.divider()
            st.subheader("Riepilogo Operazioni", divider="green")
            res_df = pd.DataFrame([{"Foglio": k, "Stato": v} for k, v in st.session_state.import_logs.items()])
            st.dataframe(res_df, use_container_width=True, hide_index=True)


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
