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
st.set_page_config(page_title="AI Alpha Terminal v9.6 ELITE", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; }
    .ticker-card { background: #0a0b10; padding: 25px; border-radius: 15px; border: 1px solid #1a1c23; margin-bottom: 25px; }
    .buy-signal { border: 2px solid #00ff88 !important; box-shadow: 0 0 25px rgba(0, 255, 136, 0.3); }
    .verdict-box { background: #07121d; padding: 15px; border-radius: 10px; border-left: 5px solid #00e5ff; margin-top: 10px; font-size: 1.1rem; color: #00e5ff; font-weight: bold; }
    .price-text { font-size: 3.2rem; font-weight: 900; color: #ffffff; margin: 0; line-height: 1; }
    .label-desc { color: #888; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .top-rank-box { background: linear-gradient(135deg, #07121d 0%, #0a0b10 100%); padding: 15px; border-radius: 12px; border: 1px solid #00ff88; margin-bottom: 30px; }
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
        if pd.isna(atr) or atr == 0: atr = price * 0.03
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "pivot": pivot,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.0),
            "trend": "HOSSA 🐂" if price > sma_d else "BESSA 🐻",
            "vol_spike": vol_spike, "df": d15, "lbb": lower_bb.iloc[-1], "ubb": upper_bb.iloc[-1],
            "lower_bb": lower_bb, "upper_bb": upper_bb
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.header("⚙️ TERMINAL")
    api_key = st.text_input("OpenAI API Key:", type="password")
    saved_list = load_tickers()
    tickers_input = st.text_area("Lista Spółek:", value=saved_list, height=150)
    if tickers_input != saved_list: save_tickers(tickers_input)
    tickers = [x.strip().upper() for x in tickers_input.split(",") if x.strip()]
    refresh_val = st.select_slider("Odświeżanie (sek)", options=, value=60)

st_autorefresh(interval=refresh_val * 1000, key="fscounter")

# --- 5. WYŚWIETLANIE ---
if api_key:
    client = OpenAI(api_key=api_key)
    
    # --- POBIERANIE WSZYSTKICH DANYCH DLA RANKINGU ---
    all_stocks = []
    for t in tickers:
        d = get_data(t)
        if d: all_stocks.append(d)
    
    # --- TOP 10 SYGNAŁÓW NA GÓRZE ---
    if all_stocks:
        st.markdown('<div class="top-rank-box"><h4>🏆 TOP 10: NAJWIĘKSZE WYPRZEDANIE / WOLUMEN</h4>', unsafe_allow_html=True)
        # Sortujemy po najniższym RSI
        sorted_stocks = sorted(all_stocks, key=lambda x: x['rsi'])[:10]
        
        cols = st.columns(5) # 2 rzędy po 5
        for i, stock in enumerate(sorted_stocks):
            with cols[i % 5]:
                color = "#00ff88" if stock['rsi'] < 35 else "#ffffff"
                st.markdown(f"**{stock['symbol']}**")
                st.markdown(f"<span style='color:{color};'>RSI: {stock['rsi']:.1f}</span>", unsafe_allow_html=True)
                if stock['vol_spike']: st.caption("🔥 VOL SPIKE")
        st.markdown('</div>', unsafe_allow_html=True)

    # --- KARTY SZCZEGÓŁOWE ---
    for data in all_stocks:
        t = data['symbol']
        is_buy_zone = data['rsi'] < 32 or data['price'] < data['lbb']
        if is_buy_zone: play_sound()

        st.markdown(f'<div class="ticker-card {"buy-signal" if is_buy_zone else ""}">', unsafe_allow_html=True)
        c1, c2 = st.columns([1.6, 2.4])
        
        with c1:
            st.subheader(t)
            st.markdown(f'<div class="label-desc">Aktualna Cena</div>', unsafe_allow_html=True)
            st.markdown(f"<p class='price-text'>{data['price']:.4f}</p>", unsafe_allow_html=True)
            
            if data['vol_spike']: st.markdown('<p style="color:#ff00ff; font-weight:bold; margin:10px 0;">🔥 SKOK WOLUMENU (Aktywność!)</p>', unsafe_allow_html=True)
            
            st.markdown(f"""
                <div style="background:#12141d; padding:20px; border-radius:10px; margin:20px 0; border:1px solid #333;">
                    <b style="color:#00ff88; font-size:1.4rem;">🎯 CEL (TP): {data['tp']:.4f}</b><br>
                    <b style="color:#ff4b4b; font-size:1.4rem;">🛑 STOP (SL): {data['sl']:.4f}</b><br>
                    <hr style='margin:15px 0; border-color:#333;'>
                    <span class='label-desc'>Trend: {data['trend']} | RSI: {data['rsi']:.1f}</span>
                </div>
            """, unsafe_allow_html=True)

            if st.button(f"🧠 DECYZJA AI DLA {t}", key=f"ai_{t}"):
                p = f"Analiza {t}: Cena {data['price']}, RSI {data['rsi']:.1f}, Trend {data['trend']}. WYDAJ WERDYKT: KUPUJ, CZEKAJ lub SPRZEDAJ. Konkretna ocena 1-10 i dlaczego."
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": p}])
                st.session_state[f"v_{t}"] = res.choices.message.content
                st.rerun()

            if f"v_{t}" in st.session_state:
                st.markdown(f'<div class="verdict-box">{st.session_state[f"v_{t}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-60:], open=data['df']['Open'][-60:], high=data['df']['High'][-60:], low=data['df']['Low'][-60:], close=data['df']['Close'][-60:])])
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['upper_bb'][-60:], line=dict(color='rgba(0, 229, 255, 0.4)', width=1.5), name="BB Góra"))
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['lower_bb'][-60:], line=dict(color='rgba(0, 229, 255, 0.4)', width=1.5), fill='tonexty'))
            fig.add_hline(y=data['pivot'], line_dash="dot", line_color="white", line_width=2)
            fig.add_hline(y=data['tp'], line_dash="dash", line_color="#00ff88", line_width=2)
            fig.add_hline(y=data['sl'], line_dash="dash", line_color="#ff4b4b", line_width=2)
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{t}", config={'displayModeBar': False})
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Wprowadź API Key OpenAI.")
