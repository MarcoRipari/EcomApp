import streamlit as st
import os
import time
import json
import pickle
import logging
import asyncio
import hashlib
import re
import random  # <--- FONDAMENTALE: mancava per i random.choice e random.uniform
from typing import List, Dict
from collections import deque

import pandas as pd
import numpy as np
import requests
from PIL import Image
import openai
from openai import AsyncOpenAI
import faiss

from utils import *

LANG_NAMES = {
    "IT": "italiano",
    "EN": "inglese",
    "FR": "francese",
    "DE": "tedesco"
}
LANG_LABELS = {v.capitalize(): k for k, v in LANG_NAMES.items()}

desc_sheet_id = st.secrets['DESC_GSHEET_ID']

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

    # 🔍 DEBUG
    logging.info(f"QUERY TEXT: {query_text[:300]} ...")
    logging.info(f"INDICI trovati: {I[0]}")
    logging.info(f"Distanze: {D[0]}")
    
    return df.iloc[I[0]]

def estimate_embedding_time(df: pd.DataFrame, col_weights: Dict[str, float], sample_size: int = 10) -> float:
    """
    Stima il tempo totale per embeddare tutti i testi del dataframe.
    """
    texts = []
    for _, row in df.head(sample_size).iterrows():
        parts = []
        for col in df.columns:
            if pd.notna(row[col]):
                weight = col_weights.get(col, 1)
                if weight > 0:
                    parts.append((f"{col}: {row[col]} ") * int(weight))
        texts.append(" ".join(parts))

    start = time.time()
    _ = embed_texts(texts)
    elapsed = time.time() - start
    avg_time_per_row = elapsed / sample_size
    total_estimated_time = avg_time_per_row * len(df)

    return total_estimated_time

def benchmark_faiss(df, col_weights, query_sample_size=10):
    import os

    st.markdown("### ⏱️ Benchmark FAISS + Embedding")

    start_embed = time.time()
    texts = []
    for _, row in df.iterrows():
        parts = [f"{col}: {row[col]}" * int(col_weights.get(col, 1))
                 for col in df.columns if pd.notna(row[col])]
        texts.append(" ".join(parts))
    vectors = embed_texts(texts)
    embed_time = time.time() - start_embed

    start_faiss = time.time()
    index = faiss.IndexFlatL2(len(vectors[0]))
    index.add(np.array(vectors).astype("float32"))
    faiss.write_index(index, "tmp_benchmark.index")
    index_time = time.time() - start_faiss

    index_size = os.path.getsize("tmp_benchmark.index")

    # Test query
    query_times = []
    for i in range(min(query_sample_size, len(df))):
        qtext = texts[i]
        start_q = time.time()
        _ = index.search(np.array([vectors[i]]).astype("float32"), 5)
        query_times.append(time.time() - start_q)

    avg_query_time = sum(query_times) / len(query_times)

    st.write({
        "🚀 Tempo embedding totale (s)": round(embed_time, 2),
        "📄 Tempo medio per riga (ms)": round(embed_time / len(df) * 1000, 2),
        "🏗️ Tempo costruzione FAISS (s)": round(index_time, 2),
        "💾 Dimensione index (KB)": round(index_size / 1024, 1),
        "🔍 Tempo medio query (ms)": round(avg_query_time * 1000, 2),
    })

    os.remove("tmp_benchmark.index")

        
# ---------------------------
# 🧠 Prompting e Generazione
# ---------------------------
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
    
def build_unified_prompt(row, col_display_names, selected_langs, simili=None, marchio=None):
    # Costruzione scheda tecnica
    fields = []
    for col in col_display_names:
        if col in row and pd.notna(row[col]):
            label = col_display_names[col]
            if label != "Codice Articolo":
                fields.append(f"- {label}: {row[col]}")
    product_info = "\n".join(fields)

    # Divisione marchi
    adulto = ["VB", "FM", "CC", "WZ"]
    bambino = ["NAT", "FAL"]
    
    # Elenco lingue in stringa
    lang_list = ", ".join([LANG_NAMES.get(lang, lang) for lang in selected_langs])

    # Descrizioni simili
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

    concept = row["Concept"]
    incipit_seeds = ["SEO-oriented", "Descrittivo", "Pratico", "Classico", "Informativo", "Accattivante"]

    if pd.notna(row["Description"]) and pd.notna(row["Description2"]):
        prompt = "SaltaRiga"
    else:
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
- Gli aggettivi possono essere usati se comuni e descrittivi
- Vietati: effetto usato, effetto vissuto, trattato, lavorato, lavato, spazzolato, vintage
- Non inserire la stagionalità del prodotto (il riferimento può essere solo sui sandali)
- NON usare abbreviazioni, ellissi o forme contratte (es. niente “-sohle”, “-lining”, ecc.)

