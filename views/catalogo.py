import streamlit as st
import pandas as pd
import json

from utils import *

load_functions_from("functions", globals())

catalogo_sheet_id = st.secrets["CATALOGO_GSHEET_ID"]
sheet_ordini = get_sheet(catalogo_sheet_id, "ORDINI")

map_cod_cli = {
  "0019243.016":"ECOM",
  "0039632":"ZFS",
  "0034630":"AMAZON"
}

def catalogo_import_ordini():
    st.title("Importa ordini nuova stagione")

    uploaded_files = st.file_uploader("Carica i file CSV", type="csv", accept_multiple_files=True)
    
    if uploaded_files:
        df_list = [] # Usiamo una lista per accumulare i DF (più efficiente)
        
        try:
            for file in uploaded_files:
                # 1. Leggi con la nuova funzione auto-encoding
                df = read_csv_auto_encoding(file)
                
                # 2. Trasformazioni (Assicurati che Cod, Var e Col esistano)
                # Usiamo fillna("") prima per evitare errori di concatenazione stringhe
                df = df.fillna("")
                df["COD.CLIENTI"] = df["COD.CLIENTI"].map(map_cod_cli)
                df["SKU"] = df["Cod"].astype(str) + df["Var."].astype(str) + df["Col."].astype(str)
                
                # Prendi solo le prime 21 colonne per essere sicuro dell'allineamento
                df = df.iloc[:, :21]
                df_list.append(df)
            
            # Uniamo tutti i file
            df_totale = pd.concat(df_list, ignore_index=True)
            st.success(f"Dati pronti: {len(df_totale)} righe totali da {len(uploaded_files)} file.")
            
            # Mostra anteprima per debug
            st.dataframe(df_totale.head())

            if st.button("Carica su GSheet"):
                with st.spinner("Upload su GSheet in corso..."):
                    # Trasformiamo in lista di liste
                    data = df_totale.fillna("").astype(str).values.tolist()
                    
                    if not data:
                        st.error("Nessun dato trovato nei file.")
                        return

                    # 3. Calcolo dinamico del Range
                    col_a = sheet_ordini.col_values(1)
                    prossima_riga = len(col_a) + 1
                    
                    # Numero di righe e colonne dai dati reali
                    num_righe = len(data)
                    num_colonne = len(data[0]) if data else 0
                    
                    # Determiniamo la lettera della colonna finale (21 = U)
                    colonna_fine = "U" 
                    riga_fine = prossima_riga + num_righe - 1
                    
                    range_target = f"A{prossima_riga}:{colonna_fine}{riga_fine}"
                    
                    # 4. Upload
                    try:
                        sheet_ordini.update(range_target, data, value_input_option="USER_ENTERED")
                        st.success(f"✅ Caricate {num_righe} righe partendo da riga {prossima_riga}")
                    except Exception as api_err:
                        st.error(f"Errore API Google: {api_err}")
                        st.info("Prova a ridurre il numero di file o a pulire le righe vuote nel foglio.")

        except Exception as e:
            st.error(f"Errore durante l'elaborazione: {e}")
