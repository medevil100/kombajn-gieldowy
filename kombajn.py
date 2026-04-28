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
st.set_page_config(page_title="NEON ALPHA SENTINEL v81", page_icon="🚨", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
        except: return "NVDA, TSLA, BTC-USD"
    return "NVDA, TSLA, BTC-USD"

def load_trades():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    with open(LOG_FILE, "w") as f: json.dump(trades, f)

# --- 2. NEON SENTINEL STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 25px; border-radius: 20px; margin-bottom: 25px; }
    .alert-critical { background: rgba(255, 0, 85, 0.2); border: 2px solid #ff0055; padding: 15px; border-radius: 10px; animation: blink 1s infinite; color: #ff0055; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .alert-profit { background: rgba(0, 255, 136, 0.2); border: 2px solid #00ff88; padding: 15px; border-radius: 10px; color: #00ff88; font-weight: bold; text-align: center; margin-bottom: 20px; }
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .metric-value { font-size: 1.5rem; font-weight: bold; }
    .neon-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; border: 1px solid #00ff88; padding: 3px 10px; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def get_ticker_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        df = fix_col(df)
        price = float(df['Close'].iloc[-1])
        h, l, c = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pp = (h + l + c) / 3
        rsi = (100 - (100 / (1 + (df['Close'].diff().where(df['Close'].diff() > 0, 0).rolling(14).mean() / 
                                 df['Close'].diff().where(df['Close'].diff() < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1]
        return {"symbol": symbol.strip().upper(), "price": price, "rsi": rsi, "pp": pp, "df": df.tail(45)}
    except: return None

def get_ai_analysis(d, api_key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"Analiza {d['symbol']} @ {d['price']}. RSI {d['rsi']:.1f}. Zwróć JSON: {{'werdykt': 'KUP'|'SPRZEDAJ'|'TRZYMAJ', 'sl': cena, 'tp': cena, 'powod': 'max 8 slow'}}"
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={ "type": "json_object" })
        res = json.loads(resp.choices.message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚨 SENTINEL v81")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    risk_cap = st.number_input("💵 Kapitał:", value=10000.0)
    t_input = st.text_area("Tickery:", value=load_tickers(), height=120)
    if st.button("🚀 SYNC"):
        st.session_state.ai_results = {}
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_input)
        st.rerun()
    if st.button("🗑️ Reset Dziennika"):
        if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
        st.rerun()
    st_autorefresh(interval=60000, key="v81_ref")

# --- 5. LOGIKA GŁÓWNA ---
trades = load_trades()
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=5) as executor:
    all_data = {d['symbol']: d for d in list(executor.map(get_ticker_data, tickers)) if d is not None}

# --- SENTINEL ALERTS ---
if trades:
    for t in trades:
        curr_p = all_data.get(t['symbol'], {}).get('price')
        if curr_p:
            if curr_p <= float(t['sl']):
                st.markdown(f'<div class="alert-critical">🚨 ALARM STOP-LOSS: {t["symbol"]} przebił {t["sl"]}! AKTUALNA CENA: {curr_p:.2f}</div>', unsafe_allow_html=True)
            elif curr_p >= float(t['tp']):
                st.markdown(f'<div class="alert-profit">💰 ALARM TAKE-PROFIT: {t["symbol"]} osiągnął {t["tp"]}! GRATULACJE!</div>', unsafe_allow_html=True)

# Podsumowanie Portfela
total_cost = sum([t['cost'] for t in trades])
c1, c2, c3 = st.columns(3)
c1.metric("KAPITAŁ", f"{risk_cap:,.0f}")
c2.metric("W POZYCJACH", f"{total_cost:,.2f}", delta=f"{((total_cost/risk_cap)*100):.1f}%", delta_color="off")
c3.metric("AKTYWNE TREJDY", len(trades))

st.divider()

# Wyświetlanie kart
if all_data:
    for sym, d in all_data.items():
        ai = get_ai_analysis(d, api_key) if api_key else None
        st.markdown(f'<div class="neon-card">', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1.2, 2.5, 1.3])
        
        with col1:
            st.markdown(f"### {d['symbol']}")
            if ai: st.markdown(f'<span class="neon-buy">{ai["werdykt"]}</span>', unsafe_allow_html=True)
            st.markdown(f'<br><small>PRICE:</small> <b>{d["price"]:.2f}</b><br><small>RSI:</small> <b>{d["rsi"]:.1f}</b>', unsafe_allow_html=True)

        with col2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"v_{d['symbol']}")

        with col3:
            if ai:
                diff = abs(d['price'] - float(ai['sl']))
                shares = int((risk_cap * 0.02) / diff) if diff > 0 else 0
                cost = shares * d['price']
                
                st.markdown(f"**TP: {ai['tp']}**")
                st.markdown(f"**SL: {ai['sl']}**")
                
                if st.button(f"📥 ZAPISZ {shares}szt.", key=f"log_{d['symbol']}"):
                    save_trade({"symbol": d['symbol'], "price": d['price'], "shares": shares, "cost": cost, "sl": ai['sl'], "tp": ai['tp'], "date": str(datetime.now())})
                    st.rerun()
                st.caption(f"Koszt: {cost:.2f} | {ai['powod']}")
        st.markdown('</div>', unsafe_allow_html=True)

# Dziennik
if trades:
    with st.expander("📓 TWÓJ DZIENNIK SENTINEL"):
        df_trades = pd.DataFrame(trades)
        st.dataframe(df_trades.style.highlight_between(left=0, right=df_trades['sl'], subset=['price'], color='#440011'))
