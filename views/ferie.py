import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta

from utils import *

load_functions_from("functions", globals())

def ferie():
    # 1. Recupero l'anagrafica che ha già i calcoli (NOME, TOTALE, FATTE, RESIDUO)
    df_dipendenti = get_dipendenti() 

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

        # Formattazione date
        dettaglio_utente['DATA INIZIO'] = pd.to_datetime(dettaglio_utente['DATA INIZIO'], dayfirst=True, errors='coerce')
        dettaglio_utente['DATA FINE'] = pd.to_datetime(dettaglio_utente['DATA FINE'], dayfirst=True, errors='coerce')

        # Filtri avanzati
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            anni = ["Tutti"] + sorted(dettaglio_utente['DATA INIZIO'].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
            anno_scelto = st.selectbox("Filtra per anno:", anni)
        with col_f2:
            tipi = ["Tutti"] + sorted(dettaglio_utente['TIPO'].unique().tolist())
            tipo_scelto = st.selectbox("Filtra per tipo:", tipi)

        dettaglio_completo = dettaglio_utente.sort_values(by='DATA INIZIO', ascending=False)

        if anno_scelto != "Tutti":
            dettaglio_utente = dettaglio_utente[dettaglio_utente['DATA INIZIO'].dt.year == anno_scelto]
        if tipo_scelto != "Tutti":
            dettaglio_utente = dettaglio_utente[dettaglio_utente['TIPO'] == tipo_scelto]

        dettaglio_utente = dettaglio_utente.sort_values(by='DATA INIZIO', ascending=False)

        MESI_ITA = {1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
                    7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"}

        # Prepariamo i dati per l'editor (usiamo le date originali per facilità di editing)
        df_editor = dettaglio_utente[['NOME', 'DATA INIZIO', 'DATA FINE', 'TIPO', 'GIORNI LAVORATIVI']].copy()
        df_editor['DATA INIZIO'] = df_editor['DATA INIZIO'].dt.date
        df_editor['DATA FINE'] = df_editor['DATA FINE'].dt.date

        edited_df = st.data_editor(
            df_editor,
            column_config={
                "NOME": st.column_config.TextColumn("DIPENDENTE", disabled=True),
                "DATA INIZIO": st.column_config.DateColumn("INIZIO", format="DD/MM/YYYY", required=True),
                "DATA FINE": st.column_config.DateColumn("FINE", format="DD/MM/YYYY", required=True),
                "TIPO": st.column_config.SelectboxColumn("TIPO", options=["Ferie", "Malattia", "Permesso", "Altro"], required=True),
                "GIORNI LAVORATIVI": st.column_config.NumberColumn("GG", disabled=True),
            },
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"editor_{dipendente_scelto}"
        )

        col_s1, col_s2 = st.columns([1, 1])
        with col_s1:
            if st.button("Salva modifiche storiche", use_container_width=True):
                with st.spinner("Sincronizzazione con GSheet..."):
                    # Se i filtri sono attivi, dobbiamo unire i dati modificati con quelli non visibili
                    if anno_scelto != "Tutti" or tipo_scelto != "Tutti":
                        # Identifica le righe originali NON incluse nel filtro
                        mask = (dettaglio_completo['DATA INIZIO'].dt.year == anno_scelto) if anno_scelto != "Tutti" else True
                        if tipo_scelto != "Tutti":
                            mask &= (dettaglio_completo['TIPO'] == tipo_scelto)

                        df_non_visibili = dettaglio_completo[~mask].copy()
                        df_final_sync = pd.concat([df_non_visibili, edited_df], ignore_index=True)
                    else:
                        df_final_sync = edited_df

                    if sync_ferie_changes(dipendente_scelto, df_final_sync):
                            st.success("Modifiche salvate!")
                            st.rerun()
        with col_s2:
            # Esportazione CSV
            csv_data = edited_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Esporta report (CSV)",
                data=csv_data,
                file_name=f"report_ferie_{dipendente_scelto}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
                use_container_width=True
            )

        # Riepilogo professionale usando i dati dell'anagrafica
        info_dip = df_dipendenti[df_dipendenti['NOME'] == dipendente_scelto].iloc[0]

        st.markdown(f"""
            <div style="background-color: #f0f7ff; border-left: 5px solid #1E88E5; padding: 15px; border-radius: 5px; margin-top: 20px;">
                <h4 style="margin-top: 0; color: #1E88E5;">📋 Riepilogo {dipendente_scelto}</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 5px 0;"><b>Giorni Totali Annui:</b></td>
                        <td style="text-align: right;">{info_dip.TOTALE:g} gg</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 0;"><b>Giorni Goduti:</b></td>
                        <td style="text-align: right;">{info_dip.FATTE:g} gg</td>
                    </tr>
                    <tr style="border-top: 1px solid #ccc;">
                        <td style="padding: 10px 0;"><b><span style="color: #d32f2f;">Residuo Attuale:</span></b></td>
                        <td style="text-align: right; font-size: 1.2em; color: #d32f2f;"><b>{info_dip.RESIDUO:g} gg</b></td>
                    </tr>
                </table>
            </div>
        """, unsafe_allow_html=True)

def aggiungi_ferie():
  st.header("Aggiungi ferie")

  dipendenti = get_dipendenti()
  nomi_dipendenti = dipendenti['NOME'].tolist()

  nome = st.selectbox("Nome Dipendente", options=nomi_dipendenti)

  col1, col2 = st.columns(2)
  with col1:
      data_inizio = st.date_input("Data inizio", format="DD/MM/YYYY")
  with col2:
      data_fine = st.date_input("Data fine", format="DD/MM/YYYY")

  if data_inizio <= data_fine:
      sovrapposizioni = check_overlaps(data_inizio, data_fine, escludi_nome=nome)
      if sovrapposizioni:
          st.warning(f"⚠️ **Attenzione:** Nelle date selezionate sono già in ferie: {', '.join(sovrapposizioni)}")

  tipo = st.selectbox("Tipo di assenza", ["Ferie", "Malattia", "Permesso", "Altro"])

  if st.button("Inserisci ferie"):
    
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
        st.rerun()
      else:
        st.error(f"{upload}")

@st.dialog("Modifica Budget Dipendente")
def modifica_ferie_totali_modal(nome, ferie_attuale):
    st.write(f"Modifica i giorni totali per: **{nome}**")
    nuovo_budget = st.number_input("Giorni totali annui", value=int(ferie_attuale), min_value=0)
    
    if st.button("Salva Modifiche"):
        if update_dipendente_budget(nome, nuovo_budget):
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
