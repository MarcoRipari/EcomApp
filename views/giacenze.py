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
    st.header("Importa giacenze2")

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
    if "file_bytes_for_upload" not in st.session_state: st.session_state.file_bytes_for_upload = None

    uploaded_file = st.file_uploader("Carica un file CSV", type="csv", key="uploader_manual")
    if uploaded_file:
        content = uploaded_file.getvalue()
        if st.session_state.file_bytes_for_upload != content:
            st.session_state.file_bytes_for_upload = content
            st.session_state.import_logs = {}

    options = ["COMPLETO"] + list(SHEETS_CONFIG.keys())
    sheet_selection = st.selectbox("Seleziona target:", options)
    targets_finali = list(SHEETS_CONFIG.values()) if sheet_selection == "COMPLETO" else [SHEETS_CONFIG[sheet_selection]]
    nome_sheet_tab = st.text_input("Nome del TAB", value="GIACENZE")

    col1, col2, col3 = st.columns(3)
    def avvia(modo):
        st.session_state.import_logs = {k: "⏳ In coda" for k in SHEETS_CONFIG.keys() if SHEETS_CONFIG[k] in targets_finali}
        st.session_state.target_rimanenti = targets_finali.copy()
        st.session_state.import_in_corso = modo
        st.rerun()

    if col1.button("Anagrafica"): avvia("ANAGRAFICA")
    if col2.button("Giacenze"): avvia("GIACENZE")
    if col3.button("Tutto"): avvia("TOTALE")

    if st.session_state.import_logs:
        st.divider()
        st.table([{"Foglio": k, "Stato": v} for k, v in st.session_state.import_logs.items()])

    # --- CORE LOOP ---
    if st.session_state.import_in_corso and st.session_state.target_rimanenti:
        current_id = st.session_state.target_rimanenti.pop(0)
        nome_leggibile = next((k for k, v in SHEETS_CONFIG.items() if v == current_id), "Sheet")
        
        st.session_state.import_logs[nome_leggibile] = "⏳ In corso..."
        
        try:
            # A. ANAGRAFICA
            if st.session_state.import_in_corso in ["ANAGRAFICA", "TOTALE"]:
                sh_ana = get_sheet(current_id, "ANAGRAFICA")
                sh_src = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
                sh_ana.batch_clear(["A1:Z2000"]) # Batch clear non rompe la formattazione esistente
                sh_ana.update("A1", sh_src.get_all_values())

            # B. GIACENZE
            if st.session_state.import_in_corso in ["GIACENZE", "TOTALE"]:
                sh_gia = get_sheet(current_id, nome_sheet_tab)
                df_temp = read_csv_auto_encoding(BytesIO(st.session_state.file_bytes_for_upload), ";")
                
                # Conversione numeri rapida (vettorizzata)
                numeric_cols_indices = [3, 12, 14, 15] + list(range(17, 29)) # D, M, O, P e Magazzini
                for idx in numeric_cols_indices:
                    if df_temp.columns.size > idx:
                        col_name = df_temp.columns[idx]
                        df_temp[col_name] = pd.to_numeric(df_temp[col_name].astype(str).str.replace(',', '.'), errors='coerce').fillna("")

                data = [df_temp.columns.tolist()] + df_temp.fillna("").values.tolist()
                if len(data[0]) >= 27:
                    data[0][18:27] = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
                
                # PULIZIA CONTENUTI SENZA TOCCARE IL FORMATO DELLE CELLE
                sh_gia.batch_clear(["A1:AZ10000"]) 
                sh_gia.update("A1", data)

                # FORMATTAZIONE "LIGHT" (Opzionale, solo se vuoi forzare il formato numero)
                # Applichiamo un formato unico a tutto il blocco numerico per risparmiare tempo
                fmt = CellFormat(numberFormat=NumberFormat(type="NUMBER", pattern="0"))
                format_cell_range(sh_gia, "D2:AC10000", fmt)

            st.session_state.import_logs[nome_leggibile] = "✅ Completato"
        except Exception as e:
            st.session_state.import_logs[nome_leggibile] = f"❌ Errore: {str(e)[:25]}"

        if not st.session_state.target_rimanenti:
            st.session_state.import_in_corso = False
            st.balloons()
        
        st.rerun()


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
