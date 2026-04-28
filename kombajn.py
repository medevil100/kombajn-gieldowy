import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime
import re

# --- 1. INICJALIZACJA ---
if "risk_cap" not in st.session_state: st.session_state.risk_cap = 10000.0
if "risk_pct" not in st.session_state: st.session_state.risk_pct = 2.0
if "ai_results" not in st.session_state: st.session_state.ai_results = {}

DB_FILE = "moje_spolki.txt"
st.set_page_config(page_title="NEON QUANT v95", page_icon="⚡", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
    return "NVDA, TSLA, BTC-USD, ETH-USD"

# --- 2. STYLE NEONOWE ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 25px; border-radius: 15px; margin-bottom: 25px; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 10px; }
    .status-sell { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; border: 2px solid #ff0055; padding: 5px 15px; border-radius: 10px; }
    .tp-box { border: 1px solid #00ff88; padding: 12px; border-radius: 10px; color: #00ff88; text-align: center; background: rgba(0,255,136,0.1); font-weight: bold; }
    .sl-box { border: 1px solid #ff0055; padding: 12px; border-radius: 10px; color: #ff0055; text-align: center; background: rgba(255,0,85,0.1); font-weight: bold; }
    .top-tile { background: #111; border: 1px solid #333; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 3px solid #58a6ff; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK TECHNICZNY ---
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty or len(df) < 50: return None
        df = fix_col(df)
        
        p = float(df['Close'].iloc[-1])
        ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
        ma200 = float(df['Close'].rolling(200).mean().iloc[-1])
        
        # Ekstrema i Pivot
        h_day, l_day = float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
        h_prev, l_prev, c_prev = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pp = (h_prev + l_prev + c_prev) / 3
        
        delta = df['Close'].diff()
        rsi = float((100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))))).iloc[-1])
        
        return {
            "symbol": symbol.strip().upper(), "price": p, "rsi": rsi, "ma50": ma50, "ma200": ma200, 
            "pp": pp, "high": h_day, "low": l_day, "df": df.tail(40), 
            "change": ((p - c_prev) / c_prev * 100)
        }
    except: return None

def run_ai(d, key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = (f"Jesteś algorytmem QUANT. Analiza {d['symbol']}:\n"
                  f"Cena: {d['price']}, Szczyt: {d['high']}, Dołek: {d['low']}, Pivot: {d['pp']:.2f}, RSI: {d['rsi']:.1f}, MA50: {d['ma50']:.2f}.\n"
                  f"Na podstawie Szczytów, Dołków i Pivotu zwróć werdykt w formacie JSON:\n"
                  f"{{\"w\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", \"sl\": cena_sl, \"tp\": cena_tp, \"uzas\": \"max 10 slow o trendzie\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices.message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("⚡ QUANT MASTER v95")
    key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap = st.number_input("💵 Kapitał:", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko % na trade", 0.5, 5.0, st.session_state.risk_pct)
    
    t_in = st.text_area("Lista Symboli:", value=load_tickers(), height=150)
    if st.button("🚀 INICJUJ SYSTEM"):
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()
    st_autorefresh(interval=60000, key="v95_ref")

# --- 5. DASHBOARD ---
tickers = [x.strip().upper() for x in t_in.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [d for d in list(executor.map(get_data, tickers)) if d is not None]

if data_list:
    st.subheader("🔥 TOP 10 SYGNAŁÓW (RSI + QUANT AI)")
    t_cols = st.columns(5)
    for i, r in enumerate(sorted(data_list, key=lambda x: x['rsi'])[:10]):
        ai_brief = run_ai(r, key) if key else None
        v_tag = ai_brief['w'] if ai_brief else "---"
        v_col = "#00ff88" if v_tag == "KUP" else "#ff4b4b" if v_tag == "SPRZEDAJ" else "#58a6ff"
        with t_cols[i % 5]:
            st.markdown(f"""<div class='top-tile'><b>{r['symbol']}</b><br><span style='color:{v_col}; font-weight:bold;'>{v_tag}</span><br><small>RSI: {r['rsi']:.1f}</small></div>""", unsafe_allow_html=True)

    st.divider()

    for d in data_list:
        ai = run_ai(d, key) if key else None
        
        st.markdown(f'<div class="neon-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 2.5, 1.5])
        
        with c1:
            st.markdown(f"### {d['symbol']}")
            if ai:
                v_class = "status-buy" if ai['w'] == "KUP" else "status-sell" if ai['w'] == "SPRZEDAJ" else "status-hold"
                st.markdown(f'<span class="{v_class}">{ai["w"]}</span>', unsafe_allow_html=True)
            st.markdown(f"<br>Cena: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.write(f"High: {d['high']:.2f} | Low: {d['low']:.2f}")
            st.write(f"Pivot: {d['pp']:.2f} | RSI: {d['rsi']:.1f}")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dot", line_color="#58a6ff", annotation_text="Pivot")
            fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f'<div class="tp-box"><small>TAKE PROFIT</small><br><b>{ai["tp"]}</b></div>', unsafe_allow_html=True)
                st.markdown(f'<div style="margin-top:10px;" class="sl-box"><small>STOP LOSS</small><br><b>{ai["sl"]}</b></div>', unsafe_allow_html=True)
                
                # Kalkulator Wielkości
                try:
                    diff = abs(d['price'] - float(ai['sl']))
                    shares = int((st.session_state.risk_cap * (st.session_state.risk_pct/100)) / diff) if diff > 0 else 0
                    st.markdown(f"""<div style='background:#111; padding:15px; border-radius:10px; border:1px solid #333; margin-top:15px; text-align:center;'>
                        KUP: <b style='color:#00ff88; font-size:1.3rem;'>{shares} szt.</b><br><small><i>{ai['uzas']}</i></small></div>""", unsafe_allow_html=True)
                except: pass
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("System czeka na klucz i symbole.")
