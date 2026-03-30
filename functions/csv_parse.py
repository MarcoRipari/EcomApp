import pandas as pd
import chardet
import io
import csv

def read_csv_auto_encoding(uploaded_file, separatore=None):
    # 1. Leggi il contenuto binario
    raw_data = uploaded_file.read()
    text_data = None
    
    # 2. TENTATIVI DI DECODIFICA (GERARCHIA)
    # Proviamo prima Latin-1 (il più comune per i vostri gestionali/Excel)
    try:
        text_data = raw_data.decode('latin-1', errors='strict')
    except Exception:
        # Se fallisce, proviamo UTF-8 (standard web)
        try:
            text_data = raw_data.decode('utf-8', errors='strict')
        except Exception:
            # Come ultima spiaggia usiamo chardet con rimpiazzo caratteri sporchi
            result = chardet.detect(raw_data)
            enc = result['encoding'] or 'utf-8'
            text_data = raw_data.decode(enc, errors='replace')

    # Pulizia: Rimuoviamo caratteri invisibili iniziali (BOM)
    text_data = text_data.lstrip('\ufeff')

    # 3. DETERMINAZIONE SEPARATORE
    if not separatore:
        try:
            # Sniffiamo il separatore dal testo decodificato
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(text_data[:8192], delimiters=";,|\t")
            separatore = dialect.delimiter
        except Exception:
            separatore = ',' # Fallback

    # 4. TRASFORMAZIONE IN DATAFRAME
    # Usiamo StringIO: Pandas legge una stringa di testo già pronta, 
    # non deve più preoccuparsi dell'encoding.
    string_io = io.StringIO(text_data)
    
    return pd.read_csv(
        string_io, 
        sep=separatore, 
        dtype=str, 
        on_bad_lines='warn', 
        engine='python'
    )
