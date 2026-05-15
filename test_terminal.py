
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from openai import OpenAI
import io, wave, math, struct, base64

# ============================================================
#  OPENAI
# ============================================================

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ============================================================
#  DŹWIĘK ALERTU
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
#  POBIERANIE DANYCH
# ============================================================

def download(tickers):
    if not tickers:
        return {}
    data = yf.download(
        tickers,
        period="180d",
        interval="1d",
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
#  WSKAŹNIKI – TRYBY
# ============================================================

def indicators(df, mode):
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
#  NEWS – FLAGI
# ============================================================

def news_flags(ticker):
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
#  SYGNAŁY 1–7
# ============================================================

def compute_signals(df):
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
#  AI #2 — KOMENTARZ LLM
# ============================================================

def ai2_comment(ticker, last, trend_state, signals, news_text):
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
    except:
        return "Błąd AI #2"

# ============================================================
#  AI #3 — SENTIMENT NEWSÓW
# ============================================================

def ai3_sentiment(news_text):
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

# ============================================================
#  AI #4 — FUNDAMENTALNE RYZYKA
# ============================================================

def ai4_fundamental(news_text):
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
#  UI — GPW / USA
# ============================================================

st.set_page_config(page_title="Dual Market Scanner", layout="wide")

st.title("📈 Dual Market Scanner — GPW & USA (4 AI)")

tab_gpw, tab_usa = st.tabs(["🇵🇱 GPW", "🇺🇸 USA"])

# ============================================================
#  FUNKCJA RYNKU
# ============================================================

def render_market(tab, market_name):
    with tab:
        st.header(f"Rynek: {market_name}")

        key = market_name.replace(" ", "_")

        if f"{key}_tickers" not in st.session_state:
            st.session_state[f"{key}_tickers"] = []

        if f"{key}_df" not in st.session_state:
            st.session_state[f"{key}_df"] = None

        tickers_input = st.text_area(
            "Wpisz swoje tickery:",
            value=",".join(st.session_state[f"{key}_tickers"]),
            key=f"{key}_input"
        )

        if st.button("💾 Zapisz listę", key=f"{key}_save"):
            st.session_state[f"{key}_tickers"] = [
                t.strip().upper() for t in tickers_input.split(",") if t.strip()
            ]
            st.success("Zapisano!")

        tickers = st.session_state[f"{key}_tickers"]

        mode = st.selectbox(
            "Tryb analizy:",
            ["Swing", "Day", "Long"],
            key=f"{key}_mode"
        )

        # ============================================================
        #  ANALIZA TECHNICZNA (AI #1)
        # ============================================================

        if st.button("🔍 Analiza techniczna (AI #1)", key=f"{key}_scan"):
            if not tickers:
                st.error("Najpierw dodaj spółki.")
                return

            with st.spinner("Analizuję..."):
                data = download(tickers)

                rows = []
                spark = {}

                for t, df in data.items():
                    if df is None or df.empty:
                        continue
                    if len(df) < 80:
                        continue

                    df = indicators(df, mode).dropna()
                    if df is None or df.empty:
                        continue
                    if len(df) < 5:
                        continue

                    last = df.iloc[-1]

                    trend_state, sigs = compute_signals(df)
                    news_text = news_flags(t)

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

            # ---------------- LEFT: TABELA ----------------

            with col_left:
                st.subheader("📊 Wyniki analizy technicznej")

                def highlight(row):
                    if row["Kolor"] == "green":
                        return ["background-color:#0f5132;color:white"] * len(row)
                    if row["Kolor"] == "red":
                        return ["background-color:#8b0000;color:white"] * len(row)
                    return ["background-color:#ff8c00;color:black"] * len(row)

                st.dataframe(
                    df_out.style.apply(highlight, axis=1),
                    use_container_width=True
                )

                st.subheader("📉 Sparklines")
                cols = st.columns(4)
                for i, t in enumerate(df_out["Ticker"]):
                    with cols[i % 4]:
                        st.caption
