import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA PLIKÓW I SEKRETY ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
        except: return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
    return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"

st.set_page_config(page_title="AI ALPHA GOLDEN v42 FULL", page_icon="🚜", layout="wide")

# Trwałe przechowywanie klucza w sesji
if 'api_key' not in st.session_state:
    st.session_state.api_key = st.secrets.get("OPENAI_API_KEY", "")
if 'risk_cap' not in st.session_state:
    st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state:
    st.session_state.risk_pct = 1.0

# --- 2. PEŁNA BIBLIOTEKA STYLÓW CSS (Przywrócenie wyglądu) ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .top-tile { 
        text-align: center; padding: 20px; border-radius: 15px; 
        background: linear-gradient(145deg, #0d1117, #050505); 
        min-height: 480px; border: 1px solid #30363d; transition: 0.3s;
    }
    .top-tile:hover { transform: translateY(-5px); border-color: #58a6ff; box-shadow: 0 10px 20px rgba(0,0,0,0.5); }
    .sig-buy { color: #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 8px; background: rgba(0,255,136,0.1); }
    .sig-sell { color: #ff4b4b; font-weight: bold; border: 2px solid #ff4b4b; padding: 5px 15px; border-radius: 8px; background: rgba(255,75,75,0.1); }
    .sig-neutral { color: #8b949e; font-weight: bold; border: 1px solid #30363d; padding: 5px 15px; border-radius: 8px; }
    .pos-calc { background: rgba(88, 166, 255, 0.1); border-radius: 10px; padding: 12px; margin: 15px 0; border: 1px solid #58a6ff; color: #58a6ff; font-weight: bold; }
    .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.8rem; text-align: left; margin-top: 10px; }
    .stat-item { border-bottom: 1px solid #21262d; padding: 4px 0; color: #c9d1d9; }
    .ai-box { padding: 12px; border-radius: 10px; margin-top: 15px; font-size: 0.85rem; background: rgba(255,255,255,0.03); min-height: 70px; line-height: 1.4; border-left: 4px solid #58a6ff; }
    .news-box { font-size: 0.75rem; color: #8b949e; text-align: left; margin-top: 15px; border-top: 1px dashed #30363d; padding-top: 10px; }
    .news-link { color: #58a6ff; text-decoration: none; display: block; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ROZBUDOWANY SILNIK ANALIZY (SZYBKI) ---
def get_analysis(symbol):
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df = t.history(period="250d", interval="1d")
        
        if df.empty or len(df) < 50: return None
        
        price = float(df['Close'].iloc[-1])
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # Pivot Klasyczny
        hp, lp, cp = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pivot = (hp + lp + cp) / 3
        
        # RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR i Zarządzanie Ryzykiem
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.6
        shares = int(risk_money / sl_dist) if sl_dist > 0 else 0
        
        # Bezpieczne pobieranie newsów
        news_list = []
        try:
            raw = t.news
            if raw:
                for n in raw[:2]:
                    news_list.append({"t": n.get('title', '')[:55] + "...", "l": n.get('link', '#')})
        except: pass
        if not news_list: news_list = [{"t": "Brak info rynkowego", "l": "#"}]

        # Sygnał
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        # AI (Tylko jeśli jest klucz)
        ai_txt = "Podaj klucz AI w Sidebar"
        if st.session_state.api_key:
            try:
                client = OpenAI(api_key=st.session_state.api_key)
                res = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": f"Analiza {s}: RSI {rsi:.0f}, Cena {price}. Napisz 1 konkretne zdanie."}],
                    max_tokens=35
                )
                ai_txt = res.choices[0].message.content
            except: ai_txt = "AI Limit / Error"

        return {
            "s": s, "p": price, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "pivot": pivot, "verd": verd, "vcl": vcl, "v_type": v_type, 
            "shares": shares, "sl": price - sl_dist, "tp": price + (atr * 3), 
            "ai": ai_txt, "news": news_list, "df": df.tail(50), "val": shares * price
        }
    except: return None

# --- 4. PANEL BOCZNY (PRZYCISK ZAPISZ) ---
with st.sidebar:
    st.title("🚜 GOLDEN v42 PRO")
    st.session_state.api_key = st.text_input("OpenAI Key", value=st.session_state.api_key, type="password")
    
    st.subheader("💰 PORTFEL (PLN)")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    st.subheader("📝 LISTA SYMBOLI")
    ticker_area = st.text_area("Symbole (np. PKO.WA, BTC-USD):", value=load_tickers(), height=200)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.success("Zapisano!")
        st.rerun()
    
    refresh = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v42_refresh")

# --- 5. LOGIKA GŁÓWNA (SZYBKA - MULTITHREADING) ---
tickers = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=refresh)
def fetch_fast(t_list):
    with ThreadPoolExecutor(max_workers=10) as executor:
        return [r for r in executor.map(get_analysis, t_list) if r is not None]

data_ready = fetch_fast(tickers)

if data_ready:
    st.subheader(f"🚀 TERMINAL ALPHA GOLDEN - {datetime.now().strftime('%H:%M:%S')}")
    
    for i in range(0, len(data_ready), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                border = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="top-tile" style="border: 2px solid {border};">
                    <div style="font-size:1.6rem; font-weight:bold;">{d['s']}</div>
                    <div style="color:#58a6ff; font-size:1.2rem; margin-bottom:10px;">{d['p']:.2f} PLN</div>
                    <div style="margin: 20px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    
                    <div class="pos-calc">KUP: {d['shares']} szt.<br><small>{d['val']:.0f} PLN</small></div>
                    
                    <div class="stat-grid">
                        <div class="stat-item"><b>SMA50:</b> {d['sma50']:.2f}</div>
                        <div class="stat-item"><b>SMA200:</b> {d['sma200']:.2f}</div>
                        <div class="stat-item"><b>PIVOT:</b> {d['pivot']:.2f}</div>
                        <div class="stat-item"><b>RSI:</b> {d['rsi']:.0f}</div>
                    </div>
                    
                    <div class="ai-box"><b>🤖 AI:</b> {d['ai']}</div>
                    
                    <div class="news-box">
                        <b>📢 INFO:</b><br>
                        <a class="news-link" href="{d['news'][0]['l']}" target="_blank">• {d['news'][0]['t']}</a>
                        {('<a class="news-link" href="'+d['news'][1]['l']+'" target="_blank">• '+d['news'][1]['t']+'</a>') if len(d['news']) > 1 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("Wykres i Poziomy"):
                    st.write(f"**SL:** {d['sl']:.2f} | **TP:** {d['tp']:.2f}")
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

st.markdown(f"<div style='text-align:center; color:gray; font-size:0.8rem; margin-top:50px;'>v42.0 MAXI FULL | Ryzyko: {st.session_state.risk_pct}%</div>", unsafe_allow_html=True)
