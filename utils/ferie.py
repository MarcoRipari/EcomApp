import streamlit as st
import gspread

ferie_sheet_id = st.secrets["FERIE_GSHEET_ID"]

def aggiungi_ferie(riga):
  sheet = get_sheet(ferie_sheet_id,"FERIE")
  try:
    sheet.append_row(riga)
    return true
  except Exception as e:
    return e
