import streamlit as st
import pandas as pd
from utils import *

load_functions_from("functions", globals())

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
      st.write(df)
