import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="ALPHA GOLDEN v16.5", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 10px; border-radius: 8px; border: 1px solid #30363d; text-align: center; height: 160px; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .v-buy { color: #238636; font-weight: bold; }
    .v-sell { color: #da3633; font-weight: bold; }
    .bid-ask { font-size: 0.75rem; color: #8b949e; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK DANYCH (Z CACHE) ---
@st.cache_data(ttl=60)
def fetch_symbol_data(symbol):
    try:
        t = yf.Ticker(symbol)
        hist_1d = t.history(period="1y", interval="1d")
        hist_15m = t.history(period="5d", interval="15m")
        if hist_15m.empty: return None
        
        info = t.info
        price = hist_15m['Close'].iloc[-1]
        
        # Oblicz RSI
        delta = hist_1d['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Analiza świec (prosta)
        last_c = hist_15m.iloc[-1]
        candle = "🔨 MŁOT" if (min(last_c['Open'], last_c['Close']) - last_c['Low']) > (abs(last_c['Close'] - last_c['Open']) * 2) else "Brak"
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "candle": candle,
            "bid": info.get('bid', price), "ask": info.get('ask', price),
            "trend": "WZROST" if price > hist_1d['Close'].rolling(200).mean().iloc[-1] else "SPADEK",
            "df": hist_15m, "change": ((price - hist_1d['Close'].iloc[-2])/hist_1d['Close'].iloc[-2])*100
        }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 ALPHA v16.5")
    api_key = st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole", "BTC-USD, ETH-USD, NVDA, TSLA, PKO.WA, ALE.WA, CDR.WA, AAPL, MSFT, META", height=150)
    refresh = st.slider("Odśwież (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="auto")

# --- 4. RENDEROWANIE ---
symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=5) as executor:
    results = [r for r in executor.map(fetch_symbol_data, symbols) if r]

if results:
    st.subheader("🔥 TOP 10 SYGNAŁÓW")
    top_10 = sorted(results, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    
    # RZĄD 1
    c1 = st.columns(5)
    for i in range(min(5, len(top_10))):
        d = top_10[i]
        with c1[i]:
            st.markdown(f"""<div class="top-tile"><b>{d['symbol']}</b><br><h3>{d['price']:.2f}</h3><span class="{'v-buy' if d['rsi']<50 else 'v-sell'}">{d['trend']}</span><div class="bid-ask">B: {d['bid']:.2f} | A: {d['ask']:.2f}</div><small>RSI: {d['rsi']:.1f}</small></div>""", unsafe_allow_html=True)

    # RZĄD 2
    if len(top_10) > 5:
        c2 = st.columns(5)
        for i in range(5, len(top_10)):
            d = top_10[i]
            with c2[i-5]:
                st.markdown(f"""<div class="top-tile"><b>{d['symbol']}</b><br><h3>{d['price']:.2f}</h3><span class="{'v-buy' if d['rsi']<50 else 'v-sell'}">{d['trend']}</span><div class="bid-ask">B: {d['bid']:.2f} | A: {d['ask']:.2f}</div><small>RSI: {d['rsi']:.1f}</small></div>""", unsafe_allow_html=True)

    # LISTA SZCZEGÓŁOWA
    for d in results:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            col1, col2 = st.columns([1, 2])
            with col1:
                st.write(f"### {d['symbol']}")
                st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**BID:** {d['bid']} | **ASK:** {d['ask']}")
                st.write(f"**Trend:** {d['trend']} | **RSI:** {d['rsi']:.1f}")
                st.write(f"**Świeca:** {d['candle']}")
                if api_key and st.button(f"DECYZJA AI", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": f"Szybka decyzja: {d['symbol']}, Cena {d['price']}, RSI {d['rsi']:.1f}. Podaj wejście/TP/SL."}])
                    st.success(res.choices[0].message.content)
            with col2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                fig.update_layout(height=250, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Pobieranie danych... Jeśli to trwa zbyt długo, Yahoo Finance zablokowało tymczasowo Twoje IP.")
