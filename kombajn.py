import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA ŚRODOWISKA
# ==============================================================================
st.set_page_config(page_title="AI ALPHA MONSTER v75 ULTRA", page_icon="🚜", layout="wide")
DB_FILE = "moje_spolki.txt"

# Klucz OpenAI ze skrytki Streamlit
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

# Inicjalizacja stanów sesji
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read().strip()
    return "ADTX, ACRS, ALZN, ANIX, ATHE, AURA, APM, BBI, BCTX, BDRX, BNOX, BOLT, BTTX, CMMB, CRVS, DRMA, ENLV, EVOK, GHSI, HILS, IMUX, IMNN, INAB, INFI, KTRA, MBIO, MNOV, MREO, NRSN, ONCS, PALI, PBYI, PGEN, RGLS, SABS, SLS, SLNO, TCON, TTOO, VINC, VIRI, XLO, PLRX, IOVA, HUMA, GOSS, FATE, LV"

# ==============================================================================
# 2. POTĘŻNY SYSTEM STYLÓW NEON PRO (Fix Rozmiaru)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    .neon-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; border-radius: 25px; border: 1px solid #30363d; 
        margin-bottom: 35px; min-height: 950px; width: 100%;
        transition: 0.3s ease-in-out;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 20px rgba(0,255,136,0.2); }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 20px rgba(255,75,75,0.2); }
    .hold { border: 1px solid #30363d !important; }
    
    .neon-label { font-size: 0.85rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1.5px; display: block; }
    .neon-value { font-size: 1.2rem; font-weight: 900; color: #ffffff; margin-bottom: 10px; display: block; }
    
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }
    .ai-box { background: rgba(0, 255, 136, 0.05); border: 1px solid rgba(0, 255, 136, 0.2); padding: 15px; border-radius: 12px; font-size: 0.9rem; text-align: left; }
    
    .block-container { max-width: 98% !important; padding-top: 1.5rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK ANALITYCZNY (WSZYSTKIE WSKAŹNIKI)
# ==============================================================================
def fetch_monster_analysis(symbol):
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        # Pobieramy 2 lata dla SMA 200
        df = t.history(period="2y", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        c = df['Close']
        curr = c.iloc[-1]
        
        # Średnie
        s20, s50, s100, s200 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1], c.rolling(100).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        
        # RSI & MACD
        delta = c.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (g / (l + 1e-9)))).iloc[-1]
        exp1 = c.ewm(span=12).mean(); exp2 = c.ewm(span=26).mean(); macd = (exp1 - exp2).iloc[-1]
        
        # Pivot & Ekstrema
        prev = df.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        h52, l52 = df['High'].tail(252).max(), df['Low'].tail(252).min()
        
        # Risk Management (ATR)
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sh = int(risk_cash / (atr * 1.5)) if atr > 0 else 0

        # Werdykt
        v_text, v_class = ("KUP 🔥", "buy") if rsi < 35 else ("SPRZEDAJ ⚠️", "sell") if rsi > 65 else ("TRZYMAJ ⏳", "hold")

        return {
            "s": s, "p": curr, "rsi": rsi, "macd": macd, "pivot": pivot, "h52": h52, "l52": l52,
            "sh": sh, "sl": curr-(atr*1.5), "tp": curr+(atr*3.5), "s20": s20, "s50": s50, "s100": s100, "s200": s200,
            "news": t.news[:2], "df": df.tail(80), "v": v_text, "vc": v_class
        }
    except: return None

def get_ai_strategy(r):
    if not client: return "Brak klucza OpenAI."
    prompt = f"Analiza {r['s']}: Cena {r['p']:.2f}, RSI {r['rsi']:.1f}, SMA200 {r['s200']:.2f}. Podaj SL, TP i 3 pkt strategii. Konkret, bez lania wody."
    try:
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=400)
        return response.choices[0].message.content
    except: return "Błąd AI."

# ==============================================================================
# 4. INTERFEJS I RENDEROWANIE (KOMBAJN)
# ==============================================================================
with st.sidebar:
    st.title("🚜 MONSTER v75")
    refresh_min = st.slider("Odświeżanie (min)", 1, 15, 5)
    st_autorefresh(interval=refresh_min * 60000, key="data_refresh")
    
    t_in = st.text_area("Symbole (CSV):", load_tickers(), height=250)
    st.session_state.risk_cap = st.number_input("Kapitał (PLN):", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

# Podział na strony (By uniknąć błędu removeChild przy 48 spółkach)
items_per_page = 6
page = st.sidebar.number_input("Strona (Paczki po 6 spółek)", 1, (len(symbols)//items_per_page)+1, 1)
start_idx = (page - 1) * items_per_page
current_batch = symbols[start_idx : start_idx + items_per_page]

st.subheader(f"🚜 Kombajn: Analiza {len(symbols)} spółek | Strona {page}")

with ThreadPoolExecutor(max_workers=10) as exe:
    results = [res for sym in current_batch if (res := fetch_monster_analysis(sym))]

cols = st.columns(3)
for idx, r in enumerate(results):
    with cols[idx % 3]:
        with st.container():
            st.markdown(f"""<div class='neon-card {r["vc"]}'>
                <h3 style='margin:0;'>{r['s']} | {r['v']}</h3>
                <h1 style='color:#58a6ff; margin:10px 0;'>{r['p']:.2f} <small style='font-size:1rem;'>USD</small></h1>
                <div class='metric-grid'>
                    <div><span class='neon-label'>RSI</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                    <div><span class='neon-label'>Pivot</span><span class='neon-value'>{r['pivot']:.2f}</span></div>
                    <div><span class='neon-label'>Max 52T</span><span class='neon-value'>{r['h52']:.2f}</span></div>
                    <div><span class='neon-label'>Min 52T</span><span class='neon-value'>{r['l52']:.2f}</span></div>
                    <div><span class='neon-label'>SMA 50</span><span class='neon-value'>{r['s50']:.2f}</span></div>
                    <div><span class='neon-label'>SMA 200</span><span class='neon-value'>{r['s200']:.2f}</span></div>
                </div>
                <div style='background:rgba(88,166,255,0.1); padding:15px; border-radius:12px; margin-bottom:15px;'>
                    <b>Pozycja: {r['sh']} szt.</b><br>
                    <small style='color:#ff4b4b;'>SL: {r['sl']:.2f}</small> | <small style='color:#00ff88;'>TP: {r['tp']:.2f}</small>
                </div>
            """, unsafe_allow_html=True)
            
            # Wykres
            fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}_{page}")
            
            if st.button(f"🤖 RAPORT AI {r['s']}", key=f"ai_{r['s']}"):
                st.info(get_ai_strategy(r))
            
            for n in r['news']:
                st.markdown(f"• [{n.get('title')[:55]}...]({n.get('link')})")
            st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<center><small>AI ALPHA MONSTER v75 ULTRA © 2026</small></center>", unsafe_allow_html=True)
