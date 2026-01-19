import streamlit as st
import pandas as pd
import gspread

from utils import *

load_functions_from("functions", globals())

def ferie():
  FERIE_TOTALI_ANNUE = 34
  dipendenti = get_dipendenti()
  
  st.header("Ferie")

  # 1. Recupero i dati dal foglio
  # Utilizzo la tua funzione get_sheet (assicurati che restituisca l'oggetto worksheet)
  sheet = get_sheet(ferie_sheet_id, "FERIE")
  
  # 2. Trasformo i dati in un DataFrame Pandas per gestirli facilmente
  data = sheet.get_all_records()
  
  if not data:
    st.warning("Non ci sono dati registrati nel foglio ferie.")
    return

  df = pd.DataFrame(data)

  # Rinominiamo le colonne per sicurezza se i nomi nel foglio sono diversi
  # Assicurati che nel foglio i nomi siano esattamente "NOME" e "GIORNI LAVORATIVI"
  # Altrimenti usa df.columns = ['NOME', 'INIZIO', 'FINE', 'TIPO', 'GIORNI']
  
  # 3. Raggruppamento per Dipendente e Somma
  # Usiamo solo le righe di tipo "Ferie" se vuoi escludere Malattia/Permessi dal conteggio
  # df_ferie = df[df['TIPO'] == 'Ferie'] 
  # (Se vuoi sommare tutto, usa direttamente df)
  
  report = df.groupby('NOME')['GIORNI LAVORATIVI'].sum().reset_index()
  report = report.merge(dipendenti[['NOME', 'TOTALE']], on='NOME', how='left')
  report['TOTALE'] = pd.to_numeric(report['TOTALE'], errors='coerce')

  
  # --- 4. Calcolo (manteniamo la logica precedente) ---
  report['Giorni Residui'] = report['TOTALE'] - report['GIORNI LAVORATIVI']

  st.subheader("📅 In ferie questa settimana")
  
  # 1. Calcoliamo l'inizio (Lunedì) e la fine (Domenica) della settimana corrente
  oggi = datetime.now().date()
  inizio_settimana = oggi - timedelta(days=oggi.weekday())
  fine_settimana = inizio_settimana + timedelta(days=6)
  
  st.info(f"Settimana dal **{inizio_settimana.strftime('%d/%m')}** al **{fine_settimana.strftime('%d/%m')}**")

  # 2. Filtriamo i dati
  chi_e_in_ferie = []
  
  for _, riga in df.iterrows():
    # Convertiamo le stringhe del foglio in oggetti data
    try:
      inizio_f = datetime.strptime(riga['DATA INIZIO'], '%d-%m-%Y').date()
      fine_f = datetime.strptime(riga['DATA FINE'], '%d-%m-%Y').date()
          
      # Logica di sovrapposizione: 
      # (InizioFerie <= FineSettimana) AND (FineFerie >= InizioSettimana)
      if inizio_f <= fine_settimana and fine_f >= inizio_settimana:
        assente_oggi = inizio_f <= oggi <= fine_f
        chi_e_in_ferie.append({
          "Dipendente": riga['NOME'],
          "Dal": inizio_f.strftime('%d/%m'),
          "Al": fine_f.strftime('%d/%m'),
          "Tipo": riga['TIPO'],
          "Oggi": assente_oggi
        })
    except:
      continue

  # 3. Visualizzazione
  if chi_e_in_ferie:
    # Creiamo delle piccole "pillole" o una lista pulita
    cols = st.columns(len(chi_e_in_ferie) if len(chi_e_in_ferie) < 4 else 4)
    for i, assenza in enumerate(chi_e_in_ferie):
      with cols[i % 4]:
        if assenza['Oggi']:
          # Stile per chi è assente proprio ora (Rosso/Arancio)
          st.error(f"🔴 **{assenza['Dipendente']}**\n\nAssente oggi\n\n{assenza['Dal']} ➡️ {assenza['Al']}")
        else:
          # Stile per chi sarà assente più avanti nella settimana (Giallo)
          st.warning(f"🟡 **{assenza['Dipendente']}**\n\n{assenza['Dal']} ➡️ {assenza['Al']}")
  else:
    st.write("✅ Nessuno è in ferie questa settimana.")
  
  st.divider()

  st.subheader("📊 Riepilogo Disponibilità")
  
  # Creiamo una griglia di card (3 colonne per riga)
  cols = st.columns(3)
  
  # Cicliamo sulla lista anagrafica completa
  for i, nome_dipendente in enumerate(dipendenti['NOME'].tolist()):
      # Cerchiamo i dati del dipendente nel report calcolato precedentemente
      # Se il dipendente non ha ancora preso ferie, impostiamo i valori a zero
      dati_report = report[report['NOME'] == nome_dipendente]
      
      if not dati_report.empty:
          giorni_goduti = dati_report.iloc[0]['GIORNI LAVORATIVI']
          giorni_residui = dati_report.iloc[0]['Giorni Residui']
          giorni_totali = dati_report.iloc[0]['TOTALE']
      else:
          # Caso per dipendente che non ha ancora registrato ferie
          giorni_goduti = 0
          giorni_residui = dipendenti[dipendenti['NOME'] == nome_dipendente].iloc[0]['TOTALE']
          giorni_totali = dipendenti[dipendenti['NOME'] == nome_dipendente].iloc[0]['TOTALE']
  
      # Calcolo logica visuale
      percentuale = min(giorni_goduti / giorni_totali, 1.0)
      colore_testo = "red" if giorni_residui < 5 else "#31333F"
      
      with cols[i % 3]:
          # HTML Card
          st.markdown(f"""
              <div style="
                  border: 1px solid #e6e9ef; 
                  padding: 20px; 
                  border-radius: 10px; 
                  background-color: #f9f9f9;
                  margin-bottom: 10px;
                  height: 160px;
                  box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                  <h3 style="margin-top:0; color:#1E88E5; font-size: 18px;">{nome_dipendente}</h3>
                  <p style="margin-bottom:5px; font-size:14px; color: #555;">Godute: <b>{giorni_goduti} gg</b></p>
                  <p style="color:{colore_testo}; font-size:16px;">Residuo: <b>{giorni_residui} gg</b></p>
              </div>
          """, unsafe_allow_html=True)
          
          # Barra di progresso
          st.progress(percentuale)

  # 6. Widget per visualizzare il dettaglio di un singolo dipendente
  st.divider()
  report.columns = ['Dipendente', 'Giorni Goduti', 'Totale', 'Residuo']
  
  # Recuperiamo i nomi unici e aggiungiamo un'opzione vuota all'inizio
  #nomi_dipendenti = report['Dipendente'].unique().tolist()
  opzioni = ["-- Seleziona un dipendente --"] + dipendenti['NOME'].tolist()

  dipendente_scelto = st.selectbox(
    "Visualizza il dettaglio storico per:", 
    options=opzioni,
    index=0  # Forza la selezione sul primo elemento ("-- Seleziona...")
  )
  
  # Mostriamo il dettaglio solo se l'utente ha scelto un nome reale
  if dipendente_scelto != "-- Seleziona un dipendente --":
    dettaglio_utente = df[df['NOME'] == dipendente_scelto]
    st.subheader(f"Dettaglio assenze: {dipendente_scelto}")

    dettaglio_utente['DATA INIZIO'] = pd.to_datetime(dettaglio_utente['DATA INIZIO'], dayfirst=True, errors='coerce')
    dettaglio_utente['DATA FINE'] = pd.to_datetime(dettaglio_utente['DATA FINE'], dayfirst=True, errors='coerce')
    
    dettaglio_utente = dettaglio_utente.sort_values(by='DATA INIZIO', ascending=True)
    
    MESI_ITA = {
        1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
        7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
    }

    dettaglio_utente['DATA INIZIO'] = dettaglio_utente['DATA INIZIO'].apply(
        lambda x: f"{x.day} {MESI_ITA[x.month]} {x.year}" if pd.notnull(x) else ""
    )
    dettaglio_utente['DATA FINE'] = dettaglio_utente['DATA FINE'].apply(
        lambda x: f"{x.day} {MESI_ITA[x.month]} {x.year}" if pd.notnull(x) else ""
    )
    
    # Mostriamo la tabella con i dettagli delle singole richieste
    st.dataframe(
      dettaglio_utente[['DATA INIZIO', 'DATA FINE', 'TIPO', 'GIORNI LAVORATIVI']],
      use_container_width=True,
      hide_index=True
    )
    
    # Un piccolo riassunto grafico per l'utente selezionato
    giorni_presi = report.loc[report['Dipendente'] == dipendente_scelto, 'Giorni Goduti'].values[0]
    giorni_restanti = report.loc[report['Dipendente'] == dipendente_scelto, 'Residuo'].values[0]
    
    st.info(f"Riepilogo: {giorni_presi} giorni goduti, {giorni_restanti} ancora disponibili.")
  else:
    st.info("Seleziona un nome dal menu a tendina per vedere l'elenco dettagliato delle date.")