### TERMINI VIETATI (NON DEVONO MAI COMPARIRE) ###
È vietato usare, anche in forma simile, parafrasata o con sinonimi diretti, i seguenti concetti o formulazioni:

- piedi freschi
- traspirazione / traspirante / traspirabilità
- respiro al piede / lascia respirare il piede
- tomaia sofisticata
- vellutato velour / velour vellutato
- indossamento eccellente / indossabilità eccellente
- aspetto distintivo
- durabilità

Se un concetto non è descrivibile senza usare uno dei termini vietati, deve essere **omesso**.

### STRUTTURA CONSIGLIATA (NON RIGIDA) ###
- Frase introduttiva
- Descrizione del modello
- Tomaia
- Dettagli
- Chiusura
- Fodera e soletta
- Fondo

### NORMALIZZAZIONE TIPO DI CALZATURA ###
- "first shoe", "first shoes" → SEMPRE trasformato in "scarpe"
- "special case slippers" → SEMPRE trasformato in "pantofole"
- Non usare derivati: prime scarpe, scarpa da primi passi, first shoes, first shoe
- Usare solo termine generico "scarpe"

### OUTPUT ###
Genera due testi:
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}

*** Uso delle descrizioni di riferimento ***
- tono
- ritmo
- ordine narrativo

### CONTROLLO FINALE ###
Il testo deve:
- sembrare scritto da un redattore catalogo
- non contenere tecnicismi
- non sembrare regolamentato o artificiale
- descrivere solo ciò che è visibile o dichiarato
"""
        elif marchio == "VB":
            prompt = f"""
Scrivi due descrizioni per una calzatura da vendere online (catalogo e-commerce),
coerenti con le INFO ARTICOLO, in ciascuna delle seguenti lingue: {lang_list}.

Le descrizioni devono riprodurre tono, ritmo e naturalezza delle descrizioni
storiche del catalogo Voile Blanche: editoriale, fluido, contemporaneo.

### INFO ARTICOLO ###
{product_info}

CONCEPT
{concept}

*** Regole del concept ***
- può ispirare l’apertura del testo
- non deve essere citato
- non deve diventare storytelling
- non deve introdurre abbinamenti di stile o outfit

### STILE E TONO ###
- Apertura: editoriale, interpretativa
- Tono: fashion contemporaneo
- Registro: medio-alto
- Linguaggio naturale, non tecnico
- Frasi complete, scorrevoli
- Nessuna formattazione, nessun elenco
- Il testo deve sembrare scritto da un redattore catalogo

### LINEE GUIDA DI SCRITTURA ###
- Descrivi il modello come una reinterpretazione contemporanea
- Introduci mood, ispirazione o attitudine nella frase iniziale
- Passa poi alla descrizione del modello e dei materiali
- I dettagli vanno suggeriti, non spiegati
- Il comfort non va mai argomentato o dimostrato
- Usa un lessico moda coerente con il catalogo storico
- Evita razionalizzazioni, cause-effetto, spiegazioni funzionali

### CONTENUTO ###
- Usa esclusivamente le informazioni presenti nelle INFO ARTICOLO
- Usa il tipo di calzatura fornito (normalizzato)
- Descrivi, in modo fluido e narrativo:
  - linee e costruzione
  - tomaia e materiali
  - dettagli estetici visibili
  - chiusura
  - fodera e soletta
  - fondo o suola
- I materiali devono essere citati in modo chiaro ma non tecnico
- Gli aggettivi devono essere comuni, descrittivi, editoriali
- Evita qualsiasi affermazione non visibile o non dichiarata
- Non inserire la stagionalità del prodotto (il riferimento può essere solo sui sandali)
- NON usare abbreviazioni, ellissi o forme contratte (es. niente “-sohle”, “-lining”, ecc.)

