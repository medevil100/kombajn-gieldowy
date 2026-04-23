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
st.set_page_config(page_title="AI ALPHA ULTRA v15.0", page_icon="📈", layout="wide")

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
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 25px; position: relative; }
    .top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
    .analysis-box { background: #010409; padding: 15px; border-left: 4px solid #1f6feb; border-radius: 5px; margin: 10px 0; font-size: 0.9rem; line-height: 1.5; color: #e6edf3; }
    .metric-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    .metric-table td { padding: 5px; border-bottom: 1px solid #21262d; font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALITYCZNY ---
def get_detailed_data(symbol):
    try:
        t_obj = yf.Ticker(symbol)
        inf = t_obj.info
        d1d = yf.download(symbol, period="2y", interval="1d", progress=False)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        
        if d15.empty or d1d.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        
        # Średnie i Ekstrema
        sma20 = d1d['Close'].rolling(20).mean().iloc[-1]
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        peak_52w = d1d['High'].max()
        bottom_52w = d1d['Low'].min()
        
        # Spread i RSI
        bid, ask = inf.get('bid', 0.0) or 0.0, inf.get('ask', 0.0) or 0.0
        spread_pct = ((ask - bid) / bid * 100) if bid > 0 else 0.0
        
        delta = d15['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma20": sma20, "sma200": sma200,
            "peak": peak_52w, "bottom": bottom_52w, "spread_pct": spread_pct,
            "bid": bid, "ask": ask, "tp": price + (atr * 2), "sl": price - (atr * 1.5),
            "df": d15, "change": ((price - d1d['Close'].iloc[-2]) / d1d['Close'].iloc[-2] * 100)
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("⚡ v15.0 ULTRA")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_detailed_data, tickers_list)) if r]

if data_list:
    # --- TOP 10 DASHBOARD ---
    st.subheader("🔥 TOP 10 - ACTIVE MONITOR")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            color = "#00ff88" if d['change'] >= 0 else "#ff4b4b"
            st.markdown(f"""<div class="top-rank-card" style="border-bottom: 3px solid {color};">
                <b>{d['symbol']}</b><br><span style="color:{color}; font-size:1.2rem;">{d['price']:.2f}</span><br>
                <small>RSI: {d['rsi']:.1f} | S: {d['spread_pct']:.2f}%</small></div>""", unsafe_allow_html=True)

    # --- LISTA SZCZEGÓŁOWA ---
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader(f"📊 {d['symbol']}")
            st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            # Tabela Parametrów (wszystko w jednym miejscu)
            st.markdown(f"""
                <table class="metric-table">
                    <tr><td>SMA20 / SMA200</td><td style="text-align:right;">{d['sma20']:.2f} / {d['sma200']:.2f}</td></tr>
                    <tr><td>Szczyt / Dołek (52w)</td><td style="text-align:right;">{d['peak']:.2f} / {d['bottom']:.2f}</td></tr>
                    <tr><td>BID / ASK</td><td style="text-align:right; color:#8b949e;">{d['bid']:.2f} / {d['ask']:.2f}</td></tr>
                    <tr><td>Spread / RSI</td><td style="text-align:right;">{d['spread_pct']:.3f}% / {d['rsi']:.1f}</td></tr>
                    <tr><td style="color:#00ff88;"><b>Target (TP)</b></td><td style="text-align:right; color:#00ff88;"><b>{d['tp']:.2f}</b></td></tr>
                    <tr><td style="color:#ff4b4b;"><b>Stop Loss (SL)</b></td><td style="text-align:right; color:#ff4b4b;"><b>{d['sl']:.2f}</b></td></tr>
                </table>
            """, unsafe_allow_html=True)

            # Analiza AI (teraz widoczna na stałe po kliknięciu)
            if api_key and st.button(f"🧠 AI DEEP SCAN: {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = (f"Analiza PRO: {d['symbol']}. Cena: {d['price']}, SMA20: {d['sma20']:.2f}, SMA200: {d['sma200']:.2f}, "
                          f"Szczyt: {d['peak']:.2f}, Dołek: {d['bottom']:.2f}, RSI: {d['rsi']:.1f}, Spread: {d['spread_pct']:.3f}%. "
                          f"Wyznacz trend względem SMA200. Określ czy cena jest blisko dołka czy szczytu. "
                          f"Podaj bezwzględny werdykt KUP/SPRZEDAJ/CZEKAJ i ryzyko.")
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"res_{d['symbol']}"] = resp.choices[0].message.content
            
            if f"res_{d['symbol']}" in st.session_state:
                st.markdown(f'<div class="analysis-box">{st.session_state[f"res_{d['symbol']}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:]))
            fig.add_hline(y=d['sma200'], line_color="red", line_dash="dash", annotation_text="SMA200")
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
