import streamlit as st
import pandas as pd
import chardet
import io
import csv

def read_csv(uploaded_file):
    # 1. Leggi il contenuto binario (una volta sola)
    raw_data = uploaded_file.read()
    text_data = None
    
    # 2. SEQUENZA DI DECODIFICA (TRY CASCATA)
    
    # TENTATIVO 1: Latin-1 (Il più comune per i tuoi CSV con caratteri speciali)
    try:
        # Usiamo 'strict' qui per capire se effettivamente è Latin-1 puro
        text_data = raw_data.decode('latin-1', errors='strict')
    except Exception:
        # TENTATIVO 2: UTF-8 (Standard universale)
        try:
            text_data = raw_data.decode('utf-8', errors='strict')
        except Exception:
            # TENTATIVO 3: Chardet (Rilevamento automatico se i precedenti falliscono)
            result = chardet.detect(raw_data)
            encoding_rilevato = result['encoding'] or 'utf-8'
            # Qui usiamo errors='replace' come ultima spiaggia per non bloccare l'app
            text_data = raw_data.decode(encoding_rilevato, errors='replace')

    # Pulizia: Rimuoviamo il Byte Order Mark (BOM) se presente
    text_data = text_data.lstrip('\ufeff')

    # 3. LOGICA SNIFFER (Invariata per i separatori)
    try:
        sniffer = csv.Sniffer()
        # Analizziamo una porzione del testo decodificato
        dialect = sniffer.sniff(text_data[:8192], delimiters=";,|\t")
        separator = dialect.delimiter
    except Exception:
        separator = ','  # Fallback

    # 4. PASSA IL TESTO A PANDAS
    # Usiamo StringIO per passare la stringa già decodificata
    string_io = io.StringIO(text_data)
    
    return pd.read_csv(
        string_io, 
        sep=separator, 
        dtype=str, 
        on_bad_lines='warn', 
        engine='python'
    )
