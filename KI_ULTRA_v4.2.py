import os
import re
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="CYBER DESK PRO — KI_ULTRA v4.2",
    page_icon="💠",
    layout="wide"
)

# --- NEON UI ---
st.markdown(
    "<style>"
    "body, .stApp { background-color: #050816; color: #E0E0FF; }"
    ".stSidebar { background: #0a0f24; }"
    ".stButton>button { background: #0ea5e9; color: white; border-radius: 6px; }"
    ".stButton>button:hover { background: #22c55e; }"
    ".stTextInput>div>div>input { background-color: #020617; color: #e5e7eb; }"
    "</style>",
    unsafe_allow_html=True
)

with st.sidebar:
    st.markdown("### 💠 CYBER DESK PRO — KI_ULTRA v4.2")
    st.caption("Czat AI + Trading + Skaner · GPT‑4.1 + Tavily + yfinance")
    mode = st.radio(
        "Tryb pracy:",
        [
            "🤖 Czat AI (internet + trading)",
            "📈 Kombajn tradingowy",
            "🧪 Skaner spółek (50 → TOP 10)"
        ]
    )

# --- HELPERS ---

def detect_ticker_from_text(text):
    pattern = r\"\\b[A-Z0-9]{2,5}\\.[A-Z]{2,3}\\b\"
    m = re.search(pattern, text)
    return m.group(0) if m else None

def to_scalar(x):
    try:
        if isinstance(x, (pd.Series, np.ndarray, list)):
            return float(np.asarray(x).ravel()[-1])
        return float(x)
    except Exception:
        return np.nan
# --- INDICATORS ENGINE PRO ---

def compute_indicators(close, volume):
    close = close.copy()
    volume = volume.copy()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = to_scalar(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else np.nan

    # MA
    ma_fast = to_scalar(close.rolling(10).mean().dropna().iloc[-1]) if len(close) >= 10 else np.nan
    ma_slow = to_scalar(close.rolling(30).mean().dropna().iloc[-1]) if len(close) >= 30 else np.nan

    # Bollinger
    ma_bb = close.rolling(20).mean()
    std_bb = close.rolling(20).std()
    upper_bb = ma_bb + 2 * std_bb
    lower_bb = ma_bb - 2 * std_bb
    last_upper_bb = to_scalar(upper_bb.dropna().iloc[-1]) if not upper_bb.dropna().empty else np.nan
    last_lower_bb = to_scalar(lower_bb.dropna().iloc[-1]) if not lower_bb.dropna().empty else np.nan

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    last_macd = to_scalar(macd.iloc[-1])
    last_macd_signal = to_scalar(macd_signal.iloc[-1])

    # Volatility
    vol = to_scalar(close.pct_change().rolling(20).std().dropna().iloc[-1]) if len(close) >= 20 else np.nan

    # Volume
    last_volume = to_scalar(volume.iloc[-1]) if len(volume) else np.nan

    # ATR
    high = close.rolling(1).max()
    low = close.rolling(1).min()
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = to_scalar(tr.rolling(14).mean().dropna().iloc[-1]) if len(tr) >= 14 else np.nan

    # ADX
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    tr_adx = tr
    atr_adx = tr_adx.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_adx + 1e-9))
    minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_adx + 1e-9))
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx = to_scalar(dx.rolling(14).mean().dropna().iloc[-1]) if len(dx.dropna()) else np.nan

    # RVOL
    avg_vol_20 = volume.rolling(20).mean()
    rvol = to_scalar((volume / (avg_vol_20 + 1e-9)).dropna().iloc[-1]) if len(volume) >= 20 else np.nan

    # Trend
    if not np.isnan(ma_fast) and not np.isnan(ma_slow):
        trend = "Uptrend" if ma_fast > ma_slow else "Downtrend" if ma_fast < ma_slow else "Sideways"
    else:
        trend = "Unknown"

    return {
        "rsi": rsi,
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
        "upper_bb": upper_bb,
        "lower_bb": lower_bb,
        "last_upper_bb": last_upper_bb,
        "last_lower_bb": last_lower_bb,
        "last_macd": last_macd,
        "last_macd_signal": last_macd_signal,
        "vol": vol,
        "volume": last_volume,
        "atr": atr,
        "adx": adx,
        "rvol": rvol,
        "trend": trend
    }

