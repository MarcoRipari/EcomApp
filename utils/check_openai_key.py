import streamlit as st

import openai

openai.api_key = st.secrets["OPENAI_API_KEY"]

def check_openai_key():
    try:
        openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1
        )
        return True
    except Exception as e:  
        msg = str(e).lower()
        return False
