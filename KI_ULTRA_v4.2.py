import os
import re
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

# ---------------- CONFIG ----------------

st.set_page_config(page_title="CYBER DESK PRO — KI_ULTRA v4.2", page_icon="💠", layout="wide")

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
    st.markdown("### 💠 CYBER DESK PRO — KI_ULTRA v4.2")
    st.caption("1 plik · Czat + Trading + Skaner · GPT-4.1 + Tavily + yfinance")
    mode = st.radio(
        "Tryb pracy:",
        [
            "🤖 Czat AI (internet + trading)",
            "📈 Kombajn tradingowy",
            "🧪 Skaner spółek (50 → TOP 10)",
        ],
    )

# ---------------- POMOCNICZE ----------------

def detect_ticker_from_text(text: str):
    pattern = r"\b[A-Z0-9]{2,5}\.[A-Z]{2,3}\b"
    m = re.search(pattern, text)
    if m:
        return m.group(0)
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
# ---------------- MODUŁ 2: KOMBAJN TRADINGOWY (DATA ENGINE PRO) ----------------

def compute_indicators(close, volume):
    close = close.copy()
    volume = volume.copy()

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
    last_macd = to_scalar(macd_series.iloc[-1])
    last_macd_signal = to_scalar(macd_signal_series.iloc[-1])
    last_macd_hist = to_scalar(macd_hist_series.iloc[-1])

    # Volatility (20)
    vol_series = close.pct_change().rolling(20).std().dropna()
    last_vol = to_scalar(vol_series.iloc[-1]) if not vol_series.empty else np.nan

    # Volume
    last_volume = to_scalar(volume.iloc[-1]) if not volume.empty else np.nan

    # ATR
    high = close.rolling(1).max()
    low = close.rolling(1).min()
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_series = tr.rolling(14).mean()
    last_atr = to_scalar(atr_series.iloc[-1]) if not atr_series.dropna().empty else np.nan

    # ADX
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr_adx = pd.concat(
        [
            (high - low).abs(),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_adx = tr_adx.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_adx + 1e-9))
    minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_adx + 1e-9))
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx_series = dx.rolling(14).mean()
    last_adx = to_scalar(adx_series.iloc[-1]) if not adx_series.dropna().empty else np.nan

    # OBV
    obv = volume.copy()
    obv[:] = 0
    obv = obv.where(close == close.shift(1), np.where(close > close.shift(1), volume, -volume)).cumsum()
    last_obv = to_scalar(obv.iloc[-1]) if not obv.empty else np.nan

    # VWAP
    vwap_series = (close * volume).rolling(20).sum() / (volume.rolling(20).sum() + 1e-9)
    last_vwap = to_scalar(vwap_series.iloc[-1]) if not vwap_series.dropna().empty else np.nan

    # ROC
    roc_series = close.pct_change(10) * 100
    last_roc = to_scalar(roc_series.iloc[-1]) if not roc_series.dropna().empty else np.nan

    # Stochastic
    low14 = close.rolling(14).min()
    high14 = close.rolling(14).max()
    stoch_k = (close - low14) / (high14 - low14 + 1e-9) * 100
    stoch_d = stoch_k.rolling(3).mean()
    last_stoch_k = to_scalar(stoch_k.iloc[-1]) if not stoch_k.dropna().empty else np.nan
    last_stoch_d = to_scalar(stoch_d.iloc[-1]) if not stoch_d.dropna().empty else np.nan

    # RVOL
    avg_vol_20 = volume.rolling(20).mean()
    rvol_series = volume / (avg_vol_20 + 1e-9)
    last_rvol = to_scalar(rvol_series.iloc[-1]) if not rvol_series.dropna().empty else np.nan

    # Trend
    if not np.isnan(last_ma_fast) and not np.isnan(last_ma_slow):
        if last_ma_fast > last_ma_slow:
            trend = "Uptrend"
        elif last_ma_fast < last_ma_slow:
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
        "atr": last_atr,
        "adx": last_adx,
        "obv": last_obv,
        "vwap": last_vwap,
        "roc": last_roc,
        "stoch_k": last_stoch_k,
        "stoch_d": last_stoch_d,
        "rvol": last_rvol,
        "trend": trend,
    }


