import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os

# --- 1. KONFIGURACJA I TRWAŁOŚĆ DANYCH ---
st.set_page_config(page_title="NEON COMMANDER v102", page_icon="⚡", layout="wide")

# Pliki do zapisu
DB_FILE = "moje_spolki.txt"
CAPITAL_FILE = "kapital.txt"

# Funkcje zapisu/odczytu kapitału
def load_capital():
    if os.path.exists(CAPITAL_FILE):
        with open(CAPITAL_FILE, "r") as f: return float(f.read())
    return 40000.0

def save_capital(val):
    with open(CAPITAL_FILE, "w") as f: f.write(str(val))

# Inicjalizacja stanu
if "risk_cap_pln" not in st.session_state: st.session_state.risk_cap_pln = load_capital()
if "ai_results" not in st.session_state: st.session_state.ai_results = {}

# AUTO-ODŚWIEŻANIE (60 sekund)
st_autorefresh(interval=60 * 1000, key="global_refresh")

# --- 2. STYLE NEONOWE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; min-height: 100px; }
    .ai-reason { background: rgba(88, 166, 255, 0.1); border-left: 3px solid #58a6ff; padding: 10px; font-size: 0.85rem; margin-top: 10px; color: #accaff; }
    .trend-tag { padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; border: 1px solid #333; }
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
        info = t.info
        # Realne dane BID/ASK z giełdy
        bid, ask = info.get('bid') or p * 0.9998, info.get('ask') or p * 1.0002
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        sma20, sma50, sma200 = df['Close'].rolling(20).mean().iloc[-1], df['Close'].rolling(50).mean().iloc[-1], df['Close'].rolling(200).mean().iloc[-1]
        trends = {"K": "UP" if p > sma20 else "DN", "S": "UP" if p > sma50 else "DN", "D": "UP" if p > sma200 else "DN"}
        return {"symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, "rsi": rsi, "trends": trends, "df": df.tail(45)}
    except: return None

def run_ai_short(d, key):
    try:
        client = OpenAI(api_key=key)
        prompt = f"Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, Trends:{d['trends']}. Zwróć JSON: {{\"w\": \"KUP/SPRZEDAJ/CZEKAJ\", \"sl\": {round(d['price']*0.95, 2)}, \"tp\": {round(d['price']*1.12, 2)}, \"u\": \"Krótkie uzasadnienie 10 słów\"}}"
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        return json.loads(resp.choices[0].message.content)
    except: return {"w": "CZEKAJ", "sl": 0, "tp": 0, "u": "Brak połączenia z AI"}

# --- 4. PANEL ---
usd_pln_rate = get_usdpln()
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    new_cap = st.number_input("💵 Twój Portfel (PLN):", value=st.session_state.risk_cap_pln)
    if new_cap != st.session_state.risk_cap_pln:
        st.session_state.risk_cap_pln = new_cap
        save_capital(new_cap)

    risk_pct = st.slider("🎯 Ryzyko na spółkę (%)", 1, 100, 10)
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers, height=150)
    if st.button("🚀 SKANUJ I ZAPISZ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()

# --- 5. LOGIKA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = [get_data(s) for s in symbols if get_data(s)]

if data_list:
    # RADAR TOP 10
    st.subheader("🔥 RADAR RSI")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5); cols2 = st.columns(5); all_cols = cols + cols2
    for i, r in enumerate(sorted_top):
        with all_cols[i]:
            res_ai = run_ai_short(r, api_key) if api_key else {"w": "---"}
            v_col = "#00ff88" if "KUP" in res_ai['w'].upper() else "#ff4b4b" if "SPRZEDAJ" in res_ai['w'].upper() else "#58a6ff"
            st.markdown(f'<div class="top-tile" style="border-bottom:4px solid {v_col}"><b>{r["symbol"]}</b><br><span style="color:{v_col}">{r["price"]:.2f}</span><br><small>{res_ai["w"]}</small></div>', unsafe_allow_html=True)

    st.divider()

    for d in data_list:
        ai = run_ai_short(d, api_key) if api_key else {"w": "BRAK AI", "sl": 0, "tp": 0, "u": ""}
        is_buy = "KUP" in str(ai['w']).upper()
        
        st.markdown(f'<div class="neon-card {"neon-card-buy" if is_buy else ""}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 1.5])
        with c1:
            st.markdown(f"## {d['symbol']}")
            st.markdown("".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span>' for k,v in d['trends'].items()]), unsafe_allow_html=True)
            st.markdown(f"<h3 style='color:{"#00ff88" if is_buy else "#ff4b4b"}'>{ai['w']}</h3>", unsafe_allow_html=True)
            st.write(f"CENA: {d['price']:.2f} | B: {d['bid']:.2f} A: {d['ask']:.2f}")
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=180, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")
            st.markdown(f'<div class="ai-reason">💡 {ai["u"]}</div>', unsafe_allow_html=True)
        with c3:
            price_pln = d['ask'] * usd_pln_rate
            budget_pln = st.session_state.risk_cap_pln * (risk_pct / 100)
            qty = int(budget_pln / price_pln) if price_pln > 0 else 0
            
            st.markdown(f"**DO KUPNA:**")
            st.markdown(f"<h2 style='color:#00ff88'>{qty} szt.</h2>", unsafe_allow_html=True)
            total_cost = qty * price_pln
            st.write(f"Koszt: {total_cost:.2f} PLN")
            
            if st.button(f"ZATWIERDŹ KUPNO", key=f"buy_{d['symbol']}"):
                st.session_state.risk_cap_pln -= total_cost
                save_capital(st.session_state.risk_cap_pln)
                st.success("Odjęto z portfela!")
                st.rerun()
                
            st.markdown(f"TP: <span style='color:#00ff88'>{ai['tp']}</span> | SL: <span style='color:#ff4b4b'>{ai['sl']}</span>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
