import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA UI ---
st.set_page_config(page_title="AI ALPHA GOLDEN v16.5", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; margin-bottom: 10px; min-height: 140px; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .verdict-badge { padding: 3px 10px; border-radius: 15px; font-weight: bold; text-transform: uppercase; font-size: 0.7rem; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .trend-label { font-size: 0.75rem; font-weight: bold; margin-top: 5px; display: block; }
    .trend-up { color: #238636; }
    .trend-down { color: #da3633; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    .candle-signal { color: #f1c40f; font-weight: bold; }
    .bid-ask { font-size: 0.8rem; margin-top: 5px; display: flex; justify-content: space-around; }
    </style>
    """, unsafe_allow_html=True)

def analyze_candles(df):
    if len(df) < 3: return "Brak"
    last, prev = df.iloc[-1], df.iloc[-2]
    body = abs(last['Close'] - last['Open'])
    upper_wick = last['High'] - max(last['Open'], last['Close'])
    lower_wick = min(last['Open'], last['Close']) - last['Low']
    if lower_wick > (2 * body) and upper_wick < (0.5 * body) and body > 0: return "🔨 MŁOT"
    if last['Close'] > prev['Open'] and last['Open'] < prev['Close'] and prev['Close'] < prev['Open']: return "🟢 OBJĘCIE"
    if upper_wick > (2 * body) and lower_wick < (0.5 * body) and body > 0: return "☄️ GWIAZDA"
    return "Brak"

def get_data(symbol):
    try:
        t = yf.Ticker(symbol)
        d_long = t.history(period="1y", interval="1d")
        d15 = t.history(period="5d", interval="15m")
        if d15.empty: return None
        
        info = t.info
        price = d15['Close'].iloc[-1]
        bid = info.get('bid') or info.get('regularMarketPreviousClose') or price
        ask = info.get('ask') or info.get('regularMarketOpen') or price
        
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        trend_val = "WZROST" if price > sma200 else "SPADEK"
        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "candle": analyze_candles(d15), "trend": trend_val,
            "v_class": "v-buy" if rsi < 32 else "v-sell" if rsi > 68 else "v-wait",
            "verdict": "KUP" if rsi < 32 else "SPRZEDAJ" if rsi > 68 else "CZEKAJ",
            "df": d15, "change": ((price - d_long['Close'].iloc[-2])/d_long['Close'].iloc[-2])*100
        }
    except: return None

# --- SIDEBAR ---
with st.sidebar:
    st.title("🍯 ALPHA GOLDEN")
    api_key = st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole", value="BTC-USD, ETH-USD, NVDA, TSLA, PKO.WA, ALE.WA, CDR.WA, AAPL, MSFT, META", height=120)
    refresh_val = st.slider("Odśwież (s)", 30, 300, 60)
st_autorefresh(interval=refresh_val * 1000, key="fsh")

# --- LOGIKA ---
t_list = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    st.subheader("🔥 TOP 10 SYGNAŁÓW RSI + TREND")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    
    # RZĄD 1 (1-5)
    row1_cols = st.columns(5)
    for i in range(min(5, len(sorted_top))):
        d = sorted_top[i]
        with row1_cols[i]:
            t_color = "#238636" if d['trend'] == "WZROST" else "#da3633"
            st.markdown(f"""<div class="top-tile"><small>{d['symbol']}</small><br><b>{d['price']:.2f}</b><br><span class="verdict-badge {d['v_class']}">{d['verdict']}</span><br><span style="color:{t_color}; font-size:0.7rem; font-weight:bold;">{d['trend']}</span><div class="bid-ask"><span style="color:#da3633">B:{d['bid']:.2f}</span><span style="color:#238636">A:{d['ask']:.2f}</span></div></div>""", unsafe_allow_html=True)

    # RZĄD 2 (6-10)
    if len(sorted_top) > 5:
        row2_cols = st.columns(5)
        for i in range(5, len(sorted_top)):
            d = sorted_top[i]
            with row2_cols[i-5]:
                t_color = "#238636" if d['trend'] == "WZROST" else "#da3633"
                st.markdown(f"""<div class="top-tile"><small>{d['symbol']}</small><br><b>{d['price']:.2f}</b><br><span class="verdict-badge {d['v_class']}">{d['verdict']}</span><br><span style="color:{t_color}; font-size:0.7rem; font-weight:bold;">{d['trend']}</span><div class="bid-ask"><span style="color:#da3633">B:{d['bid']:.2f}</span><span style="color:#238636">A:{d['ask']:.2f}</span></div></div>""", unsafe_allow_html=True)

    # SZCZEGÓŁY
    for d in data_list:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"### {d['symbol']} <span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.markdown(f"**BID:** `{d['bid']:.2f}` | **ASK:** `{d['ask']:.2f}`")
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"""<div class="metric-row"><span>RSI</span><b>{d['rsi']:.1f}</b></div><div class="metric-row"><span>Świeca</span><b class="candle-signal">{d['candle']}</b></div><div class="metric-row"><span>Trend</span><b>{d['trend']}</b></div>""", unsafe_allow_html=True)
            if api_key and st.button(f"🚀 DECYZJA AI", key=f"btn_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś suchym traderem. Podaj: 1. DECYZJA, 2. TP/SL, 3. POWÓD (1 zdanie)."}, {"role": "user", "content": f"Ticker: {d['symbol']}, RSI: {d['rsi']:.1f}, Candle: {d['candle']}"}])
                st.info(res.choices[0].message.content)
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(height=280, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
