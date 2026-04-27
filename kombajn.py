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
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

st.set_page_config(
    page_title="AI ALPHA MONSTER v75 ULTRA",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "NVDA, TSLA, BTC-USD, PKO.WA"
        except: pass
    return "NVDA, TSLA, BTC-USD, PKO.WA"

# ==============================================================================
# 2. STYLE CSS (NEON PRO)
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .neon-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 35px; border-radius: 25px; border: 1px solid #30363d; 
        margin-bottom: 40px; min-height: 800px;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 20px rgba(0,255,136,0.2); }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 20px rgba(255,75,75,0.2); }
    .hold { border: 1px solid #30363d !important; }
    .neon-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 2px; display: block; margin-bottom: 5px; }
    .neon-value { font-size: 1.1rem; font-weight: bold; color: #ffffff; display: block; margin-bottom: 10px; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }
    .news-item { color: #58a6ff; text-decoration: none; font-size: 0.8rem; display: block; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK ANALITYCZNY
# ==============================================================================
def fetch_monster_data(symbol):
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df_raw = t.history(period="2y", interval="1d", auto_adjust=True)
        if df_raw.empty or len(df_raw) < 200: return None
        
        # Wskaźniki
        close = df_raw['Close']
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        sma100 = close.rolling(100).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        
        curr = close.iloc[-1]
        h52, l52 = df_raw['High'].tail(252).max(), df_raw['Low'].tail(252).min()
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Pivot
        prev = df_raw.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        
        # ATR / Risk
        tr = pd.concat([df_raw['High']-df_raw['Low'], (df_raw['High']-close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sh = int(risk_cash / (atr * 1.5)) if atr > 0 else 0
        
        v_text, v_class = ("KUP 🔥", "buy") if rsi < 35 else ("SPRZEDAJ ⚠️", "sell") if rsi > 65 else ("TRZYMAJ ⏳", "hold")

        news = []
        try:
            for n in t.news[:3]: news.append({"t": n.get('title', 'News'), "l": n.get('link', '#')})
        except: pass

        return {
            "s": s, "p": curr, "rsi": rsi, "pp": pp, "h52": h52, "l52": l52, "sh": sh,
            "sl": curr - (atr * 1.5), "tp": curr + (atr * 3), "sma20": sma20, "sma50": sma50,
            "sma100": sma100, "sma200": sma200, "news": news, "df": df_raw.tail(80), "v": v_text, "vc": v_class
        }
    except: return None

def get_ai_strategy(data):
    if not client: return "Brak klucza OpenAI."
    prompt = f"Analiza {data['s']}: Cena {data['p']:.2f}, RSI {data['rsi']:.1f}, Pivot {data['pp']:.2f}. Podaj SL/TP i strategię 3 pkt. Konkret."
    try:
        r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], max_tokens=300)
        return r.choices.message.content
    except: return "Błąd AI."

# ==============================================================================
# 4. UI I RENDEROWANIE
# ==============================================================================
st.sidebar.title("🚜 KONTROLA")
t_in = st.sidebar.text_area("Symbole (CSV):", load_tickers(), height=150)
st.session_state.risk_cap = st.sidebar.number_input("Kapitał (PLN):", value=st.session_state.risk_cap)
st.session_state.risk_pct = st.sidebar.slider("Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct)

if st.sidebar.button("ZAPISZ I ANALIZUJ"):
    with open(DB_FILE, "w") as f: f.write(t_in)
    st.rerun()

st_autorefresh(interval=300000, key="fsh")
syms = [s.strip().upper() for s in t_in.split(",") if s.strip()]

with ThreadPoolExecutor(max_workers=10) as exe:
    results = [r for r in list(exe.map(fetch_monster_data, syms)) if r]

if results:
    st.subheader("🔥 TOP SYGNAŁY")
    top_cols = st.columns(5)
    for i, r in enumerate(sorted(results, key=lambda x: x['rsi'])[:5]):
        with top_cols[i]:
            st.markdown(f'<div class="neon-card {r["vc"]}" style="min-height:120px; padding:15px; text-align:center;"><b>{r["s"]}</b><br>{r["p"]:.2f}<br>{r["v"]}</div>', unsafe_allow_html=True)

    st.divider()

    for r in results:
        with st.container():
            st.markdown(f"<div class='neon-card {r['vc']}'>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 1.2, 1.8])
            with c1:
                st.markdown(f"### {r['s']} | {r['v']}")
                st.metric("CENA", f"{r['p']:.2f}")
                st.markdown(f"""<div class="metric-grid">
                    <div><span class="neon-label">RSI</span><span class="neon-value">{r['rsi']:.1f}</span></div>
                    <div><span class="neon-label">Pivot</span><span class="neon-value">{r['pp']:.2f}</span></div>
                    <div><span class="neon-label">Max 52T</span><span class="neon-value">{r['h52']:.2f}</span></div>
                    <div><span class="neon-label">Min 52T</span><span class="neon-value">{r['l52']:.2f}</span></div>
                    <div><span class="neon-label">SMA 50</span><span class="neon-value">{r['sma50']:.2f}</span></div>
                    <div><span class="neon-label">SMA 200</span><span class="neon-value">{r['sma200']:.2f}</span></div>
                </div>""", unsafe_allow_html=True)
            with c2:
                st.markdown("<span class='neon-label'>STRATEGIA AI</span>", unsafe_allow_html=True)
                if st.button(f"RAPORT AI", key=f"ai_{r['s']}"): st.info(get_ai_strategy(r))
                st.markdown("<br><span class='neon-label'>NEWS</span>", unsafe_allow_html=True)
                for n in r['news']: st.markdown(f"<a class='news-item' href='{n['l']}'>● {n['t'][:50]}...</a>", unsafe_allow_html=True)
            with c3:
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}")
            st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<center><small>AI ALPHA MONSTER PRO v75 ULTRA © 2026</small></center>", unsafe_allow_html=True)
