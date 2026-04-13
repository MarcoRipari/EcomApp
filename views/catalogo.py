import streamlit as st
import pandas as pd
import json

from utils import *

load_functions_from("functions", globals())

catalogo_sheet_id = st.secrets["CATALOGO_GSHEET_ID"]
sheet_ordini = get_sheet(catalogo_sheet_id, "ORDINI")

map_cod_cli = {
  "0019243.016":"ECOM",
  "0039632":"ZFS",
  "0034630":"AMAZON"
}

def catalogo_import_ordini():
  st.title("Importa ordini nuova stagione")

  uploaded_files = st.file_uploader("Carica i file CSV", type="csv", accept_multiple_files=True)
  
  df_totale = pd.DataFrame()
   
  if uploaded_files:
    try:
      for file in uploaded_files:
        df = read_csv_auto_encoding(file)
        df["COD.CLIENTI"] = df["COD.CLIENTI"].map(map_cod_cli)
        df["SKU"] = df["Cod"] + df["Var."] + df["Col."]
        df_totale = pd.concat([df_totale, df], ignore_index=True)
      st.success("File CSV caricati correttamente.")
    except Exception as e:
      st.write(f"Errore: {e}")

    data = df_totale.fillna("").astype(str).values.tolist()
    
    if st.button("Carica su GSheet"):
      if not df_totale.empty:
          with st.spinner("Upload su GSheet in corso..."):
              df_da_caricare = df_totale.fillna("").astype(str)
              data = df_da_caricare.values.tolist()
              
              col_a = sheet_ordini.col_values(1)
              prossima_riga = len(col_a) + 1
              
              riga_fine = prossima_riga + len(data) - 1
              range_target = f"A{prossima_riga}:U{riga_fine}"
              
              sheet_ordini.update(range_target, data, value_input_option="USER_ENTERED")
              
              st.success(f"Caricati correttamente su GSheet a partire dalla riga {prossima_riga}")
      else:
          st.warning("Nessun dato da caricare.")
