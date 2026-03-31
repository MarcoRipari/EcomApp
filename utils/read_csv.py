import streamlit as st
import pandas as pd
import chardet
import io
import csv

def read_csv(uploaded_file, separatore=None):
    """
    Legge un file CSV con rilevamento automatico dell'encoding e del separatore.
    Supporta il passaggio di un separatore manuale.
    """
    # 1. Leggi il contenuto binario
    if hasattr(uploaded_file, 'read'):
        raw_data = uploaded_file.read()
    else:
        raw_data = uploaded_file

    text_data = None
    
    # 2. SEQUENZA DI DECODIFICA (TRY CASCATA)
    # TENTATIVO 1: Latin-1 (Comune per CSV da Excel/gestionali italiani)
    try:
        text_data = raw_data.decode('latin-1', errors='strict')
    except Exception:
        # TENTATIVO 2: UTF-8 (Standard universale)
        try:
            text_data = raw_data.decode('utf-8', errors='strict')
        except Exception:
            # TENTATIVO 3: Chardet (Rilevamento automatico)
            result = chardet.detect(raw_data)
            encoding_rilevato = result['encoding'] or 'utf-8'
            text_data = raw_data.decode(encoding_rilevato, errors='replace')

    # Pulizia: Rimuoviamo il Byte Order Mark (BOM) se presente
    text_data = text_data.lstrip('\ufeff')

    # 3. DETERMINAZIONE SEPARATORE
    if not separatore:
        try:
            sniffer = csv.Sniffer()
            # Analizziamo una porzione del testo decodificato
            dialect = sniffer.sniff(text_data[:8192], delimiters=";,|\t")
            separatore = dialect.delimiter
        except Exception:
            separatore = ','  # Fallback

    # 4. TRASFORMAZIONE IN DATAFRAME
    string_io = io.StringIO(text_data)
    
    return pd.read_csv(
        string_io, 
        sep=separatore,
        dtype=str, 
        on_bad_lines='warn', 
        engine='python'
    )

# Alias per compatibilità con il vecchio codice
def read_csv_auto_encoding(uploaded_file, separatore=None):
    return read_csv(uploaded_file, separatore)
