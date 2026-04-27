import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I PAMIĘĆ ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "NVDA, TSLA, BTC-USD, PKO.WA"
        except: return "NVDA, TSLA, BTC-USD, PKO.WA"
    return "NVDA, TSLA, BTC-USD, PKO.WA"

st.set_page_config(page_title="AI ALPHA GOLDEN v50 FINAL", page_icon="🚜", layout="wide")

# Inicjalizacja stanów sesji
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. STYLE WIZUALNE ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0f111a, #1a1c2b); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px;
    }
    .top-tile {
        background: #111420; padding: 12px; border-radius: 10px; border-bottom: 3px solid #00ff88; 
        text-align: center; min-height: 180px; transition: 0.3s;
    }
    .top-tile:hover { transform: translateY(-5px); border-color: #58a6ff; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; }
    .sig-buy { color: #00ff88; font-weight: bold; text-shadow: 0 0 10px #00ff8855; }
    .sig-sell { color: #ff4b4b; font-weight: bold; text-shadow: 0 0 10px #ff4b4b55; }
    .pos-calc { background: rgba(88, 166, 255, 0.1); border-radius: 10px; padding: 12px; margin: 15px 0; border: 1px solid #58a6ff; color: #58a6ff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        time.sleep(0.5) # Ochrona przed Rate Limit
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        
        # Pobieranie danych (History jest stabilne, .info wiesza skrypt)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="250d", interval="1d")
        
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        
        # Wskaźniki
        sma50 = d1['Close'].rolling(50).mean().iloc[-1]
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        ema20 = d1['Close'].ewm(span=20).mean().iloc[-1]
        yearly_high = d1['High'].max()
        yearly_low = d1['Low'].min()
        
        # Pivot i ATR
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI 1h
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Kalkulator Pozycji
        risk_pln = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        shares = int(risk_pln / (atr * 1.5)) if atr > 0 else 0
        
        # Newsy (Safe Fetch)
        news_list = []
        try:
            for n in t.news[:2]: news_list.append({"t": n.get('title')[:55], "l": n.get('link')})
        except: news_list = [{"t": "Brak info rynkowego", "l": "#"}]

        # Werdykt
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma50": sma50, "sma200": sma200, 
            "ema20": ema20, "pp": pp, "verdict": verd, "vcl": vcl, "v_type": v_type,
            "y_high": yearly_high, "y_low": yearly_low, "shares": shares,
            "tp": price + (atr * 2), "sl": price - (atr * 1.5),
            "df": h1, "news": news_list, "val": shares * price
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v50 FINAL")
    # Automatyczne pobieranie klucza ze skrytki (Secrets)
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    st.subheader("💰 KONFIGURACJA PORTFELA")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    t_input = st.text_area("Lista Symboli:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.cache_data.clear()
        st.success("Lista zapisana!")
        st.rerun()
    
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v50_fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_input.replace('\n', ',').split(",") if x.strip()]

@st.cache_data(ttl=refresh)
def fetch_all(ticker_list):
    with ThreadPoolExecutor(max_workers=5) as executor:
        return [d for d in list(executor.map(get_analysis, ticker_list)) if d is not None]

all_data = fetch_all(tickers)

if all_data:
    # --- TOP 10 RANKING ---
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL")
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-tile">
                    <b>{d['symbol']}</b><br>
                    <span style="font-size:1.1rem; color:#58a6ff;">{d['price']:.2f}</span><br>
                    <div class="{d['vcl']}" style="margin-top:5px;">{d['verdict']}</div>
                    <small>RSI: {d['rsi']:.0f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            
            with c1:
                st.markdown(f"<h3 class='{d['vcl']}'>{d['symbol']} {d['verdict']}</h3>", unsafe_allow_html=True)
                st.metric("CENA", f"{d['price']:.2f} PLN")
                st.markdown(f"""
                    <div class="pos-calc">KUP: {d['shares']} szt.<br><small>{d['val']:.0f} PLN</small></div>
                    <div class="metric-row"><span>RSI (1h)</span><b>{d['rsi']:.1f}</b></div>
                    <div class="metric-row"><span>SMA 200</span><b>{d['sma200']:.2f}</b></div>
                    <div class="metric-row"><span>EMA 20</span><b>{d['ema20']:.2f}</b></div>
                    <div class="metric-row"><span>Pivot</span><b>{d['pp']:.2f}</b></div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                fig.add_hline(y=d['y_high'], line_dash="dash", line_color="#00ff88")
                fig.add_hline(y=d['y_low'], line_dash="dash", line_color="#ff4b4b")
                fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")

            with c3:
                st.write("**AI ANALIZA:**")
                if api_key and st.button(f"🤖 ANALIZUJ {d['symbol']}", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = f"Analiza {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.0f}, SMA200 {d['sma200']:.2f}. Podaj 1 konkretne zdanie strategii."
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.info(resp.choices[0].message.content)
                
                st.markdown("<br><b>📢 NEWSY:</b>", unsafe_allow_html=True)
                for n in d['news']:
                    st.markdown(f"<a href='{n['l']}' style='font-size:0.75rem; color:#58a6ff;'>• {n['t']}</a>", unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

st.markdown(f"<div style='text-align:center; color:gray;'>v50.0 FINAL | {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
