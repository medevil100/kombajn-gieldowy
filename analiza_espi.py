import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. PAMIĘĆ ---
DB_FILE = "moje_spolki.txt"
def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read()
    return "PKO.WA, BTC-USD, NVDA"

# --- 2. SETUP ---
st.set_page_config(page_title="AI Alpha Kombajn v20", page_icon="🧠", layout="wide")
st.markdown("<style>.stApp { background-color: #020202; color: #ffffff; }</style>", unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_data(symbol):
    try:
        # Pobieramy dane z filtrem MultiIndex (naprawa czarnego ekranu)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        if d15.empty or d1d.empty: return None
        
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        bid, ask = price * 0.9999, price * 1.0001
        
        # Wskaźniki
        delta = d15['Close'].diff()
        rsi = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        prev = d1d.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "pivot": pivot, "tp": price + (atr * 1.5), "sl": price - (atr * 1.0), "df": d15
        }
    except: return None

# --- 4. UI ---
with st.sidebar:
    st.header("⚙️ USTAWIENIA")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    t_input = st.text_area("Lista Spółek", value=load_tickers())
    if st.button("ZAPISZ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsc")

# --- 5. WYŚWIETLANIE ---
if api_key:
    client = OpenAI(api_key=api_key)
    tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
    
    for t in tickers:
        data = get_data(t)
        if not data: continue
        
        st.markdown(f"### {t} | RSI: {data['rsi']:.1f}")
        c1, c2 = st.columns([1.5, 2.5])
        
        with c1:
            st.metric("CENA", f"{data['price']:.4f}")
            st.write(f"**B/A:** {data['bid']:.4f} / {data['ask']:.4f}")
            st.write(f"**TP:** {data['tp']:.4f} | **SL:** {data['sl']:.4f}")
            
            if st.button(f"🧠 ANALIZA AI {t}", key=f"ai_{t}"):
                # NAPRAWIONE WYWOŁANIE:
                res = client.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=[{"role": "user", "content": f"Analiza {t}, cena {data['price']}, rsi {data['rsi']:.1f}. Werdykt?"}]
                )
                # KLUCZOWA POPRAWKA - DODANO [0]
                st.session_state[f"v_{t}"] = res.choices[0].message.content

            if f"v_{t}" in st.session_state:
                st.info(st.session_state[f"v_{t}"])

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-50:], open=data['df']['Open'][-50:], high=data['df']['High'][-50:], low=data['df']['Low'][-50:], close=data['df']['Close'][-50:])])
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{t}")
        st.divider()
else:
    st.info("Wprowadź API Key OpenAI.")
