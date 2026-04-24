import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.3", page_icon="🚀", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; min-height: 180px; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .candle-analysis { font-size: 0.8rem; color: #58a6ff; font-weight: bold; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNKCJE ANALITYCZNE ---
def get_candle_pattern(df):
    if len(df) < 2: return "Brak danych"
    last = df.iloc[-1]
    body = last['Close'] - last['Open']
    wick_top = last['High'] - max(last['Open'], last['Close'])
    wick_bot = min(last['Open'], last['Close']) - last['Low']
    if body > 0 and wick_top > abs(body) * 1.5: return "Słabość (Góra)"
    if body < 0 and wick_bot > abs(body) * 1.5: return "Odbicie (Dół)"
    if abs(body) < (last['High'] - last['Low']) * 0.1: return "Doji"
    return "Bycza" if body > 0 else "Niedźwiedzia"

def calculate_itrend(df, period=20):
    ema = df['Close'].ewm(span=period).mean()
    itrend = df['Close'] - ema
    val = itrend.iloc[-1]
    return val, "BULL" if val > 0 else "BEAR"

# --- 4. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        d15 = yf.download(symbol, period="2d", interval="15m", progress=False)
        d1h = yf.download(symbol, period="5d", interval="1h", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if d15.empty or d1h.empty: return None
        
        for df in [d15, d1h, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        price = float(d15['Close'].iloc[-1])
        bid = info.get('bid', price * 0.999)
        ask = info.get('ask', price * 1.001)
        
        itrend_val, itrend_dir = calculate_itrend(d1h)
        p15 = get_candle_pattern(d15)
        p1h = get_candle_pattern(d1h)
        
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        
        # RSI
        delta = d1h['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "change": change_pct,
            "rsi": rsi, "itrend_dir": itrend_dir, "itrend_val": itrend_val,
            "p15": p15, "p1h": p1h, "df15": d15, "df1h": d1h, 
            "trend": "HOSSA" if price > sma200 else "BESSA",
            "trend_col": "#00ff88" if price > sma200 else "#ff4b4b"
        }
    except: return None

# --- 5. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ KOMB_v12.3")
    api_key = st.text_input("OpenAI Key", type="password") if "OPENAI_API_KEY" not in st.secrets else st.secrets["OPENAI_API_KEY"]
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 6. GŁÓWNA LOGIKA ---
if api_key:
    client = OpenAI(api_key=api_key)
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    
    data_list = []
    for t in tickers:
        res = get_analysis(t)
        if res: data_list.append(res)

    if data_list:
        # --- TOP 10 KAFELKI ---
        st.subheader("📊 MONITORING TOP 10")
        top_cols = st.columns(5)
        sorted_top = sorted(data_list, key=lambda x: abs(x['change']), reverse=True)[:10]
        
        for i, d in enumerate(sorted_top):
            with top_cols[i % 5]:
                c_col = "#00ff88" if d['change'] >= 0 else "#ff4b4b"
                st.markdown(f"""
                    <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                        <small>{d['symbol']}</small><br>
                        <span style="color:{c_col}; font-size:1.2rem; font-weight:bold;">{d['price']:.2f}</span><br>
                        <span style="font-size:0.7rem;">iTrend: {d['itrend_dir']}</span><br>
                        <div style="font-size:0.7rem; color:#8b949e; margin-top:5px;">
                            15m: {d['p15']}<br>1h: {d['p1h']}
                        </div>
                    </div>
                """, unsafe_allow_html=True)

        # --- SZCZEGÓŁY ---
        st.divider()
        for d in data_list:
            st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 2])
            with c1:
                st.markdown(f"### {d['symbol']}")
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.markdown(f"**BID:** {d['bid']:.2f} | **ASK:** {d['ask']:.2f}")
                st.markdown(f"**iTrend:** {d['itrend_dir']} ({d['itrend_val']:.2f})")
                st.write(f"RSI: {d['rsi']:.1f} | Trend: {d['trend']}")
                
                if st.button(f"🧠 ANALIZA AI", key=f"btn_{d['symbol']}"):
                    prompt = f"Token: {d['symbol']}, Cena: {d['price']}, iTrend: {d['itrend_dir']}, Świeca 15m: {d['p15']}, Świeca 1h: {d['p1h']}. Krótki werdykt."
                    resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                    st.info(resp.choices[0].message.content) # Poprawione odwołanie
            
            with c2:
                st.markdown(f"<div class='candle-analysis'>Wykres 15m (Ostatnia: {d['p15']})</div>", unsafe_allow_html=True)
                f15 = go.Figure(data=[go.Candlestick(x=d['df15'].index[-40:], open=d['df15']['Open'][-40:], high=d['df15']['High'][-40:], low=d['df15']['Low'][-40:], close=d['df15']['Close'][-40:])])
                f15.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(f15, use_container_width=True)

            with c3:
                st.markdown(f"<div class='candle-analysis'>Wykres 1h (Ostatnia: {d['p1h']})</div>", unsafe_allow_html=True)
                f1h = go.Figure(data=[go.Candlestick(x=d['df1h'].index[-40:], open=d['df1h']['Open'][-40:], high=d['df1h']['High'][-40:], low=d['df1h']['Low'][-40:], close=d['df1h']['Close'][-40:])])
                f1h.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(f1h, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Wprowadź OpenAI API Key.")
