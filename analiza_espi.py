import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="AI ALPHA KOMBAJN", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    .bid-ask { color: #58a6ff; font-family: monospace; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK DANYCH ---
def get_market_data(symbol):
    try:
        t = yf.Ticker(symbol)
        d1h = t.history(period="10d", interval="1h")
        d1d = t.history(period="250d", interval="1d")
        
        if d1h.empty or d1d.empty: return None
        if isinstance(d1h.columns, pd.MultiIndex): d1h.columns = d1h.columns.get_level_values(0)
        
        price = d1h['Close'].iloc[-1]
        
        # Trendy i Pivot
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        sma50 = d1d['Close'].rolling(50).mean().iloc[-1]
        h_p, l_p, c_p = d1d['High'].iloc[-2], d1d['Low'].iloc[-2], d1d['Close'].iloc[-2]
        pp = (h_p + l_p + c_p) / 3
        
        # RSI 1h
        delta = d1h['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR / TP / SL
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "pp": pp, 
            "tp": price + (atr * 1.8), "sl": price - (atr * 1.2),
            "trend": "WZROST 🚀" if price > sma50 else "SPADEK 📉",
            "df": d1h, "change": ((price - c_p) / c_p * 100)
        }
    except: return None

# --- 3. UI ---
st.sidebar.title("🚜 KOMBAJN v18.0")
api_key = st.sidebar.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
t_input = st.sidebar.text_area("Symbole", "PKO.WA, BTC-USD, NVDA, BCS.WA")
st_autorefresh(interval=60000, key="auto_refresh")

tickers = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor() as ex:
    results = [r for r in list(ex.map(get_market_data, tickers)) if r]

if results:
    # TOP 10 RANKING
    st.subheader("🔥 TOP SYGNAŁY (RSI 1H)")
    sorted_top = sorted(results, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with t_cols[i % 5]:
            st.info(f"**{d['symbol']}**\nRSI: {d['rsi']:.1f}")

    st.divider()

    # DETALE
    for d in results:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            st.subheader(d['symbol'])
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"<div class='bid-ask'>B: {d['price']*0.9999:.2f} | A: {d['price']*1.0001:.2f}</div>", unsafe_allow_html=True)
            st.markdown(f"""
                <div class="metric-row"><span>Trend 1h</span><b>{d['trend']}</b></div>
                <div class="metric-row"><span>Pivot Point</span><b>{d['pp']:.2f}</b></div>
                <div class="metric-row"><span>Target TP</span><b style="color:#00ff88;">{d['tp']:.2f}</b></div>
                <div class="metric-row"><span>Stop SL</span><b style="color:#ff4b4b;">{d['sl']:.2f}</b></div>
            """, unsafe_allow_html=True)
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        with c3:
            if api_key and st.button(f"Mózg AI {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": f"Werdykt dla {d['symbol']}, cena {d['price']}, RSI {d['rsi']:.1f}. Krótko!"}]
                )
                st.info(resp.choices[0].message.content)
        st.markdown('</div>', unsafe_allow_html=True)