### TERMINI E CONCETTI VIETATI ###
È vietato usare, anche in forma parafrasata:

- benefici fisiologici o prestazionali
- affermazioni misurabili o dimostrative
- linguaggio tecnico o ingegneristico
- claim esplicativi (es. “garantisce”, “assicura”, “offre il massimo di”)
- spiegazioni funzionali del comfort
- Allure
- Freschezza urbana
- Charme contemporaneo
- Spirito disinvolto
- Dinamismo urbano
- Semplicità contemporanea
- Una rivisitazione contemporanea del classico
- Emerge come un'icona di stile
- Armonie metriche

Se un concetto non è descrivibile senza usare questi approcci, deve essere omesso.

### STRUTTURA NARRATIVA (NON RIGIDA) ###
- Frase editoriale introduttiva
- Definizione del modello
- Tomaia e materiali
- Dettagli iconici
- Chiusura
- Interni
- Fondo

### NORMALIZZAZIONE TIPO DI CALZATURA ###
- "low shoe" → SEMPRE trasformato in "mocassini"

### OUTPUT ###
Genera due testi distinti:
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}

*** Uso delle descrizioni di riferimento ***
- imitare tono, ritmo e ordine narrativo
- non copiare strutture sintattiche
- non ripetere formulazioni

### CONTROLLO FINALE ###
Il testo deve:
- sembrare scritto da un redattore catalogo
- non contenere tecnicismi
- non sembrare regolamentato o artificiale
- descrivere solo ciò che è visibile o dichiarato
"""
        elif marchio == "FM":
            prompt = f"""
Scrivi due descrizioni per una calzatura da vendere online (e-commerce), coerenti con le INFO ARTICOLO, in ciascuna delle seguenti lingue: {lang_list}.

Le descrizioni devono riprodurre il linguaggio di un catalogo ufficiale Flower Mountain: tecnico, descrittivo, con struttura riconoscibile e lessico ricorrente.

### INFO PRODOTTO ###
{product_info}

CONCEPT
{concept}

*** Regole del concept ***
- Serve esclusivamente come orientamento interno
- Non deve tradursi in formule testuali ricorrenti
- Non deve generare riferimenti espliciti a ispirazione
- Deve emergere indirettamente da materiali, costruzione e utilizzo

### STILE ###
- Apertura: descrittiva e assertiva
- Vietato aprire il testo con riferimenti a “ispirazione”
- Tono: tecnico–editoriale, brand–driven
- Linguaggio chiaro e dichiarativo
- Ammesse valutazioni soft (es. “ideale”, “perfetta”, “assicura”)
- Ammessi riferimenti a:
  - mondo outdoor
  - utilizzo urbano
  - capsule collection e collaborazioni (se presenti nelle INFO)
- Frasi complete
- Nessuna formattazione

### CONTENUTO ###
- Usa esclusivamente le informazioni presenti nelle INFO ARTICOLO
- Usa il tipo di calzatura fornito
Descrivi, seguendo l’ordine tipico Flower Mountain:
    - carattere del modello e destinazione d’uso (senza usare il termine “ispirazione”)
    - tomaia (materiali e costruzione overlapping se presente)
    - dettagli iconici (occhielli, nastri, loop, traforature)
    - chiusura (lacci trekking, quick stop se presente)
    - fodera e soletta (specificare materiali e trattamento se dichiarato)
    - fondo o suola (gomma ultra leggera, Vibram, megagrip, battistrada)

- I materiali devono essere citati in modo esplicito
- È ammessa la ripetizione di formule lessicali consolidate
- Non inserire la stagionalità del prodotto (il riferimento può essere solo sui sandali)
- NON usare abbreviazioni, ellissi o forme contratte (es. niente “-sohle”, “-lining”, ecc.)

