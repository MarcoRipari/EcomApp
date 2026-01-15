import streamlit as st
import gspread

from utils import *

load_functions_from("functions", globals())

def ferie():
  st.header("Ferie")

def aggiungi_ferie():
  st.header("Aggiungi ferie")

  with st.form("form_ferie", clear_on_submit=True):
    nome = st.text_input("Nome Dipendente")
    
    col1, col2 = st.columns(2)
    with col1:
        data_inizio = st.date_input("Data inizio")
    with col2:
        data_fine = st.date_input("Data fine")
        
    tipo = st.selectbox("Tipo di assenza", ["Ferie", "Malattia", "Permesso", "Altro"])
    
    submit = st.form_submit_button("Inserisci")
    
    if submit:
      if not nome:
        st.error("Il campo 'Nome' è obbligatorio.")
      elif tipo == "":
        st.error("Seleziona un 'Tipo' di assenza.")
      elif data_fine < data_inizio:
        st.error("Errore: la data di fine non può essere precedente alla data di inizio.")
      else:
        upload = aggiungi_ferie(nuova_riga)
        if upload:
          st.success("Ferie inserite con successo!")
        else:
          st.error(f"Errore tecnico: {upload}")
