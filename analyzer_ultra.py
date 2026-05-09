# ============================================
# ULTRA ENGINE v14 — FULL COMBO (TradingView-like)
# ============================================

import os
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ============================================
# TRYB TESTOWY / KLUCZ OPENAI
# ============================================

IS_TEST = os.getenv("PYTEST_RUNNING") == "1"

if IS_TEST:
    OPENAI_KEY = ""
else:
    try:
        OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
    except Exception:
        OPENAI_KEY = ""
        st.warning("Brak klucza OPENAI_API_KEY — AI wyłączone.")

# ============================================
# PRESETY GPW / BIOTECH
# ============================================

GPW_BIOTECH = [
    "MABION.WA",
    "RYVU.WA",
    "CELON.WA",
    "BIOTON.WA",
    "ONCO.WA",
]

US_BIOTECH = [
    "NVAX",
    "MRNA",
    "BNTX",
    "REGN",
    "VRTX",
]

# ============================================
# WSKAŹNIKI
# ============================================

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_macd(series):
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    return macd, signal

def compute_atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def trend_strength_score(df):
    score = np.zeros(len(df))
    score += np.where(df["EMA20"] > df["EMA50"], 1, -1)
    score += np.where(df["SMA20"] > df["SMA50"], 1, -1)
    score += np.where(df["RSI"] > 55, 1, 0)
    score += np.where(df["RSI"] < 45, -1, 0)
    return score

def volume_heat(df, window=20):
    vol = df["Volume"]
    ma = vol.rolling(window).mean()
    heat = (vol / ma).clip(0, 5)
    return heat

def add_indicators_full(df):
    df = df.copy()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["RSI"] = compute_rsi(df["Close"])
    df["MACD"], df["MACD_signal"] = compute_macd(df["Close"])
    df["ATR"] = compute_atr(df)
    df["Momentum"] = df["Close"].diff(5)
    df["Volatility"] = df["Close"].pct_change().rolling(20).std() * 100
    df["TrendScore"] = trend_strength_score(df)
    df["VolHeat"] = volume_heat(df)
    return df

# ============================================
# PATTERNY
# ============================================

def detect_breakout(df, lookback=20, thr=0.01):
    if len(df) < lookback + 1:
        return False
    recent = df["Close"].iloc[-1]
    max_prev = df["Close"].iloc[-lookback:-1].max()
    return recent > max_prev * (1 + thr)

def detect_consolidation(df, lookback=20, threshold_pct=3.0):
    if len(df) < lookback:
        return False
    window = df["Close"].iloc[-lookback:]
    rng = window.max() - window.min()
    mid = window.mean()
    if mid == 0:
        return False
    return (rng / mid * 100) < threshold_pct

def detect_volume_spike(df, window=20, spike_mult=2.0):
    if len(df) < window + 1:
        return False
    vol = df["Volume"]
    ma = vol.rolling(window).mean()
    return vol.iloc[-1] > ma.iloc[-1] * spike_mult

# ============================================
# RYZYKO / SL / TP
# ============================================

def calc_sl_tp(entry, atr, sl_mult=2.0, tp_mult=3.0, direction="long"):
    if atr is None or atr == 0 or np.isnan(atr):
        return None, None, None
    if direction == "long":
        sl = entry - sl_mult * atr
        tp = entry + tp_mult * atr
    else:
        sl = entry + sl_mult * atr
        tp = entry - tp_mult * atr
    rr = abs(tp - entry) / abs(entry - sl) if sl != entry else None
    return sl, tp, rr

# ============================================
# AI MODES
# ============================================

def ai_prop_mode(df, ticker):
    if not OPENAI_KEY:
        return "AI wyłączone — brak klucza."

    last = df.iloc[-1]

    prompt = f"""
    Tryb: Prop-Trader Mode (techniczny, konkretny).
    Ticker: {ticker}

    Dane:
    Close: {last['Close']:.2f}
    SMA20: {last['SMA20']:.2f}
    SMA50: {last['SMA50']:.2f}
    SMA200: {last['SMA200']:.2f}
    EMA20: {last['EMA20']:.2f}
    EMA50: {last['EMA50']:.2f}
    RSI: {last['RSI']:.2f}
    MACD: {last['MACD']:.2f}
    MACD_signal: {last['MACD_signal']:.2f}
    Momentum: {last['Momentum']:.2f}
    Volatility: {last['Volatility']:.2f}
    TrendScore: {last['TrendScore']:.2f}
    VolHeat: {last['VolHeat']:.2f}

    Wygeneruj:
    - Trend: strong/mixed/weak
    - Momentum: strong/mixed/weak
    - Ryzyko: low/medium/high
    - Krótki komentarz techniczny (max 3 zdania).
    """

    if IS_TEST:
        return "AI TEST MODE — Prop Mode pominięty."

    import openai
    openai.api_key = OPENAI_KEY
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp["choices"][0]["message"]["content"]

