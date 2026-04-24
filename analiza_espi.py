import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA UI ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA GOLDEN v16.5", page_icon="🍯", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .verdict-badge { padding: 5px 15px; border-radius: 20px; font-weight: bold; text-transform: uppercase; font-size: 0.8rem; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    .trend-up { color: #238636; font-weight: bold; }
    .trend-down { color: #da3633; font-weight: bold; }
    .candle-signal { color: #f1c40f; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"
    return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"

# --- 2. SILNIK ANALIZY TECHNICZNEJ (Świece + Wskaźniki) ---
def analyze_candles(df):
    if len(df) < 3: return "Brak wyraźnej formacji"
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = abs(last['Close'] - last['Open'])
    upper_wick = last['High'] - max(last['Open'], last['Close'])
    lower_wick = min(last['Open'], last['Close']) - last['Low']
    
    if lower_wick > (2 * body) and upper_wick < (0.5 * body) and body > 0: return "🔨 MŁOT (Odbicie?)"
    if last['Close'] > prev['Open'] and last['Open'] < prev['Close'] and prev['Close'] < prev['Open']: return "🟢 OBJĘCIE HOSSY"
    if last['Close'] < prev['Open'] and last['Open'] > prev['Close'] and prev['Close'] > prev['Open']: return "🔴 OBJĘCIE BESSY"
    if upper_wick > (2 * body) and lower_wick < (0.5 * body) and body > 0: return "☄️ SPADAJĄCA GWIAZDA"
    return "Brak wyraźnej formacji"

def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        d_long = ticker.history(period="2y", interval="1d")
        d15 = ticker.history(period="5d", interval="15m")
        if d15.empty or d_long.empty: return None

        price = d15['Close'].iloc[-1]
        info = ticker.info
        bid, ask = info.get('bid', price), info.get('ask', price)

        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        sma50 = d_long['Close'].rolling(50).mean().iloc[-1]
        trend_long = "WZROSTOWY" if price > sma200 else "SPADKOWY"
        trend_mid = "WZROSTOWY" if sma50 > sma200 else "SPADKOWY"

        h_p, l_p, c_p = d_long['High'].iloc[-2], d_long['Low'].iloc[-2], d_long['Close'].iloc[-2]
        pivot = (h_p + l_p + c_p) / 3
        
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        atr = (d_long['High'] - d_long['Low']).rolling(14).mean().iloc[-1]
        candle_signal = analyze_candles(d15)

        v_class = "v-buy" if rsi < 32 else "v-sell" if rsi > 68 else "v-wait"
        verdict = "KUP" if rsi < 32 else "SPRZEDAJ" if rsi > 68 else "CZEKAJ"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "sma200": sma200, "sma50": sma50, "pivot": pivot, "candle": candle_signal,
            "verdict": verdict, "v_class": v_class, "change": ((price - c_p)/c_p)*100,
            "trend_long": trend_long, "trend_mid": trend_mid,
            "tp": price + (atr * 2), "sl": price - (atr * 1.5), "df": d15
        }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 ALPHA GOLDEN v16.5")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana!")
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)
st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 4. GŁÓWNY PANEL ---
t_list = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    st.subheader("🔥 EKSTREMALNE RSI (OKAZJE)")
    top_cols = st.columns(5)
    for i, d in enumerate(sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:5]):
        with top_cols[i]:
            st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b>{d["price"]:.2f}</b><br><span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span></div>', unsafe_allow_html=True)

    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"## {d['symbol']} <span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            t_mid_c = "trend-up" if d['trend_mid'] == "WZROSTOWY" else "trend-down"
            st.markdown(f"""
                <div class="metric-row"><span>Trend Średni</span><span class="{t_mid_c}">{d['trend_mid']}</span></div>
                <div class="metric-row"><span>Analiza Świec</span><span class="candle-signal">{d['candle']}</span></div>
                <div class="metric-row"><span>RSI (14d)</span><b>{d['rsi']:.1f}</b></div>
                <div class="metric-row"><span>Sugerowane TP / SL</span><b style="color:#f1c40f;">{d['tp']:.2f} / {d['sl']:.2f}</b></div>
            """, unsafe_allow_html=True)
            
            if api_key:
                if st.button(f"🚀 DECYZJA AI: {d['symbol']}", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = f"Ticker: {d['symbol']}. Cena: {d['price']}. RSI: {d['rsi']:.1f}. Trend: {d['trend_long']}. Swiece: {d['candle']}. Nie lej wody. Odpowiedz w 3 punktach: 1. DECYZJA (KUP/SPRZEDAJ/CZEKAJ), 2. WEJSCIE/TP/SL (liczby), 3. POWOD (1 zdanie)."
                    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś suchym analitykiem. Tylko konkrety."}, {"role": "user", "content": prompt}])
                    st.info(res.choices.message.content)
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(height=300, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
