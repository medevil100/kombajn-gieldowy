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
st.set_page_config(page_title="AI ALPHA PRO v14.0", page_icon="🏦", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "BTC-USD, ETH-USD, NVDA, TSLA, PKO.WA, ALE.WA"
    return "BTC-USD, ETH-USD, NVDA, TSLA, PKO.WA, ALE.WA"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #0d1117; padding: 10px; border-radius: 10px; border: 1px solid #30363d; text-align: center; min-height: 140px; }
    .pattern-badge { background: #1f6feb; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; }
    .orderbook-box { background: #010409; padding: 10px; border-radius: 8px; border: 1px solid #30363d; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIKA ANALITYCZNA ---
def get_data(symbol):
    try:
        t_obj = yf.Ticker(symbol)
        inf = t_obj.info
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if d15.empty or d1d.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        prev_close = float(d1d['Close'].iloc[-2])
        change = ((price - prev_close) / prev_close) * 100
        
        # Bid/Ask/Spread
        bid = inf.get('bid', 0) or 0
        ask = inf.get('ask', 0) or 0
        spread = ask - bid if (ask > 0 and bid > 0) else 0
        spread_pct = (spread / bid * 100) if bid > 0 else 0

        # Wskaźniki
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        delta = d15['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        pivot = (d1d['High'].iloc[-2] + d1d['Low'].iloc[-2] + d1d['Close'].iloc[-2]) / 3
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]

        return {
            "symbol": symbol, "price": price, "change": change, "rsi": rsi, 
            "bid": bid, "ask": ask, "spread": spread, "spread_pct": spread_pct,
            "trend": "HOSSA 🚀" if price > sma200 else "BESSA 📉",
            "pivot": pivot, "tp": price + (atr * 1.5), "sl": price - (atr * 1.2), "df": d15
        }
    except: return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ PRO v14.0")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. EXECUTION ---
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, tickers)) if r]

if data_list:
    # --- TOP 10 DASHBOARD ---
    st.subheader("📊 MARKET PULSE (TOP 10 RSI)")
    top_cols = st.columns(5)
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            c_col = "#00ff88" if d['change'] >= 0 else "#ff4b4b"
            st.markdown(f"""
                <div class="top-rank-card" style="border-top: 3px solid {c_col};">
                    <b>{d['symbol']}</b><br>
                    <span style="color:{c_col}; font-size:1.1rem;">{d['price']:.2f}</span><br>
                    <small>RSI: {d['rsi']:.1f}</small><br>
                    <small style="color:#8b949e;">S: {d['spread_pct']:.3f}%</small>
                </div>
            """, unsafe_allow_html=True)

    # --- LISTA SZCZEGÓŁOWA ---
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader(d['symbol'])
            st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            # Spread i Arkusz
            st.markdown(f"""
                <div class="orderbook-box">
                    <table style="width:100%;">
                        <tr><td style="color:#00ff88;">BID: {d['bid']:.2f}</td><td style="color:#ff4b4b; text-align:right;">ASK: {d['ask']:.2f}</td></tr>
                        <tr><td colspan="2" style="text-align:center; border-top:1px solid #333; font-size:0.8rem; color:#8b949e;">
                        SPREAD: {d['spread']:.4f} ({d['spread_pct']:.3f}%)</td></tr>
                    </table>
                </div>
            """, unsafe_allow_html=True)
            
            st.write(f"**RSI:** {d['rsi']:.1f} | **Trend:** {d['trend']}")
            st.write(f"🎯 **TP:** {d['tp']:.2f} | 🛡️ **SL:** {d['sl']:.2f}")

            if api_key and st.button(f"🧠 ANALIZA PRO: {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = (f"Jesteś starszym traderem. Przeanalizuj: {d['symbol']}. Dane: Cena={d['price']}, "
                          f"RSI={d['rsi']:.1f}, Spread={d['spread_pct']:.3f}%, Trend={d['trend']}, Pivot={d['pivot']:.2f}. "
                          f"ZAKAZ pisania 'potrzeba więcej danych'. Podaj: 1. Werdykt (KUP/SPRZEDAJ/CZEKAJ), "
                          f"2. Punkt wejścia, 3. Ryzyko 1-10. Bądź konkretny i agresywny.")
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.info(resp.choices[0].message.content)

        with c2:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:]))
            fig.add_hline(y=d['pivot'], line_dash="dot", line_color="orange")
            fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.error("Błąd pobierania danych. Sprawdź symbole lub połączenie.")
