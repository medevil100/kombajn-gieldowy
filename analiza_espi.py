import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. PAMIĘĆ SPÓŁEK ---
DB_FILE = "moje_spolki.txt"

def save_tickers(text):
    with open(DB_FILE, "w") as f: f.write(text)

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, IOVA, HUMA"
    return "PKO.WA, BTC-USD, NVDA, IOVA, HUMA"

# --- 2. KONFIGURACJA ---
st.set_page_config(page_title="AI Alpha Kombajn v19.2", page_icon="🧠", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; }
    .ticker-card { background: #0a0b10; padding: 20px; border-radius: 15px; border: 1px solid #1a1c23; margin-bottom: 20px; }
    .buy-signal { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0, 255, 136, 0.1); }
    .verdict-box { background: #07121d; padding: 15px; border-radius: 10px; border-left: 5px solid #00e5ff; margin-top: 10px; font-size: 0.9rem; line-height: 1.5; }
    .tf-badge { background: #1a1a1a; padding: 4px 8px; border-radius: 6px; font-size: 0.75rem; color: #00e5ff; border: 1px solid #333; margin-right: 5px; }
    .exit-box { background: #12141d; padding: 12px; border-radius: 8px; border: 1px solid #333; margin: 15px 0; }
    .bid-ask { color: #58a6ff; font-family: monospace; font-size: 0.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIKA DANYCH ---
def get_data(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1h = yf.download(symbol, period="15d", interval="1h", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if d15.empty or d1d.empty: return None

        for df in [d15, d1h, d1d]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        bid, ask = price * 0.9999, price * 1.0001
        
        sma_h = d1h['Close'].rolling(50).mean().iloc[-1]
        sma_d = d1d['Close'].rolling(100).mean().iloc[-1]
        
        delta = d15['Close'].diff()
        rsi = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        prev = d1d.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, "pivot": pivot,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.0),
            "t_mid": "UP 📈" if price > sma_h else "DOWN 📉",
            "t_long": "BULL 🐂" if price > sma_d else "BEAR 🐻", "df": d15
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.header("⚙️ USTAWIENIA")
    api_key = st.text_input("OpenAI API Key:", type="password") or st.secrets.get("OPENAI_API_KEY")
    
    saved_list = load_tickers()
    tickers_input = st.text_area("Twoja Lista Spółek:", value=saved_list, height=200)
    if tickers_input != saved_list:
        save_tickers(tickers_input)
        
    tickers = [x.strip().upper() for x in tickers_input.split(",") if x.strip()]
    refresh_val = st.select_slider("Auto-odświeżanie (sek)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh_val * 1000, key="fscounter")

# --- 5. WYŚWIETLANIE ---
if api_key:
    client = OpenAI(api_key=api_key)
    all_data = [get_data(t) for t in tickers if get_data(t)]
    
    if all_data:
        st.subheader("🔥 TOP SYGNAŁY (RSI)")
        sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
        top_cols = st.columns(5)
        for i, d in enumerate(sorted_top):
            with top_cols[i % 5]:
                st.markdown(f"""
                    <div style="background:#0a0b10; padding:10px; border-radius:8px; border:1px solid #333; text-align:center;">
                        <small>{d['symbol']}</small><br><b>{d['price']:.2f}</b><br>
                        <small style="color:{'#00ff88' if d['rsi'] < 35 else '#888'};">RSI: {d['rsi']:.1f}</small>
                    </div>
                """, unsafe_allow_html=True)
        
        st.divider()

        for data in all_data:
            st.markdown(f'<div class="ticker-card {"buy-signal" if data["rsi"] < 35 else ""}">', unsafe_allow_html=True)
            c1, c2 = st.columns([1.5, 2.5])
            
            with c1:
                st.subheader(data['symbol'])
                st.markdown(f"## {data['price']:.4f}")
                st.markdown(f"<div class='bid-ask'>BID: {data['bid']:.4f} | ASK: {data['ask']:.4f}</div>", unsafe_allow_html=True)
                st.markdown(f"<span class='tf-badge'>H1: {data['t_mid']}</span><span class='tf-badge'>D1: {data['t_long']}</span>", unsafe_allow_html=True)
                
                st.markdown(f"""
                    <div class="exit-box">
                        <b style="color:#00ff88">🎯 TP: {data['tp']:.4f}</b> | 
                        <b style="color:#ff4b4b">🛑 SL: {data['sl']:.4f}</b><br>
                        <small style="color:#888;">PIVOT: {data['pivot']:.4f} | RSI: {data['rsi']:.1f}</small>
                    </div>
                """, unsafe_allow_html=True)

                if st.button(f"🧠 ANALIZA AI {data['symbol']}", key=f"ai_{data['symbol']}"):
                    p = f"Krótki werdykt dla {data['symbol']}: Cena {data['price']}, RSI {data['rsi']:.1f}, Trend D1 {data['t_long']}. Podaj ocenę 1-10 i decyzję."
                    # NAPRAWIONO: Dodano [0] przed .message
                    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": p}])
                    st.session_state[f"val_{data['symbol']}"] = res.choices[0].message.content

                if f"val_{data['symbol']}" in st.session_state:
                    st.markdown(f'<div class="verdict-box">{st.session_state[f"val_{data['symbol']}"]}</div>', unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-60:], open=data['df']['Open'][-60:], high=data['df']['High'][-60:], low=data['df']['Low'][-60:], close=data['df']['Close'][-60:])])
                fig.add_hline(y=data['pivot'], line_dash="dot", line_color="white")
                fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{data['symbol']}")
            
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Wprowadź API Key OpenAI.")
