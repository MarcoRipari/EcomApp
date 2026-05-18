import streamlit as st
import os
import time
import json
import pickle
import logging
import asyncio
import hashlib
import re
import random
from typing import List, Dict
from collections import deque

import pandas as pd
import numpy as np
import requests
from openai import AsyncOpenAI
import faiss

from utils import *
from functions.gsheet import get_sheet

LANG_NAMES = {
    "IT": "italiano",
    "EN": "inglese",
    "FR": "francese",
    "DE": "tedesco",
    "ES": "spagnolo"
}
LANG_LABELS = {v.capitalize(): k for k, v in LANG_NAMES.items()}

# Client OpenAI async
client = AsyncOpenAI(api_key=st.secrets["OPENAI_API_KEY"])

@st.cache_resource
def load_model():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2", use_auth_token=st.secrets["HF_TOKEN"])
    return model.to("cpu")

def embed_texts(texts: List[str], batch_size=32) -> List[List[float]]:
    model = load_model()
    return model.encode(texts, show_progress_bar=False, batch_size=batch_size).tolist()

def hash_dataframe_and_weights(df: pd.DataFrame, col_weights: Dict[str, float]) -> str:
    df_bytes = pickle.dumps((df.fillna("").astype(str), col_weights))
    return hashlib.md5(df_bytes).hexdigest()

def build_faiss_index(df: pd.DataFrame, col_weights: Dict[str, float], cache_dir="faiss_cache"):
    os.makedirs(cache_dir, exist_ok=True)
    cache_key = hash_dataframe_and_weights(df, col_weights)
    cache_path = os.path.join(cache_dir, f"{cache_key}.index")

    if os.path.exists(cache_path):
        index = faiss.read_index(cache_path)
        return index, df

    texts = []
    for _, row in df.iterrows():
        parts = []
        for col in df.columns:
            if pd.notna(row[col]):
                weight = col_weights.get(col, 1)
                if weight > 0:
                    parts.append((f"{col}: {row[col]} ") * int(weight))
        texts.append(" ".join(parts))

    vectors = embed_texts(texts)
    index = faiss.IndexFlatL2(len(vectors[0]))
    index.add(np.array(vectors).astype("float32"))
    faiss.write_index(index, cache_path)

    return index, df

def retrieve_similar(query_row: pd.Series, df: pd.DataFrame, index, k=5, col_weights: Dict[str, float] = {}):
    parts = []
    for col in df.columns:
        if pd.notna(query_row[col]):
            weight = col_weights.get(col, 1)
            if weight > 0:
                parts.append((f"{col}: {query_row[col]} ") * int(weight))
    query_text = " ".join(parts)

    query_vector = embed_texts([query_text])[0]
    D, I = index.search(np.array([query_vector]).astype("float32"), k)

    return df.iloc[I[0]]

def build_function_schema(selected_langs):
    lang_block = {}
    for lang in selected_langs:
        lang_block[lang] = {
            "type": "object",
            "properties": {
                "desc_lunga": {"type": "string"},
                "desc_breve": {"type": "string"}
            },
            "required": ["desc_lunga", "desc_breve"]
        }
    return [
        {
            "name": "generate_product_descriptions",
            "description": "Genera descrizioni prodotto per una calzatura e-commerce",
            "parameters": {
                "type": "object",
                "properties": lang_block,
                "required": selected_langs
            }
        }
    ]
    
