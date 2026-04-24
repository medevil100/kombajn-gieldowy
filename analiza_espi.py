import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA I STYLE ---
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v16", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #1c2128; padding: 15px; border-radius: 10px; border: 1px solid #444c56; text-align: center; border-top: 3px solid #58a6ff; }
    .bid-ask { font-family: monospace; color: #58a6ff; font-weight: bold; font-size: 1rem; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK ANALIZY (Z FILTREM MULTIINDEX) ---
def get_full_analysis(symbol):
    try:
        # Dane 1h (interwał świec) oraz 1d (Pivot/Trend/ATR)
        h1 = yf.download(symbol, period="10d", interval="1h", progress=False)
        d1 = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if h1.empty or d1.empty: return None
        
        # FILTR: Naprawa dzisiejszych błędów Yahoo Finance
        for df in [h1, d1]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        
        price = float(h1['Close'].iloc[-1])
        bid, ask = price * 0.9999, price * 1.0001
        
        # Wskaźniki
        rsi = 100 - (100 / (1 + (h1['Close'].diff().where(lambda x: x > 0, 0).rolling(14).mean() / 
                                 h1['Close'].diff().where(lambda x: x < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        # Trend i Pivot Points
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        trend = "Wzrostowy 🚀" if price > sma200 else "Spadkowy 📉"
        
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        r1, s1 = (2 * pp) - lp, (2 * pp) - hp
        
        # ATR dla TP/SL
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp, sl = price + (atr * 1.5), price - (atr * 1.2)

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, 
            "rsi": rsi, "pp": pp, "r1": r1, "s1": s1, "tp": tp, "sl": sl,
            "trend": trend, "df": h1, "change": ((price - cp) / cp) * 100
        }
    except: return None

# --- 3. UI SIDEBAR ---
with st.sidebar:
    st.title("🚀 KOMB_v16")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    input_tickers = st.text_area("Symbole (przecinek)", "LBW.WA, BCS.WA, PLRX, BTC-USD, NVDA, STX.WA")
    refresh = st.select_slider("Odświeżanie (s)", options=, value=60)

st_autorefresh(interval=refresh * 1000, key="auto_refresh")

# --- 4. GŁÓWNA LOGIKA ---
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
results = [get_full_analysis(t) for t in tickers if get_full_analysis(t)]

if results:
    # --- RANKING TOP 10 (SKANER RSI) ---
    st.subheader("🔥 TOP 10 - EKSTREMALNE RSI (OKAZJE)")
    sorted_top = sorted(results, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            rec = "KUPUJ" if d['rsi'] < 35 else "SPRZEDAJ" if d['rsi'] > 65 else "CZEKAJ"
            st.markdown(f"""
                <div class="top-rank-card">
                    <b style="font-size:1.1rem;">{d['symbol']}</b><br>
                    <span style="color:#00ff88;">{d['price']:.2f}</span><br>
                    <span class="stat-label">RSI: {d['rsi']:.1f}</span><br>
                    <b>{rec}</b>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in results:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                st.subheader(d['symbol'])
                st.markdown(f"<div class='bid-ask'>BID: {d['bid']:.4f}<br>ASK: {d['ask']:.4f}</div>", unsafe_allow_html=True)
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**Trend:** {d['trend']}")
                st.write(f"**Pivot:** {d['pp']:.2f}")
                st.write(f"**Target TP:** {d['tp']:.2f}")
                st.write(f"**Stop SL:** {d['sl']:.2f}")
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.add_hline(y=d['pp'], line_dash="dash", line_color="orange", annotation_text="P")
                fig.add_hline(y=d['r1'], line_dash="dot", line_color="red", annotation_text="R1")
                fig.add_hline(y=d['s1'], line_dash="dot", line_color="green", annotation_text="S1")
                fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            with c3:
                st.write("🤖 **ANALIZA GPT-4**")
                if api_key and st.button(f"Skanuj {d['symbol']}", key=f"btn_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = f"Jako trader oceń: {d['symbol']}, Cena: {d['price']}, RSI: {d['rsi']:.1f}, Pivot: {d['pp']:.2f}, Trend: {d['trend']}. Krótki konkret."
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Podaj symbole i klucz API.")
