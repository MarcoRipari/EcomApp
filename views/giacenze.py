import streamlit as st
from streamlit_option_menu import option_menu
import gspread
from gspread_formatting import *
import numpy as np
import logging
import time
from io import BytesIO, StringIO

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
    
    # Parametri Dropbox (Assicurati che get_dropbox_client e anagrafica_sheet_id siano definiti globalmente)
    dbx = get_dropbox_client()
    folder_path = "/GIACENZE"
    manual_nome_file = "GIACENZE.csv"

    # --- 2. STATO PERSISTENTE ---
    if "import_logs" not in st.session_state: st.session_state.import_logs = {}
    if "import_in_corso" not in st.session_state: st.session_state.import_in_corso = False
    if "target_rimanenti" not in st.session_state: st.session_state.target_rimanenti = []
    if "current_row_index" not in st.session_state: st.session_state.current_row_index = 0
    if "file_bytes_for_upload" not in st.session_state: st.session_state.file_bytes_for_upload = None
    if "df_input" not in st.session_state: st.session_state.df_input = None

    # --- 3. CARICAMENTO FILE ---
    uploaded_file = st.file_uploader("Carica un file CSV", type="csv", key="uploader_manual")
    if uploaded_file:
        content = uploaded_file.getvalue()
        if st.session_state.file_bytes_for_upload != content:
            st.session_state.file_bytes_for_upload = content
            st.session_state.df_input = None 
            st.session_state.import_logs = {}

    if st.session_state.file_bytes_for_upload and st.session_state.df_input is None:
        buffer = BytesIO(st.session_state.file_bytes_for_upload)
        st.session_state.df_input = read_csv_auto_encoding(buffer, ";")

    df_input = st.session_state.df_input

    # --- 4. INPUT UTENTE ---
    options = ["COMPLETO"] + list(SHEETS_CONFIG.keys())
    sheet_selection = st.selectbox("Seleziona target:", options)
    targets_finali = list(SHEETS_CONFIG.values()) if sheet_selection == "COMPLETO" else [SHEETS_CONFIG[sheet_selection]]
    
    # Riferimento al nome del foglio (tab)
    nome_sheet_tab = st.text_input("Nome del TAB", value="GIACENZE")

    # --- 5. PULSANTI ---
    col1, col2, col3, col4 = st.columns(4)

    def start_process(tipo):
        st.session_state.import_logs = {k: "⏳ In coda" for k in SHEETS_CONFIG.keys() if SHEETS_CONFIG[k] in targets_finali}
        st.session_state.target_rimanenti = targets_finali.copy()
        st.session_state.import_in_corso = tipo
        st.session_state.current_row_index = 0
        st.session_state.anagrafica_data = None # Reset dati temporanei
        st.rerun()

    if col1.button("Anagrafica", use_container_width=True): start_process("ANAGRAFICA")
    if col2.button("Giacenze", use_container_width=True): start_process("GIACENZE")
    if col3.button("Tutto", use_container_width=True): start_process("TOTALE")
    if col4.button("Dropbox", use_container_width=True):
        if st.session_state.file_bytes_for_upload:
            with st.spinner("Upload Dropbox..."):
                upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
            st.success("Backup OK!")

    # Tabella Avanzamento
    if st.session_state.import_logs:
        st.divider()
        st.subheader("📊 Stato Avanzamento")
        st.table([{"Foglio": k, "Stato": v} for k, v in st.session_state.import_logs.items()])

    # --- 6. CORE LOOP CON AUTO-RESUME ---
    if st.session_state.import_in_corso and st.session_state.target_rimanenti:
        current_id = st.session_state.target_rimanenti[0]
        nome_leggibile = next((k for k, v in SHEETS_CONFIG.items() if v == current_id), f"ID: {current_id[:5]}")
        
        try:
            # A. ANAGRAFICA
            if st.session_state.import_in_corso in ["ANAGRAFICA", "TOTALE"]:
                # Se non abbiamo ancora scaricato i dati dell'anagrafica sorgente
                st.session_state.import_logs[nome_leggibile] = "⏳ Import Anagrafica..."
                sh_src = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                sh_dest = get_sheet(current_id, "ANAGRAFICA")
                sh_dest.clear()
                sh_dest.update("A1", sh_src.get_all_values())
                st.session_state.import_logs[nome_leggibile] = "✅ Anagrafica importata correttamente."
                if st.session_state.import_in_corso == "ANAGRAFICA":
                  st.session_state.target_rimanenti.pop(0)
                  st.session_state.current_row_index = 0
                st.rerun()

            # B. GIACENZE
            if st.session_state.import_in_corso in ["GIACENZE", "TOTALE"]:
                # Utilizziamo la variabile nome_sheet_tab definita sopra
                sh_gia = get_sheet(current_id, nome_sheet_tab)
                
                # Elaborazione dati
                df_proc = df_input.copy()
                cols_to_fix = [3, 12, 14, 15] + list(range(17, 29))
                for idx in cols_to_fix:
                    if df_proc.columns.size > idx:
                        c_name = df_proc.columns[idx]
                        df_proc[c_name] = pd.to_numeric(df_proc[c_name].astype(str).str.replace(',', '.'), errors='coerce')
                
                intestazioni = df_proc.columns.tolist()
                if len(intestazioni) >= 27:
                    intestazioni[18:27] = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
                
                rows = df_proc.fillna("").values.tolist()
                total_rows = len(rows)
                CHUNK_SIZE = 3000

                # 1. Pulizia e Intestazioni
                if st.session_state.current_row_index <= 1:
                    st.session_state.import_logs[nome_leggibile] = f"🧹 Pulizia {nome_sheet_tab}..."
                    sh_gia.batch_clear(["A1:AZ35000"])
                    sh_gia.update("A1", [intestazioni], value_input_option="USER_ENTERED")
                    st.session_state.current_row_index = 2
                    st.rerun()

                # 2. Caricamento a Blocchi
                start_idx = st.session_state.current_row_index - 2
                if start_idx < total_rows:
                    end_idx = min(start_idx + CHUNK_SIZE, total_rows)
                    st.session_state.import_logs[nome_leggibile] = f"🚀 Caricamento: {end_idx} / {total_rows}"
                    
                    chunk = rows[start_idx : end_idx]
                    sh_gia.update(f"A{st.session_state.current_row_index}", chunk, value_input_option="USER_ENTERED")
                    
                    st.session_state.current_row_index += len(chunk)
                    st.rerun()
                else:
                    # Fine del foglio corrente
                    st.session_state.import_logs[nome_leggibile] = "✅ Completato"
                    st.session_state.target_rimanenti.pop(0)
                    st.session_state.current_row_index = 0
                    st.rerun()

        except Exception as e:
            st.session_state.import_logs[nome_leggibile] = f"❌ Errore: {str(e)[:30]}"
            st.session_state.import_in_corso = False

    # Fine totale del processo
    if not st.session_state.target_rimanenti and st.session_state.import_in_corso:
        if st.session_state.file_bytes_for_upload:
            upload_csv_to_dropbox(dbx, folder_path, manual_nome_file, st.session_state.file_bytes_for_upload)
        st.session_state.import_in_corso = False
        st.balloons()


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
