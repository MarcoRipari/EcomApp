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
  
  # --- 4. Calcolo (manteniamo la logica precedente) ---
  report['Giorni Residui'] = FERIE_TOTALI_ANNUE - report['GIORNI LAVORATIVI']
  
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
  nomi_dipendenti = report_view['Dipendente'].unique().tolist()
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
    giorni_presi = report_view.loc[report_view['Dipendente'] == dipendente_scelto, 'Giorni Goduti'].values[0]
    giorni_restanti = report_view.loc[report_view['Dipendente'] == dipendente_scelto, 'Residuo'].values[0]
      
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
        if upload:
          st.success("Ferie inserite con successo!")
        else:
          st.error(f"Errore tecnico: {upload}")
