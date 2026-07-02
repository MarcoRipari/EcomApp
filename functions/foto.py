import streamlit as st
import pandas as pd
#from streamlit_toggle import st_toggle_switch
#import streamlit_toggle as tog

from .gsheet import get_sheet
from .utils import normalize_bool
from utils import *

def load_df_foto(force_reload=False):
  # 🔧 FIX: Caricamento lazy + cache in sessione.
  # Prima questa funzione veniva anche chiamata a livello di modulo (fuori da
  # qualunque funzione), quindi ogni volta che il file veniva importato da
  # load_functions_from (cioè ad ogni avvio "freddo" dell'app, PRIMA ancora
  # del login, indipendentemente dalla pagina richiesta) partiva una chiamata
  # sincrona e bloccante a Google Sheets. Ora il caricamento avviene solo
  # quando serve davvero (prima apertura della pagina Foto, o refresh esplicito),
  # e il risultato resta in cache per la sessione.
  if not force_reload and "df_foto" in st.session_state:
    return st.session_state.df_foto

  sheet = get_sheet(st.secrets['FOTO_GSHEET_ID'], "LISTA")
  values = sheet.get_all_values()
  df = pd.DataFrame(values[1:], columns=values[0])
  
  # Normalizzo i booleani(True / False)
  df["SCATTARE"] = normalize_bool(df["SCATTARE"])
  df["CONSEGNATA"] = normalize_bool(df["CONSEGNATA"])
  df["RISCATTARE"] = normalize_bool(df["RISCATTARE"])
  df["DISP"] = normalize_bool(df["DISP"])
  df["DISP 027"] = normalize_bool(df["DISP 027"])
  df["DISP 012"] = normalize_bool(df["DISP 012"])

  df["X"] = pd.to_numeric(df["X"], errors="coerce").astype("Int64")
  df["Y"] = pd.to_numeric(df["Y"], errors="coerce").astype("Int64")

  st.session_state.df_foto = df
  return df

def count_da_scattare(type="totale"):
  df = st.session_state.df_foto
  scattare = len(df[df["SCATTARE"] == True])
  riscattare = len(df[df["RISCATTARE"] == True])
  consegnate = len(df[(df["CONSEGNATA"] == True) & (df["SCATTARE"] == True)])
  disponibili = len(df[((df["SCATTARE"] == True) & (df["CONSEGNATA"] == False) | (df["RISCATTARE"] == True) & (df["CONSEGNATA"] == False)) & ((df["DISP"] == True) | (df["DISP 027"] == True) | (df["DISP 012"] == True))])
  if type == "mancanti":
    return (scattare + riscattare) - consegnate
  elif type == "riscattare":
    return riscattare
  elif type == "totale":
    return scattare + riscattare
  elif type == "consegnate":
    return consegnate
  elif type == "disponibili":
    return disponibili

def get_da_riscattare():
  df = st.session_state.df_foto
  df_da_riscattare = df[df["RISCATTARE"] == True]
  return df_da_riscattare

def mostra_riscattare(sku_input):
  df = st.session_state.df_foto
  sku_norm = sku_input.strip().upper()
  match = df[(df["SKU"] == sku_norm) & (df["SCATTARE"] == False)]
  
  if match.empty:
    st.warning("❌ SKU non trovata o la foto non esiste ancora.")
  else:
    df = st.session_state.df_foto
    row = match.iloc[0]
    st.session_state["riscattare"] = row['RISCATTARE']
    
    if not st.session_state["riscattare"]:
      st.session_state["riscattare"] = False
    
    image_url = f"https://repository.falc.biz/fal001{row['SKU'].lower()}-1.jpg"
    cols = st.columns([1, 3, 1])
    
    with cols[0]:
      st.image(image_url, width=100, caption=row["SKU"])
    with cols[1]:
      st.markdown(f"**{row['DESCRIZIONE']}**")
      st.markdown(f"*Canale*: {row['CANALE']}  \n*Collezione*: {row['COLLEZIONE']}")
    with cols[2]:
      riscatta = st.toggle(
        label="Riscattare",
        value=st.session_state["riscattare"],
        key=f"ristampa_{row['SKU']}",
        args=(st.session_state["riscattare"],)
      )
      nriga = df.index[df["SKU"] == row['SKU']].tolist()[0] + 2
      if riscatta != row['RISCATTARE']:
        val = [["True"]] if riscatta else [["False"]]
        sheet = get_sheet(st.secrets['FOTO_GSHEET_ID'], "LISTA")
        sheet.update(f"L{nriga}", val)
        load_df_foto(force_reload=True)  # 🔧 forziamo il reload: ora la cache di sessione andrebbe altrimenti riusata
        if riscatta:
          df.loc[df["SKU"] == row['SKU'], "RISCATTARE"] = True
        else:
          df.loc[df["SKU"] == row['SKU'], "RISCATTARE"] = False


def aggiungi_da_riscattare(sku_input):
  df = st.session_state.df_foto
  lista_da_riscattare = df[df["RISCATTARE"] == True]
  lista_da_riscattare = lista_da_riscattare["SKU"]
  
  if sku in lista_da_riscattare:
    st.error("SKU già da riscattare")
  else:
    st.write("Imposto SKU su riscattare in ghseet")
