import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="NEON COMMANDER v102", page_icon="⚡", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "risk_cap_pln" not in st.session_state: st.session_state.risk_cap_pln = 40000.0

DB_FILE = "moje_spolki.txt"

# --- 2. STYLE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 10px; text-align: center; border-bottom: 4px solid #58a6ff; min-height: 120px; }
    .trend-tag { padding: 2px 4px; border-radius: 4px; font-size: 0.65rem; margin-right: 2px; border: 1px solid #444; }
    .calc-box { background: rgba(88, 166, 255, 0.05); border: 1px solid #58a6ff; padding: 10px; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- 3. SILNIK ---
def get_usdpln():
    try: return float(yf.Ticker("USDPLN=X").fast_info['last_price'])
    except: return 4.0

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        p = t.fast_info['last_price']
        info = t.info
        bid = info.get('bid') or p * 0.9998
        ask = info.get('ask') or p * 1.0002
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        sma20, sma50, sma200 = df['Close'].rolling(20).mean().iloc[-1], df['Close'].rolling(50).mean().iloc[-1], df['Close'].rolling(200).mean().iloc[-1]
        trends = {"K": "UP" if p > sma20 else "DN", "S": "UP" if p > sma50 else "DN", "D": "UP" if p > (sma200 if not pd.isna(sma200) else sma50) else "DN"}
        return {"symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, "rsi": rsi, "trends": trends, "df": df.tail(45)}
    except: return None

def run_ai_short(d, key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = f"Analiza {d['symbol']} cena {d['price']}. RSI {d['rsi']:.1f}. Zwróć JSON: {{\"w\": \"KUP\", \"sl\": {round(d['price']*0.95, 2)}, \"tp\": {round(d['price']*1.1, 2)}}}"
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return {"w": "CZEKAJ", "sl": 0, "tp": 0}

# --- 4. SIDEBAR ---
usd_pln_rate = get_usdpln()
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap_pln = st.number_input("Kapitał PLN:", value=float(st.session_state.risk_cap_pln))
    risk_pct = st.slider("Ryzyko %", 1, 100, 10)
    st_autorefresh(interval=2 * 60 * 1000, key="ref")
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA"
    t_in = st.text_area("Tickery:", value=default_tickers)
    if st.button("🚀 SKANUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()

# --- 5. MAIN ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = [get_data(s) for s in symbols if get_data(s)]

if data_list:
    st.subheader("🔥 RADAR RSI (NAJNIŻSZE)")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    r_cols = st.columns(len(sorted_top))
    for i, r in enumerate(sorted_top):
        with r_cols[i]:
            t_str = "".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}</span>' for k,v in r['trends'].items()])
            st.markdown(f'<div class="top-tile"><b>{r["symbol"]}</b><br>{r["price"]:.2f}<br>{t_str}<br><small>RSI: {r["rsi"]:.1f}</small></div>', unsafe_allow_html=True)

    for d in data_list:
        ai = run_ai_short(d, api_key) if api_key else {"w": "BRAK KLUCZA", "sl": 0, "tp": 0}
        is_buy = "KUP" in ai['w'].upper()
        st.markdown(f'<div class="neon-card {"neon-card-buy" if is_buy else ""}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 2])
        with c1:
            st.markdown(f"## {d['symbol']}")
            st.markdown("".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span>' for k,v in d['trends'].items()]), unsafe_allow_html=True)
            st.markdown(f"<h3 style='color:{"#00ff88" if is_buy else "#ff4b4b"}'>{ai['w']}</h3>", unsafe_allow_html=True)
            st.write(f"CENA: {d['price']:.2f} | RSI: {d['rsi']:.1f}")
            st.markdown(f"<small>B: {d['bid']:.2f} | A: {d['ask']:.2f}</small>", unsafe_allow_html=True)
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=180, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"c_{d['symbol']}")
        with c3:
            price_pln = d['ask'] * usd_pln_rate
            qty = int((st.session_state.risk_cap_pln * (risk_pct/100)) / price_pln) if price_pln > 0 else 0
            st.markdown(f'<div class="calc-box"><b>DO KUPNA:</b><h2 style="color:#00ff88; margin:0;">{qty} szt.</h2><small>Koszt: {(qty*price_pln):.2f} PLN</small><br>TP: {ai["tp"]} | SL: {ai["sl"]}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
