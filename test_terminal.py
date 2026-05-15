import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import io, wave, math, struct, base64
from datetime import datetime
from openai import OpenAI

# ============================================================
#  🔑 OPENAI – klucz z secrets
# ============================================================

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ============================================================
#  🔊 DŹWIĘK ALERTU
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
#  📊 FUNKCJE ANALITYCZNE
# ============================================================

def download(tickers):
    if not tickers:
        return {}
    data = yf.download(
        tickers,
        period="90d",
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

def indicators(df):
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["EMA200"] = df["Close"].ewm(span=200).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # Fibo high/low
    df["Fibo_high"] = df["Close"].rolling(60).max()
    df["Fibo_low"] = df["Close"].rolling(60).min()

    # Trend
    df["Trend"] = df["EMA20"] - df["EMA50"]

    # Volume
    df["Vol_avg"] = df["Volume"].rolling(20).mean()
    df["Vol_ratio"] = df["Volume"] / df["Vol_avg"]

    return df

def classify_signal(df):
    last = df.iloc[-1]

    if last["EMA20"] > last["EMA50"] > last["EMA200"] and last["RSI"] > 55:
        return "green"

    if 45 <= last["RSI"] <= 55:
        return "orange"

    return "red"

def ai_score(df):
    last = df.iloc[-1]
    score = 0
    if last["EMA20"] > last["EMA50"]:
        score += 1
    if last["EMA50"] > last["EMA200"]:
        score += 1
    if last["RSI"] > 55:
        score += 1
    if last["Vol_ratio"] > 1.5:
        score += 1
    if last["Trend"] > 0:
        score += 1
    return score

# ============================================================
#  🤖 KOMENTARZ LLM (GPT‑4o‑mini)
# ============================================================

def llm_comment(ticker, last):
    prompt = f"""
Jesteś profesjonalnym analitykiem giełdowym. Na podstawie poniższych danych wygeneruj
krótki komentarz (1–2 zdania) po polsku, opisujący sytuację techniczną spółki.

Dane:
Ticker: {ticker}
Cena zamknięcia: {last['Close']:.2f}
RSI: {last['RSI']:.2f}
EMA20: {last['EMA20']:.2f}
EMA50: {last['EMA50']:.2f}
EMA200: {last['EMA200']:.2f}
Wolumen ratio: {last['Vol_ratio']:.2f}
Trend (EMA20-EMA50): {last['Trend']:.2f}
Fibo HIGH (60 dni): {last['Fibo_high']:.2f}
Fibo LOW (60 dni): {last['Fibo_low']:.2f}

Zasady:
- pisz krótko i konkretnie,
- nie używaj ogólników,
- skup się na sygnałach technicznych,
- nie dodawaj żadnych ostrzeżeń ani disclaimers.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=120
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        return f"Błąd LLM: {e}"

# ============================================================
#  🧠 UI + LOGIKA
# ============================================================

st.set_page_config(page_title="Custom AI Scanner", layout="wide")

st.title("📈🤖 Custom AI Stock Scanner")
st.caption("Twoje własne spółki + AI ranking + mini‑sparklines + auto‑skan + komentarze LLM.")

# -----------------------------------------
#  ZAPIS / ODCZYT LISTY SPOŁEK
# -----------------------------------------

if "saved_tickers" not in st.session_state:
    st.session_state.saved_tickers = []

st.sidebar.header("⚙️ Lista spółek")

tickers_input = st.sidebar.text_area(
    "Wpisz swoje tickery (oddzielone przecinkami):",
    value=",".join(st.session_state.saved_tickers)
)

if st.sidebar.button("💾 Zapisz listę spółek"):
    st.session_state.saved_tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    st.sidebar.success("Zapisano!")

tickers = st.session_state.saved_tickers

# -----------------------------------------
#  AUTO‑SKAN CO X MINUT
# -----------------------------------------

auto_minutes = st.sidebar.slider(
    "Auto‑skan co (minuty, 0 = wyłącz)",
    min_value=0,
    max_value=60,
    value=0,
    step=5
)

auto_trigger = False
if auto_minutes > 0:
    st.experimental_set_query_params(ts=datetime.utcnow().isoformat())
    auto_trigger = True

run_button = st.button("🔍 Skanuj teraz")
run_scan = run_button or auto_trigger

# -----------------------------------------
#  SKAN + AI RANKING + SPARKLINES + LLM
# -----------------------------------------

if run_scan:
    if not tickers:
        st.error("Najpierw dodaj spółki.")
        st.stop()

    with st.spinner("Pobieram dane i analizuję..."):
        data = download(tickers)

        results = []
        spark_data = {}

        for t, df in data.items():
            if len(df) < 60:
                continue
            df = indicators(df)
            color = classify_signal(df)
            score = ai_score(df)
            last = df.iloc[-1]

            # 🔥 komentarz LLM
            comment = llm_comment(t, last)

            results.append({
                "Ticker": t,
                "Kurs": round(last["Close"], 2),
                "RSI": round(last["RSI"], 1),
                "Vol x": round(last["Vol_ratio"], 2),
                "Sygnał": color,
                "AI_score": score,
                "Komentarz LLM": comment
            })

            spark_data[t] = df["Close"].tail(20).reset_index(drop=True)

        if not results:
            st.info("Brak danych / zbyt krótka historia dla podanych spółek.")
            st.stop()

        df_out = pd.DataFrame(results)
        df_out = df_out.sort_values("AI_score", ascending=False).reset_index(drop=True)

    play_beep()

    st.subheader("📊 Tabela sygnałów (posortowana wg AI_score)")

    def highlight(row):
        if row["Sygnał"] == "green":
            return ["background-color: #0f5132; color: white"] * len(row)
        if row["Sygnał"] == "orange":
            return ["background-color: #ff8c00; color: black"] * len(row)
        if row["Sygnał"] == "red":
            return ["background-color: #8b0000; color: white"] * len(row)
        return [""] * len(row)

    st.dataframe(df_out.style.apply(highlight, axis=1), use_container_width=True)

    st.subheader("📉 Mini‑sparklines (ostatnie 20 sesji)")

    cols_per_row = 4
    tickers_order = df_out["Ticker"].tolist()

    for i in range(0, len(tickers_order), cols_per_row):
        row_tickers = tickers_order[i:i+cols_per_row]
        cols = st.columns(len(row_tickers))
        for col, t in zip(cols, row_tickers):
            with col:
                st.caption(t)
                s = spark_data.get(t)
                if s is not None:
                    st.line_chart(s)

else:
    st.info("Dodaj swoje spółki, zapisz listę i kliknij **Skanuj teraz**.")
