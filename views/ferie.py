import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta

from utils import *

load_functions_from("functions", globals())

def calendario_ferie_mensile():
    st.subheader("🗓️ Calendario Ferie")

    oggi = datetime.now().date()
    if "cal_ferie_anno" not in st.session_state:
        st.session_state.cal_ferie_anno = oggi.year
        st.session_state.cal_ferie_mese = oggi.month

    col_prev, col_titolo, col_oggi, col_next = st.columns([1, 4, 1, 1])
    with col_prev:
        if st.button("◀", use_container_width=True, key="cal_ferie_prev"):
            m = st.session_state.cal_ferie_mese - 1
            a = st.session_state.cal_ferie_anno
            if m < 1:
                m = 12
                a -= 1
            st.session_state.cal_ferie_mese = m
            st.session_state.cal_ferie_anno = a
            st.rerun()
    with col_titolo:
        titolo = f"{MESI_IT_LUNGO[st.session_state.cal_ferie_mese - 1]} {st.session_state.cal_ferie_anno}"
        st.markdown(f"<h3 style='text-align:center; margin:4px 0;'>{titolo}</h3>", unsafe_allow_html=True)
    with col_oggi:
        if st.button("Oggi", use_container_width=True, key="cal_ferie_oggi"):
            st.session_state.cal_ferie_anno = oggi.year
            st.session_state.cal_ferie_mese = oggi.month
            st.rerun()
    with col_next:
        if st.button("▶", use_container_width=True, key="cal_ferie_next"):
            m = st.session_state.cal_ferie_mese + 1
            a = st.session_state.cal_ferie_anno
            if m > 12:
                m = 1
                a += 1
            st.session_state.cal_ferie_mese = m
            st.session_state.cal_ferie_anno = a
            st.rerun()

    df_storico = get_ferie_storico()
    df_dipendenti = get_dipendenti()
    html = build_calendario_mensile_html(df_storico, st.session_state.cal_ferie_anno, st.session_state.cal_ferie_mese, df_dipendenti)
    st.markdown(html, unsafe_allow_html=True)

