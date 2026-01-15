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
  inizio_nuovo = datetime.strptime(riga[1], '%d-%m-%Y').date() if isinstance(riga[1], str) else riga[1]
  fine_nuovo = datetime.strptime(riga[2], '%d-%m-%Y').date() if isinstance(riga[2], str) else riga[2]
  
  sheet = get_sheet(ferie_sheet_id, "FERIE")
  
  try:
    esistenti = sheet.get_all_records()
    
    # DEBUG: Decommenta la riga sotto se vuoi vedere cosa legge Python dal foglio
    # st.write(esistenti[0].keys()) 

    for record in esistenti:
      # Pulizia chiavi: trasformiamo tutto in maiuscolo e togliamo spazi extra per sicurezza
      record_clean = {str(k).strip().upper(): v for k, v in record.items()}
      
      # Confronto Nome
      if str(record_clean.get('NOME', '')).strip().lower() == str(nome_nuovo).strip().lower():
        try:
          # Cerchiamo le colonne indipendentemente da piccoli errori di digitazione
          data_inizio_str = record_clean.get('DATA INIZIO') or record_clean.get('INIZIO')
          data_fine_str = record_clean.get('DATA FINE') or record_clean.get('FINE')

          if data_inizio_str and data_fine_str:
            inizio_es = datetime.strptime(str(data_inizio_str), '%d-%m-%Y').date()
            fine_es = datetime.strptime(str(data_fine_str), '%d-%m-%Y').date()
            
            # LOGICA OVERLAP
            if inizio_nuovo <= fine_es and inizio_es <= fine_nuovo:
              return f"❌ Errore: {nome_nuovo} è già assente dal {data_inizio_str} al {data_fine_str}"
          
        except Exception as e:
          # Se c'è un errore qui, vogliamo saperlo, non solo 'continue'
          # st.error(f"Errore parsing riga: {e}") 
          continue 
                  
  except Exception as e:
    return f"⚠️ Errore durante il controllo del foglio: {e}"

  # --- PROCEDI AL SALVATAGGIO ---
  totale_giorni = calcola_giorni_lavorativi_esatti(inizio_nuovo, fine_nuovo)
  
  riga_da_salvare = [
    nome_nuovo, 
    inizio_nuovo.strftime('%d-%m-%Y'), 
    fine_nuovo.strftime('%d-%m-%Y'), 
    riga[3], 
    totale_giorni
  ]
  
  try:
    sheet.append_row(riga_da_salvare)
    return True
  except Exception as e:
    return f"🚨 Errore nell'invio dei dati: {e}"
