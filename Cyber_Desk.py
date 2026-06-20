import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
from openbb import obb  # OPENBB INTEGRACJA

# ================== CONFIG & NEON UI ==================

st.set_page_config(
    page_title="CYBER DESK PRO - KI_ULTRA v5.4 OPENBB",
    page_icon="⚡",
    layout="wide"
)

st.markdown(
    """
    <style>
    body, .stApp { background-color: #050816; color: #E0E0FF; }
    .stSidebar { background: #0a0f24; }
    .stButton>button { background: #0ea5e9; color: white; border-radius: 6px; }
    .stButton>button:hover { background: #22c55e; }
    .stTextInput>div>div>input { background-color: #020617; color: #e5e7eb; }
    .stTextArea textarea { background-color: #020617; color: #e5e7eb; }
    .stSelectbox div[data-baseweb="select"] { background-color: #020617; color: #e5e7eb; }
    </style>
    """,
    unsafe_allow_html=True
)

with st.sidebar:
    st.markdown("### ⚡ CYBER DESK PRO - KI_ULTRA v5.4")
    st.caption("Trading + GPT‑4.1 + Tavily + OpenBB (price/fund/macro/charts)")
    app_mode = st.selectbox(
        "Tryb pracy:",
        ["📈 Trading", "📰 Skaner wiadomości", "📊 OpenBB Fundamentals", "🌍 OpenBB Macro"]
    )

# ================== HELPERS ==================

def to_scalar(x):
    try:
        if isinstance(x, (pd.Series, np.ndarray, list)):
            return float(np.asarray(x).ravel()[-1])
        return float(x)
    except Exception:
        return np.nan

# ================== INDICATORS ENGINE ==================

def compute_indicators(close, volume, high=None, low=None):
    close = close.copy()
    volume = volume.copy()

    if high is None:
        high = close
    if low is None:
        low = close

    # RSI 14
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = to_scalar(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else np.nan

    # MA 10/30
    ma_fast = to_scalar(close.rolling(10).mean().dropna().iloc[-1]) if len(close) >= 10 else np.nan
    ma_slow = to_scalar(close.rolling(30).mean().dropna().iloc[-1]) if len(close) >= 30 else np.nan

    # Bollinger Bands 20
    ma_bb = close.rolling(20).mean()
    std_bb = close.rolling(20).std()
    upper_bb = ma_bb + 2 * std_bb
    lower_bb = ma_bb - 2 * std_bb
    last_upper_bb = to_scalar(upper_bb.dropna().iloc[-1]) if not upper_bb.dropna().empty else np.nan
    last_lower_bb = to_scalar(lower_bb.dropna().iloc[-1]) if not lower_bb.dropna().empty else np.nan

    # MACD 12/26/9
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

    # ATR 14
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = to_scalar(tr.rolling(14).mean().dropna().iloc[-1]) if len(tr) >= 14 else np.nan

    # ADX 14
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    atr_adx = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_adx + 1e-9))
    minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_adx + 1e-9))
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx = to_scalar(dx.rolling(14).mean().dropna().iloc[-1]) if len(dx.dropna()) else np.nan

    # RVOL
    avg_vol_20 = volume.rolling(20).mean()
    rvol = to_scalar((volume / (avg_vol_20 + 1e-9)).dropna().iloc[-1]) if len(volume) >= 20 else np.nan

    # Trend
    if not np.isnan(ma_fast) and not np.isnan(ma_slow):
        if ma_fast > ma_slow:
            trend = "Uptrend"
        elif ma_fast < ma_slow:
            trend = "Downtrend"
        else:
            trend = "Sideways"
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

# ================== SCORING PRO ==================

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
        elif ind["rsi"] > 70:
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

# ================== TAVILY NEWS (ZOSTAJE) ==================

def tavily_news(query: str, max_results: int = 10):
    key = st.secrets.get("TAVILY_API_KEY", None)
    if not key:
        return []

    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "query": query,
                "max_results": max_results
            },
            timeout=10
        )
        j = r.json()
        return j.get("results", [])
    except Exception:
        return []

