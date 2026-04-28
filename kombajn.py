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

# --- 1. RDZEŃ I PAMIĘĆ ---
DB_FILE = "moje_spolki.txt"
st.set_page_config(page_title="MASTER OMNI v88", page_icon="⚡", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
    return "NVDA, TSLA, BTC-USD, ETH-USD"

# --- 2. STYLE NEONOWE ---
st.markdown("""
    <style>
    @keyframes pulse-white { 0% { box-shadow: 0 0 5px #fff; } 50% { box-shadow: 0 0 25px #fff; } 100% { box-shadow: 0 0 5px #fff; } }
    .stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 20px; border-radius: 15px; margin-bottom: 25px; }
    .volume-spike { animation: pulse-white 2s infinite; border: 1px solid #ffffff!important; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 10px; }
    .status-sell { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; border: 2px solid #ff0055; padding: 5px 15px; border-radius: 10px; }
    .box-tp { border-left: 4px solid #00ff88; padding: 10px; background: rgba(0,255,136,0.05); color: #00ff88; font-weight: bold; }
    .box-sl { border-left: 4px solid #ff0055; padding: 10px; background: rgba(255,0,85,0.05); color: #ff0055; font-weight: bold; }
    .top-tile { background: #111; border: 1px solid #333; padding: 10px; border-radius: 10px; text-align: center; border-bottom: 2px solid #58a6ff; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def get_full_analysis(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        h1 = t.history(period="15d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty or d1.empty: return None
        h1, d1 = fix_col(h1), fix_col(d1)
        
        price = float(h1['Close'].iloc[-1])
        ma50 = float(d1['Close'].rolling(50).mean().iloc[-1])
        ma200 = float(d1['Close'].rolling(200).mean().iloc[-1])
        
        h, l, c = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (h + l + c) / 3
        r1, s1 = (2 * pp) - l, (2 * pp) - h
        
        vol_rel = d1['Volume'].iloc[-1] / (d1['Volume'].tail(20).mean() + 1e-9)
        delta = d1['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))))).iloc[-1]
        
        return {
            "symbol": symbol.strip().upper(), "price": price, "rsi": rsi, "ma50": ma50, "ma200": ma200, 
            "pp": pp, "r1": r1, "s1": s1, "vol_rel": vol_rel, "df": h1.tail(50), 
            "d1_hist": d1.tail(10)[['Close']].to_string(), "change": ((price - c) / c * 100)
        }
    except: return None

def get_ai_verdict(d, api_key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=api_key)
        prompt = (f"Trader PRO. Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, MA50:{d['ma50']:.1f}, Pivot:{d['pp']:.2f}. "
                  f"Ostatnie 10 dni ceny:\n{d['d1_hist']}\n"
                  f"Zwróć JSON: {{\"w\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", \"sl\": cena, \"tp\": cena, \"u\": \"max 8 slow\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("⚡ MASTER OMNI v88")
    key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    cap = st.number_input("💵 Kapitał:", value=10000.0)
    t_in = st.text_area("Lista Symboli:", value=load_tickers(), height=150)
    if st.button("🚀 INICJUJ SYSTEM"):
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()
    st_autorefresh(interval=60000, key="v88_ref")

# --- 5. DASHBOARD ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [d for d in list(executor.map(get_full_analysis, symbols)) if d is not None]

if data_list:
    # RANKING TOP 10
    st.subheader("🔥 TOP 10 SYGNAŁÓW (RSI)")
    t_cols = st.columns(5)
    for i, r in enumerate(sorted(data_list, key=lambda x: x['rsi'])[:10]):
        with t_cols[i % 5]:
            st.markdown(f"<div class='top-tile'><b>{r['symbol']}</b><br><small>RSI: {r['rsi']:.1f}</small></div>", unsafe_allow_html=True)

    st.divider()

    for d in data_list:
        ai = get_ai_verdict(d, key) if key else None
        spike = "volume-spike" if d['vol_rel'] > 2.0 else ""
        
        st.markdown(f'<div class="neon-card {spike}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 2.5, 1.5])
        
        with c1:
            st.markdown(f"### {d['symbol']} {'🔥' if d['vol_rel'] > 2.0 else ''}")
            if ai:
                v_style = "status-buy" if ai['w'] == "KUP" else "status-sell" if ai['w'] == "SPRZEDAJ" else "status-hold"
                st.markdown(f'<span class="{v_style}">{ai["w"]}</span>', unsafe_allow_html=True)
            st.markdown(f"<br>Cena: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.write(f"RSI: {d['rsi']:.1f} | MA50: {d['ma50']:.2f}")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dot", line_color="#58a6ff", annotation_text="PP")
            fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f'<div class="box-tp">TAKE PROFIT: {ai["tp"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="margin-top:10px;" class="box-sl">STOP LOSS: {ai["sl"]}</div>', unsafe_allow_html=True)
                
                # Kalkulator
                diff = abs(d['price'] - float(ai['sl']))
                shares = int((cap * 0.02) / diff) if diff > 0 else 0
                st.markdown(f"""<div style='background:#111; padding:15px; border-radius:10px; border:1px solid #333; margin-top:10px; text-align:center;'>
                    KUP: <b style='color:#00ff88; font-size:1.2rem;'>{shares} szt.</b><br><small>{ai['u']}</small></div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj tickery i sprawdź klucz API.")
