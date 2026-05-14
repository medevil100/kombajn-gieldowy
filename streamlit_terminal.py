import os
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from openai import OpenAI

st.set_page_config(page_title="AI Trading Terminal PRO", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp { 
    background-color: #02030a; 
    color: #e5e7eb; 
}
.block-container { 
    padding-top: 0.5rem; 
}
.sidebar .sidebar-content { 
    background: radial-gradient(circle at top left, #020617, #000000); 
    border-right: 1px solid #1f2937;
}
h1, h2, h3, h4 { 
    color: #f9fafb; 
    text-shadow: 0 0 12px rgba(56,189,248,0.35);
}
.stButton>button {
    background: linear-gradient(135deg, #0f172a, #0369a1);
    color: #e5e7eb;
    border-radius: 999px;
    border: 1px solid #38bdf8;
    padding: 0.35rem 0.9rem;
    font-size: 0.85rem;
    font-weight: 600;
    box-shadow: 0 0 14px rgba(56,189,248,0.35);
}
.stButton>button:hover {
    border-color: #22c55e;
    box-shadow: 0 0 18px rgba(34,197,94,0.55);
}
.metric-green { 
    color: #22c55e; 
    text-shadow: 0 0 8px rgba(34,197,94,0.7);
}
.metric-yellow { 
    color: #eab308; 
    text-shadow: 0 0 8px rgba(234,179,8,0.7);
}
.metric-red { 
    color: #ef4444; 
    text-shadow: 0 0 8px rgba(239,68,68,0.7);
}
</style>
""", unsafe_allow_html=True)

def get_openai_client():
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except:
        return None

def calculate_rsi(series, window=14):
    if len(series) < window:
        return pd.Series([50] * len(series), index=series.index)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line
    return macd, signal_line, hist

def calculate_atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

def detect_trend(series, short=20, long=50):
    ema_short = series.ewm(span=short, adjust=False).mean()
    ema_long = series.ewm(span=long, adjust=False).mean()
    trend = np.where(ema_short > ema_long, 1, np.where(ema_short < ema_long, -1, 0))
    return ema_short, ema_long, trend

def build_trading_prompt(style: str) -> str:
    base = (
        "Jesteś profesjonalnym traderem technicznym. Oceniaj instrument konkretnie, bez lania wody.\n"
        "FORMAT:\n"
        "#1 DECYZJA: KUP / SPRZEDAJ / WSTRZYMAJ\n"
        "#2 UZASADNIENIE:\n"
        "- Trend (EMA/SMA, struktura)\n"
        "- Momentum (RSI, MACD)\n"
        "- Volatility (ATR, zakres ruchu)\n"
        "- Poziomy: wsparcia / opory\n"
        "#3 PLAN TRANSAKCJI:\n"
        "- ENTRY\n"
        "- SL\n"
        "- TP1 / TP2 / TP3\n"
        "#4 RYZYKO: 1–10\n"
        "#5 DODATKOWE UWAGI\n\n"
    )
    return base + f"Styl analizy: {style}."

def call_gpt(client: OpenAI | None, model_name: str, system_prompt: str, user_prompt: str) -> str:
    if client is None:
        return "AI OFF – brak poprawnego klucza OpenAI w secrets."
    try:
        r = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"AI ERROR: {e}"

@st.cache_data(show_spinner=False)
def load_data(symbol: str, interval: str, period: str):
    df = yf.download(symbol, interval=interval, period=period, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    return df

st.sidebar.header("⚙️ Ustawienia terminala")
symbol = st.sidebar.text_input("Ticker", value="", placeholder="np. AAPL, MSFT, TSLA, EURUSD=X")
tf_label = st.sidebar.selectbox(
    "Interwał",
    ["1m", "5m", "15m", "30m", "1h"],
    index=2
)
if tf_label == "1m":
    interval = "1m"
    period = "5d"
elif tf_label == "5m":
    interval = "5m"
    period = "10d"
elif tf_label == "15m":
    interval = "15m"
    period = "30d"
elif tf_label == "30m":
    interval = "30m"
    period = "60d"
else:
    interval = "60m"
    period = "1y"

model_name = st.sidebar.selectbox(
    "Model GPT",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini"],
    index=0
)

ai_style = st.sidebar.selectbox(
    "Styl analizy AI",
    ["Ultra krótko", "Technicznie", "Swing", "Daytrading", "Price Action", "Momentum", "Konserwatywnie"],
    index=1
)

st.title("AI Trading Terminal PRO")

if not symbol:
    st.info("Wpisz ticker w panelu bocznym, aby rozpocząć.")
else:
    df = load_data(symbol, interval, period)
    if df.empty or len(df) < 20:
        st.warning("Brak wystarczających danych dla tego instrumentu / interwału.")
    else:
        df["RSI"] = calculate_rsi(df["Close"], 14)
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        macd, macd_signal, macd_hist = calculate_macd(df["Close"])
        df["MACD"] = macd
        df["MACD_SIGNAL"] = macd_signal
        df["MACD_HIST"] = macd_hist
        df["ATR"] = calculate_atr(df, 14)
        ema_short, ema_long, trend = detect_trend(df["Close"], 20, 50)
        df["EMA_TREND_SHORT"] = ema_short
        df["EMA_TREND_LONG"] = ema_long
        df["TREND_DIR"] = trend
        bb_mid = df["Close"].rolling(20).mean()
        bb_std = df["Close"].rolling(20).std()
        df["BB_MID"] = bb_mid
        df["BB_UPPER"] = bb_mid + 2 * bb_std
        df["BB_LOWER"] = bb_mid - 2 * bb_std

        last = df.iloc[-1]
        atr = float(last["ATR"]) if not np.isnan(last["ATR"]) else 0.0
        last_close = float(last["Close"])
        if atr > 0:
            sl = last_close - 1.5 * atr
            tp1 = last_close + 1.0 * atr
            tp2 = last_close + 2.0 * atr
            tp3 = last_close + 3.0 * atr
        else:
            sl = last_close * 0.97
            tp1 = last_close * 1.02
            tp2 = last_close * 1.04
            tp3 = last_close * 1.06

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            chg = (last_close / df["Close"].iloc[-2] - 1) * 100 if len(df) > 1 else 0
            cls = "metric-green" if chg > 0 else "metric-red" if chg < 0 else "metric-yellow"
            st.markdown(f"<div class='{cls}'>Cena: {last_close:.4f} ({chg:+.2f}%)</div>", unsafe_allow_html=True)
        with col2:
            rsi_val = float(last["RSI"])
            if rsi_val < 30:
                cls = "metric-green"
            elif rsi_val > 70:
                cls = "metric-red"
            else:
                cls = "metric-yellow"
            st.markdown(f"<div class='{cls}'>RSI: {rsi_val:.1f}</div>", unsafe_allow_html=True)
        with col3:
            if trend[-1] > 0:
                txt = "Trend: Wzrostowy"
                cls = "metric-green"
            elif trend[-1] < 0:
                txt = "Trend: Spadkowy"
                cls = "metric-red"
            else:
                txt = "Trend: Boczniak"
                cls = "metric-yellow"
            st.markdown(f"<div class='{cls}'>{txt}</div>", unsafe_allow_html=True)
        with col4:
            st.markdown(
                f"<div class='metric-yellow'>ATR: {atr:.4f}</div>",
                unsafe_allow_html=True
            )

        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.45, 0.15, 0.2, 0.2]
        )

        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="Cena",
                increasing_line_color="#22c55e",
                decreasing_line_color="#ef4444"
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["EMA20"],
                line=dict(color="#22c55e", width=1.2),
                name="EMA20"
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["EMA50"],
                line=dict(color="#eab308", width=1.2),
                name="EMA50"
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["SMA200"],
                line=dict(color="#ef4444", width=1.2),
                name="SMA200"
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["BB_UPPER"],
                line=dict(color="#eab308", width=0.8, dash="dot"),
                name="BB Upper"
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["BB_MID"],
                line=dict(color="#eab308", width=0.8),
                name="BB Mid"
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["BB_LOWER"],
                line=dict(color="#eab308", width=0.8, dash="dot"),
                name="BB Lower"
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["Volume"],
                marker_color=np.where(df["Close"] >= df["Open"], "#22c55e", "#ef4444"),
                name="Volume"
            ),
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["RSI"],
                line=dict(color="#eab308", width=1.2),
                name="RSI"
            ),
            row=3, col=1
        )
        fig.add_hrect(
            y0=30, y1=70,
            line_width=0,
            fillcolor="rgba(148,163,184,0.15)",
            row=3, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MACD"],
                line=dict(color="#22c55e", width=1.2),
                name="MACD"
            ),
            row=4, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MACD_SIGNAL"],
                line=dict(color="#ef4444", width=1.0),
                name="MACD Signal"
            ),
            row=4, col=1
        )
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["MACD_HIST"],
                marker_color=np.where(df["MACD_HIST"] >= 0, "#22c55e", "#ef4444"),
                name="MACD Hist"
            ),
            row=4, col=1
        )

        fig.update_layout(
            template="plotly_dark",
            height=900,
            xaxis_rangeslider_visible=False,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Plan transakcji (ST / TP1 / TP2 / TP3)")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"<div class='metric-red'>SL: {sl:.4f}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='metric-green'>TP1: {tp1:.4f}</div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='metric-green'>TP2: {tp2:.4f}</div>", unsafe_allow_html=True)
        with c4:
            st.markdown(f"<div class='metric-green'>TP3: {tp3:.4f}</div>", unsafe_allow_html=True)

        st.subheader("AI analiza instrumentu")
        client = get_openai_client()
        if st.button("🔮 Wygeneruj analizę AI"):
            system_prompt = build_trading_prompt(ai_style)
            user_prompt = (
                f"Przeanalizuj instrument {symbol} na interwale {tf_label}. "
                f"Ostatnia cena: {last_close:.4f}, RSI: {last['RSI']:.1f}, ATR: {atr:.4f}. "
                f"Trend wyznaczony przez EMA20/EMA50 oraz SMA200. "
                f"Poziomy techniczne: BB Upper {df['BB_UPPER'].iloc[-1]:.4f}, "
                f"BB Lower {df['BB_LOWER'].iloc[-1]:.4f}. "
                f"Proponowane poziomy: SL {sl:.4f}, TP1 {tp1:.4f}, TP2 {tp2:.4f}, TP3 {tp3:.4f}."
            )
            out = call_gpt(client, model_name, system_prompt, user_prompt)
            st.markdown(out)

st.markdown("""
<hr style='border: 1px solid #1f2937; margin-top: 40px;'>
<div style='text-align: center; color: #6b7280; font-size: 0.8rem;'>
    AI Trading Terminal PRO • Neon Dark • RSI / MACD / EMA / SMA / BB / ATR • 2026
</div>
""", unsafe_allow_html=True)
