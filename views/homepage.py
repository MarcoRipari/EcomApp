import streamlit as st
import os
import importlib

from utils import *
            
load_functions_from("functions", globals())

def homepage():
    st.title("Homepage")

    if st.sidebar.button("Svuota Cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.success("Cache svuotata con successo!")
        st.rerun()


    if st.sidebar.button("Svuota Memoria"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.success("Memoria svuotata con successo!")
        st.rerun()