def compute_scoring_pro(ind, sentiment: str | None = None):
    score = 0

    if ind["trend"] == "Uptrend":
        score += 20
    elif ind["trend"] == "Sideways":
        score += 10

    adx = ind.get("adx", np.nan)
    if not np.isnan(adx):
        if adx > 40:
            score += 20
        elif adx > 20:
            score += 10

    rsi = ind.get("rsi", np.nan)
    if not np.isnan(rsi):
        if 30 <= rsi <= 50:
            score += 15
        elif rsi < 30:
            score += 10
        elif 50 < rsi <= 70:
            score += 10

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

    if ind.get("last_macd", np.nan) > ind.get("last_macd_signal", np.nan):
        score += 10

    if not np.isnan(ind.get("last_lower_bb", np.nan)):
        score += 5
    if not np.isnan(ind.get("last_upper_bb", np.nan)):
        score += 5

    if not np.isnan(ind.get("atr", np.nan)):
        score += 5

    if sentiment == "Bullish":
        score += 15
    elif sentiment == "Bearish":
        score -= 15

    return max(0, min(score, 100))


def generate_signal(price, ind, sentiment: str | None = None):
    rsi = ind["rsi"]
    ma_fast = ind["ma_fast"]
    ma_slow = ind["ma_slow"]
    vol = ind["vol"]
    sl = ind["last_lower_bb"]
    tp = ind["last_upper_bb"]
    trend = ind["trend"]
    adx = ind.get("adx", np.nan)
    rvol = ind.get("rvol", np.nan)
    stoch_k = ind.get("stoch_k", np.nan)
    stoch_d = ind.get("stoch_d", np.nan)

    if any(np.isnan(x) for x in [rsi, ma_fast, ma_slow]):
        return "HOLD", "Za mało danych do wygenerowania sygnału."

    reasons = []
    signal = "HOLD"

    if trend == "Uptrend":
        reasons.append("Trend wzrostowy (MA10 > MA30).")
    elif trend == "Downtrend":
        reasons.append("Trend spadkowy (MA10 < MA30).")
    else:
        reasons.append("Trend boczny / niejednoznaczny.")

    if not np.isnan(adx):
        if adx < 20:
            reasons.append(f"ADX {adx:.1f} → słaby trend.")
        elif adx < 40:
            reasons.append(f"ADX {adx:.1f} → umiarkowany trend.")
        else:
            reasons.append(f"ADX {adx:.1f} → silny trend.")

    if rsi < 30:
        reasons.append("RSI < 30 → wyprzedanie.")
    elif rsi > 70:
        reasons.append("RSI > 70 → wykupienie.")
    else:
        reasons.append("RSI neutralne.")

    if not np.isnan(stoch_k) and not np.isnan(stoch_d):
        if stoch_k < 20 and stoch_d < 20:
            reasons.append("Stochastic <20 → wyprzedanie.")
        elif stoch_k > 80 and stoch_d > 80:
            reasons.append("Stochastic >80 → wykupienie.")

    if not np.isnan(rvol):
        if rvol > 1.5:
            reasons.append(f"RVOL {rvol:.2f} → wysoka aktywność.")
        elif rvol < 0.7:
            reasons.append(f"RVOL {rvol:.2f} → niska aktywność.")

    if trend == "Uptrend" and rsi < 40:
        signal = "BUY"
        reasons.append("Trend wzrostowy + RSI < 40 → akumulacja.")
    elif trend == "Downtrend" and rsi > 60:
        signal = "SELL"
        reasons.append("Trend spadkowy + RSI > 60 → dystrybucja.")
    else:
        signal = "HOLD"
        reasons.append("Brak jednoznacznego sygnału.")

    if sentiment == "Bullish" and signal == "HOLD":
        signal = "BUY"
        reasons.append("News sentiment Bullish → wzmocnienie sygnału kupna.")
    elif sentiment == "Bearish" and signal == "HOLD":
        signal = "SELL"
        reasons.append("News sentiment Bearish → wzmocnienie sygnału sprzedaży.")

    if not np.isnan(sl):
        reasons.append(f"SL (Bollinger dolna): {sl:.2f}")
    if not np.isnan(tp):
        reasons.append(f"TP (Bollinger górna): {tp:.2f}")
    if not np.isnan(vol):
        reasons.append(f"Zmienność (20): {vol:.4f}")

    return signal, "\n".join(f"- {r}" for r in reasons)


