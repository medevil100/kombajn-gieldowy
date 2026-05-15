import os
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

st.set_page_config(
    page_title="Skaner Groszówek AI Master", page_icon="📱", layout="centered"
)

# --- MATRYCA WIZUALNA (CSS) ---
st.markdown(
    """
    <style>
    .stApp { background-color: #0E1117; }
    div[data-testid="stDataFrame"] { background-color: #161B22; border: 1px solid #30363D; border-radius: 8px; }
    div.stButton > button:first-child {
        background-color: #00ff66 !important; color: #000000 !important; font-weight: bold !important;
        border-radius: 6px !important; border: none !important; box-shadow: 0 0 12px rgba(0, 255, 102, 0.5);
    }
    </style>
""",
    unsafe_allow_html=True,
)

try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    st.error(
        "Błąd: Skonfiguruj 'OPENAI_API_KEY' oraz 'APP_PASSWORD' w Streamlit Secrets."
    )
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


# --- TRWAŁY ZAPIS DO PLIKÓW ---
def wczytaj_liste_z_pliku(rynek):
    nazwa_pliku = (
        "spolki_pl.txt" if rynek == "PL (GPW)" else "spolki_usa.txt"
    )
    if os.path.exists(nazwa_pliku):
        with open(nazwa_pliku, "r") as f:
            zawartosc = f.read()
            return [t.strip().upper() for t in zawartosc.split(",") if t.strip()]
    return (
        ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA"]
        if rynek == "PL (GPW)"
        else ["SNDL", "NIO", "AAL", "F"]
    )


def zapisz_liste_do_pliku(rynek, lista_tickerow):
    nazwa_pliku = (
        "spolki_pl.txt" if rynek == "PL (GPW)" else "spolki_usa.txt"
    )
    with open(nazwa_pliku, "w") as f:
        f.write(", ".join(lista_tickerow))


# --- DETEKCJA FORMACJI ŚWIECOWYCH ---
def wykryj_formacje_swiecowe(df):
    if len(df) < 2:
        return "Brak danych"

    o = df["Open"].iloc[-1]
    h = df["High"].iloc[-1]
    l = df["Low"].iloc[-1]
    c = df["Close"].iloc[-1]

    o_prev = df["Open"].iloc[-2]
    c_prev = df["Close"].iloc[-2]

    korpus = abs(c - o)
    cien_dolny = min(o, c) - l
    cien_gorny = h - max(o, c)
    zakres = h - l if (h - l) > 0 else 0.001

    if cien_dolny > (2 * korpus) and cien_gorny < (0.2 * zakres):
        return "🔨 Młot"
    if c_prev < o_prev and c > o and o <= c_prev and c >= o_prev:
        return "🔥 Objęcie Hossy"

    return "Neutralna"


# --- MATEMATYKA GIEŁDOWA ---
def oblicz_wskazniki(df):
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    exp1 = df["Close"].ewm(span=12, adjust=False).mean()
    exp2 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = exp1 - exp2
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    df["MA20"] = df["Close"].rolling(window=20).mean()
    df["STD20"] = df["Close"].rolling(window=20).std()
    df["Upper_Band"] = df["MA20"] + (df["STD20"] * 2)
    df["Lower_Band"] = df["MA20"] - (df["STD20"] * 2)

    high_low = df["High"] - df["Low"]
    high_cp = np.abs(df["High"] - df["Close"].shift())
    low_cp = np.abs(df["Low"] - df["Close"].shift())
    df["ATR"] = (
        pd.concat([high_low, high_cp, low_cp], axis=1)
        .max(axis=1)
        .rolling(14)
        .mean()
    )

    return df


def skanuj_wybrane_spolki(lista_tickerow):
    dane_spolek = []
    slownik_df = {}
    if not lista_tickerow:
        return pd.DataFrame(), {}

    for ticker in lista_tickerow:
        try:
            t = yf.Ticker(ticker.strip().upper())
            df = t.history(period="260d")
            if df.empty or len(df) < 50:
                continue

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
                skok_vol = (
                    wolumen_teraz / wolumen_srednia
                    if wolumen_srednia > 0
                    else 1.0
                )
                trend = "🟢 Wzrostowy" if cena > sma_10 else "🔴 Spadkowy"

                pozycja_bb = "Środek"
                if cena >= ostatni["Upper_Band"]:
                    pozycja_bb = "🔥 Wybicie Góra"
                elif cena <= ostatni["Lower_Band"]:
                    pozycja_bb = "⚠️ Wybicie Dół"

                odleglosc_od_dna = ((cena - low_52w) / low_52w) * 100
                formacja = wykryj_formacje_swiecowe(df)

                dane_spolek.append(
                    {
                        "Ticker": ticker.strip().upper(),
                        "Cena": round(cena, 2),
                        "Skok Vol": round(skok_vol, 2),
                        "Trend": trend,
                        "RSI (14)": (
                            round(ostatni["RSI"], 1)
                            if not pd.isna(ostatni["RSI"])
                            else 50.0
                        ),
                        "MACD Hist": (
                            round(ostatni["MACD"] - ostatni["Signal"], 4)
                            if not pd.isna(ostatni["Signal"])
                            else 0.0
                        ),
                        "Zmienność (ATR)": (
                            round(ostatni["ATR"], 3)
                            if not pd.isna(ostatni["ATR"])
                            else 0.0
                        ),
                        "Wstęgi BB": oily_bb = pozycja_bb,
                        "52W Low": round(low_52w, 2),
                        "52W High": round(high_52w, 2),
                        "Od Dna (%)": round(odleglosc_od_dna, 1),
                        "Formacja": formacja,
                    }
                )
                slownik_df[ticker.strip().upper()] = df
        except Exception:
            continue

    return pd.DataFrame(dane_spolek), slownik_df