def fetch_news_sentiment(ticker: str):
    headlines = []

    tavily_results = tavily_news(ticker, max_results=15)
    for item in tavily_results:
        title = item.get("title", "")
        if title:
            headlines.append(title)

    try:
        news = yf.Ticker(ticker).news
        for n in news:
            title = n.get("title", "")
            if title:
                headlines.append(title)
    except Exception:
        pass

    seen = set()
    uniq = []
    for h in headlines:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    headlines = uniq

    if not headlines:
        return "Mixed", [], "Brak newsów."

    score = 0
    for t in headlines:
        tl = t.lower()
        if any(w in tl for w in ["beat", "strong", "growth", "upgrade", "record", "surge", "profit", "increase"]):
            score += 1
        if any(w in tl for w in ["miss", "weak", "downgrade", "fall", "plunge", "cut", "loss", "spadek"]):
            score -= 1

    sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"
    return sentiment, headlines[:15], ""

# ================== GPT‑4.1 NEWS SUMMARY ==================

def summarize_news_with_gpt(titles, ticker):
    if not titles:
        return "Brak newsów do podsumowania."

    key = st.secrets["OPENAI_API_KEY"]
    joined = "\n".join(titles)

    prompt = f"""
Masz listę nagłówków newsów dotyczących {ticker}:

{joined}

Zrób:
- krótkie podsumowanie (3-4 zdania) po polsku,
- oceń ogólny wydźwięk: pozytywny / neutralny / negatywny.

Zwróć czysty tekst, bez JSON.
"""

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        },
        timeout=20
    )

    try:
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return "Błąd przy podsumowaniu newsów."

# ================== GPT‑4.1 AI SIGNAL (ZAOSTRZONE ZASADY) ==================

def gpt41_signal(price, ind, sentiment, ticker, scoring):
    key = st.secrets["OPENAI_API_KEY"]

    prompt = f"""
Jesteś profesjonalnym analitykiem tradingowym. Masz twarde zasady:

- RSI < 30 = wyprzedanie (możliwy BUY, ale tylko przy sensownym trendzie).
- 30 <= RSI <= 50 = strefa neutralna (brak mocnego sygnału).
- RSI > 70 = wykupienie (możliwy SELL, ale tylko przy sensownym trendzie).
- Jeśli trend = 'Unknown' lub ADX jest pusty/nan → NIE WOLNO dawać mocnego sygnału BUY/SELL, tylko HOLD lub bardzo ostrożny komentarz.
- Jeśli Scoring PRO < 60 → sygnał ma być ostrożny, preferuj HOLD lub słaby sygnał z komentarzem o ryzyku.

Na podstawie danych wygeneruj sygnał BUY/SELL/HOLD, ale respektuj powyższe zasady.

Dane:
Ticker: {ticker}
Cena: {price}
RSI: {ind['rsi']}
Trend: {ind['trend']}
MACD: {ind['last_macd']}
MACD Signal: {ind['last_macd_signal']}
ADX: {ind['adx']}
ATR: {ind['atr']}
RVOL: {ind['rvol']}
SL (BB Low): {ind['last_lower_bb']}
TP (BB High): {ind['last_upper_bb']}
Sentiment news: {sentiment}
Scoring PRO: {scoring}

Zwróć JSON:
{{
"signal": "BUY/SELL/HOLD",
"reason": "krótkie, konkretne uzasadnienie po polsku, bez ogólników",
"quality": "low/medium/high"
}}
"""

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        },
        timeout=20
    )

    try:
        txt = r.json()["choices"][0]["message"]["content"]
        import json
        j = json.loads(txt)
        return j.get("signal", "HOLD"), j.get("reason", "Brak uzasadnienia."), j.get("quality", "low")
    except Exception:
        return "HOLD", "Błąd GPT‑4.1 lub niepoprawny JSON.", "low"

# ================== OPENBB PRICE ENGINE ==================

