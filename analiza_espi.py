import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I STYLE ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA GOLDEN v16.6", page_icon="🍯", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, STX.WA, NVDA, BTC-USD"
    return "PKO.WA, STX.WA, NVDA, BTC-USD"

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
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK DANYCH (Bid/Ask, Pivot, Trend) ---
def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        d_long = ticker.history(period="2y", interval="1d")
        d1h = ticker.history(period="10d", interval="1h")
        
        if d1h.empty or d_long.empty: return None
        
        # Prostowanie MultiIndex (Naprawa czarnego ekranu)
        if isinstance(d1h.columns, pd.MultiIndex): d1h.columns = d1h.columns.get_level_values(0)
        
        price = d1h['Close'].iloc[-1]
        
        # Bid / Ask (Symulacja spreadu 0.02% dla płynności)
        bid, ask = price * 0.9999, price * 1.0001
        
        # Trendy
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        sma50 = d_long['Close'].rolling(50).mean().iloc[-1]
        t_long = "WZROSTOWY 🚀" if price > sma200 else "SPADKOWY 📉"
        t_mid = "WZROSTOWY 🚀" if price > sma50 else "SPADKOWY 📉"
        
        # Pivot Point (z wczoraj)
        h_p, l_p, c_p = d_long['High'].iloc[-2], d_long['Low'].iloc[-2], d_long['Close'].iloc[-2]
        pivot = (h_p + l_p + c_p) / 3
        
        # RSI 1h
        delta = d1h['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR dla TP/SL
        atr = (d_long['High'] - d_long['Low']).rolling(14).mean().iloc[-1]
        
        verdict, v_class = ("KUP", "v-buy") if rsi < 32 else ("SPRZEDAJ", "v-sell") if rsi > 68 else ("CZEKAJ", "v-wait")
        
        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "pivot": pivot, "verdict": verdict, "v_class": v_class,
            "change": ((price - c_p) / c_p * 100), "trend_long": t_long, "trend_mid": t_mid,
            "tp": price + (atr * 1.8), "sl": price - (atr * 1.2), "df": d1h
        }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.6 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Zapisano!")
    refresh = st.select_slider("Odśwież (s)", options=, value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 4. GŁÓWNA LOGIKA ---
t_list = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor() as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    # TOP 10 KAFELKI
    st.subheader("🔥 TOP SYGNAŁY (RSI 1H)")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with cols[i % 5]:
            st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b>{d["price"]:.2f}</b><br><span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span></div><br>', unsafe_allow_html=True)

    # SZCZEGÓŁOWE KARTY
    for d in data_list:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1.2, 2])
        with c1:
            st.markdown(f"## {d['symbol']} <span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.markdown(f"<div style='color:#58a6ff; font-family:monospace;'>B: {d['bid']:.2f} | A: {d['ask']:.2f}</div>", unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            st.markdown(f"""
                <div class="metric-row"><span>Trend Średni</span><span class="{'trend-up' if 'WZROST' in d['trend_mid'] else 'trend-down'}">{d['trend_mid']}</span></div>
                <div class="metric-row"><span>Trend Długi</span><span class="{'trend-up' if 'WZROST' in d['trend_long'] else 'trend-down'}">{d['trend_long']}</span></div>
                <div class="metric-row"><span>RSI (1h)</span><b>{d['rsi']:.1f}</b></div>
                <div class="metric-row"><span>Pivot Point</span><b style="color:orange;">{d['pivot']:.2f}</b></div>
                <div class="metric-row"><b style="color:#00ff88;">TARGET (TP)</b><b>{d['tp']:.2f}</b></div>
                <div class="metric-row"><b style="color:#ff4b4b;">STOP (SL)</b><b>{d['sl']:.2f}</b></div>
            """, unsafe_allow_html=True)
            
            if api_key and st.button(f"🧠 ANALIZA AI {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": f"Oceń {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}. Krótko!"}]
                )
                st.info(resp.choices[0].message.content) # NAPRAWIONY BŁĄD AI
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:])])
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
