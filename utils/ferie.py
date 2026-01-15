import streamlit as st
import gspread

def aggiungi_ferie(sheet, riga):
  sheet = get_sheet(sheet)
  try:
    sheet.append_row(riga)
    return true
  except Exception as e:
    return e
