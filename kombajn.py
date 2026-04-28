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
# 1. KONFIGURACJA I STYLE
# ---------------------------------------------------------
st.set_page_config(page_title="AI ALPHA MONSTER PRO v74", page_icon="🚜", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .top-mini-tile { padding: 15px; border-radius: 12px; text-align: center; background: linear-gradient(145deg,#0d1117,#050505); border:1px solid #30363d; margin-bottom:15px; }
    .tile-buy { border:2px solid #00ff88!important; box-shadow:0 0 15px rgba(0,255,136,0.3); }
    .tile-sell { border:2px solid #ff4b4b!important; box-shadow:0 0 15px rgba(255,75,75,0.3); }
    .tile-neutral { border:2px solid #8b949e!important; box-shadow:0 0 15px rgba(139,148,158,0.3); }
    .stMetric { background: #0d1117; padding: 10px; border-radius: 10px; border: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)

# Inicjalizacja Klienta AI
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None
TICKERS_FILE = "moje_spolki.txt"

# ---------------------------------------------------------
# 2. LOGIKA I FUNKCJE
# ---------------------------------------------------------
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = delta.where(delta < 0, 0).abs().rolling(period).mean()
    return 100 - (100 / (1 + (gain / (loss + 1e-12))))

def analyze_symbol(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False)
        if df.empty or len(df) < 30: return None
        
        close = df["Close"].ffill()
        price = float(close.iloc[-1])
        rsi = float(compute_rsi(close).iloc[-1])
        
        # Scoring Monster v74
        score = 50
        if rsi < 30: score += 25
        elif rsi < 40: score += 10
        elif rsi > 70: score -= 25
        elif rsi > 60: score -= 10
        
        return {"symbol": symbol, "price": price, "rsi": rsi, "score": score, "df": df}
    except:
        return None

# ---------------------------------------------------------
# 3. SIDEBAR (USTAWIENIA)
# ---------------------------------------------------------
st.sidebar.title("🚜 MONSTER v74 PRO")

if "tickers_text" not in st.session_state:
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, "r") as f:
            st.session_state.tickers_text = f.read().strip()
    else:
        st.session_state.tickers_text = "NVDA, TSLA, AAPL, BTC-USD, ETH-USD"

refresh_min = st.sidebar.slider("Auto-refresh (min)", 1, 10, 3)
st_autorefresh(interval=refresh_min * 60 * 1000, key="auto_refresh")

st.session_state.risk_cap = st.sidebar.number_input("Twój Kapitał (PLN/USD):", value=10000.0)
st.session_state.risk_pct = st.sidebar.slider("Ryzyko na pozycję (%):", 0.1, 5.0, 1.0)

new_tickers = st.sidebar.text_area("Lista tickerów (CSV):", value=st.session_state.tickers_text, height=150)
if st.sidebar.button("💾 Zastosuj i Zapisz"):
    st.session_state.tickers_text = new_tickers
    with open(TICKERS_FILE, "w") as f:
        f.write(new_tickers)
    st.rerun()

# ---------------------------------------------------------
# 4. DASHBOARD GŁÓWNY
# ---------------------------------------------------------
st.title("AI ALPHA MONSTER PRO v74")
symbols = [s.strip().upper() for s in st.session_state.tickers_text.split(",") if s.strip()]

if not symbols:
    st.warning("👈 Dodaj symbole w pasku bocznym.")
else:
    results = []
    for sym in symbols:
        res = analyze_symbol(sym)
        if res: results.append(res)

    if results:
        # Ranking Kafelkowy
        st.subheader("🔥 Top Sygnały (RSI + Price Action)")
        sorted_res = sorted(results, key=lambda x: x["score"], reverse=True)
        cols = st.columns(min(len(sorted_res), 5))
        
        for i, r in enumerate(sorted_res[:10]):
            tile_class = "tile-neutral"
            if r["rsi"] < 35: tile_class = "tile-buy"
            elif r["rsi"] > 65: tile_class = "tile-sell"

            with cols[i % 5]:
                st.markdown(f"""
                <div class='top-mini-tile {tile_class}'>
                    <div style='font-size:1.1rem; font-weight:bold;'>{r['symbol']}</div>
                    <div style='color:#58a6ff;'>{r['price']:.2f}</div>
                    <div style='font-size:0.8rem;'>Score: {r['score']} | RSI: {r['rsi']:.1f}</div>
                </div>
                """, unsafe_allow_html=True)

        # ---------------------------------------------------------
        # 5. GŁĘBOKA ANALIZA (WYKRES + AI)
        # ---------------------------------------------------------
        st.divider()
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            selected_sym = st.selectbox("Wybierz instrument do analizy:", [r['symbol'] for r in sorted_res])
            r_sel = next(item for item in results if item["symbol"] == selected_sym)
            df_sel = r_sel["df"].tail(100)

            fig = go.Figure(data=[go.Candlestick(
                x=df_sel.index, open=df_sel['Open'], high=df_sel['High'],
                low=df_sel['Low'], close=df_sel['Close'], name="Cena"
            )])
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.subheader("🤖 AI Verdict")
            if client:
                if st.button(f"Generuj raport dla {selected_sym}"):
                    with st.spinner("Analizowanie..."):
                        prompt = f"Analiza techniczna {selected_sym}. Cena: {r_sel['price']}, RSI: {r_sel['rsi']:.2f}. Napisz w 3 punktach: 1. Kierunek (Long/Short), 2. Gdzie SL, 3. Krótkie uzasadnienie."
                        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                        st.info(resp.choices[0].message.content)
            else:
                st.error("Brak klucza OpenAI w Secrets!")

            # Kalkulator Ryzyka
            st.subheader("🧮 Position Sizing")
            risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
            sl_dist = r_sel['price'] * 0.05  # Zakładamy domyślny SL 5%
            units = risk_val / sl_dist
            
            st.metric("Ilość do kupna", f"{int(units)} szt.")
            st.write(f"Przy SL 5% ({r_sel['price']*0.95:.2f}), stracisz dokładnie {risk_val:.2f} {selected_sym.split('-')[-1] if '-' in selected_sym else 'waluty'}.")

    st.sidebar.caption(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
