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
    .analysis-box { background: #070a0e; padding: 15px; border-left: 5px solid #f1c40f; border-radius: 5px; margin-top: 10px; }
    .trend-up { color: #238636; font-weight: bold; }
    .trend-down { color: #da3633; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"
    return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"

# --- 2. SILNIK DANYCH ---
def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        d_long = ticker.history(period="2y", interval="1d")
        d15 = ticker.history(period="5d", interval="15m")
        
        if d15.empty or d_long.empty: return None

        # Fix MultiIndex
        if isinstance(d15.columns, pd.MultiIndex): d15.columns = d15.columns.get_level_values(0)
        if isinstance(d_long.columns, pd.MultiIndex): d_long.columns = d_long.columns.get_level_values(0)

        price = d15['Close'].iloc[-1]
        
        # Bid / Ask simulation
        info = ticker.info
        bid = info.get('bid') or price * 0.9998
        ask = info.get('ask') or price * 1.0002

        # Średnie kroczące
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        sma50 = d_long['Close'].rolling(50).mean().iloc[-1]

        # Logika Trendów
        trend_long = "WZROSTOWY" if price > sma200 else "SPADKOWY"
        trend_mid = "WZROSTOWY" if price > sma50 else "SPADKOWY"

        # Pivot i RSI
        h_p, l_p, c_p = d_long['High'].iloc[-2], d_long['Low'].iloc[-2], d_long['Close'].iloc[-2]
        pivot = (h_p + l_p + c_p) / 3
        
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        atr = (d_long['High'] - d_long['Low']).rolling(14).mean().iloc[-1]
        change = ((price - c_p) / c_p * 100)

        if rsi < 32: verdict, v_class = "KUP", "v-buy"
        elif rsi > 68: verdict, v_class = "SPRZEDAJ", "v-sell"
        else: verdict, v_class = "CZEKAJ", "v-wait"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "sma200": sma200, "sma50": sma50, "pivot": pivot,
            "verdict": verdict, "v_class": v_class, "change": change,
            "trend_long": trend_long, "trend_mid": trend_mid,
            "peak": d_long['High'].max(), "bottom": d_long['Low'].min(),
            "tp": price + (atr * 2), "sl": price - (atr * 1.5), "df": d15
        }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.5 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana!")
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 4. LOGIKA GŁÓWNA ---
t_list = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    st.subheader("🔥 TOP SYGNAŁY")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with cols[i % 5]:
            st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b style="font-size:1.2rem;">{d["price"]:.2f}</b><br><span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span></div><br>', unsafe_allow_html=True)

    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown(f"## {d['symbol']} <span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.markdown(f"""<div style="display: flex; gap: 20px; margin-bottom: 10px;">
                <div style="color:#ff4b4b;">BID: <b>{d['bid']:.2f}</b></div>
                <div style="color:#00ff88;">ASK: <b>{d['ask']:.2f}</b></div></div>""", unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            tm_class = "trend-up" if d['trend_mid'] == "WZROSTOWY" else "trend-down"
            tl_class = "trend-up" if d['trend_long'] == "WZROSTOWY" else "trend-down"
            
            st.markdown(f"""
                <div class="metric-row"><span>Trend SMA50</span><span class="{tm_class}">{d['trend_mid']}</span></div>
                <div class="metric-row"><span>Trend SMA200</span><span class="{tl_class}">{d['trend_long']}</span></div>
                <div class="metric-row"><span>RSI (14d)</span><b>{d['rsi']:.1f}</b></div>
                <div class="metric-row"><span>Pivot Point</span><b style="color:orange;">{d['pivot']:.2f}</b></div>
                <div class="metric-row"><b style="color:#00ff88;">TARGET (TP)</b><b>{d['tp']:.2f}</b></div>
                <div class="metric-row"><b style="color:#ff4b4b;">STOP LOSS (SL)</b><b>{d['sl']:.2f}</b></div>
            """, unsafe_allow_html=True)

            if api_key and st.button(f"🧠 ANALIZA AI {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = f"Analiza {d['symbol']}: Cena {d['price']}, Trend SMA50 {d['trend_mid']}, RSI {d['rsi']:.1f}. Werdykt i plan?"
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"res_{d['symbol']}"] = resp.choices[0].message.content
            
            if f"res_{d['symbol']}" in st.session_state:
                st.markdown(f'<div class="analysis-box"><b>AI STRATEGIA:</b><br>{st.session_state[f"res_{d['symbol']}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
