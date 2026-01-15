import streamlit as st
import gspread
import holidays

from utils import *

load_functions_from("functions", globals())

ferie_sheet_id = st.secrets["FERIE_GSHEET_ID"]

def calcola_giorni_lavorativi_esatti(inizio, fine):
  # Inizializza le festività italiane per l'anno corrente e il successivo
  it_holidays = holidays.Italy(years=[inizio.year, fine.year])
  
  giorni_lavorativi = 0
  giorno_corrente = inizio
  
  while giorno_corrente <= fine:
    # Controlla: 
    # 1. Che sia lunedì-venerdì (weekday < 5)
    # 2. Che NON sia una festività nazionale
    if giorno_corrente.weekday() < 5 and giorno_corrente not in it_holidays:
      giorni_lavorativi += 1
    giorno_corrente += timedelta(days=1)
      
  return giorni_lavorativi

def add_ferie(riga):
  totale_giorni = calcola_giorni_lavorativi_esatti(riga[1], riga[2])
  #riga.append(totale_giorni)
  sheet = get_sheet(ferie_sheet_id,"FERIE")
  try:
    sheet.append_row(riga)
    return true
  except Exception as e:
    return e
