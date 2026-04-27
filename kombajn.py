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
st.set_page_config(page_title="AI ALPHA MONSTER v76", page_icon="🚜", layout="wide")
DB_FILE = "moje_spolki.txt"

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return f.read().strip()
        except: pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, AURA, APM, BBI, BCTX, BDRX, BNOX, BOLT, BTTX, CMMB, CRVS, DRMA, ENLV, EVOK, GHSI, HILS, IMUX, IMNN, INAB, INFI, KTRA, MBIO, MNOV, MREO, NRSN, ONCS, PALI, PBYI, PGEN, RGLS, SABS, SLS, SLNO, TCON, TTOO, VINC, VIRI, XLO, PLRX, IOVA, HUMA, GOSS, FATE, LV"

# ==============================================================================
# 2. STABILNE STYLE CSS
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .neon-card { 
        background: #0d1117; padding: 25px; border-radius: 15px; 
        border: 1px solid #30363d; margin-bottom: 20px; min-height: 850px;
    }
    .buy { border-left: 5px solid #00ff88; }
    .sell { border-left: 5px solid #ff4b4b; }
    .neon-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; }
    .neon-value { font-size: 1.1rem; font-weight: bold; color: #ffffff; margin-bottom: 8px; display: block; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK ANALITYCZNY (PANCERNY)
# ==============================================================================
def fetch_analysis(symbol):
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df = t.history(period="1y", auto_adjust=True)
        if df.empty or len(df) < 50: return None
        
        c = df['Close']
        curr = c.iloc[-1]
        
        # Wskaźniki
        sma50 = c.rolling(50).mean().iloc[-1]
        sma200 = c.rolling(200).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (c.diff().where(c.diff() > 0, 0).rolling(14).mean() / 
                                 c.diff().where(c.diff() < 0, 0).abs().rolling(14).mean()))).iloc[-1]
        
        h52, l52 = df['High'].max(), df['Low'].min()
        atr = (df['High']-df['Low']).rolling(14).mean().iloc[-1]
        sh = int((st.session_state.risk_cap * (st.session_state.risk_pct / 100)) / (atr * 1.5)) if atr > 0 else 0
        
        v_text, v_class = ("KUP 🔥", "buy") if rsi < 35 else ("SPRZEDAJ ⚠️", "sell") if rsi > 65 else ("TRZYMAJ ⏳", "hold")

        return {
            "s": s, "p": curr, "rsi": rsi, "h52": h52, "l52": l52, "sh": sh,
            "sl": curr - (atr * 1.5), "tp": curr + (atr * 3), "s50": sma50, "s200": sma200, 
            "df": df.tail(40), "v": v_text, "vc": v_class
        }
    except: return None

# ==============================================================================
# 4. UI GŁÓWNE
# ==============================================================================
with st.sidebar:
    st.title("🚜 KONTROLA v76")
    t_in = st.text_area("Symbole (CSV):", load_tickers(), height=300)
    st.session_state.risk_cap = st.number_input("Kapitał (PLN):", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.sidebar.slider("Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct)
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

# Równoległe pobieranie (max 10 wątków by nie blokować API)
with ThreadPoolExecutor(max_workers=10) as exe:
    raw_results = list(exe.map(fetch_analysis, symbols))
results = [r for r in raw_results if r]

st.subheader(f"🚜 Kombajn: {len(results)} aktywnych spółek")

# Renderowanie w stabilnym gridzie (3 kolumny)
cols = st.columns(3)
for idx, r in enumerate(results):
    with cols[idx % 3]:
        st.markdown(f"""
        <div class="neon-card {r['vc']}">
            <h3 style="margin:0;">{r['s']} | {r['v']}</h3>
            <h2 style="color:#58a6ff; margin:10px 0;">{r['p']:.2f} USD</h2>
            <hr style="border-color:#21262d;">
            <span class="neon-label">RSI</span><span class="neon-value">{r['rsi']:.1f}</span>
            <span class="neon-label">SMA 50 / 200</span><span class="neon-value">{r['s50']:.2f} / {r['s200']:.2f}</span>
            <span class="neon-label">Szczyt / Dołek 52T</span><span class="neon-value">{r['h52']:.2f} / {r['l52']:.2f}</span>
            <div style="background:rgba(88,166,255,0.1); padding:10px; border-radius:10px;">
                <small>Pozycja: <b>{r['sh']} szt.</b></small><br>
                <small>SL: <b>{r['sl']:.2f}</b> | TP: <b>{r['tp']:.2f}</b></small>
            </div>
        """, unsafe_allow_html=True)
        
        # Stabilny Wykres
        fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
        fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}")
        
        if st.button(f"🤖 ANALIZA AI {r['s']}", key=f"ai_{r['s']}"):
            if AI_KEY:
                client = OpenAI(api_key=AI_KEY)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=[{"role": "user", "content": f"Analiza {r['s']}: Cena {r['p']:.2f}, RSI {r['rsi']:.1f}. Podaj SL/TP i strategię 3 pkt."}]
                )
                st.info(resp.choices[0].message.content)
            else: st.warning("Brak klucza OpenAI.")
        st.markdown("</div>", unsafe_allow_html=True)
