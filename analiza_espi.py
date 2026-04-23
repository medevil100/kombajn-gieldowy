import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA I PAMIĘĆ ---
DB_FILE = "tickers_db.txt"
if 'ai_cache' not in st.session_state: st.session_state.ai_cache = {}

def save_tickers(text):
    with open(DB_FILE, "w") as f: f.write(text)

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read()
    return "PKO.WA, BTC-USD, NVDA, TSLA, AAPL, ETH-USD"

st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v10", page_icon="🚀", layout="wide")

# --- 2. STYLE PRO ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #ffffff; }
    .ticker-card { background: #0d1117; padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px; transition: 0.3s; }
    .buy-signal { border: 2px solid #00ff88 !important; box-shadow: 0 0 20px rgba(0, 255, 136, 0.2); }
    .top-rank-card { background: #161b22; padding: 10px; border-radius: 8px; border: 1px solid #30363d; text-align: center; }
    .price-tag { font-size: 1.4rem; font-weight: bold; color: #58a6ff; }
    .verdict-badge { padding: 4px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALITYCZNY ---
def get_analysis(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        if d15.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        close = d15['Close']
        price = float(close.iloc[-1])
        
        # Wskaźniki
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_bb, lower_bb = sma20 + (std20 * 2), sma20 - (std20 * 2)
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Szybka Rekomendacja (Logic)
        rec = "CZEKAJ"
        rec_color = "#8b949e"
        if rsi < 32 or price < lower_bb.iloc[-1]: 
            rec = "KUPUJ"
            rec_color = "#238636"
        elif rsi > 68 or price > upper_bb.iloc[-1]: 
            rec = "SPRZEDAJ"
            rec_color = "#da3633"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "rec": rec, "rec_color": rec_color,
            "df": d15, "lbb": lower_bb, "ubb": upper_bb, "vol_spike": d15['Volume'].iloc[-1] > d15['Volume'].rolling(20).mean().iloc[-1] * 2
        }
    except: return None

# --- 4. INTERFEJS ---
with st.sidebar:
    st.title("⚡ KOBMAJN v10")
    api_key = st.text_input("OpenAI Key", type="password")
    tickers_raw = st.text_area("Lista (po przecinku)", value=load_tickers())
    if st.button("Zapisz listę"): save_tickers(tickers_raw)
    refresh = st.select_slider("Odświeżanie", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="auto")
tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]

if api_key:
    client = OpenAI(api_key=api_key)
    data_list = [get_analysis(t) for t in tickers if get_analysis(t)]

    # --- TOP 10 RANKING ---
    st.subheader("🏆 TOP 10: OKAZJE I MONITORING")
    cols = st.columns(5)
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    
    for i, d in enumerate(sorted_top):
        with cols[i % 5]:
            st.markdown(f"""
                <div class="top-rank-card">
                    <div style="font-weight:bold;">{d['symbol']}</div>
                    <div class="price-tag">{d['price']:.2f}</div>
                    <div style="font-size:0.8rem; color:#8b949e;">RSI: {d['rsi']:.1f}</div>
                    <div class="verdict-badge" style="background:{d['rec_color']};">{d['rec']}</div>
                </div>
            """, unsafe_allow_html=True)
            st.write("")

    # --- SZCZEGÓŁY ---
    for d in data_list:
        is_buy = d['rec'] == "KUPUJ"
        st.markdown(f'<div class="ticker-card {"buy-signal" if is_buy else ""}">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown(f"## {d['symbol']} <span style='font-size:1rem; color:{d['rec_color']}'>{d['rec']}</span>", unsafe_allow_html=True)
            st.metric("Cena", f"{d['price']:.4f}", f"{d['rsi']:.1f} RSI")
            
            if st.button(f"🧠 ANALIZA AI: {d['symbol']}", key=f"btn_{d['symbol']}"):
                prompt = f"Analiza {d['symbol']}. Cena: {d['price']}, RSI: {d['rsi']:.2f}, Akcja techniczna: {d['rec']}. Czy to dobry moment na wejście? Podaj ryzyko w skali 1-10."
                response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"ai_{d['symbol']}"] = response.choices[0].message.content
            
            if f"ai_{d['symbol']}" in st.session_state:
                st.info(st.session_state[f"ai_{d['symbol']}"])

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-50:], open=d['df']['Open'][-50:], high=d['df']['High'][-50:], low=d['df']['Low'][-50:], close=d['df']['Close'][-50:])])
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Podaj API Key, aby uruchomić silnik AI.")
