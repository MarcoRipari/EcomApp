import streamlit as st
import gspread

from utils import *

load_functions_from("functions", globals())

ferie_sheet_id = st.secrets["FERIE_GSHEET_ID"]

def calcola_giorni_lavorativi(inizio, fine):
  giorni_lavorativi = 0
  giorno_corrente = inizio
  while giorno_corrente <= fine:
    # 0 = Lunedì, 1 = Martedì, ..., 4 = Venerdì, 5 = Sabato, 6 = Domenica
    if giorno_corrente.weekday() < 5:
      giorni_lavorativi += 1
    giorno_corrente += timedelta(days=1)
  return giorni_lavorativi

def add_ferie(riga):
  st.write(riga[0])
  sheet = get_sheet(ferie_sheet_id,"FERIE")
  try:
    sheet.append_row(riga)
    return true
  except Exception as e:
    return e
