import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.2", page_icon="🚀", layout="wide")

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
    .top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .candle-analysis { font-size: 0.85rem; color: #58a6ff; font-style: italic; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNKCJE ANALITYCZNE ---
def get_candle_pattern(df):
    """Prosta analiza ostatniej świecy"""
    if len(df) < 2: return "Brak danych"
    last = df.iloc[-1]
    body = last['Close'] - last['Open']
    wick_top = last['High'] - max(last['Open'], last['Close'])
    wick_bot = min(last['Open'], last['Close']) - last['Low']
    
    if body > 0 and wick_top > abs(body) * 2: return "Spadająca Gwiazda (Słabość)"
    if body < 0 and wick_bot > abs(body) * 2: return "Młot (Odbicie)"
    if abs(body) < (last['High'] - last['Low']) * 0.1: return "Doji (Niezdecydowanie)"
    return "Trend kontynuowany" if body > 0 else "Presja podaży"

def calculate_itrend(df, period=20):
    """Wskaźnik iTrend (uproszczony jako Momentum vs EMA)"""
    ema = df['Close'].ewm(span=period).mean()
    itrend = df['Close'] - ema
    return itrend.iloc[-1], "BULL" if itrend.iloc[-1] > 0 else "BEAR"

# --- 4. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieranie danych dla różnych interwałów
        d15 = yf.download(symbol, period="2d", interval="15m", progress=False)
        d1h = yf.download(symbol, period="5d", interval="1h", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        ticker_info = yf.Ticker(symbol).info

        if d15.empty or d1h.empty: return None
        
        for df in [d15, d1h, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # Bid / Ask / Price
        price = float(d15['Close'].iloc[-1])
        bid = ticker_info.get('bid', price)
        ask = ticker_info.get('ask', price)
        if bid == 0 or bid is None: bid = price * 0.9998
        if ask == 0 or ask is None: ask = price * 1.0002

        # Analiza świec
        pattern_15m = get_candle_pattern(d15)
        pattern_1h = get_candle_pattern(d1h)
        
        # iTrend
        itrend_val, itrend_dir = calculate_itrend(d1h)
        
        # Reszta statystyk
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        
        # RSI
        delta = d1h['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "change": change_pct, 
            "rsi": rsi, "trend": trend_label, "itrend": itrend_val, "itrend_dir": itrend_dir,
            "p15m": pattern_15m, "p1h": pattern_1h, "df15": d15, "df1h": d1h
        }
    except Exception as e:
        return None

# --- 5. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ ALPHA v12.2")
    if "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
        st.success("✅ Klucz aktywowany")
    else:
        api_key = st.text_input("OpenAI Key", type="password")

    tickers_input = st.text_area("Lista tickerów", value=load_tickers())
    if st.button("Zaktualizuj bazę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    
    refresh = st.select_slider("Auto-odświeżanie", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 6. GŁÓWNA LOGIKA ---
if api_key:
    client = OpenAI(api_key=api_key)
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    
    for t in tickers:
        d = get_analysis(t)
        if d:
            st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.5, 2, 2])
            
            with c1:
                st.subheader(f"{d['symbol']}")
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.markdown(f"**BID:** `{d['bid']:.2f}` | **ASK:** `{d['ask']:.2f}`")
                st.markdown(f"**iTrend:** <span style='color:{'#00ff88' if d['itrend_dir']=='BULL' else '#ff4b4b'}'>{d['itrend_dir']} ({d['itrend']:.4f})</span>", unsafe_allow_html=True)
                st.write(f"**RSI (1h):** {d['rsi']:.1f}")
                
                if st.button(f"🧠 ANALIZA AI {d['symbol']}", key=f"ai_{d['symbol']}"):
                    prompt = f"Analiza {d['symbol']}: Cena {d['price']}, Bid/Ask {d['bid']}/{d['ask']}, iTrend {d['itrend_dir']}, Świeca 15m: {d['p15m']}, Świeca 1h: {d['p1h']}. Daj krótki werdykt."
                    resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                    st.info(resp.choices[0].message.content)

            with c2:
                st.markdown(f"<p class='candle-analysis'>🕯️ Analiza 15m: {d['p15m']}</p>", unsafe_allow_html=True)
                fig15 = go.Figure(data=[go.Candlestick(x=d['df15'].index[-30:], open=d['df15']['Open'][-30:], high=d['df15']['High'][-30:], low=d['df15']['Low'][-30:], close=d['df15']['Close'][-30:])])
                fig15.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig15, use_container_width=True)

            with c3:
                st.markdown(f"<p class='candle-analysis'>⌛ Analiza 1h: {d['p1h']}</p>", unsafe_allow_html=True)
                fig1h = go.Figure(data=[go.Candlestick(x=d['df1h'].index[-30:], open=d['df1h']['Open'][-30:], high=d['df1h']['High'][-30:], low=d['df1h']['Low'][-30:], close=d['df1h']['Close'][-30:])])
                fig1h.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig1h, use_container_width=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Podaj API Key w sidebarze.")
