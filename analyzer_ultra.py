# ============================================
# ULTRA ENGINE v14 — ANALYZER FULL (1:1)
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
    cond_trend = df["EMA20"] > df["EMA50"]
    score = score + np.where(cond_trend, 1, -1)
    score = score + np.where(df["RSI"] > 55, 1, 0)
    score = score + np.where(df["RSI"] < 45, -1, 0)
    return score

def volume_heat(df, window=20):
    vol = df["Volume"]
    ma = vol.rolling(window).mean()
    heat = (vol / ma).clip(0, 5)
    return heat

def add_indicators_full(df):
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["RSI"] = compute_rsi(df["Close"])
    df["MACD"], df["MACD_signal"] = compute_macd(df["Close"])
    df["ATR"] = compute_atr(df)
    df["TrendScore"] = trend_strength_score(df)
    df["VolHeat"] = volume_heat(df)
    df["Momentum"] = df["Close"].diff(5)
    df["Volatility"] = df["Close"].pct_change().rolling(20).std() * 100
    return df

# ============================================
# PATTERNY (SPEKULACJA)
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
# AI — PROP MODE / DEEP DIVE
# ============================================

def ai_analysis_prop_mode(df, ticker):
    if not OPENAI_KEY:
        return "AI wyłączone — brak klucza."

    last = df.iloc[-1]

    prompt = f"""
    Tryb: Prop-Trader Mode (techniczny, konkretny).
    Ticker: {ticker}

    Dane:
    Close: {last['Close']:.2f}
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

def ai_deep_dive_mode(df, ticker):
    if not OPENAI_KEY:
        return "AI wyłączone — brak klucza."

    last = df.iloc[-1]
    trend = last.get("TrendScore", 0)
    rsi = last.get("RSI", None)
    atr = last.get("ATR", None)
    volh = last.get("VolHeat", None)

    prompt = f"""
    Tryb: Deep Dive (GPW/biotech, spekulacja, SL/TP, ryzyko).
    Ticker: {ticker}

    Dane:
    Close: {last['Close']:.2f}
    TrendScore: {trend}
    RSI: {rsi}
    ATR: {atr}
    VolumeHeat: {volh}

    Odpowiedz:
    - 1) Czy to sensowny moment na spekulację (tak/nie + dlaczego)?
    - 2) Główne ryzyka (max 3 punkty).
    - 3) Jakie logiczne poziomy SL/TP (opisowo, nie liczbowo).
    - 4) Bardziej trade na news/impuls czy swing/mean reversion?
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

# ============================================
# WYKRES
# ============================================

def plot_candles(df, ticker):
    fig = go.Figure(data=[
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Candles"
        )
    ])
    fig.update_layout(title=f"{ticker} — Wykres świecowy", height=600)
    return fig

# ============================================
# GŁÓWNA FUNKCJA ANALIZY
# ============================================

def run_analysis(ticker: str, period: str = "6mo", interval: str = "1d"):
    df = yf.download(ticker, period=period, interval=interval)
    if df.empty:
        st.error("Brak danych.")
        return

    df = add_indicators_full(df)

    st.subheader("Wykres")
    st.plotly_chart(plot_candles(df, ticker), use_container_width=True)

    st.subheader("Ostatnie dane (wskaźniki)")
    st.dataframe(df.tail(15))

    # Patterny
    brk = detect_breakout(df)
    cons = detect_consolidation(df)
    vspike = detect_volume_spike(df)

    st.subheader("Patterny (spekulacja biotech / news trade)")
    st.write(f"Breakout: {'TAK' if brk else 'NIE'}")
    st.write(f"Konsolidacja: {'TAK' if cons else 'NIE'}")
    st.write(f"Volume spike: {'TAK' if vspike else 'NIE'}")

    # SL/TP
    last = df.iloc[-1]
    entry = float(last["Close"])
    atr = float(last["ATR"]) if not np.isnan(last["ATR"]) else 0.0
    sl, tp, rr = calc_sl_tp(entry, atr, sl_mult=2.0, tp_mult=3.0, direction="long")

    st.subheader("Spekulacja — SL/TP (ATR-based)")
    if sl is None:
        st.write("Brak ATR — nie można policzyć SL/TP.")
    else:
        st.write(f"Entry: {entry:.2f}")
        st.write(f"SL: {sl:.2f}")
        st.write(f"TP: {tp:.2f}")
        st.write(f"R:R ≈ {rr:.2f}" if rr else "R:R: n/d")

    # AI tryb
    mode = st.radio("Tryb AI", ["Prop Mode", "Deep Dive"])
    if mode == "Prop Mode":
        ai_text = ai_analysis_prop_mode(df, ticker)
    else:
        ai_text = ai_deep_dive_mode(df, ticker)

    st.subheader(f"AI — {mode}")
    st.write(ai_text)

# ============================================
# UI STREAMLIT
# ============================================

if not IS_TEST:
    st.title("ULTRA ENGINE v14 — Analyzer (GPW / Biotech / Spekulacja)")

    default_ticker = "MABION.WA"  # przykładowy biotech z GPW
    ticker = st.text_input("Ticker (GPW: *.WA, US: np. AAPL):", default_ticker)

    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox("Okres:", ["3mo", "6mo", "1y"], index=1)
    with col2:
        interval = st.selectbox("Interwał:", ["1d", "1h"], index=0)

    if st.button("Analizuj"):
        run_analysis(ticker, period=period, interval=interval)

# ============================================
# KONIEC
# ============================================