# --- SCORING PRO ---

def compute_scoring_pro(ind, sentiment):
    score = 0

    if ind["trend"] == "Uptrend":
        score += 20
    elif ind["trend"] == "Sideways":
        score += 10

    if not np.isnan(ind["adx"]):
        if ind["adx"] > 40:
            score += 20
        elif ind["adx"] > 20:
            score += 10

    if not np.isnan(ind["rsi"]):
        if 30 <= ind["rsi"] <= 50:
            score += 15
        elif ind["rsi"] < 30:
            score += 10
        elif ind["rsi"] > 50:
            score += 10

    if not np.isnan(ind["rvol"]):
        if ind["rvol"] > 1.5:
            score += 15
        elif ind["rvol"] > 1.0:
            score += 10

    if ind["last_macd"] > ind["last_macd_signal"]:
        score += 10

    if not np.isnan(ind["last_lower_bb"]):
        score += 5
    if not np.isnan(ind["last_upper_bb"]):
        score += 5

    if not np.isnan(ind["atr"]):
        score += 5

    if sentiment == "Bullish":
        score += 15
    elif sentiment == "Bearish":
        score -= 15

    return max(0, min(score, 100))

# --- SIGNAL AI ---

def generate_signal(price, ind, sentiment):
    if any(np.isnan(x) for x in [ind["rsi"], ind["ma_fast"], ind["ma_slow"]]):
        return "HOLD", "Za mało danych."

    signal = "HOLD"
    reasons = []

    if ind["trend"] == "Uptrend" and ind["rsi"] < 40:
        signal = "BUY"
        reasons.append("Trend wzrostowy + RSI < 40")
    elif ind["trend"] == "Downtrend" and ind["rsi"] > 60:
        signal = "SELL"
        reasons.append("Trend spadkowy + RSI > 60")
    else:
        reasons.append("Brak jednoznacznego sygnału")

    if sentiment == "Bullish" and signal == "HOLD":
        signal = "BUY"
        reasons.append("News Bullish → BUY")
    elif sentiment == "Bearish" and signal == "HOLD":
        signal = "SELL"
        reasons.append("News Bearish → SELL")

    return signal, "\n".join(reasons)

# --- NEWS SENTIMENT PRO ---

def fetch_news_sentiment(ticker):
    headlines = []

    try:
        key = st.secrets.get("TAVILY_API_KEY", None)
        if key:
            r = requests.post(
                "https://api.tavily.com/search",
                headers={"Authorization": "Bearer " + key},
                json={
                    "query": ticker + " stock news finance",
                    "topic": "finance",
                    "max_results": 8
                },
                timeout=10
            )
            j = r.json()
            for item in j.get("results", []):
                title = item.get("title", "")
                if ticker.upper() in title.upper():
                    headlines.append(title)
    except Exception:
        pass

    if not headlines:
        try:
            news = yf.Ticker(ticker).news
            for n in news:
                title = n.get("title", "")
                if ticker.upper() in title.upper():
                    headlines.append(title)
        except Exception:
            pass

    if not headlines:
        return "Mixed", [], "Brak newsów."

    score = 0
    for t in headlines:
        tl = t.lower()
        if any(w in tl for w in ["beat", "strong", "growth", "upgrade"]):
            score += 1
        if any(w in tl for w in ["miss", "weak", "downgrade", "fall"]):
            score -= 1

    sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"
    return sentiment, headlines[:5], ""
# --- TRADING PANEL ---

