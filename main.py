import streamlit as st

# GŁÓWNA KONFIGURACJA (Tylko tutaj!)
st.set_page_config(layout="wide", page_title="HUB GIEŁDOWY")

# Tworzymy niezależne strony
pg = st.navigation([
    st.Page("kombajn.py", title="🚀 TERMINAL NEON AI", icon="⚡"),
    st.Page("analyzer_ultra.py", title="🔬 SILNIK ULTRA DATA", icon="🔬")
])

pg.run()
