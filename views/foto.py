import streamlit as st
from utils import *

load_functions_from("functions", globals())

def foto_import_ordini():
  st.title("Importa ordini nuova stagione")

  uploaded_files = st.upload_file("Carica i file CSV", type="csv", accept_multiple_files=True)
