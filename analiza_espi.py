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
    .top-tile { background: #161b22; padding: 10px; border-radius: 8px; border: 1px solid #30363d; text-align: center; min-height: 150px; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .v-buy { color: #238636; font-weight: bold; font-size: 0.8rem; }
    .v-sell { color: #da3633; font-weight: bold; font-size: 0.8rem; }
    .bid-ask-box { font-size: 0.75rem; background: #0d1117; padding: 4px; border-radius: 4px; margin-top: 5px; border: 1px solid #21262d; }
    .trend-up { color: #238636; font-size: 0.75rem; font-weight: bold; }
    .trend-down { color: #da3633; font-size: 0.75rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK DANYCH ---
def fetch_data(symbol):
    try:
        t = yf.Ticker(symbol)
        h1d = t.history(period="1y", interval="1d")
        h15 = t.history(period="5d", interval="15m")
        if h15.empty: return None
        
        # Pobieranie Bid/Ask z fast_info (szybsze i stabilniejsze)
        price = h15['Close'].iloc[-1]
        try:
            bid = t.info.get('bid', price)
            ask = t.info.get('ask', price)
        except:
            bid, ask = price, price

        # RSI
        delta = h1d['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Trend (SMA200)
        sma200 = h1d['Close'].rolling(200).mean().iloc[-1]
        trend = "WZROST" if price > sma200 else "SPADEK"
        
        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "trend": trend, "df": h15, "change": ((price - h1d['Close'].iloc[-2])/h1d['Close'].iloc[-2])*100
        }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.5 GOLDEN")
    api_key = st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole (min. 10)", "BTC-USD, ETH-USD, NVDA, TSLA, PKO.WA, ALE.WA, CDR.WA, AAPL, MSFT, META", height=150)
    refresh = st.slider("Odśwież (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="auto_refresh")

# --- 4. RENDEROWANIE ---
symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in executor.map(fetch_data, symbols) if r]

if results:
    st.subheader("🔥 TOP 10 SYGNAŁÓW (RSI + TREND + BID/ASK)")
    top_10 = sorted(results, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    
    # WYMUSZENIE 2 RZĘDÓW PO 5 KAFELKÓW
    for row_idx in [0, 5]:
        cols = st.columns(5)
        for col_idx in range(5):
            data_idx = row_idx + col_idx
            if data_idx < len(top_10):
                d = top_10[data_idx]
                with cols[col_idx]:
                    t_class = "trend-up" if d['trend'] == "WZROST" else "trend-down"
                    st.markdown(f"""
                        <div class="top-tile">
                            <small>{d['symbol']}</small><br>
                            <b style="font-size:1.1rem;">{d['price']:.2f}</b><br>
                            <span class="{t_class}">{d['trend']}</span><br>
                            <div class="bid-ask-box">
                                <span style="color:#da3633">B: {d['bid']:.2f}</span> | 
                                <span style="color:#238636">A: {d['ask']:.2f}</span>
                            </div>
                            <small style="color:#8b949e">RSI: {d['rsi']:.1f}</small>
                        </div>
                    """, unsafe_allow_html=True)

    # KARTY ANALIZY
    for d in results:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.write(f"### {d['symbol']}")
                st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.markdown(f"**BID:** <span style='color:#da3633'>{d['bid']:.2f}</span> | **ASK:** <span style='color:#238636'>{d['ask']:.2f}</span>", unsafe_allow_html=True)
                st.write(f"**RSI:** {d['rsi']:.1f} | **Trend:** {d['trend']}")
                if api_key and st.button(f"DECYZJA AI", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Krótko: Decyzja, TP/SL, Powód."}, {"role": "user", "content": f"{d['symbol']} RSI:{d['rsi']:.1f}"}])
                    st.success(res.choices[0].message.content)
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                fig.update_layout(height=250, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.error("Brak danych. Sprawdź symbole (np. BTC-USD, NVDA, PKO.WA).")
