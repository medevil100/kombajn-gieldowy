import os
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from openai import OpenAI

# ====================== KONFIGURACJA AI ======================

MODEL_TURBO = "gpt-4o"          # AI Turbo 3.0
MODEL_NEWS = "gpt-4o-mini"      # AI News
MODEL_RISK = "gpt-4.1"          # AI Risk Check
MODEL_PATTERN = "gpt-4o-mini"   # AI Pattern Insight

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====================== DANE RYNKOWE ======================

def get_price_data(symbol: str, period: str = "5d", interval: str = "1h") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

def get_bid_ask(symbol: str):
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        bid = info.get("bid", None)
        ask = info.get("ask", None)
        if not bid or not ask:
            return None, None, None
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid * 100 if mid else None
        return float(bid), float(ask), float(spread_pct)
    except:
        return None, None, None

def compute_entry_risk(volume, spread_pct):
    if volume >= 2_000_000:
        liquidity = "WYSOKA"
    elif volume >= 500_000:
        liquidity = "ŚREDNIA"
    else:
        liquidity = "NISKA"

    if spread_pct is None:
        spread_rating = "NIEZNANY"
    elif spread_pct < 0.5:
        spread_rating = "DOBRY"
    elif spread_pct < 2:
        spread_rating = "OK"
    else:
        spread_rating = "SŁABY"

    if liquidity == "WYSOKA" and spread_pct and spread_pct < 1:
        slippage = "NISKIE"
    elif liquidity == "ŚREDNIA" or (spread_pct and 1 <= spread_pct <= 3):
        slippage = "ŚREDNIE"
    else:
        slippage = "WYSOKIE"

    return liquidity, spread_rating, slippage

# ====================== SL / TP ======================

def compute_sl_tp(last, atr, trend):
    if not last or not atr:
        return None, None
    sl = (last - atr * 1.5, last - atr * 1.0)
    tp = (last + atr * 2.0, last + atr * 3.0)
    return sl, tp

# ====================== METRYKI ======================

def compute_metrics(symbol):
    df = get_price_data(symbol)
    if df.empty or len(df) < 3:
        return {"Symbol": symbol, "LastPrice": 0, "Change": 0, "Volume": 0,
                "ATR": 0, "Trend": "BRAK", "Signal": "NEUTRAL",
                "MomentumScore": 0, "VolatilityScore": 0,
                "TrendStrength": 0, "RiskScore": 50, "SetupScore": 0,
                "TrendScore": 0, "TrendHealth": "NIEZNANY",
                "TrendConfidence": "NIEZNANE", "TrendReversalRisk": "NIEZNANE",
                "SL_Low": None, "SL_High": None, "TP_Low": None, "TP_High": None,
                "Bid": None, "Ask": None, "SpreadPct": None,
                "Liquidity": "NIEZNANA", "SpreadRating": "NIEZNANY",
                "Slippage": "NIEZNANE"}

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = (last - prev) / prev * 100 if prev else 0

    tr = pd.concat([(high - low),
                    (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]

    if last > ema20 > ema50:
        trend = "UP"
    elif last < ema20 < ema50:
        trend = "DOWN"
    else:
        trend = "SIDE"

    signal = "BUY" if trend == "UP" and change > 0 else \
             "SELL" if trend == "DOWN" and change < 0 else "NEUTRAL"

    vol_last = float(volume.iloc[-1])
    vol_prev = float(volume.iloc[-2])
    vol_change = (vol_last - vol_prev) / vol_prev * 100 if vol_prev else 0

    momentum = max(0, min(100, 50 + change * 0.7 + vol_change * 0.3))
    vol_score = max(0, min(100, (atr / last * 100) * 2))
    trend_strength = max(0, min(100, abs(ema20 - ema50) / last * 500))

    risk = vol_score
    setup = max(0, min(100, (momentum * 0.3 + trend_strength * 0.3 - risk * 0.2 +
                             (30 if signal == "BUY" else 20 if signal == "SELL" else 0))))

    sl, tp = compute_sl_tp(last, atr, trend)

    bid, ask, spread = get_bid_ask(symbol)
    liquidity, spread_rating, slippage = compute_entry_risk(vol_last, spread)

    return {
        "Symbol": symbol,
        "LastPrice": last,
        "Change": change,
        "Volume": vol_last,
        "ATR": atr,
        "Trend": trend,
        "Signal": signal,
        "MomentumScore": momentum,
        "VolatilityScore": vol_score,
        "TrendStrength": trend_strength,
        "RiskScore": risk,
        "SetupScore": setup,
        "TrendScore": trend_strength,
        "TrendHealth": "OK",
        "TrendConfidence": "ŚREDNIE",
        "TrendReversalRisk": "NISKIE",
        "SL_Low": sl[0] if sl else None,
        "SL_High": sl[1] if sl else None,
        "TP_Low": tp[0] if tp else None,
        "TP_High": tp[1] if tp else None,
        "Bid": bid,
        "Ask": ask,
        "SpreadPct": spread,
        "Liquidity": liquidity,
        "SpreadRating": spread_rating,
        "Slippage": slippage,
    }

# ====================== WYKRES ======================

def plot_pro_chart(symbol):
    df = get_price_data(symbol)
    if df.empty:
        st.warning(f"Brak danych dla {symbol}")
        return

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name="Świece"
    ))

    ema20 = df["Close"].ewm(span=20).mean()
    ema50 = df["Close"].ewm(span=50).mean()

    fig.add_trace(go.Scatter(x=df.index, y=ema20, mode="lines", name="EMA20"))
    fig.add_trace(go.Scatter(x=df.index, y=ema50, mode="lines", name="EMA50"))

    fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

