import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from openai import OpenAI
from email.mime.text import MIMEText
import smtplib
import requests

# ============================================================
# ULTRA ENGINE v6.0 — FIXED & CLEAN
# ============================================================

st.set_page_config(
    layout="wide",
    page_title="ULTRA ENGINE v6.0 — THE SWORD",
    page_icon="⚔️"
)

# ----------------- STYLE -----------------
st.markdown("""
<style>
body { background-color: #030308; color: #d0d0ff; }
.stApp { background-color: #030308; }
.mega-card { border: 2px solid #111; padding: 30px; border-radius: 20px; background: #050a0f; box-shadow: 0 0 25px #00ff8822; margin-bottom: 30px; }
.neon-title { color: #00ff88; font-weight: bold; font-size: 3.0rem; text-shadow: 0 0 15px #00ff88; }
.signal-BUY { color: #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 10px; border-radius: 10px; }
.signal-SELL { color: #ff4444; font-weight: bold; border: 2px solid #ff4444; padding: 10px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# CLIENTS / SECRETS
# ============================================================

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ============================================================
# DATA ENGINE (YFINANCE - NO KEY REQUIRED)
# ============================================================

def get_data_daily(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")
        if df.empty: return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        return df
    except: return pd.DataFrame()

def get_data_intraday(symbol, interval="5m"):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval=interval)
        if df.empty: return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        return df
    except: return pd.DataFrame()

# ============================================================
# INDICATORS & CALCULATIONS
# ============================================================

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calc_macd(series):
    exp1 = series.ewm(span=12, adjust=False).mean()
    exp2 = series.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal, macd - signal

def get_indicators(df):
    if df.empty or len(df) < 50: return None
    close = df['close']
    macd, sig, hist = calc_macd(close)
    rsi = calc_rsi(close)
    ma20, ma50, ma200 = close.rolling(20).mean(), close.rolling(50).mean(), close.rolling(200).mean()
    
    return {
        "trend_s": "UP" if close.iloc[-1] > ma20.iloc[-1] else "DOWN",
        "trend_m": "UP" if close.iloc[-1] > ma50.iloc[-1] else "DOWN",
        "trend_l": "UP" if close.iloc[-1] > ma200.iloc[-1] else "DOWN",
        "rsi": round(rsi.iloc[-1], 2),
        "macd_hist": round(hist.iloc[-1], 4),
        "vol": round(df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1], 2),
        "price": round(close.iloc[-1], 2)
    }

# ============================================================
# SIGNALS & AI
# ============================================================

def ai_signal_engine(r):
    score = 0
    score += 1 if r["trend_s"] == "UP" else -1
    score += 2 if r["trend_m"] == "UP" else -2
    score += 3 if r["trend_l"] == "UP" else -3
    score += 2 if r["macd_hist"] > 0 else -2
    if r["rsi"] < 30: score += 2
    elif r["rsi"] > 70: score -= 2
    
    if score >= 4: return "BUY", score
    if score <= -3: return "SELL", score
    return "WATCH", score

def genesis_ai(prompt):
    if not client: return "Brak klucza OpenAI."
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Analizuj krótko i konkretnie."}, {"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content
    except Exception as e: return f"Błąd AI: {e}"

# ============================================================
# MAIN APP INTERFACE
# ============================================================

st.markdown('<div class="neon-title">ULTRA ENGINE v6.0</div>', unsafe_allow_html=True)

target_symbol = st.sidebar.text_input("SYMBOL (np. AAPL, TSLA, NVDA)", "NVDA").upper()

if st.button("URUCHOM ANALIZĘ"):
    with st.spinner("Pobieranie danych..."):
        df_daily = get_data_daily(target_symbol)
        
        if not df_daily.empty:
            stats = get_indicators(df_daily)
            if stats:
                sig, score = ai_signal_engine(stats)
                
                col1, col2, col3 = st.columns(3)
                col1.metric("CENA", f"${stats['price']}")
                col2.metric("RSI", stats['rsi'])
                col3.markdown(f"### SYGNAŁ: <span class='signal-{sig}'>{sig} ({score})</span>", unsafe_allow_html=True)
                
                st.subheader("🤖 Analiza Genesis AI")
                ai_prompt = f"Oto dane dla {target_symbol}: RSI {stats['rsi']}, Trendy: {stats['trend_s']}/{stats['trend_m']}/{stats['trend_l']}. Czy to dobry moment na wejście?"
                st.info(genesis_ai(ai_prompt))
                
                st.line_chart(df_daily['close'].tail(100))
            else:
                st.error("Zbyt mało danych historycznych dla tego symbolu.")
        else:
            st.error("Nie znaleziono symbolu lub błąd połączenia.")

# Heatmapa Sektorów
st.divider()
st.subheader("🌍 Sentyment Sektorów (Top Spółki)")
cols = st.columns(4)
for i, (sector, syms) in enumerate({"TECH": "AAPL", "CHIPS": "NVDA", "AUTO": "TSLA", "E-COM": "AMZN"}.items()):
    d = get_data_daily(syms)
    if not d.empty:
        change = round(((d['close'].iloc[-1] - d['close'].iloc[-2]) / d['close'].iloc[-2]) * 100, 2)
        cols[i].metric(sector, syms, f"{change}%")
