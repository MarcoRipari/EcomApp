import streamlit as st
import pandas as pd
import gspread

from utils import *

load_functions_from("functions", globals())

def ferie():
  FERIE_TOTALI_ANNUE = 30
  
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
  
  # 4. Calcolo dei giorni residui
  report['Ferie Totali'] = FERIE_TOTALI_ANNUE
  report['Giorni Residui'] = report['Ferie Totali'] - report['GIORNI LAVORATIVI']

  report_view = report[['NOME', 'GIORNI LAVORATIVI', 'Giorni Residui']].copy()
  report_view.columns = ['Dipendente', 'Giorni Goduti', 'Residuo']

  # 5. Visualizzazione Grafica
  st.subheader("Situazione Attuale")
  
  # Formattazione per rendere la tabella più bella
  st.dataframe(
    report_view.style.apply(lambda x: ['color: red' if x.Residuo < 5 else '' for i in x], axis=1),
    use_container_width=True,
    hide_index=True
  )

  # 6. Widget per visualizzare il dettaglio di un singolo dipendente
  st.divider()
  
  # Recuperiamo i nomi unici e aggiungiamo un'opzione vuota all'inizio
  nomi_dipendenti = report['Dipendente'].unique().tolist()
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
      
    st.info(f"Riepilogo rapido: {giorni_presi} giorni goduti, {giorni_restanti} ancora disponibili.")
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
        if upload:
          st.success("Ferie inserite con successo!")
        else:
          st.error(f"Errore tecnico: {upload}")
