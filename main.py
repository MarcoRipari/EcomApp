import streamlit as st
from streamlit_option_menu import option_menu
import os
import importlib

from utils import *

# Carica viste e funzioni
load_functions_from("functions", globals())
load_functions_from("views", globals())

st.set_page_config(page_title="Gestione ECOM", layout="wide")

st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] {
            width: 300px !important; # Set the width to your desired value
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# 📁 Caricamento dati
# Sidebar: menu
page = "Homepage"

with st.sidebar:
    DEBUG = st.checkbox("🪛 Debug")
    # Togliere per riattivare password e nome
    #st.session_state["logged_as"] = "GUEST"
    if DEBUG:
        st.session_state.user = {
            "data": "data",
            "email": "test@test.it",
            "nome": "GUEST",
            "cognome": "Test2",
            "username": "Username",
            "role": "admin"
        }

    if "user" not in st.session_state or st.session_state.user is None:
        page = "Home"
        st.markdown("## 🔑 Login")
        with st.form("login_user"):
            email = st.text_input("Username")
            password = st.text_input("Password", type="password")

            login_button = st.form_submit_button("Accedi")
            
        if login_button:
            if login(email, password):
                st.rerun()  # ricarica subito la pagina senza messaggio
    else:
        user = st.session_state.user
        st.write(f"Accesso eseguito come: {user["nome"]}")

        menu_item_list = [{"name":"Homepage", "icon":"house", "role":["guest","logistica","customer care","admin"]},
                          {"name":"Catalogo", "icon":"list", "role":["logistica","customer care","admin"]},
                          {"name":"Ordini", "icon":"truck", "role":["logistica","customer care","admin"]},
                          {"name":"Descrizioni", "icon":"list", "role":["customer care","admin"]},
                          {"name":"Foto", "icon":"camera", "role":["logistica","customer care","admin"]},
                          {"name":"Giacenze", "icon":"box", "role":["logistica","customer care","admin"]},
                          {"name":"Ferie", "icon":"palm", "role":["admin"]},
                          {"name":"Admin", "icon":"gear", "role":["admin"]},
                          {"name":"Test", "icon":"gear", "role":["admin"]},
                          {"name":"Logout", "icon":"key", "role":["guest","logistica","customer care","admin"]}
                         ]
        
        submenu_item_list = [{"main":"Catalogo", "name":"Trova articolo", "icon":"search", "role":["logistica","customer care","admin"]},
                             {"main":"Catalogo", "name":"Aggiungi ordini stagione", "icon":"plus", "role":["logistica","customer care","admin"]},
                             {"main":"Ordini", "name":"Dashboard", "icon":"bar-chart", "role":["admin"]},
                             {"main":"Ordini", "name":"Importa", "icon":"plus", "role":["admin"]},
                             {"main":"Foto", "name":"Dashboard", "icon":"gear", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Foto", "name":"Import ordini stagione", "icon":"gear", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Foto", "name":"Riscatta SKU", "icon":"repeat", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Foto", "name":"Aggiungi SKUs", "icon":"plus", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Foto", "name":"Storico", "icon":"book", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Foto", "name":"Aggiungi prelevate", "icon":"hand-index", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Giacenze", "name":"Importa", "icon":"download", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Giacenze", "name":"Per corridoio", "icon":"1-circle", "role":["guest","logistica","admin"]},
                             {"main":"Giacenze", "name":"Per corridoio/marchio", "icon":"2-circle", "role":["guest","logistica","admin"]},
                             {"main":"Giacenze", "name":"Aggiorna anagrafica", "icon":"refresh", "role":["guest","logistica","customer care","admin"]},
                             {"main":"Giacenze", "name":"Old import", "icon":"download", "role":["admin"]},
                             {"main":"Ferie", "name":"Report", "icon":"list", "role":["admin"]},
                             {"main":"Ferie", "name":"Aggiungi ferie", "icon":"plus", "role":["admin"]},
                             {"main":"Admin", "name":"Aggiungi utente", "icon":"plus", "role":["admin"]}
                            ]
        
        menu_items = []
        icon_items = []
        for item in menu_item_list:
            if user["role"] in item["role"]:
                menu_items.append(item["name"])
                icon_items.append(item["icon"])
        
        
        st.markdown("## 📋 Menu")
        # --- Menu principale verticale ---
        main_page = option_menu(
            menu_title=None,
            options=menu_items,
            icons=icon_items,
            default_index=0,
            orientation="vertical",
            styles={
                "container": {"padding": "0!important", "background-color": "#f0f0f0"},
                "nav-link": {
                    "font-size": "16px",
                    "text-align": "left",
                    "margin": "2px",
                    "padding": "5px 10px",
                    "border-radius": "5px",
                    "--hover-color": "#e0e0e0",
                },
                "nav-link-selected": {
                    "background-color": "#4CAF50",
                    "color": "white",
                    "border-radius": "5px",
                },
            },
        )

        # Rimuovo icone/emoji per gestire page name
        main_page_name = main_page

        page = main_page_name  # default

        submenu_items = []
        submenu_icons = []
        for item in submenu_item_list:
            if main_page == item["main"] and user["role"] in item["role"]:
                submenu_items.append(item["name"])
                submenu_icons.append(item["icon"])
                
        if submenu_items:
            sub_page = option_menu(
                menu_title=None,
                options=submenu_items,
                icons=submenu_icons,
                default_index=0,
                orientation="vertical",
                styles={
                    "container": {"padding": "0!important", "background-color": "#f0f0f0"},
                    "nav-link": {
                        "font-size": "15px",
                        "text-align": "left",
                        "margin": "2px",
                        "padding": "5px 15px",
                        "border-radius": "5px",
                        "--hover-color": "#e0e0e0",
                    },
                    "nav-link-selected": {
                        "background-color": "#4CAF50",
                        "color": "white",
                        "border-radius": "5px",
                    },
                },
            )
            page = f"{main_page_name} - {sub_page}"

if page == "Homepage" or not page:
    homepage()

elif page == "Foto - Dashboard":
    foto_dashboard()
    
elif page == "Foto - Import ordini stagione":
    foto_import_ordini()
