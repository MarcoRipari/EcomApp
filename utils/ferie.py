import streamlit as st
import gspread
import holidays
from datetime import datetime, timedelta

from utils import *

load_functions_from("functions", globals())

ferie_sheet_id = st.secrets["FERIE_GSHEET_ID"]

def dettaglio_dipendente(nome):
  lista = get_dipendenti()
  dettaglio = lista[lista['NOME'] == nome]
  dettaglio['TOTALE'] = pd.to_numeric(dettaglio['TOTALE'], errors='coerce')
  return dettaglio

# 🔧 FIX: nessuna di queste letture era cachata. La pagina "Report" da sola fa
# 6 chiamate a Google Sheets (get_dipendenti + lettura FERIE, ciascuna = get_sheet
# + get_all_records) ad OGNI rerun -- cioè ad ogni interazione con qualunque widget
# della pagina (cambio filtro, modifica riga, selezione dipendente). "Aggiungi ferie"
# rilegge i dipendenti e rifà check_overlaps ad ogni data selezionata. Con più
# utenti che usano contemporaneamente la sezione, la quota "richieste/minuto" di
# Google Sheets si esaurisce facilmente -> 429. Cachiamo le letture con un TTL
# breve (i dati restano freschi comunque entro 30s) e invalidiamo esplicitamente
# la cache subito dopo ogni scrittura, cosicché chi salva vede subito il risultato
# aggiornato mentre chi sta solo guardando non genera letture inutili.
@st.cache_data(ttl=30, show_spinner=False)
def get_dipendenti():
  sheet = get_sheet(ferie_sheet_id, "DIPENDENTI")
  dipendenti = pd.DataFrame(sheet.get_all_records())
  dipendenti = dipendenti.sort_values(by='NOME', ascending=True)
  return dipendenti

@st.cache_data(ttl=30, show_spinner=False)
def get_ferie_storico():
  sheet = get_sheet(ferie_sheet_id, "FERIE")
  data = sheet.get_all_records()
  return pd.DataFrame(data) if data else pd.DataFrame()

def update_dipendente_budget(nome, nuovo_budget):
    sheet = get_sheet(ferie_sheet_id, "DIPENDENTI")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    # Trova la riga corrispondente
    try:
        idx = df[df['NOME'] == nome].index[0]
        # In Google Sheets le righe iniziano da 1 e la riga 1 è l'intestazione
        row_to_update = idx + 2
        # Trova la colonna 'TOTALE'
        col_idx = df.columns.get_loc('TOTALE') + 1
        sheet.update_cell(row_to_update, col_idx, nuovo_budget)
        get_dipendenti.clear()  # 🔧 la cache va invalidata subito, altrimenti il rerun mostrerebbe ancora il valore vecchio
        return True
    except Exception as e:
        st.error(f"Errore durante l'aggiornamento: {e}")
        return False
  
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
        esistenti = get_ferie_storico().to_dict("records")  # 🔧 riusa la lettura cachata invece di un'altra chiamata a Sheets

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
        get_ferie_storico.clear()  # 🔧 invalida la cache: la nuova riga deve essere visibile subito
        return True
    except Exception as e:
        return f"🚨 Errore salvataggio: {e}"

