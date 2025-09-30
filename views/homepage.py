import streamlit as st
from utils import *

load_functions_from("functions")

def homepage():
    st.title("Homepage")
    
    sheet_id = st.text_input("Inserisci Sheet ID")
    tab = st.text_input("Inserisci Tab")
