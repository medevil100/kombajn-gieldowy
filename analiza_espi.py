import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.9", page_icon="📈", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "LBW.WA, BCS.WA, PLRX, BTC-USD, NVDA"
    return "LBW.WA, BCS.WA, PLRX, BTC-USD, NVDA"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #1c2128; padding: 12px; border-radius: 10px; border: 1px solid #444c56; text-align: center; min-height: 180px; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .bid-ask-mini { font-family: monospace; font-size: 0.75rem; color: #58a6ff; margin-top: 5px; }
    .bid-ask-large { font-family: monospace; font-size: 0.9rem; color: #58a6ff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieranie danych 1h i 1d
        h1 = yf.download(symbol, period="10d", interval="1h", progress=False)
        d1 = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if h1.empty or d1.empty: return None
        
        # MultiIndex Fix
        for df in [h1, d1]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(h1['Close'].iloc[-1])
        # Symulacja Bid/Ask (spread 0.015%)
        bid, ask = price * 0.99985, price * 1.00015
        
        prev_close = float(d1['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        
        # Pivoty i Trend
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#00ff88" if price > sma200 else "#ff4b4b"
        
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        r1, s1 = (2 * pp) - lp, (2 * pp) - hp
        
        # RSI 1h
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR dla TP/SL
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp, sl = price + (atr * 1.5), price - (atr * 1.2)

        # Rekomendacja
        if rsi < 30: rec, rec_col = "KUPUJ 🔥", "#238636"
        elif rsi > 70: rec, rec_col = "SPRZEDAJ ⚠️", "#da3633"
        else: rec, rec_col = "TRZYMAJ", "#8b949e"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "change": change_pct, 
            "rsi": rsi, "rec": rec, "rec_col": rec_col, "trend": trend_label, 
            "trend_col": trend_color, "pp": pp, "r1": r1, "s1": s1,
            "tp": tp, "sl": sl, "df": h1
        }
    except: return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("🚀 ALPHA v12.9")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Auto-Refresh (s)", options=, value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. LOGIKA GŁÓWNA ---
if api_key:
    client = OpenAI(api_key=api_key)
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    data_list = [get_analysis(t) for t in tickers if get_analysis(t)]

    if data_list:
        # --- TOP 10 RANKING Z BID/ASK ---
        st.subheader("🔥 EKSTREMALNE RSI (OKAZJE)")
        sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
        top_cols = st.columns(5)
        
        for i, d in enumerate(sorted_top):
            with top_cols[i % 5]:
                st.markdown(f"""
                    <div class="top-rank-card" style="border-top: 3px solid {d['rec_col']};">
                        <div style="font-weight:bold; font-size:1rem;">{d['symbol']}</div>
                        <div style="font-size:1.1rem; color:white; margin:5px 0;">{d['price']:.2f}</div>
                        <div class="bid-ask-mini">B: {d['bid']:.2f} | A: {d['ask']:.2f}</div>
                        <div style="background:{d['rec_col']}; font-size:0.7rem; border-radius:3px; margin:8px 0; color:white; padding:2px;">{d['rec']}</div>
                        <span class="stat-label">RSI 1H: {d['rsi']:.1f}</span>
                    </div>
                """, unsafe_allow_html=True)

        st.divider()

        # --- SZCZEGÓŁY INSTRUMENTÓW ---
        for d in data_list:
            st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 1.5, 1])
            
            with c1:
                st.markdown(f"### {d['symbol']}")
                st.markdown(f"<div class='bid-ask-large'>BID: {d['bid']:.4f} <br> ASK: {d['ask']:.4f}</div>", unsafe_allow_html=True)
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**TP:** {d['tp']:.2f} | **SL:** {d['sl']:.2f}")
                with st.expander("Pivot Points (H1)"):
                    st.write(f"R1 (Opór): {d['r1']:.2f}")
                    st.write(f"**Pivot Point: {d['pp']:.2f}**")
                    st.write(f"S1 (Wsparcie): {d['s1']:.2f}")
            
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.add_hline(y=d['pp'], line_dash="dash", line_color="orange", annotation_text="P")
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

            with c3:
                st.write("**🧠 ANALIZA AI**")
                if st.button(f"Skanuj GPT {d['symbol']}", key=f"btn_{d['symbol']}"):
                    prompt = f"Trader: Oceń {d['symbol']}. Cena: {d['price']}, RSI 1h: {d['rsi']:.1f}, Pivot: {d['pp']:.2f}. Trend: {d['trend']}. Werdykt i ryzyko."
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.session_state[f"ai_{d['symbol']}"] = resp.choices[0].message.content
                
                if f"ai_{d['symbol']}" in st.session_state:
                    st.info(st.session_state[f"ai_{d['symbol']}"])
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj OpenAI Key w sidebarze.")
