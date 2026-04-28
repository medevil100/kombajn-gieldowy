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
LOG_FILE = "trade_log.json"
st.set_page_config(page_title="OMNI MASTER v85 PRO", page_icon="🚜", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "last_signals" not in st.session_state: st.session_state.last_signals = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
    return "NVDA, TSLA, BTC-USD, ETH-USD"

def load_trades():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f: return json.load(f)
        except: return []
    return []

# --- 2. NEON STYLE + ANIMACJE ---
st.markdown("""
    <style>
    @keyframes pulse-white { 0% { box-shadow: 0 0 5px #fff; } 50% { box-shadow: 0 0 25px #fff; } 100% { box-shadow: 0 0 5px #fff; } }
    .stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 25px; border-radius: 15px; margin-bottom: 25px; }
    .volume-spike { animation: pulse-white 2s infinite; border: 1px solid #ffffff!important; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 10px; }
    .status-sell { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; border: 2px solid #ff0055; padding: 5px 15px; border-radius: 10px; }
    .tp-box { border-left: 4px solid #00ff88; padding: 10px; background: rgba(0,255,136,0.05); color: #00ff88; font-weight: bold; }
    .sl-box { border-left: 4px solid #ff0055; padding: 10px; background: rgba(255,0,85,0.05); color: #ff0055; font-weight: bold; }
    .top-tile { background: #111; border: 1px solid #333; padding: 10px; border-radius: 10px; text-align: center; }
    .alert-box { background: rgba(255,0,85,0.2); border: 2px solid #ff0055; padding: 10px; text-align: center; border-radius: 10px; margin-bottom: 10px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        p = float(df['Close'].iloc[-1])
        ma50, ma100, ma200 = df['Close'].rolling(50).mean().iloc[-1], df['Close'].rolling(100).mean().iloc[-1], df['Close'].rolling(200).mean().iloc[-1]
        h, l, c = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pp = (h + l + c) / 3
        r1, s1 = (2 * pp) - l, (2 * pp) - h
        vol_rel = df['Volume'].iloc[-1] / df['Volume'].tail(20).mean()
        
        delta = df['Close'].diff()
        rsi = (100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))))).iloc[-1]
        
        return {"symbol": symbol.strip().upper(), "price": p, "rsi": rsi, "ma50": ma50, "ma100": ma100, "ma200": ma200, "pp": pp, "r1": r1, "s1": s1, "vol_rel": vol_rel, "df": df.tail(45), "change": ((p - c) / c * 100)}
    except: return None

def run_ai(d, api_key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=api_key)
        prompt = (f"Jesteś PRO Traderem. Analizuj {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, MA50:{d['ma50']:.1f}, MA200:{d['ma200']:.1f}, Pivot:{d['pp']:.2f}. "
                  f"Ostatnie 10 świec zamknięcia: {d['df']['Close'].tail(10).tolist()}. "
                  f"Zwróć JSON: {{\"werdykt\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", \"sl\": cena, \"tp\": cena, \"uzas\": \"max 10 slow\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices.message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 MASTER v85")
    key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    cap = st.number_input("💵 Kapitał:", value=10000.0)
    t_in = st.text_area("Tickery (CSV):", value=load_tickers(), height=150)
    if st.button("🚀 INICJUJ SYSTEM"):
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()
    st_autorefresh(interval=60000, key="v85_refresh")

# --- 5. DASHBOARD ---
trades = load_trades()
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [d for d in list(executor.map(get_data, symbols)) if d is not None]

if data_list:
    # --- SENTINEL ALERTS ---
    for t in trades:
        match = next((x for x in data_list if x['symbol'] == t['symbol']), None)
        if match and match['price'] <= t['sl']:
            st.markdown(f'<div class="alert-box">🚨 {t["symbol"]} PRZEBIŁ STOP-LOSS ({t["sl"]})! CENA: {match["price"]:.2f}</div>', unsafe_allow_html=True)

    # --- TOP 10 RANKING ---
    st.subheader("🔥 RANKING OKAZJI (RSI)")
    t_cols = st.columns(5)
    for i, r in enumerate(sorted(data_list, key=lambda x: x['rsi'])[:10]):
        with t_cols[i % 5]:
            st.markdown(f"<div class='top-tile'><b>{r['symbol']}</b><br><small>RSI: {r['rsi']:.1f}</small></div>", unsafe_allow_html=True)

    st.divider()

    # --- LISTA GŁÓWNA ---
    for d in data_list:
        ai = run_ai(d, key) if key else None
        spike = "volume-spike" if d['vol_rel'] > 2.0 else ""
        
        st.markdown(f'<div class="neon-card {spike}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 2.5, 1.5])
        
        with c1:
            st.markdown(f"### {d['symbol']} {'🔥' if d['vol_rel'] > 2.0 else ''}")
            if ai:
                v_style = "status-buy" if ai['werdykt'] == "KUP" else "status-sell" if ai['werdykt'] == "SPRZEDAJ" else "neon-hold"
                st.markdown(f'<span class="{v_style}">{ai["werdykt"]}</span>', unsafe_allow_html=True)
            st.markdown(f"<br>Cena: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.write(f"RSI: {d['rsi']:.1f} | R-Vol: x{d['vol_rel']:.1f}")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dot", line_color="#58a6ff", annotation_text="Pivot")
            fig.add_hline(y=d['r1'], line_dash="dash", line_color="#00ff88", opacity=0.3)
            fig.add_hline(y=d['s1'], line_dash="dash", line_color="#ff0055", opacity=0.3)
            fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f'<div class="tp-box">TAKE PROFIT: {ai["tp"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="sl-box">STOP LOSS: {ai["sl"]}</div>', unsafe_allow_html=True)
                
                diff = abs(d['price'] - float(ai['sl']))
                shares = int((cap * 0.02) / diff) if diff > 0 else 0
                st.markdown(f"""<div style='background:#111; padding:15px; border-radius:10px; border:1px solid #333; margin-top:10px; text-align:center;'>
                    <small>KUP: <b>{shares} szt.</b> (Risk 2%)</small><br>
                    <small><i>{ai['uzas']}</i></small></div>""", unsafe_allow_html=True)
                
                if st.button(f"📥 ZAPISZ POZYCJĘ", key=f"log_{d['symbol']}"):
                    trades.append({"symbol": d['symbol'], "price": d['price'], "shares": shares, "sl": ai['sl'], "tp": ai['tp'], "cost": shares * d['price']})
                    with open(LOG_FILE, "w") as f: json.dump(trades, f)
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# Historia na samym dole
if trades:
    with st.expander("📓 DZIENNIK TREJDÓW"):
        st.table(pd.DataFrame(trades).tail(5))
