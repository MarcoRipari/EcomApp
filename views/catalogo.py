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
        output = read_csv_auto_encoding(file)
        df = pd.DataFrame(output[1:].astype(str))
        df["COD.CLIENTI"] = df["COD.CLIENTI"].map(map_cod_cli)
        df["SKU"] = df["Cod"] + df["Var."] + df["Col."]
        df_totale = pd.concat([df_totale, df], ignore_index=True)
      st.success("File CSV caricati correttamente.")
    except Exception as e:
      st.write(f"Errore: {e}")

    data = df_totale.fillna("").astype(str).values.tolist()
    
    if st.button("Carica su GSheet"):
      with st.spinner("Upload su GSheet in corso..."):
        sheet_ordini.append_rows(data, value_input_option="RAW")
        st.success("Caricati correttamente su GSheet")
