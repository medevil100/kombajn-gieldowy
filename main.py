import streamlit as st

# TYLKO TUTAJ konfigurujemy stronę
st.set_page_config(layout="wide", page_title="HUB GIEŁDOWY")

# Definicja stron - to naprawia błąd removeChild
pg = st.navigation({
    "NARZĘDZIA": [
        st.Page("kombajn.py", title="TERMINAL NEON AI", icon="⚡"),
        st.Page("analyzer_ultra.py", title="SILNIK ULTRA DATA", icon="🔬"),
    ]
})

pg.run()
