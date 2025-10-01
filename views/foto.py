import streamlit as st
from utils import *

load_functions_from("functions", globals())

def foto_import_ordini():
  st.title("Importa ordini nuova stagione")

  uploaded_files = st.file_uploader("Carica i file CSV", type="csv", accept_multiple_files=True)

  if uploaded_files:
    for file in uploaded_files:
      st.write(file)
