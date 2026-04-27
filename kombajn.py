import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA SYSTEMOWA I PAMIĘĆ SESJI
# ==============================================================================
st.set_page_config(
    page_title="AI ALPHA MONSTER v87 ULTRA PRO",
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
# 2. ARCHITEKTURA STYLÓW NEON (FULL PRO)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    .neon-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 35px; border-radius: 25px; border: 1px solid #30363d; 
        margin-bottom: 40px; min-height: 1000px; width: 100%;
        transition: 0.3s ease-in-out;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 20px rgba(0,255,136,0.2); }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 20px rgba(255,75,75,0.2); }
    .hold { border: 1px solid #30363d !important; }
    
    .neon-label { font-size: 0.85rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1.5px; display: block; }
    .neon-value { font-size: 1.2rem; font-weight: 900; color: #ffffff; margin-bottom: 12px; display: block; }
    
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.5rem; text-shadow: 0 0 10px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.5rem; text-shadow: 0 0 10px #ff4b4b; }
    
    .pos-calc-box { 
        background: rgba(88, 166, 255, 0.08); padding: 20px; border-radius: 15px; 
        border: 1px solid #58a6ff; margin: 20px 0; text-align: center;
    }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.85rem; display: block; margin-bottom: 8px; text-align: left; }
    .block-container { max-width: 98% !important; padding-top: 1.5rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. PANCERNY SILNIK ANALITYCZNY (ZABEZPIECZENIE DANYCH)
# ==============================================================================
def fetch_monster_analysis(symbol):
    try:
        time.sleep(0.15) # Delay dla stabilności API Yahoo
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        
        # Pobieramy 2 lata danych by wszystkie SMA były stabilne
        df_raw = t.history(period="2y", interval="1d", auto_adjust=False)
        if df_raw.empty or len(df_raw) < 200: return None
        
        # Fix cen groszowych i braków danych
        df_raw['Close'] = df_raw['Close'].replace(0, np.nan).ffill()
        c = df_raw['Close']
        curr = c.iloc[-1]
        
        # 1. Średnie Kroczące (Full Matrix)
        s20 = c.rolling(20).mean().iloc[-1]
        s50 = c.rolling(50).mean().iloc[-1]
        s100 = c.rolling(100).mean().iloc[-1]
        s200 = c.rolling(200).mean().iloc[-1]
        
        # 2. RSI (14)
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-12)))).iloc[-1]
        
        # 3. MACD
        e12 = c.ewm(span=12).mean(); e26 = c.ewm(span=26).mean()
        macd = (e12 - e26).iloc[-1]
        
        # 4. Pivot Points i Ekstrema 52T
        prev = df_raw.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        h52, l52 = df_raw['High'].tail(252).max(), df_raw['Low'].tail(252).min()
        
        # 5. Risk Management (ATR Based Position Sizing)
        tr = pd.concat([df_raw['High']-df_raw['Low'], (df_raw['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        
        # Pozycja i Poziomy SL/TP
        sh = int(risk_money / (atr * 1.5)) if atr > 0 else 0
        sl = curr - (atr * 1.5)
        tp = curr + (atr * 3.5)

        # 6. Logika Werdyktu Neonowego
        if rsi < 35 and curr > s200: v_text, v_class = "KUP 🔥", "buy"
        elif rsi > 65 or curr < s200 * 0.95: v_text, v_class = "SPRZEDAJ ⚠️", "sell"
        else: v_text, v_class = "TRZYMAJ ⏳", "hold"

        # 7. Bezpieczne Newsy
        m_news = []
        try:
            raw_n = t.news
            if raw_n:
                for n in raw_n[:3]:
                    title = n.get('title')
                    if title: m_news.append({"t": str(title)[:60], "l": n.get('link', '#')})
        except: pass

        return {
            "s": s, "p": curr, "rsi": rsi, "macd": macd, "pp": pp, "h52": h52, "l52": l52,
            "sh": sh, "sl": sl, "tp": tp, "s20": s20, "s50": s50, "s100": s100, "s200": s200,
            "df": df_raw.tail(100), "v": v_text, "vc": v_class, "news": m_news, "atr": atr
        }
    except: return None

# ==============================================================================
# 4. MODUŁ AI STRATEGY (BEZ UCINANIA)
# ==============================================================================
def get_ai_strategy(r):
    if not client: return "Brak klucza OpenAI w skrytce Secrets."
    prompt = f"""Ekspert Giełdowy. Analiza {r['s']}:
    Cena: {r['p']:.6f}, RSI: {r['rsi']:.1f}, Pivot: {r['pp']:.4f}, SMA200: {r['s200']:.4f}, ATR: {r['atr']:.6f}.
    Zadanie: Podaj rygorystyczny SL, TP i 3 konkretne punkty strategii wejścia/wyjścia. 
    BEZ LANIA WODY. Język polski. Max 150 słów."""
    try:
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=500)
        return res.choices[0].message.content
    except: return "AI jest chwilowo niedostępne (limit zapytań)."

# ==============================================================================
# 5. RENDEROWANIE INTERFEJSU (STABILNY GRID)
# ==============================================================================
def main():
    with st.sidebar:
        st.title("🚜 KONTROLA MONSTERA")
        st.write(f"Aktualizacja: {datetime.now().strftime('%H:%M:%S')}")
        
        # Regulacja odświeżania (Fix dla 48 spółek)
        ref_val = st.slider("Odświeżanie (min):", 1, 15, 5)
        st_autorefresh(interval=ref_val * 60000, key="data_refresh")
        
        t_in = st.text_area("Lista Tickerów (CSV):", load_tickers(), height=250)
        st.session_state.risk_cap = st.number_input("Kapitał Portfela (PLN):", value=st.session_state.risk_cap)
        st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%):", 0.1, 5.0, st.session_state.risk_pct)
        
        if st.button("💾 ZAPISZ I KOMPILUJ"):
            with open(DB_FILE, "w") as f: f.write(t_in)
            st.rerun()

    symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
    
    # SYSTEM ZAKŁADEK (By uniknąć błędu removeChild przy 48 interaktywnych wykresach)
    st.subheader(f"🚜 Kombajn: Analiza {len(symbols)} spółek")
    num_groups = (len(symbols) // 6) + (1 if len(symbols) % 6 > 0 else 0)
    tabs = st.tabs([f"Grupa {i+1}" for i in range(num_groups)])
    
    for i, tab in enumerate(tabs):
        with tab:
            batch = symbols[i*6 : (i+1)*6]
            # Wielowątkowość dla szybkości ładowania
            with ThreadPoolExecutor(max_workers=6) as executor:
                results = [r for r in list(executor.map(fetch_monster_analysis, batch)) if r]
            
            cols = st.columns(3)
            for idx, r in enumerate(results):
                with cols[idx % 3]:
                    with st.container():
                        st.markdown(f"""
                        <div class="neon-card {r['vc']}">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:1.5rem; font-weight:900;">{r['s']}</span>
                                <span class="sig-{r['vc']}">{r['v']}</span>
                            </div>
                            <h1 style="color:#58a6ff; font-size:3.5rem; margin:15px 0;">{r['p']:.6f}</h1>
                            
                            <div class="pos-calc-box">
                                <span class="neon-label">Wielkość Pozycji</span>
                                <span style="font-size:2rem; font-weight:900; color:#ffffff;">{r['sh']} SZT.</span><br>
                                <small style="color:#ff4b4b;">STOP LOSS: {r['sl']:.6f}</small> | <small style="color:#00ff88;">TAKE PROFIT: {r['tp']:.6f}</small>
                            </div>

                            <div class="metric-grid">
                                <div><span class='neon-label'>RSI (14)</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                                <div><span class='neon-label'>MACD</span><span class='neon-value'>{r['macd']:.4f}</span></div>
                                <div><span class='neon-label'>Pivot Point</span><span class='neon-value'>{r['pp']:.4f}</span></div>
                                <div><span class='neon-label'>SMA 200</span><span class='neon-value'>{r['s200']:.4f}</span></div>
                                <div><span class='neon-label'>Max 52T</span><span class='neon-value'>{r['h52']:.4f}</span></div>
                                <div><span class='neon-label'>SMA 50</span><span class='neon-value'>{r['s50']:.4f}</span></div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Wykres Świecowy (Powiększony i stabilny)
                        fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                        fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}_{i}", config={'displayModeBar': False})
                        
                        if st.button(f"🤖 RAPORT AI {r['s']}", key=f"btn_ai_{r['s']}"):
                            st.info(get_ai_strategy(r))
                        
                        st.markdown("<span class='neon-label' style='margin-top:20px;'>Newsy Rynkowe</span>", unsafe_allow_html=True)
                        for n in r['news']:
                            st.markdown(f"<a class='news-link' href='{n['l']}' target='_blank'>● {n['t']}</a>", unsafe_allow_html=True)
                        
                        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br><hr><center><small style='color:#333;'>AI ALPHA MONSTER PRO v87 ULTRA © 2026</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
