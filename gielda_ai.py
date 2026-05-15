import os
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI
import io, wave, math, struct, base64

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

# --- SECRETS / API ---
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    st.error("Błąd: Skonfiguruj 'OPENAI_API_KEY' oraz 'APP_PASSWORD' w Streamlit Secrets.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# --- AUTORYZACJA ---
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

# ============================================================
#  DŹWIĘK ALERTU – DUAL SCANNER
# ============================================================

@st.cache_resource
def generate_beep_b64():
    framerate = 44100
    duration = 0.35
    freq = 880
    n_samples = int(duration * framerate)
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(framerate)
    for i in range(n_samples):
        val = int(32767 * math.sin(2 * math.pi * freq * i / framerate))
        w.writeframes(struct.pack("<h", val))
    w.close()
    return base64.b64encode(buf.getvalue()).decode("ascii")

BEEP = generate_beep_b64()

def play_beep():
    st.markdown(
        f"""
        <audio autoplay>
            <source src="data:audio/wav;base64,{BEEP}" type="audio/wav">
        </audio>
        """,
        unsafe_allow_html=True
    )

# ============================================================
#  DUAL SCANNER – POBIERANIE DANYCH
# ============================================================

@st.cache_data(show_spinner=False)
def ds_download(tickers, period="180d", interval="1d"):
    if not tickers:
        return {}
    data = yf.download(
        tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False
    )
    result = {}
    if isinstance(data.columns, pd.MultiIndex):
        for t in tickers:
            if t in data.columns.get_level_values(0):
                df = data[t].copy().dropna()
                result[t] = df
    else:
        df = data.copy().dropna()
        result[tickers[0]] = df
    return result

# ============================================================
#  DUAL SCANNER – WSKAŹNIKI
# ============================================================

def ds_indicators(df, mode):
    df = df.copy()

    if mode == "Swing":
        df["EMA_fast"] = df["Close"].ewm(span=20).mean()
        df["EMA_mid"] = df["Close"].ewm(span=50).mean()
        df["EMA_slow"] = df["Close"].ewm(span=200).mean()
        delta = df["Close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["Fibo_high"] = df["Close"].rolling(60).max()
        df["Fibo_low"] = df["Close"].rolling(60).min()
        df["Momentum"] = df["Close"].diff(10)
        df["Vol_avg"] = df["Volume"].rolling(20).mean()

    elif mode == "Day":
        df["EMA_fast"] = df["Close"].ewm(span=9).mean()
        df["EMA_mid"] = df["Close"].ewm(span=20).mean()
        df["EMA_slow"] = df["Close"].ewm(span=50).mean()
        delta = df["Close"].diff()
        gain = delta.clip(lower=0).rolling(7).mean()
        loss = (-delta.clip(upper=0)).rolling(7).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["Fibo_high"] = df["Close"].rolling(20).max()
        df["Fibo_low"] = df["Close"].rolling(20).min()
        df["Momentum"] = df["Close"].diff(3)
        df["Vol_avg"] = df["Volume"].rolling(10).mean()

    else:  # Long
        df["EMA_fast"] = df["Close"].ewm(span=50).mean()
        df["EMA_mid"] = df["Close"].ewm(span=100).mean()
        df["EMA_slow"] = df["Close"].ewm(span=200).mean()
        delta = df["Close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["Fibo_high"] = df["Close"].rolling(120).max()
        df["Fibo_low"] = df["Close"].rolling(120).min()
        df["Momentum"] = df["Close"].diff(20)
        df["Vol_avg"] = df["Volume"].rolling(50).mean()

    df["Trend"] = df["EMA_fast"] - df["EMA_mid"]
    df["Vol_ratio"] = df["Volume"] / df["Vol_avg"]
    return df

# ============================================================
#  DUAL SCANNER – NEWS FLAGI
# ============================================================

def ds_news_flags(ticker):
    try:
        tk = yf.Ticker(ticker)
        news = tk.news or []
    except Exception:
        return ""

    text = ""
    for n in news[:5]:
        text += " " + str(n.get("title", "")) + " " + str(n.get("summary", ""))

    text_low = text.lower()
    flags = []

    if "fda" in text_low:
        flags.append("FDA")
    if "approval" in text_low:
        flags.append("approval")
    if "debt" in text_low or "zadłużenie" in text_low:
        flags.append("debt")
    if "downgrade" in text_low:
        flags.append("downgrade")
    if "profit warning" in text_low:
        flags.append("profit warning")
    if "bankruptcy" in text_low:
        flags.append("bankruptcy")
    if "offering" in text_low:
        flags.append("share offering")
    if "buyback" in text_low:
        flags.append("buyback")
    if "acquisition" in text_low:
        flags.append("M&A")

    return " | ".join(flags)

# ============================================================
#  DUAL SCANNER – SYGNAŁY
# ============================================================

def ds_compute_signals(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signals = []

    if last["EMA_fast"] > last["EMA_mid"] > last["EMA_slow"] and last["RSI"] > 55:
        trend_state = "trend rośnie"
    elif last["EMA_fast"] < last["EMA_mid"] < last["EMA_slow"] and last["RSI"] < 45:
        trend_state = "trend spada"
    else:
        trend_state = "trend stoi"

    signals.append(trend_state)

    if last["Close"] > last["EMA_mid"] and prev["Close"] <= prev["EMA_mid"]:
        signals.append("przebicie EMA_mid")
    if last["Close"] > last["Fibo_high"] * 0.999:
        signals.append("wybicie Fibo HIGH")
    if last["Close"] < last["Fibo_low"] * 1.001:
        signals.append("wybicie Fibo LOW")

    if last["Close"] > prev["Close"] and last["Vol_ratio"] > 1.5 and last["RSI"] > prev["RSI"]:
        signals.append("wzrost kupujących")

    if last["Close"] < prev["Close"] and last["Vol_ratio"] > 1.5 and last["RSI"] < prev["RSI"]:
        signals.append("wzrost sprzedających")

    return trend_state, signals

# ============================================================
#  DUAL SCANNER – AI #2 / #3 / #4
# ============================================================

def ds_ai2_comment(ticker, last, trend_state, signals, news_text):
    sig_str = ", ".join(signals)
    news_str = news_text if news_text else "brak newsów"

    prompt = f"""
Opisz sytuację spółki w 1–2 zdaniach.

Ticker: {ticker}
Cena: {last['Close']:.2f}
Trend: {trend_state}
Sygnały: {sig_str}
News: {news_str}

Zasady:
- krótko i konkretnie,
- bez rekomendacji,
- opisz trend, momentum, wolumen, newsy.
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return r.choices[0].message["content"].strip()
    except Exception:
        return "Błąd AI #2"

def ds_ai3_sentiment(news_text):
    if not news_text:
        return "brak newsów — brak analizy"

    text = news_text.lower()

    positive = ["fda", "approval", "buyback", "acquisition"]
    negative = ["debt", "downgrade", "bankruptcy", "offering", "profit warning"]

    pos = any(p in text for p in positive)
    neg = any(n in text for n in negative)

    if pos and not neg:
        return "sentiment pozytywny"
    if neg and not pos:
        return "sentiment negatywny"
    return "sentiment neutralny"

def ds_ai4_fundamental(news_text):
    if not news_text:
        return "brak newsów — brak ryzyk"

    text = news_text.lower()

    risks = []
    if "debt" in text:
        risks.append("zadłużenie")
    if "offering" in text:
        risks.append("emisja akcji")
    if "bankruptcy" in text:
        risks.append("ryzyko bankructwa")
    if "downgrade" in text:
        risks.append("obniżenie ratingu")

    if risks:
        return "ryzyka: " + ", ".join(risks)
    return "brak istotnych ryzyk"

# ============================================================
#  DUAL SCANNER – FUNKCJA RYNKU
# ============================================================

def render_market(tab, market_name):
    with tab:
        st.subheader(f"Rynek: {market_name}")

        key = f"ds_{market_name.replace(' ', '_')}"

        if f"{key}_tickers" not in st.session_state:
            if "GPW" in market_name:
                st.session_state[f"{key}_tickers"] = ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA"]
            else:
                st.session_state[f"{key}_tickers"] = ["SNDL", "NIO", "AAL", "F"]

        if f"{key}_df" not in st.session_state:
            st.session_state[f"{key}_df"] = None

        if f"{key}_spark" not in st.session_state:
            st.session_state[f"{key}_spark"] = {}

        tickers_input = st.text_area(
            "Wpisz swoje tickery (oddzielone przecinkami):",
            value=",".join(st.session_state[f"{key}_tickers"]),
            key=f"{key}_input"
        )

        if st.button("💾 Zapisz listę", key=f"{key}_save"):
            st.session_state[f"{key}_tickers"] = [
                t.strip().upper() for t in tickers_input.split(",") if t.strip()
            ]
            st.success("Zapisano listę tickerów.")

        tickers = st.session_state[f"{key}_tickers"]

        mode = st.selectbox(
            "Tryb analizy:",
            ["Swing", "Day", "Long"],
            key=f"{key}_mode"
        )

        if st.button("🔍 Analiza techniczna (AI #1)", key=f"{key}_scan"):
            if not tickers:
                st.error("Najpierw dodaj spółki.")
                return

            with st.spinner("Analizuję..."):
                data = ds_download(tickers)

                rows = []
                spark = {}

                for t, df in data.items():
                    if df is None or df.empty:
                        continue
                    if len(df) < 80:
                        continue

                    df = ds_indicators(df, mode).dropna()
                    if df is None or df.empty:
                        continue
                    if len(df) < 5:
                        continue

                    last = df.iloc[-1]

                    trend_state, sigs = ds_compute_signals(df)
                    news_text = ds_news_flags(t)

                    score = 0
                    if "rośnie" in trend_state:
                        score += 2
                    if "spada" in trend_state:
                        score -= 2
                    if any("kupujących" in s for s in sigs):
                        score += 1
                    if any("sprzedających" in s for s in sigs):
                        score -= 1

                    color = "green" if "rośnie" in trend_state else "red" if "spada" in trend_state else "orange"

                    rows.append({
                        "Ticker": t,
                        "Kurs": round(last["Close"], 2),
                        "RSI": round(last["RSI"], 1),
                        "Vol x": round(last["Vol_ratio"], 2),
                        "Trend": trend_state,
                        "Sygnały": " | ".join(sigs),
                        "News": news_text,
                        "AI_score": score,
                        "Kolor": color,
                        "Komentarz AI": "",
                        "Sentiment AI": "",
                        "Fundamental AI": ""
                    })

                    spark[t] = df["Close"].tail(20).reset_index(drop=True)

                if not rows:
                    st.warning("Brak spółek z wystarczającą ilością danych.")
                    st.session_state[f"{key}_df"] = None
                    return

                df_out = pd.DataFrame(rows).sort_values("AI_score", ascending=False)
                st.session_state[f"{key}_df"] = df_out
                st.session_state[f"{key}_spark"] = spark

            play_beep()

        df_out = st.session_state.get(f"{key}_df", None)
        spark = st.session_state.get(f"{key}_spark", {})

        if df_out is not None:

            col_left, col_right = st.columns([1, 1])

            with col_left:
                st.subheader("📊 Wyniki analizy technicznej")

                def highlight(row):
                    if row["Kolor"] == "green":
                        return ["background-color:#0f5132;color:white"] * len(row)
                    if row["Kolor"] == "red":
                        return ["background-color:#8b0000;color:white"] * len(row)
                    return ["background-color:#ff8c00;color:black"] * len(row)

                cols_order = [
                    "Ticker", "Kurs", "RSI", "Vol x", "Trend", "Sygnały", "News",
                    "AI_score", "Kolor",
                    "Komentarz AI", "Sentiment AI", "Fundamental AI"
                ]

                st.dataframe(
                    df_out[cols_order].style.apply(highlight, axis=1),
                    use_container_width=True
                )

                st.subheader("📉 Sparklines")
                cols = st.columns(4)
                for i, t in enumerate(df_out["Ticker"]):
                    with cols[i % 4]:
                        st.caption(t)
                        if t in spark:
                            st.line_chart(spark[t])

            with col_right:
                st.subheader("🧠 Wybierz AI")

                ai_choice = st.radio(
                    "Wybierz AI:",
                    ["AI #2 — Komentarz LLM",
                     "AI #3 — Sentiment newsów",
                     "AI #4 — Fundamentalne ryzyka"],
                    key=f"{key}_ai_choice"
                )

                st.subheader("📌 Wybierz spółki do analizy AI")

                selected = []
                for t in df_out["Ticker"]:
                    if st.checkbox(t, key=f"{key}_{t}_chk"):
                        selected.append(t)

                if st.button("💬 Uruchom wybraną AI", key=f"{key}_ai_run"):
                    if not selected:
                        st.warning("Nie wybrano żadnych spółek.")
                    else:
                        with st.spinner("AI pracuje..."):
                            new_rows = []
                            for _, row in df_out.iterrows():
                                if row["Ticker"] in selected:
                                    if ai_choice.startswith("AI #2"):
                                        data_single = ds_download([row["Ticker"]])
                                        df_single = list(data_single.values())[0]

                                        if df_single is None or df_single.empty:
                                            row["Komentarz AI"] = "Brak danych"
                                            new_rows.append(row)
                                            continue

                                        df_single = ds_indicators(df_single, mode).dropna()
                                        if df_single is None or df_single.empty or len(df_single) < 5:
                                            row["Komentarz AI"] = "Za mało danych"
                                            new_rows.append(row)
                                            continue

                                        last = df_single.iloc[-1]
                                        trend_state, sigs = ds_compute_signals(df_single)
                                        comment = ds_ai2_comment(row["Ticker"], last, trend_state, sigs, row["News"])
                                        row["Komentarz AI"] = comment

                                    elif ai_choice.startswith("AI #3"):
                                        comment = ds_ai3_sentiment(row["News"])
                                        row["Sentiment AI"] = comment

                                    else:  # AI #4
                                        comment = ds_ai4_fundamental(row["News"])
                                        row["Fundamental AI"] = comment

                                new_rows.append(row)

                            df_out = pd.DataFrame(new_rows)
                            st.session_state[f"{key}_df"] = df_out

                        st.success("AI zakończyła analizę.")

                        st.dataframe(
                            df_out[cols_order].style.apply(highlight, axis=1),
                            use_container_width=True
                        )

        else:
            st.info("Wpisz tickery, wybierz tryb i uruchom 🔍 Analiza techniczna (AI #1).")

# ============================================================
#  DUAL SCANNER – UI
# ============================================================

st.title("📈 Dual Market Scanner — GPW & USA (4 AI)")

tab_gpw, tab_usa = st.tabs(["🇵🇱 GPW", "🇺🇸 USA"])

render_market(tab_gpw, "GPW")
render_market(tab_usa, "USA")

st.markdown("---")

# ============================================================
#  PONIŻEJ – TWÓJ ORYGINALNY SKANER AI PRO MASTER
# ============================================================

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


def generuj_raport_pojedynczej_spolki(model, ticker, wiersz_danych, dane_tp):
    dane_tekst = wiersz_danych.to_string(index=False)
    dane_tp = dane_tp if isinstance(dane_tp, dict) else {}
    tp_tekst = (
        f"Planowane cele Take Profit: TP1={dane_tp.get('tp1')}, "
        f"TP2={dane_tp.get('tp2')}, TP3={dane_tp.get('tp3')}. Stop Loss={dane_tp.get('sl')}."
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
        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        return "❌ Błąd: Odpowiedź modeli OpenAI jest pusta."
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

    szukaj_frazy = st.text_input(
        "🔍 Szukaj (wpisz Ticker, Formację lub Trend, np. 'Młot', '🟢', 'SNDL'):"
    )
    if szukaj_frazy:
        maska = (
            df_aktywne["Ticker"].str.contains(szukaj_frazy, case=False, na=False)
            | df_aktywne["Trend"].str.contains(szukaj_frazy, case=False, na=False)
            | df_aktywne["Formacja"].str.contains(szukaj_frazy, case=False, na=False)
        )
        df_wyswietlane = df_aktywne[maska]
    else:
        df_wyswietlane = df_aktywne

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

    st.markdown("---")
    st.subheader("🔍 Detale i Wykres Spółki")

    lista_tickerow_do_wyboru = (
        df_wyswietlane["Ticker"].tolist()
        if not df_wyswietlane.empty
        else df_aktywne["Ticker"].tolist()
    )
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

    poziom_tp1 = round(cena_wejscia + odleglosc_sl, 2)
    poziom_tp2 = round(cena_wejscia + (2 * odleglosc_sl), 2)
    poziom_tp3 = round(cena_wejscia + (3 * odleglosc_sl), 2)

    liczba_akcji = (
        int(akceptowalne_ryzyko / odleglosc_sl) if odleglosc_sl > 0 else 0
    )
    calkowity_kapital = round(liczba_akcji * cena_wejscia, 2)

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

    st.markdown("**🎯 Wielopoziomowe Targety Cenowe (Take Profit):**")
    c1, c2, c3 = st.columns(3)
    c1.metric(label="TP1 (Zabezpieczenie 1:1)", value=f"{poziom_tp1} {waluta}")
    c2.metric(label="TP2 (Cel Główny 1:2)", value=f"{poziom_tp2} {waluta}")
    c3.metric(label="TP3 (Rakieta 1:3)", value=f"{poziom_tp3} {waluta}")

    slownik_tp = {
        "sl": poziom_sl,
        "tp1": poziom_tp1,
        "tp2": poziom_tp2,
        "tp3": poziom_tp3,
    }

    if st.button(
        "🧠 Analiza i Ocena Celów przez AI",
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