def generuj_raport_pojedynczej_spolki(model, ticker, wiersz_danych, dane_tp):
    client = OpenAI(api_key=OPENAI_API_KEY)
    dane_tekst = wiersz_danych.to_string(index=False)
    tp_tekst = (
        f"Planowane cele Take Profit: TP1={dane_tp['tp1']}, "
        f"TP2={dane_tp['tp2']}, TP3={dane_tp['tp3']}. Stop Loss={dane_tp['sl']}."
    )

    prompt = f"""
    Jesteś zawodowym traderem. Wykonaj analizę dla spółki {ticker}:
    {dane_tekst}
    
    Zaimplementowany plan rynkowy tradera:
    {tp_tekst}
    
    Zinterpretuj i oceń:
    1. Czy odległość od dna i formacja świecowa dają przewagę rynkową?
    2. Czy w oparciu o RSI, MACD i Skok Vol wyznaczone poziomy Take Profit (TP1, TP2, TP3) są matematycznie i technicznie realne do osiągnięcia w najbliższych dniach?
    3. Werdykt końcowy (KUP / SPRZEDAJ / CZEKAJ).
    
    Krótko, konkretnie, pod telefon. Używaj punktów i emoji.
    """

    params = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if model == "o3-mini":
        params["reasoning_effort"] = "high"

    try:
        response = client.chat.completions.create(**params)
        if hasattr(response, "choices") and len(response.choices) > 0:
            choice = response.choices
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                return choice.message.content
        return str(response)
    except Exception as e:
        return f"❌ Błąd OpenAI: {str(e)}"


# --- INTERFEJS MOBILNY ---
st.title("📱 Skaner AI Pro Master")

with st.sidebar:
    st.header("⚙️ Parametry")
    rynek_wybor = st.radio("Wybierz okno rynkowe:", ["PL (GPW)", "USA"])
    gpt_wybor = st.selectbox("Mocny Silnik AI:", ["o3-mini", "gpt-4o", "o1"])
    interwal = st.slider(
        "Interwał odświeżania (min):", min_value=1, max_value=60, value=5
    )

# Zarządzanie listą
st.subheader("📝 Trwała Lista Spółek")
aktualna_lista = wczytaj_liste_z_pliku(rynek_wybor)
lista_tekst = ", ".join(aktualna_lista)

nowa_lista_tekst = st.text_area(
    f"Modyfikuj listę dla {rynek_wybor}:", value=lista_tekst
)

if st.button("💾 Zapisz na Stałe", use_container_width=True):
    czysta_lista = [
        t.strip().upper() for t in nowa_lista_tekst.split(",") if t.strip()
    ]
    zapisz_liste_do_pliku(rynek_wybor, czysta_lista)
    st.success("Zapisano trwale w pamięci aplikacji!")
    st.rerun()

st.subheader(f"📊 Monitorowane Groszówki: {rynek_wybor}")
df_aktywne, pełne_dfs = skanuj_wybrane_spolki(aktualna_lista)

