import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime

# ---------------------------------------------------------
# 1. KONFIGURACJA
# ---------------------------------------------------------
st.set_page_config(page_title="AI ALPHA MONSTER PRO v74", page_icon="🚜", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #010101; color: #e0e0e0; }
    .top-mini-tile { padding: 15px; border-radius: 12px; text-align: center; background: #161b22; border:1px solid #30363d; margin-bottom:15px; }
    .tile-buy { border:2px solid #00ff88!important; }
    .tile-sell { border:2px solid #ff4b4b!important; }
    .stMetric { background: #0d1117; padding: 10px; border-radius: 10px; border: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None
TICKERS_FILE = "moje_spolki.txt"

# ---------------------------------------------------------
# 2. POMOCNICZE FUNKCJE
# ---------------------------------------------------------
def fix_columns(df):
    """Naprawia wielopoziomowe kolumny z yfinance"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (delta.where(delta < 0, 0).abs()).rolling(window=period).mean()
    rs = gain / (loss + 1e-12)
    return 100 - (100 / (1 + rs))

def analyze_symbol(symbol):
    try:
        # Pobieranie danych z naprawą kolumn
        df = yf.download(symbol, period="1y", interval="1d", progress=False)
        if df.empty: return None
        df = fix_columns(df)
        
        close_series = df["Close"].ffill()
        price = float(close_series.iloc[-1])
        rsi_series = compute_rsi(close_series)
        rsi = float(rsi_series.iloc[-1])
        
        score = 50
        if rsi < 35: score += 20
        if rsi > 65: score -= 20
        
        return {"symbol": symbol, "price": price, "rsi": rsi, "score": score, "df": df}
    except Exception as e:
        st.error(f"Błąd przy {symbol}: {e}")
        return None

# ---------------------------------------------------------
# 3. SESSION STATE
# ---------------------------------------------------------
if "tickers_text" not in st.session_state:
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, "r") as f:
            st.session_state.tickers_text = f.read().strip()
    else:
        st.session_state.tickers_text = "NVDA, TSLA, AAPL, BTC-USD"

# ---------------------------------------------------------
# 4. SIDEBAR
# ---------------------------------------------------------
st.sidebar.title("🚜 MONSTER v74 PRO")
refresh_min = st.sidebar.slider("Auto-refresh (min)", 1, 10, 5)
st_autorefresh(interval=refresh_min * 60 * 1000, key="refresh")

st.session_state.risk_cap = st.sidebar.number_input("Kapitał:", value=10000.0)
st.session_state.risk_pct = st.sidebar.slider("Ryzyko %:", 0.1, 5.0, 1.0)

new_tickers = st.sidebar.text_area("Tickery (CSV):", value=st.session_state.tickers_text)
if st.sidebar.button("💾 Zapisz"):
    st.session_state.tickers_text = new_tickers
    with open(TICKERS_FILE, "w") as f: f.write(new_tickers)
    st.rerun()

# ---------------------------------------------------------
# 5. DASHBOARD
# ---------------------------------------------------------
st.title("AI ALPHA MONSTER PRO v74")
symbols = [s.strip().upper() for s in st.session_state.tickers_text.split(",") if s.strip()]

if symbols:
    results = []
    # Pasek postępu
    progress_bar = st.progress(0)
    for i, sym in enumerate(symbols):
        res = analyze_symbol(sym)
        if res: results.append(res)
        progress_bar.progress((i + 1) / len(symbols))
    progress_bar.empty()

    if results:
        # Kafelki
        sorted_res = sorted(results, key=lambda x: x["score"], reverse=True)
        cols = st.columns(min(len(sorted_res), 4))
        for i, r in enumerate(sorted_res[:8]):
            with cols[i % 4]:
                color = "tile-buy" if r["rsi"] < 40 else "tile-sell" if r["rsi"] > 60 else "tile-neutral"
                st.markdown(f"""<div class='top-mini-tile {color}'>
                    <b>{r['symbol']}</b><br>{r['price']:.2f}<br>RSI: {r['rsi']:.1f}
                </div>""", unsafe_allow_html=True)

        # Wykres i AI
        st.divider()
        sel = st.selectbox("Szczegóły:", [r['symbol'] for r in sorted_res])
        r_sel = next(x for x in results if x["symbol"] == sel)
        
        c1, c2 = st.columns([2, 1])
        with c1:
            df_plot = r_sel["df"].tail(100)
            fig = go.Figure(data=[go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'])])
            fig.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with c2:
            if st.button(f"🤖 Analiza AI {sel}"):
                if client:
                    prompt = f"Cena {sel}: {r_sel['price']}, RSI: {r_sel['rsi']:.1f}. Daj krótki werdykt."
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.info(resp.choices.message.content)
                else: st.warning("Brak klucza API")
            
            risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
            units = risk_val / (r_sel['price'] * 0.05)
            st.metric("Sugerowana ilość", f"{int(units)} szt.")
