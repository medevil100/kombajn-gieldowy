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
# SEKCJA 1: KONFIGURACJA ŚRODOWISKA I BAZY DANYCH
# ==============================================================================
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BDRX, BNOX, BOLT"
        except Exception: pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BDRX, BNOX, BOLT"

st.set_page_config(page_title="AI ALPHA GOLDEN v71 MONSTER PRO", page_icon="🚜", layout="wide")

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# ==============================================================================
# SEKCJA 2: ROZBUDOWANA ARCHITEKTURA STYLÓW CSS (TWOJE NEONY)
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .top-mini-tile {
        padding: 15px; border-radius: 12px; text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505); 
        border: 1px solid #30363d; margin-bottom: 15px; transition: 0.3s ease;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.3); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.3); }
    
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        text-align: center; min-height: 1000px; transition: 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        display: flex; flex-direction: column; justify-content: space-between; margin-bottom: 30px;
    }
    .main-card:hover { border-color: #58a6ff; transform: translateY(-10px); box-shadow: 0 20px 50px rgba(88, 166, 255, 0.15); }
    
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.5rem; text-transform: uppercase; text-shadow: 0 0 12px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.5rem; text-transform: uppercase; text-shadow: 0 0 12px #ff4b4b; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.3rem; }
    
    .pos-calc-box { background: rgba(88, 166, 255, 0.08); border-radius: 15px; padding: 20px; margin: 20px 0; border: 1px solid #58a6ff; color: #58a6ff; }
    .pos-val { font-size: 2rem; display: block; margin-bottom: 5px; font-weight: 900; text-shadow: 0 0 10px #58a6ff; }
    .pos-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 2px; }
    
    .tech-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: rgba(255,255,255,0.02); padding: 20px; border-radius: 15px; text-align: left; }
    .tech-row { border-bottom: 1px solid #21262d; padding: 8px 0; font-size: 0.95rem; display: flex; justify-content: space-between; }
    .t-lab { color: #8b949e; }
    .t-val { color: #ffffff; font-weight: bold; }
    
    .ai-strategy-box { padding: 20px; border-radius: 15px; margin-top: 25px; font-size: 1rem; background: rgba(0, 255, 136, 0.05); border: 1px solid #00ff88; line-height: 1.6; text-align: left; color: #00ff88; }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.85rem; display: block; margin-bottom: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .news-link:hover { color: #ffffff; text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# SEKCJA 3: PANCERNY SILNIK ANALITYCZNY (Z TWOIM SMA I FIXEM TP/SL)
# ==============================================================================
def get_monster_analysis(symbol):
    try:
        time.sleep(0.15)
        s = symbol.strip().upper()
        ticker_obj = yf.Ticker(s)
        
        # Pobieranie RAW dla precyzji penny stocks
        df_raw = ticker_obj.history(period="2y", interval="1d", auto_adjust=False)
        if df_raw.empty or len(df_raw) < 150: return None
        
        df_raw['Close'] = df_raw['Close'].replace(0, np.nan).ffill()
        c = df_raw['Close']
        curr_price = float(c.iloc[-1])
        
        # Średnie (Twoja logika SMA)
        sma20 = c.rolling(20).mean().iloc[-1]
        sma50 = c.rolling(50).mean().iloc[-1]
        sma100 = c.rolling(100).mean().iloc[-1]
        sma200 = c.rolling(200).mean().iloc[-1]
        
        # RSI 14
        delta = c.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi_val = 100 - (100 / (1 + (g / (l + 1e-12)))).iloc[-1]
        
        # MACD
        exp12 = c.ewm(span=12).mean(); exp26 = c.ewm(span=26).mean()
        macd_val = (exp12 - exp26).iloc[-1]
        
        # Pivot Points i Ekstrema
        prev_day = df_raw.iloc[-2]
        pivot = (prev_day['High'] + prev_day['Low'] + prev_day['Close']) / 3
        h52, l52 = df_raw['High'].tail(252).max(), df_raw['Low'].tail(252).min()
        
        # ATR i Position Sizing (TWOJA LOGIKA FIX)
        tr = pd.concat([df_raw['High']-df_raw['Low'], (df_raw['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        risk_pln = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_margin = atr * 1.5 
        
        if sl_margin > 0:
            shares = int(risk_pln / sl_margin)
            max_shares = int(st.session_state.risk_cap / curr_price) if curr_price > 0 else 0
            shares = min(shares, max_shares)
        else: shares = 0
            
        market_news = []
        try:
            for n in ticker_obj.news[:3]: market_news.append({"title": n.get('title', '')[:65], "link": n.get('link', '#')})
        except: pass

        # Werdykt
        if rsi_val < 32: verd_text, verd_class, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 68: verd_text, verd_class, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd_text, verd_class, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        return {
            "symbol": s, "price": curr_price, "rsi": rsi_val, "sma20": sma20, "sma50": sma50, "sma100": sma100, "sma200": sma200,
            "pivot": pivot, "macd": macd_val, "verdict": verd_text, "v_class": verd_class, "v_type": v_type, 
            "shares": shares, "sl": curr_price - sl_margin, "tp": curr_price + (atr * 3.5), 
            "h52": h52, "l52": l52, "news": market_news, "df": df_raw.tail(60)
        }
    except: return None

# ==============================================================================
# SEKCJA 4: INTERFEJS I RENDEROWANIE (TWOJA STRUKTURA)
# ==============================================================================
st.sidebar.title("🚜 MONSTER v71 PRO")
t_area = st.sidebar.text_area("Symbole (CSV):", load_tickers(), height=250)
st.session_state.risk_cap = st.sidebar.number_input("Kapitał (PLN):", value=st.session_state.risk_cap)
st.session_state.risk_pct = st.sidebar.slider("Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct)

if st.sidebar.button("💾 ZAPISZ I ANALIZUJ"):
    with open(DB_FILE, "w") as f: f.write(t_area)
    st.rerun()

st_autorefresh(interval=600000, key="monster_refresh")
ticker_list = [t.strip().upper() for t in t_area.split(",") if t.strip()]

with ThreadPoolExecutor(max_workers=8) as executor:
    results = [r for r in list(executor.map(get_monster_analysis, ticker_list)) if r]

# --- RENDEROWANIE TOP MINI-KAFELKÓW ---
if results:
    st.subheader("🔥 TOP SYGNAŁY (Najniższe RSI)")
    top_cols = st.columns(5)
    for i, r in enumerate(sorted(results, key=lambda x: x['rsi'])[:10]):
        with top_cols[i % 5]:
            st.markdown(f"""<div class="top-mini-tile tile-{r['v_type']}"><b>{r['symbol']}</b><br>{r['price']:.4f}<br><small>{r['verdict']}</small></div>""", unsafe_allow_html=True)

    st.divider()

    # --- GŁÓWNA LISTA ---
    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"""
                <div class="main-card">
                    <div>
                        <h2 style="margin:0;">{r['symbol']}</h2>
                        <h1 style="color:#58a6ff; margin:10px 0;">{r['price']:.6f}</h1>
                        <div class="{r['v_class']}">{r['verdict']}</div>
                    </div>
                    
                    <div class="pos-calc-box">
                        <span class="pos-label">WIELKOŚĆ POZYCJI</span>
                        <span class="pos-val">{r['shares']} SZT.</span>
                        <small>SL: {r['sl']:.6f} | TP: {r['tp']:.6f}</small>
                    </div>

                    <div class="tech-grid">
                        <div class="tech-row"><span class="t-lab">RSI (14)</span><span class="t-val">{r['rsi']:.1f}</span></div>
                        <div class="tech-row"><span class="t-lab">SMA 200</span><span class="t-val">{r['sma200']:.4f}</span></div>
                        <div class="tech-row"><span class="t-lab">Pivot</span><span class="t-val">{r['pivot']:.4f}</span></div>
                        <div class="tech-row"><span class="t-lab">SMA 50</span><span class="t-val">{r['sma50']:.4f}</span></div>
                        <div class="tech-row"><span class="t-lab">Max 52T</span><span class="t-val">{r['h52']:.4f}</span></div>
                        <div class="tech-row"><span class="t-lab">Min 52T</span><span class="t-val">{r['l52']:.4f}</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Wykres Plotly (Unikalny key usuwa błąd removeChild)
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['symbol']}_{idx}")
                
                if client and st.button(f"🤖 STRATEGIA AI {r['symbol']}", key=f"ai_{r['symbol']}_{idx}"):
                    prompt = f"Analiza {r['symbol']}: Cena {r['price']:.6f}, RSI {r['rsi']:.1f}, Pivot {r['pivot']:.4f}. Podaj konkretny plan 3 pkt."
                    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}])
                    st.markdown(f'<div class="ai-strategy-box">{res.choices[0].message.content}</div>', unsafe_allow_html=True)
                
                st.markdown("<div style='text-align:left; margin-top:20px;'><span class='t-lab'>NEWSY:</span></div>", unsafe_allow_html=True)
                for n in r['news']:
                    st.markdown(f"<a class='news-link' href='{n['link']}' target='_blank'>● {n['title']}</a>", unsafe_allow_html=True)
                
                st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<center><small style='color:#333;'>AI ALPHA MONSTER PRO v71 ULTRA © 2026</small></center>", unsafe_allow_html=True)