def aggiungi_ferie():
  st.header("Aggiungi ferie")

  with st.form("form_ferie", clear_on_submit=True):
    nome = st.text_input("Nome Dipendente")
    
    col1, col2 = st.columns(2)
    with col1:
        data_inizio = st.date_input("Data inizio", format="DD/MM/YYYY")
    with col2:
        data_fine = st.date_input("Data fine", format="DD/MM/YYYY")
        
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
        nuova_riga = [nome, data_inizio.strftime('%d-%m-%Y'), data_fine.strftime('%d-%m-%Y'), tipo]
        upload = add_ferie(nuova_riga)
        if upload is True:
          st.success("Ferie inserite con successo!")
        else:
          st.error(f"{upload}")

def gestione_dipendenti():
  st.header("Gestione dipendenti")
  dipendenti = get_dipendenti()

  cols = st.columns(3)
  
  # Cicliamo sulla lista anagrafica completa
  for i, dipendente in enumerate(dipendenti.itertuples(index=False)):
      with cols[i % 3]:
          # HTML Card
          st.markdown(f"""
              <div style="
                  border: 1px solid #e6e9ef; 
                  padding: 20px; 
                  border-radius: 10px; 
                  background-color: #f9f9f9;
                  margin-bottom: 10px;
                  height: 160px;
                  box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                  <h3 style="margin-top:0; color:#1E88E5; font-size: 18px;">{dipendente.NOME}</h3>
                  <p style="margin-bottom:5px; font-size:14px; color: #555;">Totale: <b>{dipendente.TOTALE} gg</b></p>
              </div>
          """, unsafe_allow_html=True)
  
