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
  report.columns = ['Dipendente', 'Giorni Goduti', 'Budget Iniziale', 'Residuo']

  # 5. Visualizzazione Grafica
  st.subheader("Situazione Attuale")
  
  # Formattazione per rendere la tabella più bella
  st.dataframe(
    report.style.apply(lambda x: ['color: red' if x.Residuo < 30 else '' for i in x], axis=1),
    use_container_width=True,
    hide_index=True
  )

  # 6. Widget per visualizzare il dettaglio di un singolo dipendente
  st.divider()
  dipendente_scelto = st.selectbox("Seleziona un dipendente per vedere il dettaglio:", report['Dipendente'].unique())
  
  dettaglio_utente = df[df['NOME'] == dipendente_scelto]
  st.write(f"Dettaglio assenze per **{dipendente_scelto}**:")
  st.table(dettaglio_utente[['DATA INIZIO', 'DATA FINE', 'TIPO', 'GIORNI LAVORATIVI']])

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
