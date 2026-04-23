import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA TURBO v13.0", page_icon="⚡", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "BTC-USD, ETH-USD, NVDA, TSLA, AAPL"
    return "BTC-USD, ETH-USD, NVDA, TSLA, AAPL"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .pattern-badge { background: #1f6feb; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; margin-right: 5px; }
    .orderbook-box { background: #010409; padding: 10px; border-radius: 8px; border: 1px solid #30363d; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ANALIZA TECHNICZNA & FORMACJE ---
def detect_patterns(df):
    patterns = []
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Młot (Hammer)
    body = abs(last['Close'] - last['Open'])
    lower_shadow = min(last['Open'], last['Close']) - last['Low']
    upper_shadow = last['High'] - max(last['Open'], last['Close'])
    if lower_shadow > (2 * body) and upper_shadow < body:
        patterns.append("🔨 MŁOT (HAMMER)")
    
    # Objęcie Hossy (Bullish Engulfing)
    if prev['Close'] < prev['Open'] and last['Close'] > last['Open'] and \
       last['Open'] < prev['Close'] and last['Close'] > prev['Open']:
        patterns.append("🐂 OBJĘCIE HOSSY")
        
    return patterns

def fetch_data(symbol):
    try:
        t_obj = yf.Ticker(symbol)
        inf = t_obj.info
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if d15.empty or d1d.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        bid = inf.get('bid', 0)
        ask = inf.get('ask', 0)
        
        # Wskaźniki
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        delta = d15['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        patterns = detect_patterns(d15)

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "patterns": patterns,
            "bid": bid, "ask": ask, "spread_pct": ((ask-bid)/bid*100 if bid>0 else 0),
            "trend": "HOSSA" if price > sma200 else "BESSA",
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.2), "df": d15
        }
    except: return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚡ TURBO v13.0")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. EXECUTION (MULTITHREADING) ---
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(fetch_data, tickers))
data_list = [r for r in results if r]

# --- 6. RENDEROWANIE ---
if data_list:
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader(f"{d['symbol']}")
            st.metric("Cena", f"{d['price']:.2f}", f"{d['trend']}")
            
            # Formacje
            if d['patterns']:
                for p in d['patterns']:
                    st.markdown(f'<span class="pattern-badge">{p}</span>', unsafe_allow_html=True)
            
            # Arkusz
            st.markdown(f"""
                <div class="orderbook-box">
                    <small style="color:#8b949e;">SPREAD: {d['spread_pct']:.3f}%</small><br>
                    <b style="color:#00ff88;">B: {d['bid']}</b> | <b style="color:#ff4b4b;">A: {d['ask']}</b>
                </div>
            """, unsafe_allow_html=True)
            
            st.write(f"**RSI:** {d['rsi']:.1f} | **SL:** {d['sl']:.2f}")

            if api_key and st.button(f"🧠 AI ANALYZE", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = f"Analiza techniczna {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Formacje: {d['patterns']}. Daj krótki sygnał."
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.info(resp.choices[0].message.content)

        with c2:
            fig = go.Figure()
            # Świece
            fig.add_trace(go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:], name="Cena"))
            # Wolumen (jako słupki w tle)
            fig.add_trace(go.Bar(x=d['df'].index[-60:], y=d['df']['Volume'][-60:], name="Wolumen", marker_color='rgba(100,100,100,0.3)', yaxis='y2'))
            
            fig.update_layout(
                template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0),
                xaxis_rangeslider_visible=False,
                yaxis2=dict(title="Wolumen", overlaying='y', side='right', showgrid=False),
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

st.caption("v13.0 Turbo: Multithreading On | Pattern Scan Active | Volume VBP Enabled")