def render_trading():
    st.title("📈 Kombajn tradingowy")
    ticker = st.text_input("Ticker:", "AAPL")

    col1, col2 = st.columns(2)
    period = col1.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
    interval = col2.selectbox("Interwał:", ["15m", "30m", "1h", "1d"], index=3)

    if st.button("Analizuj", use_container_width=True):
        data = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=True
        )

        if data.empty:
            st.error("Brak danych.")
            return

        close = data["Close"]
        volume = data["Volume"]
        open_ = data["Open"]
        high = data["High"]
        low = data["Low"]

        # OPCJE FIX
        if close.mean() < 5 and ticker.upper() in ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL"]:
            data = yf.download(
                tickers=ticker,
                period="6mo",
                interval="1d",
                auto_adjust=True
            )
            close = data["Close"]
            volume = data["Volume"]
            open_ = data["Open"]
            high = data["High"]
            low = data["Low"]

        ind = compute_indicators(close, volume)
        price = to_scalar(close.iloc[-1])

        # WYKRES
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=data.index,
            open=open_,
            high=high,
            low=low,
            close=close
        ))
        fig.add_trace(go.Scatter(x=data.index, y=ind["upper_bb"], line=dict(color="green"), name="BB Upper"))
        fig.add_trace(go.Scatter(x=data.index, y=ind["lower_bb"], line=dict(color="red"), name="BB Lower"))
        fig.update_layout(height=500, paper_bgcolor="#020617", plot_bgcolor="#020617")
        st.plotly_chart(fig, use_container_width=True)

        sentiment, titles, comment = fetch_news_sentiment(ticker)
        signal, explanation = generate_signal(price, ind, sentiment)
        scoring = compute_scoring_pro(ind, sentiment)

        st.subheader("Sygnał AI")
        st.write("Ticker:", ticker)
        st.write("Cena:", price)
        st.write("RSI:", ind["rsi"])
        st.write("Trend:", ind["trend"])
        st.write("ADX:", ind["adx"])
        st.write("RVOL:", ind["rvol"])
        st.write("SL:", ind["last_lower_bb"])
        st.write("TP:", ind["last_upper_bb"])
        st.write("Sygnał:", signal)
        st.write("Scoring PRO:", scoring)
        st.write("Uzasadnienie:")
        st.write(explanation)

        st.subheader("NEWS RADAR")
        st.write("Sentyment:", sentiment)
        for t in titles:
            st.write("-", t)

        st.session_state["last_analysis"] = {
            "ticker": ticker,
            "price": price,
            "indicators": ind,
            "signal": signal,
            "explanation": explanation,
            "sentiment": sentiment,
            "news_titles": titles,
            "scoring": scoring
        }

# --- SKANER ---

def render_scanner():
    st.title("🧪 Skaner spółek — TOP 10")
    tickers_text = st.text_area("Tickery:", "AAPL MSFT NVDA TSLA AMZN")
    max_to_show = st.slider("TOP N:", 5, 20, 10)

    if st.button("Skanuj", use_container_width=True):
        raw = tickers_text.replace(",", " ").split()
        tickers = [t.strip().upper() for t in raw if t.strip()]
        tickers = list(dict.fromkeys(tickers))

        results = []
        progress = st.progress(0.0)

        for i, t in enumerate(tickers):
            progress.progress((i + 1) / len(tickers))

            data = yf.download(
                tickers=t,
                period="6mo",
                interval="1d",
                auto_adjust=True
            )
            if data.empty or len(data) < 60:
                continue

            close = data["Close"]
            volume = data["Volume"]

            ind = compute_indicators(close, volume)
            price = to_scalar(close.iloc[-1])
            sentiment, titles, _ = fetch_news_sentiment(t)
            scoring = compute_scoring_pro(ind, sentiment)

            results.append({
                "Ticker": t,
                "Cena": price,
                "Trend": ind["trend"],
                "RSI": ind["rsi"],
                "ADX": ind["adx"],
                "RVOL": ind["rvol"],
                "Sentyment": sentiment,
                "Scoring": scoring
            })

        progress.empty()

        if not results:
            st.error("Brak wyników.")
            return

        df = pd.DataFrame(results).sort_values("Scoring", ascending=False).head(max_to_show)

        st.subheader("Wyniki TOP")
        for _, row in df.iterrows():
            st.write(
                row["Ticker"],
                "| Cena:", row["Cena"],
                "| Trend:", row["Trend"],
                "| Sentyment:", row["Sentyment"],
                "| Scoring:", row["Scoring"]
            )
# --- TAVILY RESEARCH ---

def tavily_research(key, ticker, question):
    if not key:
        return "Brak Tavily.", False

    queries = [question]
    if ticker:
        queries.append(ticker + " stock analysis")

    answers = []
    results = []

    for q in queries:
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                headers={"Authorization": "Bearer " + key},
                json={"query": q, "topic": "finance",
