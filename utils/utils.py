import os
import importlib

def load_functions_from(folder_name):
    """
    Carica dinamicamente tutte le funzioni da una cartella
    e le aggiunge allo scope globale di chi importa questa funzione.
    """
    # path assoluto della cartella contenente main.py
    base_path = os.path.dirname(os.path.abspath(__file__))  # path di main.py
    folder_path = os.path.join(base_path, folder_name)      # cartella viste/

    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"La cartella {folder_path} non esiste!")

    # scansiona tutti i file Python nella cartella
    for file in os.listdir(folder_path):
        if file.endswith(".py") and file != "__init__.py":
            module_name = file[:-3]
            module = importlib.import_module(f"{folder_name}.{module_name}")

            # aggiunge tutte le funzioni nello scope globale di chi importa
            globals().update({k: v for k, v in module.__dict__.items() if callable(v)})
