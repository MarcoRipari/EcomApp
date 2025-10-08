import streamlit as st
import io
import base64
import requests
import dropbox
from dropbox.files import WriteMode
from zoneinfo import ZoneInfo

def get_dropbox_access_token():
    refresh_token = st.secrets["DROPBOX_REFRESH_TOKEN"]
    client_id = st.secrets["DROPBOX_CLIENT_ID"]
    client_secret = st.secrets["DROPBOX_CLIENT_SECRET"]

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    response = requests.post(
        "https://api.dropbox.com/oauth2/token",
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]

def get_dropbox_client():
    access_token = get_dropbox_access_token()
    return dropbox.Dropbox(access_token)

def upload_csv_to_dropbox(dbx, folder_path: str, file_name: str, file_bytes: bytes):
    dbx_path = f"{folder_path}/{file_name}"
    try:
        dbx.files_create_folder_v2(folder_path)
    except dropbox.exceptions.ApiError:
        pass  # cartella già esiste
    try:
        dbx.files_upload(file_bytes, dbx_path, mode=WriteMode("overwrite"))
        
        st.success(f"✅ CSV caricato su Dropbox: {dbx_path}")
    except Exception as e:
        st.error(f"❌ Errore caricando CSV su Dropbox: {e}")

def download_csv_from_dropbox(dbx, folder_path: str, file_name: str) -> io.BytesIO:
    file_path = f"{folder_path}/{file_name}"

    try:
        metadata, res = dbx.files_download(file_path)
        return io.BytesIO(res.content), metadata
    except dropbox.exceptions.ApiError as e:
        # Se l'errore è 'path/not_found' -> file mancante
        if (hasattr(e.error, "is_path") and e.error.is_path() 
                and e.error.get_path().is_not_found()):
            return None, None
        else:
            # altri errori (permessi, connessione, ecc.)
            st.error(f"Errore scaricando da Dropbox: {e}")
            return None, None
            
def format_dropbox_date(dt):
    if dt is None:
        return "Data non disponibile"

    # Dropbox restituisce sempre datetime tz-aware in UTC, ma nel dubbio gestiamo anche i naïve
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))

    # Convertiamo in fuso orario italiano
    dt_italy = dt.astimezone(ZoneInfo("Europe/Rome"))

    # Data odierna in Italia
    oggi = datetime.now(ZoneInfo("Europe/Rome")).date()

    mesi_it = [
        "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
    ]

    if dt_italy.date() == oggi:
        return f"Oggi alle {dt_italy.strftime('%H:%M')}"
    else:
        mese = mesi_it[dt_italy.month - 1]
        return f"{dt_italy.day:02d} {mese} {dt_italy.year} - {dt_italy.strftime('%H:%M')}"
