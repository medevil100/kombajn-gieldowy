import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import requests
import json
import os
from datetime import datetime

# ---------------------------------------------------------
# KONFIGURACJA
# ---------------------------------------------------------

st.set_page_config(
    page_title="AI ALPHA MONSTER PRO v74",
    page_icon="🚜",
    layout="wide",
)

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
})

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

TICKERS_FILE = "moje_spolki.txt"
PORTFOLIO_FILE = "portfolio.json"

# ---------------------------------------------------------
# SESSION STATE FIX — NAJWAŻNIEJSZA POPRAWKA
# ---------------------------------------------------------

if "tickers_text" not in st.session_state:
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, "r") as f:
            st.session_state.tickers_text = f.read().strip()
    else:
        st.session_state.tickers_text = ""

if "risk_cap" not in st.session_state:
    st.session_state.risk_cap = 10000.0

if "risk_pct" not in st.session_state:
    st.session_state.risk_pct = 1.0

# ---------------------------------------------------------
# CSS
# ---------------------------------------------------------

st.markdown("""
<style>
.stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
.top-mini-tile { padding: 15px; border-radius: 12px; text-align: center; background: linear-gradient(145deg,#0d1117,#050505); border:1px solid #30363d; margin-bottom:15px; }
.tile-buy { border:2px solid #00ff88!important; box-shadow:0 0 15px rgba(0,255,136,0.3); }
.tile-sell { border:2px solid #ff4b4b!important; box-shadow:0 0 15px rgba(255,75,75,0.3); }
.tile-neutral { border:2px solid #8b949e!important; box-shadow:0 0 15px rgba(139,148,158,0.3); }
.main-card { background:linear-gradient(145deg,#0d1117,#020202); padding:35px; border-radius:25px; border:1px solid #30363d; text-align:center; min-height:1100px; width:100%; margin-bottom:40px; }
.pos-calc-box { background:rgba(88,166,255,0.08); border-radius:15px; padding:25px; margin:25px 0; border:1px solid #58a6ff; color:#58a6ff; }
.tech-grid { display:grid; grid-template-columns:1fr 1fr; gap:15px; background:rgba(255,255,255,0.02); padding:20px; border-radius:20px; text-align:left; }
.tech-row { border-bottom:1px solid #21262d; padding:10px 0; display:flex; justify-content:space-between; }
.news-link { color:#58a6ff; text-decoration:none; font-size:0.85rem; display:block; margin-bottom:12px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# FUNKCJE
# ---------------------------------------------------------

def save_tickers(text):
    with open(TICKERS_FILE, "w") as f:
        f.write(text)

def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"positions": [], "history": [], "value_history": []}
    try:
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    except:
        return {"positions": [], "history": [], "value_history": []}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f, indent=4)

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = delta.where(delta < 0, 0).abs().rolling(period).mean()
    rs = gain / (loss + 1e-12)
    return 100 - (100 / (1 + rs))

def compute_macd(series):
    return series.ewm(span=12).mean() - series.ewm(span=26).mean()

def compute_ema(series, period):
    return series.ewm(span=period).mean()

def compute_atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def analyze_symbol(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d")
        if df.empty or len(df) < 50:
            return None

        df["Close"] = df["Close"].replace(0, np.nan).ffill()

        price = df["Close"].iloc[-1]
        prev = df.iloc[-2]

        rsi = compute_rsi(df["Close"]).iloc[-1]
        macd = compute_macd(df["Close"]).iloc[-1]
        ema20 = compute_ema(df["Close"], 20).iloc[-1]
        ema50 = compute_ema(df["Close"], 50).iloc[-1]
        atr = compute_atr(df).iloc[-1]

        sl = price - atr * 1.5
        tp = price + atr * 3.0

        score = 50
        if rsi < 30: score += 15
        if rsi > 70: score -= 15
        if macd > 0: score += 10
        if ema20 > ema50: score += 10
        if atr < price * 0.05: score += 5

        return {
            "symbol": symbol,
            "price": float(price),
            "rsi": float(rsi),
            "macd": float(macd),
            "ema20": float(ema20),
            "ema50": float(ema50),
            "atr": float(atr),
            "sl": float(sl),
            "tp": float(tp),
            "score": int(score),
            "df": df.tail(80),
            "news": []
        }
    except:
        return None

# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

st.sidebar.title("🚜 MONSTER v74 PRO")

refresh_minutes = st.sidebar.slider("Auto-refresh (minuty)", 1, 10, 3)
if st.sidebar.checkbox("Włącz auto-refresh", value=True):
    st_autorefresh(interval=refresh_minutes * 60 * 1000, key="auto_refresh_v74")

st.session_state.risk_cap = st.sidebar.number_input("Kapitał PLN:", value=st.session_state.risk_cap)
st.session_state.risk_pct = st.sidebar.slider("Ryzyko % na pozycję:", 0.1, 5.0, st.session_state.risk_pct)

tickers_text = st.sidebar.text_area(
    "Lista symboli (CSV):",
    st.session_state.tickers_text,
    height=200,
    placeholder="ADTX, ACRS, ALZN, NVDA, TSLA"
)

if st.sidebar.button("💾 Zapisz listę"):
    st.session_state.tickers_text = tickers_text
    save_tickers(tickers_text)
    st.rerun()

# ---------------------------------------------------------
# ANALIZA
# ---------------------------------------------------------

st.title("AI ALPHA MONSTER PRO v74")

symbols = [s.strip().upper() for s in st.session_state.tickers_text.split(",") if s.strip()]
results = []

for sym in symbols:
    r = analyze_symbol(sym)
    if r:
        results.append(r)

# ---------------------------------------------------------
# WYNIKI
# ---------------------------------------------------------

if results:
    st.subheader("🔥 TOP 10 (scoring 0–100)")
    cols = st.columns(5)
    for i, r in enumerate(sorted(results, key=lambda x: x["score"], reverse=True)[:10]):
        tile = "tile-neutral"
        if r["rsi"] < 33: tile = "tile-buy"
        if r["rsi"] > 67: tile = "tile-sell"

        with cols[i % 5]:
            st.markdown(
                f"<div class='top-mini-tile {tile}'><b>{r['symbol']}</b><br>{r['price']:.4f}<br><small>score: {r['score']}</small></div>",
                unsafe_allow_html=True
            )

st.divider()

# ---------------------------------------------------------
# --- POPRAWIONE ZARZĄDZANIE LISTĄ SPÓŁEK ---

# 1. Inicjalizacja session_state PRZED text_area
if "tickers_text" not in st.session_state:
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, "r") as f:
            st.session_state.tickers_text = f.read().strip()
    else:
        st.session_state.tickers_text = ""

# 2. Pole tekstowe korzysta TYLKO z session_state
tickers_text = st.sidebar.text_area(
    "Lista symboli (CSV):",
    st.session_state.tickers_text,
    height=200,
    placeholder="NVDA, TSLA, AAPL"
)

# 3. Zapis listy + rerun
if  st.sidebar.button("💾 Zapisz listę"):
    st.session_state.tickers_text = tickers_text
    with open(TICKERS_FILE, "w") as f:
        f.write(tickers_text)
    st.rerun()

# ---------------------------------------------------------

if results:
    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            st.markdown(f"<div class='main-card'><h2>{r['symbol']}</h2><h1 style='color:#58a6ff'>{r['price']:.6f}</h1>", unsafe_allow_html=True)

            st.markdown(f"<div class='pos-calc-box'>TP: {r['tp']:.6f}<br>SL: {r['sl']:.6f}</div>", unsafe_allow_html=True)

            st.markdown("<div class='tech-grid'>", unsafe_allow_html=True)
            st.markdown(f"<div class='tech-row'><span>RSI</span><span>{r['rsi']:.1f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='tech-row'><span>MACD</span><span>{r['macd']:.4f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='tech-row'><span>EMA20</span><span>{r['ema20']:.4f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='tech-row'><span>EMA50</span><span>{r['ema50']:.4f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='tech-row'><span>ATR</span><span>{r['atr']:.4f}</span></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            fig = go.Figure(data=[go.Candlestick(
                x=r["df"].index,
                open=r["df"]["Open"],
                high=r["df"]["High"],
                low=r["df"]["Low"],
                close=r["df"]["Close"]
            )])
            fig.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# STOPKA
# ---------------------------------------------------------

st.markdown("<center><br><small style='color:#333;'>AI ALPHA MONSTER PRO v74 © 2026</small></center>", unsafe_allow_html=True)


