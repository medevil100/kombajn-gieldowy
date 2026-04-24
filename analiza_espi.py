import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- KONFIGURACJA ---
st.set_page_config(page_title="AI SUPERKOMBAJN v12.8", page_icon="📈", layout="wide")

# --- SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieranie danych 1h i 1d
        d1h = yf.download(symbol, period="5d", interval="1h", progress=False)
        d1d = yf.download(symbol, period="5d", interval="1d", progress=False)
        
        if d1h.empty or d1d.empty: return None
        
        # Fix dla MultiIndex kolumn
        for df in [d1h, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d1h['Close'].iloc[-1])
        # Realistyczne Bid/Ask (spread 0.01%)
        bid, ask = price * 0.9999, price * 1.0001
        
        # Pivot Points z wczorajszego dnia
        h, l, c = d1d['High'].iloc[-2], d1d['Low'].iloc[-2], d1d['Close'].iloc[-2]
        pp = (h + l + c) / 3
        r1, s1 = (2 * pp) - l, (2 * pp) - h
        
        # RSI 1h
        delta = d1h['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        return {"symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, "pivot": pp, "r1": r1, "s1": s1, "df": d1h}
    except: return None

# --- UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ USTAWIENIA")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    tickers = st.text_area("Symbole", "PKO.WA, BTC-USD, NVDA, TSLA").split(",")
    refresh = st.slider("Odśwież (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- GŁÓWNA LOGIKA ---
data = [get_analysis(t.strip().upper()) for t in tickers if get_analysis(t.strip().upper())]

if data:
    # TOP 10
    st.subheader("📊 TOP 10 - SKANER 1H")
    sorted_data = sorted(data, key=lambda x: x['rsi'])[:10]
    cols = st.columns(5)
    for i, d in enumerate(sorted_data):
        with cols[i % 5]:
            st.metric(d['symbol'], f"{d['price']:.2f}", f"RSI: {d['rsi']:.1f}", delta_color="off")

    st.divider()

    # SZCZEGÓŁY
    for d in data:
        with st.expander(f"🔍 {d['symbol']} - ANALIZA SZCZEGÓŁOWA", expanded=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                st.write(f"**BID:** {d['bid']:.4f} | **ASK:** {d['ask']:.4f}")
                st.write(f"**Pivot:** {d['pivot']:.2f} (R1: {d['r1']:.2f} / S1: {d['s1']:.2f})")
                if api_key and st.button(f"Analiza AI {d['symbol']}", key=d['symbol']):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":f"Oceń {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}"}])
                    st.info(resp.choices[0].message.content)
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
