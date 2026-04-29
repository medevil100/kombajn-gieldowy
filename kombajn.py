import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os
from datetime import datetime

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
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; }
    .status-sell { color: #ff4b4b; text-shadow: 0 0 10px #ff4b4b; font-weight: bold; }
    .ai-full-box { background: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; padding: 15px; margin-top: 10px; border-radius: 5px; font-size: 0.9rem; }
    .tp-box { color: #00ff88; font-weight: bold; }
    .sl-box { color: #ff4b4b; font-weight: bold; }
    .trend-tag { padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_usdpln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        return float(data['Close'].iloc[-1])
    except:
        return 4.0  # Kurs awaryjny

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        
        p = float(df['Close'].iloc[-1])
        h, l = float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
        pp = (df['High'].iloc[-2] + df['Low'].iloc[-2] + df['Close'].iloc[-2]) / 3
        
        bid = p * 0.9998
        ask = p * 1.0002
        
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else sma50
        trends = {"K": "UP" if p > sma20 else "DN", "S": "UP" if p > sma50 else "DN", "D": "UP" if p > sma200 else "DN"}

        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        
        return {
            "symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, 
            "rsi": rsi, "pp": pp, "high": h, "low": l, 
            "change": ((p - df['Close'].iloc[-2])/df['Close'].iloc[-2]*100), 
            "trends": trends, "df": df.tail(45)
        }
    except: return None

def run_ai_short(d, key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = f"Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, Pivot:{d['pp']:.2f}. Zwróć JSON: {{\"w\": \"KUP/SPRZEDAJ/TRZYMAJ\", \"sl\": {round(d['price']*0.95, 4)}, \"tp\": {round(d['price']*1.15, 4)}}}"
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        res['sl'] = round(float(res.get('sl', 0)), 4)
        res['tp'] = round(float(res.get('tp', 0)), 4)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL STEROWANIA ---
usd_pln_rate = get_usdpln()

with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    st.markdown(f"**Kurs USD/PLN: {usd_pln_rate:.4f}**")
    st.session_state.risk_cap_pln = st.number_input("💵 Kapitał (PLN):", value=float(st.session_state.risk_cap_pln))
    risk_per_trade = st.slider("🎯 Ryzyko (%)", 0.1, 5.0, 1.0)
    
    st_autorefresh(interval=120000, key="auto_ref")
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers, height=150)
    if st.button("🚀 SKANUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.ai_results = {}; st.session_state.full_analysis = {}
        st.rerun()

# --- 5. LOGIKA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = []
for sym in symbols:
    res = get_data(sym)
    if res:
        if api_key: res['ai'] = run_ai_short(res, api_key)
        data_list.append(res)

if data_list:
    st.subheader("🔥 TOP 10 RADAR")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5); cols2 = st.columns(5); all_cols = cols + cols2
    
    for i, r in enumerate(sorted_top):
        if i < len(all_cols):
            with all_cols[i]:
                ai_v = r.get('ai', {}).get('w', '---').upper()
                v_col = "#00ff88" if "KUP" in ai_v else "#ff4b4b" if "SPRZEDAJ" in ai_v else "#58a6ff"
                st.markdown(f'<div class="top-tile" style="border-bottom: 4px solid {v_col};"><b>{r["symbol"]}</b><br>{r["price"]:.2f}<br><small>RSI: {r["rsi"]:.1f}</small></div>', unsafe_allow_html=True)

    st.divider()

    for d in data_list:
        ai = d.get('ai')
        card_border = "neon-card-buy" if ai and "KUP" in str(ai.get('w','')).upper() else ""
        st.markdown(f'<div class="neon-card {card_border}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 1.5])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            t_html = "".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span>' for k,v in d['trends'].items()])
            st.markdown(t_html, unsafe_allow_html=True)
            st.markdown(f"CENA: **{d['price']:.4f} USD**")
            st.markdown(f"B: <span style='color:#00ff88'>{d['bid']:.4f}</span> | A: <span style='color:#ff4b4b'>{d['ask']:.4f}</span>", unsafe_allow_html=True)
            st.write(f"RSI: **{d['rsi']:.1f}**")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f"<span class='tp-box'>TP: {ai.get('tp')}</span><br><span class='sl-box'>SL: {ai.get('sl')}</span>", unsafe_allow_html=True)
                
                # KALKULATOR W PLN
                try:
                    sl_price_usd = float(ai['sl'])
                    diff_usd = abs(d['price'] - sl_price_usd)
                    
                    # Kapitał w PLN przeliczony na USD dla kalkulacji sztuk
                    risk_pln = st.session_state.risk_cap_pln * (risk_per_trade / 100)
                    risk_usd = risk_pln / usd_pln_rate
                    
                    if diff_usd > 0:
                        shares = int(risk_usd / diff_usd)
                        st.success(f"KUP: {shares} szt.")
                        st.caption(f"Ryzyko: {risk_pln:.2f} PLN")
                        st.caption(f"Wartość: {(shares * d['price'] * usd_pln_rate):.2f} PLN")
                except: pass
        st.markdown('</div>', unsafe_allow_html=True)
