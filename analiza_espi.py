import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="AI ALPHA v13", layout="wide")

# --- 2. STYLE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #1c2128; padding: 12px; border-radius: 10px; border: 1px solid #444c56; text-align: center; }
    .bid-ask { font-family: monospace; color: #58a6ff; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        # Pobieranie danych: 1h (wykres) i 1d (wskaźniki)
        h1 = yf.download(symbol, period="10d", interval="1h", progress=False)
        d1 = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if h1.empty or d1.empty: return None
        
        # Spłaszczanie kolumn (fix dla yfinance)
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        if isinstance(d1.columns, pd.MultiIndex): d1.columns = d1.columns.get_level_values(0)
        
        price = float(h1['Close'].iloc[-1])
        # Symulacja Bid/Ask (spread 0.02%)
        bid, ask = price * 0.9999, price * 1.0001
        
        # Wskaźniki
        rsi = 100 - (100 / (1 + (h1['Close'].diff().where(lambda x: x > 0, 0).rolling(14).mean() / 
                                 h1['Close'].diff().where(lambda x: x < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        # Pivot Points z wczoraj
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        r1, s1 = (2 * pp) - lp, (2 * pp) - hp
        
        # ATR dla TP/SL
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp, sl = price + (atr * 1.5), price - (atr * 1.2)

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "pp": pp, "r1": r1, "s1": s1, "tp": tp, "sl": sl, "df": h1,
            "change": ((price - d1['Close'].iloc[-2]) / d1['Close'].iloc[-2]) * 100
        }
    except: return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("🚀 ALPHA v13")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    ticker_input = st.text_area("Symbole", "LBW.WA, BCS.WA, PLRX, BTC-USD, NVDA")
    refresh = st.select_slider("Odśwież (s)", options=, value=60)

st_autorefresh(interval=refresh * 1000, key="auto_refresh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
results = [get_analysis(t) for t in tickers if get_analysis(t)]

if results:
    # --- TOP 10 RANKING ---
    st.subheader("🔥 EKSTREMALNE RSI (OKAZJE)")
    sorted_top = sorted(results, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            rec = "KUPUJ" if d['rsi'] < 35 else "SPRZEDAJ" if d['rsi'] > 65 else "CZEKAJ"
            st.markdown(f"""
                <div class="top-rank-card">
                    <b>{d['symbol']}</b><br>{d['price']:.2f}<br>
                    <span class="bid-ask">B: {d['bid']:.2f} | A: {d['ask']:.2f}</span><br>
                    <small>RSI: {d['rsi']:.1f}</small><br>
                    <b>{rec}</b>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in results:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                st.subheader(d['symbol'])
                st.markdown(f"<div class='bid-ask'>BID: {d['bid']:.4f}<br>ASK: {d['ask']:.4f}</div>", unsafe_allow_html=True)
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**TP / SL:**  \n{d['tp']:.2f} / {d['sl']:.2f}")
                st.write(f"**Pivot:** {d['pp']:.2f}")
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            with c3:
                st.write("**AI ANALIZA**")
                if api_key and st.button(f"Skanuj {d['symbol']}", key=f"btn_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": f"Oceń {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['pp']:.2f}. Podaj werdykt."}])
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Podaj symbole i klucz API, aby rozpocząć.")