### TERMINI E CONCETTI VIETATI ###
È vietato usare, anche in forma parafrasata:
- Vocazione
- La chiusura è affidata a
- costruzione minimale
- classici lacci
- lacci tradizionali
- sapientemente
- assicura proprietà antibatteriche
- bicolori
- "bicolore", utilizzabile solamente per il fondo se indicato.
- ispirazione
- ispirata / ispirato
- ispira / ispirare
- riferimenti espliciti al marchio
- Flower Mountain
- Stagione del prodotto (il riferimento può essere solo sui sandali/ciabatte)

### LESSICO GUIDA (AMMESSO E INCORAGGIATO) ###
- mondo outdoor
- utilizzo outdoor
- carattere outdoor
- vocazione sportiva
- design
- performance
- comfort e benessere
- costruzione overlapping
- lacci trekking / stringhe tecniche
- occhielli sagomati a fiore
- soletta in sughero naturale antibatterico / anatomica
- fondo in gomma ultra leggera
- battistrada dentellato
- Vibram / megagrip (se presente)

### LIMITI ###
- Non introdurre informazioni non presenti nelle INFO ARTICOLO
- Non inventare certificazioni o trattamenti
- Non usare metafore o storytelling emozionale
- Non descrivere abbinamenti di abbigliamento
- Non usare linguaggio lifestyle generico

### NORMALIZZAZIONE TIPO DI CALZATURA ###
- Usa esclusivamente il tipo di calzatura fornito.
- Mantieni la terminologia coerente con Flower Mountain
- Ammessi: sneaker, hiking shoe, stivaletto, slip on, ecc. se presenti nelle INFO
- "special case slippers" → SEMPRE trasformato in "ciabatte"

### OUTPUT ###
Genera due testi per ciascuna lingua:
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}

*** Uso delle descrizioni di riferimento ***
- Replicare struttura sintattica e ritmo
- Riutilizzare formule verbali consolidate
- Privilegiare costruzioni già presenti nello storico
- In caso di conflitto, lo stile delle descrizioni di riferimento ha priorità

### CONTROLLO FINALE ###
> Verifica che “ispirazione” e derivati NON siano presenti
    Se presenti, riscrivere la frase mantenendo il contenuto tecnico

> Il testo deve:
    - sembrare scritto per un catalogo ufficiale Flower Mountain
    - essere coerente con altri modelli simili
    - poter essere riutilizzato su più varianti colore
    - privilegiare coerenza e riconoscibilità rispetto all’unicità
    In caso contrario, riscrivere il testo mantenendo contenuto e ordine degli elementi.
"""
        elif marchio == "CC":
            prompt = f"""
Scrivi due descrizioni per una calzatura da vendere online (e-commerce), coerenti con le INFO ARTICOLO, in ciascuna delle seguenti lingue: {lang_list}.

Le descrizioni devono riprodurre il linguaggio di un catalogo ufficiale Candice Cooper: fashion–editoriale, metropolitano, raffinato, con struttura riconoscibile e lessico ricorrente.

### INFO PRODOTTO ###
{product_info}

CONCEPT
{concept}

*** Regole del concept ***
- Serve esclusivamente come orientamento interno
- Non deve tradursi in formule testuali ricorrenti
- Non deve generare riferimenti espliciti a ispirazioni, epoche o storytelling
- Deve emergere indirettamente da materiali, costruzione, dettagli e posizionamento del modello
- Il posizionamento urbano deve emergere indirettamente
  attraverso materiali, proporzioni, finiture e utilizzo quotidiano
- Evitare l’uso esplicito e ripetuto dei termini “metropolitano” e derivati

### STILE ###
- Apertura: evocativa e dichiarativa
- Vietato aprire il testo con riferimenti a “ispirazione”
- Tono: fashion–editoriale, premium, urbano
- Linguaggio fluido e descrittivo
- Ammesse valutazioni soft (es. “raffinata”, “essenziale”, “intramontabile”, “ideale”)
- Ammessi riferimenti a:
  - contesto urbano
  - glamour metropolitano
  - rilettura contemporanea di modelli iconici
- Frasi complete
- Nessuna formattazione

### CONTENUTO ###
- Usa esclusivamente le informazioni presenti nelle INFO ARTICOLO
- Usa il tipo di calzatura fornito

