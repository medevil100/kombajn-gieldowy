import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
from streamlit_autorefresh import st_autorefresh
import ta
import plotly.graph_objects as go
from datetime import datetime

# ============================================================
# ULTRA ENGINE v13+ — PROP-TRADER MODE + CYBERPUNK UI + DEEP DIVE
# Trend Strength, Risk Index, Pattern Recognition, Volume Heatmap, Pre-Market Radar
# ============================================================

st.set_page_config(layout="wide", page_title="ULTRA ENGINE v13+", page_icon="⚔️")

# --- CYBERPUNK UI / STYL ---
st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at top, #2b0040 0, #050510 45%, #000000 100%);
    color: #f0f0f0;
    font-family: "Roboto", sans-serif;
}
.sidebar .sidebar-content {
    background-color: #050510 !important;
}
.neon-button {
    background: linear-gradient(90deg, #ff0099, #ffcc00);
    padding: 10px 22px;
    border-radius: 10px;
    color: #000000 !important;
    font-weight: 800;
    font-size: 18px;
    border: 1px solid #ffcc00;
    box-shadow: 0 0 18px #ff0099;
    display: inline-block;
}
.neon-label {
    color: #ffcc00;
    font-weight: bold;
}
h1, h2, h3, h4 {
    color: #ffcc00;
}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: USTAWIENIA SYSTEMU ---
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

st.sidebar.header("🤖 MODEL AI")
model_choice = st.sidebar.selectbox(
    "Model",
    ["gpt-4o-mini", "gpt-4o","gpt-41", "gpt-4.1-mini"],
    index=0
)

st.sidebar.header("🧠 TRYBY")
ai_only_mode = st.sidebar.checkbox("Tryb tylko AI (bez skanowania)", value=False)
prop_trader_mode = st.sidebar.checkbox("Prop‑Trader Mode (styl odpowiedzi)", value=True)
gpw_focus_mode = st.sidebar.checkbox("GPW focus (uwzględnia specyfikę GPW)", value=True)
premarket_mode = st.sidebar.checkbox("Pre‑Market Radar (USA)", value=True)

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
st.sidebar.header("📡 PRESETY LIST")
preset = st.sidebar.selectbox(
    "Wybierz preset:",
    [
        "Brak",
        "Polska spekuła",
        "USA growth",
        "Mega-cap tech",
        "Biotech USA",
        "Crypto miners",
        "AI small-caps",
        "GPW gaming",
        "GPW mid-caps",
        "GPW śmieciówki",
        "Semiconductors"
    ],
    index=0
)

st.sidebar.header("📡 SKANER MASOWY")
default_list = "EMT.WA, ENE.WA, EON.WA, ETL.WA, FAS.WA, FTE.WA, GTC.WA, HBP.WA, HLD.WA, IFE.WA, ING.WA, KRU.WA, LPP.WA, LWB.WA, MAB.WA, MCI.WA, MEX.WA, MLP.WA, MSO.WA, VGO.WA,HRT.WA,CFS.WA,PRT.WA,ATT.WA,STX.WA,PUR.WA,BCS.WA,KCH.WA,GTN.WALBW.WA,PGV.WA,HPE.WA,DNS.WA.ZUK.WA,VVD.WA,HIVE,MLN.WA,MER.WA,AP"
symbols_input = st.sidebar.text_area("Lista do analizy (nadpisywana przez preset)", default_list)
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

# Presety
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
elif preset == "Biotech USA":
    symbols = ["IOVA", "IMGN", "SAVA", "NVAX", "BLUE", "BMRN", "VRTX"]
elif preset == "Crypto miners":
    symbols = ["MARA", "RIOT", "HUT", "BITF", "CIFR"]
elif preset == "AI small-caps":
    symbols = ["PLTR", "SOFI", "AI", "UPST", "PATH"]
elif preset == "GPW gaming":
    symbols = ["CDR.WA", "TEN.WA", "PLW.WA", "11B.WA", "CIG.WA"]
elif preset == "GPW mid-caps":
    symbols = ["ALR.WA", "PKP.WA", "MRC.WA", "PKP.WA"]
elif preset == "GPW śmieciówki":
    symbols = ["BBT.WA", "VRC.WA", "CNT.WA", "BML.WA", "MAB.WA"]
elif preset == "Semiconductors":
    symbols = ["NVDA", "AMD", "AVGO", "ASML", "TSM", "INTC"]

st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area(
    "SYMBOL,ILOŚĆ,CENA",
    "IOVA"
)

# ============================================================
# SYSTEM PROMPT BUILDER
# ============================================================

def build_system_prompt():
    base = []
    if prop_trader_mode:
        base.append(
            "Jesteś technicznym traderem z prop‑tradingu. Mówisz krótko, konkretnie, bez dyplomacji. "
            "Analizujesz wyłącznie dane techniczne i informacje, które dostajesz."
        )
    else:
        base.append(
            "Jesteś analitykiem technicznym rynku akcji. Oceniasz sygnały na podstawie wskaźników i danych."
        )

    if gpw_focus_mode:
        base.append(
            "Uwzględniasz specyfikę GPW: płytki rynek, możliwe zrzuty, znaczenie wolumenu, spekulacyjny charakter wielu spółek."
        )

    base.append(
        "Zakazy: nie pisz, że nie możesz przewidywać przyszłości, nie pisz ogólników o ryzyku inwestowania, "
        "nie odsyłaj do 'dokładnej analizy fundamentalnej'. "
        "Zamiast tego opisuj sygnały techniczne jako: silne / mieszane / słabe, ryzyko: niskie / średnie / wysokie."
    )

    base.append(
        "Zawsze odwołuj się do konkretnych parametrów: RSI, Momentum, EMA Trend, MACD, Volatility, Score, Volume, News/komunikaty. "
        "Używaj pojęć typu: trend wzrostowy/spadkowy/boczny, wykupienie/wyprzedanie, sygnał byczy/niedźwiedzi, momentum rośnie/gaśnie."
    )

    return "\n".join(base)

# ============================================================
# TRYB TYLKO AI
# ============================================================

if ai_only_mode:
    st.title("🤖 ULTRA ENGINE v13+ — TRYB TYLKO AI")
    st.markdown(f'<span class="neon-label">Model:</span> {model_choice}', unsafe_allow_html=True)

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
                        {"role": "system", "content": build_system_prompt()},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.25
                )
            st.write(res.choices[0].message.content)
    st.stop()

