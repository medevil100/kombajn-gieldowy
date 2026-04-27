import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA PLIKÓW I SEKRETY ---
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
        except: return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"

st.set_page_config(page_title="AI ALPHA GOLDEN v48 FINAL", page_icon="🚜", layout="wide")

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. PEŁNA BIBLIOTEKA STYLÓW CSS (65 LINII) ---
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    /* TOP 10 Mini Kafelki */
    .top-mini-tile {
        padding: 12px; border-radius: 12px; text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505); 
        border: 1px solid #30363d; margin-bottom: 10px; transition: 0.3s;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); }
    
    /* Główne Karty */
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 25px; border-radius: 18px; border: 1px solid #30363d; 
        text-align: center; min-height: 640px; transition: 0.3s;
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .main-card:hover { border-color: #58a6ff; transform: translateY(-5px); box-shadow: 0 12px 40px rgba(0,0,0,0.6); }
    
    /* Sygnały */
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.2rem; text-transform: uppercase; text-shadow: 0 0 10px #00ff8855; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.2rem; text-transform: uppercase; text-shadow: 0 0 10px #ff4b4b55; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.1rem; }
    
    /* Kalkulator PLN */
    .pos-calc { 
        background: rgba(88, 166, 255, 0.1); border-radius: 12px; padding: 15px; 
        margin: 15px 0; border: 1px solid #58a6ff; color: #58a6ff; font-weight: bold;
    }
    
    /* Grid Techniczny */
    .tech-grid { 
        display: grid; grid-template-columns: 1fr 1fr; gap: 8px; 
        background: rgba(255,255,255,0.02); padding: 12px; border-radius: 12px; text-align: left;
    }
    .tech-row { border-bottom: 1px solid #21262d; padding: 4px 0; font-size: 0.85rem; display: flex; justify-content: space-between; }
    .tech-n { color: #8b949e; }
    .tech-v { color: #ffffff; font-weight: bold; }
    
    /* AI Analiza i News */
    .ai-box { 
        padding: 15px; border-radius: 12px; margin-top: 15px; font-size: 0.88rem; 
        background: rgba(88, 166, 255, 0.05); border-left: 5px solid #58a6ff;
        min-height: 80px; display: flex; align-items: center; line-height: 1.4; font-style: italic;
    }
    .news-container { margin-top: 15px; text-align: left; border-top: 1px dashed #30363d; padding-top: 12px; }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.75rem; display: block; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. EKSTREMALNY SILNIK ANALITYCZNY (WSZYSTKIE WSKAŹNIKI) ---
def get_full_analysis(symbol):
    try:
        s = symbol.strip().upper()
        ticker = yf.Ticker(s)
        df = ticker.history(period="250d", interval="1d")
        if df.empty or len(df) < 100: return None
        
        price = float(df['Close'].iloc[-1])
        
        # Trend i Srednie
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        
        # Bollinger Bands
        std_dev = df['Close'].rolling(20).std().iloc[-1]
        bb_up = ema20 + (std_dev * 2)
        bb_low = ema20 - (std_dev * 2)
        
        # MACD
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_val = (ema12 - ema26).iloc[-1]
        
        # Pivot
        prev = df.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        
        # RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR i Zarządzanie Ryzykiem
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        shares = int(risk_money / (atr * 1.6)) if atr > 0 else 0
        
        # Newsy (Safe Fetch)
        news_data = []
        try:
            raw_news = ticker.news
            if raw_news:
                for n in raw_news[:2]: news_data.append({"t": n.get('title', '')[:60], "u": n.get('link', '#')})
        except: pass
        if not news_data: news_data = [{"t": "Brak info rynkowego", "u": "#"}]

        # Sygnały
        v_type = "neutral"
        if rsi < 32 and price < bb_low: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68 and price > bb_up: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        # AI Analiza
        ai_msg = "Dodaj OpenAI Key w Secrets"
        if AI_KEY:
            try:
                client = OpenAI(api_key=AI_KEY)
                resp = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": f"Analiza {s}: RSI {rsi:.0f}, MACD {macd_val:.2f}, Cena {price}. Napisz 1 techniczne zdanie bez lania wody."}],
                    max_tokens=40
                )
                ai_msg = resp.choices.message.content
            except: ai_msg = "AI Limit"

        return {
            "s": s, "p": price, "rsi": rsi, "sma50": sma50, "sma200": sma200, "ema20": ema20,
            "pivot": pivot, "macd": macd_val, "verd": verd, "vcl": vcl, "v_type": v_type, 
            "shares": shares, "sl": price - (atr*1.6), "tp": price + (atr*3.5), 
            "ai": ai_msg, "news": news_data, "df": df.tail(60), "val": shares * price
        }
    except: return None

# --- 4. PANEL BOCZNY (PRZYCISK ZAPISZ I LISTA) ---
with st.sidebar:
    st.title("🚜 ALPHA ULTIMATE v48")
    st.markdown("---")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, st.session_state.risk_pct)
    ticker_area = st.text_area("Lista spółek:", value=load_tickers(), height=200)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.rerun()
    
    refresh_val = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300, 600], value=60)

st_autorefresh(interval=refresh_val * 1000, key="v48_refresh")

# --- 5. LOGIKA WYŚWIETLANIA I TERMINAL TOP 10 ---
tickers = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=refresh_val)
def fetch_all_parallel(t_list):
    with ThreadPoolExecutor(max_workers=10) as executor:
        return [r for r in executor.map(get_full_analysis, t_list) if r is not None]

data_ready = fetch_all_parallel(tickers)

if data_ready:
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL (RANKING RSI)")
    top_10 = sorted(data_ready, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for idx, d in enumerate(top_10):
        with t_cols[idx % 5]:
            t_cls = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""<div class="top-mini-tile {t_cls}"><b>{d['s']}</b> | {d['p']:.2f}<br><small>RSI: {d['rsi']:.0f}</small><br><span class="{d['vcl']}">{d['verd']}</span></div>""", unsafe_allow_html=True)

    st.divider()

    for i in range(0, len(data_ready), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                accent = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {accent};">
                    <div>
                        <div style="font-size:1.7rem; font-weight:bold;">{d['s']}</div>
                        <div style="color:#58a6ff; font-size:1.2rem;">{d['p']:.2f} PLN</div>
                        <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    </div>
                    <div class="pos-calc">
                        <small>Kupno:</small><br><span style="font-size:1.5rem;font-weight:bold;">{d['shares']} szt.</span><br><small>{d['val']:.0f} PLN</small>
                    </div>
                    <div class="tech-grid">
                        <div class="tech-row"><span class="tech-n">SMA200:</span><span class="tech-v">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">EMA20:</span><span class="tech-v">{d['ema20']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">MACD:</span><span class="tech-v">{d['macd']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">PIVOT:</span><span class="tech-v">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">RSI:</span><span class="tech-v">{d['rsi']:.0f}</span></div>
                    </div>
                    <div class="ai-box"><b>🤖 AI:</b> {d['ai']}</div>
                    <div class="news-container">
                        {"".join([f'<a class="news-link" href="{n["u"]}" target="_blank">• {n["t"]}</a>' for n in d['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander("🔍 ANALIZA WYKRESU"):
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:50px;'>v48.0 | Ostatnie odświeżenie: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