def build_unified_prompt(row, col_display_names, selected_langs, selected_tones, desc_lunga_length, desc_breve_length, simili=None, marchio=None):
    fields = []
    for col in col_display_names:
        if col in row and pd.notna(row[col]):
            label = col_display_names[col]
            if label != "Codice Articolo":
                fields.append(f"- {label}: {row[col]}")
    product_info = "\n".join(fields)

    adulto = ["VB", "FM", "CC", "WZ"]
    bambino = ["NAT", "FAL"]
    
    lang_list = ", ".join([LANG_NAMES.get(lang.upper(), lang) for lang in selected_langs])

    sim_text = ""
    if simili is not None and not simili.empty:
        sim_lines = []
        for _, ex in simili.iterrows():
            dl = ex.get("Description", "").strip()
            db = ex.get("Description2", "").strip()
            if dl and db:
                sim_lines.append(f"- {dl}\n  {db}")
        if sim_lines:
            sim_text = "\nDescrizioni simili:\n" + "\n".join(sim_lines)

    concept = row.get("Concept", "")
    incipit_seeds = ["SEO-oriented", "Descrittivo", "Pratico", "Classico", "Informativo", "Accattivante"]

    # Fallback to general prompt if no specific brand logic is found
    # (Keeping the structure from app_old.py but removing image-specific lines)

    if marchio in bambino:
        prompt = f"""Scrivi due descrizioni per una calzatura da vendere online (e-commerce), coerenti con le INFO ARTICOLO, in ciascuna delle seguenti lingue: {lang_list}.

Le descrizioni devono riprendere tono, struttura e naturalezza delle descrizioni catalogo tradizionali, con un linguaggio semplice, fluido e descrittivo.

### INFO PRODOTTO ###
{product_info}
CONCEPT
{concept}

*** Regole del concept ***
- può ispirare l’apertura del testo
- non deve essere citato
- non deve introdurre abbinamenti o stili di abbigliamento

### STILE ###
- Apertura: {random.choice(incipit_seeds)}
- Tono: {", ".join(selected_tones)}
- Linguaggio naturale, editoriale
- Frasi complete e scorrevoli
- Nessuna formattazione

### CONTENUTO ###
- Usa esclusivamente le informazioni presenti nelle INFO ARTICOLO
- Usa il tipo di calzatura fornito
- Descrivi:
  - forma o costruzione
  - tomaia
  - eventuali dettagli visibili
  - chiusura
  - fodera e soletta
  - fondo o suola
- I materiali devono essere citati in modo chiaro e diretto
- Vietati: effetto usato, effetto vissuto, trattato, lavorato, lavato, spazzolato, vintage, scarpa prima, prime scarpe
- NON usare abbreviazioni, ellissi o forme contratte

### OUTPUT ###
Genera due testi:
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}
"""
    elif marchio == "VB":
        prompt = f"""
Scrivi due descrizioni per una calzatura da vendere online (catalogo e-commerce), in ciascuna delle seguenti lingue: {lang_list}.

### INFO ARTICOLO ###
{product_info}
CONCEPT
{concept}

### STILE E TONO ###
- Tono: fashion contemporaneo
- Registro: medio-alto
- Nessuna formattazione, nessun elenco

### OUTPUT ###
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}
"""
    elif marchio == "FM":
        prompt = f"""
Scrivi due descrizioni per una calzatura da vendere online (e-commerce), in ciascuna delle seguenti lingue: {lang_list}.

### INFO PRODOTTO ###
{product_info}
CONCEPT
{concept}

### STILE ###
- Tono: tecnico–editoriale, brand–driven
- Mondo outdoor / urbano

### OUTPUT ###
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}
"""
    elif marchio == "CC":
        prompt = f"""
Scrivi due descrizioni per una calzatura da vendere online (e-commerce), in ciascuna delle seguenti lingue: {lang_list}.

### INFO PRODOTTO ###
{product_info}
CONCEPT
{concept}

### STILE ###
- Tono: fashion–editoriale, premium, urbano

### OUTPUT ###
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}
"""
    else:
        # Default fallback
        prompt = f"""Genera descrizioni per {lang_list} basate su:\n{product_info}\nTono: {", ".join(selected_tones)}"""

    return prompt

async def async_generate_description(prompt: str, idx: int, use_model: str, langs):
    if prompt == "SaltaRiga":
        return idx, {"Continuativo": "Si"}

    try:
        functions = build_function_schema(langs)
        response = await client.chat.completions.create(
            model=use_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            functions=functions,
            function_call={"name": "generate_product_descriptions"},
        )
        message = response.choices[0].message
        if message.function_call:
            data = json.loads(message.function_call.arguments)
            return idx, {"result": data, "usage": response.usage.model_dump()}
        return idx, {"error": "No function call in response"}
    except Exception as e:
        return idx, {"error": str(e)}

async def generate_all_prompts(prompts: list[str], model: str, langs) -> dict:
    tasks = [async_generate_description(prompt, idx, model, langs) for idx, prompt in enumerate(prompts)]
    results = await asyncio.gather(*tasks)
    return dict(results)

def calcola_tokens(df_input, col_display_names, selected_langs, selected_tones, desc_lunga_length, desc_breve_length, k_simili, marchio, faiss_index, DEBUG=False):
    if df_input.empty:
        return None, None, "❌ Il CSV è vuoto"

    row = df_input.iloc[0]
    simili = pd.DataFrame([])
    if k_simili > 0 and faiss_index:
        index, index_df = faiss_index
        simili = retrieve_similar(row, index_df, index, k=k_simili, col_weights=st.session_state.col_weights)
        
    prompt = build_unified_prompt(
        row=row,
        col_display_names=col_display_names,
        selected_langs=selected_langs,
        selected_tones=selected_tones,
        desc_lunga_length=desc_lunga_length,
        desc_breve_length=desc_breve_length,
        simili=simili,
        marchio=marchio
    )

    num_chars = len(prompt)
    token_est = num_chars // 4
    cost_est = round(token_est / 1000 * 0.001, 6)

    if DEBUG:
        st.code(prompt)
    return token_est, cost_est, prompt
