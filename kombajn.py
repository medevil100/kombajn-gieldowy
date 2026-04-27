import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
import time
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA I PANCERNE POBIERANIE (FINAL PRO)
# ==============================================================================
st.set_page_config(page_title="AI ALPHA MONSTER v100", page_icon="🚜", layout="wide")

DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# Stabilizacja sesji Yahoo
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read().strip()
        except: pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX, CMMB, DRMA"

# CSS NEON PRO (Maksymalna szerokość i stabilność)
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .monster-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        margin-bottom: 35px; min-height: 1150px; width: 100%;
        transition: 0.3s;
    }
    .buy { border-top: 5px solid #00ff88; box-shadow: 0 5px 20px rgba(0,255,136,0.1); }
    .sell { border-top: 5px solid #ff4b4b; box-shadow: 0 5px 20px rgba(255,75,75,0.1); }
    .hold { border-top: 5px solid #30363d; }
    .n-label { font-size: 0.85rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; display: block; }
    .n-val { font-size: 1.2rem; font-weight: 900; color: #ffffff; margin-bottom: 10px; display: block; }
    .m-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }
    .pos-box { background: rgba(88, 166, 255, 0.08); padding: 20px; border-radius: 15px; border: 1px solid #58a6ff; text-align: center; }
    .block-container { max-width: 98% !important; padding-top: 1rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. SILNIK ANALITYCZNY (WSZYSTKIE DANE TECHNICZNE)
# ==============================================================================
def fetch_ticker_full(symbol):
    try:
        time.sleep(0.15) # Ochrona przed banem
        s = symbol.strip().upper()
        t = yf.Ticker(s, session=session)
        
        # Pobieramy 2 lata dla SMA 200
        df = t.history(period="2y", interval="1d", auto_adjust=False)
        if df.empty or len(df) < 150: return None
        
        df['Close'] = df['Close'].replace(0, np.nan).ffill()
        c = df['Close']
        curr = float(c.iloc[-1])
        
        # Średnie
        s20, s50, s100, s200 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1], c.rolling(100).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        
        # RSI 14
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-12)))).iloc[-1]
        
        # MACD
        e12 = c.ewm(span=12).mean(); e26 = c.ewm(span=26).mean(); macd = (e12 - e26).iloc[-1]
        
        # Pivot & ATR
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        h52, l52 = df['High'].tail(252).max(), df['Low'].tail(252).min()
        
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        risk = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sh = int(risk / (atr * 1.5)) if atr > 0 else 0
        
        v_txt, v_cls = ("KUP 🔥", "buy") if rsi < 35 else ("SPRZEDAJ ⚠️", "sell") if rsi > 65 else ("TRZYMAJ ⏳", "hold")

        news = []
        try:
            for n in t.news[:2]: news.append({"t": n.get('title')[:55], "l": n.get('link')})
        except: pass

        return {
            "s": s, "p": curr, "rsi": rsi, "macd": macd, "pp": pp, "h52": h52, "l52": l52,
            "sh": sh, "sl": curr - (atr * 1.5), "tp": curr + (atr * 3.5),
            "s20": s20, "s50": s50, "s100": s100, "s200": s200, "atr": atr,
            "df": df.tail(80), "v": v_txt, "vc": v_cls, "news": news
        }
    except: return None

# ==============================================================================
# 3. UI I RENDEROWANIE (GRID 3-KOLUMNOWY)
# ==============================================================================
def main():
    with st.sidebar:
        st.title("🚜 MONSTER v100")
        st.write(f"Zegar: {datetime.now().strftime('%H:%M:%S')}")
        st_autorefresh(interval=300000, key="global_refresh")
        
        t_in = st.sidebar.text_area("Symbole (CSV):", load_tickers(), height=250)
        st.session_state.risk_cap = st.number_input("Kapitał (PLN):", value=st.session_state.risk_cap)
        st.session_state.risk_pct = st.slider("Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct)
        
        if st.button("💾 ZAPISZ I ANALIZUJ"):
            with open(DB_FILE, "w") as f: f.write(t_in)
            st.rerun()

    symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
    
    # Wielowątkowość z ograniczeniem by nie banowali IP
    with ThreadPoolExecutor(max_workers=5) as exe:
        results = [r for r in list(exe.map(fetch_ticker_full, symbols)) if r]

    st.subheader(f"🚜 Analiza: {len(results)} spółek (Pełny Widok)")

    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"""
                <div class="monster-card {r['vc']}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:1.6rem; font-weight:900;">{r['s']}</span>
                        <span style="font-weight:900; color:{'#00ff88' if r['vc']=='buy' else '#ff4b4b' if r['vc']=='sell' else '#8b949e'}">{r['v']}</span>
                    </div>
                    <h1 style="color:#58a6ff; font-size:3.5rem; margin:10px 0;">{r['p']:.6f}</h1>
                    
                    <div class="pos-box">
                        <span class="n-label">Pozycja ATR (Risk {st.session_state.risk_pct}%)</span>
                        <span style="font-size:2rem; font-weight:900; color:#ffffff;">{r['sh']} SZT.</span><br>
                        <small style="color:#ff4b4b;">SL: {r['sl']:.6f}</small> | <small style="color:#00ff88;">TP: {r['tp']:.6f}</small>
                    </div>

                    <div class="m-grid">
                        <div><span class='n-label'>RSI</span><span class='n-val'>{r['rsi']:.1f}</span></div>
                        <div><span class='n-label'>MACD</span><span class='n-val'>{r['macd']:.4f}</span></div>
                        <div><span class='n-label'>Pivot</span><span class='n-val'>{r['pp']:.4f}</span></div>
                        <div><span class='n-label'>SMA 200</span><span class='n-val'>{r['s200']:.4f}</span></div>
                        <div><span class='n-label'>Max 52T</span><span class='n-val'>{r['h52']:.4f}</span></div>
                        <div><span class='n-label'>SMA 50</span><span class='n-val'>{r['s50']:.4f}</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Wykres
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"c_{r['s']}_{idx}", config={'displayModeBar': False})
                
                if client and st.button(f"🤖 RAPORT AI {r['s']}", key=f"ai_{r['s']}"):
                    p = f"Analiza {r['s']}: Cena {r['p']:.6f}, RSI {r['rsi']:.1f}, Pivot {r['pp']:.4f}. Podaj SL/TP i plan 3 pkt. Konkretnie, PL."
                    res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content":p}], max_tokens=400)
                    st.info(res.choices.message.content)
                
                for n in r['news']:
                    st.markdown(f"<small>● <a href='{n['l']}' target='_blank' style='color:#58a6ff;'>{n['t']}</a></small>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
