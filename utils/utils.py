import os
import importlib

def load_functions_from(folder_name):
    base_path = os.path.dirname(os.path.abspath(__file__))  # path di main.py
    folder_path = os.path.join(base_path, folder_name)

    print("Controllo path funzioni:", folder_path)
    print("Esiste?", os.path.exists(folder_path))

    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"La cartella {folder_path} non esiste!")

    for file in os.listdir(folder_path):
        if file.endswith(".py") and file != "__init__.py":
            module_name = file[:-3]
            module = importlib.import_module(f"{folder_name}.{module_name}")
            globals().update({k: v for k, v in module.__dict__.items() if callable(v)})