def fetch_news_sentiment(ticker):
    headlines = []

    try:
        tavily_key = st.secrets.get("TAVILY_API_KEY", None)
        if tavily_key:
            resp = requests.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {tavily_key}"},
                json={
                    "query": f"{ticker} stock news finance",
                    "topic": "finance",
                    "max_results": 8,
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=12,
            )
            resp.raise_for_status()
            j = resp.json()
            results = j.get("results", [])
        else:
            results = []
    except Exception:
        results = []

    for r in results:
        title = r.get("title", "")
        if not title:
            continue
        bad = ["shocking", "insane", "crazy", "must see", "you won't believe"]
        if any(b in title.lower() for b in bad):
            continue
        if ticker.upper() not in title.upper():
            continue
        headlines.append(title.strip())

    if not headlines:
        try:
            t = yf.Ticker(ticker)
            news = t.news if hasattr(t, "news") else []
            for n in news:
                title = n.get("title", "")
                if title and ticker.upper() in title.upper():
                    headlines.append(title.strip())
        except Exception:
            pass

    if not headlines:
        return "Mixed", [], "Brak newsów dla tego tickera."

    score = 0
    for title in headlines:
        tl = title.lower()
        if any(w in tl for w in ["beat", "strong", "growth", "upgrade", "profit", "record", "surge"]):
            score += 1
        if any(w in tl for w in ["miss", "weak", "downgrade", "fall", "loss", "cut", "plunge"]):
            score -= 1

    sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"
    return sentiment, headlines[:5], ""
