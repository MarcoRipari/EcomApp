import strealit as st
import gspread

def ferie():
  st.header("Ferie")

def aggiungi_ferie():
  st.header("Aggiungi ferie")

  with st.form("form_ferie", clear_on_submit=True):
    nome = st.text_input("Nome Dipendente")
    
    col1, col2 = st.columns(2)
    with col1:
        data_inizio = st.date_input("Data inizio")
    with col2:
        data_fine = st.date_input("Data fine")
        
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
          # Se tutti i controlli passano, procediamo al salvataggio
          try:
            sheet = connect_to_sheet()
            nuova_riga = [nome, str(data_inizio), str(data_fine), tipo]
            sheet.append_row(nuova_riga)
            st.success(f"Richiesta registrata con successo per **{nome}**!")
          except Exception as e:
            st.error(f"Errore tecnico: {e}")
