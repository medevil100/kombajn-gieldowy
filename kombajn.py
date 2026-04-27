import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
import time
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA I TOTALNY RESET
# ==============================================================================
st.set_page_config(page_title="AI MONSTER v90 FINAL", layout="wide")

DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read().strip()
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX, CMMB, DRMA, EVOK"

# ==============================================================================
# 2. STABILNE STYLE CSS (WIDOK CIĄGŁY)
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; }
    .monster-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; 
        margin-bottom: 25px; min-height: 1000px; width: 100%;
    }
    .buy-line { border-top: 5px solid #00ff88; }
    .sell-line { border-top: 5px solid #ff4b4b; }
    .hold-line { border-top: 5px solid #30363d; }
    .q-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; }
    .q-val { font-size: 1.1rem; font-weight: 800; color: #ffffff; display: block; margin-bottom: 8px; }
    .m-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }
    .sh-box { background: rgba(88, 166, 255, 0.1); padding: 15px; border-radius: 10px; text-align: center; border: 1px solid #58a6ff; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. PANCERNY SILNIK POBIERANIA (FIX NAZWY I NaN)
# ==============================================================================
def fetch_data_engine(symbol):
    try:
        # Bardzo ważne: mały delay, by Yahoo nas nie wyrzuciło
        time.sleep(random.uniform(0.1, 0.3))
        s = symbol.strip().upper()
        if not s: return None
        
        t = yf.Ticker(s)
        # Pobieranie RAW (Precyzja dla Penny Stocks)
        df = t.history(period="1y", interval="1d", auto_adjust=False)
        
        if df.empty or len(df) < 30: return None
        
        # Naprawa cen groszowych
        df['Close'] = df['Close'].replace(0, np.nan).ffill()
        c = df['Close']
        curr = float(c.iloc[-1])
        
        # Średnie
        s50 = c.rolling(50).mean().iloc[-1]
        s200 = c.rolling(200).mean().iloc[-1] if len(c) > 200 else s50
        
        # RSI 14
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-12)))).iloc[-1]
        
        # Pivot i ATR
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        h52, l52 = df['High'].max(), df['Low'].min()
        
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Pozycja
        risk = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sh = int(risk / (atr * 1.5)) if atr > 0 else 0
        
        v_txt, v_cls = ("KUP 🔥", "buy-line") if rsi < 35 else ("SPRZEDAJ ⚠️", "sell-line") if rsi > 65 else ("TRZYMAJ ⏳", "hold-line")

        return {
            "s": s, "p": curr, "rsi": rsi, "pp": pp, "h52": h52, "l52": l52, "sh": sh,
            "sl": curr - (atr * 1.5), "tp": curr + (atr * 3.5), "s50": s50, "s200": s200,
            "df": df.tail(60), "v": v_txt, "vc": v_cls
        }
    except:
        return None

# ==============================================================================
# 4. INTERFEJS I PĘTLA RENDERUJĄCA (DOKOŃCZONA)
# ==============================================================================
with st.sidebar:
    st.title("🚜 MONSTER v90 FINAL")
    st_autorefresh(interval=300000, key="fsh")
    
    t_in = st.text_area("Symbole (CSV):", load_tickers(), height=250)
    st.session_state.risk_cap = st.number_input("Kapitał PLN", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko %", 0.1, 5.0, st.session_state.risk_pct)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

# Pobieranie danych - używamy nazwy funkcji fetch_data_engine
with ThreadPoolExecutor(max_workers=8) as exe:
    results = [r for r in list(exe.map(fetch_data_engine, symbols)) if r]

st.subheader(f"🚜 Aktywne spółki: {len(results)} z {len(symbols)}")

if not results:
    st.error("Błąd: Serwer Yahoo Finance tymczasowo zablokował zapytania lub symbole są błędne. Spróbuj za 1 minutę.")

# Renderowanie - 3 KOLUMNY, ZERO GRUP
cols = st.columns(3)
for idx, r in enumerate(results):
    with cols[idx % 3]:
        with st.container():
            st.markdown(f"""
            <div class="monster-card {r['vc']}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:1.6rem; font-weight:900;">{r['s']}</span>
                    <span style="font-weight:900; opacity:0.8;">{r['v']}</span>
                </div>
                <h1 style="color:#58a6ff; font-size:3.2rem; margin:10px 0;">{r['p']:.6f}</h1>
                
                <div class="sh-box">
                    <span class="q-label">Wielkość Pozycji</span>
                    <span style="font-size:1.8rem; font-weight:900; color:#ffffff;">{r['sh']} SZT.</span><br>
                    <small style="color:#ff4b4b;">SL: {r['sl']:.6f}</small> | <small style="color:#00ff88;">TP: {r['tp']:.6f}</small>
                </div>

                <div class="m-grid">
                    <div><span class="q-label">RSI (14)</span><span class="q-val">{r['rsi']:.1f}</span></div>
                    <div><span class="q-label">Pivot</span><span class="q-val">{r['pp']:.4f}</span></div>
                    <div><span class="q-label">SMA 50</span><span class="q-val">{r['s50']:.4f}</span></div>
                    <div><span class="q-label">SMA 200</span><span class="q-val">{r['s200']:.4f}</span></div>
                    <div><span class="q-label">Max 52T</span><span class="q-val">{r['h52']:.4f}</span></div>
                    <div><span class="q-label">Min 52T</span><span class="q-val">{r['l52']:.4f}</span></div>
                </div>
            """, unsafe_allow_html=True)
            
            fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True, key=f"c_{r['s']}_{idx}")
            
            if client and st.button(f"🤖 ANALIZA AI {r['s']}", key=f"ai_{r['s']}_{idx}"):
                p = f"Analiza {r['s']}: Cena {r['p']:.6f}, RSI {r['rsi']:.1f}. Podaj SL/TP i plan 3 pkt."
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":p}])
                st.info(res.choices[0].message.content)
            
            st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<center><small style='color:#444;'>AI ALPHA MONSTER PRO v90 FINAL © 2026</small></center>", unsafe_allow_html=True)
