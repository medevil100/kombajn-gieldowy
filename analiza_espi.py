import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I WYGLĄD ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA KOMBAJN v17.0", page_icon="🚜", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #1c2128; padding: 15px; border-radius: 10px; border: 1px solid #444c56; text-align: center; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .verdict-badge { padding: 5px 15px; border-radius: 20px; font-weight: bold; text-transform: uppercase; font-size: 0.8rem; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.95rem; }
    .trend-up { color: #00ff88; font-weight: bold; }
    .trend-down { color: #ff4b4b; font-weight: bold; }
    .bid-ask { font-family: monospace; color: #58a6ff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK DANYCH ---
def get_data(symbol):
    try:
        t = yf.Ticker(symbol)
        d1h = t.history(period="10d", interval="1h")
        d1d = t.history(period="2y", interval="1d")
        
        if d1h.empty or d1d.empty: return None

        # Naprawa MultiIndex
        if isinstance(d1h.columns, pd.MultiIndex): d1h.columns = d1h.columns.get_level_values(0)
        
        price = d1h['Close'].iloc[-1]
        
        # Obliczenia techniczne
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        sma50 = d1d['Close'].rolling(50).mean().iloc[-1]
        
        # Pivot Points
        h_p, l_p, c_p = d1d['High'].iloc[-2], d1d['Low'].iloc[-2], d1d['Close'].iloc[-2]
        pp = (h_p + l_p + c_p) / 3
        r1 = (2 * pp) - l_p
        s1 = (2 * pp) - h_p
        
        # RSI 1h
        delta = d1h['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR / TP / SL
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "pp": pp, "r1": r1, "s1": s1,
            "sma200": sma200, "sma50": sma50, "tp": price + (atr * 1.8), "sl": price - (atr * 1.2),
            "trend_mid": "WZROSTOWY" if price > sma50 else "SPADKOWY",
            "trend_long": "WZROSTOWY" if price > sma200 else "SPADKOWY",
            "df": d1h, "change": ((price - c_p) / c_p * 100)
        }
    except: return None

# --- 3. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 KOMBAJN v17.0")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli", "PKO.WA, BCS.WA, STX.WA, BTC-USD, NVDA", height=150)
    refresh = st.slider("Odśwież (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="refresh")

# --- 4. LOGIKA GŁÓWNA ---
t_list = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor() as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    # --- TOP 10 RANKING ---
    st.subheader("🔥 TOP SYGNAŁY (RSI 1H)")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    t_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with t_cols[i % 5]:
            v, c = ("KUP", "v-buy") if d['rsi'] < 32 else ("SPRZEDAŃ", "v-sell") if d['rsi'] > 68 else ("CZEKAJ", "v-wait")
            st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b>{d["price"]:.2f}</b><br><span class="verdict-badge {c}">{v}</span></div>', unsafe_allow_html=True)

    st.divider()

    # --- KARTY SZCZEGÓŁOWE ---
    for d in data_list:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.2, 2, 1.2])
        
        with c1:
            st.subheader(d['symbol'])
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"<div class='bid-ask'>BID: {d['price']*0.9999:.2f} | ASK: {d['price']*1.0001:.2f}</div>", unsafe_allow_html=True)
            
            tm_cl = "trend-up" if d['trend_mid'] == "WZROSTOWY" else "trend-down"
            tl_cl = "trend-up" if d['trend_long'] == "WZROSTOWY" else "trend-down"
            
            st.markdown(f"""
                <div class="metric-row"><span>Trend Średni</span><span class="{tm_cl}">{d['trend_mid']}</span></div>
                <div class="metric-row"><span>Trend Długi</span><span class="{tl_cl}">{d['trend_long']}</span></div>
                <div class="metric-row"><span>RSI (1h)</span><b>{d['rsi']:.1f}</b></div>
                <div class="metric-row"><span>Pivot Point</span><b style="color:orange;">{d['pp']:.2f}</b></div>
                <div class="metric-row"><span>Opór R1</span><b>{d['r1']:.2f}</b></div>
                <div class="metric-row"><b style="color:#00ff88;">TARGET (TP)</b><b>{d['tp']:.2f}</b></div>
                <div class="metric-row"><b style="color:#ff4b4b;">STOP (SL)</b><b>{d['sl']:.2f}</b></div>
            """, unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-50:], open=d['df']['Open'][-50:], high=d['df']['High'][-50:], low=d['df']['Low'][-50:], close=d['df']['Close'][-50:])])
            fig.add_hline(y=d['pp'], line_dash="dash", line_color="orange", annotation_text="PIVOT")
            fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with c3:
            st.write("🤖 **STRATEGIA AI**")
            if api_key and st.button(f"Skanuj {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": f"Analiza {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['pp']:.2f}. Werdykt?"}]
                )
                st.info(resp.choices[0].message.content) # Poprawione pobieranie treści
        st.markdown('</div>', unsafe_allow_html=True)
