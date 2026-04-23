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
st.set_page_config(page_title="AI ALPHA GOLDEN v16.0", page_icon="🍯", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "STX.WA, PKO.WA, NVDA, TSLA, BTC-USD"
    return "STX.WA, PKO.WA, NVDA, TSLA, BTC-USD"

# --- 2. STYLE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 25px; }
    .sl-alert { border: 2px solid #ff4b4b !important; background: #2d1616 !important; }
    .verdict-badge { padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; text-transform: uppercase; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .analysis-box { background: #070a0e; padding: 15px; border-left: 5px solid #f1c40f; border-radius: 5px; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_golden_data(symbol):
    try:
        t_obj = yf.Ticker(symbol)
        inf = t_obj.info
        d1d = yf.download(symbol, period="2y", interval="1d", progress=False)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        
        if d15.empty or d1d.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        
        # PIVOT
        pivot = (d1d['High'].iloc[-2] + d1d['Low'].iloc[-2] + d1d['Close'].iloc[-2]) / 3
        
        # RSI
        delta = d15['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # SZYBKI WERDYKT (Kropla miodu)
        if rsi < 30: verdict, v_class = "KUP", "v-buy"
        elif rsi > 70: verdict, v_class = "SPRZEDAJ", "v-sell"
        else: verdict, v_class = "CZEKAJ", "v-wait"

        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        bid = inf.get('bid', 0.0) or 0.0
        ask = inf.get('ask', 0.0) or 0.0

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma200": sma200, "pivot": pivot,
            "verdict": verdict, "v_class": v_class, "bid": bid, "ask": ask,
            "spread_pct": ((ask-bid)/bid*100 if bid>0 else 0),
            "tp": price + (atr * 2), "sl": price - (atr * 1.5),
            "df": d15, "change": ((price - d1d['Close'].iloc[-2]) / d1d['Close'].iloc[-2] * 100)
        }
    except: return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.0 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. LOGIKA ---
tickers_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_golden_data, tickers_list)) if r]

if data_list:
    # --- TOP 10 ---
    st.subheader("🍯 SYGNAŁY DNIA (TOP 10)")
    t_cols = st.columns(min(len(data_list), 5))
    for i, d in enumerate(data_list[:10]):
        with t_cols[i % 5]:
            st.markdown(f"""<div style="background:#0d1117; padding:10px; border-radius:10px; border:1px solid #30363d; text-align:center;">
                <small>{d['symbol']}</small><br>
                <span class="verdict-badge {d['v_class']}">{d['verdict']}</span><br>
                <b>{d['price']:.2f}</b>
            </div>""", unsafe_allow_html=True)

    # --- SZCZEGÓŁY ---
    for d in data_list:
        # Alert jeśli cena < SL
        card_style = "sl-alert" if d['price'] <= d['sl'] else ""
        st.markdown(f'<div class="ticker-card {card_style}">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"### {d['symbol']} <span class="f'verdict-badge {d["v_class"]}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            st.markdown(f"""<table style="width:100%; font-size:0.85rem;">
                <tr><td>Pivot (Orange)</td><td style="text-align:right;">{d['pivot']:.2f}</td></tr>
                <tr><td>SMA200 (Red)</td><td style="text-align:right;">{d['sma200']:.2f}</td></tr>
                <tr><td>Spread / RSI</td><td style="text-align:right;">{d['spread_pct']:.3f}% / {d['rsi']:.1f}</td></tr>
                <tr style="color:#00ff88;"><td><b>TARGET (TP)</b></td><td style="text-align:right;"><b>{d['tp']:.2f}</b></td></tr>
                <tr style="color:#ff4b4b;"><td><b>STOP LOSS (SL)</b></td><td style="text-align:right;"><b>{d['sl']:.2f}</b></td></tr>
            </table>""", unsafe_allow_html=True)

            if api_key and st.button(f"🧠 ANALIZA EXPERT: {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = (f"Werdykt dla {d['symbol']}. Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['pivot']:.2f}, Trend {d['sma200']:.2f}. "
                          f"Bądź agresywny. Podaj: 1. WERDYKT, 2. CENA WEJŚCIA, 3. POTENCJAŁ ZYSKU %. Nie pisz o 'obserwacji'.")
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"res_{d['symbol']}"] = resp.choices.message.content
            
            if f"res_{d['symbol']}" in st.session_state:
                st.markdown(f'<div class="analysis-box">{st.session_state[f"res_{d['symbol']}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:]))
            fig.add_hline(y=d['pivot'], line_color="orange", line_dash="dot", annotation_text="PIVOT")
            fig.add_hline(y=d['sma200'], line_color="red", line_dash="dash", annotation_text="SMA200")
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
