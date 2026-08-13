import os
import re
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

# ---------------- CONFIG ----------------

st.set_page_config(page_title="CYBER DESK PRO", page_icon="💠", layout="wide")

# Dark / neon style
st.markdown(
    """
    <style>
    body, .stApp {
        background-color: #050816;
        color: #E0E0FF;
    }
    .stSidebar, section[data-testid="stSidebar"] {
        background: radial-gradient(circle at top, #111827 0, #020617 60%);
        color: #E0E0FF;
    }
    .stButton>button {
        background: linear-gradient(90deg, #0ea5e9, #6366f1);
        color: white;
        border-radius: 8px;
        border: none;
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #22c55e, #6366f1);
        color: #e5e7eb;
    }
    .stTextInput>div>div>input {
        background-color: #020617;
        color: #e5e7eb;
    }
    .stSelectbox>div>div>div {
        background-color: #020617;
        color: #e5e7eb;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 💠 CYBER DESK PRO")
    st.caption("1 plik · Czat + Trading + Skaner · GPT-4.1 + Tavily + yfinance")
    mode = st.radio(
        "Tryb pracy:",
        [
            "🤖 Czat AI (internet + trading)",
            "📈 Kombajn tradingowy",
            "🧪 Skaner spółek (wpisz własne tickery)",
        ],
    )


# ---------------- POMOCNICZE ----------------

def detect_ticker_from_text(text: str):
    """Wykrywa ticker w formacie np. AAPL, MSFT, STX.WA"""
    pattern = r"\b[A-Z0-9]{2,5}\.[A-Z]{2,3}\b|\b[A-Z]{1,5}\b"
    matches = re.findall(pattern, text)
    stop_words = {'I', 'A', 'THE', 'TO', 'FOR', 'OF', 'WITH', 'ON', 'AT', 'BY', 'IN', 'IS', 'IT', 'AS', 'OR', 'AND', 'BUT'}
    for m in matches:
        if m not in stop_words and len(m) >= 2:
            return m
    return None


def to_scalar(x):
    if isinstance(x, (pd.Series, np.ndarray, list)):
        if len(x) == 0:
            return np.nan
        try:
            return float(np.asarray(x).ravel()[-1])
        except Exception:
            return np.nan
    try:
        return float(x)
    except Exception:
        return np.nan


# ---------------- MODUŁ 2: KOMBAJN TRADINGOWY ----------------

def compute_indicators(close, volume):
    """Oblicza wszystkie wskaźniki techniczne"""
    close = close.copy()
    volume = volume.copy()
    
    if len(close) < 30:
        return {
            "rsi": np.nan, "ma_fast": np.nan, "ma_slow": np.nan,
            "upper_bb": pd.Series([np.nan]), "lower_bb": pd.Series([np.nan]),
            "last_upper_bb": np.nan, "last_lower_bb": np.nan,
            "macd": pd.Series([np.nan]), "macd_signal": pd.Series([np.nan]),
            "macd_hist": pd.Series([np.nan]),
            "last_macd": np.nan, "last_macd_signal": np.nan, "last_macd_hist": np.nan,
            "vol": np.nan, "volume": np.nan,
            "sl": np.nan, "tp": np.nan,
            "trend": "Unknown",
            "atr": np.nan, "adx": np.nan,
            "obv": np.nan, "vwap": np.nan,
            "roc": np.nan, "stoch_k": np.nan, "stoch_d": np.nan,
            "rvol": np.nan
        }

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.dropna()
    last_rsi = to_scalar(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

    # MA
    ma_fast_series = close.rolling(10).mean().dropna()
    ma_slow_series = close.rolling(30).mean().dropna()
    last_ma_fast = to_scalar(ma_fast_series.iloc[-1]) if not ma_fast_series.empty else np.nan
    last_ma_slow = to_scalar(ma_slow_series.iloc[-1]) if not ma_slow_series.empty else np.nan

    # Bollinger
    ma_bb = close.rolling(20).mean()
    std_bb = close.rolling(20).std()
    upper_bb = ma_bb + 2 * std_bb
    lower_bb = ma_bb - 2 * std_bb
    last_upper_bb = to_scalar(upper_bb.iloc[-1]) if not upper_bb.dropna().empty else np.nan
    last_lower_bb = to_scalar(lower_bb.iloc[-1]) if not lower_bb.dropna().empty else np.nan

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_series = ema12 - ema26
    macd_signal_series = macd_series.ewm(span=9, adjust=False).mean()
    macd_hist_series = macd_series - macd_signal_series
    last_macd = to_scalar(macd_series.iloc[-1]) if not macd_series.empty else np.nan
    last_macd_signal = to_scalar(macd_signal_series.iloc[-1]) if not macd_signal_series.empty else np.nan
    last_macd_hist = to_scalar(macd_hist_series.iloc[-1]) if not macd_hist_series.empty else np.nan

    # Volatility
    vol_series = close.pct_change().rolling(20).std().dropna()
    last_vol = to_scalar(vol_series.iloc[-1]) if not vol_series.empty else np.nan

    # Volume
    last_volume = to_scalar(volume.iloc[-1]) if not volume.empty else np.nan

    # ATR
    high = close.rolling(1).max()
    low = close.rolling(1).min()
    high_low = (high - low).abs()
    high_close_prev = (high - close.shift(1)).abs()
    low_close_prev = (low - close.shift(1)).abs()
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    atr_series = tr.rolling(14).mean()
    last_atr = to_scalar(atr_series.iloc[-1]) if not atr_series.dropna().empty else np.nan

    # ADX
    try:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        tr_adx = pd.concat([
            (high - low).abs(),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_adx = tr_adx.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_adx + 1e-9))
        minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_adx + 1e-9))
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
        adx_series = dx.rolling(14).mean()
        last_adx = to_scalar(adx_series.iloc[-1]) if not adx_series.dropna().empty else np.nan
    except:
        last_adx = np.nan

    # OBV
    try:
        obv = volume.copy()
        obv[:] = 0
        obv = obv.where(close == close.shift(1), np.where(close > close.shift(1), volume, -volume)).cumsum()
        last_obv = to_scalar(obv.iloc[-1]) if not obv.empty else np.nan
    except:
        last_obv = np.nan

    # VWAP
    try:
        vwap_series = (close * volume).rolling(20).sum() / (volume.rolling(20).sum() + 1e-9)
        last_vwap = to_scalar(vwap_series.iloc[-1]) if not vwap_series.dropna().empty else np.nan
    except:
        last_vwap = np.nan

    # ROC
    try:
        roc_series = close.pct_change(10) * 100
        last_roc = to_scalar(roc_series.iloc[-1]) if not roc_series.dropna().empty else np.nan
    except:
        last_roc = np.nan

    # Stochastic
    try:
        low14 = close.rolling(14).min()
        high14 = close.rolling(14).max()
        stoch_k = (close - low14) / (high14 - low14 + 1e-9) * 100
        stoch_d = stoch_k.rolling(3).mean()
        last_stoch_k = to_scalar(stoch_k.iloc[-1]) if not stoch_k.dropna().empty else np.nan
        last_stoch_d = to_scalar(stoch_d.iloc[-1]) if not stoch_d.dropna().empty else np.nan
    except:
        last_stoch_k = np.nan
        last_stoch_d = np.nan

    # RVOL
    try:
        avg_vol_20 = volume.rolling(20).mean()
        rvol_series = volume / (avg_vol_20 + 1e-9)
        last_rvol = to_scalar(rvol_series.iloc[-1]) if not rvol_series.dropna().empty else np.nan
    except:
        last_rvol = np.nan

    # SL/TP
    sl_level = last_lower_bb if not np.isnan(last_lower_bb) else np.nan
    tp_level = last_upper_bb if not np.isnan(last_upper_bb) else np.nan

    # Trend
    if not np.isnan(last_ma_fast) and not np.isnan(last_ma_slow):
        if last_ma_fast > last_ma_slow * 1.01:
            trend = "Uptrend"
        elif last_ma_fast < last_ma_slow * 0.99:
            trend = "Downtrend"
        else:
            trend = "Sideways"
    else:
        trend = "Unknown"

    return {
        "rsi": last_rsi,
        "ma_fast": last_ma_fast,
        "ma_slow": last_ma_slow,
        "upper_bb": upper_bb,
        "lower_bb": lower_bb,
        "last_upper_bb": last_upper_bb,
        "last_lower_bb": last_lower_bb,
        "macd": macd_series,
        "macd_signal": macd_signal_series,
        "macd_hist": macd_hist_series,
        "last_macd": last_macd,
        "last_macd_signal": last_macd_signal,
        "last_macd_hist": last_macd_hist,
        "vol": last_vol,
        "volume": last_volume,
        "sl": sl_level,
        "tp": tp_level,
        "trend": trend,
        "atr": last_atr,
        "adx": last_adx,
        "obv": last_obv,
        "vwap": last_vwap,
        "roc": last_roc,
        "stoch_k": last_stoch_k,
        "stoch_d": last_stoch_d,
        "rvol": last_rvol,
    }


def compute_scoring_pro(ind, sentiment: str | None = None):
    """Oblicza scoring dla spółki"""
    score = 0

    if ind["trend"] == "Uptrend":
        score += 20
    elif ind["trend"] == "Sideways":
        score += 10

    adx = ind.get("adx", np.nan)
    if not np.isnan(adx):
        if adx > 40:
            score += 20
        elif adx > 25:
            score += 15
        elif adx > 20:
            score += 10

    rsi = ind.get("rsi", np.nan)
    if not np.isnan(rsi):
        if 30 <= rsi <= 50:
            score += 15
        elif rsi < 30:
            score += 10
        elif 50 < rsi <= 70:
            score += 5

    k = ind.get("stoch_k", np.nan)
    d = ind.get("stoch_d", np.nan)
    if not np.isnan(k) and not np.isnan(d):
        if k < 20 and d < 20:
            score += 10
        elif k > 80 and d > 80:
            score += 0
        else:
            score += 5

    rvol = ind.get("rvol", np.nan)
    if not np.isnan(rvol):
        if rvol > 1.5:
            score += 15
        elif rvol > 1.0:
            score += 10
        elif rvol > 0.7:
            score += 5

    if not np.isnan(ind.get("last_macd", np.nan)) and not np.isnan(ind.get("last_macd_signal", np.nan)):
        if ind["last_macd"] > ind["last_macd_signal"]:
            score += 10

    if not np.isnan(ind.get("last_lower_bb", np.nan)):
        score += 5
    if not np.isnan(ind.get("last_upper_bb", np.nan)):
        score += 5

    atr = ind.get("atr", np.nan)
    if not np.isnan(atr):
        score += 5

    if sentiment == "Bullish":
        score += 10
    elif sentiment == "Bearish":
        score -= 10

    return max(0, min(score, 100))


def generate_signal(price, ind):
    """Generuje sygnał tradingowy"""
    rsi = ind["rsi"]
    ma_fast = ind["ma_fast"]
    ma_slow = ind["ma_slow"]
    trend = ind["trend"]
    adx = ind.get("adx", np.nan)
    rvol = ind.get("rvol", np.nan)
    stoch_k = ind.get("stoch_k", np.nan)
    stoch_d = ind.get("stoch_d", np.nan)
    sl = ind["sl"]
    tp = ind["tp"]
    vol = ind["vol"]

    if any(np.isnan(x) for x in [rsi, ma_fast, ma_slow]):
        return "HOLD", "Za mało danych do wygenerowania sygnału."

    reasons = []
    signal = "HOLD"

    if trend == "Uptrend":
        reasons.append("📈 Trend wzrostowy (MA10 > MA30)")
    elif trend == "Downtrend":
        reasons.append("📉 Trend spadkowy (MA10 < MA30)")
    else:
        reasons.append("➡️ Trend boczny / niejednoznaczny")

    if not np.isnan(adx):
        if adx < 20:
            reasons.append(f"🔹 ADX {adx:.1f} → słaby trend")
        elif adx < 40:
            reasons.append(f"🔸 ADX {adx:.1f} → umiarkowany trend")
        else:
            reasons.append(f"🔺 ADX {adx:.1f} → silny trend")

    if rsi < 30:
        reasons.append(f"📊 RSI {rsi:.1f} → wyprzedanie")
    elif rsi > 70:
        reasons.append(f"📊 RSI {rsi:.1f} → wykupienie")
    else:
        reasons.append(f"📊 RSI {rsi:.1f} → strefa neutralna")

    if not np.isnan(stoch_k) and not np.isnan(stoch_d):
        if stoch_k < 20 and stoch_d < 20:
            reasons.append(f"🔻 Stochastic %K/D: {stoch_k:.1f}/{stoch_d:.1f} → wyprzedanie")
        elif stoch_k > 80 and stoch_d > 80:
            reasons.append(f"🔺 Stochastic %K/D: {stoch_k:.1f}/{stoch_d:.1f} → wykupienie")

    if not np.isnan(rvol):
        if rvol > 1.5:
            reasons.append(f"📊 RVOL {rvol:.2f} → podwyższony wolumen")
        elif rvol < 0.7:
            reasons.append(f"📊 RVOL {rvol:.2f} → niski wolumen")

    if trend == "Uptrend" and rsi < 40:
        signal = "BUY"
        reasons.append("✅ Sygnał BUY: trend wzrostowy + RSI < 40")
    elif trend == "Downtrend" and rsi > 60:
        signal = "SELL"
        reasons.append("⛔ Sygnał SELL: trend spadkowy + RSI > 60")
    elif trend == "Uptrend" and rsi < 50 and rsi > 30:
        signal = "BUY"
        reasons.append("✅ Sygnał BUY: trend wzrostowy + RSI w strefie akumulacji")
    elif trend == "Downtrend" and rsi < 30:
        signal = "BUY"
        reasons.append("✅ Sygnał BUY: wyprzedanie w trendzie spadkowym (kontra)")
    else:
        signal = "HOLD"
        reasons.append("⏸️ HOLD: brak jednoznacznego sygnału")

    if not np.isnan(sl):
        reasons.append(f"🛑 SL: {sl:.2f}")
    if not np.isnan(tp):
        reasons.append(f"🎯 TP: {tp:.2f}")

    return signal, "\n".join(f"- {r}" for r in reasons)


def fetch_news_sentiment(ticker):
    """Pobiera sentyment z newsów"""
    try:
        t = yf.Ticker(ticker)
        news = t.news if hasattr(t, "news") else []
    except Exception:
        news = []

    titles = [n.get("title", "") for n in news if isinstance(n.get("title", ""), str)]
    titles = [t for t in titles if t.strip()][:5]

    if not titles:
        return "Mixed", [], "Brak newsów."

    score = 0
    positive_words = ["beat", "strong", "growth", "upgrade", "profit", "record", "surge", "rally", "positive"]
    negative_words = ["miss", "weak", "downgrade", "fall", "loss", "cut", "crash", "negative", "concern"]

    for title in titles:
        tl = title.lower()
        if any(w in tl for w in positive_words):
            score += 1
        if any(w in tl for w in negative_words):
            score -= 1

    sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"
    return sentiment, titles, ""


def render_trading():
    """Renderuje panel tradingowy"""
    st.title("📈 Kombajn tradingowy – pełny panel")
    st.caption("Świece, wskaźniki, scoring, sygnały, SL/TP, trend, wolumen, RVOL, news sentiment.")

    ticker = st.text_input("Ticker (np. AAPL, MSFT, STX.WA):", "AAPL")

    col1, col2 = st.columns(2)
    period = col1.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
    interval = col2.selectbox("Interwał:", ["15m", "30m", "1h", "1d"], index=3)

    if st.button("Pobierz dane i policz sygnały", use_container_width=True):
        try:
            with st.spinner(f"Pobieram dane dla {ticker}..."):
                data = yf.download(ticker, period=period, interval=interval, progress=False)
                
                if data.empty:
                    st.error("Brak danych dla tego tickera lub interwału.")
                    return

                if len(data) < 60:
                    st.info("Za mało danych, używam okresu 6mo i interwału 1d")
                    data = yf.download(ticker, period="6mo", interval="1d", progress=False)
                    if data.empty:
                        st.error("Brak wystarczających danych historycznych.")
                        return

                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"].iloc[:, 0]
                    open_ = data["Open"].iloc[:, 0]
                    high = data["High"].iloc[:, 0]
                    low = data["Low"].iloc[:, 0]
                    volume = data["Volume"].iloc[:, 0]
                else:
                    close = data["Close"]
                    open_ = data["Open"]
                    high = data["High"]
                    low = data["Low"]
                    volume = data["Volume"]

                ind = compute_indicators(close, volume)
                price = to_scalar(close.iloc[-1])

                # Wykres
                fig = go.Figure()
                fig.add_trace(
                    go.Candlestick(
                        x=data.index,
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        name="Świece",
                    )
                )
                
                if not ind["upper_bb"].isna().all():
                    fig.add_trace(
                        go.Scatter(
                            x=data.index,
                            y=ind["upper_bb"],
                            line=dict(color="rgba(34,197,94,0.5)", width=1),
                            name="Bollinger górna",
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=data.index,
                            y=ind["lower_bb"],
                            line=dict(color="rgba(239,68,68,0.5)", width=1),
                            name="Bollinger dolna",
                        )
                    )
                
                fig.update_layout(
                    height=500,
                    title=f"{ticker} - {period} ({interval})",
                    paper_bgcolor="#020617",
                    plot_bgcolor="#020617",
                    font=dict(color="#E5E7EB"),
                    xaxis=dict(gridcolor="#1a1a3e"),
                    yaxis=dict(gridcolor="#1a1a3e"),
                )
                st.plotly_chart(fig, use_container_width=True)

                sentiment, titles, comment = fetch_news_sentiment(ticker)
                signal, explanation = generate_signal(price, ind)
                scoring = compute_scoring_pro(ind, sentiment)

                st.subheader("🤖 Analiza automatyczna")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Cena", f"{price:.2f}" if not np.isnan(price) else "Brak")
                    st.metric("RSI (14)", f"{ind['rsi']:.1f}" if not np.isnan(ind['rsi']) else "Brak")
                    st.metric("Trend", ind['trend'])
                    st.metric("Sygnał", signal)
                
                with col2:
                    st.metric("Scoring PRO", f"{scoring}/100")
                    st.metric("ADX (14)", f"{ind['adx']:.1f}" if not np.isnan(ind['adx']) else "Brak")
                    st.metric("RVOL (20)", f"{ind['rvol']:.2f}" if not np.isnan(ind['rvol']) else "Brak")
                    st.metric("Sentyment", sentiment)

                with st.expander("📊 Wszystkie wskaźniki"):
                    indicators = {
                        "RSI (14)": ind['rsi'],
                        "MA10": ind['ma_fast'],
                        "MA30": ind['ma_slow'],
                        "ADX (14)": ind['adx'],
                        "ATR (14)": ind['atr'],
                        "Volatility (20)": ind['vol'],
                        "Volume": ind['volume'],
                        "RVOL (20)": ind['rvol'],
                        "VWAP (20)": ind['vwap'],
                        "ROC (10)": ind['roc'],
                        "Stochastic %K": ind['stoch_k'],
                        "Stochastic %D": ind['stoch_d'],
                        "SL (Bollinger dolna)": ind['sl'],
                        "TP (Bollinger górna)": ind['tp'],
                        "MACD": ind['last_macd'],
                        "MACD Signal": ind['last_macd_signal'],
                    }
                    for name, value in indicators.items():
                        if not np.isnan(value):
                            st.write(f"**{name}:** {value:.2f}" if isinstance(value, float) else f"**{name}:** {value}")

                st.markdown("**Uzasadnienie sygnału:**")
                st.markdown(explanation)

                st.subheader("📰 News sentiment")
                st.write(f"**Sentyment:** {sentiment}")
                if titles:
                    for t in titles:
                        st.write(f"- {t}")

                st.session_state["last_analysis"] = {
                    "ticker": ticker,
                    "price": price,
                    "indicators": ind,
                    "signal": signal,
                    "explanation": explanation,
                    "sentiment": sentiment,
                    "news_titles": titles,
                    "scoring": scoring,
                    "period": period,
                    "interval": interval,
                }

                st.success("✅ Analiza zapisana – czat AI będzie korzystać z tych danych.")

        except Exception as e:
            st.error(f"❌ Błąd: {str(e)}")


# ---------------- MODUŁ: SKANER SPÓŁEK ----------------

def render_scanner():
    """Renderuje skaner spółek"""
    st.title("🧪 Skaner spółek – własne tickery → TOP N")
    st.caption("Wpisz własną listę tickerów, skrypt policzy scoring PRO i wybierze najlepsze.")

    tickers_text = st.text_area(
        "Tickery (oddzielone spacją, przecinkiem lub nową linią):",
        "AAPL MSFT NVDA TSLA AMZN META GOOGL NFLX AMD INTC",
        height=120,
        help="Wpisz tickery spółek, które chcesz przeanalizować"
    )

    max_to_show = st.slider("Ile spółek pokazać (TOP N):", 5, 20, 10)

    if st.button("🔍 Skanuj spółki", use_container_width=True):
        raw = re.split(r'[,\s\n]+', tickers_text)
        tickers = [t.strip().upper() for t in raw if t.strip()]
        tickers = list(dict.fromkeys(tickers))

        if not tickers:
            st.error("Brak poprawnych tickerów.")
            return

        st.info(f"Przetwarzam {len(tickers)} tickerów...")

        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, ticker in enumerate(tickers):
            status_text.text(f"Skanuję: {ticker} ({i+1}/{len(tickers)})")
            progress_bar.progress((i + 1) / len(tickers))

            try:
                data = yf.download(ticker, period="6mo", interval="1d", progress=False)
                if data.empty or len(data) < 30:
                    continue

                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"].iloc[:, 0]
                    volume = data["Volume"].iloc[:, 0]
                else:
                    close = data["Close"]
                    volume = data["Volume"]

                ind = compute_indicators(close, volume)
                price = to_scalar(close.iloc[-1])

                sentiment, _, _ = fetch_news_sentiment(ticker)
                scoring = compute_scoring_pro(ind, sentiment)

                results.append({
                    "Ticker": ticker,
                    "Cena": price,
                    "Trend": ind["trend"],
                    "RSI": ind["rsi"],
                    "ADX": ind["adx"],
                    "RVOL": ind["rvol"],
                    "Sentyment": sentiment,
                    "Scoring": scoring,
                })
            except Exception:
                continue

        progress_bar.empty()
        status_text.empty()

        if not results:
            st.error("Nie udało się policzyć scoringu dla żadnego tickera.")
            return

        df = pd.DataFrame(results)
        df_sorted = df.sort_values("Scoring", ascending=False).head(max_to_show)

        st.subheader(f"🏆 TOP {len(df_sorted)} spółek wg Scoring PRO")

        for _, row in df_sorted.iterrows():
            score = row["Scoring"]
            
            if score >= 70:
                color = "rgba(34,197,94,0.25)"
                border = "2px solid #22c55e"
                label = "🔥 Mocny sygnał"
            elif score >= 40:
                color = "rgba(251,146,60,0.25)"
                border = "2px solid #fb923c"
                label = "📊 Neutralny / obserwacja"
            else:
                color = "rgba(239,68,68,0.25)"
                border = "2px solid #ef4444"
                label = "⚠️ Słaby sygnał"

            st.markdown(
                f"""
                <div style="
                    background-color:{color};
                    padding:15px;
                    border-radius:10px;
                    margin-bottom:10px;
                    border:{border};
                ">
                    <b style="font-size:18px;">{row['Ticker']}</b>
                    <br>Cena: {row['Cena']:.2f} | Trend: {row['Trend']} | RSI: {row['RSI']:.1f}
                    <br>ADX: {row['ADX']:.1f} | RVOL: {row['RVOL']:.2f} | Sentyment: {row['Sentyment']}
                    <br><b>Scoring PRO: {score}/100</b> — {label}
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption("_Scoring PRO łączy trend, ADX, RSI, Stochastic, RVOL, MACD, Bollinger, ATR oraz sentyment newsów._")
        
        if st.button("💾 Zapisz wyniki do CSV"):
            csv = df_sorted.to_csv(index=False)
            st.download_button(
                label="Pobierz CSV",
                data=csv,
                file_name="skaner_wyniki.csv",
                mime="text/csv",
            )


# ---------------- MODUŁ 1: CZAT AI ----------------

def tavily_research(tavily_key, ticker, question):
    """Wyszukiwanie w Tavily"""
    if not tavily_key:
        return "Brak klucza Tavily API.", False
    
    base_queries = [question]
    if ticker:
        base_queries.extend([
            f"{ticker} company profile financials",
            f"{ticker} stock news",
            f"{ticker} analyst ratings",
        ])

    all_answers = []
    all_results = []

    for q in base_queries[:3]:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {tavily_key}"},
                json={
                    "query": q,
                    "topic": "finance",
                    "max_results": 3,
                    "include_answer": True,
                    "include_raw_content": False,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                j = resp.json()
                if j.get("answer"):
                    all_answers.append(j["answer"])
                all_results.extend(j.get("results", []))
        except Exception:
            continue

    filtered_results = []
    ticker_upper = (ticker or "").upper()

    for item in all_results:
        title = item.get("title", "") or ""
        url = item.get("url", "") or ""
        content = item.get("content", "") or ""
        blob = f"{title} {content} {url}"

        if ticker_upper and ticker_upper not in blob.upper():
            continue
        filtered_results.append(item)

    bullets = []
    for item in filtered_results[:5]:
        title = item.get("title", "")
        url = item.get("url", "")
        if title or url:
            bullets.append(f"- {title} ({url})")

    merged_answer = ""
    if all_answers:
        merged_answer = "\n\n".join(all_answers)

    research_text = ""
    if merged_answer:
        research_text += f"Podsumowanie Tavily:\n{merged_answer}\n\n"
    if bullets:
        research_text += "Źródła Tavily:\n" + "\n".join(bullets)

    if not research_text:
        return "Brak wiarygodnych danych z Tavily dla tego tickera.", False

    return research_text, True


def render_ai_chat():
    """Renderuje czat AI"""
    st.title("🤖 Czat AI – Analityk finansowy")
    st.caption("Zero zgadywania: tylko dane z trading engine + Tavily.")

    if "OPENAI_API_KEY" not in st.secrets:
        st.error("❌ Brak OPENAI_API_KEY w .streamlit/secrets.toml")
        st.info("Dodaj plik .streamlit/secrets.toml z zawartością:\n```\
