import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
from streamlit_autorefresh import st_autorefresh
import ta

# ============================================================
# ULTRA ENGINE v12.1 — FULL AI PIPELINE + CHAT + PRESETY
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v12.1", page_icon="⚔️")

# --- STYL / NEONY / KOLORY ---
st.markdown("""
<style>
.stApp {
    background-color: #050510;
    color: #e0e0e0;
}
.neon-button {
    background: linear-gradient(90deg, #ff00cc, #3333ff);
    padding: 10px 20px;
    border-radius: 8px;
    color: white !important;
    font-weight: bold;
    font-size: 18px;
    border: 1px solid #ff00cc;
    box-shadow: 0 0 12px #ff00cc;
    display: inline-block;
}
.neon-label {
    color: #ff66ff;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: USTAWIENIA ---
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

st.sidebar.header("🤖 MODEL AI")
model_choice = st.sidebar.selectbox(
    "Model",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    index=0
)

st.sidebar.header("🧠 TRYBY PRACY")
ai_only_mode = st.sidebar.checkbox("Tryb tylko AI (bez skanowania)", value=False)

# --- CLIENT & SECRETS ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
        return 4.0
    except:
        return 4.0

USD_PLN = get_usd_pln()

def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = [n.get("title", "") for n in t.news[:2]]
        return " | ".join(news) if news else "Brak newsów."
    except:
        return "Lagg."

# --- SIDEBAR: PRESETY + LISTA + PORTFOLIO ---
st.sidebar.header("🇵🇱 PRESETY LIST")
preset = st.sidebar.selectbox(
    "Wybierz preset:",
    ["Brak", "Polska spekuła", "USA growth", "Mega-cap tech"],
    index=0
)

st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy (nadpisywana przez preset)", default_list)

symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

if preset == "Polska spekuła":
    symbols = [
        "BBT.WA", "BIOM.WA", "MAB.WA", "CRL.WA", "BML.WA",
        "VRC.WA", "CNT.WA", "STS.WA", "PLW.WA", "TEN.WA",
        "CDR.WA", "11B.WA"
    ]
elif preset == "USA growth":
    symbols = ["NVDA", "TSLA", "AMD", "PLTR", "SMCI", "META", "AAPL"]
elif preset == "Mega-cap tech":
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]

st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area(
    "SYMBOL,ILOŚĆ,CENA",
    "NVDA,1,900\nSTX.WA,100,5.0"
)

# --- TRYB TYLKO AI ---
if ai_only_mode:
    st.title("🤖 ULTRA ENGINE v12.1 — TRYB TYLKO AI")
    st.markdown('<span class="neon-label">Model:</span> ' + model_choice, unsafe_allow_html=True)

    user_prompt = st.text_area("Wpisz dowolne pytanie do AI:", "")

    if st.button("Wyślij do AI"):
        if not client:
            st.error("Brak klucza API — AI wyłączone.")
        elif not user_prompt.strip():
            st.info("Najpierw wpisz pytanie.")
        else:
            with st.spinner("AI analizuje..."):
                res = client.chat.completions.create(
                    model=model_choice,
                    messages=[
                        {"role": "system", "content": "Jesteś brutalnym zarządzającym funduszem hedgingowym."},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.25
                )
            st.write(res.choices[0].message.content)
    st.stop()

# --- MAIN HEADER ---
st.title(f"⚔️ ULTRA ENGINE v12.1 — REFRESH: {refresh_val} MIN")

# ============================================================
# ANALIZA POJEDYNCZEGO SYMBOLU
# ============================================================

def analyze_symbol(symbol: str):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="3mo")
        if df.empty or len(df) < 20:
            return None

        last_p = df["Close"].iloc[-1]

        # RSI
        rsi_series = ta.momentum.RSIIndicator(close=df["Close"], window=14).rsi()
        rsi = float(rsi_series.iloc[-1])

        # Momentum 10 dni
        if len(df) > 10:
            mom = ((last_p - df["Close"].iloc[-10]) / df["Close"].iloc[-10]) * 100
        else:
            mom = np.nan

        # EMA TREND
        ema20 = df["Close"].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
        ema_trend = int(ema20 > ema50)   # 1 = UP

        # MACD
        ema12 = df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = df["Close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_trend = int(macd_line.iloc[-1] > signal_line.iloc[-1])  # 1 = bullish

        # Volatility (10d)
        vol10 = df["Close"].pct_change().rolling(10).std().iloc[-1] * 100

        # News
        news = get_beast_news(symbol)

        # SCORING
        score = 0

        # RSI
        if rsi < 30: score += 30
        elif rsi < 40: score += 15
        elif rsi > 70: score -= 25

        # Momentum
        if not np.isnan(mom):
            if mom > 5: score += 20
            elif mom < -5: score -= 10

        # EMA trend
        if ema_trend == 1: score += 20
        else: score -= 10

        # MACD trend
        if macd_trend == 1: score += 20
        else: score -= 10

        score = max(0, min(100, score))

        return {
            "Symbol": symbol,
            "Cena": round(last_p, 2),
            "RSI": round(rsi, 1),
            "Mom% 10d": round(mom, 2) if not np.isnan(mom) else np.nan,
            "EMA Trend": "UP" if ema_trend else "DOWN",
            "MACD Trend": "UP" if macd_trend else "DOWN",
            "Volatility10d": round(vol10, 2),
            "Score": int(score),
            "News": news
        }
    except:
        return None

# ============================================================
# SKANER + GŁÓWNY PIPELINE
# ============================================================

results_df = None

col1, col2 = st.columns([1, 3])
with col1:
    run_scan = st.button("🚀 SKANUJ LISTĘ", key="scan_button")
with col2:
    st.markdown('<div class="neon-button">Pełny skan techniczny + AI + czat</div>', unsafe_allow_html=True)

if run_scan:
    results = []
    progress = st.progress(0)

    for i, s in enumerate(symbols):
        r = analyze_symbol(s)
        if r:
            results.append(r)
        progress.progress((i + 1) / max(len(symbols), 1))

    if results:
        results_df = pd.DataFrame(results).sort_values("Score", ascending=False)
        st.session_state["last_scan"] = results_df.copy()

        st.subheader("📊 Wyniki skanowania — pełny widok")
        styled = results_df.style.background_gradient(subset=["Score"], cmap="viridis")
        st.dataframe(styled, use_container_width=True)
    else:
        st.warning("Brak wyników — sprawdź listę tickerów lub dane z Yahoo Finance.")

# ============================================================
# AI: GLOBALNY RAPORT + TOP OKAZJE
# ============================================================

if "last_scan" in st.session_state and client:
    results_df = st.session_state["last_scan"]

    if not results_df.empty:
        st.divider()
        st.subheader("🤖 GENESIS AI — RAPORT GLOBALNY")

        summary = results_df.to_string(index=False)

        prompt_global = f"""
Jesteś brutalnym zarządzającym funduszem hedgingowym.

DANE:
{summary}

KURS USD/PLN: {USD_PLN}

ZADANIE:
1. Wybierz TOP 3 OKAZJE (wysoki Score, niskie RSI, sensowny trend).
2. Wskaż 3 NAJWIĘKSZE PUŁAPKI (wysokie RSI, słaby trend, ryzykowne newsy).
3. Dla każdej pozycji podaj:
   - SYMBOL
   - WERDYKT: KUP / OBSERWUJ / UCIEKAJ
   - KRÓTKI POWÓD (konkretnie, bez lania wody).
Odpowiedz w formie listy punktów.
"""

        with st.spinner("AI analizuje cały rynek..."):
            res_global = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "system", "content": "Jesteś brutalnym, bezlitosnym zarządzającym funduszem hedgingowym. Nienawidzisz ogólników."},
                    {"role": "user", "content": prompt_global}
                ],
                temperature=0.2
            )
            st.warning("RAPORT STRATEGICZNY:")
            st.write(res_global.choices[0].message.content)

        st.subheader("🔥 TOP 5 wg Score")
        top_df = results_df.sort_values("Score", ascending=False).head(5)
        st.table(top_df)

# ============================================================
# CZAT Z AI NAD OSTATNIM SKANEM
# ============================================================

st.divider()
st.subheader("💬 Czat z AI (synchronizowany z ostatnim skanem)")

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "last_scan" not in st.session_state:
    st.info("Najpierw uruchom skanowanie listy, żeby AI miało dane.")
else:
    scan_data = st.session_state["last_scan"]
    user_msg = st.text_input("Twoje pytanie do AI:")

    if st.button("Wyślij pytanie do AI"):
        if not client:
            st.error("Brak klucza API.")
        elif not user_msg.strip():
            st.info("Najpierw wpisz pytanie.")
        else:
            context = scan_data.to_string(index=False)

            prompt_chat = f"""
DANE Z OSTATNIEGO SKANU:
{context}

Pytanie użytkownika:
{user_msg}

Odpowiadaj konkretnie, używaj symboli i parametrów (RSI, Score, EMA Trend, MACD Trend, Volatility).
"""

            with st.spinner("AI analizuje dane..."):
                res_chat = client.chat.completions.create(
                    model=model_choice,
                    messages=[
                        {"role": "system", "content": "Jesteś brutalnym analitykiem hedge fund."},
                        {"role": "user", "content": prompt_chat}
                    ],
                    temperature=0.25
                )
                answer = res_chat.choices[0].message.content

            st.session_state["chat_history"].append(("Ty", user_msg))
            st.session_state["chat_history"].append(("AI", answer))

    if st.session_state["chat_history"]:
        st.markdown("### Historia rozmowy")
        for speaker, text in st.session_state["chat_history"]:
            if speaker == "Ty":
                st.markdown(f"**Ty:** {text}")
            else:
                st.markdown(f"**AI:** {text}")

# ============================================================
# PORTFOLIO
# ============================================================

st.divider()
st.subheader(f"📈 Twoje Pozycje (Kurs USD/PLN: {round(USD_PLN, 2)})")

try:
    port_data = []
    for line in portfolio_input.split("\n"):
        if not line or "," not in line:
            continue

        parts = line.split(",")
        sym = parts[0].strip().upper()
        qty = float(parts[1])
        b_p = float(parts[2])

        t_ticker = yf.Ticker(sym)
        t_hist = t_ticker.history(period="1d")
        if t_hist.empty:
            continue

        t_p = float(t_hist["Close"].iloc[-1])

        is_usd = ".WA" not in sym
        current_val_pln = (t_p * qty * USD_PLN) if is_usd else (t_p * qty)
        cost_val_pln = (b_p * qty * USD_PLN) if is_usd else (b_p * qty)
        profit = current_val_pln - cost_val_pln

        port_data.append({
            "Symbol": sym,
            "Cena (waluta)": round(t_p, 2),
            "Wartość PLN": round(current_val_pln, 2),
            "Zysk PLN": round(profit, 2)
        })

    if port_data:
        dfp = pd.DataFrame(port_data)
        st.table(dfp)
        st.metric("SUMA ZYSKU (PLN)", f"{round(sum(d['Zysk PLN'] for d in port_data), 2)} PLN")
    else:
        st.info("Brak poprawnych pozycji w portfelu.")
except Exception:
    st.info("Oczekiwanie na poprawne dane portfolio... (Format: SYMBOL,ILOŚĆ,CENA)")
