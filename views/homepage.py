import streamlit as st
import os
import importlib

from utils import *
            
load_functions_from("functions", globals())

def homepage():
    st.title("Homepage")
    st.write("ok")
    sheet_id = st.text_input("Inserisci Sheet ID")
    tab = st.text_input("Inserisci Tab")
