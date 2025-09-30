import os
import importlib

def load_functions_from(folder_name):
    """
    Carica tutte le funzioni da una cartella e le mette nello scope globale.
    """
    # path assoluto della cartella che contiene main.py
    base_path = os.path.dirname(os.path.abspath(__file__))  # se eseguito da main.py, va bene
    folder_path = os.path.join(base_path, folder_name)      # folder_name = "functions" o "views"

    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"La cartella {folder_path} non esiste!")

    for file in os.listdir(folder_path):
        if file.endswith(".py") and file != "__init__.py":
            module_name = file[:-3]
            module = importlib.import_module(f"{folder_name}.{module_name}")
            globals().update({k: v for k, v in module.__dict__.items() if callable(v)})
