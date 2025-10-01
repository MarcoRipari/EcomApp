import streamlit as st
import pandas as pd
from utils import *

load_functions_from("functions", globals())

def foto_import_ordini():
  st.title("Importa ordini nuova stagione")

  uploaded_files = st.file_uploader("Carica i file CSV", type="csv", accept_multiple_files=True)

  if uploaded_files:
    for file in uploaded_files:
      output = read_csv_auto_encoding(file)
      headers = output[1]
      df = pd.DataFrame(output[2:], headers=headers)
      st.write(df)
