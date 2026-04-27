import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import requests

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.2", page_icon="🚜", layout="wide")

# Stabilna sesja dla yfinance
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# Inicjalizacja sesji dla formularzy (zapobiega resetowaniu danych)
if "capital" not in st.session_state: st.session_state.capital = 10000.0
if "risk_per_trade" not in st.session_state: st.session_state.risk_per_trade = 1.0

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .pos-box { background: rgba(88, 166, 255, 0.1); border: 1px solid #58a6ff; padding: 10px; border-radius: 8px; margin-top: 10px; }
    .top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; height: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieranie danych z użyciem sesji
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False, session=session)
        if d1d.empty: return None
        
        if isinstance(d1d.columns, pd.MultiIndex): d1d.columns = d1d.columns.get_level_values(0)
        
        price = float(d1d['Close'].iloc[-1])
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        
        # Trend i ATR do pozycji
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        # RSI
        delta = d1d['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Kalkulator Pozycji (Risk Management)
        risk_amount = st.session_state.capital * (st.session_state.risk_per_trade / 100)
        # Stop Loss na poziomie 1.5 * ATR
        sl_dist = atr * 1.5
        shares = int(risk_amount / sl_dist) if sl_dist > 0 else 0
        
        return {
            "symbol": symbol, "price": price, "change": change_pct, "rsi": rsi, 
            "trend": "HOSSA 🚀" if price > sma200 else "BESSA 📉",
            "trend_col": "#00ff88" if price > sma200 else "#ff4b4b",
            "shares": shares, "sl": price - sl_dist, "tp": price + (atr * 3), "df": d1d
        }
    except: return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ PANEL STEROWANIA")
    
    # Zarządzanie kapitałem
    st.session_state.capital = st.number_input("Twój Kapitał ($)", value=st.session_state.capital)
    st.session_state.risk_per_trade = st.slider("Ryzyko na transakcję (%)", 0.1, 5.0, st.session_state.risk_per_trade)
    
    st.write("---")
    if "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
        st.success("✅ AI Ready")
    else:
        api_key = st.text_input("OpenAI Key", type="password")

    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
        st.rerun()
    
    refresh = st.select_slider("Auto-Refresh (s)", options=[30, 60, 300], value=60)

# Poprawione odświeżanie - tylko jeśli użytkownik nie klika w AI
st_autorefresh(interval=refresh * 1000, key="global_refresh")

# --- 5. GŁÓWNA LOGIKA ---
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
data_list = []

# Progress bar dla lepszego UX
p_bar = st.progress(0)
for i, t in enumerate(tickers):
    res = get_analysis(t)
    if res: data_list.append(res)
    p_bar.progress((i + 1) / len(tickers))
p_bar.empty()

if data_list:
    # Sekcja TOP Monitoring
    st.subheader("📊 MONITORING RYNKU")
    top_cols = st.columns(len(data_list[:6]))
    for i, d in enumerate(data_list[:6]):
        with top_cols[i]:
            st.markdown(f"""
                <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                    <small>{d['symbol']}</small><br>
                    <b style="color:{d['trend_col']};">{d['price']:.2f}</b><br>
                    <span style="font-size:0.7rem;">RSI: {d['rsi']:.1f}</span>
                </div>
            """, unsafe_allow_html=True)

    # Sekcja Szczegółowa z Kalkulatorem
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown(f"### {d['symbol']}")
            st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            # KALKULATOR POZYCJI
            st.markdown(f"""
                <div class="pos-box">
                    <small>MONSTER CALCULATOR</small><br>
                    Sugerowana ilość: <b>{d['shares']} szt.</b><br>
                    <span style="color:#ff4b4b;">SL: {d['sl']:.2f}</span> | 
                    <span style="color:#00ff88;">TP: {d['tp']:.2f}</span>
                </div>
            """, unsafe_allow_html=True)

            if api_key and st.button(f"🧠 ANALIZA AI {d['symbol']}", key=f"btn_{d['symbol']}"):
                try:
                    client = OpenAI(api_key=api_key)
                    prompt = f"Spółka {d['symbol']}, Cena {d['price']}, RSI {d['rsi']:.1f}. Trend {d['trend']}. Daj krótki, agresywny werdykt tradera."
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.session_state[f"ai_{d['symbol']}"] = resp.choices[0].message.content
                except: st.error("AI Error")

            if f"ai_{d['symbol']}" in st.session_state:
                st.info(st.session_state[f"ai_{d['symbol']}"])
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:])])
            fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
