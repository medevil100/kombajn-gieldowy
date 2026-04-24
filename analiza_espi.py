import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA I PAMIĘĆ ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA KOMBAJN v2026", page_icon="🚜", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# --- 2. STYLE WIZUALNE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #1c2128; padding: 12px; border-radius: 10px; border: 1px solid #444c56; text-align: center; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.95rem; }
    .bid-ask { font-family: monospace; color: #58a6ff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_market_data(symbol):
    try:
        # Pobieranie danych: 1h (interwał świec) oraz 1d (wskaźniki i Pivot)
        h1 = yf.download(symbol, period="10d", interval="1h", progress=False)
        d1 = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if h1.empty or d1.empty: return None

        # FIX: Prostowanie danych z Yahoo Finance (zapobiega błędowi wykresów)
        for df in [h1, d1]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        
        price = float(h1['Close'].iloc[-1])
        # Symulacja Bid/Ask (spread 0.02%)
        bid, ask = price * 0.9999, price * 1.0001
        
        # Trendy
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        sma50 = d1['Close'].rolling(50).mean().iloc[-1]
        trend_long = "WZROST 🚀" if price > sma200 else "SPADEK 📉"
        
        # Pivot Points (z wczoraj)
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        
        # RSI 1h
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR dla TP/SL
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp, sl = price + (atr * 1.5), price - (atr * 1.2)

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, 
            "rsi": rsi, "pp": pp, "tp": tp, "sl": sl, "trend": trend_long,
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 SCANNER v2026")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    input_tickers = st.text_area("Lista Symboli", value=load_tickers(), height=200)
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f: f.write(input_tickers)
        st.success("Zapisano!")
    
    refresh = st.select_slider("Odświeżanie (s)", options=, value=60)

st_autorefresh(interval=refresh * 1000, key="refresh_main")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
results = [get_market_data(t) for t in tickers if get_market_data(t)]

if results:
    # --- TOP 10 RANKING ---
    st.subheader("🔥 TOP SYGNAŁY (RSI 1H)")
    sorted_top = sorted(results, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-rank-card">
                    <b>{d['symbol']}</b><br>{d['price']:.2f}<br>
                    <small>RSI: {d['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in results:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.2, 2.5, 1.2])
            
            with c1:
                st.subheader(d['symbol'])
                st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.markdown(f"<div class='bid-ask'>BID: {d['bid']:.4f}<br>ASK: {d['ask']:.4f}</div>", unsafe_allow_html=True)
                st.markdown(f"""
                    <div class="metric-row"><span>Trend Długi</span><b>{d['trend']}</b></div>
                    <div class="metric-row"><span>Pivot Point</span><b>{d['pp']:.2f}</b></div>
                    <div class="metric-row"><span>Target TP</span><b style="color:#00ff88;">{d['tp']:.2f}</b></div>
                    <div class="metric-row"><span>Stop SL</span><b style="color:#ff4b4b;">{d['sl']:.2f}</b></div>
                """, unsafe_allow_html=True)

            with c2:
                # Wykres świecowy 1h
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-50:], open=d['df']['Open'][-50:], high=d['df']['High'][-50:], low=d['df']['Low'][-50:], close=d['df']['Close'][-50:])])
                fig.add_hline(y=d['pp'], line_dash="dash", line_color="orange")
                fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{d['symbol']}")

            with c3:
                st.write("🤖 **STRATEGIA AI**")
                if api_key and st.button(f"Skanuj {d['symbol']}", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    # POPRAWIONA LOGIKA ODPOWIEDZI
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": f"Werdykt dla {d['symbol']}, cena {d['price']}, RSI {d['rsi']:.1f}. Krótko!"}]
                    )
                    st.info(response.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Podaj symbole w panelu bocznym i klucz API.")
