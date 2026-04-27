import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time

# --- 1. KONFIGURACJA PLIKÓW I PAMIĘCI ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA, TSLA"
        except: return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA, TSLA"

# Konfiguracja strony
st.set_page_config(page_title="AI ALPHA GOLDEN v43 MAXI PRO", page_icon="🚜", layout="wide")

# Inicjalizacja stanów sesji (pamięć klucza i kapitału)
if 'api_key' not in st.session_state: st.session_state.api_key = ""
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. PEŁNA BIBLIOTEKA STYLÓW CSS (Przywrócenie 100% wyglądu) ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    
    /* Karta spółki i kafelki */
    .top-tile { 
        background: linear-gradient(145deg, #0d1117, #050505); 
        padding: 20px; border-radius: 15px; border: 1px solid #30363d; 
        text-align: center; min-height: 520px; transition: 0.3s;
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .top-tile:hover { border-color: #58a6ff; transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0,0,0,0.6); }
    
    /* Sygnały i Kolory */
    .sig-buy { color: #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 6px 12px; border-radius: 10px; background: rgba(0, 255, 136, 0.1); display: inline-block; font-size: 1.1rem; }
    .sig-sell { color: #ff4b4b; font-weight: bold; border: 2px solid #ff4b4b; padding: 6px 12px; border-radius: 10px; background: rgba(255, 75, 75, 0.1); display: inline-block; font-size: 1.1rem; }
    .sig-neutral { color: #8b949e; font-weight: bold; border: 1px solid #30363d; padding: 6px 12px; border-radius: 10px; display: inline-block; }
    
    /* Kalkulator Ryzyka */
    .pos-calc { 
        background: rgba(88, 166, 255, 0.12); border-radius: 12px; padding: 15px; 
        margin: 15px 0; border: 1px solid rgba(88, 166, 255, 0.4); color: #58a6ff; 
    }
    .pos-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    
    /* Dane Techniczne */
    .tech-grid { 
        display: grid; grid-template-columns: 1fr 1fr; gap: 10px; 
        background: rgba(255,255,255,0.03); padding: 12px; border-radius: 10px; text-align: left;
    }
    .tech-row { border-bottom: 1px solid #21262d; padding: 4px 0; font-size: 0.8rem; display: flex; justify-content: space-between; }
    .tech-n { color: #8b949e; }
    .tech-v { color: #ffffff; font-weight: bold; }
    
    /* AI Box i News */
    .ai-box { 
        padding: 12px; border-radius: 10px; margin-top: 15px; font-size: 0.85rem; 
        min-height: 80px; border-left: 4px solid #58a6ff; background: rgba(88, 166, 255, 0.05);
        display: flex; align-items: center; justify-content: center; font-style: italic;
    }
    .news-container { margin-top: 15px; text-align: left; border-top: 1px dashed #30363d; padding-top: 10px; }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.75rem; display: block; margin-bottom: 6px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    .news-link:hover { text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. PEŁNY SILNIK ANALITYCZNY ---
def get_analysis(symbol):
    try:
        s = symbol.strip().upper()
        ticker = yf.Ticker(s)
        # Pobieramy 250 dni, aby SMA200 było stabilne
        df = ticker.history(period="250d", interval="1d")
        
        if df.empty or len(df) < 200: return None
        
        price = float(df['Close'].iloc[-1])
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # Pivot Points (Standard)
        prev = df.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        
        # RSI 14
        delta = df['Close'].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ema_up = up.rolling(window=14).mean()
        ema_down = down.rolling(window=14).mean()
        rs = ema_up / (ema_down + 1e-9)
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        # ATR i Zarządzanie Ryzykiem
        high_low = df['High'] - df['Low']
        high_cp = (df['High'] - df['Close'].shift()).abs()
        low_cp = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Kalkulacja pozycji w PLN
        r_pln = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_d = atr * 1.6 # 1.6x ATR jako bezpieczny Stop Loss
        shares = int(r_pln / sl_d) if sl_d > 0 else 0
        
        # Newsy (Safe Fetch)
        news_items = []
        try:
            raw_news = ticker.news
            if raw_news:
                for n in raw_news[:2]:
                    news_items.append({"title": n.get('title', '')[:60]+"...", "url": n.get('link', '#')})
        except: pass
        if not news_items: news_items = [{"title": "Brak bieżących newsów", "url": "#"}]

        # Werdykt
        if rsi < 32: verd, vcl, vt = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, vt = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, vt = "CZEKAJ ⏳", "sig-neutral", "neutral"

        # AI (Analiza OpenAI)
        ai_msg = "Wpisz klucz w Sidebar"
        if st.session_state.api_key:
            try:
                client = OpenAI(api_key=st.session_state.api_key)
                resp = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": f"Symbol: {s}, RSI: {rsi:.0f}, Cena: {price}. Napisz 1 zdanie analizy."}],
                    max_tokens=35
                )
                ai_msg = resp.choices.message.content
            except: ai_msg = "AI Offline / Limit"

        return {
            "s": s, "p": price, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "pivot": pivot, "verd": verd, "vcl": vcl, "vt": vt, "shares": shares,
            "sl": price - sl_d, "tp": price + (atr * 3.5), "ai": ai_msg,
            "news": news_items, "df": df.tail(60), "val": shares * price
        }
    except: return None

# --- 4. PANEL BOCZNY (PEŁNY SIDEBAR) ---
with st.sidebar:
    st.title("🚜 GOLDEN v43 PRO")
    st.markdown("---")
    st.session_state.api_key = st.text_input("OpenAI Key", value=st.session_state.api_key, type="password")
    
    st.subheader("💰 KONFIGURACJA PLN")
    st.session_state.risk_cap = st.number_input("Kapitał Portfela (PLN)", value=st.session_state.risk_cap, step=5000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na transakcję (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    st.subheader("📝 LISTA OBSERWOWANYCH")
    ticker_input = st.text_area("Symbole (np. PKO.WA, BTC-USD):", value=load_tickers(), height=180)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_input)
        st.cache_data.clear()
        st.success("Baza zaktualizowana!")
        st.rerun()
    
    ref_sec = st.select_slider("Auto-odświeżanie (s)", options=[30, 60, 120, 300, 600], value=60)

st_autorefresh(interval=ref_sec * 1000, key="v43_refresh")

# --- 5. LOGIKA WYŚWIETLANIA I RENDEROWANIE ---
tickers = [x.strip().upper() for x in ticker_input.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=ref_sec)
def fetch_data_parallel(t_list):
    with ThreadPoolExecutor(max_workers=10) as executor:
        return [r for r in executor.map(get_analysis, t_list) if r is not None]

data = fetch_data_parallel(tickers)

if data:
    st.subheader(f"🚀 TERMINAL ALPHA MAXI - {datetime.now().strftime('%H:%M:%S')}")
    
    for i in range(0, len(data), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data[i:i+5]):
            with cols[idx]:
                # Kolorystyka zależna od trendu/sygnału
                accent = "#00ff88" if d['vt'] == "buy" else "#ff4b4b" if d['vt'] == "sell" else "#30363d"
                
                st.markdown(f"""
                <div class="top-tile" style="border: 2px solid {accent};">
                    <div>
                        <div style="font-size:1.6rem; font-weight:bold; letter-spacing:-1px;">{d['s']}</div>
                        <div style="color:#58a6ff; font-size:1.3rem;">{d['p']:.2f} <small>PLN</small></div>
                        <div style="margin: 20px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    </div>
                    
                    <div class="pos-calc">
                        <div class="pos-label">Ilość do kupna:</div>
                        <div style="font-size:1.5rem; font-weight:bold;">{d['shares']} <small>szt.</small></div>
                        <div style="font-size:0.8rem; opacity:0.8;">Wartość: {d['val']:.0f} PLN</div>
                    </div>
                    
                    <div class="tech-grid">
                        <div class="tech-row"><span class="tech-n">SMA50:</span><span class="tech-v">{d['sma50']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">SMA200:</span><span class="tech-v">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">PIVOT:</span><span class="tech-v">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">RSI:</span><span class="tech-v">{d['rsi']:.0f}</span></div>
                    </div>
                    
                    <div class="ai-box">
                        {d['ai']}
                    </div>
                    
                    <div class="news-container">
                        <a href="{d['news'][0]['url']}" class="news-link" target="_blank">• {d['news'][0]['title']}</a>
                        {('<a href="'+d['news'][1]['url']+'" class="news-link" target="_blank">• '+d['news'][1]['title']+'</a>') if len(d['news']) > 1 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("📊 WYKRES I POZIOMY"):
                    st.write(f"**Stop Loss:** {d['sl']:.2f} | **Take Profit:** {d['tp']:.2f}")
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'], name="Cena")])
                    fig.add_trace(go.Scatter(x=d['df'].index, y=d['df']['Close'].rolling(50).mean(), line=dict(color='orange', width=1.5), name="SMA50"))
                    fig.add_trace(go.Scatter(x=d['df'].index, y=d['df']['Close'].rolling(200).mean(), line=dict(color='red', width=2), name="SMA200"))
                    fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Błąd pobierania danych. Sprawdź symbole lub połączenie.")

st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:50px;'>v43.0 MAXI PRO | {datetime.now().year}</div>", unsafe_allow_html=True)