def render_trading():
    st.title("📈 Kombajn tradingowy – pełny panel (Data Engine PRO)")
    st.caption("Świece, wskaźniki PRO, scoring, sygnały, SL/TP, trend, wolumen, RVOL, NEWS RADAR.")

    ticker = st.text_input("Ticker (np. AAPL, MSFT, STX.WA):", "AAPL")

    col1, col2 = st.columns(2)
    period = col1.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
    interval = col2.selectbox("Interwał:", ["15m", "30m", "1h", "1d"], index=3)

    if st.button("Pobierz dane i policz sygnały", use_container_width=True):
        try:
            data = yf.download(
                tickers=ticker,
                period=period,
                interval=interval,
                auto_adjust=True,
                group_by="ticker",
            )
            if data.empty:
                st.error("Brak danych dla tego tickera lub interwału.")
                return

            if len(data) < 60:
                data = yf.download(
                    tickers=ticker,
                    period="6mo",
                    interval="1d",
                    auto_adjust=True,
                    group_by="ticker",
                )
                if data.empty:
                    st.error("Brak wystarczających danych historycznych (nawet po fallbacku 6m).")
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

            # prosty filtr na dane opcyjne (bardzo niska cena przy znanym dużym tickerze)
            if close.mean() < 5 and ticker.upper() in ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL"]:
                st.warning("Wykryto podejrzanie niskie ceny (możliwe dane opcyjne) – wymuszam pobranie danych akcji (6m, 1d).")
                data = yf.download(
                    tickers=ticker,
                    period="6mo",
                    interval="1d",
                    auto_adjust=True,
                    group_by="ticker",
                )
                if data.empty:
                    st.error("Brak poprawnych danych akcyjnych po wymuszeniu.")
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
                title=f"Wykres {ticker}",
                paper_bgcolor="#020617",
                plot_bgcolor="#020617",
                font=dict(color="#E5E7EB"),
            )
            st.plotly_chart(fig, use_container_width=True)

            sentiment, titles, comment = fetch_news_sentiment(ticker)

            signal, explanation = generate_signal(price, ind, sentiment)
            scoring = compute_scoring_pro(ind, sentiment)

            st.subheader("🤖 AI Sygnał automatyczny (engine PRO + NEWS)")
            st.write(f"**Ticker:** {ticker}")
            if not np.isnan(price):
                st.write(f"**Cena:** {price:.2f}")
            if not np.isnan(ind["rsi"]):
                st.write(f"**RSI (14):** {ind['rsi']:.1f}")
            if not np.isnan(ind["ma_fast"]) and not np.isnan(ind["ma_slow"]):
                st.write(f"**MA10:** {ind['ma_fast']:.2f} | **MA30:** {ind['ma_slow']:.2f}")
            st.write(f"**Trend:** {ind['trend']}")
            if not np.isnan(ind["adx"]):
                st.write(f"**ADX (14):** {ind['adx']:.1f}")
            if not np.isnan(ind["atr"]):
                st.write(f"**ATR (14):** {ind['atr']:.2f}")
            if not np.isnan(ind["vol"]):
                st.write(f"**Volatility (20):** {ind['vol']:.4f}")
            if not np.isnan(ind["volume"]):
                st.write(f"**Wolumen (ostatnia świeca):** {ind['volume']:.0f}")
            if not np.isnan(ind["rvol"]):
                st.write(f"**RVOL (20):** {ind['rvol']:.2f}")
            if not np.isnan(ind["vwap"]):
                st.write(f"**VWAP (20):** {ind['vwap']:.2f}")
            if not np.isnan(ind["roc"]):
                st.write(f"**ROC (10):** {ind['roc']:.2f}%")
            if not np.isnan(ind["stoch_k"]) and not np.isnan(ind["stoch_d"]):
                st.write(f"**Stochastic %K/%D:** {ind['stoch_k']:.1f} / {ind['stoch_d']:.1f}")
            if not np.isnan(ind["last_lower_bb"]):
                st.write(f"**SL (Bollinger dolna):** {ind['last_lower_bb']:.2f}")
            if not np.isnan(ind["last_upper_bb"]):
                st.write(f"**TP (Bollinger górna):** {ind['last_upper_bb"]:.2f}")
            st.write(f"**Sygnał (z newsami): {signal}**")
            st.write(f"**Scoring PRO (0–100): {scoring}**")
            st.markdown("**Uzasadnienie:**")
            st.markdown(explanation)

            st.markdown("---")
            st.subheader("📰 NEWS RADAR – sentyment i nagłówki")
            st.write(f"**Sentyment newsów:** {sentiment}")
            if comment:
                st.write(comment)
            if titles:
                for t in titles:
                    st.markdown(f"- {t}")

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

            st.success("Analiza zapisana – czat AI i skaner będą korzystać z tych danych.")

        except Exception as e:
            st.error(f"Błąd: {e}")


