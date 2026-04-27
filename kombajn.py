import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
import time

# --- 1. KONFIGURACJA I SEKRETY ---
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS"
        except: return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS"

st.set_page_config(page_title="AI ALPHA GOLDEN v46 ULTIMATE", page_icon="🚜", layout="wide")

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. PEŁNE STYLE CSS (NEON DARK MODE) ---
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; }
    .top-mini-tile {
        padding: 12px; border-radius: 10px; text-align: center;
        background: #0d1117; border: 1px solid #30363d; margin-bottom: 5px;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); }
    
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 20px; border-radius: 15px; border: 1px solid #30363d; 
        text-align: center; min-height: 600px; transition: 0.3s;
    }
    .main-card:hover { border-color: #58a6ff; transform: translateY(-3px); }
    
    .sig-buy { color: #00ff88; font-weight: bold; font-size: 1.1rem; text-shadow: 0 0 5px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: bold; font-size: 1.1rem; text-shadow: 0 0 5px #ff4b4b; }
    
    .pos-calc { background: rgba(88, 166, 255, 0.1); border-radius: 10px; padding: 10px; margin: 10px 0; border: 1px solid #58a6ff; }
    .tech-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; font-size: 0.75rem; text-align: left; }
    .tech-row { border-bottom: 1px solid #21262d; padding: 2px 0; display: flex; justify-content: space-between; }
    
    .ai-box { padding: 10px; border-radius: 8px; margin-top: 10px; font-size: 0.8rem; background: #161b22; border-left: 3px solid #58a6ff; line-height: 1.3; }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.7rem; display: block; margin-top: 4px; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALITYCZNY (ALL INDICATORS) ---
def get_full_analysis(symbol):
    try:
        time.sleep(0.3) 
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df = t.history(period="250d", interval="1d")
        if df.empty or len(df) < 50: return None
        
        price = float(df['Close'].iloc[-1])
        
        # Srednie i Wstęgi
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        std = df['Close'].rolling(20).std().iloc[-1]
        b_upper = ema20 + (std * 2)
        b_lower = ema20 - (std * 2)
        
        # MACD
        exp1 = df['Close'].ewm(span=12).mean()
        exp2 = df['Close'].ewm(span=26).mean()
        macd = (exp1 - exp2).iloc[-1]
        signal_line = (exp1 - exp2).ewm(span=9).mean().iloc[-1]
        
        # Pivot & RSI
        hp, lp, cp = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pivot = (hp + lp + cp) / 3
        delta = df['Close'].diff()
        gain, loss = (delta.where(delta > 0, 0)).rolling(14).mean(), (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Risk & ATR
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        shares = int(risk_money / (atr * 1.5)) if atr > 0 else 0
        
        # Newsy rynkowe
        news = []
        try:
            for n in t.news[:2]: news.append({"t": n.get('title')[:55], "l": n.get('link')})
        except: pass

        v_type = "neutral"
        if rsi < 32 and price > b_lower: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68 or price > b_upper: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        ai_msg = "Wpisz OpenAI Key w Secrets"
        if AI_KEY:
            try:
                client = OpenAI(api_key=AI_KEY)
                res = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": f"Analiza techniczna {s}: RSI {rsi:.0f}, MACD {macd:.2f}, Cena {price}. Napisz 1 konkretne zdanie bez lania wody."}], max_tokens=35)
                ai_msg = res.choices.message.content
            except: ai_msg = "AI Offline"

        return { 
            "s": s, "p": price, "rsi": rsi, "sma50": sma50, "sma200": sma200, "ema20": ema20,
            "pivot": pivot, "macd": macd, "sig": signal_line, "verd": verd, "vcl": vcl, "v_type": v_type, 
            "shares": shares, "sl": price - (atr*1.5), "tp": price + (atr*3), "ai": ai_msg, 
            "news": news, "df": df.tail(40), "val": shares * price 
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 ALPHA ULTIMATE")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
    ticker_area = st.text_area("Lista spółek:", value=load_tickers(), height=200)
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.rerun()
    refresh = st.select_slider("Auto-refresh (s)", options=, value=60)

st_autorefresh(interval=refresh * 1000, key="v46_refresh")

# --- 5. WYŚWIETLANIE ---
tickers = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]
data_ready = []
pbar = st.progress(0)
for i, t in enumerate(tickers):
    res = get_full_analysis(t); data_ready.append(res) if res else None
    pbar.progress((i + 1) / len(tickers))

if data_ready:
    # --- TOP 10 TERMINAL ---
    st.subheader("🏆 TOP 10 RANKING OKAZJI (RSI/TREND)")
    top_10 = sorted(data_ready, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for idx, d in enumerate(top_10):
        with t_cols[idx % 5]:
            b_cls = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""<div class="top-mini-tile {b_cls}"><b>{d['s']}</b> | {d['p']:.2f}<br><small>RSI: {d['rsi']:.0f}</small> | <b class="{d['vcl']}">{d['verd']}</b></div>""", unsafe_allow_html=True)
    
    st.divider()
    
    # --- LISTA GŁÓWNA ---
    for i in range(0, len(data_ready), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                accent = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {accent};">
                    <div style="font-size:1.6rem; font-weight:bold;">{d['s']}</div>
                    <div style="color:#58a6ff; font-size:1.2rem;">{d['p']:.2f} PLN</div>
                    <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    <div class="pos-calc">KUP: {d['shares']} szt.<br><small>{d['val']:.0f} PLN</small></div>
                    <div class="tech-grid">
                        <div class="tech-row"><span>SMA200:</span><b>{d['sma200']:.2f}</b></div>
                        <div class="tech-row"><span>EMA20:</span><b>{d['ema20']:.2f}</b></div>
                        <div class="tech-row"><span>PIVOT:</span><b>{d['pivot']:.2f}</b></div>
                        <div class="tech-row"><span>MACD:</span><b>{d['macd']:.2f}</b></div>
                        <div class="tech-row"><span>RSI:</span><b>{d['rsi']:.0f}</b></div>
                    </div>
                    <div class="ai-box"><b>🤖 AI:</b> {d['ai']}</div>
                    <div style="text-align:left; border-top:1px dashed #30363d; margin-top:10px; padding-top:5px;">
                        <b>📢 NEWS:</b>
                        {"".join([f'<a class="news-link" href="{n["l"]}" target="_blank">• {n["t"]}</a>' for n in d['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander("Analiza Wykresu"):
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False); st.plotly_chart(fig, use_container_width=True)