def openbb_load_price(ticker: str, interval: str = "1d", period: str = "1mo") -> pd.DataFrame:
    """
    Używa OpenBB do pobrania danych cenowych zamiast yfinance.
    """
    try:
        # mapowanie period na start_date (prosto, bez filozofii)
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        if period == "5d":
            start = now - timedelta(days=5)
        elif period == "1mo":
            start = now - timedelta(days=30)
        elif period == "3mo":
            start = now - timedelta(days=90)
        elif period == "6mo":
            start = now - timedelta(days=180)
        elif period == "1y":
            start = now - timedelta(days=365)
        else:
            start = now - timedelta(days=60)

        start_str = start.strftime("%Y-%m-%d")
        end_str = now.strftime("%Y-%m-%d")

        data = obb.equity.price.historical(
            ticker,
            start_date=start_str,
            end_date=end_str,
            provider="yfinance"  # dalej yfinance, ale przez OpenBB
        )
        df = data.to_dataframe()

        # Upewniamy się, że mamy kolumny jak w starym kodzie
        # OpenBB zwykle zwraca: open, high, low, close, volume, dividend, ...
        rename_map = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        }
        for k, v in rename_map.items():
            if k in df.columns and v not in df.columns:
                df[v] = df[k]

        # sortowanie po dacie
        df = df.sort_index()

        return df
    except Exception as e:
        st.error(f"Błąd OpenBB price: {e}")
        return pd.DataFrame()

# ================== OPENBB FUNDAMENTALS ==================

def openbb_load_fundamentals(ticker: str) -> pd.DataFrame:
    try:
        data = obb.equity.fundamentals.overview(
            ticker,
            provider="yfinance"
        )
        df = data.to_dataframe()
        return df.T if df.index.name == "metric" else df
    except Exception as e:
        st.error(f"Błąd OpenBB fundamentals: {e}")
        return pd.DataFrame()

# ================== OPENBB MACRO ==================

def openbb_load_macro(series: str = "CPI") -> pd.DataFrame:
    """
    Przykład: CPI, GDP, UNRATE, FEDFUNDS itd. (FRED / inne providery).
    """
    try:
        data = obb.economy.macro(series)
        df = data.to_dataframe()
        return df
    except Exception as e:
        st.error(f"Błąd OpenBB macro: {e}")
        return pd.DataFrame()

# ================== OPENBB CHARTS (CANDLE) ==================

def openbb_candlestick_figure(df: pd.DataFrame, ticker: str):
    if df.empty:
        return go.Figure()

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    open_ = df["Open"]

    ind = compute_indicators(close, df["Volume"], high, low)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=open_,
        high=high,
        low=low,
        close=close,
        name="Cena"
    ))
    fig.add_trace(go.Scatter(x=df.index, y=ind["upper_bb"], line=dict(color="green"), name="BB Upper"))
    fig.add_trace(go.Scatter(x=df.index, y=ind["lower_bb"], line=dict(color="red"), name="BB Lower"))
    fig.update_layout(
        title=f"{ticker} — OpenBB Candlestick",
        height=500,
        paper_bgcolor="#020617",
        plot_bgcolor="#020617"
    )
    return fig, ind, to_scalar(close.iloc[-1])

# ================== TRADING PANEL (OPENBB PRICE + NEWS + AI) ==================

def render_trading():
    st.title("📈 Trading + AI + News (OpenBB price)")

    ticker = st.text_input("Ticker (np. NVG.WA, STX.WA, AAPL):", "")
    interval = st.selectbox("Interwał (wizualny):", ["15m", "30m", "1h", "1d"], index=3)
    period = st.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)

    if st.button("Analizuj", use_container_width=True):
        if not ticker.strip():
            st.error("Podaj ticker.")
            return

        # TERAZ: dane z OpenBB
        data = openbb_load_price(ticker, interval=interval, period=period)

        if data.empty:
            st.error("Brak danych dla tego tickera / interwału (OpenBB).")
            return

        close = data["Close"]
        volume = data["Volume"]
        high = data["High"]
        low = data["Low"]
        open_ = data["Open"]

        ind = compute_indicators(close, volume, high, low)
        price = to_scalar(close.iloc[-1])

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=data.index, open=open_, high=high, low=low, close=close, name="Cena"
        ))
        fig.add_trace(go.Scatter(x=data.index, y=ind["upper_bb"], line=dict(color="green"), name="BB Upper"))
        fig.add_trace(go.Scatter(x=data.index, y=ind["lower_bb"], line=dict(color="red"), name="BB Lower"))
        fig.update_layout(height=500, paper_bgcolor="#020617", plot_bgcolor="#020617")
        st.plotly_chart(fig, use_container_width=True)

        sentiment, titles, _ = fetch_news_sentiment(ticker)
        scoring = compute_scoring_pro(ind, sentiment)
        ai_signal, ai_reason, ai_quality = gpt41_signal(price, ind, sentiment, ticker, scoring)

        st.subheader("🤖 Sygnał AI (GPT‑4.1)")
        st.write("**Sygnał:**", ai_signal)
        st.write("**Jakość sygnału:**", ai_quality)
        st.write("**Scoring PRO:**", f"{scoring}/100")
        st.write("**SL (BB Low):**", ind["last_lower_bb"])
        st.write("**TP (BB High):**", ind["last_upper_bb"])
        st.write("**Uzasadnienie:**")
        st.code(ai_reason)

        st.subheader("📊 Wskaźniki")
        st.write("Cena:", price)
        st.write("RSI:", ind["rsi"])
        st.write("Trend:", ind["trend"])
        st.write("MACD:", ind["last_macd"])
        st.write("MACD Signal:", ind["last_macd_signal"])
        st.write("ADX:", ind["adx"])
        st.write("ATR:", ind["atr"])
        st.write("RVOL:", ind["rvol"])

        st.subheader("📰 NEWS RADAR (Tavily + Yahoo)")
        if titles:
            for t in titles[:5]:
                st.write("- ", t)
            st.write("**Podsumowanie newsów (GPT‑4.1):**")
            summary = summarize_news_with_gpt(titles[:10], ticker)
            st.code(summary)
        else:
            st.write("Brak newsów.")

