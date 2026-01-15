import streamlit as st
import gspread

def aggiungi_ferie(sheet, riga):
  sheet = connect_to_sheet()
  nuova_riga = [nome, str(data_inizio), str(data_fine), tipo]
  sheet.append_row(nuova_riga)