def sync_ferie_changes(nome_dipendente, edited_df):
    """
    Sincronizza le modifiche dello storico ferie con Google Sheets.
    Ricalcola i giorni lavorativi per ogni riga modificata.
    """
    sheet = get_sheet(ferie_sheet_id, "FERIE")
    try:
        # 1. Recupera tutti i dati attuali
        all_data = get_ferie_storico()

        # 2. Rimuove tutte le righe del dipendente corrente dal dataframe globale
        df_others = all_data[all_data['NOME'] != nome_dipendente].copy()

        # 🔧 FIX: se l'utente elimina tutte le righe rimaste per questo dipendente,
        # edited_df arriva vuoto (0 righe). Su un DataFrame vuoto, operazioni
        # riga-per-riga come .apply(axis=1) possono restituire una forma che
        # pandas non riesce ad assegnare correttamente a una singola colonna,
        # causando "Columns must be same length as key". Gestiamo il caso
        # esplicitamente: se non ci sono righe da salvare, saltiamo il ricalcolo
        # e scriviamo solo gli altri dipendenti (equivale a svuotare lo storico
        # di questa persona, che è esattamente quello che l'utente ha chiesto).
        if edited_df.empty:
            final_df = df_others
        else:
            # 3. Prepara le nuove righe del dipendente ricalcolando i giorni lavorativi
            new_rows = edited_df.copy()
            # Guardia difensiva: forziamo comunque NOME sul dipendente selezionato,
            # nel caso l'editor permetta righe con NOME vuoto.
            new_rows['NOME'] = nome_dipendente
            new_rows['GIORNI LAVORATIVI'] = new_rows.apply(
                lambda r: calcola_giorni_lavorativi_esatti(
                    pd.to_datetime(r['DATA INIZIO']).date() if not isinstance(r['DATA INIZIO'], datetime) else r['DATA INIZIO'],
                    pd.to_datetime(r['DATA FINE']).date() if not isinstance(r['DATA FINE'], datetime) else r['DATA FINE']
                ),
                axis=1
            )

            # Formattazione date per GSheet
            new_rows['DATA INIZIO'] = pd.to_datetime(new_rows['DATA INIZIO']).dt.strftime('%d-%m-%Y')
            new_rows['DATA FINE'] = pd.to_datetime(new_rows['DATA FINE']).dt.strftime('%d-%m-%Y')

            # 4. Unisce i dati
            final_df = pd.concat([df_others, new_rows], ignore_index=True)

        # Pulizia intestazioni e caricamento
        sheet.clear()
        sheet.update("A1", [final_df.columns.tolist()] + final_df.fillna("").values.tolist())
        get_ferie_storico.clear()  # 🔧 invalida la cache: il foglio è stato riscritto, la vecchia versione non è più valida
        return True
    except Exception as e:
        st.error(f"Errore sincronizzazione: {e}")
        return False

def check_overlaps(inizio_nuovo, fine_nuovo, escludi_nome=None):
    """
    Controlla se ci sono altre persone in ferie nelle date selezionate.
    Ritorna una lista di nomi che si sovrappongono.
    """
    try:
        df = get_ferie_storico()  # 🔧 riusa la lettura cachata: veniva chiamato ad ogni singola data selezionata nell'UI
        if df.empty:
            return []

        overlaps = []
        for _, row in df.iterrows():
            nome = row.get('NOME')
            if escludi_nome and nome == escludi_nome:
                continue

            try:
                # 🔧 stesso fix: accetta sia 'gg-mm-aaaa' che 'gg/mm/aaaa', come add_ferie
                inizio_es = pd.to_datetime(row.get('DATA INIZIO'), dayfirst=True, errors='raise').date()
                fine_es = pd.to_datetime(row.get('DATA FINE'), dayfirst=True, errors='raise').date()

                if inizio_nuovo <= fine_es and inizio_es <= fine_nuovo:
                    overlaps.append(nome)
            except:
                continue

        return list(set(overlaps))
    except Exception as e:
        st.error(f"Errore controllo sovrapposizioni: {e}")
        return []


# --- NUOVA FUNZIONE DIALOG PER MODIFICA BUDGET ---
@st.dialog("Modifica Budget Ferie")
def edit_budget_dialog(nome, budget_attuale):
    st.write(f"Stai modificando il budget annuo per **{nome}**")
    nuovo_budget = st.number_input("Nuovo Totale Giorni", value=int(budget_attuale), min_value=0)
    
    if st.button("Salva"):
        if update_dipendente_budget(nome, nuovo_budget):
            st.success(f"Budget per {nome} aggiornato a {nuovo_budget}!")
            st.rerun()
