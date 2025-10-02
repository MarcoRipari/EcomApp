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
