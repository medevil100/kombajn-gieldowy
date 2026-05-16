import os
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

# --- KONFIGURACJA STRONY ---
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

# --- SECRETS & AUTORYZACJA ---
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


# --- TRWAŁY ZAPIS DO PLIKÓW ---
def wczytaj_liste_z_pliku(rynek):
    nazwa_pliku = "spolki_pl.txt" if rynek == "PL (GPW)" else "spolki_usa.txt"
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
    nazwa_pliku = "spolki_pl.txt" if rynek == "PL (GPW)" else "spolki_usa.txt"
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
                        "Wstęgi BB": pozycja_bb,
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


# --- GENEROWANIE RAPORTU AI (Z OBSŁUGĄ 3 MODELI) ---
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

    # Dodatkowa konfiguracja specyficzna dla o3-mini
    if model == "o3-mini":
        params["reasoning_effort"] = "high"

    try:
        response = client.chat.completions.create(**params)
        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        return "❌ Błąd: Odpowiedź modelu OpenAI jest pusta."
    except Exception as e:
        return f"❌ Błąd OpenAI ({model}): {str(e)}"


# --- WIZUALIZACJA WYKRESU INTERAKTYWNEGO ---
def rysuj_wykres(df, ticker):
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Cena",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Upper_Band"],
            line=dict(color="rgba(255, 0, 0, 0.4)", width=1),
            name="Górna Wstęga BB",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Lower_Band"],
            line=dict(color="rgba(0, 0, 255, 0.4)", width=1),
            name="Dolna Wstęga BB",
        )
    )
    fig.update_layout(
        title=f"Wykres techniczny {ticker}",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


# --- INTERFEJS UŻYTKOWNIKA (STREAMLIT) ---
st.title("📱 Skaner AI Pro Master")

# --- PANEL BOCZNY (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Panel Sterowania")

    rynek = st.radio("Wybierz rynek:", ["PL (GPW)", "USA (NYSE/NASDAQ)"])

    # Wybór modelu GPT z trzech obiecanych opcji
    wybrany_model = st.selectbox(
        "🧠 Wybierz model AI:",
        ["o3-mini", "gpt-4o", "gpt-4o-mini"],
        index=0,
        help="o3-mini: głębokie rozumowanie (najlepszy do matematyki). gpt-4o: zaawansowana analiza rynkowa. gpt-4o-mini: najszybsza odpowiedź.",
    )

    lista_tickerow = wczytaj_liste_z_pliku(rynek)

    st.subheader("📝 Edycja Listy Spółek")
    nowa_lista_str = st.text_area(
        "Wpisz tickery po przecinku:", value=", ".join(lista_tickerow)
    )

    if st.button("Zapisz listę spółek", use_container_width=True):
        zaktualizowana_lista = [
            t.strip().upper() for t in nowa_lista_str.split(",") if t.strip()
        ]
        zapisz_liste_do_pliku(rynek, zaktualizowana_lista)
        st.success("Lista została zaktualizowana i zapisana!")
        st.rerun()

# --- GŁÓWNY EKRAN SKANOWANIA ---
if st.button("🚀 URUCHOM SKANOWANIE RYNKU", use_container_width=True):
    with st.spinner("Pobieranie danych i obliczanie wskaźników..."):
        df_wyniki, slownik_df = skanuj_wybrane_spolki(lista_tickerow)

        if df_wyniki.empty:
            st.warning("Brak danych do wyświetlenia. Sprawdź tickery.")
        else:
            st.session_state["df_wyniki"] = df_wyniki
            st.session_state["slownik_df"] = slownik_df
            st.success(f"Przeskanowano {len(df_wyniki)} spółek!")

# Prezentacja danych jeśli są w sesji
if "df_wyniki" in st.session_state and not st.session_state["df_wyniki"].empty:
    df_wyniki = st.session_state["df_wyniki"]
    slownik_df = st.session_state["slownik_df"]

    st.subheader("📊 Wyniki Analizy Technicznej")
    st.dataframe(df_wyniki, use_container_width=True)

    st.divider()
    st.subheader("🤖 Analiza Strategiczna AI")

    # Wybór spółki do pogłębionego raportu AI
    wybrany_ticker = st.selectbox(
        "Wybierz spółkę do raportu i wykresu:", df_wyniki["Ticker"].tolist()
    )

    wiersz = df_wyniki[df_wyniki["Ticker"] == wybrany_ticker].iloc[0]

    # Formularz celów tradera do promptu
    st.write(f"### 🎯 Parametry pozycji dla {wybrany_ticker}")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        tp1 = st.number_input(
            "TP1", value=float(wiersz["Cena"] * 1.05), step=0.01
        )
    with col2:
        tp2 = st.number_input(
            "TP2", value=float(wiersz["Cena"] * 1.10), step=0.01
        )
    with col3:
        tp3 = st.number_input(
            "TP3", value=float(wiersz["Cena"] * 1.20), step=0.01
        )
    with col4:
        sl = st.number_input(
            "Stop Loss", value=float(wiersz["Cena"] * 0.95), step=0.01
        )

    dane_tp = {"tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl}

    # Przycisk generowania raportu wybranym modelem
    if st.button(
        f"🤖 Generuj Raport AI ({wybrany_model})", use_container_width=True
    ):
        with st.spinner(f"Model {wybrany_model} analizuje dane rynkowe..."):
            raport = generuj_raport_pojedynczej_spolki(
                wybrany_model, wybrany_ticker, wiersz, dane_tp
            )
            st.markdown(f"### 📋 Raport Tradera AI ({wybrany_model})")
            st.info(raport)

    # Rysowanie wykresu dla wybranej spółki
    if wybrany_ticker in slownik_df:
        rysuj_wykres(slownik_df[wybrany_ticker], wybrany_ticker)