def ai_deep_dive(df, ticker, patterns, sl, tp, rr):
    if not OPENAI_KEY:
        return "AI wyłączone — brak klucza."

    last = df.iloc[-1]
    brk, cons, vspike = patterns

    prompt = f"""
    Tryb: Deep Dive (GPW/biotech, spekulacja, SL/TP, ryzyko).
    Ticker: {ticker}

    Dane:
    Close: {last['Close']:.2f}
    TrendScore: {last['TrendScore']:.2f}
    RSI: {last['RSI']:.2f}
    ATR: {last['ATR']:.2f}
    VolumeHeat: {last['VolHeat']:.2f}
    Breakout: {brk}
    Konsolidacja: {cons}
    VolumeSpike: {vspike}
    SL: {sl}
    TP: {tp}
    RR: {rr}

    Odpowiedz:
    - 1) Czy to sensowny moment na spekulację (tak/nie + dlaczego)?
    - 2) Główne ryzyka (max 3 punkty).
    - 3) Jakie logiczne scenariusze (bull / bear / neutral).
    - 4) Jak traktować ten trade: impuls/news vs swing.
    """

    if IS_TEST:
        return "AI TEST MODE — Deep Dive pominięty."

    import openai
    openai.api_key = OPENAI_KEY
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp["choices"][0]["message"]["content"]

def ai_signal_mode(df, ticker):
    if not OPENAI_KEY:
        return "AI wyłączone — brak klucza."

    last = df.iloc[-1]

    prompt = f"""
    Tryb: Signal Mode (SMA/EMA/MACD/RSI).
    Ticker: {ticker}

    Dane:
    Close: {last['Close']:.2f}
    SMA20: {last['SMA20']:.2f}
    SMA50: {last['SMA50']:.2f}
    SMA200: {last['SMA200']:.2f}
    EMA20: {last['EMA20']:.2f}
    EMA50: {last['EMA50']:.2f}
    RSI: {last['RSI']:.2f}
    MACD: {last['MACD']:.2f}
    MACD_signal: {last['MACD_signal']:.2f}
    TrendScore: {last['TrendScore']:.2f}

    Odpowiedz:
    - 1) Sygnał: long / short / neutral.
    - 2) Siła sygnału: 1-10.
    - 3) Krótki komentarz (max 2 zdania).
    """

    if IS_TEST:
        return "AI TEST MODE — Signal Mode pominięty."

    import openai
    openai.api_key = OPENAI_KEY
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp["choices"][0]["message"]["content"]

def ai_chat_mode(user_question, df, ticker):
    if not OPENAI_KEY:
        return "AI wyłączone — brak klucza."

    last = df.iloc[-1]

    prompt = f"""
    Tryb: AI-Chat o tickerze.
    Ticker: {ticker}

    Dane (ostatnia świeca):
    Close: {last['Close']:.2f}
    SMA20: {last['SMA20']:.2f}
    SMA50: {last['SMA50']:.2f}
    SMA200: {last['SMA200']:.2f}
    EMA20: {last['EMA20']:.2f}
    EMA50: {last['EMA50']:.2f}
    RSI: {last['RSI']:.2f}
    MACD: {last['MACD']:.2f}
    MACD_signal: {last['MACD_signal']:.2f}
    TrendScore: {last['TrendScore']:.2f}
    VolHeat: {last['VolHeat']:.2f}

    Pytanie użytkownika:
    {user_question}

    Odpowiedz konkretnie, technicznie, bez lania wody.
    """

    if IS_TEST:
        return "AI TEST MODE — Chat Mode pominięty."

    import openai
    openai.api_key = OPENAI_KEY
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp["choices"][0]["message"]["content"]

# ============================================
# WYKRES (TradingView-like)
# ============================================

