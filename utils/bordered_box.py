import streamlit as st

def bordered_box(title, value, emoji="✅", border_color="#ccc", bg_color="#f9f9f9"):
    st.markdown(
        f"""
        <div style="
            border: 2px solid {border_color};
            border-radius: 10px;
            padding: 10px;
            background-color: {bg_color};
            text-align: center;
            box-shadow: 2px 2px 8px rgba(0,0,0,0.05);
        ">
            <div style="font-size: 1.1rem; font-weight: 600;">{emoji} {title}</div>
            <div style="font-size: 2rem; font-weight: bold;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )
