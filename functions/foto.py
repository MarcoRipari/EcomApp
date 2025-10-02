import streamlit as st
import pandas as pd

from .gsheet import get_sheet
from .utils import normalize_bool

sheet = get_sheet(st.secrets['FOTO_GSHEET_ID'], "LISTA")
values = sheet.get_all_values()
df = pd.DataFrame(values[1:], columns=values[0])

# Normalizzo i booleani (True / False)
df["SCATTARE"] = normalize_bool(df["SCATTARE"])
df["CONSEGNATA"] = normalize_bool(df["CONSEGNATA"])
df["RISCATTARE"] = normalize_bool(df["RISCATTARE"])
df["DISP"] = normalize_bool(df["DISP"])
df["DISP 027"] = normalize_bool(df["DISP 027"])
df["DISP 028"] = normalize_bool(df["DISP 028"])

def count_da_scattare(type="totale"):
  scattare = len(df[df["SCATTARE"] == True])
  riscattare = len(df[df["RISCATTARE"] == True])
  if type == "mancanti":
    return scattare
  elif type == "riscattare":
    return riscattare
  elif type == "totale":
    return scattare + riscattare

def get_da_riscattare():
  da_riscattare = df[df["RISCATTARE"] == True]
  return da_riscattare["SKU"]

def mostra_riscattare(sku_input):
  sku_norm = sku_input.strip().upper()
  match = df[(df["SKU"] == sku_norm) & (df["SCATTARE"] == False)]
  
  if match.empty:
    st.warning("❌ SKU non trovata o la foto non esiste ancora.")
  else:
    row = match.iloc[0]
    riscattare = row['RISCATTARE']
    
    if not riscattare:
      riscattare = False

    image_url = f"https://repository.falc.biz/fal001{row['SKU'].lower()}-1.jpg"
    cols = st.columns([1, 3, 1])
    
    with cols[0]:
        st.image(image_url, width=100, caption=row["SKU"])
    with cols[1]:
        st.markdown(f"**{row['DESCRIZIONE']}**")
        st.markdown(f"*Canale*: {row['CANALE']}  \n*Collezione*: {row['COLLEZIONE']}")
    with cols[2]:
        ristampa_checkbox = st.checkbox("🔁 Ristampa", value=riscattare, key=f"ristampa_{row['SKU']}")

def aggiungi_da_riscattare(sku_input):
  lista_da_riscattare = df[df["RISCATTARE"] == True]
  lista_da_riscattare = lista_da_riscattare["SKU"]
  
  if sku in lista_da_riscattare:
    st.error("SKU già da riscattare")
  else:
    st.write("Imposto SKU su riscattare in ghseet")
  
