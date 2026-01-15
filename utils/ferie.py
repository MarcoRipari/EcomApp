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
    # Estraiamo i dati dalla nuova richiesta
    nome_nuovo = riga[0]
    # Assicuriamoci che siano oggetti date per il confronto
    inizio_nuovo = datetime.strptime(riga[1], '%d-%m-%Y').date() if isinstance(riga[1], str) else riga[1]
    fine_nuovo = datetime.strptime(riga[2], '%d-%m-%Y').date() if isinstance(riga[2], str) else riga[2]
    
    sheet = get_sheet(ferie_sheet_id, "FERIE")
    
    try:
        # Recuperiamo tutti i dati
        esistenti = sheet.get_all_records()
        
        for record in esistenti:
            # 1. Filtriamo per nome (attenzione alle maiuscole/minuscole e spazi)
            if str(record.get('NOME', '')).strip().lower() == str(nome_nuovo).strip().lower():
                
                # 2. Convertiamo le date del foglio da stringa a oggetto date
                try:
                    inizio_es = datetime.strptime(record['INIZIO'], '%d-%m-%Y').date()
                    fine_es = datetime.strptime(record['FINE'], '%d-%m-%Y').date()
                    
                    # 3. Logica di sovrapposizione (OVERLAP)
                    # (Inizio1 <= Fine2) AND (Inizio2 <= Fine1)
                    if inizio_nuovo <= fine_es and inizio_es <= fine_nuovo:
                        return f"❌ Errore: {nome_nuovo} è già assente dal {record['INIZIO']} al {record['FINE']}"
                
                except (ValueError, KeyError):
                    continue # Salta righe vuote o con formato data errato
                    
    except Exception as e:
        return f"⚠️ Errore durante il controllo del foglio: {e}"

    # --- Se arriviamo qui, non ci sono sovrapposizioni ---
    totale_giorni = calcola_giorni_lavorativi_esatti(inizio_nuovo, fine_nuovo)
    
    # Prepariamo la riga finale con le date formattate come stringhe per Google Sheets
    riga_da_salvare = [
        nome_nuovo, 
        inizio_nuovo.strftime('%d-%m-%Y'), 
        fine_nuovo.strftime('%d-%m-%Y'), 
        riga[3], # Tipo
        totale_giorni
    ]
    
    try:
        sheet.append_row(riga_da_salvare)
        return True
    except Exception as e:
        return f"🚨 Errore nell'invio dei dati: {e}"
