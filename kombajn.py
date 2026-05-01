import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os

# --- 1. KONFIGURACJA I TRWAŁOŚĆ ---
st.set_page_config(page_title="NEON COMMANDER v102", page_icon="⚡", layout="wide")

DB_FILE = "moje_spolki.txt"
CAPITAL_FILE = "kapital.txt"

def load_cap():
    if os.path.exists(CAPITAL_FILE):
        try:
            with open(CAPITAL_FILE, "r") as f: return float(f.read())
        except: return 40000.0
    return 40000.0

def save_cap(val):
    with open(CAPITAL_FILE, "w") as f: f.write(str(val))

if "risk_cap_pln" not in st.session_state: st.session_state.risk_cap_pln = load_cap()
if "full_analysis" not in st.session_state: st.session_state.full_analysis = {}

# AUTO-ODŚWIEŻANIE (60 sekund dla Bid/Ask i Kursu USD)
st_autorefresh(interval=60 * 1000, key="global_refresh")

# --- 2. STYLE NEONOWE (ZGODNE Z PIERWOTNĄ WERSJĄ) ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; min-height: 100px; }
    .tp-box { color: #00ff88; font-weight: bold; }
    .sl-box { color: #ff4b4b; font-weight: bold; }
    .ai-full-box { background: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; padding: 15px; margin-top: 10px; border-radius: 5px; font-size: 0.9rem; color: #accaff; }
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
        bid = info.get('bid') or p * 0.9998
        ask = info.get('ask') or p * 1.0002
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        sma20, sma50, sma200 = df['Close'].rolling(20).mean().iloc[-1], df['Close'].rolling(50).mean().iloc[-1], df['Close'].rolling(200).mean().iloc[-1]
        trends = {"K": "UP" if p > sma20 else "DN", "S": "UP" if p > sma50 else "DN", "D": "UP" if p > (sma200 if not pd.isna(sma200) else sma50) else "DN"}
        return {"symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, "rsi": rsi, "trends": trends, "df": df.tail(45)}
    except: return None

def run_ai_logic(d, key):
    """Surowa analiza AI - decyduje czy kupić, czy czekać"""
    try:
        client = OpenAI(api_key=key)
        # Zaostrzony prompt - AI ma być krytyczne
        prompt = (f"Jesteś surowym analitykiem. Spółka {d['symbol']} cena {d['price']}. RSI:{d['rsi']:.1f}, Trendy:{d['trends']}. "
                  f"Zarekomenduj KUP tylko jeśli RSI < 35 lub trend jest silny UP. W innym przypadku CZEKAJ. "
                  f"Zwróć JSON: {{\"w\": \"KUP\"/\"CZEKAJ\"/\"SPRZEDAJ\", \"sl\": {round(d['price']*0.94, 2)}, \"tp\": {round(d['price']*1.15, 2)}, "
                  f"\"u\": \"Krótki techniczny powód (max 10 słów)\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        return json.loads(resp.choices[0].message.content)
    except: return {"w": "CZEKAJ", "sl": 0, "tp": 0, "u": "Błąd połączenia z AI"}

# --- 4. PANEL BOCZNY ---
usd_pln_rate = get_usdpln()
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    current_cap = st.number_input("💵 Portfel (PLN):", value=st.session_state.risk_cap_pln)
    if current_cap != st.session_state.risk_cap_pln:
        st.session_state.risk_cap_pln = current_cap
        save_cap(current_cap)

    risk_pct = st.slider("🎯 Ryzyko na spółkę (%)", 1, 100, 10)
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA, AAPL, BTC-USD"
    
    t_in = st.text_area("Twoje Spółki:", value=default_tickers, height=150)
    if st.button("🚀 SKANUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.full_analysis = {}
        st.rerun()

# --- 5. LOGIKA GŁÓWNA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = [get_data(s) for s in symbols if get_data(s)]

if data_list:
    # --- RADAR TOP 10 (TAK JAK BYŁO) ---
    st.subheader("🔥 TOP 10 RADAR (NAJNIŻSZE RSI)")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5); cols2 = st.columns(5); all_cols = cols + cols2
    for i, r in enumerate(sorted_top):
        with all_cols[i]:
            st.markdown(f'<div class="top-tile"><b>{r["symbol"]}</b><br><span style="color:#58a6ff">{r["price"]:.2f}</span><br><small>RSI: {r["rsi"]:.1f}</small></div>', unsafe_allow_html=True)

    st.divider()

    # --- LISTA GŁÓWNA ---
    for d in data_list:
        # Pobranie analizy AI (Werdykt + Uzasadnienie)
        ai = run_ai_logic(d, api_key) if api_key else {"w": "BRAK KLUCZA", "u": "Wpisz klucz API w sidebare."}
        is_buy = "KUP" in str(ai['w']).upper()
        
        st.markdown(f'<div class="neon-card {"neon-card-buy" if is_buy else ""}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 1.5])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            # Trendy K S D
            t_html = "".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span>' for k,v in d['trends'].items()])
            st.markdown(t_html, unsafe_allow_html=True)
            st.markdown(f"<h3 style='color:{"#00ff88" if is_buy else "#ff4b4b"}'>{ai['w']}</h3>", unsafe_allow_html=True)
            st.write(f"CENA: **{d['price']:.2f}**")
            st.markdown(f"B: <span style='color:#00ff88'>{d['bid']:.2f}</span> | A: <span style='color:#ff4b4b'>{d['ask']:.2f}</span>", unsafe_allow_html=True)
            st.write(f"RSI: **{d['rsi']:.1f}**")
            
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")
            
            # ANALIZA AI ROZBUDOWANA (Uzasadnienie techniczne)
            st.markdown(f'<div class="ai-full-box"><b>ANALIZA TECHNICZNA:</b><br>{ai.get("u", "Brak danych.")}</div>', unsafe_allow_html=True)
                
        with c3:
            # KALKULACJA ILOŚCI I KAPITAŁU
            price_pln = d['ask'] * usd_pln_rate
            budget_pln = st.session_state.risk_cap_pln * (risk_pct / 100)
            qty = int(budget_pln / price_pln) if price_pln > 0 else 0
            
            st.markdown(f"**SUGESTIA:**")
            st.markdown(f"<h2 style='color:#00ff88'>{qty} szt.</h2>", unsafe_allow_html=True)
            cost_now = qty * price_pln
            
            if st.button(f"POTWIERDŹ KUPNO", key=f"buy_{d['symbol']}"):
                st.session_state.risk_cap_pln -= cost_now
                save_cap(st.session_state.risk_cap_pln)
                st.success(f"Zakupiono! Pozostało: {st.session_state.risk_cap_pln:.2f} PLN")
                st.rerun()
                
            st.write(f"Koszt: {cost_now:.2f} PLN")
            st.markdown(f"TP: <span class='tp-box'>{ai.get('tp', 0)}</span>", unsafe_allow_html=True)
            st.markdown(f"SL: <span class='sl-box'>{ai.get('sl', 0)}</span>", unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
