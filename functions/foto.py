import streamlit as st
import pandas as pd

from .gsheet import get_sheet

sheet = get_sheet(st.secrets['FOTO_GSHEET_ID'], "LISTA")
values = sheet.get_all_values()
def count_foto_mancanti():
  
  df = pd.DataFrame(values[1:], columns=values[0])
  scattare = len(df[df["SCATTARE"] == True])
  riscattare = len(df[df["RISCATTARE"] == True])
  st.write(f"Da Scattare: {scattare}")
