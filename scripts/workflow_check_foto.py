import asyncio
import aiohttp
import os
import json
import gspread
import io
import hashlib
import imagehash
from PIL import Image, ImageChops
from datetime import datetime
from typing import List, Dict
from google.oauth2.service_account import Credentials
import dropbox
from dropbox.files import WriteMode
from skimage.metrics import structural_similarity as ssim
import numpy as np
import time
import random

# -------------------------------
# CONFIG
# -------------------------------
SHEET_ID = os.environ.get("FOTO_GSHEET_ID")
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")

FOGLIO = "LISTA"
MAX_CONCURRENT = 40
RETRY_LIMIT = 3
TIMEOUT_SECONDS = 10

# -------------------------------
# AUTENTICAZIONE
# -------------------------------
credentials = Credentials.from_service_account_info(
    json.loads(SERVICE_ACCOUNT_JSON),
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs_client = gspread.authorize(credentials)
dbx = dropbox.Dropbox(
    oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
    app_key=DROPBOX_APP_KEY,
    app_secret=DROPBOX_APP_SECRET
)

# -------------------------------
# UTILS
# -------------------------------
def gsheets_retry(max_retries=6, initial_delay=5, backoff_factor=2):
    """Decorator per gestire i retry sulle chiamate Google Sheets API."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except gspread.exceptions.APIError as e:
                    code = getattr(e.response, 'status_code', None)
                    if code in [429, 500, 502, 503, 504] or code is None:
                        retries += 1
                        if retries == max_retries:
                            print(f"❌ Raggiunto il limite di retry per {func.__name__}")
                            raise
                        sleep_time = delay + random.uniform(0, 2)
                        print(f"⚠️ Google Sheets API Error {code}. Retry {retries}/{max_retries} in {sleep_time:.2f}s...")
                        time.sleep(sleep_time)
                        delay *= backoff_factor
                    else:
                        raise
                except Exception as e:
                    retries += 1
                    if retries == max_retries:
                        raise
                    sleep_time = delay + random.uniform(0, 2)
                    print(f"⚠️ Errore imprevisto {type(e).__name__}: {e}. Retry {retries}/{max_retries} in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    delay *= backoff_factor
            return func(*args, **kwargs)
        return wrapper
    return decorator

@gsheets_retry()
def get_worksheet(sheet_id, tab_name):
    return gs_client.open_by_key(sheet_id).worksheet(tab_name)

@gsheets_retry()
def get_values_optimized(worksheet, range_name="A:P"):
    """Recupera i valori solo per il range necessario per ridurre il carico."""
    return worksheet.get(range_name)

@gsheets_retry()
def batch_update_with_retry(worksheet, data):
    return worksheet.batch_update(data)

@gsheets_retry()
def clear_sheet_with_retry(worksheet):
    return worksheet.clear()

@gsheets_retry()
def update_sheet_with_retry(worksheet, range_name, values):
    return worksheet.update(range_name, values)

def get_dropbox_latest_image(sku: str) -> (str, str, Image.Image):
    folder_path = f"/repository/{sku}"
    try:
        res = dbx.files_list_folder(folder_path)
        jpgs = sorted(
            [entry for entry in res.entries if entry.name.lower().endswith(".jpg")],
            key=lambda e: e.client_modified,
            reverse=True
        )
        if not jpgs:
            return None, None, None
        latest = jpgs[0]
        _, resp = dbx.files_download(latest.path_display)
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        return latest.name, latest.client_modified.strftime("%d%m%Y"), img
    except dropbox.exceptions.ApiError:
        return None, None, None
    except Exception as e:
        print(f"⚠️ Errore Dropbox per {sku}: {e}")
        return None, None, None

def save_image_to_dropbox(sku: str, filename: str, image: Image.Image):
    folder_path = f"/repository/{sku}"
    file_path = f"{folder_path}/{filename}"

    img_bytes = io.BytesIO()
    image.save(img_bytes, format="JPEG")
    img_bytes.seek(0)

    try:
        dbx.files_create_folder_v2(folder_path)
    except dropbox.exceptions.ApiError:
        pass

    dbx.files_upload(img_bytes.read(), file_path, mode=WriteMode("overwrite"))

def hashdiff(img1: Image.Image, img2: Image.Image):
    hash1 = imagehash.phash(img1)
    hash2 = imagehash.phash(img2)
    return hash1 - hash2

def ssim_similarity(img1, img2):
    img1 = np.array(img1.resize((256, 256)).convert("L"))
    img2 = np.array(img2.resize((256, 256)).convert("L"))
    score, _ = ssim(img1, img2, full=True)
    return score

def mse(img1, img2):
    arr1 = np.array(img1.resize((256, 256)).convert("L"))
    arr2 = np.array(img2.resize((256, 256)).convert("L"))
    return np.mean((arr1 - arr2) ** 2)

async def check_photo(sku: str, riscattare: str, sem: asyncio.Semaphore, session: aiohttp.ClientSession) -> (str, bool, bool):
    url = f"https://repository.falc.biz/fal001{sku.lower()}-1.jpg"
    async with sem:
        try:
            async with session.get(url, timeout=TIMEOUT_SECONDS, allow_redirects=True) as get_resp:
                if get_resp.status == 200:
                    img_bytes = await get_resp.read()
                    new_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    foto_salvata = False
                    
                    if riscattare == "true" or riscattare == "check":
                        old_name, old_date, old_img = get_dropbox_latest_image(sku)
                        if old_img:
                            h_diff = hashdiff(new_img, old_img)
                            s_sim = ssim_similarity(new_img, old_img)
                            m_err = mse(new_img, old_img)
                        else:
                            h_diff, s_sim, m_err = 5, 0, 100

                        if not old_img or (h_diff >= 0 and s_sim < 0.998 and m_err > 1.5):
                            if old_name:
                                ext = old_name.split(".")[-1]
                                new_old_name = f"{sku}_{old_date}.{ext}"
                                try:
                                    dbx.files_move_v2(
                                        from_path=f"/repository/{sku}/{old_name}",
                                        to_path=f"/repository/{sku}/{new_old_name}",
                                        allow_shared_folder=True,
                                        autorename=True
                                    )
                                except Exception as e:
                                    print(f"⚠️ Errore rinominando {old_name}: {e}")
                            save_image_to_dropbox(sku, f"{sku}.jpg", new_img)
                            foto_salvata = True

                    return sku, False, foto_salvata
                else:
                    return sku, True, False
        except Exception:
            return sku, True, False

async def process_skus(data_rows: List[List[str]], sku_idx: int, riscattare_idx: int) -> (Dict[str, tuple], int):
    results = {}
    foto_salvate = 0
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for row in data_rows:
            if len(row) > max(sku_idx, riscattare_idx):
                sku = row[sku_idx].strip()
                riscattare = row[riscattare_idx].strip().lower()
                if sku:
                    tasks.append(check_photo(sku, riscattare, sem, session))
        
        for coro in asyncio.as_completed(tasks):
            try:
                sku_res, mancante, salvata = await coro
                results[sku_res] = (mancante, salvata)
                if salvata:
                    foto_salvate += 1    
            except Exception:
                pass
    return results, foto_salvate

async def retry_until_complete(data_rows, sku_idx, riscattare_idx) -> (Dict[str, tuple], int):
    checked = {}
    foto_salvate_totali = 0
    for attempt in range(RETRY_LIMIT):
        pending = [row for row in data_rows if row[sku_idx].strip() not in checked]
        if not pending:
            break
        print(f"🔄 Elaborazione di {len(pending)} SKU (Tentativo {attempt+1}/{RETRY_LIMIT})")
        partial, salvate = await process_skus(pending, sku_idx, riscattare_idx)
        checked.update(partial)
        foto_salvate_totali += salvate
    return checked, foto_salvate_totali

def get_val(row, idx):
    return row[idx].strip() if len(row) > idx else ""

# -------------------------------
# MAIN
# -------------------------------
async def main():
    print(f"🚀 Avvio workflow check foto sul foglio {FOGLIO}")
    
    try:
        lista_worksheet = get_worksheet(SHEET_ID, FOGLIO)
        all_data = get_values_optimized(lista_worksheet, "A:P")
    except Exception as e:
        print(f"❌ Impossibile caricare il foglio LISTA: {e}")
        return

    if len(all_data) < 2:
        print("❌ Foglio vuoto o intestazione mancante.")
        return

    header = all_data[0]
    rows = all_data[1:]

    try:
        sku_idx = header.index("SKU")
        riscattare_idx = header.index("RISCATTARE")
        consegnata_idx = header.index("CONSEGNATA")
    except ValueError:
        sku_idx, riscattare_idx, consegnata_idx = 0, 11, 15
        print(f"⚠️ Indici colonne non trovati, uso default: SKU={sku_idx}, RISCATTARE={riscattare_idx}, CONSEGNATA={consegnata_idx}")

    print(f"🔍 Righe da elaborare: {len(rows)}")
    results, tot_foto_salvate = await retry_until_complete(rows, sku_idx, riscattare_idx)
    
    output_col_k, output_col_l = [], []
    
    for row in rows:
        sku = get_val(row, sku_idx)
        mancante, salvata = results.get(sku, (True, False))
        output_col_k.append([str(mancante)])
    
        val_riscattare = get_val(row, riscattare_idx).lower()
        val_consegnata = get_val(row, consegnata_idx).lower()
        
        if salvata:
            if val_riscattare == "true":
                if val_consegnata == "true":
                    output_col_l.append(["Check"])
                else:
                    output_col_l.append(["True"])
            else:
                output_col_l.append([""])
        else:
            if val_riscattare == "true":
                output_col_l.append(["Check" if val_consegnata == "true" else "True"])
            elif val_riscattare == "check":
                output_col_l.append(["Check"])
            else:
                output_col_l.append([""])
    
    print("⏳ Aggiornamento Google Sheet...")
    try:
        batch_update_with_retry(lista_worksheet, [
            {"range": f"K2:K{len(output_col_k)+1}", "values": output_col_k},
            {"range": f"L2:L{len(output_col_l)+1}", "values": output_col_l}
        ])
        print("✅ Google Sheet 'LISTA' aggiornato")
    except Exception as e:
        print(f"⚠️ Errore durante l'aggiornamento del foglio LISTA: {e}")

    # Aggiornamento Foglio URGENZE
    URGENZE_SHEET_ID = "1YbU9twZgJECIsbxhRft-7yGGuH37xzVdOkz7jJIL5aQ"
    try:
        all_data_updated = get_values_optimized(lista_worksheet, "A:P")
        rows_updated = all_data_updated[1:]
        
        is_t = lambda v: str(v).strip().upper() in ["TRUE", "VERO", "1"]
        is_f = lambda v: str(v).strip().upper() in ["FALSE", "FALSO", "0", ""]

        nuovi_sku_foto = []
        for r_upd in rows_updated:
            k, m, n, o, p = get_val(r_upd, 10), get_val(r_upd, 12), get_val(r_upd, 13), get_val(r_upd, 14), get_val(r_upd, 15)
            if is_t(k) and is_f(m) and is_f(n) and is_f(o) and is_f(p):
                sku = get_val(r_upd, 0)
                if sku: nuovi_sku_foto.append([sku, "FOTO"])

        urg_worksheet = get_worksheet(URGENZE_SHEET_ID, "URGENZE")
        dat_esistenti = get_values_optimized(urg_worksheet, "A:B")
        
        lista_finale = [[ "SKU", "TIPO" ]]
        if dat_esistenti: lista_finale = [dat_esistenti[0]]
        
        for r in dat_esistenti[1:]:
            if len(r) >= 2 and r[1] != "FOTO" and r[0].strip():
                lista_finale.append(r)
            elif len(r) == 1 and r[0].strip():
                lista_finale.append(r)

        lista_finale.extend(nuovi_sku_foto)
        clear_sheet_with_retry(urg_worksheet)
        update_sheet_with_retry(urg_worksheet, "A1", lista_finale)
        print(f"🚀 Foglio URGENZE aggiornato. Nuovi SKU 'FOTO': {len(nuovi_sku_foto)}")
    except Exception as e:
        print(f"⚠️ Errore foglio URGENZE: {e}")
    
if __name__ == "__main__":
    asyncio.run(main())
