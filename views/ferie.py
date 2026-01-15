import streamlit as st
import pandas as pd
import gspread

from utils import *

load_functions_from("functions", globals())

def ferie():
  FERIE_TOTALI_ANNUE = 33
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

  
  # --- 4. Calcolo (manteniamo la logica precedente) ---
  report['Giorni Residui'] = FERIE_TOTALI_ANNUE - report['GIORNI LAVORATIVI']

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
  
  for i, row in report.iterrows():
      # Selezioniamo la colonna della griglia (cicla tra 0, 1, 2)
      with cols[i % 3]:
          # Calcolo percentuale per la barra di progresso
          percentuale = min(row['GIORNI LAVORATIVI'] / FERIE_TOTALI_ANNUE, 1.0)
          
          # Colore dinamico in base al residuo
          colore_testo = "red" if row['Giorni Residui'] < 5 else "gray"
          
          # HTML/Markdown per creare una card personalizzata
          st.markdown(f"""
              <div style="
                  border: 1px solid #e6e9ef; 
                  padding: 20px; 
                  border-radius: 10px; 
                  background-color: #f9f9f9;
                  margin-bottom: 10px;
                  height: 180px">
                  <h3 style="margin-top:0; color:#31333F;">{row['NOME']}</h3>
                  <p style="margin-bottom:5px; font-size:14px;">Ferie Godute: <b>{row['GIORNI LAVORATIVI']}</b></p>
                  <p style="color:{colore_testo}; font-size:14px;">Residuo: <b>{row['Giorni Residui']} gg</b></p>
              </div>
          """, unsafe_allow_html=True)
          
          # Aggiungiamo una barra di progresso sotto ogni card per un feedback visivo immediato
          st.progress(percentuale)

  # 6. Widget per visualizzare il dettaglio di un singolo dipendente
  st.divider()
  report.columns = ['Dipendente', 'Giorni Goduti', 'Residuo']
  
  # Recuperiamo i nomi unici e aggiungiamo un'opzione vuota all'inizio
  #nomi_dipendenti = report['Dipendente'].unique().tolist()
  opzioni = ["-- Seleziona un dipendente --"] + nomi_dipendenti

  dipendente_scelto = st.selectbox(
    "Visualizza il dettaglio storico per:", 
    options=opzioni,
    index=0  # Forza la selezione sul primo elemento ("-- Seleziona...")
  )
  
  # Mostriamo il dettaglio solo se l'utente ha scelto un nome reale
  if dipendente_scelto != "-- Seleziona un dipendente --":
    dettaglio_utente = df[df['NOME'] == dipendente_scelto]
    st.subheader(f"Dettaglio assenze: {dipendente_scelto}")
    
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
