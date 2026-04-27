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
# 1. KONFIGURACJA SYSTEMOWA (PANCERNA)
# ==============================================================================
st.set_page_config(
    page_title="AI ALPHA MONSTER v88 ULTRA",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                c = f.read().strip()
                return c if c else "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BNOX, CMMB, DRMA"
        except: pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BNOX, CMMB, DRMA"

# ==============================================================================
# 2. DESIGN NEON PRO (BEZ GRUPOWANIA - FULL WIDTH)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    .neon-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        margin-bottom: 30px; min-height: 950px; width: 100%;
        transition: 0.3s ease-in-out;
    }
    .buy { border-top: 4px solid #00ff88; box-shadow: 0 5px 20px rgba(0,255,136,0.1); }
    .sell { border-top: 4px solid #ff4b4b; box-shadow: 0 5px 20px rgba(255,75,75,0.1); }
    .hold { border-top: 4px solid #30363d; }
    
    .neon-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1.5px; display: block; }
    .neon-value { font-size: 1.1rem; font-weight: 900; color: #ffffff; margin-bottom: 10px; display: block; }
    
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 15px 0; }
    .sig-text { font-weight: 900; font-size: 1.5rem; text-transform: uppercase; }
    
    .pos-box { 
        background: rgba(88, 166, 255, 0.08); padding: 15px; border-radius: 12px; 
        border: 1px solid #58a6ff; margin: 15px 0; text-align: center;
    }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.8rem; display: block; margin-bottom: 5px; text-align: left; }
    .block-container { max-width: 98% !important; padding-top: 1.5rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK ANALITYCZNY (PENNY STOCK PRECISION)
# ==============================================================================
def fetch_monster_analysis(symbol):
    try:
        # Losowe opóźnienie, aby uniknąć blokady Yahoo Finance
        time.sleep(random.uniform(0.1, 0.4))
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        
        # Pobieranie RAW dla precyzji cen ułamkowych
        df_raw = t.history(period="2y", interval="1d", auto_adjust=False)
        if df_raw.empty or len(df_raw) < 150: return None
        
        # Naprawa cen zerowych i NaN (częste przy Penny Stocks)
        df_raw['Close'] = df_raw['Close'].replace(0, np.nan).ffill()
        c = df_raw['Close']
        curr = float(c.iloc[-1])
        
        # 1. Średnie Kroczące
        s20, s50, s100, s200 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1], c.rolling(100).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        
        # 2. RSI 14
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-12)))).iloc[-1]
        
        # 3. MACD
        e12 = c.ewm(span=12).mean(); e26 = c.ewm(span=26).mean(); macd = (e12 - e26).iloc[-1]
        
        # 4. Pivot Points i Ekstrema 52T
        prev = df_raw.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        h52, l52 = df_raw['High'].tail(252).max(), df_raw['Low'].tail(252).min()
        
        # 5. Risk Management (ATR)
        tr = pd.concat([df_raw['High']-df_raw['Low'], (df_raw['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        
        sh = int(risk_cash / (atr * 1.5)) if atr > 0 else 0
        sl = curr - (atr * 1.5)
        tp = curr + (atr * 3.5)

        # 6. Werdykt
        if rsi < 35: v_text, v_class = "KUP 🔥", "buy"
        elif rsi > 65: v_text, v_class = "SPRZEDAJ ⚠️", "sell"
        else: v_text, v_class = "CZEKAJ ⏳", "hold"

        # 7. Newsy
        m_news = []
        try:
            raw_n = t.news
            if raw_n:
                for n in raw_n[:3]:
                    title = n.get('title')
                    if title: m_news.append({"t": str(title)[:55], "l": n.get('link', '#')})
        except: pass

        return {
            "s": s, "p": curr, "rsi": rsi, "macd": macd, "pp": pp, "h52": h52, "l52": l52,
            "sh": sh, "sl": sl, "tp": tp, "s20": s20, "s50": s50, "s100": s100, "s200": s200,
            "df": df_raw.tail(60), "v": v_text, "vc": v_class, "news": m_news, "atr": atr
        }
    except: return None

def get_ai_strategy(r):
    if not client: return "Brak klucza OpenAI."
    prompt = f"Analiza {r['s']}: Cena {r['p']:.6f}, RSI {r['rsi']:.1f}, SMA200 {r['s200']:.4f}. Podaj SL, TP i strategię 3 pkt. Konkretnie, PL."
    try:
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=400)
        return res.choices.message.content
    except: return "AI timeout."

# ==============================================================================
# 4. RENDEROWANIE (FULL LIST - NO GROUPS)
# ==============================================================================
def main():
    with st.sidebar:
        st.title("🚜 KONTROLA MONSTERA")
        st.write(f"Zegar: {datetime.now().strftime('%H:%M:%S')}")
        
        # Regulacja odświeżania
        ref_val = st.slider("Odświeżanie (min):", 1, 20, 5)
        st_autorefresh(interval=ref_val * 60000, key="monster_refresh")
        
        t_in = st.text_area("Symbole (CSV):", load_tickers(), height=250)
        st.session_state.risk_cap = st.number_input("Kapitał Portfela (PLN):", value=st.session_state.risk_cap)
        st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
        
        if st.button("💾 ZAPISZ I ANALIZUJ"):
            with open(DB_FILE, "w") as f: f.write(t_in)
            st.rerun()

    symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
    st.subheader(f"🚜 Kombajn: Analiza {len(symbols)} spółek")

    # Pobieranie danych (Równoległe, ale mniejsza ilość wątków dla stabilności Yahoo)
    with ThreadPoolExecutor(max_workers=5) as exe:
        raw_results = list(exe.map(fetch_monster_analysis, symbols))
    
    results = [r for r in raw_results if r]

    # Wyświetlanie wszystkiego na jednej liście (3 kolumny)
    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"""
                <div class="neon-card {r['vc']}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:1.5rem; font-weight:900;">{r['s']}</span>
                        <span class="sig-text" style="color:{'#00ff88' if r['vc']=='buy' else '#ff4b4b' if r['vc']=='sell' else '#8b949e'}">{r['v']}</span>
                    </div>
                    <h1 style="color:#58a6ff; font-size:3.5rem; margin:10px 0;">{r['p']:.6f}</h1>
                    
                    <div class="pos-box">
                        <span class="neon-label">Pozycja</span>
                        <span style="font-size:1.8rem; font-weight:900; color:#ffffff;">{r['sh']} SZT.</span><br>
                        <small style="color:#ff4b4b;">SL: {r['sl']:.6f}</small> | <small style="color:#00ff88;">TP: {r['tp']:.6f}</small>
                    </div>

                    <div class="metric-grid">
                        <div><span class='neon-label'>RSI</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                        <div><span class='neon-label'>MACD</span><span class='neon-value'>{r['macd']:.4f}</span></div>
                        <div><span class='neon-label'>Pivot</span><span class='neon-value'>{r['pp']:.4f}</span></div>
                        <div><span class='neon-label'>SMA 200</span><span class='neon-value'>{r['s200']:.4f}</span></div>
                        <div><span class='neon-label'>Max 52T</span><span class='neon-value'>{r['h52']:.4f}</span></div>
                        <div><span class='neon-label'>SMA 50</span><span class='neon-value'>{r['s50']:.4f}</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Wykres Świecowy
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}_{idx}", config={'displayModeBar': False})
                
                if st.button(f"🤖 RAPORT AI {r['s']}", key=f"ai_{r['s']}"):
                    st.info(get_ai_strategy(r))
                
                for n in r['news']:
                    st.markdown(f"<a class='news-link' href='{n['l']}' target='_blank'>● {n['t']}</a>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br><hr><center><small style='color:#333;'>AI ALPHA MONSTER PRO v88 ULTRA © 2026</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
