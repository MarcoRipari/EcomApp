import streamlit as st
import pandas as pd
import json

from utils import *

load_functions_from("functions", globals())

foto_sheet_id = "1MFwBu5qcXwD0Hti1Su9KTxl3Z9OLGtQtp1d3HJNEiY4"
sheet_ordini = get_sheet(foto_sheet_id, "ORDINI")

map_cod_cli = {
  "0019243.016":"ECOM",
  "0039632":"ZFS",
  "0034630":"AMAZON"
}

def foto_import_ordini():
  st.title("Importa ordini nuova stagione")

  uploaded_files = st.file_uploader("Carica i file CSV", type="csv", accept_multiple_files=True)

  if uploaded_files:
    for file in uploaded_files:
      output = read_csv_auto_encoding(file)
      df = pd.DataFrame(output[1:])
      df["COD.CLIENTI"] = df["COD.CLIENTI"].map(map_cod_cli)
      
      data = df
      sheet_ordini.append_rows(data, value_input_option="RAW")
