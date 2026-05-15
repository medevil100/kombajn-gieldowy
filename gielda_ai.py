```python
import os
import io
import math
import wave
import struct
import base64

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from openai import OpenAI

# ================== USTAWIENIA APLIKACJI ==================

st.set_page_config(
    page_title="📈 Dual Market Scanner — GPW & USA (3× AI: Swing / Day / Long)",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0E1117; color: #E6EDF3; }
    div[data-testid="stDataFrame"] { background-color: #161B22; border: 1px solid #30363D; border-radius: 8px; }
    div.stButton > button:first-child {
        background-color: #00ff66 !important; color: #000000 !important; font-weight: bold !important;
        border-radius: 6px !important; border: none !important; box-shadow: 0 0 12px rgba(0, 255, 102, 0.5);
    }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ================== SECRETS / API ==================

try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    st.error("Błąd: Skonfiguruj 'OPENAI_API_KEY' oraz 'APP_PASSWORD' w Streamlit Secrets.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# ================== AUTORYZACJA ==================

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

# ================== BEEP ==================

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

# ================== DOWNLOAD DANYCH ==================

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

# ================== WSKAŹNIKI: SWING / DAY / LONG ==================

def ds_indicators_all(df):
    df = df.copy()
    delta = df["Close"].diff()

    # Swing
    df["EMA20_s"] = df["Close"].ewm(span=20).mean()
    df["EMA50_s"] = df["Close"].ewm(span=50).mean()
    df["EMA200_s"] = df["Close"].ewm(span=200).mean()
    gain14 = delta.clip(lower=0).rolling(14).mean()
    loss14 = (-delta.clip(upper=0)).rolling(14).mean()
    rs14 = gain14 / loss14
    df["RSI14_s"] = 100 - (100 / (1 + rs14))
    df["Mom10_s"] = df["Close"].diff(10)
    df["Fibo60_high_s"] = df["Close"].rolling(60).max()
    df["Fibo60_low_s"] = df["Close"].rolling(60).min()

    # Day
    df["EMA9_d"] = df["Close"].ewm(span=9).mean()
    df["EMA20_d"] = df["Close"].ewm(span=20).mean()
    df["EMA50_d"] = df["Close"].ewm(span=50).mean()
    gain7 = delta.clip(lower=0).rolling(7).mean()
    loss7 = (-delta.clip(upper=0)).rolling(7).mean()
    rs7 = gain7 / loss7
    df["RSI7_d"] = 100 - (100 / (1 + rs7))
    df["Mom3_d"] = df["Close"].diff(3)
    df["Fibo20_high_d"] = df["Close"].rolling(20).max()
    df["Fibo20_low_d"] = df["Close"].rolling(20).min()

    # Long
    df["EMA50_l"] = df["Close"].ewm(span=50).mean()
    df["EMA100_l"] = df["Close"].ewm(span=100).mean()
    df["EMA200_l"] = df["Close"].ewm(span=200).mean()
    df["Fibo120_high_l"] = df["Close"].rolling(120).max()
    df["Fibo120_low_l"] = df["Close"].rolling(120).min()

    df["Vol_avg20"] = df["Volume"].rolling(20).mean()
    df["Vol_ratio"] = df["Volume"] / df["Vol_avg20"]

    return df

# ================== NEWS ==================

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

# ================== SYGNAŁY: SWING / DAY / LONG ==================

def ds_signals_swing(df):
    last = df.iloc[-1]
    sig = []

    up = last["EMA20_s"] > last["EMA50_s"] > last["EMA200_s"]
    down = last["EMA20_s"] < last["EMA50_s"] < last["EMA200_s"]

    if up and last["RSI14_s"] > 55:
        trend = "swing: mocny trend wzrostowy"
    elif down and last["RSI14_s"] < 45:
        trend = "swing: mocny trend spadkowy"
    elif up:
        trend = "swing: trend wzrostowy"
    elif down:
        trend = "swing: trend spadkowy"
    else:
        trend = "swing: trend boczny / niejednoznaczny"

    sig.append(trend)

    if last["Close"] >= last["Fibo60_high_s"] * 0.999:
        sig.append("swing: wybicie Fibo60 HIGH")
    if last["Close"] <= last["Fibo60_low_s"] * 1.001:
        sig.append("swing: wybicie Fibo60 LOW")

    if last["Mom10_s"] > 0:
        sig.append("swing: dodatnie momentum 10")
    if last["Mom10_s"] < 0:
        sig.append("swing: ujemne momentum 10")

    if last["Vol_ratio"] > 2:
        sig.append("swing: bardzo wysoki wolumen")
    elif last["Vol_ratio"] > 1.3:
        sig.append("swing: podwyższony wolumen")

    score = 0
    if "wzrostowy" in trend:
        score += 3
    if "spadkowy" in trend:
        score -= 3
    if "dodatnie momentum" in " ".join(sig):
        score += 1
    if "ujemne momentum" in " ".join(sig):
        score -= 1
    if "bardzo wysoki wolumen" in sig:
        score += 1

    return trend, sig, score, last

def ds_signals_day(df):
    last = df.iloc[-1]
    sig = []

    up = last["EMA9_d"] > last["EMA20_d"] > last["EMA50_d"]
    down = last["EMA9_d"] < last["EMA20_d"] < last["EMA50_d"]

    if up and last["RSI7_d"] > 55:
        trend = "day: mocny trend wzrostowy"
    elif down and last["RSI7_d"] < 45:
        trend = "day: mocny trend spadkowy"
    elif up:
        trend = "day: trend wzrostowy"
    elif down:
        trend = "day: trend spadkowy"
    else:
        trend = "day: trend boczny / niejednoznaczny"

    sig.append(trend)

    if last["Close"] >= last["Fibo20_high_d"] * 0.999:
        sig.append("day: wybicie Fibo20 HIGH")
    if last["Close"] <= last["Fibo20_low_d"] * 1.001:
        sig.append("day: wybicie Fibo20 LOW")

    if last["Mom3_d"] > 0:
        sig.append("day: dodatnie momentum 3")
    if last["Mom3_d"] < 0:
        sig.append("day: ujemne momentum 3")

    if last["Vol_ratio"] > 2:
        sig.append("day: bardzo wysoki wolumen")
    elif last["Vol_ratio"] > 1.3:
        sig.append("day: podwyższony wolumen")

    score = 0
    if "wzrostowy" in trend:
        score += 3
    if "spadkowy" in trend:
        score -= 3
    if "dodatnie momentum" in " ".join(sig):
        score += 1
    if "ujemne momentum" in " ".join(sig):
        score -= 1
    if "bardzo wysoki wolumen" in sig:
        score += 1

    return trend, sig, score, last

def ds_signals_long(df):
    last = df.iloc[-1]
    sig = []

    up = last["EMA50_l"] > last["EMA100_l"] > last["EMA200_l"]
    down = last["EMA50_l"] < last["EMA100_l"] < last["EMA200_l"]

    if up:
        trend = "long: trend wzrostowy"
    elif down:
        trend = "long: trend spadkowy"
    else:
        trend = "long: trend boczny / niejednoznaczny"

    sig.append(trend)

    if last["Close"] >= last["Fibo120_high_l"] * 0.999:
        sig.append("long: wybicie Fibo120 HIGH")
    if last["Close"] <= last["Fibo120_low_l"] * 1.001:
        sig.append("long: wybicie Fibo120 LOW")

    if last["Vol_ratio"] > 2:
        sig.append("long: bardzo wysoki wolumen")
    elif last["Vol_ratio"] > 1.3:
        sig.append("long: podwyższony wolumen")

    score = 0
    if "wzrostowy" in trend:
        score += 2
    if "spadkowy" in trend:
        score -= 2
    if "bardzo wysoki wolumen" in sig:
        score += 1

    return trend, sig, score, last

# ================== 3× AI: SWING / DAY / LONG ==================

def ai_swing_comment(ticker, tech, news_flags):
    prompt = f"""
Jesteś zawodowym traderem swingowym.

DANE_TECHNICZNE (SWING, JSON):
{tech}

ZADANIE:
- Zrób analizę SWING (kilka dni–tygodni) dla spółki {ticker}.
- Skup się na: trendzie swingowym, momentum 10, RSI14, wolumenie, wybiciach Fibo60.
- Uwzględnij flagi newsów: {news_flags or "brak"}.
- Napisz 2–3 zdania, konkretnie, pod telefon.
- Zero słów KUP/SPRZEDAJ.
- Zero kopiowania JSON.
- Tylko interpretacja.
"""
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI Swing: {e}"

def ai_day_comment(ticker, tech, news_flags):
    prompt = f"""
Jesteś daytraderem.

DANE_TECHNICZNE (DAY, JSON):
{tech}

ZADANIE:
- Zrób analizę DAY (krótkie ruchy intraday/sesja) dla spółki {ticker}.
- Skup się na: trendzie day (EMA9/20/50), momentum 3, RSI7, wolumenie, wybiciach Fibo20.
- Uwzględnij flagi newsów: {news_flags or "brak"}.
- Napisz 2–3 zdania, bardzo konkretnie, pod telefon.
- Zero słów KUP/SPRZEDAJ.
- Zero kopiowania JSON.
- Tylko interpretacja.
"""
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI Day: {e}"

def ai_long_comment(ticker, tech, news_flags):
    prompt = f"""
Jesteś analitykiem długoterminowym.

DANE_TECHNICZNE (LONG, JSON):
{tech}

ZADANIE:
- Zrób analizę LONG (tygodnie–miesiące) dla spółki {ticker}.
- Skup się na: trendzie EMA50/100/200, wybiciach Fibo120, wolumenie, ogólnym kierunku.
- Uwzględnij flagi newsów: {news_flags or "brak"}.
- Napisz 2–3 zdania, spokojnie, pod telefon.
- Zero słów KUP/SPRZEDAJ.
- Zero kopiowania JSON.
- Tylko interpretacja.
"""
    try:
        r = client.chat.completions.create(
            model="o3-mini",
            reasoning_effort="high",
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI Long: {e}"

# ================== RYNEK – RENDER ==================

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
            "Tryb analizy technicznej (bez LLM):",
            ["Swing", "Day", "Long"],
            index=0,
            key=f"{key}_mode"
        )

        if st.button("🔍 Analiza techniczna (bez AI LLM)", key=f"{key}_scan"):
            if not tickers:
                st.error("Najpierw dodaj spółki.")
                return

            with st.spinner("Liczenie wskaźników..."):
                data = ds_download(tickers)

                rows = []
                spark = {}

                for t, df in data.items():
                    if df is None or df.empty:
                        continue
                    if len(df) < 120:
                        continue

                    df = ds_indicators_all(df).dropna()
                    if df is None or df.empty or len(df) < 10:
                        continue

                    if mode == "Swing":
                        trend_state, sigs, score, last = ds_signals_swing(df)
                        rsi_main = last["RSI14_s"]
                    elif mode == "Day":
                        trend_state, sigs, score, last = ds_signals_day(df)
                        rsi_main = last["RSI7_d"]
                    else:
                        trend_state, sigs, score, last = ds_signals_long(df)
                        rsi_main = last["RSI14_s"] if "RSI14_s" in df.columns else 50

                    news_raw = ds_news_raw(t)
                    news_flags = ds_news_flags(news_raw)

                    color = "green" if "wzrostowy" in trend_state else "red" if "spadkowy" in trend_state else "orange"

                    rows.append({
                        "Ticker": t,
                        "Kurs": round(last["Close"], 2),
                        "RSI_main": round(rsi_main, 1),
                        "Vol x": round(last["Vol_ratio"], 2),
                        "Trend": trend_state,
                        "Sygnały": " | ".join(sigs),
                        "News_flags": news_flags,
                        "News_raw": news_raw,
                        "Score": score,
                        "Kolor": color,
                        "AI_Swing": "",
                        "AI_Day": "",
                        "AI_Long": "",
                    })

                    spark[t] = df["Close"].tail(30).reset_index(drop=True)

                if not rows:
                    st.warning("Brak spółek z wystarczającą ilością danych.")
                    st.session_state[f"{key}_df"] = None
                    return

                df_out = pd.DataFrame(rows).sort_values("Score", ascending=False)
                st.session_state[f"{key}_df"] = df_out
                st.session_state[f"{key}_spark"] = spark

            play_beep()

        df_out = st.session_state.get(f"{key}_df", None)
        spark = st.session_state.get(f"{key}_spark", {})

        if df_out is not None:

            col_left, col_right = st.columns([1.3, 1])

            with col_left:
                st.subheader("📊 Wyniki analizy technicznej (bez LLM)")

                def highlight(row):
                    if row["Kolor"] == "green":
                        return ["background-color:#0f5132;color:white"] * len(row)
                    if row["Kolor"] == "red":
                        return ["background-color:#8b0000;color:white"] * len(row)
                    return ["background-color:#ff8c00;color:black"] * len(row)

                cols_order = [
                    "Ticker", "Kurs", "RSI_main", "Vol x",
                    "Trend", "Sygnały", "News_flags",
                    "Score", "Kolor",
                    "AI_Swing", "AI_Day", "AI_Long",
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
                st.subheader("🧠 Wybierz AI do analizy LLM")

                ai_choice = st.selectbox(
                    "Które AI ma zrobić analizę?",
                    [
                        "AI Swing — analiza swingowa (gpt-4o-mini)",
                        "AI Day — analiza daytradingowa (gpt-4o)",
                        "AI Long — analiza długoterminowa (o3-mini)",
                    ],
                    key=f"{key}_ai_choice",
                )

                st.markdown("### 📌 Wybierz spółki do analizy AI:")

                selected = []
                for t in df_out["Ticker"]:
                    if st.checkbox(f"{t}", key=f"{key}_{t}_chk"):
                        selected.append(t)

                if st.button("🚀 Uruchom wybrane AI", key=f"{key}_ai_run"):
                    if not selected:
                        st.warning("Nie wybrano żadnych spółek.")
                    else:
                        with st.spinner("AI analizuje wybrane spółki..."):
                            new_rows = []

                            for _, row in df_out.iterrows():
                                if row["Ticker"] in selected:
                                    news_flags = row["News_flags"]

                                    if ai_choice.startswith("AI Swing"):
                                        tech = {
                                            "close": row["Kurs"],
                                            "rsi14": row["RSI_main"],
                                            "vol_ratio": row["Vol x"],
                                            "trend": row["Trend"],
                                            "signals": row["Sygnały"].split(" | "),
                                        }
                                        row["AI_Swing"] = ai_swing_comment(
                                            row["Ticker"], tech, news_flags
                                        )

                                    elif ai_choice.startswith("AI Day"):
                                        tech = {
                                            "close": row["Kurs"],
                                            "rsi7": row["RSI_main"],
                                            "vol_ratio": row["Vol x"],
                                            "trend": row["Trend"],
                                            "signals": row["Sygnały"].split(" | "),
                                        }
                                        row["AI_Day"] = ai_day_comment(
                                            row["Ticker"], tech, news_flags
                                        )

                                    else:  # AI Long
                                        tech = {
                                            "close": row["Kurs"],
                                            "rsi": row["RSI_main"],
                                            "vol_ratio": row["Vol x"],
                                            "trend": row["Trend"],
                                            "signals": row["Sygnały"].split(" | "),
                                        }
                                        row["AI_Long"] = ai_long_comment(
                                            row["Ticker"], tech, news_flags
                                        )

                                new_rows.append(row)

                            df_out = pd.DataFrame(new_rows)
                            st.session_state[f"{key}_df"] = df_out

                        st.success("AI zakończyła analizę.")

                        st.dataframe(
                            df_out[cols_order].style.apply(highlight, axis=1),
                            use_container_width=True,
                        )

        else:
            st.info("Wpisz tickery, wybierz tryb (Swing/Day/Long) i uruchom analizę techniczną.")

# ================== UI GŁÓWNE ==================

st.title("📈 Dual Market Scanner — GPW & USA (3× AI: Swing / Day / Long)")

tab_gpw, tab_usa = st.tabs(["🇵🇱 GPW", "🇺🇸 USA"])

render_market(tab_gpw, "GPW")
render_market(tab_usa, "USA")
```
