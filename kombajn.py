import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import re

# --- 1. KONFIGURACJA PLIKÓW ---
DB_FILE = "moje_spolki.txt"
LOG_FILE = "trade_log.json"

st.set_page_config(page_title="NEON ALPHA REBORN v82", page_icon="🚜", layout="wide")

# Ładowanie / Inicjalizacja danych
if "ai_results" not in st.session_state: st.session_state.ai_results = {}

def get_tickers():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: f.write("NVDA, TSLA, AAPL, BTC-USD")
    with open(DB_FILE, "r") as f: return f.read()

def load_trades():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f: return json.load(f)
        except: return []
    return []

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .top-tile { background: #111; border: 1px solid #333; padding: 10px; border-radius: 10px; text-align: center; }
    .neon-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight:bold; }
    .neon-sell { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight:bold; }
    .metric-small { font-size: 0.8rem; color: #888; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIKA DANYCH ---
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        df = fix_col(df)
        price = float(df['Close'].iloc[-1])
        rsi = (100 - (100 / (1 + (df['Close'].diff().where(df['Close'].diff() > 0, 0).rolling(14).mean() / 
                                 df['Close'].diff().where(df['Close'].diff() < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1]
        return {"symbol": symbol.strip().upper(), "price": price, "rsi": rsi, "df": df.tail(40), "change": ((price - df['Close'].iloc[-2])/df['Close'].iloc[-2]*100)}
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("⚡ MONSTER REBORN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    cap = st.number_input("Portfel:", value=10000.0)
    tick_in = st.text_area("Lista Symboli (CSV):", value=get_tickers(), height=150)
    if st.button("💾 ZAPISZ I SKANUJ"):
        with open(DB_FILE, "w") as f: f.write(tick_in)
        st.session_state.ai_results = {}
        st.rerun()
    st_autorefresh(interval=60000, key="v82_ref")

# --- 5. DASHBOARD ---
symbols = [s.strip().upper() for s in tick_in.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in list(executor.map(get_data, symbols)) if r is not None]

if results:
    # TOP 10 RANKING
    st.subheader("🔥 TOP 10 - NAJLEPSZE OKAZJE (RSI)")
    top_cols = st.columns(5)
    for i, r in enumerate(sorted(results, key=lambda x: x['rsi'])[:10]):
        with top_cols[i % 5]:
            st.markdown(f"""<div class='top-tile'><b style='color:#58a6ff'>{r['symbol']}</b><br>{r['price']:.2f}<br><small>RSI: {r['rsi']:.1f}</small></div>""", unsafe_allow_html=True)

    st.divider()

    # LISTA WSZYSTKICH SPÓŁEK
    for r in results:
        with st.container():
            st.markdown(f'<div class="neon-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1.2])
            
            with c1:
                st.subheader(r['symbol'])
                st.metric("CENA", f"{r['price']:.2f}", f"{r['change']:.2f}%")
                st.write(f"RSI: {r['rsi']:.1f}")
                
                if api_key and st.button(f"🧠 ANALIZA AI", key=f"ai_{r['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = f"Analiza {r['symbol']} @ {r['price']}. RSI {r['rsi']:.1f}. Podaj: WERDYKT (KUP/SPRZEDAJ/TRZYMAJ), SL: [cena], TP: [cena] i 1 zdanie powodu. Krótko!"
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_results[r['symbol']] = resp.choices[0].message.content

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"fig_{r['symbol']}")

            with c3:
                if r['symbol'] in st.session_state.ai_results:
                    txt = st.session_state.ai_results[r['symbol']]
                    st.info(txt)
                    # Kalkulator
                    sl_match = re.search(r"SL:.*?([\d\.]+)", txt)
                    if sl_match:
                        sl = float(sl_match.group(1))
                        diff = abs(r['price'] - sl)
                        shares = int((cap * 0.02) / diff) if diff > 0 else 0
                        st.success(f"KUP: {shares} szt. (Ryzyko 2%)")
                else:
                    st.write("Kliknij Analiza AI, aby zobaczyć werdykt i poziomy.")
            
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Brak danych. Sprawdź listę spółek w panelu bocznym.")
