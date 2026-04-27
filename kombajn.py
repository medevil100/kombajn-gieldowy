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

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX, CMMB, DRMA, EVOK"
        except: pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX, CMMB, DRMA, EVOK"

# ==============================================================================
# 2. STYLE CSS (NEON PRO)
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .neon-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        margin-bottom: 30px; min-height: 850px; width: 100%;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); }
    .hold { border: 1px solid #30363d !important; }
    .neon-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; display: block; }
    .neon-value { font-size: 1.1rem; font-weight: bold; color: #ffffff; margin-bottom: 10px; display: block; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK ANALITYCZNY
# ==============================================================================
def fetch_monster_analysis(symbol):
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df = t.history(period="2y", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close']
        curr = close.iloc[-1]
        
        # Wskaźniki
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        h52, l52 = df['High'].tail(252).max(), df['Low'].tail(252).min()
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Pivot & Risk
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        atr = (df['High']-df['Low']).rolling(14).mean().iloc[-1]
        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sh = int(risk_cash / (atr * 1.5)) if atr > 0 else 0
        
        v_text, v_class = ("KUP 🔥", "buy") if rsi < 35 else ("SPRZEDAJ ⚠️", "sell") if rsi > 65 else ("TRZYMAJ ⏳", "hold")
        
        # Bezpieczne Newsy (Poprawione)
        raw_news = t.news if hasattr(t, 'news') else []
        news_list = []
        for n in raw_news[:3]:
            title = n.get('title')
            link = n.get('link', '#')
            if title: # Tylko jeśli tytuł istnieje
                news_list.append({"t": str(title)[:55], "l": link})

        return {
            "s": s, "p": curr, "rsi": rsi, "pp": pp, "h52": h52, "l52": l52, "sh": sh,
            "sl": curr - (atr * 1.5), "tp": curr + (atr * 3), 
            "sma50": sma50, "sma200": sma200, "df": df.tail(60), "v": v_text, "vc": v_class,
            "news": news_list
        }
    except: return None

def get_ai_strategy(r):
    if not client: return "Brak klucza OpenAI."
    prompt = f"Analiza {r['s']}: Cena {r['p']:.2f}, RSI {r['rsi']:.1f}, Pivot {r['pp']:.2f}. Podaj SL, TP i strategię 3 pkt. Konkret."
    try:
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=400)
        return response.choices.message.content
    except: return "Błąd AI."

# ==============================================================================
# 4. INTERFEJS I PAGINACJA
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
    items_per_page = 6
    total_pages = (len(symbols) // items_per_page) + (1 if len(symbols) % items_per_page > 0 else 0)
    page = st.number_input("Strona (Paczki po 6)", 1, total_pages, 1)

# Pobieranie danych dla strony
start_idx = (page - 1) * items_per_page
current_batch = symbols[start_idx : start_idx + items_per_page]

with ThreadPoolExecutor(max_workers=6) as exe:
    results = list(exe.map(fetch_monster_analysis, current_batch))

# Filtracja pustych wyników
results = [r for r in results if r is not None]

st.subheader(f"🚜 Analiza: {len(symbols)} spółek | Strona {page} z {total_pages}")

# Renderowanie kolumn
if results:
    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"""<div class='neon-card {r["vc"]}'>
                    <h3 style='margin:0;'>{r['s']} | {r['v']}</h3>
                    <h1 style='color:#58a6ff; margin:10px 0;'>{r['p']:.2f} <small style='font-size:1rem;'>USD</small></h1>
                    <div class='metric-grid'>
                        <div><span class='neon-label'>RSI</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                        <div><span class='neon-label'>Pivot</span><span class='neon-value'>{r['pp']:.2f}</span></div>
                        <div><span class='neon-label'>SMA 50</span><span class='neon-value'>{r['sma50']:.2f}</span></div>
                        <div><span class='neon-label'>SMA 200</span><span class='neon-value'>{r['sma200']:.2f}</span></div>
                    </div>
                    <div style='background:rgba(88,166,255,0.1); padding:15px; border-radius:12px; margin-bottom:15px;'>
                        <b>Pozycja: {r['sh']} szt.</b><br>
                        <small style='color:#ff4b4b;'>SL: {r['sl']:.2f}</small> | <small style='color:#00ff88;'>TP: {r['tp']:.2f}</small>
                    </div>
                """, unsafe_allow_html=True)
                
                # Wykres
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}")
                
                if st.button(f"🤖 RAPORT AI {r['s']}", key=f"ai_{r['s']}"):
                    st.info(get_ai_strategy(r))
                
                st.markdown("<br><span class='neon-label'>NEWS</span>", unsafe_allow_html=True)
                for n in r['news']:
                    st.markdown(f"• [{n['t']}...]({n['l']})")
                st.markdown("</div>", unsafe_allow_html=True)
else:
    st.warning("Brak danych dla tej strony. Sprawdź symbole lub połączenie.")

st.markdown("<center><small>AI ALPHA MONSTER v75 ULTRA © 2026</small></center>", unsafe_allow_html=True)
