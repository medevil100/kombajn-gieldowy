import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# SEKCJA 1: KONFIGURACJA ŚRODOWISKA I BAZY DANYCH
# ==============================================================================
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

st.set_page_config(
    page_title="AI ALPHA MONSTER PRO v71",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0
if 'ai_cache' not in st.session_state: st.session_state.ai_cache = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            c = f.read().strip()
            return c if c else "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS"

# ==============================================================================
# SEKCJA 2: ARCHITEKTURA STYLÓW CSS (PRO NEON DARK)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 25px; border-radius: 20px; border: 1px solid #30363d; 
        text-align: center; margin-bottom: 25px; min-height: 1050px;
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.6rem; text-shadow: 0 0 15px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.6rem; text-shadow: 0 0 15px #ff4b4b; }
    .pos-box { background: rgba(88, 166, 255, 0.08); border-radius: 15px; padding: 15px; margin: 15px 0; border: 1px solid #58a6ff; }
    .pos-val { font-size: 2.2rem; font-weight: 900; color: #ffffff; display: block; }
    .tech-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }
    .tech-item { background: rgba(255,255,255,0.03); padding: 10px; border-radius: 10px; border: 1px solid #21262d; text-align: left; }
    .tech-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .tech-value { font-size: 1rem; font-weight: bold; }
    .ai-box { background: rgba(0, 255, 136, 0.03); border: 1px solid rgba(0, 255, 136, 0.2); padding: 15px; border-radius: 12px; text-align: left; font-size: 0.85rem; }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.75rem; display: block; margin: 4px 0; text-align: left; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# SEKCJA 3: SILNIK ANALITYCZNY I WIZUALIZACJA
# ==============================================================================
def get_ai_opinion(symbol, data_summary):
    if not client: return "Skonfiguruj OPENAI_API_KEY w Secrets."
    key = f"{symbol}_{datetime.now().strftime('%H')}"
    if key in st.session_state.ai_cache: return st.session_state.ai_cache[key]
    try:
        p = f"Analizuj {symbol}: {data_summary}. Podaj: 1. Werdykt 2. Ryzyko 3. Target. Max 40 słów."
        r = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content":p}], max_tokens=100)
        st.session_state.ai_cache[key] = r.choices[0].message.content
        return st.session_state.ai_cache[key]
    except: return "Analiza AI czasowo niedostępna."

def create_chart(df):
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'].rolling(50).mean(), line=dict(color='#00ff88', width=1)))
    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def fetch_monster_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="150d", auto_adjust=True)
        if df.empty or len(df) < 50: return None
        c = df['Close']
        curr, sma50, sma200 = c.iloc[-1], c.rolling(50).mean().iloc[-1], c.rolling(150).mean().iloc[-1]
        delta = c.diff(); gain = delta.where(delta > 0, 0).rolling(14).mean(); loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1); atr = tr.rolling(14).mean().iloc[-1]
        risk = st.session_state.risk_cap * (st.session_state.risk_pct / 100); sl_d = atr * 1.5
        sh = int(risk / sl_d) if sl_d > 0 else 0
        if sh * curr > st.session_state.risk_cap: sh = int(st.session_state.risk_cap / curr)
        v, vc = ("KUP 🔥", "sig-buy") if rsi < 35 else ("SPRZEDAJ ⚠️", "sig-sell") if rsi > 65 else ("CZEKAJ ⏳", "sig-neutral")
        return {"s":symbol,"p":curr,"rsi":rsi,"sma50":sma50,"sma200":sma200,"v":v,"vc":vc,"sh":sh,"atr":atr,"sl":curr-sl_d,"tp":curr+(atr*3),"news":t.news[:2],"df":df}
    except: return None
# ==============================================================================
# SEKCJA 4: INTERFEJS I PĘTLA WYŚWIETLANIA
# ==============================================================================
def main():
    st.sidebar.title("🚜 KONTROLA MONSTERA")
    t_area = st.sidebar.text_area("Tickery (CSV):", load_tickers(), height=200)
    st.session_state.risk_cap = st.sidebar.number_input("Kapitał (PLN):", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.sidebar.slider("Ryzyko (%):", 0.1, 5.0, st.session_state.risk_pct)
    
    if st.sidebar.button("💾 ZAPISZ I START"):
        with open(DB_FILE, "w") as f: f.write(t_area)
        st.rerun()

    st_autorefresh(interval=600000, key="m_refresh")
    symbols = [s.strip().upper() for s in t_area.split(",") if s.strip()]
    
    st.write(f"### 🚜 Monitorowanie {len(symbols)} spółek | Ryzyko: {st.session_state.risk_pct}% ({st.session_state.risk_cap * st.session_state.risk_pct / 100:.0f} PLN)")
    
    with ThreadPoolExecutor(max_workers=10) as exe:
        results = list(exe.map(fetch_monster_data, symbols))
    
    cols = st.columns(3)
    for idx, r in enumerate([res for res in results if res]):
        with cols[idx % 3]:
            with st.container(key=f"cont_{r['s']}"):
                st.markdown(f"""
                <div class="main-card">
                    <div>
                        <div style="display:flex; justify-content:space-between; opacity:0.6; font-size:0.8rem;">
                            <span>{r['s']}</span><span>{datetime.now().strftime('%H:%M')}</span>
                        </div>
                        <h1 style="color:#58a6ff; font-size:3rem; margin:10px 0;">{r['p']:.2f}<small style="font-size:0.8rem;"> USD</small></h1>
                        <div class="{r['vc']}">{r['v']}</div>
                        
                        <div class="pos-box">
                            <span class="tech-label">Sugerowana Pozycja</span>
                            <span class="pos-val">{r['sh']} <small style="font-size:1rem;">szt.</small></span>
                            <div style="display:flex; justify-content:space-between; margin-top:8px; font-size:0.8rem;">
                                <span style="color:#ff4b4b;">SL: {r['sl']:.2f}</span><span style="color:#00ff88;">TP: {r['tp']:.2f}</span>
                            </div>
                        </div>
                """, unsafe_allow_html=True)
                
                st.plotly_chart(create_chart(r['df']), use_container_width=True, config={'displayModeBar': False}, key=f"plot_{r['s']}")
                
                st.markdown(f"""
                        <div class="tech-grid">
                            <div class="tech-item"><span class="tech-label">RSI</span><span class="tech-value">{r['rsi']:.1f}</span></div>
                            <div class="tech-item"><span class="tech-label">ATR</span><span class="tech-value">{r['atr']:.2f}</span></div>
                            <div class="tech-item"><span class="tech-label">SMA50</span><span class="tech-value">{r['sma50']:.2f}</span></div>
                            <div class="tech-item"><span class="tech-label">SMA200</span><span class="tech-value">{r['sma200']:.2f}</span></div>
                        </div>
                        <div class="ai-box"><b>🤖 AI:</b> {get_ai_opinion(r['s'], f"P:{r['p']}, RSI:{r['rsi']}")}</div>
                        <div style="margin-top:15px; padding-top:10px; border-top:1px solid #21262d;">
                            {''.join([f'<a class="news-link" href="{n["l"]}" target="_blank">● {n["t"]}</a>' for n in r['news']])}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<br><hr><center><small style='color:#30363d;'>AI ALPHA MONSTER PRO v71 © 2024</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
