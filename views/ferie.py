import streamlit as st
import pandas as pd
import gspread

from utils import *

load_functions_from("functions", globals())

def ferie():
    # 1. Recupero l'anagrafica che ha già i calcoli (NOME, TOTALE, FATTE, RESIDUO)
    df_dipendenti = get_dipendenti() 
    
    st.header("Ferie")

    # 2. Recupero i dati grezzi delle ferie solo per la sezione "In ferie questa settimana" e il "Dettaglio"
    sheet = get_sheet(ferie_sheet_id, "FERIE")
    data_ferie = sheet.get_all_records()
    df_storico = pd.DataFrame(data_ferie) if data_ferie else pd.DataFrame()

    # --- SEZIONE 1: CHI È IN FERIE QUESTA SETTIMANA ---
    st.subheader("📅 In ferie questa settimana")
    oggi = datetime.now().date()
    inizio_settimana = oggi - timedelta(days=oggi.weekday())
    fine_settimana = inizio_settimana + timedelta(days=6)
    st.info(f"Settimana dal **{inizio_settimana.strftime('%d/%m')}** al **{fine_settimana.strftime('%d/%m')}**")

    chi_e_in_ferie = []
    if not df_storico.empty:
        for _, riga in df_storico.iterrows():
            try:
                inizio_f = datetime.strptime(riga['DATA INIZIO'], '%d-%m-%Y').date()
                fine_f = datetime.strptime(riga['DATA FINE'], '%d-%m-%Y').date()
                if inizio_f <= fine_settimana and fine_f >= inizio_settimana:
                    assente_oggi = inizio_f <= oggi <= fine_f
                    chi_e_in_ferie.append({
                        "Dipendente": riga['NOME'],
                        "Dal": inizio_f.strftime('%d/%m'),
                        "Al": fine_f.strftime('%d/%m'),
                        "Oggi": assente_oggi
                    })
            except: continue

    if chi_e_in_ferie:
        cols_sett = st.columns(len(chi_e_in_ferie) if len(chi_e_in_ferie) < 4 else 4)
        for i, assenza in enumerate(chi_e_in_ferie):
            with cols_sett[i % 4]:
                if assenza['Oggi']:
                    st.error(f"🔴 **{assenza['Dipendente']}**\n\nAssente oggi\n\n{assenza['Dal']} ➡️ {assenza['Al']}")
                else:
                    st.warning(f"🟡 **{assenza['Dipendente']}**\n\n{assenza['Dal']} ➡️ {assenza['Al']}")
    else:
        st.write("✅ Nessuno è in ferie questa settimana.")

    st.divider()

    # --- SEZIONE 2: RIEPILOGO DISPONIBILITÀ (Utilizzando i dati già pronti) ---
    st.subheader("📊 Riepilogo Disponibilità")
    cols = st.columns(3)

    # Usiamo itertuples per scorrere i dati pronti dal foglio Dipendenti
    for i, dip in enumerate(df_dipendenti.itertuples(index=False)):
        # Recuperiamo i valori dalle colonne esistenti
        fatte = float(dip.FATTE)
        totale = float(dip.TOTALE)
        residuo = float(dip.RESIDUO)
        
        percentuale = min(fatte / totale, 1.0) if totale > 0 else 0
        colore_residuo = "red" if residuo < 5 else "#31333F"

        with cols[i % 3]:
            st.markdown(f"""
                <div style="border: 1px solid #e6e9ef; padding: 20px; border-radius: 10px; background-color: #f9f9f9; height: 150px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                    <h3 style="margin-top:0; color:#1E88E5; font-size: 18px;">{dip.NOME}</h3>
                    <p style="margin-bottom:5px; font-size:14px; color: #555;">Godute: <b>{int(fatte)} gg</b> / {int(totale)}</p>
                    <p style="color:{colore_residuo}; font-size:16px;">Residuo: <b>{int(residuo)} gg</b></p>
                </div>
            """, unsafe_allow_html=True)
            st.progress(percentuale)

    # --- SEZIONE 3: DETTAGLIO STORICO ---
    st.divider()
    opzioni = ["-- Seleziona un dipendente --"] + df_dipendenti['NOME'].tolist()
    dipendente_scelto = st.selectbox("Visualizza il dettaglio storico per:", options=opzioni)

    if dipendente_scelto != "-- Seleziona un dipendente --" and not df_storico.empty:
        dettaglio_utente = df_storico[df_storico['NOME'] == dipendente_scelto].copy()
        st.subheader(f"Dettaglio assenze: {dipendente_scelto}")

        # Formattazione date per tabella
        dettaglio_utente['DATA INIZIO'] = pd.to_datetime(dettaglio_utente['DATA INIZIO'], dayfirst=True, errors='coerce')
        dettaglio_utente['DATA FINE'] = pd.to_datetime(dettaglio_utente['DATA FINE'], dayfirst=True, errors='coerce')
        dettaglio_utente = dettaglio_utente.sort_values(by='DATA INIZIO', ascending=False)

        MESI_ITA = {1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
                    7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"}

        dettaglio_utente['DATA INIZIO_STR'] = dettaglio_utente['DATA INIZIO'].apply(lambda x: f"{x.day} {MESI_ITA[x.month]} {x.year}" if pd.notnull(x) else "")
        dettaglio_utente['DATA FINE_STR'] = dettaglio_utente['DATA FINE'].apply(lambda x: f"{x.day} {MESI_ITA[x.month]} {x.year}" if pd.notnull(x) else "")

        st.dataframe(
            dettaglio_utente[['DATA INIZIO_STR', 'DATA FINE_STR', 'TIPO', 'GIORNI LAVORATIVI']],
            column_config={
                "DATA INIZIO_STR": "INIZIO",
                "DATA FINE_STR": "FINE",
            },
            use_container_width=True,
            hide_index=True
        )

        # Riepilogo veloce usando i dati dell'anagrafica
        info_dip = df_dipendenti[df_dipendenti['NOME'] == dipendente_scelto].iloc[0]
        st.info(f"Riepilogo {dipendente_scelto}: {info_dip.FATTE} giorni goduti, {info_dip.RESIDUO} residui su {info_dip.TOTALE} totali.")

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

@st.dialog("Modifica Budget Dipendente")
def modifica_ferie_totali_modal(nome, ferie_attuale):
    st.write(f"Modifica i giorni totali per: **{nome}**")
    nuovo_budget = st.number_input("Giorni totali annui", value=int(ferie_attuale), min_value=0)
    
    if st.button("Salva Modifiche"):
        # Qui chiamerai la funzione per aggiornare Google Sheets
        # update_budget_on_gsheet(nome, nuovo_budget)
        st.success(f"Ferie totali aggiornate per {nome}!")
        st.rerun() # Ricarica l'app per vedere i nuovi dati
      
def gestione_dipendenti():
  st.header("Gestione dipendenti")
  dipendenti = get_dipendenti()

  cols = st.columns(3)
  
  # Cicliamo sulla lista anagrafica completa
  for i, dipendente in enumerate(dipendenti.itertuples(index=False)):
        with cols[i % 3]:
            # Visualizzazione Card
            st.markdown(f"""
                <div style="
                    border: 1px solid #e6e9ef; 
                    padding: 20px; 
                    border-radius: 10px; 
                    background-color: #f9f9f9;
                    margin-bottom: 5px;
                    height: 120px;
                    box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                    <h3 style="margin-top:0; color:#1E88E5; font-size: 18px;">{dipendente.NOME}</h3>
                    <p style="margin-bottom:5px; font-size:14px; color: #555;">Totale: <b>{dipendente.TOTALE} gg</b></p>
                </div>
            """, unsafe_allow_html=True)
            
            # Pulsante Modifica con icona
            # Usiamo una chiave unica (key) basata sul nome per distinguere i bottoni
            if st.button(f"📝 Modifica {dipendente.NOME}", key=f"edit_{dipendente.NOME}", use_container_width=True):
                modifica_ferie_totali_modal(dipendente.NOME, dipendente.TOTALE)