def ferie():
    # 1. Recupero l'anagrafica che ha già i calcoli (NOME, TOTALE, FATTE, RESIDUO)
    df_dipendenti = get_dipendenti() 

    # 2. Recupero i dati grezzi delle ferie solo per la sezione "In ferie questa settimana" e il "Dettaglio"
    df_storico = get_ferie_storico()  # 🔧 ora cachata: prima veniva riletta ad ogni interazione sulla pagina

    # --- SEZIONE 1: CALENDARIO FERIE (questa settimana + prossima) ---
    st.subheader("📅 Chi è in ferie")
    st.markdown(build_calendario_ferie_html(df_storico, df_dipendenti), unsafe_allow_html=True)

    st.divider()

    # --- SEZIONE 2: RIEPILOGO DISPONIBILITÀ (anno corrente, con riporto residuo anno precedente) ---
    st.subheader("📊 Riepilogo Disponibilità")
    st.caption(f"Anno {datetime.now().year} — include il riporto del residuo (positivo o negativo) dell'anno precedente")
    cols = st.columns(3)

    anno_corrente = datetime.now().year
    for i, dip in enumerate(df_dipendenti.itertuples(index=False)):
        riepilogo = calcola_riepilogo_ferie_annuale(df_storico, dip.NOME, dip.TOTALE)
        dati_anno = riepilogo[anno_corrente]
        usati = dati_anno["usati"]
        disponibili = dati_anno["disponibili"]
        residuo = dati_anno["residuo"]

        # 🔧 Il residuo ora può includere il riporto dell'anno precedente e può
        # andare in negativo (dipendente che ha usato più ferie di quante ne
        # avesse a disposizione, es. per permessi orari). La barra di progresso
        # non può visualizzare valori negativi, quindi la blocchiamo a 0 e
        # mostriamo il colore rosso + il numero negativo reale nel testo.
        percentuale = min(usati / disponibili, 1.0) if disponibili > 0 else 1.0
        percentuale = max(percentuale, 0.0)
        colore_residuo = "red" if residuo < 5 else "#31333F"
        # 🔧 st.progress() non permette di personalizzare il colore (resta sempre
        # blu, fisso al tema). Usiamo una barra HTML su misura per poterla
        # colorare di rosso quando il residuo va in negativo.
        colore_barra = "#d32f2f" if residuo < 0 else "#1E88E5"

        with cols[i % 3]:
            st.markdown(f"""
                <div style="border: 1px solid #e6e9ef; padding: 20px; border-radius: 10px; background-color: #f9f9f9; height: 150px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                    <h3 style="margin-top:0; color:#1E88E5; font-size: 18px;">{dip.NOME}</h3>
                    <p style="margin-bottom:5px; font-size:14px; color: #555;">Godute: <b>{formatta_giorni_ore(usati)}</b> / {formatta_giorni_ore(disponibili)} disponibili</p>
                    <p style="color:{colore_residuo}; margin-bottom:8px; font-size:16px;">Residuo: <b>{formatta_giorni_ore(residuo)}</b></p>
                    <div style="background:#e6e9ef; border-radius:6px; height:10px; width:100%; overflow:hidden;">
                        <div style="background:{colore_barra}; height:100%; width:{percentuale*100}%; border-radius:6px;"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

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
            # 🔧 FIX: righe storiche con TIPO vuoto (NaN) facevano crashare sorted()
            # mescolando stringhe e float nel confronto. Le escludiamo dalla lista
            # delle opzioni del filtro (restano comunque visibili in tabella).
            tipi_validi = dettaglio_utente['TIPO'].dropna()
            tipi = ["Tutti"] + sorted(tipi_validi.unique().tolist())
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
            # 🔧 Corretto: "fixed" toglieva anche la possibilità di ELIMINARE una riga
            # (non solo di aggiungerne), che invece serve. Torniamo a "dynamic": il
            # rischio di riga orfana con NOME vuoto è già risolto a monte in
            # sync_ferie_changes, che forza NOME = dipendente_scelto su ogni riga
            # salvata, indipendentemente da cosa arriva dall'editor.
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

        # Riepilogo professionale usando il nuovo calcolo annuale con riporto
        info_dip = df_dipendenti[df_dipendenti['NOME'] == dipendente_scelto].iloc[0]
        riepilogo_anni = calcola_riepilogo_ferie_annuale(df_storico, dipendente_scelto, info_dip.TOTALE)
        anno_corrente = datetime.now().year
        dati_anno_corrente = riepilogo_anni[anno_corrente]

        # --- Recap veloce anni precedenti (solo un riassunto, niente dettaglio riga per riga) ---
        anni_precedenti = sorted([a for a in riepilogo_anni if a < anno_corrente], reverse=True)
        if anni_precedenti:
            with st.expander("📜 Storico anni precedenti"):
                for anno_prec in anni_precedenti:
                    dati = riepilogo_anni[anno_prec]
                    colore = "red" if dati["residuo"] < 0 else "#555"
                    st.markdown(
                        f"**{anno_prec}**: Usati {formatta_giorni_ore(dati['usati'])} &nbsp;|&nbsp; "
                        f"Residuo fine anno: <span style='color:{colore};'>{formatta_giorni_ore(dati['residuo'])}</span>",
                        unsafe_allow_html=True
                    )

        colore_residuo_card = "#d32f2f" if dati_anno_corrente["residuo"] < 0 else "#1E88E5"
        st.markdown(f"""
            <div style="background-color: #f0f7ff; border-left: 5px solid #1E88E5; padding: 15px; border-radius: 5px; margin-top: 20px;">
                <h4 style="margin-top: 0; color: #1E88E5;">📋 Riepilogo {dipendente_scelto} — {anno_corrente}</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 5px 0;"><b>Giorni Annui + Riporto:</b></td>
                        <td style="text-align: right;">{formatta_giorni_ore(dati_anno_corrente['disponibili'])}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 0;"><b>Giorni Goduti (anno corrente):</b></td>
                        <td style="text-align: right;">{formatta_giorni_ore(dati_anno_corrente['usati'])}</td>
                    </tr>
                    <tr style="border-top: 1px solid #ccc;">
                        <td style="padding: 10px 0;"><b><span style="color: {colore_residuo_card};">Residuo Attuale:</span></b></td>
                        <td style="text-align: right; font-size: 1.2em; color: {colore_residuo_card};"><b>{formatta_giorni_ore(dati_anno_corrente['residuo'])}</b></td>
                    </tr>
                </table>
            </div>
        """, unsafe_allow_html=True)

def aggiungi_ferie():
  st.header("Aggiungi ferie")

  dipendenti = get_dipendenti()
  nomi_dipendenti = dipendenti['NOME'].tolist()

  modalita = st.radio(
      "Tipo di inserimento",
      ["Giorno intero", "Entrata posticipata / Uscita anticipata"],
      horizontal=True
  )

  nome = st.selectbox("Nome Dipendente", options=nomi_dipendenti)

  if modalita == "Giorno intero":
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

  else:
      # --- Permesso orario: ritardo/uscita anticipata/assenza di mezza giornata ---
      riga_dip = dipendenti[dipendenti['NOME'] == nome].iloc[0]
      orario = get_orario_dipendente(riga_dip)
      ore_previste = ore_giornaliere_previste(orario)

      st.caption(
          f"Orario previsto per **{nome}**: "
          f"{orario['mattina_inizio'].strftime('%H:%M')}–{orario['mattina_fine'].strftime('%H:%M')} / "
          f"{orario['pomeriggio_inizio'].strftime('%H:%M')}–{orario['pomeriggio_fine'].strftime('%H:%M')} "
          f"({ore_previste:g} ore/giorno). Modificabile in 'Gestione dipendenti'."
      )

      data_giorno = st.date_input("Data", format="DD/MM/YYYY", key="data_permesso_orario")

      col_mattina, col_pomeriggio = st.columns(2)
      with col_mattina:
          st.markdown("**Mattina**")
          assente_mattina = st.checkbox("Assente tutta la mattina", key="assente_mattina")
          if not assente_mattina:
              ingresso_mattina = st.time_input("Ingresso mattina", value=orario["mattina_inizio"], key="ingresso_mattina")
              uscita_mattina = st.time_input("Uscita mattina", value=orario["mattina_fine"], key="uscita_mattina")
          else:
              ingresso_mattina = orario["mattina_inizio"]
              uscita_mattina = orario["mattina_inizio"]  # ininfluente: assente_mattina=True forza 0 ore comunque

      with col_pomeriggio:
          st.markdown("**Pomeriggio**")
          assente_pomeriggio = st.checkbox("Assente tutto il pomeriggio", key="assente_pomeriggio")
          if not assente_pomeriggio:
              ingresso_pomeriggio = st.time_input("Ingresso pomeriggio", value=orario["pomeriggio_inizio"], key="ingresso_pomeriggio")
              uscita_pomeriggio = st.time_input("Uscita pomeriggio", value=orario["pomeriggio_fine"], key="uscita_pomeriggio")
          else:
              ingresso_pomeriggio = orario["pomeriggio_inizio"]
              uscita_pomeriggio = orario["pomeriggio_inizio"]

      frazione_anteprima = calcola_giorni_da_permesso_orario(
          orario, assente_mattina, ingresso_mattina, uscita_mattina,
          assente_pomeriggio, ingresso_pomeriggio, uscita_pomeriggio
      )
      ha_assenza_dichiarata = assente_mattina or assente_pomeriggio
      ha_orari_modificati = (
          ingresso_mattina != orario["mattina_inizio"] or uscita_mattina != orario["mattina_fine"] or
          ingresso_pomeriggio != orario["pomeriggio_inizio"] or uscita_pomeriggio != orario["pomeriggio_fine"]
      )
      if frazione_anteprima > 0:
          st.info(f"Verranno sottratti **{frazione_anteprima:g} giorni** dal monte ferie di {nome}.")
      elif ha_assenza_dichiarata or ha_orari_modificati:
          st.info("Le ore extra compensano l'assenza: **0 giorni** verranno scalati, ma l'assenza verrà comunque registrata.")
      else:
          st.caption("Nessuna variazione rispetto all'orario previsto: nulla da registrare.")

      if st.button("Inserisci permesso orario"):
          if not nome:
              st.error("Il campo 'Nome' è obbligatorio.")
          else:
              esito = add_permesso_orario(
                  nome, data_giorno, orario, assente_mattina, ingresso_mattina, uscita_mattina,
                  assente_pomeriggio, ingresso_pomeriggio, uscita_pomeriggio
              )
              if esito is True:
                  st.success("Permesso orario registrato con successo!")
                  st.rerun()
              else:
                  st.warning(esito) if isinstance(esito, str) and esito.startswith("⚠️") else st.error(esito)

@st.dialog("Modifica Dipendente")
def modifica_ferie_totali_modal(nome, ferie_attuale, orario_attuale):
    st.write(f"Stai modificando i dati per: **{nome}**")
    nuovo_budget = st.number_input("Giorni totali annui", value=int(ferie_attuale), min_value=0)

    st.markdown("**Orario di lavoro personale** (step di 15 minuti)")
    col1, col2 = st.columns(2)
    with col1:
        mattina_inizio = time_slider("Mattina - inizio", orario_attuale["mattina_inizio"], key="mod_mattina_inizio")
        pomeriggio_inizio = time_slider("Pomeriggio - inizio", orario_attuale["pomeriggio_inizio"], key="mod_pomeriggio_inizio")
    with col2:
        mattina_fine = time_slider("Mattina - fine", orario_attuale["mattina_fine"], key="mod_mattina_fine")
        pomeriggio_fine = time_slider("Pomeriggio - fine", orario_attuale["pomeriggio_fine"], key="mod_pomeriggio_fine")

    if st.button("Salva Modifiche"):
        ok_budget = update_dipendente_budget(nome, nuovo_budget)
        ok_orario = update_orario_dipendente(nome, {
            "mattina_inizio": mattina_inizio.strftime("%H:%M"),
            "mattina_fine": mattina_fine.strftime("%H:%M"),
            "pomeriggio_inizio": pomeriggio_inizio.strftime("%H:%M"),
            "pomeriggio_fine": pomeriggio_fine.strftime("%H:%M"),
        })
        # 🔧 Se le colonne orario non esistono ancora sul foglio, update_orario_dipendente
        # mostra già un errore chiaro (con i nomi delle colonne mancanti). In quel caso
        # non nascondiamo comunque il successo del salvataggio del budget.
        if ok_budget:
            st.success(f"Dati aggiornati per {nome}!" if ok_orario else f"Budget aggiornato per {nome} (orario non salvato, vedi errore sopra).")
        if ok_budget or ok_orario:
            st.rerun()

def gestione_dipendenti():
  st.header("Gestione dipendenti")
  dipendenti = get_dipendenti()

  cols = st.columns(3)
  
  # Cicliamo sulla lista anagrafica completa
  for i, dipendente in enumerate(dipendenti.itertuples(index=False)):
        with cols[i % 3]:
            orario_dip = get_orario_dipendente(dipendenti[dipendenti['NOME'] == dipendente.NOME].iloc[0])
            orario_label = (
                f"{orario_dip['mattina_inizio'].strftime('%H:%M')}–{orario_dip['mattina_fine'].strftime('%H:%M')} / "
                f"{orario_dip['pomeriggio_inizio'].strftime('%H:%M')}–{orario_dip['pomeriggio_fine'].strftime('%H:%M')}"
            )
            # Visualizzazione Card
            st.markdown(f"""
                <div style="
                    border: 1px solid #e6e9ef; 
                    padding: 20px; 
                    border-radius: 10px; 
                    background-color: #f9f9f9;
                    margin-bottom: 5px;
                    height: 140px;
                    box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                    <h3 style="margin-top:0; color:#1E88E5; font-size: 18px;">{dipendente.NOME}</h3>
                    <p style="margin-bottom:3px; font-size:14px; color: #555;">Totale annuo: <b>{dipendente.TOTALE} gg</b></p>
                    <p style="margin-bottom:0; font-size:12px; color: #888;">🕐 {orario_label}</p>
                </div>
            """, unsafe_allow_html=True)
            
            # Pulsante Modifica con icona
            # Usiamo una chiave unica (key) basata sul nome per distinguere i bottoni
            if st.button(f"📝 Modifica {dipendente.NOME}", key=f"edit_{dipendente.NOME}", use_container_width=True):
                modifica_ferie_totali_modal(dipendente.NOME, dipendente.TOTALE, orario_dip)
