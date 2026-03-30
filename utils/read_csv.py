import streamlit as st
import pandas as pd
import chardet
import io
import csv

def read_csv(uploaded_file):
    # 1. Leggi il contenuto binario
    raw_data = uploaded_file.read()
    
    # 2. Rileva l'encoding
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    
    # Fallback se chardet non è sicuro (spesso succede con file piccoli)
    if not encoding or result['confidence'] < 0.5:
        encoding = 'utf-8'
    
    # 3. Decodifica in stringa per lo sniffing del separatore
    # Usiamo errors='replace' per evitare crash se un singolo carattere è sporco
    try:
        text_data = raw_data.decode(encoding, errors='replace')
    except Exception:
        text_data = raw_data.decode('latin1', errors='replace')
        encoding = 'latin1'

    # 4. Sniffing del separatore
    try:
        sniffer = csv.Sniffer()
        # Analizziamo una porzione significativa ma non eccessiva
        dialect = sniffer.sniff(text_data[:8192], delimiters=";,|\t")
        separator = dialect.delimiter
    except Exception:
        separator = ','  # Fallback standard

    # 5. PASSA IL TESTO DECODIFICATO A PANDAS
    # Invece di passare il file originale, passiamo un buffer di testo
    # Questo evita che Pandas cerchi di ri-decodificare il file binario
    string_io = io.StringIO(text_data)
    
    return pd.read_csv(
        string_io, 
        sep=separator, 
        dtype=str, 
        on_bad_lines='warn', # Non crashare se una riga è malformata
        engine='python'      # Più tollerante con encoding complessi
    )
