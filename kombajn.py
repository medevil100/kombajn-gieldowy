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

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="NEON COMMANDER v102", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "previous_trends" not in st.session_state: st.session_state.previous_trends = {}

DB_FILE = "moje_spolki.txt"

# --- 2. STYLE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    .trend-up { color: #00ff88; font-weight: bold; }
    .trend-down { color: #ff4b4b; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNKCJE (ZABEZPIECZONE) ---
def get_safe_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="6mo", interval="1d")
        if df.empty or len(df) < 200: return None
        
        p = float(df['Close'].iloc[-1])
        # Trendy
        s20 = df['Close'].rolling(20).mean().iloc[-1]
        s50 = df['Close'].rolling(50).mean().iloc[-1]
        s200 = df['Close'].rolling(200).mean().iloc[-1]
        
        return {
            "sym": symbol.upper(),
            "p": p,
            "trends": {
                "K": "UP" if p > s20 else "DOWN",
                "S": "UP" if p > s50 else "DOWN",
                "D": "UP" if p > s200 else "DOWN"
            },
            "df": df.tail(40)
        }
    except:
        return None

def run_ai(d, key):
    if not key: return None
    try:
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Analiza {d['sym']} cena {d['p']}. Zwroc JSON: {{\"w\":\"KUP\",\"sl\":{d['p']*0.9},\"tp\":{d['p']*1.1}}}"}],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except:
        return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    email_pass = st.text_input("E-mail Pass", type="password")
    cap = st.number_input("Kapitał", value=10000.0)
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: def_t = f.read()
    else: def_t = "NVDA, TSLA, AAPL"
    
    t_in = st.text_area("Tickery", value=def_t)
    if st.button("🚀 SKANUJ"):
        st.session_state.ai_results = {}
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

st_autorefresh(interval=120000, key="refresh")

# --- 5. WYŚWIETLANIE ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

for sym in symbols:
    data = get_safe_data(sym)
    if not data:
        st.warning(f"Brak danych dla {sym} (może brakuje historii 200 dni?)")
        continue
    
    # AI logic
    if sym not in st.session_state.ai_results and api_key:
        st.session_state.ai_results[sym] = run_ai(data, api_key)
    
    ai = st.session_state.ai_results.get(sym)
    
    # Rysowanie karty
    with st.container():
        st.markdown(f'<div class="neon-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])
        
        with c1:
            st.subheader(data['sym'])
            st.write(f"Cena: **{data['p']:.2f}**")
            # Wyświetlanie trendów
            for k, v in data['trends'].items():
                cls = "trend-up" if v == "UP" else "trend-down"
                st.markdown(f"{k}: <span class='{cls}'>{v}</span>", unsafe_allow_html=True)
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=data['df'].index, open=data['df']['Open'], high=data['df']['High'], low=data['df']['Low'], close=data['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{sym}")
            
        with c3:
            if ai:
                st.write(f"Sygnał: {ai.get('w')}")
                st.write(f"SL: {ai.get('sl')}")
                # Kalkulator
                try:
                    diff = abs(data['p'] - float(ai['sl']))
                    shares = int((cap * 0.01) / diff) if diff > 0 else 0
                    st.success(f"Kup: {shares} szt.")
                except: pass
        
        st.markdown('</div>', unsafe_allow_html=True)

# --- 6. EMAIL LOGIC (Tylko przy zmianie) ---
# [Tutaj możesz dodać funkcję wysyłki, jeśli powyższe ruszy]
