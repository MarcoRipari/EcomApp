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

    # --- 2. STATO PERSISTENTE ---
    if "import_logs" not in st.session_state: st.session_state.import_logs = {}
    if "import_in_corso" not in st.session_state: st.session_state.import_in_corso = False
    if "target_rimanenti" not in st.session_state: st.session_state.target_rimanenti = []
    if "current_row_index" not in st.session_state: st.session_state.current_row_index = 0
    if "file_bytes_for_upload" not in st.session_state: st.session_state.file_bytes_for_upload = None

    uploaded_file = st.file_uploader("Carica CSV", type="csv")
    if uploaded_file:
        content = uploaded_file.getvalue()
        if st.session_state.file_bytes_for_upload != content:
            st.session_state.file_bytes_for_upload = content
            st.session_state.import_logs = {}

    options = ["COMPLETO"] + list(SHEETS_CONFIG.keys())
    sheet_selection = st.selectbox("Target:", options)
    targets_finali = list(SHEETS_CONFIG.values()) if sheet_selection == "COMPLETO" else [SHEETS_CONFIG[sheet_selection]]

    if st.button("Avvia Giacenze"):
        st.session_state.import_logs = {k: "⏳ In coda" for k in SHEETS_CONFIG.keys() if SHEETS_CONFIG[k] in targets_finali}
        st.session_state.target_rimanenti = targets_finali.copy()
        st.session_state.import_in_corso = "GIACENZE"
        st.session_state.current_row_index = 0
        st.rerun()

    if st.session_state.import_logs:
        st.divider()
        st.table([{"Foglio": k, "Stato": v} for k, v in st.session_state.import_logs.items()])

    # --- CORE LOOP CON AUTO-RESUME ---
    if st.session_state.import_in_corso and st.session_state.target_rimanenti:
        current_id = st.session_state.target_rimanenti[0] # Non facciamo pop() subito
        nome_leggibile = next((k for k, v in SHEETS_CONFIG.items() if v == current_id), "Sheet")
        
        try:
            sh_gia = get_sheet(current_id, "GIACENZE")
            df_temp = read_csv_auto_encoding(BytesIO(st.session_state.file_bytes_for_upload), ";")
            
            # Conversione numeri
            cols_to_fix = [3, 12, 14, 15] + list(range(17, 29))
            for idx in cols_to_fix:
                if df_temp.columns.size > idx:
                    c_name = df_temp.columns[idx]
                    df_temp[c_name] = pd.to_numeric(df_temp[c_name].astype(str).str.replace(',', '.'), errors='coerce')
            
            rows = df_temp.fillna("").values.tolist()
            total_rows = len(rows)
            CHUNK_SIZE = 2000

            # Se siamo all'inizio del foglio, puliamo e mettiamo intestazioni
            if st.session_state.current_row_index == 0:
                st.session_state.import_logs[nome_leggibile] = "🧹 Pulizia..."
                sh_gia.batch_clear(["A1:AZ35000"])
                intestazioni = df_temp.columns.tolist()
                if len(intestazioni) >= 27:
                    intestazioni[18:27] = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
                sh_gia.update("A1", [intestazioni], value_input_option="USER_ENTERED")
                st.session_state.current_row_index = 1 # Segna che abbiamo iniziato
                st.rerun()

            # Invio del blocco corrente
            i = st.session_state.current_row_index - 1 # Riportiamo a 0-based per lo slice
            if i < total_rows:
                end_idx = min(i + CHUNK_SIZE, total_rows)
                st.session_state.import_logs[nome_leggibile] = f"🚀 Caricamento: {end_idx} / {total_rows}"
                
                chunk = rows[i : end_idx]
                start_row_google = i + 2
                sh_gia.update(f"A{start_row_google}", chunk, value_input_option="USER_ENTERED")
                
                # AGGIORNA INDICE E FORZA RERUN (Rinfresca la connessione)
                st.session_state.current_row_index = end_idx + 1
                st.rerun()
            else:
                # FOGLIO COMPLETATO
                st.session_state.import_logs[nome_leggibile] = "✅ Completato"
                st.session_state.target_rimanenti.pop(0) # Rimuoviamo il foglio finito
                st.session_state.current_row_index = 0 # Resetta per il prossimo foglio
                st.rerun()

        except Exception as e:
            st.session_state.import_logs[nome_leggibile] = f"❌ Errore: {str(e)[:30]}"
            st.session_state.import_in_corso = False

    if not st.session_state.target_rimanenti and st.session_state.import_logs:
        if st.session_state.import_in_corso:
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
