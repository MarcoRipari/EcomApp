import streamlit as st
import pandas as pd
import json

from utils import *

load_functions_from("functions", globals())

foto_sheet_id = st.secrets["FOTO_GSHEET_ID"]
sheet_ordini = get_sheet(foto_sheet_id, "ORDINI")

map_cod_cli = {
  "0019243.016":"ECOM",
  "0039632":"ZFS",
  "0034630":"AMAZON"
}

def foto_dashboard():
  with st.spinner("Carico lista SKUs..."):
    load_df_foto()
    df = st.session_state.df_foto

  st.session_state.df_foto_filtro = "Tutti"
  
  st.title("Dashboard")
  col1, col2, col3, col4 = st.columns(4)
  with col1:
      bordered_box("Da scattare", count_da_scattare(), "📸")
  with col2:
      bordered_box("Dal fotografo", count_da_scattare("consegnate"), "🧑‍🎨")
  with col3:
      bordered_box("Mancanti", count_da_scattare("mancanti"), "⏳")
  with col4:
      bordered_box("Riscattare", count_da_scattare("riscattare"), "🔁")

  if st.button("Aggiorna"):
    load_df_foto()
      
  filtro_foto = st.selectbox("📌 Filtro", ["Tutti", "Solo da scattare", "Solo già scattate", "Solo da riscattare", "Disponibili da prelevare", "Disponibili per Matias", "Disponibili per Matteo"], key=st.session_state.df_foto_filtro)
  if df.empty:
    st.warning("Nessuna SKU disponibile.")
  else:
    # 🔍 Applica filtro
    if filtro_foto == "Solo da scattare":
      df = df[df["SCATTARE"] == True]
      st.session_state.df_foto_filtro =  "Solo da scattare"
    elif filtro_foto == "Solo già scattate":
      df = df[df["SCATTARE"] == False]
      st.session_state.df_foto_filtro = "Solo già scattate"
    elif filtro_foto == "Solo da riscattare":
      df = df[df["RISCATTARE"] == True]
      st.session_state.df_foto_filtro = "Solo da riscattare"
    elif filtro_foto == "Disponibili da prelevare":
      df = df[df["DISP"] == True]
      st.session_state.df_foto_filtro = "Disponibili da prelevare"
    elif filtro_foto == "Disponibili per Matias":
      df = df[df["FOTOGRAFO"] == "MATIAS"]
      st.session_state.df_foto_filtro = "Disponibili per Matias"
    elif filtro_foto == "Disponibili per Matteo":
      df = df[df["FOTOGRAFO"] == "MATTEO"]
      st.session_state.df_foto_filtro = "Disponibili per Matteo"

  df = df[["CANALE", "SKU", "COLLEZIONE", "DESCRIZIONE", "SCATTARE", "RISCATTARE", "FOTOGRAFO", "DISP", "DISP 027", "DISP 012"]]
  st.write(df)
  

def foto_riscattare():
  st.title("Riscattare")

  lista_da_riscattare = get_da_riscattare()
  
  sku_input = st.text_input("Inserisci SKU")
  
  if sku_input:
    mostra_riscattare(sku_input)
  

def foto_import_ordini():
  st.title("Importa ordini nuova stagione")

  uploaded_files = st.file_uploader("Carica i file CSV", type="csv", accept_multiple_files=True)
  
  df_totale = pd.DataFrame()
   
  if uploaded_files:
    try:
      for file in uploaded_files:
        output = read_csv_auto_encoding(file)
        df = pd.DataFrame(output[1:].astype(str))
        df["COD.CLIENTI"] = df["COD.CLIENTI"].map(map_cod_cli)
        df["SKU"] = df["Cod"] + df["Var."] + df["Col."]
        df_totale = pd.concat([df_totale, df], ignore_index=True)
      st.success("File CSV caricati correttamente.")
    except Exception as e:
      st.write(f"Errore: {e}")

    data = df_totale.fillna("").astype(str).values.tolist()
    
    if st.button("Carica su GSheet"):
      with st.spinner("Upload su GSheet in corso..."):
        sheet_ordini.append_rows(data, value_input_option="RAW")
        st.success("Caricati correttamente su GSheet")
