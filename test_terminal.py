import time
import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf
from openai import OpenAI

st.set_page_config(
    page_title="Skaner Groszówek AI Pro", 
    page_icon="📱", 
    layout="centered"
)

# --- MATRYCA WIZUALNA (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    div[data-testid="stDataFrame"] { background-color: #161B22; border: 1px solid #30363D; border-radius: 8px; }
    div.stButton > button:first-child {
        background-color: #00ff66 !important; color: #000000 !important; font-weight: bold !important;
        border-radius: 6px !important; border: none !important; box-shadow: 0 0 12px rgba(0, 255, 102, 0.5);
    }
    </style>
""", unsafe_allow_html=True)

try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    st.error("Błąd: Skonfiguruj 'OPENAI_API_KEY' oraz 'APP_PASSWORD' w Streamlit Secrets.")
    st.stop()

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

if "spolki_pl" not in st.session_state:
    st.session_state.spolki_pl = ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA", "RFK.WA"]
if "spolki_usa" not in st.session_state:
    st.session_state.spolki_usa = ["SNDL", "NIO", "AAL", "F", "LCID", "RIG"]

# --- ZAAWANSOWANA MATEMATYKA GIEŁDOWA ---
def oblicz_wskazniki(df):
    """Kalkuluje dodatkowe wymiary danych technicznych."""
    # 1. RSI (Pęd rynku / Wykupienie-Wyprzedanie)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 2. MACD (Zbieżność i rozbieżność średnich)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # 3. Wstęgi Bollingera (Zmienność i ekstrema cenowe)
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['STD20'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['STD20'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['STD20'] * 2)
    
    # 4. ATR (Średni rzeczywisty zasięg - zmienność kwotowa)
    high_low = df['High'] - df['Low']
    high_cp = np.abs(df['High'] - df['Close'].shift())
    low_cp = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1).rolling(14).mean()
    
    return df

def skanuj_wybrane_spolki(lista_tickerow):
    dane_spolek = []
    if not lista_tickerow:
        return pd.DataFrame()
        
    for ticker in lista_tickerow:
        try:
            t = yf.Ticker(ticker.strip().upper())
            df = t.history(period="60d") # Większy zapas pod wskaźniki kroczące
            if df.empty or len(df) < 30:
                continue
                
            df = oblicz_wskazniki(df)
            
            ostatni = df.iloc[-1]
            cena = ostatni["Close"]
            wolumen_teraz = ostatni["Volume"]
            wolumen_srednia = df["Volume"].rolling(10).mean().iloc[-1]
            
            if wolumen_teraz > 0:
                sma_10 = df["Close"].rolling(10).mean().iloc[-1]
                skok_vol = wolumen_teraz / wolumen_srednia if wolumen_srednia > 0 else 1.0
                trend = "🟢 Wzrostowy" if cena > sma_10 else "🔴 Spadkowy"
                
                # Określenie pozycji ceny względem wstęg Bollingera
                pozycja_bb = "Środek"
                if cena >= ostatni['Upper_Band']: pozycja_bb = "🔥 Wybicie Góra"
                elif cena <= ostatni['Lower_Band']: pozycja_bb = "⚠️ Wybicie Dół"

                dane_spolek.append({
                    "Ticker": ticker.strip().upper(),
                    "Cena": round(cena, 2),
                    "Skok Vol": round(skok_vol, 2),
                    "Trend": trend,
                    "RSI (14)": round(ostatni['RSI'], 1) if not pd.isna(ostatni['RSI']) else 50.0,
                    "MACD Hist": round(ostatni['MACD'] - ostatni['Signal'], 4) if not pd.isna(ostatni['Signal']) else 0.0,
                    "Zmienność (ATR)": round(ostatni['ATR'], 3) if not pd.isna(ostatni['ATR']) else 0.0,
                    "Wstęgi BB": pozycja_bb
                })
        except Exception:
            continue
            
    return pd.DataFrame(dane_spolek)

def generuj_raport_mocne_llm(model, dane_tabeli):
    client = OpenAI(api_key=OPENAI_API_KEY)
    tekst_tabeli = dane_tabeli.to_string(index=False)
    
    prompt = f"""
    Jesteś algorytmicznym traderem groszówek. Dokonaj głębokiej wielowskaźnikowej analizy technicznej:

    {tekst_tabeli}

    Wykorzystaj synergie wskaźników:
    - OKAZJA KUPNA: Wysoki Skok Vol (>1.5) + Trend Wzrostowy + RSI rosnące ale nie wykupione (<65) + MACD Hist dodatni + Wybicie Góra z BB.
    - OSTRZEŻENIE/SŁABOŚĆ: Trend Spadkowy + Wybicie Dół z BB LUB skrajne wykupienie na RSI (>75) sugerujące dystrybucję.
    
    Zwróć ekstremalnie zwięzły, konkretny raport na ekran smartfona. Pogrub kluczowe tickery.
    """
    
    # Konfiguracja parametrów zależnie od architektury modelu OpenAI
    params = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if model == "o3-mini":
        params["reasoning_effort"] = "high" # Maksymalna moc obliczeniowa i logiczna
        
    response = client.chat.completions.create(**params)
    return response.choices[0].message.content


# --- INTERFEJS MOBILNY ---
st.title("📱 Skaner AI Ultra")

with st.sidebar:
    st.header("⚙️ Parametry")
    rynek_wybor = st.radio("Wybierz okno rynkowe:", ["PL (GPW)", "USA"])
    gpt_wybor = st.selectbox("Mocny Silnik AI:", ["o3-mini", "gpt-4o", "o1"])
    interwal = st.slider("Interwał odświeżania (min):", min_value=1, max_value=60, value=5)

st.subheader("📝 Edytuj swoją listę")
aktualna_lista = st.session_state.spolki_pl if rynek_wybor == "PL (GPW)" else st.session_state.spolki_usa
lista_tekst = ", ".join(aktualna_lista)

nowa_lista_tekst = st.text_area(f"Tickery dla {rynek_wybor} (rozdziel przecinkami):", value=lista_tekst)

if st.button("💾 Zapisz i Odśwież", use_container_width=True):
    czysta_lista = [t.strip().upper() for t in nowa_lista_tekst.split(",") if t.strip()]
    if rynek_wybor == "PL (GPW)": st.session_state.spolki_pl = czysta_lista
    else: st.session_state.spolki_usa = czysta_lista
    st.success("Lista zapisana!")
    st.rerun()

st.subheader(f"📊 Monitorowane Groszówki: {rynek_wybor}")
df_aktywne = skanuj_wybrane_spolki(aktualna_lista)

if not df_aktywne.empty:
    df_aktywne = df_aktywne.sort_values(by="Skok Vol", ascending=False)
    # Wyświetlanie nowej tabeli bogatej we wskaźniki
    st.dataframe(df_aktywne, use_container_width=True, hide_index=True)
    
    if st.button(f"🧠 Analiza Wielowskaźnikowa ({gpt_wybor})", type="primary", use_container_width=True):
        with st.spinner("Najmocniejsze AI koreluje wskaźniki..."):
            wynik_ai = generuj_raport_mocne_llm(gpt_wybor, df_aktywne)
            st.markdown("### 📝 Strategia i Alerty AI:")
            st.info(wynik_ai)
else:
    st.warning("Lista pusta lub brak aktywności na spółkach.")

st.caption(f"Aktualizacja: {time.strftime('%H:%M:%S')} | Odświeżenie za {interwal} min.")
time.sleep(interwal * 60)
st.rerun()
