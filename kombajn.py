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

# --- 2. STYLE NEONOWE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; min-height: 100px; }
    .trend-tag { padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; border: 1px solid #333; }
    .calc-box { background: rgba(88, 166, 255, 0.05); border: 1px solid #58a6ff; padding: 10px; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_usdpln():
    try: return float(yf.Ticker("USDPLN=X").fast_info['last_price'])
    except: return 4.0

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        
        p = t.fast_info['last_price']
        # Próba pobrania realnego bid/ask, jeśli nie ma - symulacja 0.02% spreadu
        info = t.info
        bid = info.get('bid') if info.get('bid', 0) > 0 else p * 0.9998
        ask = info.get('ask') if info.get('ask', 0) > 0 else p * 1.0002
        
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else sma50
        trends = {"K": "UP" if p > sma20 else "DN", "S": "UP" if p > sma50 else "DN", "D": "UP" if p > sma200 else "DN"}

        return {
            "symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, "rsi": rsi, 
            "trends": trends, "df": df.tail(45)
        }
    except: return None

def run_ai_short(d, key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = f"Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}. Zwróć JSON: {{\"w\": \"KUP\", \"sl\": {round(d['price']*0.95, 2)}, \"tp\": {round(d['price']*1.1, 2)}}}"
        resp = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except Exception as e:
        return {"w": "BŁĄD AI", "sl": 0, "tp": 0}

# --- 4. PANEL BOCZNY ---
usd_pln_rate = get_usdpln()
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.text_input("OpenAI Key", type="password", value=st.secrets.get("OPENAI_API_KEY", ""))
    st.session_state.risk_cap_pln = st.number_input("💵 Kapitał (PLN):", value=float(st.session_state.risk_cap_pln))
    risk_pct = st.slider("🎯 Ryzyko na spółkę (%)", 1, 100, 10)
    
    amount_per_trade_pln = st.session_state.risk_cap_pln * (risk_pct / 100)
    
    st_autorefresh(interval=2 * 60 * 1000, key="auto_ref")
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers)
    if st.button("🚀 SKANUJ / RESET"):
        st.session_state.ai_results = {}
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

# --- 5. WYŚWIETLANIE ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = []
for sym in symbols:
    res = get_data(sym)
    if res:
        if api_key: res['ai'] = run_ai_short(res, api_key)
        data_list.append(res)

if data_list:
    # RADAR
    st.subheader("🔥 RADAR RSI")
    r_cols = st.columns(len(data_list[:8]))
    for i, r in enumerate(data_list[:8]):
        with r_cols[i]:
            st.markdown(f"<div class='top-tile'><b>{r['symbol']}</b><br>{r['price']:.2f}<br><small>RSI: {r['rsi']:.1f}</small></div>", unsafe_allow_html=True)

    st.divider()

    for d in data_list:
        ai = d.get('ai', {"w": "WAIT", "sl": 0, "tp": 0})
        is_buy = "KUP" in str(ai.get('w')).upper()
        
        st.markdown(f'<div class="neon-card {"neon-card-buy" if is_buy else ""}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 2])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            # K:S:D
            st.markdown("".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span>' for k,v in d['trends'].items()]), unsafe_allow_html=True)
            st.markdown(f"<h3 style='color:{"#00ff88" if is_buy else "#ff4b4b"}'>{ai['w']}</h3>", unsafe_allow_html=True)
            st.write(f"CENA: {d['price']:.2f}")
            # BID / ASK
            st.markdown(f"<small>BID: <span style='color:#00ff88'>{d['bid']:.2f}</span> | ASK: <span style='color:#ff4b4b'>{d['ask']:.2f}</span></small>", unsafe_allow_html=True)
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=180, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{d['symbol']}")
            
        with c3:
            # KALKULATOR
            price_pln = d['ask'] * usd_pln_rate
            qty = int(amount_per_trade_pln / price_pln) if price_pln > 0 else 0
            st.markdown(f'<div class="calc-box">', unsafe_allow_html=True)
            st.markdown(f"**ILOŚĆ DO KUPNA:**")
            st.markdown(f"<h2 style='color:#00ff88; margin:0;'>{qty} szt.</h2>", unsafe_allow_html=True)
            st.write(f"Koszt: {(qty * price_pln):.2f} PLN")
            st.write(f"USD/PLN: {usd_pln_rate:.4f}")
            st.markdown(f"<span style='color:#00ff88'>TP: {ai['tp']}</span> | <span style='color:#ff4b4b'>SL: {ai['sl']}</span>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

