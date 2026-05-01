import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="NEON COMMANDER v102", page_icon="⚡", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "full_analysis" not in st.session_state: st.session_state.full_analysis = {}
if "risk_cap_pln" not in st.session_state: st.session_state.risk_cap_pln = 40000.0

DB_FILE = "moje_spolki.txt"

# --- 2. STYLE NEONOWE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; min-height: 100px; }
    .calc-box { background: rgba(0, 255, 136, 0.1); border: 1px solid #00ff88; padding: 10px; border-radius: 5px; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 3. SILNIK DANYCH (POPRAWIONY) ---
def get_usdpln():
    try:
        # Pobieramy najbardziej aktualną cenę USDPLN
        ticker = yf.Ticker("USDPLN=X")
        return float(ticker.fast_info['last_price'])
    except: return 4.0

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        # Pobieramy historię do wykresu i RSI
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        
        # POPRAWKA: Pobieranie ceny LIVE zamiast historycznej ceny zamknięcia
        current_price = t.fast_info['last_price']
        
        # Pobieranie realnego Bid/Ask jeśli dostępne, inaczej symulacja spreadu 0.05%
        bid = t.info.get('bid', current_price * 0.9995)
        ask = t.info.get('ask', current_price * 1.0005)
        
        # RSI i Trendy (na bazie DF)
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        trends = {"K": "UP" if current_price > sma20 else "DN", "S": "UP" if current_price > sma50 else "DN"}

        return {
            "symbol": symbol.upper(), "price": current_price, "bid": bid, "ask": ask, "rsi": rsi, 
            "trends": trends, "df": df.tail(45)
        }
    except Exception as e:
        return None

# --- 4. PANEL BOCZNY ---
usd_pln_rate = get_usdpln()

with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    st.session_state.risk_cap_pln = st.number_input("💵 Twój Kapitał (PLN):", value=float(st.session_state.risk_cap_pln))
    risk_per_trade_pct = st.slider("🎯 Ryzyko na 1 transakcję (%)", 1.0, 100.0, 10.0)
    
    # Obliczamy ile PLN chcemy wydać na jedną spółkę
    amount_per_trade_pln = st.session_state.risk_cap_pln * (risk_per_trade_pct / 100)
    st.info(f"Budżet na spółkę: {amount_per_trade_pln:.2f} PLN")

    refresh_min = st.slider("⏱️ Odświeżanie (min)", 1, 10, 1)
    st_autorefresh(interval=refresh_min * 60 * 1000, key="auto_ref")
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers)
    if st.button("🚀 SKANUJ"):
        st.session_state.ai_results = {}
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

# --- 5. LOGIKA GŁÓWNA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
for sym in symbols:
    d = get_data(sym)
    if d:
        # KALKULACJA ILOŚCI AKCJI
        # Cena akcji w PLN = Cena USD * Kurs USDPLN
        price_in_pln = d['ask'] * usd_pln_rate
        quantity = int(amount_per_trade_pln / price_in_pln) if price_in_pln > 0 else 0
        
        st.markdown(f'<div class="neon-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 3, 2])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            st.markdown(f"CENA: **{d['price']:.2f} USD**")
            st.markdown(f"<span style='color:#00ff88'>BID: {d['bid']:.2f}</span> | <span style='color:#ff4b4b'>ASK: {d['ask']:.2f}</span>", unsafe_allow_html=True)
            st.write(f"RSI: {d['rsi']:.1f}")
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=180, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{d['symbol']}")
            
        with c3:
            st.markdown(f'<div class="calc-box">', unsafe_allow_html=True)
            st.markdown("**KALKULATOR POZYCJI**")
            st.write(f"Kurs USD/PLN: {usd_pln_rate:.4f}")
            st.write(f"Koszt 1 akcji: {price_in_pln:.2f} PLN")
            st.markdown(f"### DO KUPNA: <span style='color:#00ff88'>{quantity} szt.</span>", unsafe_allow_html=True)
            st.markdown(f"<small>Łączny koszt: {quantity * price_in_pln:.2f} PLN</small>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
