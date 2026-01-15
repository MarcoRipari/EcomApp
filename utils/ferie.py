import streamlit as st
import gspread
import holidays

from utils import *

load_functions_from("functions", globals())

ferie_sheet_id = st.secrets["FERIE_GSHEET_ID"]

def get_dipendenti():
  sheet = get_sheet(ferie_sheet_id, "DIPENDENTI")
  dipendenti = pd.DataFrame(sheet.get_all_records())['NOME'].tolist().sort_values(by='NOME', ascending=True)
  return dipendenti
  
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
    nome_nuovo = str(riga[0]).strip().lower()
    # Gestione flessibile input data
    inizio_nuovo = datetime.strptime(riga[1], '%d-%m-%Y').date() if isinstance(riga[1], str) else riga[1]
    fine_nuovo = datetime.strptime(riga[2], '%d-%m-%Y').date() if isinstance(riga[2], str) else riga[2]
    
    sheet = get_sheet(ferie_sheet_id, "FERIE")
    
    try:
        esistenti = sheet.get_all_records()

        for record in esistenti:
            # Pulizia chiavi del record (toglie spazi e rende maiuscolo)
            rec = {str(k).strip().upper(): v for k, v in record.items()}
            
            nome_es = str(rec.get('NOME', '')).strip().lower()
            
            if nome_es == nome_nuovo:
                # Se arriviamo qui, il nome è giusto. Ora controlliamo le date.
                raw_inizio = str(rec.get('DATA INIZIO', rec.get('INIZIO', '')))
                raw_fine = str(rec.get('DATA FINE', rec.get('FINE', '')))
                
                # Tentiamo la conversione supportando sia '-' che '/'
                try:
                    inizio_es = None
                    for fmt in ('%d-%m-%Y', '%d/%m/%Y'):
                        try:
                            inizio_es = datetime.strptime(raw_inizio, fmt).date()
                            fine_es = datetime.strptime(raw_fine, fmt).date()
                            break
                        except: continue
                    
                    if inizio_es and fine_es:
                        # CONTROLLO MATEMATICO OVERLAP
                        if inizio_nuovo <= fine_es and inizio_es <= fine_nuovo:
                            st.write("Gia ok")
                            return f"❌ {riga[0]} ha già ferie dal {raw_inizio} al {raw_fine}"
                except Exception as e:
                    st.write(f"DEBUG: Errore conversione date riga {nome_es}: {e}")
                    continue
                    
    except Exception as e:
        return f"⚠️ Errore critico: {e}"

    # --- SALVATAGGIO ---
    totale_giorni = calcola_giorni_lavorativi_esatti(inizio_nuovo, fine_nuovo)
    riga_da_salvare = [riga[0], inizio_nuovo.strftime('%d-%m-%Y'), fine_nuovo.strftime('%d-%m-%Y'), riga[3], totale_giorni]
    
    try:
        sheet.append_row(riga_da_salvare)
        return True
    except Exception as e:
        return f"🚨 Errore salvataggio: {e}"
