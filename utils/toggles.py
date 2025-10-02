def custom_toggle(label="Switch", default=False, key="custom_toggle"):
    toggle_id = f"{key}_toggle"

    html_code = f"""
    <style>
    .switch {{
      position: relative;
      display: inline-block;
      width: 50px;
      height: 24px;
    }}
    .switch input {{ display: none; }}
    .slider {{
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: #ccc;
      transition: .4s;
      border-radius: 24px;
    }}
    .slider:before {{
      position: absolute;
      content: "";
      height: 18px; width: 18px;
      left: 3px; bottom: 3px;
      background-color: white;
      transition: .4s;
      border-radius: 50%;
    }}
    input:checked + .slider {{
      background-color: #4CAF50;
    }}
    input:checked + .slider:before {{
      transform: translateX(26px);
    }}
    </style>

    <label class="switch">
      <input type="checkbox" id="{toggle_id}" {"checked" if default else ""} 
             onchange="const val=this.checked;
                       const input=window.parent.document.querySelector('input#{toggle_id}_hidden');
                       if(input) input.value=val; input.dispatchEvent(new Event('input',{{bubbles:true}}));">
      <span class="slider"></span>
    </label>
    <span style="margin-left:10px;">{label}</span>
    <input type="hidden" id="{toggle_id}_hidden" value="{str(default).lower()}">
    """

    value = components.html(html_code, height=50)

    # Recuperiamo il valore dall'hidden input
    toggle_value = st.text_input("", value=str(default).lower(), key=f"{toggle_id}_hidden")
    return toggle_value == "true"
