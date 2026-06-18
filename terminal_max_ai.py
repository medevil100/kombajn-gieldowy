import re
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ============================================================
#   CONFIG
# ============================================================

st.set_page_config(
    page_title="CYBER‑DESK PRO ULTRA v4",
    page_icon="💠",
    layout="wide",
)

# ============================================================
#   GLOBAL CSS
# ============================================================

st.markdown("""
<style>
body, .stApp {
    background-color: #050816;
    color: #E5E7EB;
    font-family: 'Inter', sans-serif;
}

.neon-box {
    border-radius: 12px;
    padding: 14px 18px;
    border: 1px solid rgba(56,189,248,0.4);
    background: radial-gradient(circle at top left, rgba(56,189,248,0.12), rgba(15,23,42,0.95));
}
.neon-box-yellow {
    border-radius: 12px;
    padding: 14px 18px;
    border: 1px solid rgba(250,204,21,0.6);
    background: radial-gradient(circle at top left, rgba(250,204,21,0.12), rgba(15,23,42,0.95));
}

.signal-buy { color: #22c55e; font-weight: 700; }
.signal-sell { color: #f97316; font-weight: 700; }
.signal-hold { color: #e5e7eb; font-weight: 700; }

.score-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.85rem;
    background: rgba(56,189,248,0.12);
    border: 1px solid rgba(56,189,248,0.6);
    color: #e5e7eb;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
#   HELPERS
# ============================================================

def to_scalar(x):
    try:
        if isinstance(x, (pd.Series, np.ndarray, list)):
            return float(np.asarray(x).ravel()[-1])
        return float(x)
    except:
        return np.nan

def safe_last(series):
    try:
        return float(series.dropna().iloc[-1])
    except:
        return np.nan

# ============================================================
#   INDICATORS — ENGINE 3.1 (zero NaN)
# ============================================================

def compute_indicators(close, volume):
    close = close.copy()

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = safe_last(rsi_series)

    # MA
    ma_fast = safe_last(close.rolling(10).mean())
    ma_slow = safe_last(close.rolling(30).mean())

    # Bollinger
    ma_bb = close.rolling(20).mean()
    std_bb = close.rolling(20).std()
    upper_bb = ma_bb + 2 * std_bb
    lower_bb = ma_bb - 2 * std_bb
    last_upper = safe_last(upper_bb)
    last_lower = safe_last(lower_bb)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()

    # Volatility
    vol = safe_last(close.pct_change().rolling(20).std())

    # Volume
    vol_last = safe_last(volume)

    # Trend
    if not np.isnan(ma_fast) and not np.isnan(ma_slow):
        trend = "Uptrend" if ma_fast > ma_slow else "Downtrend"
    else:
        trend = "Unknown"

    return {
        "rsi": rsi,
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
        "upper_bb": upper_bb,
        "lower_bb": lower_bb,
        "last_upper_bb": last_upper,
        "last_lower_bb": last_lower,
        "macd": macd,
        "macd_signal": macd_signal,
        "vol": vol,
        "volume": vol_last,
        "sl": last_lower,
        "tp": last_upper,
        "trend": trend,
    }

# ============================================================
#   SCORING ENGINE 3.1
# ============================================================

def compute_score(price, ind):
    score = 50
    details = []

    rsi = ind["rsi"]
    trend = ind["trend"]
    vol = ind["vol"]
    sl = ind["sl"]
    tp = ind["tp"]

    # RSI
    if not np.isnan(rsi):
        if rsi < 25:
            score += 25
            details.append("RSI < 25 → wyprzedanie → +25")
        elif rsi > 75:
            score -= 25
            details.append("RSI > 75 → wykupienie → -25")
        else:
            score += 10
            details.append("RSI neutralne → +10")

    # Trend
    if trend == "Uptrend":
        score += 15
        details.append("Trend wzrostowy → +15")
    elif trend == "Downtrend":
        score -= 15
        details.append("Trend spadkowy → -15")

    # Volatility
    if not np.isnan(vol):
        if vol < 0.01:
            score -= 5
            details.append("Niska zmienność → -5")
        elif vol > 0.06:
            score -= 5
            details.append("Wysoka zmienność → -5")
        else:
            score += 5
            details.append("Umiarkowana zmienność → +5")

    # Bollinger
    if not any(np.isnan([price, sl, tp])) and tp != sl:
        rel = (price - sl) / (tp - sl)
        if rel < 0.1:
            score += 10
            details.append("Cena przy dolnym BB → +10")
        elif rel > 0.9:
            score -= 10
            details.append("Cena przy górnym BB → -10")
        else:
            score += 15
            details.append("Cena w środku kanału → +15")

    score = max(0, min(100, score))

    if score >= 80:
        label = "Silny setup"
    elif score >= 65:
        label = "Dobry setup"
    elif score >= 45:
        label = "Neutralny"
    elif score >= 30:
        label = "Słaby setup"
    else:
        label = "Ryzykowny setup"

    return score, label, details

# ============================================================
#   SIGNAL ENGINE
# ============================================================

def generate_signal(price, ind):
    rsi = ind["rsi"]
    trend = ind["trend"]

    if np.isnan(rsi):
        return "STOP", "Brak danych RSI"

    if rsi < 25:
        return "BUY", "RSI < 25 → wyprzedanie"
    if rsi > 75:
        return "SELL", "RSI > 75 → wykupienie"

    return "HOLD", "Brak jednoznacznego edge"

# ============================================================
#   RISK
# ============================================================

def compute_risk_summary(price, sl, tp):
    if any(np.isnan([price, sl, tp])):
        return None
    risk = (price - sl) / price * 100
    reward = (tp - price) / price * 100
    rr = reward / abs(risk) if risk > 0 else np.nan
    return {"risk": risk, "reward": reward, "rr": rr}

# ============================================================
#   MAIN CHART — COMPACT‑MINI (260px)
# ============================================================

def render_main_chart(ticker, data, ind):
    close = data["Close"]
    open_ = data["Open"]
    high = data["High"]
    low = data["Low"]

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=open_, high=high, low=low, close=close,
        increasing_line_color="#22c55e",
        decreasing_line_color="#f97316",
    ))
    fig.add_trace(go.Scatter(
        x=data.index, y=ind["upper_bb"],
        line=dict(color="rgba(34,197,94,0.6)", width=1),
        name="BB Upper",
    ))
    fig.add_trace(go.Scatter(
        x=data.index, y=ind["lower_bb"],
        line=dict(color="rgba(239,68,68,0.6)", width=1),
        name="BB Lower",
    ))

    fig.update_layout(
        height=260,
        autosize=False,
        margin=dict(l=8, r=8, t=28, b=8),
        plot_bgcolor="#020617",
        paper_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        xaxis=dict(gridcolor="#1f2937"),
        yaxis=dict(gridcolor="#1f2937"),
        title=f"{ticker} — wykres świecowy (COMPACT‑MINI)",
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
#   MINI CHARTS
# ============================================================

def render_mini_charts(close, ind):
    st.markdown("### 📉 Mini‑wykresy")

    # Sparkline
    mini = close.tail(60)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=mini.index, y=mini.values,
        mode="lines", line=dict(color="#22c55e", width=2),
    ))
    fig.update_layout(
        height=120,
        margin=dict(l=5, r=5, t=20, b=5),
        plot_bgcolor="#020617",
        paper_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False),
        title="Sparkline",
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
#   MONITOR — RIGHT PANEL (auto‑height)
# ============================================================

def render_monitor(monitor_tickers, refresh_choice):
    st.markdown("### 🖥️ Monitor 5 spółek")

    tick_list = [t.strip() for t in monitor_tickers.split(",") if t.strip()]
    tick_list = tick_list[:5]

    if not tick_list:
        st.info("Wpisz tickery do monitorowania.")
        return

    for tck in tick_list:
        try:
            d = yf.download(tck, period="5d", interval="1d")

            if d.empty:
                st.write(f"**{tck}:** brak danych")
                continue

            # Obsługa MultiIndex (np. GPW, ETF-y, indeksy)
            if isinstance(d.columns, pd.MultiIndex):
                close = d["Close"].iloc[:, 0].dropna()
                vol = d["Volume"].iloc[:, 0].fillna(0)
            else:
                close = d["Close"].dropna()
                vol = d["Volume"].fillna(0)

            if close.empty:
                st.write(f"**{tck}:** brak świec")
                continue

            price = to_scalar(close.iloc[-1])
            ind = compute_indicators(close, vol)
            score, label, _ = compute_score(price, ind)

            color = "#22c55e" if score >= 60 else "#f97316" if score < 40 else "#e5e7eb"

            st.markdown(
                f"""
                <div class="neon-box-yellow">
                    <div class="neon-title">{tck}</div>
                    <div class="neon-sub">
                        Cena: {price:.2f}<br/>
                        Scoring: <span style="color:{color};">{score} – {label}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        except Exception as e:
            st.write(f"**{tck}:** błąd danych ({e})")


# ============================================================
#   TRADING PANEL — LEFT + RIGHT COLUMNS
# ============================================================

def render_trading():
    st.markdown("## 📈 Kombajn Tradingowy — ULTRA Panel v4 (COMPACT‑MINI)")

    left, right = st.columns([0.7, 0.3])

    with left:
        ticker = st.text_input("Ticker:", "AAPL")
        period = st.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
        interval = st.selectbox("Interwał:", ["1m", "5m", "15m", "30m", "1h", "1d"], index=5)

        if st.button("Pobierz dane i policz sygnały", use_container_width=True):
            data = yf.download(ticker, period=period, interval=interval)
            if data.empty:
                st.error("Brak danych.")
                return

            close = data["Close"]
            vol = data["Volume"]
            price = to_scalar(close.iloc[-1])

            ind = compute_indicators(close, vol)
            score, score_label, score_details = compute_score(price, ind)
            signal, explanation = generate_signal(price, ind)
            risk = compute_risk_summary(price, ind["sl"], ind["tp"])

            render_main_chart(ticker, data, ind)

            st.markdown("### 🤖 Sygnał AI")
            st.write(f"**Sygnał:** {signal}")
            st.write(f"**Cena:** {price:.2f}")

            sl = ind["sl"]
            tp = ind["tp"]

            st.write(f"**SL:** {sl:.2f}" if not np.isnan(sl) else "**SL:** brak danych")
            st.write(f"**TP:** {tp:.2f}" if not np.isnan(tp) else "**TP:** brak danych")

            st.markdown(f'<span class="score-badge">Scoring: {score}/100 – {score_label}</span>', unsafe_allow_html=True)

            st.markdown("### Uzasadnienie")
            st.write(explanation)

            st.markdown("### Detale scoringu")
            for d in score_details:
                st.write(f"- {d}")

            st.markdown("---")
            render_mini_charts(close, ind)

    with right:
        monitor_tickers = st.text_input("Monitor (max 5):", "AAPL, MSFT, NVDA")
        refresh_choice = st.selectbox("Auto‑refresh:", ["Brak", "10 min", "15 min", "30 min"])
        render_monitor(monitor_tickers, refresh_choice)

# ============================================================
#   ROUTING
# ============================================================

render_trading()
