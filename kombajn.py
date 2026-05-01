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
if "full_analysis" not in st.session_state: st.session_state.full_analysis = {}
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
    .calc-box { background: rgba(88, 166, 255, 0.05); border: 1px solid #58a6ff; padding: 10px; border-radius: 8px; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_usdpln():
    try:
        ticker = yf.Ticker("USDPLN=X")
        return float(ticker.fast_info['last_price'])
    except: return 4.0

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        
        # Cena LIVE i realny Bid/Ask
        p = t.fast_info['last_price']
        info = t.info
        bid = info.get('bid') or p * 0.9998
        ask = info.get('ask') or p * 1.0002
        
        # RSI
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        
        # Trendy K/S/D
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
        prompt = f"Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}. Zwróć JSON: {{\"w\": \"KUP/SPRZEDAJ/TRZYMAJ\", \"sl\": {round(d['price']*0.95, 4)}, \"tp\": {round(d['price']*1.15, 4)}}}"
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL BOCZNY ---
usd_pln_rate = get_usdpln()
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap_pln = st.number_input("💵 Kapitał (PLN):", value=float(st.session_state.risk_cap_pln))
    risk_per_trade_pct = st.slider("🎯 Ryzyko na spółkę (%)", 1.0, 50.0, 10.0)
    
    amount_per_trade_pln = st.session_state.risk_cap_pln * (risk_per_trade_pct / 100)
    
    refresh_min = st.slider("⏱️ Odświeżanie (min)", 1, 10, 2)
    st_autorefresh(interval=refresh_min * 60 * 1000, key="auto_ref")
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers)
    
    if st.button("🚀 SKANUJ"):
        st.session_state.ai_results = {}; st.session_state.full_analysis = {}
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.rerun()

# --- 5. LOGIKA GŁÓWNA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = []
for sym in symbols:
    res = get_data(sym)
    if res:
        if api_key: res['ai'] = run_ai_short(res, api_key)
        data_list.append(res)

if data_list:
    # --- RADAR TOP 10 ---
    st.subheader("🔥 TOP 10 RADAR (RSI)")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5)
    for i, r in enumerate(sorted_top):
        with cols[i % 5]:
            ai_v = r.get('ai', {}).get('w', '---').upper()
            v_col = "#00ff88" if "KUP" in ai_v else "#ff4b4b" if "SPRZEDAJ" in ai_v else "#58a6ff"
            st.markdown(f'<div class="top-tile" style="border-bottom: 4px solid {v_col};"><b>{r["symbol"]}</b><br><span style="color:{v_col}">{r["price"]:.2f}</span><br><small>RSI: {r["rsi"]:.1f}</small></div>', unsafe_allow_html=True)

    st.divider()

    # --- LISTA GŁÓWNA ---
    for d in data_list:
        ai = d.get('ai')
        is_buy = ai and "KUP" in str(ai.get('w','')).upper()
        card_class = "neon-card-buy" if is_buy else ""
        
        st.markdown(f'<div class="neon-card {card_class}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 2])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            # Trendy K/S/D
            t_html = "".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span>' for k,v in d['trends'].items()])
            st.markdown(t_html, unsafe_allow_html=True)
            if ai: st.markdown(f"<h3 style='color:{"#00ff88" if is_buy else "#ff4b4b"};'>{ai['w']}</h3>", unsafe_allow_html=True)
            st.write(f"CENA: **{d['price']:.2f} USD**")
            st.write(f"RSI: **{d['rsi']:.1f}**")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"c_{d['symbol']}")

        with c3:
            # KALKULATOR POZYCJI
            price_pln = d['ask'] * usd_pln_rate
            qty = int(amount_per_trade_pln / price_pln) if price_pln > 0 else 0
            
            st.markdown(f'<div class="calc-box">', unsafe_allow_html=True)
            st.markdown("🎯 **DO KUPNA (PLN):**")
            st.markdown(f"<h2 style='color:#00ff88; margin:0;'>{qty} <small>szt.</small></h2>", unsafe_allow_html=True)
            st.write(f"Koszt: {(qty * price_pln):.2f} PLN")
            st.markdown("---")
            if ai:
                st.markdown(f"<span style='color:#00ff88'>TP: {ai['tp']}</span> | <span style='color:#ff4b4b'>SL: {ai['sl']}</span>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
