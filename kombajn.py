import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA ŚRODOWISKA
# ==============================================================================
st.set_page_config(page_title="AI ALPHA MONSTER v75 ULTRA", page_icon="🚜", layout="wide")
DB_FILE = "moje_spolki.txt"

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "NVDA, TSLA, BTC-USD, AAPL"
        except: pass
    return "NVDA, TSLA, BTC-USD, AAPL"

# ==============================================================================
# 2. STABILNE STYLE CSS (NEON ULTRA WIDE)
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; }
    .neon-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 35px; border-radius: 20px; border: 1px solid #30363d; 
        margin-bottom: 25px; min-height: 800px; width: 100%;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); }
    .neon-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; display: block; }
    .neon-value { font-size: 1.1rem; font-weight: bold; color: #ffffff; margin-bottom: 10px; display: block; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK ANALITYCZNY (ZABEZPIECZONY)
# ==============================================================================
def fetch_monster_analysis(symbol):
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df = t.history(period="2y", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 150: return None
        
        close = df['Close']
        # Wskaźniki
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (close.diff().where(close.diff() > 0, 0).rolling(14).mean() / 
               close.diff().where(close.diff() < 0, 0).abs().rolling(14).mean()))).iloc[-1]
        
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        atr = (df['High']-df['Low']).rolling(14).mean().iloc[-1]
        
        sh = int((st.session_state.risk_cap * (st.session_state.risk_pct / 100)) / (atr * 1.5)) if atr > 0 else 0
        v_text, v_class = ("KUP 🔥", "buy") if rsi < 35 else ("SPRZEDAJ ⚠️", "sell") if rsi > 65 else ("TRZYMAJ ⏳", "hold")
        
        # Bezpieczne newsy
        news = []
        try:
            for n in t.news[:3]:
                title = n.get('title')
                if title: news.append({"t": str(title)[:55], "l": n.get('link', '#')})
        except: pass

        return {
            "s": s, "p": close.iloc[-1], "rsi": rsi, "pp": pp, "sh": sh,
            "sl": close.iloc[-1] - (atr * 1.5), "tp": close.iloc[-1] + (atr * 3), 
            "s50": sma50, "s200": sma200, "df": df.tail(60), "v": v_text, "vc": v_class, "news": news
        }
    except: return None

def get_ai_strategy(r):
    if not client: return "Brak klucza OpenAI."
    try:
        resp = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": f"Analiza {r['s']}: Cena {r['p']:.2f}, RSI {r['rsi']:.1f}. Podaj SL, TP i strategię 3 pkt. Konkret."}],
            max_tokens=500
        )
        return resp.choices.message.content
    except: return "Błąd AI."

# ==============================================================================
# 4. INTERFEJS GŁÓWNY (SYSTEM ZAKŁADEK)
# ==============================================================================
with st.sidebar:
    st.title("🚜 MONSTER v75 ULTRA")
    t_in = st.text_area("Symbole (CSV):", load_tickers(), height=250)
    st.session_state.risk_cap = st.number_input("Kapitał (PLN):", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct)
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

# Podział na grupy po 6 spółek za pomocą TABS (rozwiązuje błąd removeChild i Paginacji)
num_groups = (len(symbols) // 6) + (1 if len(symbols) % 6 > 0 else 0)
tabs = st.tabs([f"Grupa {i+1}" for i in range(num_groups)]) if symbols else []

for i, tab in enumerate(tabs):
    with tab:
        batch = symbols[i*6 : (i+1)*6]
        with ThreadPoolExecutor(max_workers=6) as exe:
            results = [r for r in list(exe.map(fetch_monster_analysis, batch)) if r]
        
        cols = st.columns(3)
        for idx, r in enumerate(results):
            with cols[idx % 3]:
                st.markdown(f"""<div class='neon-card {r["vc"]}'>
                    <h3 style='margin:0;'>{r['s']} | {r['v']}</h3>
                    <h2 style='color:#58a6ff; margin:10px 0;'>{r['p']:.2f} USD</h2>
                    <div class='metric-grid'>
                        <div><span class='neon-label'>RSI</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                        <div><span class='neon-label'>Pivot</span><span class='neon-value'>{r['pp']:.2f}</span></div>
                        <div><span class='neon-label'>SMA 50</span><span class='neon-value'>{r['s50']:.2f}</span></div>
                        <div><span class='neon-label'>SMA 200</span><span class='neon-value'>{r['s200']:.2f}</span></div>
                    </div>
                    <div style='background:rgba(88,166,255,0.1); padding:15px; border-radius:12px; margin-bottom:15px;'>
                        <b>Pozycja: {r['sh']} szt.</b><br>
                        <small style='color:#ff4b4b;'>SL: {r['sl']:.2f}</small> | <small style='color:#00ff88;'>TP: {r['tp']:.2f}</small>
                    </div>
                """, unsafe_allow_html=True)
                
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}_{i}")
                
                if st.button(f"🤖 RAPORT AI {r['s']}", key=f"ai_{r['s']}_{i}"):
                    st.info(get_ai_strategy(r))
                
                for n in r['news']:
                    st.markdown(f"• [{n['t']}...]({n['l']})")
                st.markdown("</div>", unsafe_allow_html=True)
