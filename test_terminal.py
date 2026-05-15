import time
import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf
from openai import OpenAI

st.set_page_config(
    page_title="Skaner Groszówek AI Ultra", 
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

# --- MATEMATYKA I SZACOWANIE WSKAŹNIKÓW ---
def oblicz_wskazniki(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['STD20'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['STD20'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['STD20'] * 2)
    
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
            # Pobieramy dane z ostatniego roku (252 dni robocze) dla 52W High/Low
            df = t.history(period="260d")
            if df.empty or len(df) < 50:
                continue
                
            # Wyliczanie ekstremów 52-tygodniowych
            okres_52w = df.iloc[-252:] if len(df) >= 252 else df
            high_52w = okres_52w["High"].max()
            low_52w = okres_52w["Low"].min()
            
            df = oblicz_wskazniki(df)
            ostatni = df.iloc[-1]
            cena = ostatni["Close"]
            wolumen_teraz = ostatni["Volume"]
            wolumen_srednia = df["Volume"].rolling(10).mean().iloc[-1]
            
            if wolumen_teraz > 0:
                sma_10 = df["Close"].rolling(10).mean().iloc[-1]
                skok_vol = wolumen_teraz / wolumen_srednia if wolumen_srednia > 0 else 1.0
                trend = "🟢 Wzrostowy" if cena > sma_10 else "🔴 Spadkowy"
                
                pozycja_bb = "Środek"
                if cena >= ostatni['Upper_Band']: pozycja_bb = "🔥 Wybicie Góra"
                elif cena <= ostatni['Lower_Band']: pozycja_bb = "⚠️ Wybicie Dół"

                # Odległość ceny od historycznego dna (w procentach)
                odleglosc_od_dna = ((cena - low_52w) / low_52w) * 100

                dane_spolek.append({
                    "Ticker": ticker.strip().upper(),
                    "Cena": round(cena, 2),
                    "Skok Vol": round(skok_vol, 2),
                    "Trend": trend,
                    "RSI (14)": round(ostatni['RSI'], 1) if not pd.isna(ostatni['RSI']) else 50.0,
                    "MACD Hist": round(ostatni['MACD'] - ostatni['Signal'], 4) if not pd.isna(ostatni['Signal']) else 0.0,
                    "Zmienność (ATR)": round(ostatni['ATR'], 3) if not pd.isna(ostatni['ATR']) else 0.0,
                    "Wstęgi BB": pozycja_bb,
                    "52W Low": round(low_52w, 2),
                    "52W High": round(high_52w, 2),
                    "Od Dna (%)": round(odleglosc_od_dna, 1)
                })
        except Exception:
            continue
            
    return pd.DataFrame(dane_spolek)

def generuj_raport_pojedynczej_spolki(model, ticker, wiersz_danych):
    client = OpenAI(api_key=OPENAI_API_KEY)
    dane_tekst = wiersz_danych.to_string(index=False)
    
    prompt = f"""
    Jesteś zawodowym traderem giełdowym. Wykonaj indywidualną, maksymalnie szczegółową analizę dla spółki {ticker}.
    
    Oto jej pełne parametry rynkowe wraz z poziomami 52-tygodniowymi:
    {dane_tekst}
    
    Zinterpretuj precyzyjnie:
    1. Czy odległość od historycznego dna ('Od Dna (%)') stanowi bezpieczną strefę akumulacji, czy ryzyko bankructwa?
    2. Co sugeruje poziom RSI, MACD i pozycja ceny względem Wstęg Bollingera (BB)?
    3. Jaki jest dokładny werdykt i krótka strategia rynkowa?
    
    Napisz konkretny, strukturyzowany raport przy użyciu punktów i emoji pod ekran telefonu.
    """
    
    params = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if model == "o3-mini":
        params["reasoning_effort"] = "high"
        
    try:
        response = client.chat.completions.create(**params)
        if hasattr(response, 'choices') and len(response.choices) > 0:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                return choice.message.content
        return str(response)
    except Exception as e:
        return f"❌ Błąd API OpenAI: {str(e)}"


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
    
    # Wyświetlamy najważniejsze kolumny w tabeli głównej dla przejrzystości na telefonie
    widok_tabeli = df_aktywne[["Ticker", "Cena", "Skok Vol", "Trend", "RSI (14)", "Wstęgi BB", "Od Dna (%)"]]
    st.dataframe(widok_tabeli, use_container_width=True, hide_index=True)
    
    # --- SEKCJA ROZDZIELONEJ ANALIZY + KALKULATOR RYZYKA ---
    st.markdown("---")
    st.subheader("🔍 Indywidualna Analiza i MM")
    
    lista_tickerow_do_wyboru = df_aktywne["Ticker"].tolist()
    wybrany_ticker = st.selectbox("Wybierz spółkę:", lista_tickerow_do_wyboru)
    
    # Pobranie wiersza danych wybranej spółki
    wiersz_spolki = df_aktywne[df_aktywne["Ticker"] == wybrany_ticker].iloc[0]
    
    # --- INTEGRACJA KALKULATORA ATR (MONEY MANAGEMENT) ---
    st.markdown("##### 🧮 Kalkulator wielkości pozycji (ATR)")
    waluta = "PLN" if rynek_wybor == "PL (GPW)" else "USD"
    
    akceptowalne_ryzyko = st.number_input(
        f"Maksymalna kwota straty na pozycję ({waluta}):", 
        min_value=10, max_value=50000, value=200, step=50
    )
    
    # Logika kalkulatora: Stop Loss ustawiany jako odległość 2 * ATR od ceny wejściowej
    cena_wejscia = wiersz_spolki["Cena"]
    atr = wiersz_spolki["Zmienność (ATR)"]
    
    # Ochrona przed ATR równym 0
    if atr <= 0:
        atr = cena_wejscia * 0.05
        
    odleglosc_sl = round(2 * atr, 2)
    poziom_sl = round(cena_wejscia - odleglosc_sl, 2)
    
    if poziom_sl <= 0:
        poziom_sl = round(cena_wejscia * 0.5, 2)
        odleglosc_sl = round(cena_wejscia - poziom_sl, 2)

    # Obliczenie wielkości pozycji na podstawie zadeklarowanego ryzyka kwotowego
    liczba_akcji = int(akceptowalne_ryzyko / odleglosc_sl) if odleglosc_sl > 0 else 0
    calkowity_kapital = round(liczba_akcji * cena_wejscia, 2)

    # Prezentacja wyników kalkulatora w widoku mobilnym
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Sugerowana obrona (SL)", value=f"{poziom_sl} {waluta}", delta=f"-{odleglosc_sl}")
        st.metric(label="Liczba akcji do kupna", value=f"{liczba_akcji} szt.")
    with col2:
        st.metric(label="Całkowity koszt pozycji", value=f"{calkowity_kapital} {waluta}")
        st.metric(label="Dołek 52W", value=f"{wiersz_spolki['52W Low']} {waluta}", delta=f"{wiersz_spolki['Od Dna (%)']}% od dna", delta_color="inverse")

    # Przycisk uruchomienia analizy dedykowanej dla tej spółki z uwzględnieniem danych rocznych
    if st.button(f"🧠 Generuj Raport AI dla {wybrany_ticker}", type="primary", use_container_width=True):
        dane_spolki_pelne = df_aktywne[df_aktywne["Ticker"] == wybrany_ticker]
        with st.spinner(f"Potężny model {gpt_wybor} analizuje profil {wybrany_ticker}..."):
            wynik_indywidualny = generuj_raport_pojedynczej_spolki(gpt_wybor, wybrany_ticker, dane_spolki_pelne)
            st.markdown(f"### 📝 Raport Głęboki dla {wybrany_ticker}:")
            st.info(wynik_indywidualny)
else:
    st.warning("Lista pusta lub brak aktywności na spółkach.")

st.caption(f"Aktualizacja: {time.strftime('%H:%M:%S')} | Odświeżenie za {interwal} min.")
time.sleep(interwal * 60)
st.rerun()