if not df_aktywne.empty:
    df_aktywne = df_aktywne.sort_values(by="Skok Vol", ascending=False)

    # --- NOWOŚĆ: WYSZUKIWANIE SPÓŁEK PO SŁOWACH KLUCZOWYCH ---
    szukaj_frazy = st.text_input(
        "🔍 Szukaj (wpisz Ticker, Formację lub Trend, np. 'Młot', '🟢', 'SNDL'):"
    )
    if szukaj_frazy:
        # Filtrowanie elastyczne po tekście w kolumnach Ticker, Trend lub Formacja
        maska = (
            df_aktywne["Ticker"]
            .str.contains(szukaj_frazy, case=False, na=False)

            | df_aktywne["Trend"].str.contains(szukaj_frazy, case=False, na=False)
            | df_aktywne["Formacja"].str.contains(
                szukaj_frazy, case=False, na=False
            )
        )
        df_wyswietlane = df_aktywne[maska]
    else:
        df_wyswietlane = df_aktywne

    # Widok tabeli na telefon
    widok_tabeli = df_wyswietlane[
        [
            "Ticker",
            "Cena",
            "Skok Vol",
            "Trend",
            "RSI (14)",
            "Od Dna (%)",
            "Formacja",
        ]
    ]
    st.dataframe(widok_tabeli, use_container_width=True, hide_index=True)

    if df_wyswietlane.empty:
        st.info("Brak wyników dla wpisanej frazy kluczowej.")

    # --- INDYWIDUALNA ANALIZA I WYKRES ---
    st.markdown("---")
    st.subheader("🔍 Detale i Wykres Spółki")

    lista_tickerow_do_wyboru = df_wyswietlane["Ticker"].tolist() if not df_wyswietlane.empty else df_aktywne["Ticker"].tolist()
    wybrany_ticker = st.selectbox(
        "Wybierz ticker do analizy:", lista_tickerow_do_wyboru
    )

    if wybrany_ticker in pełne_dfs:
        df_wykres = pełne_dfs[wybrany_ticker].tail(30)
        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=df_wykres.index,
                open=df_wykres["Open"],
                high=df_wykres["High"],
                low=df_wykres["Low"],
                close=df_wykres["Close"],
                name="Cena",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df_wykres.index,
                y=df_wykres["Upper_Band"],
                line=dict(color="rgba(0, 255, 102, 0.3)", width=1),
                name="BB Górna",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df_wykres.index,
                y=df_wykres["Lower_Band"],
                line=dict(color="rgba(255, 51, 51, 0.3)", width=1),
                name="BB Dolna",
            )
        )
        fig.update_layout(
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            height=240,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- KALKULATOR RYZYKA I WIELOPOZIOMOWYCH TP ---
    wiersz_spolki = df_aktywne[df_aktywne["Ticker"] == wybrany_ticker].iloc[0]
    waluta = "PLN" if rynek_wybor == "PL (GPW)" else "USD"

    st.markdown("##### 🧮 Kalkulator Wielkości i Targetów (TP)")
    akceptowalne_ryzyko = st.number_input(
        f"Ryzyko kwotowe ({waluta}):", min_value=10, value=200, step=50
    )

    cena_wejscia = wiersz_spolki["Cena"]
    atr = wiersz_spolki["Zmienność (ATR)"]
    if atr <= 0:
        atr = cena_wejscia * 0.05

    odleglosc_sl = round(2 * atr, 2)
    poziom_sl = round(cena_wejscia - odleglosc_sl, 2)
    if poziom_sl <= 0:
        poziom_sl = round(cena_wejscia * 0.5, 2)
        odleglosc_sl = round(cena_wejscia - poziom_sl, 2)

    # --- NOWOŚĆ: STRATEGIA WIELOPOZIOMOWEGO TAKE PROFIT (R:R) ---
    poziom_tp1 = round(cena_wejscia + odleglosc_sl, 2)  # R:R = 1:1
    poziom_tp2 = round(cena_wejscia + (2 * odleglosc_sl), 2)  # R:R = 1:2
    poziom_tp3 = round(cena_wejscia + (3 * odleglosc_sl), 2)  # R:R = 1:3

    liczba_akcji = (
        int(akceptowalne_ryzyko / odleglosc_sl) if odleglosc_sl > 0 else 0
    )
    calkowity_kapital = round(liczba_akcji * cena_wejscia, 2)

    # Prezentacja Money Management
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            label="Stop Loss (Obrona)",
            value=f"{poziom_sl} {waluta}",
            delta=f"-{odleglosc_sl}",
        )
        st.metric(label="Kup akcji", value=f"{liczba_akcji} szt.")
    with col2:
        st.metric(label="Koszt pozycji", value=f"{calkowity_kapital} {waluta}")
        st.metric(label="Od Dna 52W", value=f"{wiersz_spolki['Od Dna (%)']}%")

    # Wizualizacja dynamicznych poziomów profitu
    st.markdown("**🎯 Wielopoziomowe Targety Cenowe (Take Profit):**")
    c1, c2, c3 = st.columns(3)
    c1.metric(label="TP1 (Zabezpieczenie 1:1)", value=f"{poziom_tp1} {waluta}")
    c2.metric(label="TP2 (Cel Główny 1:2)", value=f"{poziom_tp2} {waluta}")
    c3.metric(label="TP3 (Rakieta 1:3)", value=f"{poziom_tp3} {waluta}")

    # Przekazanie kompletnej struktury targetów do analizy AI
    slownik_tp = {
        "sl": poziom_sl,
        "tp1": poziom_tp1,
        "tp2": poziom_tp2,
        "tp3": poziom_tp3,
    }

    if st.button(
        f"🧠 Analiza i Ocena Celów przez AI",
        type="primary",
        use_container_width=True,
    ):
        dane_spolki_pelne = df_aktywne[df_aktywne["Ticker"] == wybrany_ticker]
        with st.spinner("Najsilniejsze AI weryfikuje poziomy TP i geometrię świec..."):
            wynik_indywidualny = generuj_raport_pojedynczej_spolki(
                gpt_wybor, wybrany_ticker, dane_spolki_pelne, slownik_tp
            )
            st.markdown(f"### 📝 Strategiczny Raport AI dla {wybrany_ticker}:")
            st.info(wynik_indywidualny)
else:
    st.warning("Lista pusta lub brak aktywności na spółkach.")

st.caption(
    f"Aktualizacja: {time.strftime('%H:%M:%S')} | Odświeżenie za {interwal} min."
)
time.sleep(interwal * 60)
st.rerun()
