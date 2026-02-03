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


def bordered_box_fotografi_old(title, data_dict, emoji="📥", border_color="#ccc", bg_color="#f9f9f9"):

    cols_html = ""
    for label, df in data_dict.items():
        cols_html += f"""
<div style="flex:1; text-align:center;">
    <div style="font-size:1.2rem; font-weight:600;">{label}</div>
    <div style="font-size:2rem; font-weight:bold;">{df.shape[0]}</div>
</div>
"""

    html = (
f'<div style="border:2px solid {border_color};'
f'border-radius:10px;'
f'width:80%;'
f'padding:10px;'
f'margin:0 auto 15px;'
f'background-color:{bg_color};'
f'text-align:center;'
f'box-shadow:2px 2px 8px rgba(0,0,0,0.05);">'
f'<div style="font-size:1.3rem; font-weight:700; margin-bottom:10px;">{emoji} {title}</div>'
f'<div style="display:flex; justify-content:space-around;">{cols_html}</div>'
f'</div>'
    )

    st.markdown(html, unsafe_allow_html=True)





def bordered_box_fotografi(title, data_dict, genera_pdf_fn, emoji="📥"):
    larghezza_col = {
        "COD":50,
        "VAR":35,
        "COL":40,
        "DESCRIZIONE":250,
        "COR":35,
        "LAT":35,
        "X":25,
        "Y":25
    }
    align_col = {"DESCRIZIONE":"LEFT"}
    limiti_chars = {"DESCRIZIONE":35}
    st.markdown(f"### {emoji} {title}")

    cols = st.columns(len(data_dict))
    for col, (label, df) in zip(cols, data_dict.items()):
        with col:
            st.markdown(f"""
                <div style="
                    border:2px solid #ccc;
                    border-radius:10px;
                    padding:15px;
                    text-align:center;
                    background-color:#f9f9f9;
                    box-shadow:2px 2px 6px rgba(0,0,0,0.05);
                    margin-bottom:5px;">
                    <strong>{label}</strong><br>
                    <span style="font-size:2rem">{df.shape[0]}</span>
                </div>
            """, unsafe_allow_html=True)
            # Pulsante subito sotto
            st.download_button(
                label="📥 Download",
                data=genera_pdf_fn(df, header_align="CENTER", text_align="CENTER", valign="MIDDLE",
                            col_widths=larghezza_col, align_map=align_col, truncate_map=limiti_chars),
                file_name=f"{title}_{label}.pdf",
                mime="application/pdf",
                disabled=df.empty,
                key=f"{title}_{label}"
            )
