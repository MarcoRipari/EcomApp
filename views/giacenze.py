import streamlit as st
from streamlit_option_menu import option_menu
import gspread
import numpy as np
import logging

from utils import *

load_functions_from("functions", globals())

anagrafica_sheet_id = st.secrets["ANAGRAFICA_GSHEET_ID"]
giacenze_sheet_id = st.secrets["GIACENZE_GSHEET_ID"]

sheets_to_import2 = ['1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4', # FOTO
                    '13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U', # VECCHIA STAGIONE
                    '1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ', # NUOVA STAGIONE
                    '1o8Zir8DNKxW9QERqeZr7G-EEnoTqwRVYlyuOrzQJnhA', # SELE-SALDI-25-2
                    '1mvMi-ybuLdIF3GnAnl2GLqR2Bxic1nBD3Bxt1GQZTec', # Base_Dati_Retag
                    '1eR3ZOE6IzGgYP4mPnyGBfWiDof4Gpv9olOVu_G_k1dg', # SELE-OUTLET-PE26
                    '1wvHZpS8Y45V4MWKgVv_WZx7t98p3Z83EXWc_e9vNFwc'  # LISTA-SKUS-PE26
                   ]


sheets_to_import = ['1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4', # FOTO
                    '13DnpAX7M9wymMR1YIH5IP28y_UaCPajBUIcoHca562U', # VECCHIA STAGIONE
                    '1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ', # NUOVA STAGIONE
                   ]

def giacenze_importa():
  st.header("Importa giacenze")

  csv_import = None
  file_bytes_for_upload = None
  last_update = None
  df_input = None

  dbx = get_dropbox_client()
  folder_path = "/GIACENZE"

  uploaded_file = st.file_uploader("Carica un file CSV manualmente", type="csv", key="uploader_manual")

  if uploaded_file:
    uploaded_file.seek(0)
        
    csv_import = uploaded_file
    file_bytes_for_upload = csv_import.getvalue()
    manual_nome_file = "GIACENZE.csv"

  # --- Carico CSV solo se df_input è None ---
  if csv_import:
    with st.spinner("Carico il CSV..."):
      df_input = read_csv_auto_encoding(csv_import, ";")

  default_sheet_id = giacenze_sheet_id
  
  SHEETS = {
    "COMPLETO": sheets_to_import,
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


  status_container = st.empty()
  
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

      
      
    data_to_write = [df_input.columns.tolist()] + df_input.values.tolist()
      
    intestazioni_magazzini = ["060/029","060/018","060/015","060/025","027/001","028/029","139/029","028/001","012/001"]
    data_to_write[0][18:27] = intestazioni_magazzini

    def import_giacenze(sheet_id, tab, n_cols, dtw):
      try:
        with status_container.container():
          st.info(f"Aggiorno foglio {sheet_id}")
          sheet_upload_tab = get_sheet(sheet_id, tab)
          sheet_upload_tab.clear()
          sheet_upload_tab.update("A1", dtw)
                        
          last_row = len(df_input) + 1
          st.success(f"✅ {sheet_id} - Giacenze importate con successo!")
        
        return True
      except Exception as e:
        return e

    def import_anagrafica(sheet_id):
      sheet_upload_anagrafica = get_sheet(sheet_id, "ANAGRAFICA")
      sheet_anagrafica = get_sheet(anagrafica_sheet_id, "ANAGRAFICA")
      sheet_upload_anagrafica.clear()
      sheet_upload_anagrafica.update("A1", sheet_anagrafica.get_all_values())
      st.success(f"✅ {sheet_id} - Anagrafica importata con successo!")

      
      # --- Destinazione GSheet ---       
    with col2:
      if st.button("Importa Giacenze"):
        if type(selected_sheet_id) == list:
          for s in selected_sheet_id:
            res = import_giacenze(s, numeric_cols_info, nome_sheet_tab, data_to_write)
            if res:
              st.success(f"✅ {s} - Giacenze importate con successo!")
            else:
              st.error(f"✅ {s} - {res}")
        else:
          res = import_giacenze(selected_sheet_id, numeric_cols_info, nome_sheet_tab, data_to_write)
          if res:
            st.success(f"✅ {selected_sheet_id,} - Giacenze importate con successo!")
          else:
            st.error(f"✅ {selected_sheet_id,} - {res}")
            
      with st.spinner("Carico il file su DropBox..."):
        upload_csv_to_dropbox(dbx, folder_path, f"{manual_nome_file}", file_bytes_for_upload)
              
                      
    with col3:
      if st.button("Importa Giacenze & Anagrafica"):
        if type(selected_sheet_id) == list:
          for s in selected_sheet_id:
            res = import_giacenze(s, numeric_cols_info, nome_sheet_tab, data_to_write)
            if res:
              st.success(f"✅ {s} - Giacenze importate con successo!")
            else:
              st.error(f"✅ {s} - Errore importazione giacenze!")
              
          import_anagrafica(s)
        else:
          res = import_giacenze(selected_sheet_id, numeric_cols_info, nome_sheet_tab, data_to_write)
          if res:
            st.success(f"✅ {selected_sheet_id} - Giacenze importate con successo!")
          else:
            st.error(f"✅ {selected_sheet_id} - {res}")
                    
          import_anagrafica(selected_sheet_id)
                
        with st.spinner("Carico il file su DropBox..."):
          upload_csv_to_dropbox(dbx, folder_path, f"{manual_nome_file}", file_bytes_for_upload)


    with col4:
      if st.button("Carica su DropBox"):
        with st.spinner("Carico il file su DropBox..."):
          upload_csv_to_dropbox(dbx, folder_path, f"{manual_nome_file}", file_bytes_for_upload)

                  
  with col1:
    if st.button("Importa Anagrafica"):
      if type(selected_sheet_id) == list:
        for s in selected_sheet_id:
          import_anagrafica(s)
      else:
        import_anagrafica(selected_sheet_id)


def aggiorna_anagrafica():
    st.header("Aggiorna anagrafica da CSV")

    sheet = get_sheet(anagrafica_sheet_id, "DATA")
    
    uploaded_file = st.file_uploader("Carica CSV", type=["csv"])

    if uploaded_file:
        if st.button("Carica su GSheet"):
            added, updated = process_csv_and_update(sheet, uploaded_file)
            st.success(f"✅ Aggiunte {added} nuove SKU, aggiornate {updated} SKU già presenti.")
