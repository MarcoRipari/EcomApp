import streamlit as st
import pages  # importa il pacchetto con i moduli

st.set_page_config(page_title="Gestione ECOM", layout="wide")

# qui scegli quale pagina visualizzare
pagina = st.sidebar.selectbox("Pagina", ["Home", "Login", "Admin"])

if pagina == "Home":
    pages.homepage.view()  # richiama la funzione della pagina