# ============================================================
# MAIN HEADER
# ============================================================

st.title(f"⚔️ ULTRA ENGINE v13+ — REFRESH: {refresh_val} MIN")

# ============================================================
# ANALIZA POJEDYNCZEGO SYMBOLU (SKANER)
# ============================================================

def detect_pattern(df):
    # bardzo prosty pattern recognition: breakout / squeeze / range
    if len(df) < 30:
        return "Brak danych"
    closes = df["Close"]
    recent = closes[-5:]
    last = recent.iloc[-1]
    max_20 = closes[-20:].max()
    min_20 = closes[-20:].min()
    vol = closes.pct_change().rolling(20).std().iloc[-1] * 100

    pattern = []
    if last > max_20 * 1.01:
        pattern.append("Breakout")
    if vol < 2:
        pattern.append("Volatility squeeze")
    if (max_20 - min_20) / min_20 < 0.05:
        pattern.append("Range")

    return ", ".join(pattern) if pattern else "Brak wyraźnego patternu"

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
        ema20_series = df["Close"].ewm(span=20, adjust=False).mean()
        ema50_series = df["Close"].ewm(span=50, adjust=False).mean()
        ema20 = ema20_series.iloc[-1]
        ema50 = ema50_series.iloc[-1]
        ema_trend = int(ema20 > ema50)   # 1 = UP

        # MACD
        ema12 = df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = df["Close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_trend = int(macd_line.iloc[-1] > signal_line.iloc[-1])  # 1 = bullish

        # Volatility (10d)
        vol10 = df["Close"].pct_change().rolling(10).std().iloc[-1] * 100

        # Volume (ostatnia świeca)
        volume = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else np.nan

        # News
        news = get_beast_news(symbol)

        # Trend Strength Score (0–100)
        trend_score = 0
        if ema_trend == 1:
            trend_score += 35
        if macd_trend == 1:
            trend_score += 35
        if not np.isnan(mom):
            if mom > 5:
                trend_score += 20
            elif mom > 0:
                trend_score += 10
        if not np.isnan(vol10) and vol10 > 1:
            trend_score += 10
        trend_score = max(0, min(100, trend_score))

        # Risk Index (0–100)
        risk_index = 0
        if not np.isnan(vol10):
            if vol10 > 10:
                risk_index += 40
            elif vol10 > 5:
                risk_index += 25
            else:
                risk_index += 10
        if not np.isnan(rsi):
            if rsi > 70 or rsi < 30:
                risk_index += 25
            else:
                risk_index += 10
        if not np.isnan(volume):
            risk_index += 15
        risk_index += 10  # spekuła baseline
        risk_index = max(0, min(100, risk_index))

        # Pattern
        pattern = detect_pattern(df)

        # SCORING (ogólny)
        score = 0
        if rsi < 30: score += 30
        elif rsi < 40: score += 15
        elif rsi > 70: score -= 25

        if not np.isnan(mom):
            if mom > 5: score += 20
            elif mom < -5: score -= 10

        if ema_trend == 1: score += 20
        else: score -= 10

        if macd_trend == 1: score += 20
        else: score -= 10

        if not np.isnan(vol10):
            if vol10 > 8:
                score += 5
            elif vol10 < 2:
                score -= 5

        score = max(0, min(100, score))

        return {
            "Symbol": symbol,
            "Cena": round(last_p, 2),
            "RSI": round(rsi, 1),
            "Mom% 10d": round(mom, 2) if not np.isnan(mom) else np.nan,
            "EMA Trend": "UP" if ema_trend else "DOWN",
            "MACD Trend": "UP" if macd_trend else "DOWN",
            "Volatility10d": round(vol10, 2),
            "Volume": int(volume) if not np.isnan(volume) else None,
            "Score": int(score),
            "TrendStrength": int(trend_score),
            "RiskIndex": int(risk_index),
            "Pattern": pattern,
            "News": news
        }
    except:
        return None

# ============================================================
# FUNKCJE DO DEEP DIVE (WYKRESY)
# ============================================================

def get_chart_data(symbol):
    t = yf.Ticker(symbol)
    df = t.history(period="6mo", interval="1d")
    if df.empty:
        return None

    # RSI
    df["RSI"] = ta.momentum.RSIIndicator(df["Close"], window=14).rsi()

    # MACD
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # Momentum 10d
    df["Momentum10d"] = df["Close"].pct_change(10) * 100

    # EMA20/EMA50
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

    return df

def build_single_ticker_prompt(row):
    data_block = f"""
SYMBOL: {row['Symbol']}
Cena: {row['Cena']}
RSI: {row['RSI']}
Momentum 10d: {row['Mom% 10d']}
EMA Trend: {row['EMA Trend']}
MACD Trend: {row['MACD Trend']}
Volatility10d: {row['Volatility10d']}
Volume: {row['Volume']}
TrendStrength: {row['TrendStrength']}
RiskIndex: {row['RiskIndex']}
Pattern: {row['Pattern']}
News: {row['News']}
Score: {row['Score']}
"""

    prompt = f"""
DANE TECHNICZNE I SENTYMENT (POJEDYNCZY TICKER):
{data_block}

ZADANIE:
1. Oceń sygnały techniczne wyłącznie na podstawie powyższych danych.
2. Opisz:
   - TREND: wzrostowy / spadkowy / boczny (na podstawie EMA, MACD, Momentum, TrendStrength).
   - STAN RYNKU: wykupienie / wyprzedanie / neutralny (na podstawie RSI).
   - CHARAKTER SYGNAŁÓW: bycze / mieszane / niedźwiedzie.
   - RYZYKO: niskie / średnie / wysokie (na podstawie RiskIndex, Volatility, Volume, Pattern, News).
3. Używaj pojęć typu: trend wzrostowy/spadkowy, sygnał byczy/niedźwiedzi, momentum rośnie/gaśnie, wykupienie/wyprzedanie, pattern breakout/squeeze/range.
4. Mów jak trader techniczny: krótko, konkretnie, bez ogólników.
"""
    return prompt

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

    total = max(len(symbols), 1)
    for i, s in enumerate(symbols):
        r = analyze_symbol(s)
        if r:
            results.append(r)
        progress.progress((i + 1) / total)

    if results:
        results_df = pd.DataFrame(results).sort_values("Score", ascending=False)
        st.session_state["last_scan"] = results_df.copy()

        st.subheader("📊 Wyniki skanowania — pełny widok")

        def color_rsi(val):
            if pd.isna(val):
                return ""
            if val < 30:
                return "background-color: #004d40; color: #a5ffea;"
            if val > 70:
                return "background-color: #4a0000; color: #ffb3b3;"
            return ""

        styled = (
            results_df.style
            .background_gradient(subset=["Score"], cmap="plasma")
            .background_gradient(subset=["TrendStrength"], cmap="Greens")
            .background_gradient(subset=["RiskIndex"], cmap="Reds")
            .apply(lambda s: [color_rsi(v) for v in s], subset=["RSI"])
        )
        st.dataframe(styled, use_container_width=True)
    else:
        st.warning("Brak wyników — sprawdź listę tickerów lub dane z Yahoo Finance.")

# ============================================================
# HEATMAPA WOLUMENU
# ============================================================

if "last_scan" in st.session_state:
    st.divider()
    st.subheader("🔥 Heatmapa wolumenu (ostatnia świeca)")

    vol_df = st.session_state["last_scan"][["Symbol", "Volume"]].copy()
    vol_df = vol_df.sort_values("Volume", ascending=False)
    st.dataframe(
        vol_df.style.background_gradient(subset=["Volume"], cmap="magma"),
        use_container_width=True
    )

# ============================================================
# PRE-MARKET RADAR (USA)
# ============================================================

if premarket_mode and "last_scan" in st.session_state:
    st.divider()
    st.subheader("🌅 Pre‑Market Radar (USA)")

    radar_rows = []
    for sym in st.session_state["last_scan"]["Symbol"]:
        if ".WA" in sym:
            continue
        try:
            t = yf.Ticker(sym)
            info = t.fast_info if hasattr(t, "fast_info") else {}
            pre = getattr(info, "last_price", None)
            # fallback: użyj history intraday, jeśli chcesz rozbudować
            # tutaj uproszczenie: tylko aktualna cena vs wczorajsze close
            hist = t.history(period="2d")
            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                last_close = hist["Close"].iloc[-1]
                change = (last_close - prev_close) / prev_close * 100
            else:
                change = np.nan
            radar_rows.append({"Symbol": sym, "Zmiana vs wczoraj (%)": round(change, 2)})
        except:
            continue

    if radar_rows:
        radar_df = pd.DataFrame(radar_rows).sort_values("Zmiana vs wczoraj (%)", ascending=False)
        st.dataframe(
            radar_df.style.background_gradient(subset=["Zmiana vs wczoraj (%)"], cmap="coolwarm"),
            use_container_width=True
        )
    else:
        st.info("Brak danych pre‑market / dziennych dla obecnych tickerów USA.")

# ============================================================
# AI: GLOBALNY RAPORT + TOP OKAZJE
# ============================================================

if "last_scan" in st.session_state and client:
    results_df = st.session_state["last_scan"]

    if not results_df.empty:
        st.divider()
        st.subheader("🤖 RAPORT TECHNICZNY — PROP‑TRADER VIEW")

        summary = results_df.to_string(index=False)

        user_prompt_global = f"""
DANE TECHNICZNE I SENTYMENT:
{summary}

KURS USD/PLN: {USD_PLN}

ZADANIE:
1. Oceń każdą spółkę wyłącznie na podstawie powyższych danych (RSI, Momentum, EMA Trend, MACD, Volatility, Score, TrendStrength, RiskIndex, Volume, Pattern, News).
2. Wybierz:
   - TOP 3 z najsilniejszymi sygnałami wzrostowymi (wysoki TrendStrength, sensowny Score, akceptowalne RiskIndex),
   - TOP 3 z najsłabszymi sygnałami (przewaga ryzyka spadku, wysoki RiskIndex, słaby TrendStrength).
3. Dla każdej spółki podaj:
   SYMBOL – OCENA (silne sygnały wzrostowe / mieszane / przewaga ryzyka spadku) – POWÓD (konkretnie, z parametrami).
4. Używaj pojęć: trend wzrostowy/spadkowy, wykupienie/wyprzedanie, sygnał byczy/niedźwiedzi, momentum rośnie/gaśnie, pattern breakout/squeeze/range.
5. Mów jak trader techniczny: krótko, konkretnie, bez ogólników.
"""

        with st.spinner("AI analizuje cały skan..."):
            res_global = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_prompt_global}
                ],
                temperature=0.25
            )
            st.warning("RAPORT TECHNICZNY:")
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
    user_msg = st.text_input("Twoje pytanie do AI (np. 'Które spółki mają najsilniejsze momentum?'):")

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

