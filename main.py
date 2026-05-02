import streamlit as st

# Stylizacja menu, żeby pasowała do reszty
st.set_page_config(layout="wide", page_title="NEON HUB")

st.sidebar.markdown("<h1 style='color:#39FF14;'>🎮 HUB OPERACYJNY</h1>", unsafe_allow_html=True)
wybor = st.sidebar.radio("WYBIERZ NARZĘDZIE:", ["🚀 KOMBAJN NEON AI", "🔬 SILNIK ULTRA (TEST)"])

if wybor == "🚀 KOMBAJN NEON AI":
    try:
        # Uruchamia Twój działający kombajn.py
        with open("kombajn.py", encoding="utf-8") as f:
            code = f.read()
        exec(code)
    except Exception as e:
        st.error(f"Błąd w kombajn.py: {e}")

elif wybor == "🔬 SILNIK ULTRA (TEST)":
    try:
        # Uruchamia analyzer_ultra.py, żebyś mógł sprawdzić czy działa
        with open("analyzer_ultra.py", encoding="utf-8") as f:
            code = f.read()
        exec(code)
    except Exception as e:
        st.warning("⚠️ Silnik Ultra wykrył błędy lub braki w kodzie.")
        st.error(f"Szczegóły błędu: {e}")
        st.info("Sprawdź czy plik analyzer_ultra.py ma wszystkie biblioteki w requirements.txt")
