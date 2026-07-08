import streamlit as st
from supabase import create_client, Client

supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]
service_role_key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
supabase: Client = create_client(supabase_url, supabase_key)
supabase_admin = create_client(supabase_url, service_role_key)

def login(username: str, password: str) -> bool:
    try:
        # 1. Recupera il profilo dallo username
        res_profile = supabase.table("profiles").select("*").eq("username", username).limit(1).execute()
        if not res_profile.data:
            st.error("❌ Username non trovato")
            return False

        # Estraiamo il dizionario dalla lista [0]
        profile_data = res_profile.data[0]
        user_id = profile_data["user_id"]

        # 2. Recupera l'utente auth per ottenere l'email (richiede service_role_key)
        res_user = supabase_admin.auth.admin.get_user_by_id(user_id)
        email = res_user.user.email
        output1 = res_user
        output2 = email
        if not email:
            st.error("❌ Nessuna email trovata per questo utente")
            return False

        # 3. Login usando email + password
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        output2 = res
        if res.user:
            # 4. Salva in session_state
            st.session_state.user = {
                "email": email,
                "username": profile_data.get("username", ""),
                "nome": profile_data.get("nome", ""),
                "cognome": profile_data.get("cognome", ""),
                "role": profile_data.get("role", "guest"),
            }
            return True
        else:
            st.error("❌ Credenziali errate")
            return False

    except Exception as e:
        st.success(output1)
        st.write(output2)
        st.error(f"Errore login: {e}")
        return False


      
def login_password(email: str, password: str) -> bool:
    try:
        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
        except Exception:
            st.error("❌ Email o password errati")
            return False

        if res.user is not None:
            # Recupera il profilo dell'utente usando limit(1)
            profile = supabase.table("profiles").select("*").eq("user_id", res.user.id).limit(1).execute()
            
            if not profile.data:
                st.error("❌ Profilo utente non trovato nel database")
                return False
            
            # Estraiamo il dizionario della riga trovato
            profile_data = profile.data[0]
            
            # Salva tutto in session_state usando profile_data
            st.session_state.user = {
                "data": res.user,
                "email": res.user.email,
                "nome": profile_data.get("nome", ""),
                "cognome": profile_data.get("cognome", ""),
                "username": profile_data.get("username", ""),
                "role": profile_data.get("role", "guest")
            }
            return True
        else:
            st.error("❌ Email o password errati")
            return False
    except Exception as e:
        st.error(f"Errore login: {e}")
        return False


def logout():
    if "user" in st.session_state:
        supabase.auth.sign_out()
        st.session_state.user = None
        #st.session_state.username = None
        st.rerun()

def register_user(email: str, password: str, **param) -> bool:
    try:
        # 1. Crea l'utente in Supabase Auth
        res = supabase_admin.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True
        })

        if not res.user:
            st.error("❌ Errore nella creazione utente in Auth")
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

        supabase_admin.table("profiles").insert(profile).execute()

        st.success(f"✅ Utente {param.get('username', email)} creato correttamente")
        return True

    except Exception as e:
        st.error(f"Errore registrazione: {e}")
        return False
