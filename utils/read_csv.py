import streamlit as st
import pandas as pd
import chardet

def read_csv(uploaded_file, separatore=None):
    raw_data = uploaded_file.read()
    result = chardet.detect(raw_data)
    encoding = result['encoding'] or 'utf-8'
    
    text_data = raw_data.decode(encoding, errors='replace')
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(text_data[:4096], delimiters=";,|\t")
        separator = dialect.delimiter
    except csv.Error:
        separator = ','  # fallback
        
    uploaded_file.seek(0)  # Rewind after read
    return pd.read_csv(uploaded_file, sep=separator, encoding=encoding, dtype=str)
