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
  nome_nuovo = riga[0]
  inizio_nuovo = datetime.strptime(riga[1], '%d-%m-%Y').date()
  fine_nuovo = datetime.strptime(riga[2], '%d-%m-%Y').date()
  
  sheet = get_sheet(ferie_sheet_id, "FERIE")
  
  # --- 1. CONTROLLO SOVRAPPOSIZIONI ---
  try:
    # Recuperiamo tutti i dati esistenti
    esitenti = sheet.get_all_records()
    
    for record in esitenti:
      # Controlliamo solo i record dello stesso dipendente
      if record['NOME'] == nome_nuovo:
        try:
          inizio_es = datetime.strptime(record['INIZIO'], '%d-%m-%Y').date()
          fine_es = datetime.strptime(record['FINE'], '%d-%m-%Y').date()
          
          # Logica di sovrapposizione:
          # Se l'inizio della nuova è prima della fine della vecchia
          # E la fine della nuova è dopo l'inizio della vecchia
          if inizio_nuovo <= fine_es and fine_nuovo >= inizio_es:
            return f"Errore: {nome_nuovo} ha già un'assenza registrata in questo periodo ({record['INIZIO']} - {record['FINE']})"
        except ValueError:
          continue # Salta righe con date malformate nel foglio
                  
  except Exception as e:
    return f"Errore durante il controllo disponibilità: {e}"

  # --- 2. INSERIMENTO (Se il controllo è passato) ---
  totale_giorni = calcola_giorni_lavorativi_esatti(inizio_nuovo, fine_nuovo)
  
  # Se 'riga' ha già i 4 elementi (Nome, Inizio, Fine, Tipo), aggiungiamo il totale
  if len(riga) == 4:
    riga.append(totale_giorni)
  
  try:
    sheet.append_row(riga)
    return True # In Python 'True' è maiuscolo
  except Exception as e:
    return f"Errore nel salvataggio: {e}"
