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
    #incipit_seeds = ["SEO-oriented", "Descrittivo", "Pratico", "Classico", "Informativo", "Accattivante"]
    incipit_seeds = [
        "Inizia direttamente con il tipo di calzatura come soggetto grammaticale, seguito da una caratteristica materica o costruttiva (es: 'La sneaker si presenta con tomaia in...' / 'Il mocassino unisce...')",
        "Inizia con uno o due aggettivi visivi o sensoriali seguiti dal tipo di calzatura (es: 'Morbida e avvolgente, la scarpina...' / 'Essenziale e pulita, questa scarpa...')",
        "Inizia con il materiale principale della tomaia come punto di partenza narrativo (es: 'In pelle liscia dal colore...' / 'Tomaia in nabuk con...')",
        "Inizia con un verbo alla terza persona singolare che descrive una qualità visiva o fisica del prodotto (es: 'Si distingue per la tomaia in...' / 'Scintilla ad ogni passo...')",
        "Inizia con una costruzione nominale che descrive la forma o il profilo del modello (es: 'Linee pulite e tomaia in...' / 'Profilo basso e costruzione...')",
        "Inizia con il nome del tipo di calzatura preceduto da un articolo determinativo, presentandolo come elemento di riferimento della categoria (es: 'La ballerina classica si rinnova con...' / 'Il sandalo si caratterizza per...')",
        "Inizia con due sostantivi astratti legati da 'e' che evocano le qualità del prodotto, seguiti dal tipo di calzatura (es: 'Forma e funzione si incontrano in questa...' / 'Semplicità e cura del dettaglio per...')",
        "Inizia con una frase breve che descrive il colore o l'aspetto visivo d'insieme del prodotto (es: 'Un tono caldo e naturale caratterizza...' / 'Il colore deciso della tomaia...')",
        "Inizia con un participio presente o passato riferito alla calzatura, che introduce subito una caratteristica fisica (es: 'Realizzata interamente in pelle, questa...' / 'Costruita su una suola flessibile...')",
        "Inizia riprendendo liberamente il concept come suggestione visiva o di contesto, senza citarlo, per introdurre il prodotto (es: se il concept evoca leggerezza, aprire con 'Dal passo leggero e...' / se evoca classicità, aprire con 'Nel rispetto di una linea essenziale...')",
    ]

    # Fallback to general prompt if no specific brand logic is found
    # (Keeping the structure from app_old.py but removing image-specific lines)

    if marchio in bambino:
        prompt = f"""Scrivi due descrizioni per una calzatura per bambini da vendere online (e-commerce), coerenti con le INFO ARTICOLO, in ciascuna delle seguenti lingue: {lang_list}.

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
- bicolore / bicolori / multicolore / multicolori
- le sneakers si impongono
- terreni insidiosi
- morbido colore 
- stagione fredda
- linee eleganti
- linee moderne

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
- "boots" → SEMPRE trasformato in "stivali"
- "ankle boots" → SEMPRE trasformato in "stivali alla caviglia"
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
