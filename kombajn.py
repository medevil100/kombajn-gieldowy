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

st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    .trend-up { color: #00ff88; font-weight: bold; font-size: 0.8rem; }
    .trend-down { color: #ff4b4b; font-weight: bold; font-size: 0.8rem; }
    .bid-ask { font-size: 0.8rem; color: #888; }
</style>
""", unsafe_allow_html=True)

# --- 2. SILNIK DANYCH (ZMODYFIKOWANY) ---
def get_safe_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        # Pobieramy 1 rok, ale akceptujemy mniej danych
        df = t.history(period="1y", interval="1d")
        if df.empty or len(df) < 10: return None
        
        p = float(df['Close'].iloc[-1])
        info = t.info
        bid = info.get('bid') or p * 0.998
        ask = info.get('ask') or p * 1.002
        
        # Obliczanie trendów z zabezpieczeniem przed brakiem danych
        def check_trend(price, window):
            if len(df) >= window:
                sma = df['Close'].rolling(window).mean().iloc[-1]
                return "UP" if price > sma else "DOWN"
            return "N/A"

        return {
            "sym": symbol.upper(),
            "p": p,
            "bid": bid,
            "ask": ask,
            "trends": {
                "K (20)": check_trend(p, 20),
                "S (50)": check_trend(p, 50),
                "D (200)": check_trend(p, 200)
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
            messages=[{"role": "user", "content": f"Analiza {d['sym']} cena {d['p']}. Zwroc JSON: {{\"w\":\"KUP\",\"sl\":{d['p']*0.92},\"tp\":{d['p']*1.15}}}"}],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except:
        return None

# --- 3. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    email_pass = st.text_input("E-mail Pass (T-Online)", type="password")
    cap = st.number_input("Kapitał", value=10000.0)
    risk_pct = st.slider("Ryzyko %", 0.1, 5.0, 1.0)
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: def_t = f.read()
    else: def_t = "HUMA, TCRX, GOSS"
    
    t_in = st.text_area("Lista spółek", value=def_t, height=200)
    if st.button("🚀 SKANUJ"):
        st.session_state.ai_results = {}
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

st_autorefresh(interval=120000, key="refresh")

# --- 4. WYŚWIETLANIE ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]

for sym in symbols:
    data = get_safe_data(sym)
    if not data:
        st.error(f"❌ {sym}: Błąd danych Yahoo")
        continue
    
    if sym not in st.session_state.ai_results and api_key:
        st.session_state.ai_results[sym] = run_ai(data, api_key)
    
    ai = st.session_state.ai_results.get(sym)
    
    with st.container():
        st.markdown(f'<div class="neon-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1.2])
        
        with c1:
            st.subheader(data['sym'])
            st.markdown(f"Cena: **{data['p']:.2f}**")
            st.markdown(f"<span class='bid-ask'>B: <span style='color:#00ff88'>{data['bid']:.2f}</span> | A: <span style='color:#ff4b4b'>{data['ask']:.2f}</span></span>", unsafe_allow_html=True)
            
            # Trendy
            for k, v in data['trends'].items():
                cls = "trend-up" if v == "UP" else "trend-down" if v == "DOWN" else ""
                st.markdown(f"<small>{k}:</small> <span class='{cls}'>{v}</span>", unsafe_allow_html=True)
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=data['df'].index, open=data['df']['Open'], high=data['df']['High'], low=data['df']['Low'], close=data['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=180, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{sym}")
            
        with c3:
            if ai:
                v_col = "#00ff88" if "KUP" in ai.get('w','').upper() else "#ff4b4b"
                st.markdown(f"<b style='color:{v_col}'>{ai.get('w')}</b>", unsafe_allow_html=True)
                st.write(f"SL: {ai.get('sl')} | TP: {ai.get('tp')}")
                
                # Kalkulator pozycji
                try:
                    sl_dist = abs(data['p'] - float(ai['sl']))
                    if sl_dist > 0:
                        risk_cash = cap * (risk_pct / 100)
                        shares = int(risk_cash / sl_dist)
                        st.success(f"KUP: {shares} szt.")
                        st.caption(f"Ryzyko: {risk_cash:.2f} USD")
                except: pass
        st.markdown('</div>', unsafe_allow_html=True)
