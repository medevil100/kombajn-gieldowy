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

# --- 1. RDZEŃ I PAMIĘĆ ---
DB_FILE = "moje_spolki.txt"
st.set_page_config(page_title="NEON MASTER OMNI v91", page_icon="🚜", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
    return "NVDA, TSLA, BTC-USD, PKO.WA"

# --- 2. STYLE NEONOWE (MAX ROZBUDOWA) ---
st.markdown("""
    <style>
    @keyframes pulse-white { 0% { box-shadow: 0 0 5px #fff; } 50% { box-shadow: 0 0 25px #fff; } 100% { box-shadow: 0 0 5px #fff; } }
    .stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 25px; border-radius: 15px; margin-bottom: 25px; }
    .vol-spike { animation: pulse-white 2s infinite; border: 1px solid #ffffff!important; }
    .status-buy { color: #00ff88; text-shadow: 0 0 15px #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 10px; text-transform: uppercase; }
    .status-sell { color: #ff0055; text-shadow: 0 0 15px #ff0055; font-weight: bold; border: 2px solid #ff0055; padding: 5px 15px; border-radius: 10px; text-transform: uppercase; }
    .status-hold { color: #58a6ff; text-shadow: 0 0 15px #58a6ff; font-weight: bold; border: 2px solid #58a6ff; padding: 5px 15px; border-radius: 10px; text-transform: uppercase; }
    .tp-box { border: 1px solid #00ff88; padding: 12px; border-radius: 10px; color: #00ff88; text-align: center; background: rgba(0,255,136,0.05); font-weight: bold; }
    .sl-box { border: 1px solid #ff0055; padding: 12px; border-radius: 10px; color: #ff0055; text-align: center; background: rgba(255,0,85,0.05); font-weight: bold; }
    .top-tile { background: #111; border: 1px solid #333; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 3px solid #58a6ff; }
    .uzas-text { font-style: italic; color: #888; font-size: 0.85rem; margin-top: 10px; border-top: 1px solid #222; padding-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY TECHNICZNEJ ---
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        df = fix_col(df)
        p = float(df['Close'].iloc[-1])
        # Rozbudowane wskaźniki
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma100 = df['Close'].rolling(100).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]
        h, l, c = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pp = (h + l + c) / 3
        r1, s1 = (2 * pp) - l, (2 * pp) - h
        vol_rel = df['Volume'].iloc[-1] / (df['Volume'].tail(20).mean() + 1e-9)
        delta = df['Close'].diff()
        rsi = (100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))))).iloc[-1]
        
        return {
            "symbol": symbol.strip().upper(), "price": p, "rsi": rsi, 
            "ma50": ma50, "ma100": ma100, "ma200": ma200, "pp": pp, "r1": r1, "s1": s1,
            "vol": vol_rel, "df": df.tail(45), "change": ((p - c) / c * 100)
        }
    except: return None

def run_ai(d, key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = (f"Jesteś algorytmem tradingowym PRO. Analiza {d['symbol']} @ {d['price']}.\n"
                  f"DANE: RSI:{d['rsi']:.1f}, MA50:{d['ma50']:.1f}, MA200:{d['ma200']:.1f}, Pivot:{d['pp']:.2f}, Wolumen:x{d['vol']:.1f}.\n"
                  f"Ostatnie 5 cen: {d['df']['Close'].tail(5).tolist()}.\n"
                  f"Zwróć JSON: {{\"w\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", \"sl\": cena, \"tp\": cena, \"u\": \"max 8 slow uzasadnienia\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices.message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("⚡ OMNI v91 PRO")
    key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    cap = st.number_input("💰 Kapitał Portfela:", value=10000.0)
    t_in = st.text_area("Lista Symboli (CSV):", value=load_tickers(), height=150)
    if st.button("🚀 URUCHOM SYSTEM"):
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()
    st_autorefresh(interval=60000, key="v91_refresh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_in.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [d for d in list(executor.map(get_data, tickers)) if d is not None]

if data_list:
    # --- ROZBUDOWANY RANKING TOP 10 ---
    st.subheader("🔥 MONITOR SYGNAŁÓW TOP 10")
    t_cols = st.columns(5)
    sorted_data = sorted(data_list, key=lambda x: x['rsi'])[:10]
    for i, r in enumerate(sorted_data):
        ai_brief = run_ai(r, key) if key else None
        v_tag = ai_brief['w'] if ai_brief else "---"
        v_col = "#00ff88" if v_tag == "KUP" else "#ff4b4b" if v_tag == "SPRZEDAJ" else "#58a6ff"
        with t_cols[i % 5]:
            st.markdown(f"""
                <div class='top-tile'>
                    <b style='font-size:1.1rem;'>{r['symbol']}</b><br>
                    <span style='color:{v_col}; font-weight:bold; font-size:0.9rem;'>{v_tag}</span><br>
                    <small>RSI: {r['rsi']:.1f} | x{r['vol']:.1f} VOL</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA KART INSTRUMENTÓW ---
    for d in data_list:
        ai = run_ai(d, key) if key else None
        spike = "vol-spike" if d['vol'] > 2.0 else ""
        
        st.markdown(f'<div class="neon-card {spike}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 2.5, 1.5])
        
        with c1:
            st.markdown(f"### {d['symbol']} {'🔥' if d['vol'] > 2.0 else ''}")
            if ai:
                v_class = "status-buy" if ai['w'] == "KUP" else "status-sell" if ai['w'] == "SPRZEDAJ" else "status-hold"
                st.markdown(f'<span class="{v_class}">{ai["w"]}</span>', unsafe_allow_html=True)
            st.markdown(f"<br>Cena: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.write(f"RSI: {d['rsi']:.1f} | R-Vol: x{d['vol']:.1f}")
            st.markdown(f"<small>MA50: {d['ma50']:.2f} | MA200: {d['ma200']:.2f}</small>", unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dot", line_color="#58a6ff", annotation_text="Pivot")
            fig.add_hline(y=d['r1'], line_dash="dash", line_color="#00ff88", opacity=0.3)
            fig.add_hline(y=d['s1'], line_dash="dash", line_color="#ff4b4b", opacity=0.3)
            fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f'<div class="tp-box"><small>TARGET PROFIT</small><br>{ai["tp"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="margin-top:10px;" class="sl-box"><small>STOP LOSS</small><br>{ai["sl"]}</div>', unsafe_allow_html=True)
                
                # Kalkulator Wielkości Pozycji (Ryzyko 2% portfela)
                diff = abs(d['price'] - float(ai['sl']))
                risk_money = cap * 0.02
                shares = int(risk_money / diff) if diff > 0 else 0
                
                st.markdown(f"""
                <div style='background:#111; padding:15px; border-radius:12px; border:1px solid #333; margin-top:15px; text-align:center;'>
                    <span style='color:#888; font-size:0.8rem;'>WIELKOŚĆ POZYCJI:</span><br>
                    <b style='color:#00ff88; font-size:1.4rem;'>{shares} szt.</b><br>
                    <small>Koszt: {(shares * d['price']):.2f}</small>
                    <div class="uzas-text">{ai['u']}</div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj tickery i sprawdź klucz API. System oczekuje na start.")
