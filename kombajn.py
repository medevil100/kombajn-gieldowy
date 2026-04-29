import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="NEON COMMANDER v102", page_icon="⚡", layout="wide")

EMAIL_RECEIVER = "szelag-adam@t-online.de"
EMAIL_SENDER = "szelag-adam@t-online.de" 
SMTP_SERVER = "securesmtp.t-online.de"
SMTP_PORT = 465

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "full_analysis" not in st.session_state: st.session_state.full_analysis = {}
if "risk_cap" not in st.session_state: st.session_state.risk_cap = 10000.0
if "previous_trends" not in st.session_state: st.session_state.previous_trends = {}

DB_FILE = "moje_spolki.txt"

# --- 2. STYLE NEONOWE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; }
    .status-sell { color: #ff4b4b; text-shadow: 0 0 10px #ff4b4b; font-weight: bold; }
    .tp-box { color: #00ff88; font-weight: bold; }
    .sl-box { color: #ff4b4b; font-weight: bold; }
    .trend-tag { padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; border: 1px solid #30363d; }
    .bid-style { color: #00ff88; font-weight: bold; }
    .ask-style { color: #ff4b4b; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNKCJE ---
def send_email(subject, body, password):
    if not password: return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_SENDER, password)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        return True
    except: return False

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        
        info = t.info
        p = float(df['Close'].iloc[-1])
        bid = info.get('bid') or p * 0.999
        ask = info.get('ask') or p * 1.001
        
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        return {
            "symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, 
            "rsi": 50.0, # uproszczone dla stabilności
            "pp": (df['High'].iloc[-2] + df['Low'].iloc[-2] + df['Close'].iloc[-2]) / 3,
            "trends": {"K": "UP" if p > sma20 else "DOWN", "S": "UP" if p > sma50 else "DOWN", "D": "UP" if p > sma200 else "DOWN"},
            "df": df.tail(45)
        }
    except: return None

def run_ai_short(d, key):
    if not key or d['symbol'] in st.session_state.ai_results: 
        return st.session_state.ai_results.get(d['symbol'])
    try:
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": f"Analiza {d['symbol']} @ {d['price']}. Zwróć JSON: {{\"w\": \"KUP\", \"sl\": {d['price']*0.9}, \"tp\": {d['price']*1.1}}}"}], 
            response_format={"type": "json_object"}
        )
        res = json.loads(resp.choices[0].message.content) # POPRAWIONE [0]
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL ---
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    email_pass = st.text_input("T-Online App Password", type="password")
    st.session_state.risk_cap = st.number_input("💵 Kapitał:", value=st.session_state.risk_cap)
    risk_pct = st.slider("🎯 Ryzyko (%)", 0.1, 5.0, 1.0)
    st_autorefresh(interval=120000, key="auto_ref") # Stałe 2 min dla stabilności

    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA, BTC-USD"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers)
    if st.button("🚀 SKANUJ"):
        st.session_state.ai_results = {}
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

# --- 5. START ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = []
email_updates = []

for sym in symbols:
    res = get_data(sym)
    if res:
        if api_key: res['ai'] = run_ai_short(res, api_key)
        data_list.append(res)
        cur_t = str(res['trends'])
        if sym in st.session_state.previous_trends and st.session_state.previous_trends[sym] != cur_t:
            email_updates.append(f"{sym} zmiana trendu!")
        st.session_state.previous_trends[sym] = cur_t

if email_updates and email_pass:
    send_email("MONSTER Update", "\n".join(email_updates), email_pass)

# --- 6. RYSOWANIE ---
if data_list:
    for d in data_list:
        try: # ZABEZPIECZENIE PRZED CRASHEM KARTY
            ai = d.get('ai')
            card_class = "neon-card-buy" if ai and "KUP" in str(ai.get('w','')).upper() else ""
            st.markdown(f'<div class="neon-card {card_class}">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.5, 3, 1.8])
            with c1:
                st.markdown(f"## {d['symbol']}")
                t_html = "".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span> ' for k,v in d['trends'].items()])
                st.markdown(t_html, unsafe_allow_html=True)
                st.write(f"CENA: **{d['price']:.2f}**")
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=180, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")
            with c3:
                if ai:
                    st.write(f"TP: {ai.get('tp')} | SL: {ai.get('sl')}")
                    diff = abs(d['price'] - float(ai.get('sl', d['price']*0.9)))
                    shares = int((st.session_state.risk_cap * (risk_pct/100)) / diff) if diff > 0 else 0
                    st.success(f"POZYCJA: {shares} szt.")
            st.markdown('</div>', unsafe_allow_html=True)
        except:
            st.error(f"Błąd wyświetlania {d['symbol']}")
