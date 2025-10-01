import streamlit as st
import os
import importlib

def load_functions_from(folder_name, global_scope=None):
    base_path = os.path.dirname(os.path.abspath(__file__))
    base_path = os.path.dirname(base_path)  # vai a /ecomapp
    folder_path = os.path.join(base_path, folder_name)

    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"La cartella {folder_path} non esiste!")

    for file in os.listdir(folder_path):
        if file.endswith(".py") and file != "__init__.py":
            module_name = file[:-3]
            module = importlib.import_module(f"{folder_name}.{module_name}")
            
            target_scope = global_scope if global_scope is not None else globals()
            target_scope.update({k: v for k, v in module.__dict__.items() if callable(v)})
