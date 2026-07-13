import asyncio
import aiohttp
import os
import json
import gspread
from google.oauth2.service_account import Credentials
import time
import random

# -------------------------------
# CONFIGURAZIONE (Modifica questi dati)
# -------------------------------
SHEET_ID = "1JW30e-RF2WREWe96Qj-M_zVtjqbvg3ZhRgXuY2E5CqU"
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON") # Assicurati che l'env var sia settata

FOGLIO = "Foglio6" # Nome del tab/foglio

# Impostazione Colonne (usa le lettere)
COLONNA_SKU = "E"       # Colonna da cui leggere la SKU
COLONNA_OUTPUT = "B"    # Colonna dove scrivere SI/NO

# URL Template: usa {sku} dove deve essere iniettata la sku. 
# Se la SKU deve essere minuscola nell'url, l'ho gestito sotto nel codice.
URL_TEMPLATE = "https://repository.falc.biz/fal001{sku}-2.jpg"

MAX_CONCURRENT = 40
TIMEOUT_SECONDS = 10

# -------------------------------
# UTILS & AUTH
# -------------------------------
def gsheets_retry(max_retries=6, initial_delay=5, backoff_factor=2):
    """Decorator per gestire i retry sulle chiamate Google Sheets API."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries, delay = 0, initial_delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except gspread.exceptions.APIError as e:
                    code = getattr(e.response, 'status_code', None)
                    if code in [429, 500, 502, 503, 504] or code is None:
                        retries += 1
                        sleep_time = delay + random.uniform(0, 2)
                        print(f"⚠️ API Error {code}. Retry {retries}/{max_retries} in {sleep_time:.2f}s...")
                        time.sleep(sleep_time)
                        delay *= backoff_factor
                    else:
                        raise
            return func(*args, **kwargs)
        return wrapper
    return decorator

def col2num(col_letter):
    """Converte una lettera di colonna in numero (A -> 1, B -> 2) per gspread"""
    num = 0
    for c in col_letter.upper():
        num = num * 26 + (ord(c) - ord('A')) + 1
    return num

# Autenticazione Google Sheets
try:
    credentials = Credentials.from_service_account_info(
        json.loads(SERVICE_ACCOUNT_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gs_client = gspread.authorize(credentials)
except Exception as e:
    print(f"❌ Errore di autenticazione con le credenziali JSON: {e}")
    exit(1)

@gsheets_retry()
def get_worksheet():
    return gs_client.open_by_key(SHEET_ID).worksheet(FOGLIO)

@gsheets_retry()
def batch_update_colonna(worksheet, range_name, values):
    """Aggiorna una singola colonna con i risultati"""
    return worksheet.update(range_name, values)

# -------------------------------
# CORE LOGIC
# -------------------------------
async def check_url(sku: str, sem: asyncio.Semaphore, session: aiohttp.ClientSession) -> str:
    """Verifica l'esistenza dell'immagine restituendo 'SI' o 'NO'."""
    if not sku.strip():
        return "" # Lascia vuoto se la cella SKU è vuota

    # Genera l'URL (qui formatto la sku in minuscolo come nel tuo script originale)
    url = URL_TEMPLATE.format(sku=sku.strip().lower())
    
    async with sem:
        try:
            # Usiamo una GET ma non scarichiamo il contenuto, controlliamo solo lo status.
            # Questo rende lo script fulmineo.
            async with session.get(url, timeout=TIMEOUT_SECONDS) as resp:
                if resp.status == 200:
                    return "SI"
                else:
                    return "NO"
        except Exception:
            return "NO"

async def process_skus(skus: list) -> list:
    """Elabora tutte le SKU in parallelo."""
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    risultati = []
    
    async with aiohttp.ClientSession() as session:
        tasks = [check_url(sku, sem, session) for sku in skus]
        # await asyncio.gather mantiene l'ordine esatto dell'input!
        risultati = await asyncio.gather(*tasks)
        
    return risultati

# -------------------------------
# MAIN
# -------------------------------
async def main():
    print(f"🚀 Avvio workflow controllo foto manuale...")
    
    # 1. Recupero dati foglio
    try:
        worksheet = get_worksheet()
        col_sku_num = col2num(COLONNA_SKU)
        
        # Scarichiamo SOLO la colonna delle SKU (molto più leggero)
        print(f"📥 Download colonna SKU ({COLONNA_SKU})...")
        skus_column = worksheet.col_values(col_sku_num)
        
    except Exception as e:
        print(f"❌ Errore caricamento foglio: {e}")
        return

    if len(skus_column) <= 1:
        print("⚠️ Nessuna SKU trovata oltre all'intestazione.")
        return

    # Escludiamo l'intestazione (riga 1)
    skus_da_processare = skus_column[1:]
    totale = len(skus_da_processare)
    print(f"🔍 Trovate {totale} SKU da elaborare.")

    # 2. Controllo URLs in asincrono
    print(f"⚡ Controllo dell'esistenza delle foto in corso (max {MAX_CONCURRENT} in parallelo)...")
    risultati = await process_skus(skus_da_processare)
    
    # 3. Preparazione dati per Google Sheets
    # Formattiamo i risultati in una lista di liste come richiesto da gspread (es: [["SI"], ["NO"], ...])
    output_data = [[res] for res in risultati]
    
    # Creiamo il range esatto dove scrivere (es: K2:K100)
    range_output = f"{COLONNA_OUTPUT}2:{COLONNA_OUTPUT}{len(output_data) + 1}"
    
    # 4. Scrittura sul foglio
    print(f"⏳ Scrittura dei risultati nel range {range_output}...")
    try:
        batch_update_colonna(worksheet, range_output, output_data)
        print(f"✅ Fatto! Colonna {COLONNA_OUTPUT} aggiornata con successo con {totale} risultati.")
    except Exception as e:
        print(f"❌ Errore durante il caricamento dei risultati: {e}")

if __name__ == "__main__":
    asyncio.run(main())
