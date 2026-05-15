import os
import time
import io
import wave
import math
import struct
import base64

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

st.set_page_config(
    page_title="Dual Market + Skaner AI Pro Master",
    page_icon="📈",
    layout="wide",
)

# --- CSS ---
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
#  BEEP
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
#  DUAL SCANNER – DOWNLOAD
# ============================================================

@st.cache_data(show_spinner=False)
def ds_download(tickers, period="240d", interval="1d"):
    if not tickers:
        return {}
    data = yf.download(
        tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
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
#  DUAL SCANNER – HYBRYDOWE WSKAŹNIKI (Swing + Day + Long)
# ============================================================

def ds_indicators_hybrid(df):
    df = df.copy()

    # Swing
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["EMA200"] = df["Close"].ewm(span=200).mean()
    delta = df["Close"].diff()
    gain14 = delta.clip(lower=0).rolling(14).mean()
    loss14 = (-delta.clip(upper=0)).rolling(14).mean()
    rs14 = gain14 / loss14
    df["RSI14"] = 100 - (100 / (1 + rs14))
    df["Fibo60_high"] = df["Close"].rolling(60).max()
    df["Fibo60_low"] = df["Close"].rolling(60).min()
    df["Mom10"] = df["Close"].diff(10)

    # Day
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA20_d"] = df["Close"].ewm(span=20).mean()
    df["EMA50_d"] = df["Close"].ewm(span=50).mean()
    gain7 = delta.clip(lower=0).rolling(7).mean()
    loss7 = (-delta.clip(upper=0)).rolling(7).mean()
    rs7 = gain7 / loss7
    df["RSI7"] = 100 - (100 / (1 + rs7))
    df["Fibo20_high"] = df["Close"].rolling(20).max()
    df["Fibo20_low"] = df["Close"].rolling(20).min()
    df["Mom3"] = df["Close"].diff(3)

    # Long
    df["EMA50_l"] = df["Close"].ewm(span=50).mean()
    df["EMA100_l"] = df["Close"].ewm(span=100).mean()
    df["EMA200_l"] = df["Close"].ewm(span=200).mean()
    df["Fibo120_high"] = df["Close"].rolling(120).max()
    df["Fibo120_low"] = df["Close"].rolling(120).min()

    df["Vol_avg20"] = df["Volume"].rolling(20).mean()
    df["Vol_ratio"] = df["Volume"] / df["Vol_avg20"]

    df["Trend_swing"] = df["EMA20"] - df["EMA50"]
    df["Trend_day"] = df["EMA9"] - df["EMA20_d"]
    df["Trend_long"] = df["EMA50_l"] - df["EMA100_l"]

    return df

# ============================================================
#  DUAL SCANNER – NEWS
# ============================================================

def ds_news_raw(ticker):
    try:
        tk = yf.Ticker(ticker)
        news = tk.news or []
    except Exception:
        return ""
    text = ""
    for n in news[:8]:
        text += f" {n.get('title','')} {n.get('summary','')}"
    return text.strip()

def ds_news_flags(text):
    if not text:
        return ""
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
#  DUAL SCANNER – SYGNAŁY HYBRYDOWE
# ============================================================

def ds_compute_signals_hybrid(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signals = []

    # Multi‑frame trend
    swing_up = last["EMA20"] > last["EMA50"] > last["EMA200"]
    swing_down = last["EMA20"] < last["EMA50"] < last["EMA200"]
    day_up = last["EMA9"] > last["EMA20_d"] > last["EMA50_d"]
    day_down = last["EMA9"] < last["EMA20_d"] < last["EMA50_d"]
    long_up = last["EMA50_l"] > last["EMA100_l"] > last["EMA200_l"]
    long_down = last["EMA50_l"] < last["EMA100_l"] < last["EMA200_l"]

    if swing_up and day_up and long_up and last["RSI14"] > 55:
        trend_state = "mocny trend wzrostowy (Swing+Day+Long)"
    elif swing_down and day_down and long_down and last["RSI14"] < 45:
        trend_state = "mocny trend spadkowy (Swing+Day+Long)"
    elif (swing_up or day_up or long_up) and last["RSI14"] > 50:
        trend_state = "trend wzrostowy mieszany"
    elif (swing_down or day_down or long_down) and last["RSI14"] < 50:
        trend_state = "trend spadkowy mieszany"
    else:
        trend_state = "trend boczny / niejednoznaczny"

    signals.append(trend_state)

    # Fibo
    if last["Close"] >= last["Fibo20_high"] * 0.999:
        signals.append("wybicie Fibo20 HIGH")
    if last["Close"] <= last["Fibo20_low"] * 1.001:
        signals.append("wybicie Fibo20 LOW")
    if last["Close"] >= last["Fibo60_high"] * 0.999:
        signals.append("wybicie Fibo60 HIGH")
    if last["Close"] <= last["Fibo60_low"] * 1.001:
        signals.append("wybicie Fibo60 LOW")

    # Momentum
    if last["Mom3"] > 0 and last["Mom10"] > 0:
        signals.append("mocne momentum wzrostowe (3/10)")
    if last["Mom3"] < 0 and last["Mom10"] < 0:
        signals.append("mocne momentum spadkowe (3/10)")

    # Vol
    if last["Vol_ratio"] > 2:
        signals.append("bardzo wysoki wolumen")
    elif last["Vol_ratio"] > 1.3:
        signals.append("podwyższony wolumen")

    # RSI
    if last["RSI14"] > 70:
        signals.append("RSI14 wykupienie")
    elif last["RSI14"] < 30:
        signals.append("RSI14 wyprzedanie")

    # Kupujący / sprzedający
    if last["Close"] > prev["Close"] and last["Vol_ratio"] > 1.3 and last["RSI7"] > prev["RSI7"]:
        signals.append("wzrost kupujących (RSI7 + wolumen)")
    if last["Close"] < prev["Close"] and last["Vol_ratio"] > 1.3 and last["RSI7"] < prev["RSI7"]:
        signals.append("wzrost sprzedających (RSI7 + wolumen)")

    # Score
    score = 0
    if "wzrostowy" in trend_state:
        score += 3
    if "spadkowy" in trend_state:
        score -= 3
    if "mocne momentum wzrostowe" in signals:
        score += 2
    if "mocne momentum spadkowe" in signals:
        score -= 2
    if "bardzo wysoki wolumen" in signals:
        score += 1
    if "RSI14 wykupienie" in signals:
        score -= 1
    if "RSI14 wyprzedanie" in signals:
        score += 1
    if any("kupujących" in s for s in signals):
        score += 1
    if any("sprzedających" in s for s in signals):
        score -= 1

    return trend_state, signals, score

# ============================================================
#  DUAL SCANNER – AI #2 / #3 / #4 (o3‑mini)
# ============================================================

def ds_ai2_comment(ticker, last, trend_state, signals, news_flags, mode_desc):
    sig_str = "; ".join(signals)
    prompt = f"""
Jesteś zawodowym traderem. Zrób krótką, konkretną analizę techniczną spółki.

Ticker: {ticker}
Cena zamknięcia: {last['Close']:.2f}
Zmiana dzienna: {((last['Close'] / last['Open']) - 1) * 100:.2f}%
RSI14: {last['RSI14']:.1f}
RSI7: {last['RSI7']:.1f}
Momentum 3: {last['Mom3']:.2f}
Momentum 10: {last['Mom10']:.2f}
Vol ratio (20): {last['Vol_ratio']:.2f}
Trend hybrydowy: {trend_state}
Sygnały: {sig_str}
Tryb: {mode_desc}
Flagi newsów: {news_flags or "brak"}

Zasady:
- 2–3 zdania,
- bez słów KUP/SPRZEDAJ,
- opisz trend (krótko/średnio/długoterminowy), momentum, wolumen i wpływ newsów,
- język: polski, styl: konkretny, pod telefon.
"""
    try:
        r = client.chat.completions.create(
            model="o3-mini",
            reasoning_effort="medium",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI #2: {e}"

def ds_ai3_sentiment(news_text):
    if not news_text:
        return "Brak newsów — brak analizy sentymentu."
    prompt = f"""
Masz newsy o spółce (tytuły + skróty):

\"\"\"{news_text[:4000]}\"\"\"

Oceń:
- czy sentyment jest pozytywny, neutralny czy negatywny,
- wskaż 1–2 kluczowe powody.

Forma:
- 1 zdanie werdyktu (Pozytywny/Neutralny/Negatywny),
- 1 zdanie uzasadnienia,
- język: polski, krótko, pod telefon.
"""
    try:
        r = client.chat.completions.create(
            model="o3-mini",
            reasoning_effort="medium",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI #3: {e}"

def ds_ai4_fundamental(news_text):
    if not news_text:
        return "Brak newsów — brak wykrytych ryzyk fundamentalnych."
    prompt = f"""
Masz newsy o spółce (tytuły + skróty):

\"\"\"{news_text[:4000]}\"\"\"

Wypisz krótko:
- jakie ryzyka fundamentalne są widoczne (np. zadłużenie, emisja akcji, bankructwo, obniżka ratingu, problemy regulacyjne),
- jeśli brak istotnych ryzyk — napisz to wprost.

Forma:
- lista punktów z emoji,
- język: polski, krótko, pod telefon.
"""
    try:
        r = client.chat.completions.create(
            model="o3-mini",
            reasoning_effort="medium",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI #4: {e}"
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
            "Tryb analizy (opis tylko dla AI #2):",
            ["Swing", "Day", "Long", "Hybrid"],
            index=3,
            key=f"{key}_mode"
        )

        mode_desc = {
            "Swing": "swing trading (kilka dni–tygodni)",
            "Day": "day trading (krótkie ruchy)",
            "Long": "dłuższy horyzont",
            "Hybrid": "hybrydowa analiza multi‑frame (Swing+Day+Long)",
        }[mode]

        if st.button("🔍 AI #1 — Hybrydowa analiza techniczna", key=f"{key}_scan"):
            if not tickers:
                st.error("Najpierw dodaj spółki.")
                return

            with st.spinner("AI #1 analizuje technicznie..."):
                data = ds_download(tickers)

                rows = []
                spark = {}

                for t, df in data.items():
                    if df is None or df.empty:
                        continue
                    if len(df) < 120:
                        continue

                    df = ds_indicators_hybrid(df).dropna()
                    if df is None or df.empty or len(df) < 10:
                        continue

                    last = df.iloc[-1]
                    trend_state, sigs, score = ds_compute_signals_hybrid(df)
                    news_raw = ds_news_raw(t)
                    news_flags = ds_news_flags(news_raw)

                    color = "green" if "wzrostowy" in trend_state else "red" if "spadkowy" in trend_state else "orange"

                    rows.append({
                        "Ticker": t,
                        "Kurs": round(last["Close"], 2),
                        "RSI14": round(last["RSI14"], 1),
                        "RSI7": round(last["RSI7"], 1),
                        "Vol x": round(last["Vol_ratio"], 2),
                        "Trend": trend_state,
                        "Sygnały": " | ".join(sigs),
                        "News_flags": news_flags,
                        "News_raw": news_raw,
                        "AI_score": score,
                        "Kolor": color,
                        "Komentarz AI": "",
                        "Sentiment AI": "",
                        "Fundamental AI": "",
                    })

                    spark[t] = df["Close"].tail(30).reset_index(drop=True)

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

            col_left, col_right = st.columns([1.2, 1])

            with col_left:
                st.subheader("📊 Wyniki AI #1 — Hybrydowa analiza techniczna")

                def highlight(row):
                    if row["Kolor"] == "green":
                        return ["background-color:#0f5132;color:white"] * len(row)
                    if row["Kolor"] == "red":
                        return ["background-color:#8b0000;color:white"] * len(row)
                    return ["background-color:#ff8c00;color:black"] * len(row)

                cols_order = [
                    "Ticker", "Kurs", "RSI14", "RSI7", "Vol x",
                    "Trend", "Sygnały", "News_flags",
                    "AI_score", "Kolor",
                    "Komentarz AI", "Sentiment AI", "Fundamental AI",
                ]

                st.dataframe(
                    df_out[cols_order].style.apply(highlight, axis=1),
                    use_container_width=True,
                )

                st.subheader("📉 Sparklines (30 sesji)")
                cols = st.columns(4)
                for i, t in enumerate(df_out["Ticker"]):
                    with cols[i % 4]:
                        st.caption(t)
                        if t in spark:
                            st.line_chart(spark[t], height=120)

            with col_right:
                st.subheader("🧠 AI #2 / #3 / #4")

                ai_choice = st.radio(
                    "Wybierz AI:",
                    [
                        "AI #2 — Komentarz LLM (pełna analiza)",
                        "AI #3 — Sentiment newsów",
                        "AI #4 — Fundamentalne ryzyka",
                    ],
                    key=f"{key}_ai_choice",
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
                                        # pełna analiza techniczna + newsy
                                        comment = ds_ai2_comment(
                                            row["Ticker"],
                                            last=pd.Series({
                                                "Close": row["Kurs"],
                                                "RSI14": row["RSI14"],
                                                "RSI7": row["RSI7"],
                                                "Mom3": 0.0,
                                                "Mom10": 0.0,
                                                "Vol_ratio": row["Vol x"],
                                                "Open": row["Kurs"],  # przybliżenie
                                            }),
                                            trend_state=row["Trend"],
                                            signals=row["Sygnały"].split(" | ") if row["Sygnały"] else [],
                                            news_flags=row["News_flags"],
                                            mode_desc=mode_desc,
                                        )
                                        row["Komentarz AI"] = comment

                                    elif ai_choice.startswith("AI #3"):
                                        comment = ds_ai3_sentiment(row["News_raw"])
                                        row["Sentiment AI"] = comment

                                    else:  # AI #4
                                        comment = ds_ai4_fundamental(row["News_raw"])
                                        row["Fundamental AI"] = comment

                                new_rows.append(row)

                            df_out = pd.DataFrame(new_rows)
                            st.session_state[f"{key}_df"] = df_out

                        st.success("AI zakończyła analizę.")

                        st.dataframe(
                            df_out[cols_order].style.apply(highlight, axis=1),
                            use_container_width=True,
                        )

        else:
            st.info("Wpisz tickery, wybierz tryb i uruchom 🔍 AI #1 — Hybrydowa analiza techniczna.")

# ============================================================
#  DUAL SCANNER – UI GŁÓWNE
# ============================================================

st.title("📈 Dual Market Scanner — GPW & USA (4 AI, HYBRID + o3‑mini)")

tab_gpw, tab_usa = st.tabs(["🇵🇱 GPW", "🇺🇸 USA"])

render_market(tab_gpw, "GPW")
render_market(tab_usa, "USA")

st.markdown("---")
# --- TRWAŁY ZAPIS DO PLIKÓW ---
def wczytaj_liste_z_pliku(rynek):
    
