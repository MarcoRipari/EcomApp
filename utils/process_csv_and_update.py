import streamlit as st
import pandas as pd


def process_csv_and_update(sheet, uploaded_file, batch_size=100):
    st.text("1️⃣ Leggo CSV...")
    df = read_csv(uploaded_file)

    expected_cols = [
        "Anno","Stag.","Clz.","Descr.","Serie","Descriz1","Annullato",
        "Campionato","Cat","Cod","Descr2","Var.","DescrizVar","Col.",
        "DescrCol","TAGLIA","QUANTIA","DATA_CREAZIONE","N=NOOS"
    ]

    if df.shape[1] != len(expected_cols):
        st.error(f"⚠️ CSV ha {df.shape[1]} colonne invece di {len(expected_cols)}. Controlla separatore o formato!")
        st.dataframe(df.head())
        return 0, 0

    df.columns = expected_cols
    df["SKU"] = df["Cod"].astype(str) + df["Var."].astype(str) + df["Col."].astype(str)

    # Porta SKU come prima colonna
    cols = ["SKU"] + [c for c in df.columns if c != "SKU"]
    df = df[cols]

    st.text("2️⃣ Carico dati esistenti dal foglio...")
    existing_values = sheet.get("A:U")
    if not existing_values:
        header = df.columns.tolist()
        existing_df = pd.DataFrame(columns=header)
    else:
        header = existing_values[0]
        data = existing_values[1:]
        existing_df = pd.DataFrame(data, columns=header)

    existing_df = existing_df.fillna("").astype(str)
    existing_dict = {row["SKU"]: row for _, row in existing_df.iterrows()}

    st.text("3️⃣ Identifico nuove righe e aggiornamenti...")
    new_rows = []
    updates = []

    total = len(df)
    progress = st.progress(0)

    for i, row in df.iterrows():
        sku = row["SKU"]
        new_year_stage = (int(row["Anno"]), int(row["Stag."]))
        single_row = ["" if pd.isna(x) else str(x) for x in row]

        if sku not in existing_dict:
            new_rows.append(single_row)
        else:
            existing_row = existing_dict[sku]
            existing_year_stage = (int(existing_row["Anno"]), int(existing_row["Stag."]))
            if new_year_stage[0] > existing_year_stage[0] or \
               (new_year_stage[0] == existing_year_stage[0] and new_year_stage[1] > existing_year_stage[1]):
                idx = existing_df.index[existing_df["SKU"] == sku][0] + 2  # +2 per header e base 1
                updates.append((idx, single_row))

        if i % 50 == 0:
            progress.progress(i / total)
    progress.progress(1.0)

    st.text(f"✅ Nuove righe da aggiungere: {len(new_rows)}")
    st.text(f"✅ Aggiornamenti da effettuare: {len(updates)}")
