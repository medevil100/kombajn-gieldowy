import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
import time
import os
from datetime import datetime

# --- 1. CONFIG & CACHE ---
st.set_page_config(page_title="AI MONSTER v101 SAFE", layout="wide")
DB_FILE = "moje_spolki.txt"

# Funkcja cache'ująca pobieranie danych na 5 minut (kluczowe, by nie dostać bana)
@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        time.sleep(0.4) # Bezpieczny odstęp czasowy
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="2y", interval="1d", auto_adjust=False)
        if df.empty or len(df) < 150: return None
        
        df['Close'] = df['Close'].replace(0, np.nan).ffill()
        c = df['Close']
        curr = float(c.iloc[-1])
        
        # Wskaźniki
        s20, s50, s100, s200 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1], c.rolling(100).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        delta = c.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (g / (l + 1e-12)))).iloc[-1]
        e12 = c.ewm(span=12).mean(); e26 = c.ewm(span=26).mean(); macd = (e12 - e26).iloc[-1]
        
        # Pivot i Ekstrema
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        h52, l52 = df['High'].tail(252).max(), df['Low'].tail(252).min()
        
        # Risk ATR
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        return {
            "s": symbol.upper(), "p": curr, "rsi": rsi, "macd": macd, "pp": pp, "h52": h52, "l52": l52,
            "s50": s50, "s200": s200, "atr": atr, "df": df.tail(60), "news": t.news[:2]
        }
    except: return None

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; }
    .monster-card { 
        background: #0d1117; padding: 20px; border-radius: 12px; 
        border: 1px solid #30363d; margin-bottom: 20px; min-height: 800px;
    }
    .buy { border-top: 4px solid #00ff88; } .sell { border-top: 4px solid #ff4b4b; }
    .q-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; }
    .q-val { font-size: 1.1rem; font-weight: bold; color: #ffffff; display: block; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. UI ---
with st.sidebar:
    st.title("🚜 MONSTER v101")
    t_in = st.text_area("Symbole (CSV):", "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX, CMMB, DRMA", height=200)
    kapital = st.number_input("Kapitał PLN", value=10000.0)
    ryzyko = st.slider("Ryzyko %", 0.1, 5.0, 1.0)
    if st.button("💾 START ANALIZY"):
        st.cache_data.clear()
        st.rerun()

symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
st.subheader(f"🚜 Kombajn: {len(symbols)} spółek")

# Pasek postępu (Yahoo nie lubi spamu, więc lecimy pętlą)
progress = st.progress(0)
all_results = []
for i, sym in enumerate(symbols):
    data = get_stock_data(sym)
    if data: all_results.append(data)
    progress.progress((i + 1) / len(symbols))

# --- 4. RENDER ---
cols = st.columns(3)
for idx, r in enumerate(all_results):
    with cols[idx % 3]:
        sh = int((kapital * (ryzyko / 100)) / (r['atr'] * 1.5)) if r['atr'] > 0 else 0
        v_txt, v_cls = ("KUP", "buy") if r['rsi'] < 35 else ("SPRZEDAJ", "sell") if r['rsi'] > 65 else ("HOLD", "hold")
        
        st.markdown(f"""
        <div class="monster-card {v_cls}">
            <h2 style="margin:0;">{r['s']} | {v_txt}</h2>
            <h1 style="color:#58a6ff;">{r['p']:.6f}</h1>
            <div style="background:rgba(88,166,255,0.1); padding:10px; border-radius:8px;">
                <small>POZYCJA: <b>{sh} SZT</b></small><br>
                <small>SL: {r['p']-(r['atr']*1.5):.6f} | TP: {r['p']+(r['atr']*3):.6f}</small>
            </div>
            <div class="metric-grid">
                <div><span class="q-label">RSI</span><span class="q-val">{r['rsi']:.1f}</span></div>
                <div><span class="q-label">MACD</span><span class="q-val">{r['macd']:.4f}</span></div>
                <div><span class="q-label">SMA200</span><span class="q-val">{r['s200']:.4f}</span></div>
                <div><span class="q-label">PIVOT</span><span class="q-val">{r['pp']:.4f}</span></div>
                <div><span class="q-label">MAX 52T</span><span class="q-val">{r['h52']:.4f}</span></div>
                <div><span class="q-label">MIN 52T</span><span class="q-val">{r['l52']:.4f}</span></div>
            </div>
        """, unsafe_allow_html=True)
        
        fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True, key=f"c_{r['s']}")
        st.markdown("</div>", unsafe_allow_html=True)