Descrivi, seguendo l’ordine tipico Candice Cooper:
    - carattere del modello e posizionamento estetico
    - tomaia (materiali, lavorazioni, finiture)
    - dettagli distintivi (rinforzi, bordo, impunture, piping, traforature, inserti)
    - chiusura (lacci, fibbia, zip, slip on se presente)
    - fodera e soletta (materiali, estraibilità, comfort)
    - fondo o suola (gomma, profilo che risale il tallone, disegno se dichiarato)

- I materiali devono essere citati in modo esplicito
- È ammessa la ripetizione di formule lessicali consolidate
- Non inserire stagionalità del prodotto
- NON usare abbreviazioni, ellissi o forme contratte

### TERMINI E CONCETTI VIETATI ###
È vietato usare, anche in forma parafrasata:
- vocazione
- performance
- mondo outdoor
- utilizzo outdoor
- tecnico / tecnicità
- costruzione minimale
- sapientemente
- assicura proprietà antibatteriche (se non esplicitamente dichiarate)
- ispirazione
- ispirata / ispirato
- ispira / ispirare
- riferimenti espliciti ad altri marchi
- Candice Cooper
- stagionalità del prodotto

### LESSICO GUIDA (AMMESSO E INCORAGGIATO) ###
- design intramontabile
- raffinatezza
- essenziale
- urbano
- city chic
- glamour
- vintage reinterpretato
- materiali sofisticati
- pelle / suede / velour / vitello
- pelle tamponata / invecchiata / metallizzata / laminata (se presenti)
- comfort
- calzata confortevole
- soletta interna estraibile / ergonomica (se dichiarato)
- suola in gomma
- profilo che risale il tallone
- bordo avvolgente
- impunture a vista
- rinforzi su punta e tallone

### LIMITI ###
- Non introdurre informazioni non presenti nelle INFO ARTICOLO
- Non inventare trattamenti, lavorazioni o certificazioni
- Non usare metafore o storytelling emozionale
- Non descrivere abbinamenti di abbigliamento
- Non usare linguaggio lifestyle generico

### NORMALIZZAZIONE TIPO DI CALZATURA ###
- Usa esclusivamente il tipo di calzatura fornito
- Mantieni terminologia coerente con Candice Cooper
- Ammessi: sneaker, sneaker low rise, sneaker mid rise, sandalo, ballerina, mocassino, stivaletto, slip on se presenti nelle INFO
- “special case slippers” → SEMPRE trasformato in “ciabatte”

### OUTPUT ###
Genera due testi per ciascuna lingua:
- desc_lunga: {desc_lunga_length} parole
- desc_breve: {desc_breve_length} parole

### DESCRIZIONI DI RIFERIMENTO ###
{sim_text}

*** Uso delle descrizioni di riferimento ***
- Replicare struttura sintattica e ritmo
- Riutilizzare formule verbali consolidate
- Privilegiare costruzioni già presenti nello storico
- In caso di conflitto, lo stile delle descrizioni di riferimento ha priorità

### CONTROLLO FINALE ###
> Verifica che “ispirazione” e derivati NON siano presenti  
  Se presenti, riscrivere la frase mantenendo il contenuto descrittivo

> Il testo deve:
    - sembrare scritto per un catalogo ufficiale Candice Cooper
    - risultare coerente con altri modelli della collezione
    - poter essere riutilizzato su più varianti colore
    - privilegiare coerenza editoriale e riconoscibilità rispetto all’unicità
    In caso contrario, riscrivere il testo mantenendo contenuto e ordine degli elementi.
