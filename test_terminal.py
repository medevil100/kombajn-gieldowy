import time
import pandas as pd
import streamlit as st
import yfinance as yf
from openai import OpenAI

# Ustawienia strony pod smartfony
st.set_page_config(
    page_title="Skaner Groszówek AI Pro", 
    page_icon="📱", 
    layout="centered"
)

# --- NEONOWY TUNING KOLORÓW (CSS) ---
st.markdown("""
    <style>
    /* Główny kontener aplikacji */
    .stApp {
        background-color: #0E1117;
    }
    /* Stylizacja tabel giełdowych */
    div[data-testid="stDataFrame"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
    }
    /* Przyciski akcji */
    div.stButton > button:first-child {
        background-color: #00ff66 !important;
        color: #000000 !important;
        font-weight: bold !important;
        border-radius: 6px !important;
        border: none !important;
        box-shadow: 0 0 10px rgba(0, 255, 102, 0.4);
    }
    /* Teksty alertów */
    .wzrost-alert {
        color: #00ff66;
        font-weight: bold;
        background-color: #12221A;
        padding: 8px;
        border-radius: 4px;
        border-left: 4px solid #00ff66;
    }
    .spadek-alert {
        color: #ff3333;
        font-weight: bold;
        background-color: #241416;
        padding: 8px;
        border-radius: 4px;
        border-left: 4px solid #ff3333;
    }
    </style>
""", unsafe_allow_html=True)

# Bezpieczne pobieranie kluczy
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    st.error("Błąd: Skonfiguruj 'OPENAI_API_KEY' oraz 'APP_PASSWORD' w Streamlit Secrets.")
    st.stop()

# Logowanie
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔒 Autoryzacja")
    haslo = st.text_input("Wpisz hasło mobilne:", type="password")
    if st.button("Zaloguj się", use_container_width=True):
        if haslo == APP_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Błędne hasło!")
    st.stop()

# Inicjalizacja list w sesji
if "spolki_pl" not in st.session_state:
    st.session_state.spolki_pl = ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA", "RFK.WA"]

if "spolki_usa" not in st.session_state:
    st.session_state.spolki_usa = ["SNDL", "NIO", "AAL", "F", "LCID", "RIG"]

# --- FUNKCJE ANALITYCZNE ---
def skanuj_wybrane_spolki(lista_tickerow):
    dane_spolek = []
    if not lista_tickerow:
        return pd.DataFrame()
        
    for ticker in lista_tickerow:
        try:
            t = yf.Ticker(ticker.strip().upper())
            df = t.history(period="15d")
            if df.empty or len(df) < 10:
                continue
                
            cena = df["Close"].iloc[-1]
            wolumen_teraz = df["Volume"].iloc[-1]
            wolumen_srednia = df["Volume"].rolling(10).mean().iloc[-1]
            
            if wolumen_teraz > 0:
                sma_10 = df["Close"].rolling(10).mean().iloc[-1]
                skok_vol = wolumen_teraz / wolumen_srednia if wolumen_srednia > 0 else 1.0
                trend = "🟢 Wzrostowy" if cena > sma_10 else "🔴 Spadkowy"
                
                dane_spolek.append({
                    "Ticker": ticker.strip().upper(),
                    "Cena": round(cena, 2),
                    "Skok Vol": round(skok_vol, 2),
                    "Trend": trend
                })
        except Exception:
            continue
            
    return pd.DataFrame(dane_spolek)

def generuj_raport_mocne_llm(model, dane_tabeli):
    """Wysyła zapytanie do OpenAI zachowując indeksowanie choices[0] dla o1/o3-mini."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    tekst_tabeli = dane_tabeli.to_string(index=False)
    
    prompt = f"""
    Jesteś elitarnym analitykiem ilościowym. Dokonaj analizy dla poniższych pozycji giełdowych:

    {tekst_tabeli}

    Wskaż:
    1. Najsilniejsze anomalie wolumenowe potwierdzające napływ kapitału (Skok Vol >> 1.0 + Trend Wzrostowy).
    2. Spółki, które tracą siłę (Trend Spadkowy) - wygeneruj dla nich ALERT.
    
    Format odpowiedzi: bardzo krótki, pod ekran telefonu. Używaj emoji.
    """
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    # POPRAWKA BŁĘDU: choices[0] zamiast choices
    return response.choices[0].message.content


# --- INTERFEJS MOBILNY ---
st.title("📱 Skaner AI Pro")

with st.sidebar:
    st.header("⚙️ Parametry")
    rynek_wybor = st.radio("Wybierz okno rynkowe:", ["PL (GPW)", "USA"])
    gpt_wybor = st.selectbox("Mocny Silnik AI:", ["o3-mini", "o1", "gpt-4o"])
    interwal = st.slider("Interwał odświeżania (min):", min_value=1, max_value=60, value=5)

# Zarządzanie listami
st.subheader("📝 Edytuj swoją listę")
aktualna_lista = st.session_state.spolki_pl if rynek_wybor == "PL (GPW)" else st.session_state.spolki_usa
lista_tekst = ", ".join(aktualna_lista)

nowa_lista_tekst = st.text_area(
    f"Tickery dla {rynek_wybor} (rozdziel przecinkami):", 
    value=lista_tekst
)

if st.button("💾 Zapisz i Odśwież", use_container_width=True):
    czysta_lista = [t.strip().upper() for t in nowa_lista_tekst.split(",") if t.strip()]
    if rynek_wybor == "PL (GPW)":
        st.session_state.spolki_pl = czysta_lista
    else:
        st.session_state.spolki_usa = czysta_lista
    st.success("Lista zapisana!")
    st.rerun()

# Wyświetlanie tabeli i raportu
st.subheader(f"📊 Monitorowane Groszówki: {rynek_wybor}")
df_aktywne = skanuj_wybrane_spolki(st.session_state.spolki_pl if rynek_wybor == "PL (GPW)" else st.session_state.spolki_usa)

if not df_aktywne.empty:
    df_aktywne = df_aktywne.sort_values(by="Skok Vol", ascending=False)
    st.dataframe(df_aktywne, use_container_width=True, hide_index=True)
    
    # POPRAWIONE WYWOŁANIE FUNKCJI (Usunięty ciąg wielokrotnego przypisania)
    if st.button(f"🧠 Generuj Raport ({gpt_wybor})", type="primary", use_container_width=True):
        with st.spinner("Model AI kalkuluje trendy..."):
            wynik_ai = generuj_raport_mocne_llm(gpt_wybor, df_aktywne)
            st.markdown("### 📝 Analiza i Alerty AI:")
            st.info(wynik_ai)
else:
    st.warning("Lista pusta lub brak aktywności na spółkach.")

st.caption(f"Aktualizacja: {time.strftime('%H:%M:%S')} | Odświeżenie za {interwal} min.")
time.sleep(interwal * 60)
st.rerun()
