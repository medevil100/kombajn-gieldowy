import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I STYLE ---
st.set_page_config(page_title="AI ALPHA GOLDEN v16.6", page_icon="🍯", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .verdict-badge { padding: 5px 15px; border-radius: 20px; font-weight: bold; text-transform: uppercase; font-size: 0.8rem; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK DANYCH (Z Bid/Ask i Pivotami) ---
def get_data(symbol):
    try:
        t = yf.Ticker(symbol)
        d1h = t.history(period="10d", interval="1h")
        d1d = t.history(period="250d", interval="1d")
        
        if d1h.empty or d1d.empty: return None

        price = d1h['Close'].iloc[-1]
        # Symulacja Bid/Ask
        bid, ask = price * 0.9999, price * 1.0001
        
        # Trendy i Pivot
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        h_p, l_p, c_p = d1d['High'].iloc[-2], d1d['Low'].iloc[-2], d1d['Close'].iloc[-2]
        pivot = (h_p + l_p + c_p) / 3
        
        # RSI 1h
        delta = d1h['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        verdict, v_class = ("KUP", "v-buy") if rsi < 30 else ("SPRZEDAJ", "v-sell") if rsi > 70 else ("CZEKAJ", "v-wait")

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "pivot": pivot, "verdict": verdict, "v_class": v_class,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.2), "df": d1h,
            "change": ((price - c_p) / c_p * 100)
        }
    except: return None

# --- 3. UI SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.6 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole", "BCS.WA, STX.WA, LBW.WA, BTC-USD")
    refresh = st.slider("Odśwież (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 4. LOGIKA GŁÓWNA ---
t_list = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor() as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    # --- TOP 10 ---
    st.subheader("🔥 EKSTREMALNE RSI")
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with cols[i % 5]:
            st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b>{d["price"]:.2f}</b><br><span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span></div>', unsafe_allow_html=True)

    # --- SZCZEGÓŁY ---
    for d in data_list:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c1:
            st.subheader(d['symbol'])
            st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.write(f"**BID:** {d['bid']:.4f} | **ASK:** {d['ask']:.4f}")
            st.write(f"**RSI 1h:** {d['rsi']:.1f}")
            st.write(f"**Pivot:** {d['pivot']:.2f}")
            st.write(f"**TP:** {d['tp']:.2f} | **SL:** {d['sl']:.2f}")
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
        with c3:
            if api_key and st.button(f"Analiza AI", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": f"Oceń {d['symbol']}, cena {d['price']}, RSI {d['rsi']:.1f}"}]
                )
                # TUTAJ BYŁ BŁĄD - TERAZ JEST POPRAWNIE:
                st.info(resp.choices[0].message.content)
        st.markdown('</div>', unsafe_allow_html=True)