# ====================== AI ======================

def ai_turbo_v3(df):
    prompt = f"Analiza prop-desk na podstawie danych: {df.to_dict(orient='records')}"
    resp = client.chat.completions.create(
        model=MODEL_TURBO,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

def ai_news_summary(symbol, raw_news):
    prompt = f"News sentiment dla {symbol}: {raw_news}"
    resp = client.chat.completions.create(
        model=MODEL_NEWS,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

def ai_risk_check(df):
    prompt = f"Risk check: {df.to_dict(orient='records')}"
    resp = client.chat.completions.create(
        model=MODEL_RISK,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

def ai_pattern_insight(symbols):
    prompt = f"Pattern insight dla: {symbols}"
    resp = client.chat.completions.create(
        model=MODEL_PATTERN,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

# ====================== MAIN ======================

def main():
    st.set_page_config(page_title="KOMBAJN v5.4", layout="wide")
    st.title("🔥 KOMBAJN v5.4 — BEZ SEKTORÓW + AI Turbo 3.0")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []

    st.sidebar.header("⚙️ Ustawienia")

    symbols_input = st.sidebar.text_input("Dodaj tickery (oddzielone przecinkami):")

    if st.sidebar.button("Dodaj"):
        for raw in symbols_input.split(","):
            sym = raw.strip().upper()
            if sym and sym not in st.session_state.symbols:
                st.session_state.symbols.append(sym)

    if st.sidebar.button("Wyczyść"):
        st.session_state.symbols = []

    if not st.session_state.symbols:
        st.warning("Dodaj spółki w sidebarze, aby rozpocząć.")
        return

    tabs = st.tabs([
        "📊 Heatmapa",
        "📈 Wykres",
        "📡 Skaner",
        "⚡ AI Turbo",
        "📰 AI News",
        "🛡️ AI Risk",
        "📐 AI Pattern",
    ])

    # --- HEATMAPA ---
    with tabs[0]:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False)
        st.dataframe(df, use_container_width=True)

    # --- WYKRES ---
    with tabs[1]:
        symbol = st.selectbox("Wybierz spółkę:", st.session_state.symbols)
        plot_pro_chart(symbol)

    # --- SKANER ---
    with tabs[2]:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False)
        st.dataframe(df, use_container_width=True)

    # --- AI TURBO ---
    with tabs[3]:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False)
        st.dataframe(df, use_container_width=True)
        if st.button("AI Turbo 3.0"):
            st.write(ai_turbo_v3(df))

    # --- AI NEWS ---
    with tabs[4]:
        symbol = st.selectbox("Spółka:", st.session_state.symbols)
        news = yf.Ticker(symbol).news
        raw = "\n".join([n["title"] for n in news]) if news else "Brak newsów"
        st.write(raw)
        if st.button("Analiza newsów"):
            st.write(ai_news_summary(symbol, raw))

    # --- AI RISK ---
    with tabs[5]:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        if st.button("Risk Check"):
            st.write(ai_risk_check(df))

    # --- AI PATTERN ---
    with tabs[6]:
        if st.button("Pattern Insight"):
            st.write(ai_pattern_insight(st.session_state.symbols))


if __name__ == "__main__":
    main()
