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


# CSS per il box
st.markdown("""
<style>
.box-style {
    border: 2px solid #ccc;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 20px;
    background-color: #f9f9f9;
    box-shadow: 2px 2px 8px rgba(0,0,0,0.05);
}
</style>
""", unsafe_allow_html=True)





def bordered_box_fotografi(title, data_dict, emoji="✅", border_color="#ccc", bg_color="#f9f9f9"):
    labels = list(data_dict.keys())
    dfs = list(data_dict.values())
    cols = st.columns(len(labels))
    html = f"""
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
            """
                    
    for col, label, df in zip(cols, labels, dfs):
        with col:
            html = html + f"""<div style="font-size: 2rem; font-weight: bold;">{label}<br>{df.shape[0]}</div>"""
            
    html = html + "</div>"
    st.markdown(html,
                unsafe_allow_html=True
            )
