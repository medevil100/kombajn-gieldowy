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

# --- 1. KONFIGURACJA PLIKÓW I SKRYTKA SECRETS ---
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX"
        except: return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX"

# Konfiguracja strony
st.set_page_config(page_title="AI ALPHA GOLDEN v47 ULTIMATE", page_icon="🚜", layout="wide")

# Inicjalizacja stanów sesji
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. PEŁNA, ROZBUDOWANA BIBLIOTEKA STYLÓW CSS (OK. 60 LINII) ---
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Segoe UI', Roboto, sans-serif; }
    
    /* Sekcja TOP 10 Mini-Kafle */
    .top-mini-tile {
        padding: 15px; border-radius: 12px; text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505); 
        border: 1px solid #30363d; margin-bottom: 10px; transition: 0.3s;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); }
    
    /* Główne Karty Spółek */
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; 
        text-align: center; min-height: 620px; transition: 0.3s;
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .main-card:hover { border-color: #58a6ff; transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
    
    /* Typografia Sygnałów */
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.2rem; text-transform: uppercase; letter-spacing: 1px; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.2rem; text-transform: uppercase; letter-spacing: 1px; }
    .sig-neutral { color: #8b949e; font-weight: 900; font-size: 1.1rem; }
    
    /* Kalkulator i Dane Techniczne */
    .pos-calc { 
        background: rgba(88, 166, 255, 0.08); border-radius: 12px; padding: 15px; 
        margin: 15px 0; border: 1px solid rgba(88, 166, 255, 0.3); color: #58a6ff; 
    }
    .tech-grid { 
        display: grid; grid-template-columns: 1fr 1fr; gap: 8px; 
        background: rgba(255,255,255,0.02); padding: 12px; border-radius: 12px; text-align: left;
    }
    .tech-row { border-bottom: 1px solid #21262d; padding: 4px 0; font-size: 0.85rem; display: flex; justify-content: space-between; }
    .tech-n { color: #8b949e; }
    .tech-v { color: #ffffff; font-weight: bold; }
    
    /* AI Box i Newsy */
    .ai-box { 
        padding: 15px; border-radius: 10px; margin-top: 15px; font-size: 0.88rem; 
        background: rgba(88, 166, 255, 0.05); border-left: 4px solid #58a6ff;
        min-height: 80px; display: flex; align-items: center; line-height: 1.4;
    }
    .news-container { margin-top: 15px; text-align: left; border-top: 1px dashed #30363d; padding-top: 12px; }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.78rem; display: block; margin-bottom: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .news-link:hover { color: #ffffff; text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. EKSTREMALNY SILNIK ANALITYCZNY (OK. 80 LINII) ---
def get_full_analysis(symbol):
    try:
        s = symbol.strip().upper()
        ticker = yf.Ticker(s)
        # Pobieramy 250 dni dla pełnej stabilności SMA200 i MACD
        df = ticker.history(period="250d", interval="1d")
        
        if df.empty or len(df) < 100: return None
        
        price = float(df['Close'].iloc[-1])
        
        # --- WSKAŹNIKI TRENDU ---
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        
        # --- WSTĘGI BOLLINGERA ---
        std_dev = df['Close'].rolling(20).std().iloc[-1]
        bb_mid = ema20
        bb_up = bb_mid + (std_dev * 2)
        bb_low = bb_mid - (std_dev * 2)
        
        # --- MACD ---
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        curr_macd = macd_line.iloc[-1]
        curr_sig = signal_line.iloc[-1]
        
        # --- PIVOT POINT (KLASYCZNY) ---
        prev = df.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        
        # --- RSI (14) ---
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        # --- ATR I ZARZĄDZANIE RYZYKIEM ---
        tr1 = df['High'] - df['Low']
        tr2 = (df['High'] - df['Close'].shift()).abs()
        tr3 = (df['Low'] - df['Close'].shift()).abs()
        atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1]
        
        r_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.6
        shares = int(r_money / sl_dist) if sl_dist > 0 else 0
        
        # --- NEWSY (WPŁYWAJĄCE NA CENĘ) ---
        news_data = []
        try:
            raw_news = ticker.news
            if raw_news:
                for n in raw_news[:2]:
                    news_data.append({"t": n.get('title', '')[:60], "u": n.get('link', '#')})
        except: pass
        if not news_data: news_data = [{"t": "Brak komunikatów rynkowych", "u": "#"}]

        # --- WERDYKT LOGICZNY ---
        v_type = "neutral"
        if rsi < 32 and price < bb_low: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68 and price > bb_up: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        # --- ANALIZA AI (BEZ LANIA WODY) ---
        ai_txt = "Klucz AI nieobecny"
        if AI_KEY:
            try:
                client = OpenAI(api_key=AI_KEY)
                prompt = f"Analiza {s}: RSI {rsi:.0f}, MACD {curr_macd:.2f}, Cena {price}. Napisz 1 konkretne zdanie techniczne bez lania wody."
                res = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=40)
                ai_txt = res.choices.message.content
            except: ai_txt = "AI Offline / Limit"

        return {
            "s": s, "p": price, "rsi": rsi, "sma50": sma50, "sma200": sma200, "ema20": ema20,
            "pivot": pivot, "macd": curr_macd, "bb_up": bb_up, "bb_low": bb_low,
            "verd": verd, "vcl": vcl, "v_type": v_type, "shares": shares,
            "sl": price - sl_dist, "tp": price + (atr * 3.5), "ai": ai_txt,
            "news": news_data, "df": df.tail(60), "val": shares * price
        }
    except: return None

# --- 4. PANEL BOCZNY (OBSŁUGA LISTY) ---
with st.sidebar:
    st.title("🚜 ALPHA ULTIMATE v47")
    st.markdown("---")
    st.session_state.risk_cap = st.number_input("Kapitał Portfela (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    ticker_area = st.text_area("Lista Symboli:", value=load_tickers(), height=200)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.success("Zaktualizowano listę!")
        st.rerun()
    
    ref_val = st.select_slider("Auto-odświeżanie (s)", options=, value=60)

st_autorefresh(interval=ref_val * 1000, key="v47_refresh")

# --- 5. LOGIKA WYŚWIETLANIA (OK. 80 LINII) ---
ticker_list = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=ref_val)
def fetch_all_parallel(t_list):
    with ThreadPoolExecutor(max_workers=10) as executor:
        return [r for r in executor.map(get_full_analysis, t_list) if r is not None]

data_ready = fetch_all_parallel(ticker_list)

if data_ready:
    # --- RANKING TOP 10 (SZYBKI PODGLĄD) ---
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL (RANKING RSI)")
    top_10 = sorted(data_ready, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for idx, d in enumerate(top_10):
        with t_cols[idx % 5]:
            t_cls = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""
                <div class="top-mini-tile {t_cls}">
                    <b style="font-size:1.1rem;">{d['s']}</b><br>
                    <span style="color:#58a6ff;">{d['p']:.2f}</span><br>
                    <small>RSI: {d['rsi']:.0f}</small><br>
                    <span class="{d['vcl']}">{d['verd']}</span>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA (KAFELKI GŁÓWNE) ---
    for i in range(0, len(data_ready), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                border = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {border};">
                    <div>
                        <div style="font-size:1.6rem; font-weight:bold; letter-spacing:-1px;">{d['s']}</div>
                        <div style="color:#58a6ff; font-size:1.2rem;">{d['p']:.2f} <small>PLN</small></div>
                        <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    </div>
                    
                    <div class="pos-calc">
                        <small style="color:#8b949e;text-transform:uppercase;font-size:0.7rem;">Kupno:</small><br>
                        <span style="font-size:1.5rem;font-weight:bold;">{d['shares']} szt.</span><br>
                        <small>Wartość: {d['val']:.0f} PLN</small>
                    </div>
                    
                    <div class="tech-grid">
                        <div class="tech-row"><span class="tech-n">SMA200:</span><span class="tech-v">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">EMA20:</span><span class="tech-v">{d['ema20']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">MACD:</span><span class="tech-v">{d['macd']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">PIVOT:</span><span class="tech-v">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="tech-n">RSI:</span><span class="tech-v">{d['rsi']:.0f}</span></div>
                    </div>
                    
                    <div class="ai-box">
                        {d['ai']}
                    </div>
                    
                    <div class="news-container">
                        <b>INFO RYNKOWE:</b>
                        {"".join([f'<a class="news-link" href="{n["u"]}" target="_blank">• {n["t"]}</a>' for n in d['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("🔍 ANALIZA WYKRESU"):
                    st.write(f"SL: {d['sl']:.2f} | TP: {d['tp']:.2f}")
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:50px;'>v47.0 ULTIMATE FULL | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>", unsafe_allow_html=True)