def render_scanner():
    st.title("🧪 Skaner spółek – 50 tickerów → TOP 10 — Scoring PRO + NEWS")

    st.caption("Wklej listę tickerów (np. 50), skrypt policzy scoring PRO (z newsami) i wybierze TOP 10.")

    tickers_text = st.text_area(
        "Tickery (oddzielone spacją, przecinkiem lub nową linią):",
        "AAPL MSFT NVDA TSLA AMZN META GOOGL NFLX AMD INTC",
        height=120,
    )

    max_to_show = st.slider("Ile spółek pokazać (TOP N):", 5, 20, 10)

    if st.button("Skanuj spółki", use_container_width=True):
        raw = tickers_text.replace(",", " ").split()
        tickers = [t.strip().upper() for t in raw if t.strip()]
        tickers = list(dict.fromkeys(tickers))

        if not tickers:
            st.error("Brak poprawnych tickerów.")
            return

        results = []
        progress = st.progress(0.0)
        status = st.empty()

        for i, ticker in enumerate(tickers):
            progress.progress((i + 1) / len(tickers))
            status.write(f"Skanuję: {ticker} ({i+1}/{len(tickers)})")

            try:
                data = yf.download(
                    tickers=ticker,
                    period="6mo",
                    interval="1d",
                    auto_adjust=True,
                    group_by="ticker",
                )
                if data.empty or len(data) < 60:
                    continue

                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"].iloc[:, 0]
                    volume = data["Volume"].iloc[:, 0]
                else:
                    close = data["Close"]
                    volume = data["Volume"]

                ind = compute_indicators(close, volume)
                price = to_scalar(close.iloc[-1])

                sentiment, titles, _ = fetch_news_sentiment(ticker)
                scoring = compute_scoring_pro(ind, sentiment)

                results.append(
                    {
                        "Ticker": ticker,
                        "Cena": price,
                        "Trend": ind["trend"],
                        "RSI": ind["rsi"],
                        "ADX": ind["adx"],
                        "RVOL": ind["rvol"],
                        "Sentyment": sentiment,
                        "Scoring": scoring,
                    }
                )
            except Exception:
                continue

        progress.empty()
        status.empty()

        if not results:
            st.error("Nie udało się policzyć scoringu dla żadnego tickera.")
            return

        df = pd.DataFrame(results)
        df_sorted = df.sort_values("Scoring", ascending=False).head(max_to_show)

        st.subheader(f"TOP {min(max_to_show, len(df_sorted))} spółek wg Scoring PRO + NEWS")

        for _, row in df_sorted.iterrows():
            score = row["Scoring"]
            ticker = row["Ticker"]
            price = row["Cena"]
            trend = row["Trend"]
            sentiment = row["Sentyment"]

            if score >= 70:
                color = "rgba(34,197,94,0.35)"
                text_color = "#eaffea"
                label = "Mocny sygnał"
            elif score >= 40:
                color = "rgba(251,146,60,0.35)"
                text_color = "#fff4e5"
                label = "Neutralny / obserwacja"
            else:
                color = "rgba(239,68,68,0.35)"
                text_color = "#ffe5e5"
                label = "Słaby sygnał"

            st.markdown(
                f"""
                <div style="
                    background-color:{color};
                    padding:12px;
                    border-radius:8px;
                    margin-bottom:8px;
                    color:{text_color};
                    font-size:16px;
                ">
                    <b>{ticker}</b> — cena: {price:.2f}  
                    <br>Trend: {trend}  
                    <br>Sentyment newsów: {sentiment}  
                    <br><b>Scoring PRO: {score} / 100</b> — {label}
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            "_Scoring PRO łączy trend, ADX, RSI, Stochastic, RVOL, MACD, Bollinger, ATR oraz sentyment newsów._"
        )
def tavily_research(tavily_key, ticker, question):
    base_queries = [question]
    if ticker:
        base_queries.extend(
            [
                f"{ticker} company profile",
                f"{ticker} financial statements",
                f"{ticker} dividend policy",
                f"{ticker} sector and industry",
                f"{ticker} market cap and valuation",
                f"{ticker} outlook 2026",
            ]
        )

    all_answers = []
    all_results = []

    for q in base_queries:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {tavily_key}"},
                json={
                    "query": q,
                    "topic": "finance",
                    "max_results": 4,
                    "include_answer": True,
                    "include_raw_content": False,
                },
                timeout=20,
            )
            resp.raise_for_status()
            j = resp.json()
            ans = j.get("answer", "")
            res = j.get("results", [])
            if ans:
                all_answers.append(ans)
            all_results.extend(res)
        except Exception:
            continue

    filtered_results = []
    ticker_upper = (ticker or "").upper()
    is_gpw = ticker_upper.endswith(".WA")

    for item in all_results:
        title = item.get("title", "") or ""
        url = item.get("url", "") or ""
        content = item.get("content", "") or ""
        blob = f"{title} {content} {url}"

        if ticker_upper and ticker_upper not in blob.upper():
            if not (is_gpw and any(k in blob for k in ["GPW", "Warsaw", "Poland", ".WA"])):
                continue

        if is_gpw:
            if not any(k in blob for k in ["GPW", "Warsaw", "Poland", ".WA"]):
                continue

        filtered_results.append(item)

    bullets = []
    for item in filtered_results:
        title = item.get("title", "")
        url = item.get("url", "")
        if title or url:
            bullets.append(f"- {title} ({url})")

    merged_answer = ""
    if all_answers:
        merged_answer = "\n\n".join(all_answers)

    has_fundamentals = bool(merged_answer or bullets)
    if not filtered_results and not merged_answer:
        has_fundamentals = False

    if not has_fundamentals:
        return "Brak wiarygodnych danych fundamentalnych z Tavily dla tego tickera. Analiza fundamentalna ograniczona lub niemożliwa.", False

    research_text = ""
    if merged_answer:
        research_text += f"Podsumowanie Tavily (fundamenty, profil, dywidendy, sektor):\n{merged_answer}\n\n"
    if bullets:
        research_text += "Źródła Tavily:\n" + "\n".join(bullets)

    return research_text, True


def render_ai_chat():
    st.title("🤖 Czat AI – Analityk finansowy (GPT-4.1 + Tavily + Trading Engine PRO)")
    st.caption("Zero zgadywania: tylko dane z trading engine + Tavily (finance/news).")

    if "OPENAI_API_KEY" not in st.secrets:
        st.error("Brak OPENAI_API_KEY w .streamlit/secrets.toml")
        return
    if "TAVILY_API_KEY" not in st.secrets:
        st.error("Brak TAVILY_API_KEY w .streamlit/secrets.toml")
        return

    openai_key = st.secrets["OPENAI_API_KEY"]
    tavily_key = st.secrets["TAVILY_API_KEY"]

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.markdown("### Historia rozmowy")
    for sender, msg in st.session_state.chat_history:
        st.markdown(f"**{sender}:** {msg}")

    user_input = st.text_input("Twoja wiadomość:")

    col_send, col_clear = st.columns([3, 1])
    send = col_send.button("Wyślij")
    clear = col_clear.button("Wyczyść czat")

    if clear:
        st.session_state.chat_history = []
        st.rerun()

    if not send or not user_input.strip():
        return

    question = user_input.strip()
    st.session_state.chat_history.append(("Ty", question))

    ticker = detect_ticker_from_text(question)
    if not ticker and "last_analysis" in st.session_state:
        ticker = st.session_state["last_analysis"].get("ticker")

    trading_data = st.session_state.get("last_analysis", None)

    trading_summary = "Brak danych z Trading Engine."
    if trading_data:
        ind = trading_data["indicators"]
        scoring = trading_data.get("scoring", compute_scoring_pro(ind, trading_data.get("sentiment")))
        lines = [f"Ticker: {trading_data['ticker']}"]
        if not np.isnan(trading_data["price"]):
            lines.append(f"Cena: {trading_data['price']:.2f}")
        lines.append(f"Sygnał engine (z newsami): {trading_data['signal']}")
        lines.append(f"Scoring PRO (0–100): {scoring}")
        if not np.isnan(ind["rsi"]):
            lines.append(f"RSI(14): {ind['rsi']:.1f}")
        if not np.isnan(ind["ma_fast"]) and not np.isnan(ind["ma_slow"]):
            lines.append(f"MA10: {ind['ma_fast']:.2f}, MA30: {ind['ma_slow']:.2f}")
        lines.append(f"Trend: {ind['trend']}")
        if not np.isnan(ind["adx"]):
            lines.append(f"ADX(14): {ind['adx']:.1f}")
        if not np.isnan(ind["atr"]):
            lines.append(f"ATR(14): {ind['atr']:.2f}")
        if not np.isnan(ind["vol"]):
            lines.append(f"Volatility(20): {ind['vol']:.4f}")
        if not np.isnan(ind["volume"]):
            lines.append(f"Wolumen (ostatnia świeca): {ind['volume']:.0f}")
        if not np.isnan(ind["rvol"]):
            lines.append(f"RVOL(20): {ind['rvol']:.2f}")
        if not np.isnan(ind["vwap"]):
            lines.append(f"VWAP(20): {ind['vwap']:.2f}")
        if not np.isnan(ind["roc"]):
            lines.append(f"ROC(10): {ind['roc']:.2f}%")
        if not np.isnan(ind["stoch_k"]) and not np.isnan(ind["stoch_d"]):
            lines.append(f"Stochastic %K/%D: {ind['stoch_k']:.1f} / {ind['stoch_d']:.1f}")
        if not np.isnan(ind["last_lower_bb"]):
            lines.append(f"SL (Bollinger dolna): {ind['last_lower_bb']:.2f}")
        if not np.isnan(ind["last_upper_bb"]):
            lines.append(f"TP (Bollinger górna): {ind['last_upper_bb']:.2f}")
        lines.append(f"Sentyment newsów (NEWS RADAR): {trading_data['sentiment']}")
        trading_summary = "\n".join(lines)

    research_text, has_fundamentals = tavily_research(tavily_key, ticker, question)

    try:
        system_prompt = (
            "Jesteś profesjonalnym analitykiem finansowym w terminalu tradingowym.\n"
            "Masz dwa źródła danych:\n"
            "1) Trading Engine (yfinance) – twarde dane: cena, RSI, MA, Bollinger, MACD, wolumen, SL/TP, trend, ADX, ATR, RVOL, VWAP, ROC, Stochastic, sentyment newsów, scoring PRO.\n"
            "2) Tavily (topic=finance/news) – kontekst rynkowy, newsy, raporty, fundamenty, informacje o dywidendach i sektorze.\n\n"
            "Zasady ZERO HALUCYNACJI:\n"
            "- Jeśli nie masz danych → NIE ZGADUJ.\n"
            "- Jeśli ticker nieznany → NIE ZGADUJ.\n"
            "- Jeśli branża nieznana → NIE ZGADUJ.\n"
            "- Jeśli Tavily nie zwróciło wiarygodnych wyników → powiedz to wprost i oprzyj się tylko na analizie technicznej.\n"
            "- Jeśli Trading Engine nie zwrócił danych → powiedz to wprost.\n"
            "- Odpowiadasz TYLKO na podstawie danych z trading engine i Tavily.\n"
            "- NIE wolno Ci wymyślać wyników finansowych, branży, danych historycznych ani prognoz.\n"
            "- Jeśli dane są niepełne → podaj scenariusze warunkowe.\n"
            "- Jeśli Tavily zwróciło newsy/fundamenty → uwzględnij je w analizie.\n"
            "- Jeśli Trading Engine zwrócił wskaźniki i scoring PRO → wykorzystaj je w analizie technicznej i scenariuszach.\n"
            "Odpowiadasz po polsku, konkretnie, jak analityk biura maklerskiego."
        )

        def ask_gpt():
            return requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}"},
                json={
                    "model": "gpt-4.1",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "system", "content": f"Dane z Trading Engine:\n{trading_summary}"},
                        {"role": "system", "content": f"Research z Tavily (topic=finance/news):\n{research_text}"},
                        *[
                            {"role": "user" if s == "Ty" else "assistant", "content": c}
                            for s, c in st.session_state.chat_history
                        ],
                    ],
                    "temperature": 0.1,
                },
                timeout=60,
            )

        gpt_resp = ask_gpt()
        if gpt_resp.status_code != 200:
            gpt_resp = ask_gpt()

        gpt_resp.raise_for_status()
        gpt_json = gpt_resp.json()
        ai_msg = gpt_json["choices"][0]["message"]["content"]
    except Exception as e:
        ai_msg = f"[Błąd GPT] {e}"

    st.session_state.chat_history.append(("AI", ai_msg))
    st.rerun()


# ---------------- ROUTING ----------------

if mode == "🤖 Czat AI (internet + trading)":
    render_ai_chat()
elif mode == "📈 Kombajn tradingowy":
    render_trading()
else:
    render_scanner()
