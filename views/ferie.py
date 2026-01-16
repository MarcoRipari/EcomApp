import streamlit as st
import pandas as pd
import gspread

from utils import *

load_functions_from("functions", globals())
      
def ferie():
      # 1. Recupero Anagrafica (con i budget personalizzati)
      df_anagrafica = get_dipendenti() # Assumiamo sia un DataFrame con colonne NOME e TOTALE
    
      st.header("Ferie")

      # 2. Recupero Dati Ferie effettive
      sheet = get_sheet(ferie_sheet_id, "FERIE")
      data = sheet.get_all_records()
      if not data:
            st.warning("Non ci sono dati registrati nel foglio ferie.")
            df = pd.DataFrame(columns=['NOME', 'GIORNI LAVORATIVI', 'DATA INIZIO', 'DATA FINE', 'TIPO'])
      else:
            df = pd.DataFrame(data)

      # 3. Calcolo giorni goduti per dipendente
      report_godute = df.groupby('NOME')['GIORNI LAVORATIVI'].sum().reset_index()

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
    
      cols = st.columns(3)
    
      # Cicliamo sul DataFrame ANAGRAFICA per avere i budget corretti
      for i, riga_dip in df_anagrafica.iterrows():
            nome_dip = riga_dip['NOME']
            budget_personale = riga_dip['TOTALE'] # Prende il valore dal foglio Dipendenti

            # Cerchiamo quanto ha fatto nel foglio ferie
            dato_fatte = report_godute[report_godute['NOME'] == nome_dip]
            giorni_goduti = dato_fatte.iloc[0]['GIORNI LAVORATIVI'] if not dato_fatte.empty else 0
        
            giorni_residui = budget_personale - giorni_goduti
            percentuale = min(giorni_goduti / budget_personale, 1.0) if budget_personale > 0 else 0
            colore_testo = "red" if giorni_residui < 5 else "#31333F"
        
            with cols[i % 3]:
                  # Card con HTML
                  st.markdown(f"""
                        <div style="border: 1px solid #e6e9ef; padding: 20px; border-radius: 10px; 
                              background-color: #f9f9f9; height: 160px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                        <h3 style="margin:0; color:#1E88E5; font-size: 18px;">{nome_dip}</h3>
                        <p style="margin:5px 0; font-size:14px;">Budget: <b>{budget_personale} gg</b></p>
                        <p style="margin:5px 0; font-size:14px;">Godute: <b>{giorni_goduti} gg</b></p>
                        <p style="color:{colore_testo}; font-size:16px; margin:0;">Residuo: <b>{giorni_residui} gg</b></p>
                        </div>
                  """, unsafe_allow_html=True)
            
            st.progress(percentuale)
            
            # Pulsante per aprire il popup (Dialog)
            if st.button(f"Modifica Budget {nome_dip}", key=f"btn_{nome_dip}"):
                edit_budget_dialog(nome_dip, budget_personale)

      # 6. Widget per visualizzare il dettaglio di un singolo dipendente
      st.divider()
      report.columns = ['Dipendente', 'Giorni Goduti', 'Residuo']
  
      # Recuperiamo i nomi unici e aggiungiamo un'opzione vuota all'inizio
      #nomi_dipendenti = report['Dipendente'].unique().tolist()
      opzioni = ["-- Seleziona un dipendente --"] + dipendenti

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
  dipendenti = get_dipendenti()['NOME'].tolist()
  
  