"""
    return prompt

client = AsyncOpenAI(api_key=openai.api_key)

# Configurazione per il piano gratuito
RPS_LIMIT = 1  # 1 richiesta al secondo per il piano gratuito
RPS_LIMIT_DEEPSEEK = 20 # Prova per deepseek
MAX_RETRIES = 3  # Numero massimo di tentativi per ogni richiesta
DELAY_BETWEEN_REQUESTS = 1  # 1 secondo tra una richiesta e l'altra
TOKEN_WINDOW = deque()  # (timestamp, token_count)
MAX_TOKENS_PER_MINUTE = 500000

def check_token_limit(tokens: int) -> bool:
    current_time = time.time()
    # Rimuovi i record più vecchi di 60 secondi
    while TOKEN_WINDOW and current_time - TOKEN_WINDOW[0][0] > 60:
        TOKEN_WINDOW.popleft()

    total_tokens = sum(count for _, count in TOKEN_WINDOW)
    if total_tokens + tokens > MAX_TOKENS_PER_MINUTE:
        return False  # Limite superato

    TOKEN_WINDOW.append((current_time, tokens))
    return True

# -----------------------------
# RATE LIMITER (20 richieste/min)
# -----------------------------
MAX_REQUESTS_PER_MIN = RPS_LIMIT_DEEPSEEK
request_times = deque()

async def rate_limiter():
    """Assicura che non vengano fatte più di MAX_REQUESTS_PER_MIN richieste in 60s."""
    now = time.time()
    # Rimuove timestamp più vecchi di 60s
    while request_times and now - request_times[0] > 60:
        request_times.popleft()

    if len(request_times) >= MAX_REQUESTS_PER_MIN:
        sleep_for = 60 - (now - request_times[0])
        st.warning(f"⏳ Rate limit raggiunto. Attendo {sleep_for:.1f}s...")
        await asyncio.sleep(sleep_for)
        # Dopo l'attesa, aggiorna il deque
        now = time.time()
        while request_times and now - request_times[0] > 60:
            request_times.popleft()

    # Registra questa richiesta
    request_times.append(time.time())


async def async_generate_description(prompt: str, idx: int, use_model: str, lang):
    temperature = random.uniform(0.9, 1.2)
    presence_penalty = random.uniform(0.4, 0.8)
    functions = build_function_schema(lang)

    if prompt == "SaltaRiga":
        return idx, {"Continuativo": "Si"}
        
    if len(prompt) < 50:
        return idx, {
            "result": prompt,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0}
        }
        
    try:
        response = await client.chat.completions.create(
            model=use_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            top_p=0.95,
            frequency_penalty=0.4,
            presence_penalty=presence_penalty,
            max_tokens=3000,
            functions=functions,
            function_call={"name": "generate_product_descriptions"},
        )
        
        content = response.choices[0].message.content
        message = response.choices[0].message
        usage = response.usage

        if message.function_call:
            data = json.loads(message.function_call.arguments)
            
        return idx, {"result": data, "usage": usage.model_dump()}
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
        simili=simili,
        marchio=marchio
    )

    # Token estimation (~4 chars per token)
    num_chars = len(prompt)
    token_est = num_chars // 4
    cost_est = round(token_est / 1000 * 0.001, 6)

    if DEBUG:
        st.code(prompt)
        st.markdown(f"📊 **Prompt Length**: {num_chars} caratteri ≈ {token_est} token")
        st.markdown(f"💸 **Costo stimato per riga**: ${cost_est:.6f}")

    return token_est, cost_est, prompt
        
# ---------------------------
# Funzioni varie
# ---------------------------
AVAILABLE_LANGS = ["en", "fr", "de", "es"]
OPENAI_MODEL = "gpt-4o-mini"
SAVE_TRANSLATE_EVERY = 25  # batch size consigliato

# =========================
# MANUAL OVERRIDES
# =========================
MANUAL_TRANSLATIONS = {
    "strappo": {
        "es": "cierre adherente",
        "fr": "scratch",
        "en": "strap",
        "de": "klettverschluss"
    }
}
MANUAL_TRANSLATIONS_PROMPT = """
IMPORTANTE:
Alcune parole devono seguire regole fisse:
- "strappo" -> {"en": "strap", "fr": "scratch", "es": "cierre adherente", "de": "klettverschluss"}
- "sneakers" -> {"en": "sneakers", "fr": "sneakers", "es": "sneakers"}
"""

# =========================
# UTILS
# =========================
def normalize(text: str) -> str:
    return text.strip().lower()
    
def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.create_task(coro)

def safe_json_loads(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # cerca il primo blocco JSON {...}
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        # se non trova JSON valido, fallback con traduzione originale in tutte le lingue
        return {lang: text for lang in ["en", "fr", "de", "es"]}

def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"

def vocab_to_rows(vocab):
    rows = []
    for it_key, langs in vocab.items():
        row = [
            it_key,
            langs.get("en", ""),
            langs.get("fr", ""),
            langs.get("de", ""),
            langs.get("es", "")
        ]
        rows.append(row)
    return rows

def append_vocab_rows(ws, rows):
    """
    rows = lista di dict {"it": ..., "en": ..., "fr": ..., "de": ..., "es": ...}
    """
    values = []
    for r in rows:
        values.append([
            r.get("it", ""),
            r.get("en", ""),
            r.get("fr", ""),
            r.get("de", ""),
            r.get("es", ""),
            r.get("source_col", "")
        ])

    if values:
        ws.append_rows(values, value_input_option="RAW")
        
# =========================
# VOCABULARY
# =========================
def worksheet_to_df(ws):
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)
    
def load_vocab(sheet_id, tab):
    ws = get_sheet(sheet_id, tab)
    df = worksheet_to_df(ws)
    df.columns = [c.strip().lower() for c in df.columns]
    
    vocab = {}

    if df.empty:
        return vocab, ws

    for _, row in df.iterrows():
        it = str(row["it"]).strip()

        vocab[it] = {
            lang: row.get(lang)
            for lang in row.index
            if lang != "it" and pd.notna(row.get(lang))
        }

    return vocab, ws


def vocab_to_df(vocab):
    rows = []
    for it, langs in vocab.items():
        row = {"it": it}
        row.update(langs)
        rows.append(row)
    return pd.DataFrame(rows)


# =========================
# OPENAI TRANSLATION
# =========================
async def translate_term(client, term, target_langs, col_name):
    important_note = ""
    if col_name and "colore" in col_name.lower():
        important_note = (
            "IMPORTANTE: Il termine è un colore o una combinazione di colori, se contiene un trattino, "
            "traduci ciascuna parte separatamente e mantieni il trattino.\n"
        )
        
    messages = [
        {"role": "user", "content": f"""
        Traduci questo testo italiano nelle lingue: {', '.join(target_langs)}.
        Mantieni maiuscole e punteggiatura come nell'originale.
        NON usare abbreviazioni, ellissi o forme contratte (es. niente “-sohle”, “-lining”, ecc.)
        {important_note}
        
        Testo da tradurre:
        \"\"\"{term}\"\"\"
        
        {MANUAL_TRANSLATIONS_PROMPT}
        
        Rispondi SOLO in JSON valido nel formato:
        {{
          "en": "...",
          "fr": "...",
          "de": "...",
          "es": "..."
        }}
        """}
    ]

    functions = [
        {
            "name": "translate_text",
            "description": "Traduci il testo italiano nelle lingue specificate, mantenendo maiuscole, punteggiatura e nomi propri",
            "parameters": {
                "type": "object",
                "properties": {lang: {"type": "string"} for lang in target_langs},
                "required": target_langs
            }
        }
    ]

    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        functions=functions,
        function_call={"name": "translate_text"},
        temperature=0
    )

    message = response.choices[0].message  # ChatCompletionMessage object

    # Accesso corretto a function_call
    func_call = getattr(message, "function_call", None)
    if func_call and hasattr(func_call, "arguments"):
        return json.loads(func_call.arguments)

    # fallback in caso di errore
    return {lang: term for lang in target_langs}


async def enrich_vocab_with_ui(
    client,
    vocab,
    missing_terms,
    target_langs,
    progress_bar,
    status_text,
    timer_text,
    ws,
    saved_badge
):
    total = len(missing_terms)
    start_time = time.time()
    buffer = []
    saved_count = 0

    #for i, term in enumerate(missing_terms, start=1):
    for i, (term, col_name) in enumerate(missing_terms.items(), start=1):
        #key = term.strip().lower()  # normalizzazione chiave
        key = term.strip()

        # TIMER E PROGRESS BAR
        elapsed = time.time() - start_time
        avg_time = elapsed / i
        remaining = avg_time * (total - i)

        progress_bar.progress(i / total)
        saved_badge.markdown(f"💾 **Salvate su Google:** {saved_count}")
        status_text.text(f"🔤 Traduzione: {term} ({i}/{total})")
        timer_text.text(
            f"⏱️ Trascorso: {format_time(elapsed)} | "
            f"Stimato: {format_time(remaining)}"
        )

        # OVERRIDE MANUALE
        if key in MANUAL_TRANSLATIONS:
            vocab[key] = {lang: MANUAL_TRANSLATIONS[key].get(lang, term) for lang in target_langs}
            continue

        # CHIAMATA GPT FUNCTION CALL
        try:
            translations = await translate_term(client, term, target_langs, col_name)
            vocab[key] = translations
        except Exception as e:
            st.warning(f"Errore traduzione '{term}': {e}")
            # fallback: testo originale in tutte le lingue
            #vocab[key] = {lang: term for lang in target_langs}
            vocab[key] = {lang: "" for lang in target_langs}

        buffer.append({
            "it": key,
            **vocab[key],
            "source_col": col_name
        })
        
        if len(buffer) >= SAVE_TRANSLATE_EVERY:
            append_vocab_rows(ws, buffer)
            saved_count += len(buffer)
            saved_badge.markdown(f"💾 **Salvate su Google:** {saved_count}")
            buffer.clear()

    if buffer:
        append_vocab_rows(ws, buffer)
        saved_count += len(buffer)
        saved_badge.markdown(f"💾 **Salvate su Google:** {saved_count}")

# =========================
# CSV TRANSLATION
# =========================
def extract_missing_terms(df, columns, vocab):
    #missing = set()
    missing = {}

    for col in columns:
        for value in df[col].dropna():
            key = str(value).strip()  # ✅ NON più .lower()
            if key not in vocab and key not in MANUAL_TRANSLATIONS:
                missing[key] = col

    return missing

LANG_RE = re.compile(r"\(([^)]+)\)$")

def get_base_name(col):
    # "Variante (it)" -> "Variante"
    return LANG_RE.sub("", col).strip()

def get_lang(col):
    m = LANG_RE.search(col)
    return m.group(1).lower() if m else None

def apply_translations(df, columns, langs, vocab):
    """
    Ritorna dict {lang: df}
    - Esclude righe che nel CSV originale hanno valore popolato nella colonna dopo
      una colonna selezionata (it)
    """
    dfs_by_lang = {}

    # colonne base selezionate (Variante, Colore, ecc.)
    selected_bases = {get_base_name(c) for c in columns}

    # ------------------------
    # TROVA RIGHE DA ESCLUDERE
    # ------------------------
    rows_to_drop = set()
    col_list = list(df.columns)
    for idx, col in enumerate(col_list):
        base = get_base_name(col)
        lang = get_lang(col)

        # solo colonne selezionate (it)
        if base in selected_bases and lang == "it":
            # colonna successiva
            if idx + 1 < len(col_list):
                next_col = col_list[idx + 1]
                next_lang = get_lang(next_col)
                # se la colonna successiva NON-it e popolata → scarta riga
                if next_lang != "it":
                    populated_rows = df[next_col].notna() & (df[next_col].astype(str).str.strip() != "")
                    rows_to_drop.update(df.index[populated_rows])

    # ------------------------
    # CREAZIONE CSV PER OGNI LINGUA
    # ------------------------
    for lang in langs:
        df_lang = df.copy()

        # elimina righe da scartare
        if rows_to_drop:
            df_lang.drop(index=list(rows_to_drop), inplace=True)

        # traduzioni e rinomina colonne
        for col in df_lang.columns:
            col_lang = get_lang(col)
            base = get_base_name(col)

            # colonne senza lingua o colonne (it) → lasciale così
            if not col_lang or col_lang == "it":
                continue

            # colonne selezionate → traduci
            if base in selected_bases:
                it_col = col.replace(f"({col_lang})", "(it)")
                if it_col in df_lang.columns:
                    def translate_cell(val):
                        if pd.isna(val):
                            return ""
                        key = str(val).strip()
                        return vocab.get(key, {}).get(lang, key)
                    df_lang[col] = df_lang[it_col].apply(translate_cell)
                else:
                    df_lang[col] = df_lang[col].fillna("")
            else:
                df_lang[col] = df_lang[col]

            # rinomina colonna con lingua corrente
            new_col = re.sub(LANG_RE, f"({lang})", col)
            df_lang.rename(columns={col: new_col}, inplace=True)

        dfs_by_lang[lang] = df_lang

    return dfs_by_lang
