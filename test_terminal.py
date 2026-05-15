import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import io, wave, math, struct, base64
from datetime import datetime
from openai import OpenAI

# ==========================
# OpenAI client (klucz w st.secrets)
# ==========================

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ==========================
# Dźwięk alertu
# ==========================

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

# ==========================
# Pobieranie danych
# ==========================

def download(tickers, period="180d", interval="1d"):
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

# ==========================
# Wskaźniki – zależne od trybu
# ==========================

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

# ==========================
# News – proste flagi z yfinance
# ==========================

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
        flags.append("news: FDA")
    if "approval" in text_low or "approved" in text_low:
        flags.append("news: approval")
    if "debt" in text_low or "zadłużenie" in text_low:
        flags.append("news: debt")
    if "downgrade" in text_low:
        flags.append("news: downgrade")
    if "no coverage" in text_low:
        flags.append("news: no coverage")
    if "profit warning" in text_low:
        flags.append("news: profit warning")
    if "bankruptcy" in text_low or "bankrupt" in text_low:
        flags.append("news: bankruptcy")
    if "offering" in text_low or "share offering" in text_low:
        flags.append("news: share offering")
    if "buyback" in text_low:
        flags.append("news: buyback")
    if "acquisition" in text_low or "merger" in text_low:
        flags.append("news: m&a")

    return " | ".join(flags)

# ==========================
# Sygnały 1–7
# ==========================

def compute_signals(df, mode):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signals = []

    # 1/2/3 – trend rośnie / spada / stoi
    if last["EMA_fast"] > last["EMA_mid"] > last["EMA_slow"] and last["RSI"] > 55 and last["Momentum"] > 0:
        trend_state = "trend rośnie"
        signals.append("trend rośnie")
    elif last["EMA_fast"] < last["EMA_mid"] < last["EMA_slow"] and last["RSI"] < 45 and last["Momentum"] < 0:
        trend_state = "trend spada"
        signals.append("trend spada")
    else:
        trend_state = "trend stoi / konsolidacja"
        signals.append("trend stoi / konsolidacja")

    # 4 – wybicie / przebicie poziomu
    if last["Close"] > last["EMA_mid"] and prev["Close"] <= prev["EMA_mid"]:
        signals.append("przebicie powyżej EMA_mid")
    if last["Close"] > last["Fibo_high"] * 0.999:
        signals.append("wybicie powyżej Fibo HIGH")
    if last["Close"] < last["Fibo_low"] * 1.001:
        signals.append("wybicie poniżej Fibo LOW")

    # 5 – wzrost kupujących
    if last["Close"] > prev["Close"] and last["Vol_ratio"] > 1.5 and last["RSI"] > prev["RSI"]:
        signals.append("wzrost kupujących (mocny popyt)")

    # 6 – wzrost sprzedających
    if last["Close"] < prev["Close"] and last["Vol_ratio"] > 1.5 and last["RSI"] < prev["RSI"]:
        signals.append("wzrost sprzedających (mocna podaż)")

    # 7 – placeholder, newsy dokładamy osobno
    return trend_state, signals

# ==========================
# AI score (siła sytuacji)
# ==========================

def ai_score(df, mode):
    last = df.iloc[-1]
    score = 0

    if last["EMA_fast"] > last["EMA_mid"]:
        score += 1
    if last["EMA_mid"] > last["EMA_slow"]:
        score += 1
    if last["RSI"] > 55:
        score += 1
    if last["Momentum"] > 0:
        score += 1
    if last["Vol_ratio"] > 1.5:
        score += 1

    return score

# ==========================
# Komentarz LLM
# ==========================

