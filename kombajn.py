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
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. SILNIK PANCERNY (CORE ENGINE) - OBSŁUGA PENNY STOCKS I RATELIMITING
# ==============================================================================
st.set_page_config(page_title="IRONCLAD v85 QUANT", page_icon="🏦", layout="wide")
DB_FILE = "moje_spolki.txt"

# Pobieranie klucza OpenAI z bezpiecznej skrytki
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read().strip()
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BNOX, CMMB, DRMA, EVOK"

# --- SYSTEM STYLÓW IRON (STABILNY HTML/CSS) ---
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    .stApp { background-color: #020202; color: #dcdcdc; font-family: 'Inter', sans-serif; }
    .iron-card { 
        background: #0a0a0a; border: 1px solid #1e1e1e; padding: 25px; border-radius: 4px;
        margin-bottom: 30px; min-height: 1000px; width: 100%; transition: 0.1s;
    }
    .buy { border-top: 4px solid #00ff88 !important; box-shadow: 0 4px 20px rgba(0,255,136,0.1); }
    .sell { border-top: 4px solid #ff4b4b !important; box-shadow: 0 4px 20px rgba(255,75,75,0.1); }
    .hold { border-top: 4px solid #444 !important; }
    .label-quant { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #666; text-transform: uppercase; }
    .value-quant { font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 700; color: #eee; }
    .metric-container { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 15px 0; }
    .bid-ask-bar { background: #111; padding: 10px; border-radius: 2px; border-left: 3px solid #58a6ff; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. LOGIKA FINANSOWA (PIVOTY, ŚREDNIE, ATR, RSI, MACD)
# ==============================================================================
def iron_fetch(symbol):
    try:
        time.sleep(0.2) # Throttling przeciwko banom IP
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        
        # Pobieranie RAW bez auto_adjust dla precyzji Penny Stocks
        df = t.history(period="2y", interval="1d", auto_adjust=False)
        if df.empty or len(df) < 200: return None
        
        # Fix cen zerowych i NaN
        df['Close'] = df['Close'].replace(0, np.nan).ffill()
        c = df['Close']
        curr = float(c.iloc[-1])
        
        # 1. Średnie Kroczące (SMA 20, 50, 100, 200)
        s20 = c.rolling(20).mean().iloc[-1]
        s50 = c.rolling(50).mean().iloc[-1]
        s100 = c.rolling(100).mean().iloc[-1]
        s200 = c.rolling(200).mean().iloc[-1]
        
        # 2. RSI (14) - Klasyczny Algorytm
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(window=14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-12)))).iloc[-1]
        
        # 3. MACD (12, 26, 9)
        e12 = c.ewm(span=12, adjust=False).mean()
        e26 = c.ewm(span=26, adjust=False).mean()
        macd_line = (e12 - e26).iloc[-1]
        signal_line = (e12 - e26).ewm(span=9, adjust=False).mean().iloc[-1]
        
        # 4. Pivot Points (Floor Pivots)
        prev = df.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        r1 = (2 * pp) - prev['Low']; s1 = (2 * pp) - prev['High']
        
        # 5. Ekstrema 52T
        h52 = df['High'].tail(252).max()
        l52 = df['Low'].tail(252).min()
        
        # 6. Zarządzanie ryzykiem (ATR Based)
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs(), (df['Low']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        
        # Rozmiar pozycji: SL ustawiony na 1.5 ATR od ceny
        sl_dist = atr * 1.5
        sh = int(risk_val / sl_dist) if sl_dist > 0 else 0
        tp = curr + (atr * 3.5)
        sl = curr - sl_dist

        # Werdykt silnika
        if rsi < 32 and curr > s200: v, vc = "KUP 🔥", "buy"
        elif rsi > 68 or curr < s200 * 0.95: v, vc = "SPRZEDAJ ⚠️", "sell"
        else: v, vc = "TRZYMAJ ⏳", "hold"

        # Bezpieczne pobieranie newsów
        news = []
        try:
            raw_n = t.news[:3]
            for n in raw_n: news.append({"t": n.get('title', '')[:55], "l": n.get('link', '#')})
        except: pass

        return {
            "s": s, "p": curr, "rsi": rsi, "macd": macd_line, "pp": pp, "r1": r1, "s1": s1,
            "h52": h52, "l52": l52, "sh": sh, "sl": sl, "tp": tp, "atr": atr,
            "s20": s20, "s50": s50, "s100": s100, "s200": s200, "v": v, "vc": vc,
            "df": df.tail(60), "news": news
        }
    except Exception as e:
        return None

# ==============================================================================
# 3. INTERFEJS I GENEROWANIE RAPORTÓW AI
# ==============================================================================
def get_ai_quant(r):
    if not client: return "Błąd: Brak klucza OpenAI w Secrets."
    prompt = f"""[ANALIZA KWANTOWA {r['s']}]
    Cena: {r['p']:.6f}, RSI: {r['rsi']:.1f}, SMA200: {r['s200']:.6f}, MACD: {r['macd']:.6f}.
    Pivot: {r['pp']:.6f}, ATR: {r['atr']:.6f}.
    Zadanie: Podaj rygorystyczny plan wejścia/wyjścia. Konkretne SL/TP. Max 100 słów."""
    try:
        resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=400)
        return resp.choices[0].message.content
    except: return "AI timeout. Spróbuj ponownie."

# --- MAIN RENDERER ---
def main():
    with st.sidebar:
        st.title("🛡️ IRONCLAD v85")
        st.subheader("Konfiguracja Portfela")
        
        ref = st.slider("Interwał odświeżania (min)", 1, 15, 5)
        st_autorefresh(interval=ref * 60000, key="iron_ref")
        
        t_in = st.text_area("Lista Tickerów (CSV):", load_tickers(), height=250)
        st.session_state.risk_cap = st.number_input("Kapitał w PLN", value=st.session_state.risk_cap)
        st.session_state.risk_pct = st.slider("Ryzyko na transakcję (%)", 0.1, 5.0, st.session_state.risk_pct)
        
        if st.button("💾 ZAPISZ I KOMPILUJ DANE"):
            with open(DB_FILE, "w") as f: f.write(t_in)
            st.rerun()

    symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
    
    # Równoległe pobieranie danych (Speed Optimization)
    with ThreadPoolExecutor(max_workers=10) as exe:
        results = [r for r in list(exe.map(iron_fetch, symbols)) if r]

    st.markdown(f"### ⚡ ANALIZA IRONCLAD: {len(results)} AKTYWNYCH WALORÓW")

    # Siatka kart
    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"""
                <div class="iron-card {r['vc']}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:1.4rem; font-weight:900;">{r['s']}</span>
                        <span class="label-quant">{datetime.now().strftime('%H:%M')}</span>
                    </div>
                    <h1 style="color:#58a6ff; font-family:'JetBrains Mono'; margin:15px 0;">{r['p']:.6f}</h1>
                    <div style="font-size:1.2rem; font-weight:900; margin-bottom:20px;">{r['v']}</div>
                    
                    <div class="bid-ask-bar">
                        <span class="label-quant">Zarządzanie Pozycją</span><br>
                        <span style="font-size:1.3rem; font-weight:700;">{r['sh']} SZTUK</span><br>
                        <small style="color:#ff4b4b;">SL: {r['sl']:.6f}</small> | <small style="color:#00ff88;">TP: {r['tp']:.6f}</small>
                    </div>

                    <div class="metric-container">
                        <div><span class="label-quant">RSI (14)</span><br><span class="value-quant">{r['rsi']:.2f}</span></div>
                        <div><span class="label-quant">MACD</span><br><span class="value-quant">{r['macd']:.6f}</span></div>
                        <div><span class="label-quant">SMA 50</span><br><span class="value-quant">{r['s50']:.4f}</span></div>
                        <div><span class="label-quant">SMA 200</span><br><span class="value-quant">{r['s200']:.4f}</span></div>
                        <div><span class="label-quant">Pivot</span><br><span class="value-quant">{r['pp']:.6f}</span></div>
                        <div><span class="label-quant">High 52T</span><br><span class="value-quant">{r['h52']:.4f}</span></div>
                    </div>
                """, unsafe_allow_html=True)

                # Wykres Świecowy (Lżejszy Render)
                fig = go.Figure(data=[go.Candlestick(
                    x=r['df'].index, open=r['df']['Open'], high=r['df']['High'],
                    low=r['df']['Low'], close=r['df']['Close'], name="Cena"
                )])
                fig.update_layout(
                    template="plotly_dark", height=320, margin=dict(l=0,r=0,t=0,b=0),
                    xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}", config={'displayModeBar': False})
                
                if st.button(f"🔎 RAPORT KWANTOWY {r['s']}", key=f"ai_{r['s']}"):
                    st.markdown(f"<div style='background:#111; padding:15px; border-radius:5px; border:1px solid #333;'>{get_ai_quant(r)}</div>", unsafe_allow_html=True)

                st.markdown("<br><span class='label-quant'>Wiadomości Rynkowe</span>", unsafe_allow_html=True)
                for n in r['news']:
                    st.markdown(f"<small>● <a href='{n['l']}' style='color:#58a6ff; text-decoration:none;'>{n['t']}</a></small>", unsafe_allow_html=True)
                
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br><hr><center><small style='color:#444;'>IRONCLAD v85 QUANT TERMINAL | © 2026</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
