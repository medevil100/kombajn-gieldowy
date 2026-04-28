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

# --- 1. RDZEŃ ---
DB_FILE = "moje_spolki.txt"
st.set_page_config(page_title="OMNI NEON v84 PRO", page_icon="⚡", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "last_signals" not in st.session_state: st.session_state.last_signals = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
    return "NVDA, TSLA, BTC-USD, ETH-USD"

# --- 2. NEON STYLE + AUDIO ---
st.markdown("""
    <style>
    @keyframes pulse-white { 0% { box-shadow: 0 0 5px #fff; } 50% { box-shadow: 0 0 25px #fff; } 100% { box-shadow: 0 0 5px #fff; } }
    .stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 20px; border-radius: 15px; margin-bottom: 20px; transition: 0.3s; }
    .volume-spike { animation: pulse-white 2s infinite; border: 1px solid #ffffff!important; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 2px 10px; border-radius: 5px; }
    .status-sell { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; border: 2px solid #ff0055; padding: 2px 10px; border-radius: 5px; }
    .tp-box { border: 1px solid #00ff88; padding: 10px; border-radius: 8px; color: #00ff88; text-align: center; font-weight: bold; }
    .sl-box { border: 1px solid #ff0055; padding: 10px; border-radius: 8px; color: #ff0055; text-align: center; font-weight: bold; }
    .top-tile { background: #111; border: 1px solid #333; padding: 10px; border-radius: 10px; text-align: center; border-bottom: 2px solid #58a6ff; }
    </style>
    """, unsafe_allow_html=True)

def play_alert():
    st.markdown("""<audio autoplay><source src="https://soundjay.com" type="audio/mpeg"></audio>""", unsafe_allow_html=True)

# --- 3. ANALIZA ---
def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        p = float(df['Close'].iloc[-1])
        # Średnie i Pivot
        ma50, ma100, ma200 = df['Close'].rolling(50).mean().iloc[-1], df['Close'].rolling(100).mean().iloc[-1], df['Close'].rolling(200).mean().iloc[-1]
        h, l, c = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pp = (h + l + c) / 3
        # Wolumen
        vol_rel = df['Volume'].iloc[-1] / df['Volume'].tail(20).mean()
        # RSI
        delta = df['Close'].diff()
        rsi = (100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))))).iloc[-1]
        
        return {"symbol": symbol.strip().upper(), "price": p, "rsi": rsi, "ma50": ma50, "ma100": ma100, "ma200": ma200, "pp": pp, "vol_rel": vol_rel, "df": df.tail(30), "change": ((p - c) / c * 100)}
    except: return None

def run_ai(d, api_key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=api_key)
        prompt = (f"Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, MA50:{d['ma50']:.1f}, MA200:{d['ma200']:.1f}, Pivot:{d['pp']:.2f}. "
                  f"Zwróć JSON: {{\"werdykt\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", \"sl\": cena, \"tp\": cena, \"uzas\": \"max 8 slow\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices.message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("⚡ NEON OMNI v84")
    key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    cap = st.number_input("Kapitał:", value=10000.0)
    t_in = st.text_area("Tickery:", value=load_tickers(), height=150)
    if st.button("🚀 SKANUJ"):
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()
    st_autorefresh(interval=60000, key="v84_ref")

# --- 5. DASHBOARD ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [d for d in list(executor.map(get_data, symbols)) if d is not None]

if data_list:
    # TOP 10 RANKING
    st.subheader("🔥 TOP 10 SYGNAŁÓW (RSI)")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for i, r in enumerate(sorted_top):
        with t_cols[i % 5]:
            st.markdown(f"<div class='top-tile'><b>{r['symbol']}</b><br><small>RSI: {r['rsi']:.1f}</small></div>", unsafe_allow_html=True)

    st.divider()

    # LISTA GŁÓWNA
    for d in data_list:
        ai = run_ai(d, key) if key else None
        
        # Audio alert dla nowych "KUP"
        if ai and ai['werdykt'] == "KUP" and st.session_state.last_signals.get(d['symbol']) != "KUP":
            play_alert()
            st.session_state.last_signals[d['symbol']] = "KUP"

        # Podświetlenie wolumenu
        spike_class = "volume-spike" if d['vol_rel'] > 2.0 else ""
        
        st.markdown(f'<div class="neon-card {spike_class}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 2.5, 1.5])
        
        with c1:
            st.markdown(f"### {d['symbol']} {'🔥' if d['vol_rel'] > 2.0 else ''}")
            if ai:
                v_class = "status-buy" if ai['werdykt'] == "KUP" else "status-sell" if ai['werdykt'] == "SPRZEDAJ" else "status-hold"
                st.markdown(f'<span class="{v_class}">{ai["werdykt"]}</span>', unsafe_allow_html=True)
            st.markdown(f"<br>Cena: **{d['price']:.2f}**<br>Ziana: **{d['change']:.2f}%**", unsafe_allow_html=True)
            st.write(f"R-Vol: x{d['vol_rel']:.2f}")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dot", line_color="#58a6ff")
            fig.update_layout(template="plotly_dark", height=220, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{d['symbol']}")

        with c3:
            if ai:
                st.columns[0].markdown(f'<div class="tp-box"><small>TP</small><br>{ai["tp"]}</div>', unsafe_allow_html=True)
                st.columns[1].markdown(f'<div class="sl-box"><small>SL</small><br>{ai["sl"]}</div>', unsafe_allow_html=True)
                
                # Kalkulator
                diff = abs(d['price'] - float(ai['sl']))
                shares = int((cap * 0.02) / diff) if diff > 0 else 0
                st.markdown(f"""<div style='background:#111; padding:10px; border-radius:10px; border:1px solid #333; margin-top:10px; text-align:center;'>
                    <small>KUP: <b>{shares} szt.</b> (Ryzyko 2%)</small><br><small><i>{ai['uzas']}</i></small></div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj tickery i klucz OpenAI.")
