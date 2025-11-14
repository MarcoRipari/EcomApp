import streamlit as st

def bordered_box(title, value, emoji="✅", border_color="#ccc", bg_color="#f9f9f9"):
    st.markdown(
        f"""
        <div style="
            border: 2px solid {border_color};
            border-radius: 10px;
            width: 80%;
            padding: 10px;
            margin: 0 auto;
            margin-bottom: 15px;
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

import streamlit as st

def bordered_box_fotografi(title, data_dict, emoji="📥"):
    box = st.container()
    with box:
        st.markdown(f"<div class='bordered-box'>", unsafe_allow_html=True)

        # TITOLO
        st.markdown(
            f"<div style='text-align:center; font-size:1.4rem; font-weight:700;'>{emoji} {title}</div>",
            unsafe_allow_html=True
        )
        st.markdown("<br>", unsafe_allow_html=True)

        # COLONNE
        labels = list(data_dict.keys())
        dfs = list(data_dict.values())
        cols = st.columns(len(labels))

        for col, label, df in zip(cols, labels, dfs):
            with col:
                st.markdown(f"### {label}")
                st.markdown(
                    f"<div style='font-size:2rem;font-weight:bold;text-align:center'>{df.shape[0]}</div>",
                    unsafe_allow_html=True
                )
                st.download_button(
                    "⬇ Download",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name=f"{title}_{label}.csv",
                    mime="text/csv"
                )

        st.markdown("</div>", unsafe_allow_html=True)