def plot_tradingview_style(df, ticker):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Price",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a",
        decreasing_fillcolor="#ef5350",
        showlegend=False,
    ))

    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA20"],
        line=dict(color="#42a5f5", width=1),
        name="SMA20"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA50"],
        line=dict(color="#ab47bc", width=1),
        name="SMA50"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA200"],
        line=dict(color="#ffa726", width=1),
        name="SMA200"
    ))

    fig.update_layout(
        title=f"{ticker} — TradingView-like",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=600,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig

# ============================================
# GŁÓWNA ANALIZA
# ============================================

def run_analysis(ticker, period="6mo", interval="1d"):
    df = yf.download(ticker, period=period, interval=interval)
    if df.empty:
        st.error("Brak danych.")
        return

    df = add_indicators_full(df)

    col_chart, col_info = st.columns([2, 1])

    with col_chart:
        st.plotly_chart(plot_tradingview_style(df, ticker), use_container_width=True)

    with col_info:
        last = df.iloc[-1]
        st.markdown("### Snapshot")
        st.write(f"**Close:** {last['Close']:.2f}")
        st.write(f"**RSI:** {last['RSI']:.2f}")
        st.write(f"**TrendScore:** {last['TrendScore']:.2f}")
        st.write(f"**VolHeat:** {last['VolHeat']:.2f}")
        st.write(f"**ATR:** {last['ATR']:.2f}")

        st.markdown("### Patterny")
        brk = detect_breakout(df)
        cons = detect_consolidation(df)
        vspike = detect_volume_spike(df)
        st.write(f"Breakout: {'TAK' if brk else 'NIE'}")
        st.write(f"Konsolidacja: {'TAK' if cons else 'NIE'}")
        st.write(f"Volume spike: {'TAK' if vspike else 'NIE'}")

        entry = float(last["Close"])
        atr = float(last["ATR"]) if not np.isnan(last["ATR"]) else 0.0
        sl, tp, rr = calc_sl_tp(entry, atr, sl_mult=2.0, tp_mult=3.0, direction="long")

        st.markdown("### SL/TP (ATR-based)")
        if sl is None:
            st.write("Brak ATR — nie można policzyć SL/TP.")
        else:
            st.write(f"Entry: {entry:.2f}")
            st.write(f"SL: {sl:.2f}")
            st.write(f"TP: {tp:.2f}")
            st.write(f"R:R ≈ {rr:.2f}" if rr else "R:R: n/d")

    st.markdown("### Dane (ostatnie 30)")
    st.dataframe(df.tail(30))

    st.markdown("### AI Mode")
    mode = st.selectbox("Tryb AI:", ["Prop Mode", "Deep Dive", "Signal Mode", "Chat Mode"])

    if mode == "Prop Mode":
        ai_text = ai_prop_mode(df, ticker)
        st.write(ai_text)

    elif mode == "Deep Dive":
        brk = detect_breakout(df)
        cons = detect_consolidation(df)
        vspike = detect_volume_spike(df)
        entry = float(df["Close"].iloc[-1])
        atr = float(df["ATR"].iloc[-1]) if not np.isnan(df["ATR"].iloc[-1]) else 0.0
        sl, tp, rr = calc_sl_tp(entry, atr, sl_mult=2.0, tp_mult=3.0, direction="long")
        ai_text = ai_deep_dive(df, ticker, (brk, cons, vspike), sl, tp, rr)
        st.write(ai_text)

    elif mode == "Signal Mode":
        ai_text = ai_signal_mode(df, ticker)
        st.write(ai_text)

    else:  # Chat Mode
        question = st.text_area("Twoje pytanie do AI o ten ticker:")
        if st.button("Wyślij pytanie"):
            ai_text = ai_chat_mode(question, df, ticker)
            st.write(ai_text)

# ============================================
# UI — TRADINGVIEW-LIKE KOMBAJN
# ============================================

if not IS_TEST:
    st.set_page_config(page_title="ULTRA ENGINE v14", layout="wide")
    st.title("ULTRA ENGINE v14 — TradingView-like GPW / Biotech / AI")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        market = st.selectbox("Rynek:", ["GPW Biotech", "US Biotech", "Custom"])
        if market == "GPW Biotech":
            ticker = st.selectbox("Spółka:", GPW_BIOTECH)
        elif market == "US Biotech":
            ticker = st.selectbox("Spółka:", US_BIOTECH)
        else:
            ticker = st.text_input("Własny ticker (np. AAPL, MABION.WA):", "MABION.WA")

    with col_right:
        period = st.selectbox("Okres:", ["3mo", "6mo", "1y"], index=1)
        interval = st.selectbox("Interwał:", ["1d", "1h"], index=0)

    if st.button("Analizuj"):
        run_analysis(ticker, period=period, interval=interval)
