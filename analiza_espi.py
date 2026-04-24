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
st.set_page_config(page_title="AI ALPHA GOLDEN v17.0", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 10px; border-radius: 8px; border: 1px solid #30363d; text-align: center; margin-bottom: 5px; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 25px; }
    .metric-box { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 3px 0; font-size: 0.85rem; }
    .signal-buy { color: #238636; font-weight: bold; }
    .signal-sell { color: #da3633; font-weight: bold; }
    .signal-wait { color: #8b949e; font-weight: bold; }
    .tp-green { color: #238636; font-weight: bold; }
    .sl-red { color: #da3633; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. LOGIKA ANALITYCZNA (PIVOTY, ŚREDNIE, ŚWIECE) ---
def get_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        # Dane do Pivotów i Średnich (1 rok)
        d_day = t.history(period="1y", interval="1d")
        # Dane do analizy świecowej (10 min) - pobieramy więcej by mieć zapas
        d_10m = t.history(period="2d", interval="15m") # yfinance nie ma 10m, 15m to najbliższy standard
        
        if d_day.empty or d_10m.empty: return None

        curr = d_10m.iloc[-1]
        prev_day = d_day.iloc[-2]
        price = curr['Close']
        
        # PIVOT POINTS (Standard)
        h, l, c = prev_day['High'], prev_day['Low'], prev_day['Close']
        p = (h + l + c) / 3
        r1, s1 = (2 * p) - l, (2 * p) - h
        r2, s2 = p + (h - l), p - (h - l)
        r3, s3 = h + 2 * (p - l), l - 2 * (h - p)

        # ŚREDNIE KROCZĄCE
        sma50 = d_day['Close'].rolling(50).mean().iloc[-1]
        sma200 = d_day['Close'].rolling(200).mean().iloc[-1]

        # ANALIZA 10 POPRZEDNICH ŚWIEC
        candles_10 = d_10m.tail(11).head(10) # 10 poprzednich bez obecnej
        bullish_count = len(candles_10[candles_10['Close'] > candles_10['Open']])
        candle_bias = "BYCZY" if bullish_count > 5 else "NIEDŹWIEDZI"

        # BID/ASK FALLBACK
        info = t.info
        bid = info.get('bid') or price * 0.999
        ask = info.get('ask') or price * 1.001

        # RSI I VERDICT
        delta = d_day['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        verdict = "KUP" if rsi < 30 else "SPRZEDAJ" if rsi > 70 else "CZEKAJ"
        v_color = "signal-buy" if rsi < 30 else "signal-sell" if rsi > 70 else "signal-wait"

        # ATR do TP/SL
        atr = (d_day['High'] - d_day['Low']).rolling(14).mean().iloc[-1]

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "p": p, "r1": r1, "s1": s1, "r2": r2, "s2": s2, "r3": r3, "s3": s3,
            "sma50": sma50, "sma200": sma200, "bias": candle_bias, "bulls": bullish_count,
            "verdict": verdict, "v_class": v_color, "tp": price + (atr * 2), "sl": price - (atr * 1.5),
            "df": d_10m.tail(30), "change": ((price - c)/c)*100
        }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 v17.0 KOMBAJN")
    api_key = st.text_input("OpenAI API Key", type="password")
    t_input = st.text_area("Lista Symboli", "BTC-USD, ETH-USD, NVDA, TSLA, AAPL, MSFT, AMZN, META, GOOGL, NFLX", height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana!")
    refresh = st.slider("Odśwież (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="refresh_sync")

# --- 4. GŁÓWNY PANEL ---
symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in list(executor.map(get_analysis, symbols)) if r]

if results:
    # --- TOP 10 KAFELKI (2x5) ---
    st.subheader("📊 SZYBKI PODGLĄD (TOP 10)")
    top_10 = results[:10]
    for r in :
        cols = st.columns(5)
        for c in range(5):
            idx = r + c
            if idx < len(top_10):
                d = top_10[idx]
                with cols[c]:
                    st.markdown(f"""
                    <div class="top-tile">
                        <small>{d['symbol']}</small><br>
                        <b style="font-size:1.2rem;">{d['price']:.2f}</b><br>
                        <span class="{d['v_class']}">{d['verdict']}</span><br>
                        <div style="font-size:0.7rem; margin-top:5px;">
                            B: {d['bid']:.2f} | A: {d['ask']:.2f}<br>
                            Piv: {d['p']:.2f}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # --- PEŁNA ANALIZA (KARTY) ---
    for d in results:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        col1, col2, col3 = st.columns()
        
        with col1:
            st.markdown(f"### {d['symbol']} <span class='{d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"""
                <div class="metric-box"><span>BID / ASK</span><b>{d['bid']:.2f} / {d['ask']:.2f}</b></div>
                <div class="metric-box"><span>SMA 50 / 200</span><b>{d['sma50']:.1f} / {d['sma200']:.1f}</b></div>
                <div class="metric-box"><span>Ostatnie 10ś (10m)</span><b>{d['bias']} ({d['bulls']}W)</b></div>
                <div class="metric-row"><br>
                    <span class="tp-green">TP Target: {d['tp']:.2f}</span><br>
                    <span class="sl-red">SL Limit: {d['sl']:.2f}</span>
                </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown("**POZIOMY PIVOT**")
            st.markdown(f"""
                <div class="metric-box"><span>Resistance 3</span><b style="color:#da3633">{d['r3']:.2f}</b></div>
                <div class="metric-box"><span>Resistance 1</span><b>{d['r1']:.2f}</b></div>
                <div class="metric-box"><span>PIVOT POINT</span><b style="color:#f1c40f">{d['p']:.2f}</b></div>
                <div class="metric-box"><span>Support 1</span><b>{d['s1']:.2f}</b></div>
                <div class="metric-box"><span>Support 3</span><b style="color:#238636">{d['s3']:.2f}</b></div>
            """, unsafe_allow_html=True)
            
            if api_key:
                if st.button(f"🧠 ANALIZA AI: {d['symbol']}", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = f"Analiza {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['p']:.2f}, 10ś: {d['bias']}. Podaj tylko: 1. DECYZJA (KUP/CZEKAJ/SPRZEDAJ), 2. PRECYZYJNE TP/SL, 3. RYZYKO (1 zdanie)."
                    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś bezwzględnym traderem. Zero lania wody. Tylko komendy."}, {"role": "user", "content": prompt}])
                    st.info(res.choices.message.content)

        with col3:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['p'], line_dash="dash", line_color="yellow", annotation_text="Pivot")
            fig.update_layout(height=300, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.error("Wpisz poprawne symbole (np. BTC-USD, NVDA) w sidebarze.")
