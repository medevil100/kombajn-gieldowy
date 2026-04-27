import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import time
import os
from concurrent.futures import ThreadPoolExecutor

# --- KONFIGURACJA ---
st.set_page_config(page_title="AI MONSTER v81 ULTRA FIX", layout="wide")
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read().strip()
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX, CMMB, DRMA, EVOK"

# --- STYLE CSS (Naprawione pod Penny Stocks) ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .compact-card { 
        background: #0d1117; padding: 20px; border-radius: 15px; 
        border: 1px solid #30363d; margin-bottom: 20px; min-height: 600px;
    }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    .n-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; }
    .n-val { font-size: 1rem; font-weight: bold; color: #ffffff; display: block; margin-bottom: 5px; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- SILNIK POBIERANIA (Penny Stock Fix) ---
def get_pro_data(symbol):
    try:
        s = symbol.strip().upper()
        time.sleep(0.3) # Spowolnienie, by uniknąć bana od Yahoo
        t = yf.Ticker(s)
        
        # Pobieramy dane bez auto_adjust (ważne dla spółek poniżej 1 USD)
        df = t.history(period="1y", interval="1d", auto_adjust=False)
        
        if df.empty or len(df) < 30: return None
        
        # Naprawa cen zerowych
        df['Close'] = df['Close'].replace(0, np.nan).ffill()
        curr = df['Close'].iloc[-1]
        
        # Obliczenia techniczne
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # RSI (14)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Ekstrema i Pivot
        h52, l52 = df['High'].max(), df['Low'].min()
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        
        # ATR i Pozycja
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        risk = st.session_state.get('risk_cap', 10000) * (st.session_state.get('risk_pct', 1.0) / 100)
        # Dla penny stocks używamy większego bufora ATR (2.0)
        sh = int(risk / (atr * 2.0)) if atr > 0 else 0

        return {
            "s": s, "p": curr, "rsi": rsi, "s50": sma50, "s200": sma200, "h52": h52, "l52": l52,
            "pp": pp, "sh": sh, "sl": curr - (atr * 2.0), "tp": curr + (atr * 4.0),
            "df": df.tail(40), "news": t.news[:2]
        }
    except: return None

# --- UI ---
with st.sidebar:
    st.title("🚜 MONSTER v81 FIX")
    t_in = st.text_area("Symbole (CSV):", load_tickers(), height=250)
    st.session_state.risk_cap = st.number_input("Kapitał (PLN):", value=10000.0)
    st.session_state.risk_pct = st.slider("Ryzyko %:", 0.1, 5.0, 1.0)
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()
    st_autorefresh(interval=300000, key="data_refresh")

symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

# Pobieranie danych
with ThreadPoolExecutor(max_workers=5) as exe: # Mniej pracowników = mniejsza szansa na ban od Yahoo
    results = [r for r in list(exe.map(get_pro_data, symbols)) if r]

st.subheader(f"🚜 Aktywne analizy: {len(results)} spółek")

cols = st.columns(3)
for idx, r in enumerate(results):
    with cols[idx % 3]:
        # Karta spółki
        st.markdown(f"""
        <div class="compact-card">
            <div style="display:flex; justify-content:space-between;">
                <b style="font-size:1.5rem;">{r['s']}</b>
                <span class="{'sig-buy' if r['rsi'] < 35 else 'sig-sell' if r['rsi'] > 65 else ''}">
                    {'KUP 🔥' if r['rsi'] < 35 else 'SPRZEDAJ ⚠️' if r['rsi'] > 65 else 'CZEKAJ ⏳'}
                </span>
            </div>
            <h1 style="color:#58a6ff; margin:10px 0;">{r['p']:.6f}</h1>
            
            <div style="background:rgba(88,166,255,0.1); padding:12px; border-radius:10px; margin-bottom:15px; border:1px solid #58a6ff;">
                <span class="n-label">Sugerowana Pozycja</span>
                <span style="font-size:1.4rem; font-weight:bold; color:#ffffff; display:block;">{r['sh']} SZT.</span>
                <small style="color:#ff4b4b;">SL: {r['sl']:.6f}</small> | <small style="color:#00ff88;">TP: {r['tp']:.6f}</small>
            </div>

            <div class="metric-grid">
                <div><span class="n-label">RSI (14)</span><span class="n-val">{r['rsi']:.1f}</span></div>
                <div><span class="n-label">Pivot Point</span><span class="n-val">{r['pp']:.4f}</span></div>
                <div><span class="n-label">Szczyt 52T</span><span class="n-val">{r['h52']:.4f}</span></div>
                <div><span class="n-label">Dołek 52T</span><span class="n-val">{r['l52']:.4f}</span></div>
            </div>
        """, unsafe_allow_html=True)
        
        # Wykres
        fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True, key=f"c_{r['s']}")
        
        if st.button(f"🤖 AI ANALIZA {r['s']}", key=f"ai_{r['s']}"):
            if client:
                prompt = f"Analiza {r['s']}: Cena {r['p']:.6f}, RSI {r['rsi']:.1f}. Podaj SL/TP i plan 3 pkt dla Penny Stock."
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                st.info(resp.choices.message.content)
            else: st.warning("Brak klucza OpenAI.")

        st.markdown("</div>", unsafe_allow_html=True)
