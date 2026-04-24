import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA GOLDEN", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 10px; border-radius: 10px; border: 1px solid #30363d; text-align: center; margin-bottom: 5px; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px; }
    .verdict-badge { padding: 3px 8px; border-radius: 10px; font-weight: bold; font-size: 0.7rem; }
    .v-buy { background: #238636; } .v-sell { background: #da3633; } .v-wait { background: #8b949e; }
    .trend-up { color: #238636; font-size: 0.7rem; } .trend-down { color: #da3633; font-size: 0.7rem; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

def load_tickers():
    return "BTC-USD, ETH-USD, NVDA, TSLA, PKO.WA, ALE.WA, CDR.WA, AAPL, MSFT, META"

def analyze_candles(df):
    if len(df) < 3: return "Brak"
    last, prev = df.iloc[-1], df.iloc[-2]
    body = abs(last['Close'] - last['Open'])
    if (min(last['Open'], last['Close']) - last['Low']) > (2 * body) and body > 0: return "🔨 MŁOT"
    if last['Close'] > prev['Open'] and last['Open'] < prev['Close']: return "🟢 OBJĘCIE"
    return "Brak"

def get_data(symbol):
    try:
        t = yf.Ticker(symbol)
        d_long = t.history(period="1y", interval="1d")
        d15 = t.history(period="5d", interval="15m")
        if d15.empty: return None
        
        price = d15['Close'].iloc[-1]
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        trend = "WZROST" if price > sma200 else "SPADEK"
        t_class = "trend-up" if trend == "WZROST" else "trend-down"
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "candle": analyze_candles(d15),
            "verdict": "KUP" if rsi < 32 else "SPRZEDAJ" if rsi > 68 else "CZEKAJ",
            "v_class": "v-buy" if rsi < 32 else "v-sell" if rsi > 68 else "v-wait",
            "trend": trend, "t_class": t_class, "df": d15
        }
    except: return None

# --- 2. SIDEBAR ---
with st.sidebar:
    st.title("🍯 ALPHA v16.5")
    api_key = st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole", value=load_tickers(), height=150)
    refresh_val = st.slider("Odświeżanie (s)", 30, 300, 60)

st_autorefresh(interval=refresh_val * 1000, key="fsh")

# --- 3. LOGIKA ---
t_list = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=5) as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    st.subheader("🔥 TOP 10 SYGNAŁÓW")
    sorted_data = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    
    # Rząd 1
    c_row1 = st.columns(5)
    for i in range(min(5, len(sorted_data))):
        d = sorted_data[i]
        with c_row1[i]:
            st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b>{d["price"]:.2f}</b><br><span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span><br><span class="{d["t_class"]}">{d["trend"]}</span></div>', unsafe_allow_html=True)
            
    # Rząd 2
    if len(sorted_data) > 5:
        c_row2 = st.columns(5)
        for i in range(5, len(sorted_data)):
            d = sorted_data[i]
            with c_row2[i-5]:
                st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b>{d["price"]:.2f}</b><br><span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span><br><span class="{d["t_class"]}">{d["trend"]}</span></div>', unsafe_allow_html=True)

    # Karty
    for d in data_list:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(f"### {d['symbol']} <span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
                st.markdown(f"""
                    <div class="metric-row"><span>RSI</span><b>{d['rsi']:.1f}</b></div>
                    <div class="metric-row"><span>Świeca</span><b>{d['candle']}</b></div>
                    <div class="metric-row"><span>Trend</span><b class="{d['t_class']}">{d['trend']}</b></div>
                """, unsafe_allow_html=True)
                if api_key and st.button(f"AI DECYZJA", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": f"Ticker {d['symbol']}, RSI {d['rsi']:.1f}, Candle {d['candle']}. Podaj tylko: 1. DECYZJA, 2. TP/SL, 3. POWÓD (1 zdanie)."}])
                    st.info(res.choices[0].message.content)
            with col2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                fig.update_layout(height=250, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
