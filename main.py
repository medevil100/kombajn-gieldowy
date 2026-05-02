import streamlit as st

# 1. GŁÓWNA KONFIGURACJA — tylko i wyłącznie w tym pliku!
st.set_page_config(
    layout="wide", 
    page_title="NEON HUB OPERACYJNY",
    page_icon="💠"
)

# 2. DEFINICJA NAWIGACJI
# System st.navigation automatycznie ładuje pliki i zapobiega błędom interfejsu (removeChild)
pg = st.navigation([
    st.Page("kombajn.py", title="🚀 TERMINAL NEON AI", icon="⚡"),
    st.Page("analyzer_ultra.py", title="🔬 SILNIK ULTRA DATA", icon="🔬")
])

# 3. URUCHOMIENIE WYBRANEJ STRONY
pg.run()