# ================== SKANER WIADOMOŚCI (TAVILY) ==================

def render_news_scanner():
    st.title("📰 Skaner wiadomości (Tavily)")

    query = st.text_input("Fraza / ticker / temat (np. NVG.WA, Orlen, 'spółki skarbu państwa'):", "")
    max_results = st.slider("Liczba wyników:", 5, 30, 15)

    if st.button("Skanuj wiadomości", use_container_width=True):
        if not query.strip():
            st.error("Podaj frazę lub ticker.")
            return

        results = tavily_news(query, max_results=max_results)

        if not results:
            st.warning("Brak wyników z Tavily.")
            return

        titles = []
        for item in results:
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("content", "") or item.get("snippet", "")
            if title:
                titles.append(title)
            st.markdown(f"**{title}**")
            if snippet:
                st.write(snippet[:400] + ("..." if len(snippet) > 400 else ""))
            if url:
                st.write(url)
            st.markdown("---")

        if titles:
            st.subheader("Podsumowanie newsów (GPT‑4.1)")
            summary = summarize_news_with_gpt(titles[:10], query)
            st.code(summary)

# ================== OPENBB FUNDAMENTALS PANEL ==================

def render_openbb_fundamentals():
    st.title("📊 OpenBB Fundamentals")

    ticker = st.text_input("Ticker (np. AAPL, MSFT, NVDA):", "")
    if st.button("Pobierz fundamenty", use_container_width=True):
        if not ticker.strip():
            st.error("Podaj ticker.")
            return

        df = openbb_load_fundamentals(ticker)
        if df.empty:
            st.warning("Brak danych fundamentalnych (OpenBB).")
            return

        st.subheader(f"Fundamenty: {ticker}")
        st.dataframe(df)

# ================== OPENBB MACRO PANEL ==================

def render_openbb_macro():
    st.title("🌍 OpenBB Macro")

    series = st.text_input("Seria makro (np. CPI, GDP, UNRATE, FEDFUNDS):", "CPI")
    if st.button("Pobierz dane makro", use_container_width=True):
        df = openbb_load_macro(series)
        if df.empty:
            st.warning("Brak danych makro (OpenBB).")
            return

        st.subheader(f"Seria makro: {series}")
        st.dataframe(df)

        if "value" in df.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df["value"], mode="lines+markers", name=series))
            fig.update_layout(
                title=f"{series} (OpenBB Macro)",
                height=400,
                paper_bgcolor="#020617",
                plot_bgcolor="#020617"
            )
            st.plotly_chart(fig, use_container_width=True)

# ================== MAIN ==================

def main():
    if app_mode == "📈 Trading":
        render_trading()
    elif app_mode == "📰 Skaner wiadomości":
        render_news_scanner()
    elif app_mode == "📊 OpenBB Fundamentals":
        render_openbb_fundamentals()
    elif app_mode == "🌍 OpenBB Macro":
        render_openbb_macro()

if __name__ == "__main__":
    main()
