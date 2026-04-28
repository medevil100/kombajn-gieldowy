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
if "risk_cap" not in st.session_state: st.session_state.risk_cap = 10000.0

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
</style>
""", unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        p = float(df['Close'].iloc[-1])
        h, l = float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
        pp = (df['High'].iloc[-2] + df['Low'].iloc[-2] + df['Close'].iloc[-2]) / 3
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        return {"symbol": symbol.upper(), "price": p, "rsi": rsi, "pp": pp, "high": h, "low": l, "change": ((p - df['Close'].iloc[-2])/df['Close'].iloc[-2]*100), "df": df.tail(45)}
    except: return None

def run_ai_short(d, key):
    """Szybki werdykt do kafelków i startu"""
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = f"Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, Pivot:{d['pp']:.2f}. Zwróć JSON: {{\"w\": \"KUP/SPRZEDAJ/TRZYMAJ\", \"sl\": cena, \"tp\": cena}}"
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

def run_ai_full(d, key):
    """Pełna analiza na żądanie bez lania wody"""
    try:
        client = OpenAI(api_key=key)
        prompt = (f"Jako ekspert techniczny przeanalizuj {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, Pivot:{d['pp']:.2f}, High:{d['high']}, Low:{d['low']}. "
                  f"Podaj w 3-4 krótkich żołnierskich punktach: trend, kluczowe wsparcie/opór i konkretny powód wejścia/wyjścia. Żadnego lania wody.")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        res = resp.choices[0].message.content
        st.session_state.full_analysis[d['symbol']] = res
        return res
    except: return "Błąd analizy."

# --- 4. PANEL STEROWANIA ---
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap = st.number_input("💵 Kapitał:", value=st.session_state.risk_cap)
    
    # SUWAK ODŚWIEŻANIA
    refresh_min = st.slider("⏱️ Odświeżanie (minuty)", 1, 10, 2)
    st_autorefresh(interval=refresh_min * 60 * 1000, key="auto_ref")

    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA, BTC-USD"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers, height=150)
    if st.button("🚀 SKANUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.ai_results = {}; st.session_state.full_analysis = {}
        st.rerun()

# --- 5. LOGIKA GŁÓWNA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = []
with st.spinner("Pobieranie danych..."):
    for sym in symbols:
        res = get_data(sym)
        if res:
            if api_key: res['ai'] = run_ai_short(res, api_key)
            data_list.append(res)

if data_list:
    # TOP 10 RADAR
    st.subheader("🔥 TOP 10 RADAR")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5)
    cols2 = st.columns(5)
    all_cols = cols + cols2
    
    for i, r in enumerate(sorted_top):
        with all_cols[i]:
            ai_v = r.get('ai', {}).get('w', '---').upper()
            v_col = "#00ff88" if "KUP" in ai_v else "#ff4b4b" if "SPRZEDAJ" in ai_v else "#58a6ff"
            st.markdown(f"""
                <div class="top-tile" style="border-bottom: 4px solid {v_col};">
                    <b>{r['symbol']}</b> | <span style="color:{v_col}">{r['price']:.2f}</span><br>
                    <span style="color:{v_col}; font-weight:bold;">{ai_v}</span><br>
                    <small>RSI: {r['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # LISTA GŁÓWNA
    for d in data_list:
        ai = d.get('ai')
        card_border = "neon-card-buy" if ai and "KUP" in ai['w'].upper() else ""
        
        st.markdown(f'<div class="neon-card {card_border}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 1.5])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            if ai:
                v_class = "status-buy" if "KUP" in ai['w'].upper() else "status-sell" if "SPRZEDAJ" in ai['w'].upper() else ""
                st.markdown(f'<span class="{v_class}" style="font-size:1.2rem;">{ai["w"]}</span>', unsafe_allow_html=True)
            
            st.markdown(f"CENA: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.write(f"H: {d['high']:.2f} | L: {d['low']:.2f} | PP: {d['pp']:.2f}")
            st.write(f"RSI: **{d['rsi']:.1f}**")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dash", line_color="#58a6ff", opacity=0.5)
            fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f"<span class='tp-box'>TP: {ai['tp']}</span><br><span class='sl-box'>SL: {ai['sl']}</span>", unsafe_allow_html=True)
                
                # Kalkulator
                diff = abs(d['price'] - float(ai['sl']))
                shares = int((st.session_state.risk_cap * 0.02) / diff) if diff > 0 else 0
                st.success(f"KUP: {shares} szt.")

                # PRZYCISK PEŁNEJ ANALIZY
                if st.button("🧠 PEŁNA ANALIZA", key=f"full_{d['symbol']}"):
                    run_ai_full(d, api_key)
                
                if d['symbol'] in st.session_state.full_analysis:
                    st.markdown(f'<div class="ai-full-box">{st.session_state.full_analysis[d["symbol"]]}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj symbole w panelu bocznym.")
