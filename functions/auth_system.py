import streamlit as st
from supabase import create_client, Client

supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]
service_role_key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
supabase: Client = create_client(supabase_url, supabase_key)
supabase_admin: Client = create_client(supabase_url, service_role_key)

def _messaggio_errore_italiano(e: Exception) -> str:
    """Traduce le eccezioni più comuni di Supabase in messaggi leggibili in
    italiano, invece di mostrare il testo grezzo (spesso in inglese e poco
    chiaro per l'utente finale)."""
    testo = str(e).lower()
    if "invalid login credentials" in testo or "invalid_credentials" in testo:
        return "❌ Username/email o password errati."
    if "email not confirmed" in testo:
        return "❌ Email non confermata. Contatta un amministratore."
    if "user already registered" in testo or "already been registered" in testo:
        return "❌ Esiste già un utente registrato con questa email."
    if "password" in testo and ("short" in testo or "weak" in testo or "6 characters" in testo):
        return "❌ La password è troppo corta (minimo 6 caratteri)."
    if "rate limit" in testo or "429" in testo:
        return "❌ Troppi tentativi in poco tempo. Riprova tra qualche minuto."
    if "network" in testo or "timeout" in testo or "connection" in testo:
        return "❌ Errore di connessione al server. Riprova."
    if "jwt" in testo or "expired" in testo:
        return "❌ Sessione scaduta. Effettua di nuovo l'accesso."
    return f"❌ Si è verificato un errore imprevisto: {e}"

def login(identificativo: str, password: str) -> bool:
    """Effettua il login con username OPPURE email (rilevato automaticamente
    dalla presenza di '@'). Supabase Auth richiede sempre l'email per
    autenticarsi: se l'utente inserisce lo username, prima risaliamo
    all'email associata leggendo la tabella 'profiles'."""
    try:
        identificativo = (identificativo or "").strip()
        password = password or ""
        if not identificativo or not password:
            st.error("❌ Inserisci username/email e password.")
            return False

        if "@" in identificativo:
            email = identificativo
        else:
            # 🔧 FIX: prima si cercava SEMPRE per username, quindi inserire
            # un'email qui falliva sempre con "Username non trovato". Ora
            # rileviamo il formato e usiamo l'email direttamente se presente.
            try:
                res_profile = supabase.table("profiles").select("*").eq("username", identificativo).execute()
            except Exception as e:
                st.error(_messaggio_errore_italiano(e))
                return False

            if not res_profile.data:
                st.error("❌ Username non trovato.")
                return False

            user_id = res_profile.data[0]["user_id"]
            try:
                res_user = supabase_admin.auth.admin.get_user_by_id(user_id)
                email = res_user.user.email if res_user and res_user.user else None
            except Exception as e:
                st.error(_messaggio_errore_italiano(e))
                return False

            if not email:
                st.error("❌ Nessuna email associata a questo username.")
                return False

        # Login vero e proprio (richiede sempre email, anche se l'utente ha digitato lo username)
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as e:
            st.error(_messaggio_errore_italiano(e))
            return False

        if not res or not res.user:
            st.error("❌ Username/email o password errati.")
            return False

        # Recupero profilo (nome, cognome, ruolo) tramite user_id: funziona sia
        # per chi ha fatto login con username sia con email
        try:
            res_profile2 = supabase.table("profiles").select("*").eq("user_id", res.user.id).execute()
        except Exception as e:
            st.error(_messaggio_errore_italiano(e))
            return False

        if not res_profile2.data:
            st.error("❌ Accesso riuscito ma profilo utente non trovato. Contatta un amministratore.")
            return False

        profilo = res_profile2.data[0]
        st.session_state.user = {
            "email": email,
            "username": profilo.get("username", ""),
            "nome": profilo.get("nome", ""),
            "cognome": profilo.get("cognome", ""),
            "role": profilo.get("role", "guest"),
        }
        return True

    except Exception as e:
        st.error(_messaggio_errore_italiano(e))
        return False


      
def login_password(email: str, password: str) -> bool:
    try:
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if res.user is not None:
           
            # Recupera il profilo dell'utente usando user_id
            profile = supabase.table("profiles").select("*").eq("user_id", res.user.id).single().execute()
            
            if profile.data is None:
                st.error("❌ Profilo utente non trovato")
                return False
            
            # Salva tutto in session_state
            st.session_state.user = {
                "data": res.user,
                "email": res.user.email,
                "nome": profile.data["nome"],
                "cognome": profile.data["cognome"],
                "username": profile.data["username"],
                "role": profile.data["role"]
            }
            #st.session_state.user = res.user
            #st.session_state.username = profile.data.get("username", res.user.email)
            return True
        else:
            st.error("❌ Email o password errati")
            return False
    except Exception as e:
        st.error(f"Errore login: {e}")
        return False


def logout():
    if "user" in st.session_state:
        try:
            supabase.auth.sign_out()
        except Exception as e:
            # Anche se il logout lato Supabase fallisce (es. sessione già scaduta),
            # puliamo comunque la sessione locale per non lasciare l'utente bloccato
            st.warning(f"⚠️ Disconnessione dal server non riuscita ({e}), ma la sessione locale è stata comunque chiusa.")
        st.session_state.user = None
        st.rerun()

def register_user(email: str, password: str, **param) -> bool:
    try:
        email = (email or "").strip()
        password = password or ""
        if not email or "@" not in email:
            st.error("❌ Inserisci un'email valida.")
            return False
        if len(password) < 6:
            st.error("❌ La password deve essere di almeno 6 caratteri.")
            return False
        if not param.get("username"):
            st.error("❌ Lo username è obbligatorio.")
            return False

        # 1. Crea l'utente in Supabase Auth
        try:
            res = supabase_admin.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
        except Exception as e:
            st.error(_messaggio_errore_italiano(e))
            return False

        if not res or not res.user:
            st.error("❌ Errore nella creazione dell'utente.")
            return False

        user_id = res.user.id

        # 2. Inserisci il profilo nella tabella profiles
        profile = {
            "user_id": user_id,
            "nome": param.get("nome", None),
            "cognome": param.get("cognome", None),
            "username": param.get("username", None),
            "role": param.get("role", None)
        }

        try:
            supabase_admin.table("profiles").insert(profile).execute()
        except Exception as e:
            # L'utente Auth è stato creato ma il profilo no: lo segnaliamo chiaramente
            # invece di lasciare un utente "fantasma" senza spiegazioni
            st.error(
                f"⚠️ Utente creato in autenticazione, ma il salvataggio del profilo è fallito: "
                f"{_messaggio_errore_italiano(e)} Contatta un amministratore per completare la registrazione."
            )
            return False

        st.success(f"✅ Utente {param.get('username', email)} creato correttamente")
        return True

    except Exception as e:
        st.error(_messaggio_errore_italiano(e))
        return False
