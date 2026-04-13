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
        df_list = []
        try:
            for file in uploaded_files:
                df = read_csv_auto_encoding(file)
                df = df.fillna("")
                df["COD.CLIENTI"] = df["COD.CLIENTI"].map(map_cod_cli)
                df["SKU"] = df["Cod"].astype(str) + df["Var."].astype(str) + df["Col."].astype(str)
                # Forza il numero di colonne a 21
                df = df.iloc[:, :21]
                df_list.append(df)
            
            df_totale = pd.concat(df_list, ignore_index=True)
            st.info(f"Totale righe da caricare: {len(df_totale)}")

            if st.button("Carica su GSheet"):
                with st.spinner("Verifica spazio e upload in corso..."):
                    data = df_totale.fillna("").astype(str).values.tolist()
                    
                    # 1. Calcola la posizione di partenza
                    col_a = sheet_ordini.col_values(1)
                    prossima_riga = len(col_a) + 1
                    num_righe_nuove = len(data)
                    riga_finale_necessaria = prossima_riga + num_righe_nuove - 1

                    # 2. CONTROLLO LIMITI GRIGLIA (La parte che mancava)
                    # Verifichiamo quante righe ha attualmente il foglio
                    righe_attuali = sheet_ordini.row_count
                    
                    if riga_finale_necessaria > righe_attuali:
                        righe_da_aggiungere = riga_finale_necessaria - righe_attuali
                        sheet_ordini.add_rows(righe_da_aggiungere)
                        st.write(f"Aggiunte {righe_da_aggiungere} righe al foglio per fare spazio.")

                    # 3. Definizione Range (21 colonne = U)
                    range_target = f"A{prossima_riga}:U{riga_finale_necessaria}"
                    
                    # 4. Upload finale
                    sheet_ordini.update(range_target, data, value_input_option="USER_ENTERED")
                    st.success(f"✅ Caricamento completato con successo fino alla riga {riga_finale_necessaria}")

        except Exception as e:
            st.error(f"Errore durante l'elaborazione: {e}")
