import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA ŚRODOWISKA
# ==============================================================================
DB_FILE = "moje_spolki.txt"
st.set_page_config(page_title="AI MONSTER v80 COMPACT", page_icon="🚜", layout="wide")

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read().strip()
        except: pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX"

# ==============================================================================
# 2. STYLIZACJA COMPACT (Zmniejszone okna i czcionki)
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .compact-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 15px; border-radius: 12px; border: 1px solid #30363d; 
        margin-bottom: 15px; min-height: 650px; width: 100%;
        transition: 0.2s;
    }
    .buy { border-left: 4px solid #00ff88; }
    .sell { border-left: 4px solid #ff4b4b; }
    .hold { border-left: 4px solid #8b949e; }
    
    .n-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .n-val { font-size: 0.95rem; font-weight: 700; color: #ffffff; display: block; margin-bottom: 4px; }
    
    .metric-grid { 
        display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; 
        margin: 10px 0; background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px;
    }
    
    .pos-mini-box {
        background: rgba(88, 166, 255, 0.05); padding: 10px; 
        border-radius: 8px; border: 1px solid #58a6ff; margin: 10px 0; text-align: center;
    }
    .sig-mini { font-weight: 900; font-size: 1rem; }
    .block-container { max-width: 98% !important; padding-top: 1rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK ANALITYCZNY (WSZYSTKIE DANE)
# ==============================================================================
def fetch_data(symbol):
    try:
        time.sleep(0.1)
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df = t.history(period="2y", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 150: return None
        
        c = df['Close'].replace(0, np.nan).ffill()
        curr = c.iloc[-1]
        
        # Wskaźniki
        s50, s200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        delta = c.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (g / (l + 1e-9)))).iloc[-1]
        
        exp1 = c.ewm(span=12).mean(); exp2 = c.ewm(span=26).mean(); macd = (exp1 - exp2).iloc[-1]
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        h52, l52 = df['High'].tail(252).max(), df['Low'].tail(252).min()
        
        # ATR i Pozycja
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        sh = int((st.session_state.risk_cap * (st.session_state.risk_pct / 100)) / (atr * 1.5)) if atr > 0 else 0
        
        v_text, v_class = ("KUP", "buy") if rsi < 35 else ("SPRZEDAJ", "sell") if rsi > 65 else ("CZEKAJ", "hold")
        
        # Formacja
        last = df.iloc[-1]; body = abs(last['Open'] - last['Close'])
        pattern = "DOJI" if body < (last['High'] - last['Low']) * 0.1 else "STANDARD"

        return {
            "s": s, "p": curr, "rsi": rsi, "macd": macd, "pp": pp, "h52": h52, "l52": l52,
            "sh": sh, "sl": curr-(atr*1.5), "tp": curr+(atr*3.5), "s50": s50, "s200": s200,
            "df": df.tail(40), "v": v_text, "vc": v_class, "pat": pattern, "news": t.news[:2]
        }
    except: return None

def get_ai_response(r):
    if not client: return "Brak klucza."
    try:
        p = f"Analiza {r['s']}: Cena {r['p']:.2f}, RSI {r['rsi']:.1f}, SMA200 {r['s200']:.2f}. Podaj SL/TP i plan."
        return client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":p}], max_tokens=200).choices[0].message.content
    except: return "AI błąd."

# ==============================================================================
# 4. INTERFEJS I WYŚWIETLANIE (Lista bez grup)
# ==============================================================================
with st.sidebar:
    st.title("🚜 MONSTER v80")
    refresh_val = st.slider("Refresh (min):", 1, 15, 5)
    st_autorefresh(interval=refresh_val * 60000, key="global_refresh")
    t_in = st.text_area("Symbole:", load_tickers(), height=200)
    st.session_state.risk_cap = st.number_input("Kapitał:", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct)
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in); st.rerun()

symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

with ThreadPoolExecutor(max_workers=10) as exe:
    results = [r for r in list(exe.map(fetch_data, symbols)) if r]

st.subheader(f"🚜 Kombajn: {len(results)} spółek (Pełna Lista)")

cols = st.columns(3)
for idx, r in enumerate(results):
    with cols[idx % 3]:
        with st.container():
            st.markdown(f"""
            <div class="compact-card {r['vc']}">
                <div style="display:flex; justify-content:space-between;">
                    <b>{r['s']}</b><span class="sig-mini" style="color:{'#00ff88' if r['vc']=='buy' else '#ff4b4b' if r['vc']=='sell' else '#8b949e'}">{r['v']}</span>
                </div>
                <h2 style="color:#58a6ff; margin:5px 0;">{r['p']:.4f}</h2>
                
                <div class="pos-mini-box">
                    <span class="n-label">Sugerowana Pozycja</span>
                    <b style="font-size:1.2rem; color:#58a6ff;">{r['sh']} SZT.</b><br>
                    <small>SL: {r['sl']:.2f} | TP: {r['tp']:.2f}</small>
                </div>

                <div class="metric-grid">
                    <div><span class="n-label">RSI</span><span class="n-val">{r['rsi']:.1f}</span></div>
                    <div><span class="n-label">MACD</span><span class="n-val">{r['macd']:.2f}</span></div>
                    <div><span class="n-label">SMA200</span><span class="n-val">{r['s200']:.2f}</span></div>
                    <div><span class="n-label">Pivot</span><span class="n-val">{r['pp']:.2f}</span></div>
                    <div><span class="n-label">Max 52T</span><span class="n-val">{r['h52']:.2f}</span></div>
                    <div><span class="n-label">Świeca</span><span class="n-val">{r['pat']}</span></div>
                </div>
            """, unsafe_allow_html=True)
            
            fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=220, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"c_{r['s']}")
            
            if st.button(f"AI Analiza {r['s']}", key=f"a_{r['s']}"):
                st.info(get_ai_response(r))
            
            for n in r['news']:
                st.markdown(f"<small style='font-size:0.7rem;'>• <a href='{n.get('link','#')}'>{n.get('title','News')[:40]}...</a></small>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
