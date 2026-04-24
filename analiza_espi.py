import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="AI ALPHA v15", layout="wide")

# --- 2. SILNIK Z FILTREM (NAPRAWIA CZARNY EKRAN) ---
def get_market_data(symbol):
    try:
        h1 = yf.download(symbol, period="10d", interval="1h", progress=False)
        d1 = yf.download(symbol, period="250d", interval="1d", progress=False)
        if h1.empty or d1.empty: return None
        
        # Filtr MultiIndex - musimy to mieć, żeby wykresy działały
        for df in [h1, d1]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        
        price = float(h1['Close'].iloc[-1])
        bid, ask = price * 0.9999, price * 1.0001
        
        # RSI 1h
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Pivot Point z wczoraj
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        
        # Trend i TP/SL (ATR)
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp, sl = price + (atr * 1.5), price - (atr * 1.2)
        trend = "HOSSA 🚀" if price > d1['Close'].rolling(200).mean().iloc[-1] else "BESSA 📉"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, 
            "rsi": rsi, "pp": pp, "tp": tp, "sl": sl,
            "trend": trend, "df": h1, "change": ((price - cp) / cp) * 100
        }
    except: return None

# --- 3. BOCZNY PANEL ---
with st.sidebar:
    st.title("🚀 SCANNER v15")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    input_tickers = st.text_area("Symbole", "STX.WA, LBW.WA, BCS.WA, BTC-USD")
    st_autorefresh(interval=60000, key="auto_refresh")

# --- 4. LOGIKA GŁÓWNA ---
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
results = [get_market_data(t) for t in tickers if get_market_data(t)]

if results:
    # --- TOP 10 RANKING RSI ---
    st.subheader("🔥 TOP 10 (OKAZJE RSI)")
    sorted_top = sorted(results, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.info(f"**{d['symbol']}**\nRSI: {d['rsi']:.1f}")

    st.divider()

    # --- DETALE ---
    for d in results:
        with st.container():
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                st.subheader(d['symbol'])
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.markdown(f"**BID:** {d['bid']:.4f} | **ASK:** {d['ask']:.4f}")
                st.write(f"**Pivot:** {d['pp']:.2f}")
                st.write(f"**TP / SL:** {d['tp']:.2f} / {d['sl']:.2f}")
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.add_hline(y=d['pp'], line_dash="dash", line_color="orange")
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            with c3:
                st.write("**AI ANALIZA**")
                if api_key and st.button(f"Skanuj {d['symbol']}", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini", 
                        messages=[{"role":"user","content":f"Werdykt dla {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}. Krótko!"}]
                    )
                    st.info(resp.choices[0].message.content) # Poprawione na 100%
            st.divider()
else:
    st.info("Podaj symbole i klucz API.")