def llm_comment(ticker, last, mode, trend_state, signals, news_text):
    mode_desc = {
        "Swing": "średni horyzont (swing)",
        "Day": "krótki horyzont (day)",
        "Long": "długi horyzont (long-term)"
    }[mode]

    sig_str = ", ".join(signals) if signals else "brak wyraźnych sygnałów"
    news_part = news_text if news_text else "brak istotnych newsów w ostatnich wiadomościach"

    prompt = f"""
Jesteś analitykiem technicznym. Na podstawie danych wygeneruj krótki komentarz (1–2 zdania) po polsku.

Tryb analizy: {mode_desc}

Dane:
Ticker: {ticker}
Cena zamknięcia: {last['Close']:.2f}
RSI: {last['RSI']:.2f}
EMA_fast: {last['EMA_fast']:.2f}
EMA_mid: {last['EMA_mid']:.2f}
EMA_slow: {last['EMA_slow']:.2f}
Momentum: {last['Momentum']:.2f}
Vol_ratio: {last['Vol_ratio']:.2f}
Fibo_high: {last['Fibo_high']:.2f}
Fibo_low: {last['Fibo_low']:.2f}

Trend: {trend_state}
Sygnały: {sig_str}
News: {news_part}

Zasady:
- pisz krótko i konkretnie,
- nie dawaj rekomendacji kupna/sprzedaży,
- skup się na opisie sytuacji (trend, popyt/podaż, wybicia, ryzyko),
- nie dodawaj disclaimers.
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

# ==========================
# UI – całość
# ==========================

st.set_page_config(page_title="Dual Market Scanner FINAL", layout="wide")

st.title("📈🤖 Dual Market Scanner – GPW & USA (Swing / Day / Long)")
st.caption("Trend rośnie / spada / stoi • wybicia • kupujący / sprzedający • newsy • AI komentarz • ranking siły")

tab_gpw, tab_usa = st.tabs(["🇵🇱 GPW", "🇺🇸 USA"])

def render_market(tab, market_name):
    with tab:
        st.header(f"Rynek: {market_name}")

        key_prefix = market_name.replace(" ", "_")

        if f"{key_prefix}_tickers" not in st.session_state:
            st.session_state[f"{key_prefix}_tickers"] = []

        tickers_input = st.text_area(
            "Wpisz swoje tickery (oddzielone przecinkami):",
            value=",".join(st.session_state[f"{key_prefix}_tickers"]),
            key=f"{key_prefix}_input"
        )

        if st.button("💾 Zapisz listę", key=f"{key_prefix}_save"):
            st.session_state[f"{key_prefix}_tickers"] = [
                t.strip().upper() for t in tickers_input.split(",") if t.strip()
            ]
            st.success("Zapisano!")

        tickers = st.session_state[f"{key_prefix}_tickers"]

        mode = st.selectbox(
            "Tryb analizy:",
            ["Swing", "Day", "Long"],
            key=f"{key_prefix}_mode"
        )

        auto_minutes = st.slider(
            "Auto‑skan co (minuty, 0 = wyłącz)",
            0, 60, 0, 5,
            key=f"{key_prefix}_auto"
        )

        run_button = st.button("🔍 Skanuj teraz", key=f"{key_prefix}_scan")

        run_scan = run_button
        if auto_minutes > 0:
            now = datetime.utcnow().minute
            if now % auto_minutes == 0:
                run_scan = True

        if run_scan:
            if not tickers:
                st.error("Najpierw dodaj spółki.")
                return

            with st.spinner("Pobieram dane, liczę wskaźniki i analizuję..."):
                data = download(tickers)

                results = []
                spark_data = {}

                for t, df in data.items():
                    if len(df) < 80:
                        continue

                    df = indicators(df, mode)
                    df = df.dropna()
                    if len(df) < 5:
                        continue

                    last = df.iloc[-1]

                    trend_state, sigs = compute_signals(df, mode)
                    news_text = news_flags(t)
                    comment = llm_comment(t, last, mode, trend_state, sigs, news_text)
                    score = ai_score(df, mode)

                    # kolor
                    if "trend rośnie" in trend_state:
                        color = "green"
                    elif "trend spada" in trend_state:
                        color = "red"
                    else:
                        color = "orange"

                    results.append({
                        "Ticker": t,
                        "Kurs": round(last["Close"], 2),
                        "RSI": round(last["RSI"], 1),
                        "Vol x": round(last["Vol_ratio"], 2),
                        "Trend": trend_state,
                        "Sygnały": " | ".join(sigs),
                        "News": news_text,
                        "AI_score": score,
                        "Kolor": color,
                        "Komentarz LLM": comment
                    })

                    spark_data[t] = df["Close"].tail(20).reset_index(drop=True)

                if not results:
                    st.info("Brak danych / zbyt krótka historia.")
                    return

                df_out = pd.DataFrame(results)
                df_out = df_out.sort_values("AI_score", ascending=False).reset_index(drop=True)

            play_beep()

            st.subheader("📊 Tabela sygnałów (posortowana wg AI_score)")

            def highlight(row):
                if row["Kolor"] == "green":
                    return ["background-color: #0f5132; color: white"] * len(row)
                if row["Kolor"] == "orange":
                    return ["background-color: #ff8c00; color: black"] * len(row)
                if row["Kolor"] == "red":
                    return ["background-color: #8b0000; color: white"] * len(row)
                return [""] * len(row)

            show_cols = ["Ticker", "Kurs", "RSI", "Vol x", "Trend", "Sygnały", "News", "AI_score", "Komentarz LLM"]
            st.dataframe(
                df_out[show_cols].style.apply(highlight, axis=1),
                use_container_width=True
            )

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
            st.info("Ustaw tickery, wybierz tryb i kliknij **Skanuj teraz** (lub włącz auto‑skan).")

render_market(tab_gpw, "GPW")
render_market(tab_usa, "USA")
