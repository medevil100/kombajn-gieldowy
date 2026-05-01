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
CAP_FILE = "kapital.txt"

def load_cap():
    if os.path.exists(CAP_FILE):
        with open(CAP_FILE, "r") as f: return float(f.read())
    return 40000.0

def save_cap(val):
    with open(CAP_FILE, "w") as f: f.write(str(val))

if "risk_cap_pln" not in st.session_state: st.session_state.risk_cap_pln = load_cap()
if "ai_memo" not in st.session_state: st.session_state.ai_memo = {} # Pamięć analiz, by nie zniknęły przy odświeżaniu cen

# Odświeżanie cen rynkowych co 60s (BEZ AI)
st_autorefresh(interval=60 * 1000, key="price_refresh")

# --- 2. STYLE NEONOWE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; min-height: 100px; }
    .ai-full-box { background: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; padding: 15px; margin-top: 10px; border-radius: 5px; font-size: 0.85rem; color: #accaff; }
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
        bid, ask = info.get('bid') or p*0.9998, info.get('ask') or p*1.0002
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        sma20, sma50, sma200 = df['Close'].rolling(20).mean().iloc[-1], df['Close'].rolling(50).mean().iloc[-1], df['Close'].rolling(200).mean().iloc[-1]
        trends = {"K": "UP" if p > sma20 else "DN", "S": "UP" if p > sma50 else "DN", "D": "UP" if p > (sma200 if not pd.isna(sma200) else sma50) else "DN"}
        return {"symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, "rsi": rsi, "trends": trends, "df": df.tail(45)}
    except: return None

def get_ai_analysis(d, key):
    try:
        client = OpenAI(api_key=key)
        prompt = (f"Jako polski ekspert giełdowy przeanalizuj {d['symbol']} cena {d['price']}. RSI:{d['rsi']:.1f}, Trendy:{d['trends']}. "
                  f"Odpowiedz wyłącznie po POLSKU. Zastosuj żołnierski styl. "
                  f"Zwróć JSON: {{\"w\": \"KUP/CZEKAJ\", \"sl\": {round(d['price']*0.94, 2)}, \"tp\": {round(d['price']*1.12, 2)}, \"u\": \"3 punkty analizy po polsku\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        return json.loads(resp.choices.message.content)
    except: return {"w": "BŁĄD", "u": "Nie udało się pobrać analizy."}

# --- 4. PANEL ---
usd_pln_rate = get_usdpln()
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap_pln = st.number_input("💵 Kapitał (PLN):", value=st.session_state.risk_cap_pln)
    save_cap(st.session_state.risk_cap_pln)
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA"
    
    t_in = st.text_area("Twoje Spółki:", value=default_tickers, height=150)
    if st.button("🚀 SKANUJ I ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.ai_memo = {}
        st.rerun()

# --- 5. LOGIKA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = [get_data(s) for s in symbols if get_data(s)]

if data_list:
    st.subheader("🔥 RADAR RSI (NAJNIŻSZE)")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5); cols2 = st.columns(5); all_cols = cols + cols2
    for i, r in enumerate(sorted_top):
        with all_cols[i]:
            st.markdown(f'<div class="top-tile"><b>{r["symbol"]}</b><br>{r["price"]:.2f}<br><small>RSI: {r["rsi"]:.1f}</small></div>', unsafe_allow_html=True)

    st.divider()

    for d in data_list:
        # Sprawdzamy czy mamy już analizę w pamięci
        ai = st.session_state.ai_memo.get(d['symbol'], {"w": "CZEKAJ", "u": "Kliknij przycisk poniżej, aby pobrać analizę AI."})
        is_buy = "KUP" in str(ai.get('w','')).upper()
        
        st.markdown(f'<div class="neon-card {"neon-card-buy" if is_buy else ""}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 1.5])
        with c1:
            st.markdown(f"## {d['symbol']}")
            t_html = "".join([f'<span class="trend-tag" style="color:{"#00ff88" if v=="UP" else "#ff4b4b"}">{k}:{v}</span>' for k,v in d['trends'].items()])
            st.markdown(t_html, unsafe_allow_html=True)
            st.markdown(f"<h3 style='color:{"#00ff88" if is_buy else "#ff4b4b"}'>{ai['w']}</h3>", unsafe_allow_html=True)
            st.write(f"CENA: **{d['price']:.2f}**")
            st.markdown(f"B: <span style='color:#00ff88'>{d['bid']:.2f}</span> | A: <span style='color:#ff4b4b'>{d['ask']:.2f}</span>", unsafe_allow_html=True)
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")
            
            # --- PRZYCISK AI NA ŻĄDANIE ---
            if st.button(f"🧠 GENERUJ ANALIZĘ AI ({d['symbol']})", key=f"ai_btn_{d['symbol']}"):
                with st.spinner("Łączenie z AI..."):
                    st.session_state.ai_memo[d['symbol']] = get_ai_analysis(d, api_key)
                    st.rerun()
            
            if d['symbol'] in st.session_state.ai_memo:
                st.markdown(f'<div class="ai-full-box"><b>ANALIZA TECHNICZNA (PL):</b><br>{st.session_state.ai_memo[d["symbol"]]["u"]}</div>', unsafe_allow_html=True)
        with c3:
            price_pln = d['ask'] * usd_pln_rate
            max_qty = int(st.session_state.risk_cap_pln / price_pln) if price_pln > 0 else 0
            
            st.markdown("**WYBIERZ ILOŚĆ:**")
            buy_qty = st.slider("Sztuki", 0, max_qty, 0, key=f"sld_{d['symbol']}")
            
            total_cost = buy_qty * price_pln
            st.write(f"Koszt: {total_cost:.2f} PLN")
            
            if st.button(f"POTWIERDŹ ZAKUP", key=f"buy_{d['symbol']}"):
                if buy_qty > 0:
                    st.session_state.risk_cap_pln -= total_cost
                    save_cap(st.session_state.risk_cap_pln)
                    st.rerun()
            
            if d['symbol'] in st.session_state.ai_memo:
                res = st.session_state.ai_memo[d['symbol']]
                st.markdown(f"TP: <span style='color:#00ff88'>{res.get('tp')}</span> | SL: <span style='color:#ff4b4b'>{res.get('sl')}</span>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
