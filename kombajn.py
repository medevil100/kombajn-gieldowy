import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# SEKCJA 1: KONFIGURACJA ŚRODOWISKA I BAZY
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

# Inicjalizacja stanów sesji
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
# SEKCJA 2: ROZBUDOWANA ARCHITEKTURA STYLÓW CSS
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 25px; border-radius: 20px; border: 1px solid #30363d; 
        text-align: center; margin-bottom: 25px; min-height: 1100px;
        display: flex; flex-direction: column; justify-content: space-between;
    }
    
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.8rem; text-shadow: 0 0 15px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.8rem; text-shadow: 0 0 15px #ff4b4b; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.5rem; }
    
    .pos-box { background: rgba(88, 166, 255, 0.08); border-radius: 15px; padding: 15px; margin: 15px 0; border: 1px solid #58a6ff; }
    .pos-val { font-size: 2.2rem; font-weight: 900; color: #ffffff; display: block; }
    
    .tech-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }
    .tech-item { background: rgba(255,255,255,0.03); padding: 10px; border-radius: 10px; border: 1px solid #21262d; text-align: left; }
    .tech-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .tech-value { font-size: 0.9rem; font-weight: bold; color: #ffffff; }
    
    .ai-box { 
        background: rgba(0, 255, 136, 0.03); border: 1px solid rgba(0, 255, 136, 0.2); 
        padding: 15px; border-radius: 12px; margin-top: 15px; text-align: left; font-size: 0.85rem;
    }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.8rem; display: block; margin: 5px 0; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# SEKCJA 3: SILNIK ANALITYCZNY PRO
# ==============================================================================
def get_ai_analysis(symbol, tech_data):
    if not client: return "Brak klucza OpenAI."
    key = f"{symbol}_{datetime.now().strftime('%H')}"
    if key in st.session_state.ai_cache: return st.session_state.ai_cache[key]
    try:
        p = f"Analizuj technicznie {symbol}: {tech_data}. Podaj: 1. Strategia 2. Ryzyko 3. Cel. Krótko, konkretnie, PL."
        r = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content":p}], max_tokens=120)
        st.session_state.ai_cache[key] = r.choices.message.content
        return st.session_state.ai_cache[key]
    except: return "Analiza AI niedostępna."

def fetch_pro_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="200d", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 100: return None
        
        c = df['Close']
        # Wskaźniki
        sma50 = c.rolling(50).mean().iloc[-1]
        sma200 = c.rolling(200).mean().iloc[-1]
        
        # Bollinger Bands
        std = c.rolling(20).std().iloc[-1]
        sma20 = c.rolling(20).mean().iloc[-1]
        b_upper = sma20 + (std * 2)
        b_lower = sma20 - (std * 2)
        
        # RSI
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # MACD
        exp1 = c.ewm(span=12, adjust=False).mean()
        exp2 = c.ewm(span=26, adjust=False).mean()
        macd = (exp1 - exp2).iloc[-1]
        
        # ATR / Risk
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        curr = float(c.iloc[-1])
        risk_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_val = atr * 1.5
        sh = int(risk_money / sl_val) if sl_val > 0 else 0
        if sh * curr > st.session_state.risk_cap: sh = int(st.session_state.risk_cap / curr)

        # Verdict logic
        v, vc = ("KUP 🔥", "sig-buy") if rsi < 32 and curr < b_lower else \
                ("SPRZEDAJ ⚠️", "sig-sell") if rsi > 68 or curr > b_upper else \
                ("CZEKAJ ⏳", "sig-neutral")

        return {
            "s": symbol, "p": curr, "rsi": rsi, "sma50": sma50, "sma200": sma200, "macd": macd,
            "v": v, "vc": vc, "sh": sh, "atr": atr, "sl": curr - sl_val, "tp": curr + (atr * 3),
            "news": t.news[:2], "df": df, "b_up": b_upper, "b_low": b_lower
        }
    except: return None

def draw_chart(df, b_up, b_low):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Cena"))
    fig.add_trace(go.Scatter(x=df.index, y=[b_up]*len(df), line=dict(color='rgba(255,75,75,0.2)', dash='dot'), name="BB Upper"))
    fig.add_trace(go.Scatter(x=df.index, y=[b_low]*len(df), line=dict(color='rgba(0,255,136,0.2)', dash='dot'), name="BB Lower"))
    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    return fig

# ==============================================================================
# SEKCJA 4: RENDEROWANIE INTERFEJSU
# ==============================================================================
def main():
    st.sidebar.title("🚜 MONSTER KONTROLA")
    tickers_raw = st.sidebar.text_area("Lista spółek (CSV):", load_tickers(), height=200)
    st.session_state.risk_cap = st.sidebar.number_input("Twój Kapitał (PLN):", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.sidebar.slider("Ryzyko na pozycję (%):", 0.1, 5.0, st.session_state.risk_pct)
    
    if st.sidebar.button("💾 ZAPISZ I ANALIZUJ WSZYSTKO"):
        with open(DB_FILE, "w") as f: f.write(tickers_raw)
        st.rerun()

    st_autorefresh(interval=600000, key="pro_refresh")
    
    symbols = [s.strip().upper() for s in tickers_raw.split(",") if s.strip()]
    st.write(f"### 🚜 Monitorowanie {len(symbols)} spółek | Ryzyko: {st.session_state.risk_pct}%")

    with ThreadPoolExecutor(max_workers=10) as exe:
        results = list(exe.map(fetch_pro_data, symbols))

    cols = st.columns(3)
    for idx, r in enumerate([res for res in results if res]):
        with cols[idx % 3]:
            # Stabilny kontener dla każdej spółki
            with st.container():
                st.markdown(f"""
                <div class="main-card">
                    <div>
                        <div style="display:flex; justify-content:space-between; opacity:0.5;">
                            <b>{r['s']}</b><span>{datetime.now().strftime('%H:%M')}</span>
                        </div>
                        <h1 style="color:#58a6ff; font-size:3.5rem; margin:10px 0;">{r['p']:.2f}</h1>
                        <div class="{r['vc']}">{r['v']}</div>
                        
                        <div class="pos-box">
                            <span class="tech-label">Sugerowana Pozycja</span>
                            <span class="pos-val">{r['sh']} SZT.</span>
                            <div style="display:flex; justify-content:space-between; margin-top:10px;">
                                <span style="color:#ff4b4b;">SL: {r['sl']:.2f}</span>
                                <span style="color:#00ff88;">TP: {r['tp']:.2f}</span>
                            </div>
                        </div>
                """, unsafe_allow_html=True)

                st.plotly_chart(draw_chart(r['df'], r['b_up'], r['b_low']), use_container_width=True, config={'displayModeBar': False}, key=f"p_{r['s']}")

                st.markdown(f"""
                        <div class="tech-grid">
                            <div class="tech-item"><span class="tech-label">RSI (14)</span><br><span class="tech-value">{r['rsi']:.1f}</span></div>
                            <div class="tech-item"><span class="tech-label">MACD</span><br><span class="tech-value">{r['macd']:.4f}</span></div>
                            <div class="tech-item"><span class="tech-label">SMA 50</span><br><span class="tech-value">{r['sma50']:.2f}</span></div>
                            <div class="tech-item"><span class="tech-label">ATR</span><br><span class="tech-value">{r['atr']:.2f}</span></div>
                        </div>
                        <div class="ai-box">
                            <b>🤖 STRATEGIA AI:</b><br>{get_ai_opinion(r['s'], f"P:{r['p']}, RSI:{r['rsi']}") if 'get_ai_opinion' in globals() else get_ai_analysis(r['s'], f"P:{r['p']}, RSI:{r['rsi']}")}
                        </div>
                        <div style="margin-top:15px; border-top:1px solid #21262d; padding-top:10px;">
                            {''.join([f'<a class="news-link" href="{n["link"]}" target="_blank">● {n["title"][:50]}...</a>' for n in r['news']])}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<br><hr><center><small style='color:#444;'>AI ALPHA MONSTER PRO v71 | © 2024</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
