import streamlit as st
import pandas as pd

from .gsheet import get_sheet

sheet = get_sheet(st.secrets['FOTO_GSHEET_ID'], "LISTA")

def count_foto_mancanti():
  df = pd.DataFrame(sheet.get_all_values())
  st.dataframe(df)
