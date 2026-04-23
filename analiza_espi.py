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
st.set_page_config(page_title="AI ALPHA ELITE v15.5", page_icon="💎", layout="wide")

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
    .analysis-box { background: #070a0e; padding: 15px; border-left: 5px solid #ff4b4b; border-radius: 5px; margin: 10px 0; font-family: 'Courier New', monospace; }
    .metric-table { width: 100%; margin-top: 10px; border-spacing: 0 5px; border-collapse: separate; }
    .metric-table td { padding: 8px; background: #21262d; font-size: 0.85rem; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALITYCZNY ---
def get_elite_data(symbol):
    try:
        t_obj = yf.Ticker(symbol)
        inf = t_obj.info
        d1d = yf.download(symbol, period="2y", interval="1d", progress=False)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        
        if d15.empty or d1d.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        sma20 = d1d['Close'].rolling(20).mean().iloc[-1]
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        peak_52w = d1d['High'].max()
        bottom_52w = d1d['Low'].min()
        
        # PIVOT POINT (Standard)
        high_p = d1d['High'].iloc[-2]
        low_p = d1d['Low'].iloc[-2]
        close_p = d1d['Close'].iloc[-2]
        pivot = (high_p + low_p + close_p) / 3
        
        bid = inf.get('bid', 0.0) or 0.0
        ask = inf.get('ask', 0.0) or 0.0
        spread_pct = ((ask - bid) / bid * 100) if bid > 0 else 0.0
        
        delta = d15['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma20": sma20, "sma200": sma200,
            "peak": peak_52w, "bottom": bottom_52w, "spread_pct": spread_pct, "pivot": pivot,
            "bid": bid, "ask": ask, "tp": price + (atr * 2), "sl": price - (atr * 1.5),
            "df": d15, "change": ((price - close_p) / close_p * 100)
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("💎 v15.5 ELITE")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_elite_data, tickers_list)) if r]

if data_list:
    # --- TOP 10 DASHBOARD ---
    st.subheader("🔥 TOP 10 OPPORTUNITIES")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    top_cols = st.columns(min(len(sorted_top), 5))
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            color = "#00ff88" if d['change'] >= 0 else "#ff4b4b"
            st.markdown(f"""<div style="background:#0d1117; padding:10px; border-radius:10px; border:1px solid #30363d; text-align:center;">
                <b>{d['symbol']}</b><br><span style="color:{color}; font-size:1.1rem;">{d['price']:.2f}</span><br>
                <small>RSI: {d['rsi']:.1f}</small></div>""", unsafe_allow_html=True)

    # --- LISTA SZCZEGÓŁOWA ---
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader(f"📊 {d['symbol']}")
            st.metric("AKTUALNA CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            st.markdown(f"""<table class="metric-table">
                <tr><td>SMA200 (Trend)</td><td style="text-align:right;">{d['sma200']:.2f}</td></tr>
                <tr><td>PIVOT POINT</td><td style="text-align:right; color:orange;">{d['pivot']:.2f}</td></tr>
                <tr><td>RSI (15m)</td><td style="text-align:right;">{d['rsi']:.1f}</td></tr>
                <tr><td>SPREAD %</td><td style="text-align:right;">{d['spread_pct']:.3f}%</td></tr>
                <tr><td style="color:#00ff88;">TARGET (TP)</td><td style="text-align:right;">{d['tp']:.2f}</td></tr>
                <tr><td style="color:#ff4b4b;">STOP LOSS (SL)</td><td style="text-align:right;">{d['sl']:.2f}</td></tr>
            </table>""", unsafe_allow_html=True)

            if api_key and st.button(f"🧠 WYGENERUJ WERDYKT: {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = (f"Jesteś bezwzględnym algorytmem handlowym. Asset: {d['symbol']}. Dane: Cena {d['price']}, SMA200 {d['sma200']:.2f}, "
                          f"Pivot {d['pivot']:.2f}, 52w Peak {d['peak']:.2f}, 52w Bottom {d['bottom']:.2f}, RSI {d['rsi']:.1f}. "
                          f"ZAKAZ lania wody. WYMAGANY konkret: 1. WERDYKT (KUP/SPRZEDAJ/CZEKAJ). 2. CENA WEJŚCIA. 3. UZASADNIENIE 1 ZDANIEM. "
                          f"Jeśli trend jest spadkowy i brak sygnału - napisz SPRZEDAJ lub CZEKAJ, nie każ obserwować.")
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"res_{d['symbol']}"] = resp.choices[0].message.content
            
            if f"res_{d['symbol']}" in st.session_state:
                st.markdown(f'<div class="analysis-box"><b>RAPORT AI:</b><br>{st.session_state[f"res_{d['symbol']}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:], name="Cena"))
            fig.add_hline(y=d['pivot'], line_color="orange", line_dash="dot", annotation_text="PIVOT")
            fig.add_hline(y=d['sma200'], line_color="red", line_dash="dash", annotation_text="SMA200")
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

st.caption("AI ALPHA ELITE v15.5 | Pivot & SMA200 Active | Zero-Vague Analysis Mode")
