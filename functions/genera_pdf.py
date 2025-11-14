import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

def genera_pdf(df_disp, **param):
    # --- Parametri ---
    truncate_map = param.get("truncate_map", None)  # se None = niente troncamento

    # --- Copia DF per non modificare l'originale ---
    df_proc = df_disp.copy()

    # --- Applico troncamento solo se truncate_map è definito ---
    if truncate_map:
        for col, max_len in truncate_map.items():
            if col in df_proc.columns:
                df_proc[col] = df_proc[col].astype(str).apply(
                    lambda x: x if len(x) <= max_len else x[:max_len-3]
                )

    # --- Altri parametri ---
    font_size = param.get("font_size", 12)
    header_bg_color = param.get("header_bg_color", colors.grey)
    header_text_color = param.get("header_text_color", colors.whitesmoke)
    row_bg_color = param.get("row_bg_color", colors.beige)
    header_align = param.get("header_align", "CENTER")
    text_align = param.get("text_align", "CENTER")
    valign = param.get("valign", "MIDDLE")
    margins = param.get("margins", (20, 20, 30, 20))
    row_height_factor = param.get("row_height_factor", 2.2)
    repeat_header = param.get("repeat_header", True)
    col_widths = param.get("col_widths", {})
    align_map = param.get("align_map", {})

    row_height_default = font_size * row_height_factor
    row_heights = [row_height_default] * (len(df_proc) + 1)

    # --- PDF ---
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margins[0],
        rightMargin=margins[1],
        topMargin=margins[2],
        bottomMargin=margins[3],
    )

    data = [list(df_proc.columns)] + df_proc.values.tolist()
    table = Table(
        data,
        repeatRows=1 if repeat_header else 0,
        hAlign='CENTER',
        rowHeights=row_heights
    )

    if col_widths:
        table._argW = [col_widths.get(col, 60) for col in df_proc.columns]

    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), header_text_color),
        ("ALIGN", (0, 0), (-1, 0), header_align),
        ("ALIGN", (0, 1), (-1, -1), text_align),
        ("VALIGN", (0, 0), (-1, -1), valign),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, 1), (-1, -1), row_bg_color),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ])

    for col_name, align in align_map.items():
        if col_name in df_proc.columns:
            idx = df_proc.columns.get_loc(col_name)
            style.add("ALIGN", (idx, 0), (idx, -1), align)

    table.setStyle(style)

    elements = [table]
    doc.build(elements)
    buffer.seek(0)
    return buffer
