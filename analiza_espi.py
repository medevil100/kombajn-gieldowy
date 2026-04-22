import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. PAMIĘĆ ---
DB_FILE = "moje.txt" 
if 'ai_cache' not in st.session_state: st.session_state.ai_cache = {}

def save_tickers(text):
    try:
        with open(DB_FILE, "w") as f: f.write(text)
    except: pass

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, IOVA"
    return "PKO.WA, BTC-USD, NVDA, IOVA"

# --- 2. STYLE PRO ---
st.set_page_config(page_title="AI Alpha Terminal v9.3 GOLD", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; }
    .ticker-card { background: #0a0b10; padding: 20px; border-radius: 15px; border: 1px solid #1a1c23; margin-bottom: 25px; }
    .buy-signal { border: 2px solid #00ff88 !important; animation: blink 2s infinite; }
    @keyframes blink { 0% { box-shadow: 0 0 5px #00ff88; } 50% { box-shadow: 0 0 20px #00ff88; } 100% { box-shadow: 0 0 5px #00ff88; } }
    .verdict-box { background: #07121d; padding: 15px; border-radius: 10px; border-left: 5px solid #00e5ff; margin-top: 10px; }
    .top-bar { background: linear-gradient(90deg, #07121d, #0a0b10); padding: 15px; border-radius: 10px; border: 1px solid #333; margin-bottom: 20px; }
    .price-text { font-size: 2.2rem; font-weight: 800; color: #ffffff; margin: 0; }
    .tf-badge { background: #1a1a1a; padding: 5px 10px; border-radius: 6px; font-size: 0.8rem; color: #00e5ff; border: 1px solid #333; margin-right: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. DANE ---
def play_sound():
    st.components.v1.html('<audio autoplay><source src="https://mixkit.co" type="audio/mpeg"></audio>', height=0)

def get_data(symbol):
    try:
        d15 = yf.download(symbol, period="3d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        if d15.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        sma20 = d15['Close'].rolling(20).mean()
        std20 = d15['Close'].rolling(20).std()
        upper_bb, lower_bb = sma20 + (std20 * 2), sma20 - (std20 * 2)
        avg_vol = d15['Volume'].rolling(30).mean().iloc[-1]
        vol_spike = d15['Volume'].iloc[-1] > (avg_vol * 1.8)
        
        delta = d15['Close'].diff()
        gain, loss = delta.where(delta > 0, 0).rolling(14).mean(), delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        if pd.isna(rsi): rsi = 50.0

        sma_d = d1d['Close'].rolling(100).mean().iloc[-1]
        pivot = (d1d['High'].iloc[-2] + d1d['Low'].iloc[-2] + d1d['Close'].iloc[-2]) / 3
        atr = (d1d['High'] - d1d['Low']).rolling(20).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "pivot": pivot,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.0),
            "trend": "BULL 🐂" if price > sma_d else "BEAR 🐻",
            "vol_spike": vol_spike, "df": d15, "lbb": lower_bb.iloc[-1],
            "lower_bb": lower_bb, "upper_bb": upper_bb
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ TERMINAL")
    api_key = st.text_input("OpenAI API Key:", type="password")
    saved_list = load_tickers()
    tickers_input = st.text_area("Lista Spółek:", value=saved_list, height=150)
    if tickers_input != saved_list: save_tickers(tickers_input)
    tickers = [x.strip().upper() for x in tickers_input.split(",") if x.strip()]
    refresh_val = st.select_slider("Odświeżanie (sek)", options=[30, 60, 300, 600], value=60)

st_autorefresh(interval=refresh_val * 1000, key="fscounter")

# --- 5. MAIN ---
if api_key:
    client = OpenAI(api_key=api_key)
    
    # --- RANKING NA GÓRZE ---
    st.markdown('<div class="top-bar"><h4>🏆 REKOMENDACJE AI (TOP)</h4>', unsafe_allow_html=True)
    top_cols = st.columns(6)
    count = 0
    for t in tickers:
        if f"v_{t}" in st.session_state and "KUPUJ" in st.session_state[f"v_{t}"]:
            if count < 6:
                with top_cols[count]:
                    st.success(f"🔥 {t}")
                    st.caption("Status: KUPUJ")
                count += 1
    if count == 0: st.info("Brak aktywnych sygnałów KUPUJ. Wygeneruj werdykty poniżej.")
    st.markdown('</div>', unsafe_allow_html=True)

    # --- LISTA SPÓŁEK ---
    for t in tickers:
        data = get_data(t)
        if not data: continue
        
        is_buy_zone = data['rsi'] < 32 or data['price'] < data['lbb']
        if is_buy_zone: play_sound()

        st.markdown(f'<div class="ticker-card {"buy-signal" if is_buy_zone else ""}">', unsafe_allow_html=True)
        c1, c2 = st.columns([1.5, 2.5])
        
        with c1:
            st.subheader(t)
            st.markdown(f"<p class='price-text'>{data['price']:.4f}</p>", unsafe_allow_html=True)
            if data['vol_spike']: st.markdown('<span style="color:#ff00ff; font-weight:bold;">🔥 WOLUMEN!</span>', unsafe_allow_html=True)
            st.markdown(f"<span class='tf-badge'>{data['trend']}</span><span class='tf-badge'>RSI: {data['rsi']:.1f}</span>", unsafe_allow_html=True)
            
            st.markdown(f"""<div style="background:#12141d; padding:12px; border-radius:8px; margin:15px 0; border:1px solid #333;">
                <b style="color:#00ff88; font-size:1.1rem;">🎯 TP: {data['tp']:.3f}</b> | <b style="color:#ff4b4b; font-size:1.1rem;">🛑 SL: {data['sl']:.3f}</b><br>
                <span style='color:#888; font-size:0.8rem;'>Pivot: {data['pivot']:.3f} | BB Dół: {data['lbb']:.3f}</span>
            </div>""", unsafe_allow_html=True)

            if st.button(f"🧠 DECYZJA {t}", key=f"ai_{t}"):
                p = f"Analiza {t}: Cena {data['price']}, RSI {data['rsi']:.1f}, Trend {data['trend']}. WYSTAW OCENĘ 1-10 i WERDYKT: KUPUJ/CZEKAJ/SPRZEDAJ. Konkretnie, 1 zdanie."
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": p}])
                st.session_state[f"v_{t}"] = res.choices.message.content
                st.rerun()

            if f"v_{t}" in st.session_state:
                st.markdown(f'<div class="verdict-box">{st.session_state[f"v_{t}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-60:], open=data['df']['Open'][-60:], high=data['df']['High'][-60:], low=data['df']['Low'][-60:], close=data['df']['Close'][-60:])])
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['upper_bb'][-60:], line=dict(color='rgba(0, 229, 255, 0.2)', width=1), name="BB Góra"))
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['lower_bb'][-60:], line=dict(color='rgba(0, 229, 255, 0.2)', width=1), fill='tonexty'))
            fig.add_hline(y=data['pivot'], line_dash="dot", line_color="white")
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{t}", config={'displayModeBar': False})
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Wprowadź API Key OpenAI.")