Odpowiadaj konkretnie, używaj symboli i parametrów (RSI, Score, TrendStrength, RiskIndex, EMA Trend, MACD Trend, Volatility, Volume, Pattern, News).
Opisuj sygnały jako: silne / mieszane / słabe, ryzyko: niskie / średnie / wysokie.
Używaj pojęć: trend wzrostowy/spadkowy, wykupienie/wyprzedanie, sygnał byczy/niedźwiedzi, momentum rośnie/gaśnie, pattern breakout/squeeze/range.
"""

            with st.spinner("AI analizuje dane..."):
                res_chat = client.chat.completions.create(
                    model=model_choice,
                    messages=[
                        {"role": "system", "content": build_system_prompt()},
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
# DEEP DIVE: POJEDYNCZY TICKER (WYKRESY + AI)
# ============================================================

st.divider()
st.subheader("🎯 Deep Dive — pojedynczy ticker")

if "last_scan" not in st.session_state:
    st.info("Najpierw uruchom skanowanie listy, żeby mieć dane do analizy.")
else:
    scan_data = st.session_state["last_scan"]
    tickers_available = list(scan_data["Symbol"].unique())

    selected_ticker = st.selectbox(
        "Wybierz ticker z ostatniego skanu:",
        tickers_available
    )

    if st.button("Przeprowadź Deep Dive"):
        row = scan_data[scan_data["Symbol"] == selected_ticker].iloc[0]

        # Wykresy
        chart_df = get_chart_data(selected_ticker)

        if chart_df is None:
            st.warning("Brak danych wykresowych dla tego tickera.")
        else:
            # ŚWIECOWY + EMA
            st.markdown("### 📈 Mini‑wykres świecowy (6m) + EMA20/EMA50")

            fig = go.Figure(data=[
                go.Candlestick(
                    x=chart_df.index,
                    open=chart_df["Open"],
                    high=chart_df["High"],
                    low=chart_df["Low"],
                    close=chart_df["Close"],
                    increasing_line_color="#00ff99",
                    decreasing_line_color="#ff0066",
                    name="Cena"
                )
            ])

            fig.add_trace(go.Scatter(
                x=chart_df.index,
                y=chart_df["EMA20"],
                mode="lines",
                line=dict(color="#00ccff", width=1.5),
                name="EMA20"
            ))
            fig.add_trace(go.Scatter(
                x=chart_df.index,
                y=chart_df["EMA50"],
                mode="lines",
                line=dict(color="#ffcc00", width=1.5),
                name="EMA50"
            ))

            fig.update_layout(
                height=350,
                margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor="#050510",
                plot_bgcolor="#050510",
                font=dict(color="#ffcc00"),
                xaxis_rangeslider_visible=False
            )

            st.plotly_chart(fig, use_container_width=True)

            # RSI
            st.markdown("### 📉 RSI (14) — historia")

            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Scatter(
                x=chart_df.index,
                y=chart_df["RSI"],
                mode="lines",
                line=dict(color="#ff0099", width=2),
                name="RSI"
            ))

            fig_rsi.add_hline(y=70, line=dict(color="#ff0066", dash="dot"))
            fig_rsi.add_hline(y=30, line=dict(color="#00ff99", dash="dot"))

            fig_rsi.update_layout(
                height=200,
                margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor="#050510",
                plot_bgcolor="#050510",
                font=dict(color="#ffcc00")
            )

            st.plotly_chart(fig_rsi, use_container_width=True)

            # MACD
            st.markdown("### 📊 MACD — historia")

            fig_macd = go.Figure()
            fig_macd.add_trace(go.Scatter(
                x=chart_df.index,
                y=chart_df["MACD"],
                mode="lines",
                line=dict(color="#ffcc00", width=2),
                name="MACD"
            ))
            fig_macd.add_trace(go.Scatter(
                x=chart_df.index,
                y=chart_df["Signal"],
                mode="lines",
                line=dict(color="#00ccff", width=2),
                name="Signal"
            ))

            fig_macd.update_layout(
                height=200,
                margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor="#050510",
                plot_bgcolor="#050510",
                font=dict(color="#ffcc00")
            )

            st.plotly_chart(fig_macd, use_container_width=True)

            # MOMENTUM
            st.markdown("### ⚡ Momentum 10d — historia")

            fig_mom = go.Figure()
            fig_mom.add_trace(go.Bar(
                x=chart_df.index,
                y=chart_df["Momentum10d"],
                marker_color="#ffcc00",
                name="Momentum 10d (%)"
            ))

            fig_mom.update_layout(
                height=200,
                margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor="#050510",
                plot_bgcolor="#050510",
                font=dict(color="#ffcc00")
            )

            st.plotly_chart(fig_mom, use_container_width=True)

        # AI Deep Dive
        if client:
            single_prompt = build_single_ticker_prompt(row)

            with st.spinner(f"AI analizuje {selected_ticker} (Deep Dive)..."):
                res_single = client.chat.completions.create(
                    model=model_choice,
                    messages=[
                        {"role": "system", "content": build_system_prompt()},
                        {"role": "user", "content": single_prompt}
                    ],
                    temperature=0.25
                )
                st.markdown(f"### 🤖 Analiza techniczna — {selected_ticker}")
                st.write(res_single.choices[0].message.content)
        else:
            st.info("Brak klucza API — analiza AI dla tickera wyłączona.")

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
