import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="AI ALPHA v14.5 - STABILNA", layout="wide")

# --- 2. STYLE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #1c2128; padding: 10px; border-radius: 8px; border: 1px solid #444c56; text-align: center; }
    .bid-ask { font-family: monospace; color: #58a6ff; font-size: 0.9rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK Z FILTREM (KLUCZOWY!) ---
def get_market_data(symbol):
    try:
        # Pobieranie danych 1h i 1d
        h1 = yf.download(symbol, period="10d", interval="1h", progress=False)
        d1 = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if h1.empty or d1.empty: return None
        
        # --- FILTR MULTIINDEX (Naprawia czarny ekran) ---
        for df in [h1, d1]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        
        price = float(h1['Close'].iloc[-1])
        # Symulacja Bid/Ask
        bid, ask = price * 0.9999, price * 1.0001
        
        # RSI 1h
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Pivot Points (z wczoraj)
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        r1, s1 = (2 * pp) - lp, (2 * pp) - hp
        
        # Trend SMA 200
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        trend = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        
        # ATR dla TP/SL
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp, sl = price + (atr * 1.5), price - (atr * 1.2)

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, 
            "rsi": rsi, "pp": pp, "r1": r1, "s1": s1, "tp": tp, "sl": sl,
            "trend": trend, "df": h1, "change": ((price - cp) / cp) * 100
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚀 SCANNER v14.5")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    input_tickers = st.text_area("Symbole", "LBW.WA, BCS.WA, PLRX, BTC-USD, NVDA")
    refresh = st.select_slider("Odśwież (s)", options=, value=60)

st_autorefresh(interval=refresh * 1000, key="auto_refresh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
results = [get_market_data(t) for t in tickers if get_market_data(t)]

if results:
    # --- TOP 10 RANKING ---
    st.subheader("🔥 TOP 10 - EKSTREMALNE RSI (OKAZJE)")
    sorted_top = sorted(results, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            color = "#00ff88" if d['rsi'] < 35 else "#ff4b4b" if d['rsi'] > 65 else "#8b949e"
            st.markdown(f"""
                <div class="top-rank-card" style="border-top:3px solid {color};">
                    <b>{d['symbol']}</b><br>{d['price']:.2f}<br>
                    <span class="bid-ask">B: {d['bid']:.2f} | A: {d['ask']:.2f}</span><br>
                    <small>RSI: {d['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in results:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns()
            with c1:
                st.subheader(d['symbol'])
                st.markdown(f"<div class='bid-ask'>BID: {d['bid']:.4f}<br>ASK: {d['ask']:.4f}</div>", unsafe_allow_html=True)
                st.write(f"**Trend:** {d['trend']}")
                st.write(f"**TP / SL:** {d['tp']:.2f} / {d['sl']:.2f}")
                st.write(f"**Pivot:** {d['pp']:.2f}")
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.add_hline(y=d['pp'], line_dash="dash", line_color="orange")
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            with c3:
                st.write("**AI ANALIZA**")
                if api_key and st.button(f"Skanuj {d['symbol']}", key=f"btn_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini", 
                        messages=[{"role":"user","content":f"Werdykt dla {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['pp']:.2f}. Krótko!"}]
                    )
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Podaj symbole i klucz API w panelu bocznym.")
