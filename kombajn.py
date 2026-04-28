import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os
from datetime import datetime

# --- 1. KONFIGURACJA I STYLE ---
st.set_page_config(page_title="NEON COMMANDER v101", page_icon="⚡", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "risk_cap" not in st.session_state: st.session_state.risk_cap = 10000.0

DB_FILE = "moje_spolki.txt"

st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 25px; border-radius: 15px; margin-bottom: 20px; transition: 0.3s; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .neon-card-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 15px; text-align: center; border-bottom: 4px solid #58a6ff; min-height: 120px; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; font-size: 1.2rem; }
    .status-sell { color: #ff4b4b; text-shadow: 0 0 10px #ff4b4b; font-weight: bold; font-size: 1.2rem; }
    .status-hold { color: #58a6ff; font-weight: bold; }
    .tp-box { border: 1px solid #00ff88; padding: 10px; border-radius: 8px; color: #00ff88; text-align: center; font-weight: bold; margin-bottom: 10px; }
    .sl-box { border: 1px solid #ff4b4b; padding: 10px; border-radius: 8px; color: #ff4b4b; text-align: center; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. SILNIK DANYCH ---
def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        p = float(df['Close'].iloc[-1])
        h_day, l_day = float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
        h_prev, l_prev, c_prev = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        
        pp = (h_prev + l_prev + c_prev) / 3
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        
        return {
            "symbol": symbol.strip().upper(), "price": p, "rsi": rsi, "pp": pp, 
            "high": h_day, "low": l_day, "change": ((p - c_prev) / c_prev * 100), "df": df.tail(45)
        }
    except: return None

def run_ai(d, key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = (f"Jesteś PRO Traderem. Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}, Pivot PP:{d['pp']:.2f}, High:{d['high']}, Low:{d['low']}. "
                  f"Zwróć TYLKO JSON: {{\"w\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", \"sl\": cena, \"tp\": cena, \"u\": \"max 8 slow\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

# --- 3. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 NEON OMNI v101")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap = st.number_input("💵 Kapitał Portfela:", value=st.session_state.risk_cap)
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA, BTC-USD"
    
    t_in = st.text_area("Lista Tickerów (CSV):", value=default_tickers, height=150)
    if st.button("🚀 SKANUJ RYNEK"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()
    st_autorefresh(interval=60000, key="auto_ref")

# --- 4. DASHBOARD GŁÓWNY ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = []

if symbols:
    with st.status("🛸 SKANOWANIE...", expanded=False) as status:
        for sym in symbols:
            res = get_data(sym)
            if res:
                if api_key: res['ai'] = run_ai(res, api_key)
                data_list.append(res)
        status.update(label="SYSTEM LIVE 🟢", state="complete")

if data_list:
    # TOP 10 KAFELKI
    st.subheader("🔥 TOP 10 RADAR (Sygnały AI)")
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
                    <b>{r['symbol']}</b><br>
                    <span style="color:{v_col}; font-weight:bold;">{ai_v}</span><br>
                    <small>RSI: {r['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # LISTA GŁÓWNA
    for d in data_list:
        ai = d.get('ai')
        card_class = "neon-card"
        if ai:
            if "KUP" in ai['w'].upper(): card_class += " neon-card-buy"
            if "SPRZEDAJ" in ai['w'].upper(): card_class += " neon-card-sell"

        st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 1.5])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            if ai:
                v_class = "status-buy" if "KUP" in ai['w'].upper() else "status-sell" if "SPRZEDAJ" in ai['w'].upper() else "status-hold"
                st.markdown(f'<span class="{v_class}">{ai["w"]}</span>', unsafe_allow_html=True)
            
            st.markdown(f"""
                <div style='margin-top:15px;'>
                    <span style='color:#888;'>CENA:</span> <b style='font-size:1.4rem;'>{d['price']:.2f}</b><br>
                    <span style='color:#00ff88;'>Szczyt: {d['high']:.2f}</span> | <span style='color:#ff4b4b;'>Dołek: {d['low']:.2f}</span><br>
                    <span style='color:#58a6ff;'>Pivot PP: {d['pp']:.2f}</span><br>
                    <span style='color:#ffcc00;'>RSI: {d['rsi']:.1f}</span>
                </div>
            """, unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dash", line_color="#58a6ff", annotation_text="Pivot PP")
            fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f"""
                    <div class="tp-box"><small>TARGET PROFIT</small><br>{ai['tp']}</div>
                    <div class="sl-box"><small>STOP LOSS</small><br>{ai['sl']}</div>
                """, unsafe_allow_html=True)
                
                # Kalkulator pozycji (Ryzyko 2% portfela)
                diff = abs(d['price'] - float(ai['sl']))
                shares = int((st.session_state.risk_cap * 0.02) / diff) if diff > 0 else 0
                st.markdown(f"""
                    <div style='background:rgba(0,255,136,0.1); padding:10px; border-radius:10px; text-align:center; border:1px solid #00ff88; margin-top:10px;'>
                        <small>KUP: <b>{shares} szt.</b></small><br>
                        <small style='color:#aaa;'>{ai['u']}</small>
                    </div>
                """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("System gotowy. Dodaj symbole w panelu bocznym.")
