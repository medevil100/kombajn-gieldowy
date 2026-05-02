import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from streamlit_autorefresh import st_autorefresh
import openai
import os
import math

# =========================
# SILNIK ULTRA — MATEMATYKA
# =========================

def calculate_rsi(closes, period=14):
    if len(closes) <= period: return 50
    delta = pd.Series(closes).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs.iloc[-1]))

def calculate_atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close'].shift(1)
    tr = pd.concat([high - low, abs(high - close), abs(low - close)], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

# --- DESIGN I STYLE ---
st.set_page_config(layout="wide", page_title="NEON ULTRA TERMINAL")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .neon-card { border: 1px solid #222; padding: 20px; border-radius: 12px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 20px; }
    .neon-title { color: #39FF14; text-shadow: 0 0 10px #39FF14; font-weight: bold; font-size: 24px; }
    .stat-label { color: #888; font-size: 0.9rem; }
    .stat-value { color: #fff; font-weight: bold; font-size: 1.1rem; }
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 1px solid #39FF14; padding: 5px; border-radius: 5px; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 1px solid #FF3131; padding: 5px; border-radius: 5px; }
    .neon-bid { color: #00FF00; font-weight: bold; }
    .neon-ask { color: #FF0000; font-weight: bold; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 1px solid #39FF14; box-shadow: 0 0 10px #39FF14; }
    </style>
""", unsafe_allow_html=True)

# --- KONFIGURACJA ---
refresh_min = st.sidebar.slider("Odświeżanie (min)", 1, 10, 5)
st_autorefresh(interval=refresh_min * 60 * 1000, key="ultra_refresh")

if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]

# --- FUNKCJA ANALIZY ULTRA ---
def fetch_ultra_data(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        
        info = tk.info
        last = df['Close'].iloc[-1]
        prev = df.iloc[-2]
        
        # Wskaźniki Ultra
        ema10 = df['Close'].ewm(span=10).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['Close'].ewm(span=200).mean().iloc[-1]
        rsi_val = calculate_rsi(df['Close'])
        atr_val = calculate_atr(df)
        
        # Trend Score (-6 do +6)
        s = 1 if last > ema10 else -1
        m = 2 if last > ema50 else -2
        l = 3 if last > ema200 else -3
        trend_score = s + m + l
        
        # Formacja świecowa
        body = last - df['Open'].iloc[-1]
        rng = df['High'].iloc[-1] - df['Low'].iloc[-1]
        pattern = "BYCZA" if body > 0 and abs(body) > 0.6 * rng else "NIEDŹWIEDZIA" if body < 0 and abs(body) > 0.6 * rng else "NEUTRALNA"
        
        # Sygnał
        if trend_score >= 4 and rsi_val < 70: sig, s_class = "KUP", "signal-KUP"
        elif trend_score <= -4: sig, s_class = "SPRZEDAJ", "signal-SPRZEDAJ"
        else: sig, s_class = "TRZYMAJ", "neon-hold"

        return {
            "symbol": symbol, "price": last, "bid": info.get('bid', 'N/A'), "ask": info.get('ask', 'N/A'),
            "trend_score": trend_score, "rsi": rsi_val, "atr": atr_val,
            "pattern": pattern, "signal": sig, "s_class": s_class,
            "h52": df['High'].max(), "pivot": (df['High'].iloc[-1] + df['Low'].iloc[-1] + last) / 3,
            "vol_rel": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean()
        }
    except: return None

# --- UI ---
st.sidebar.title("💠 Sterowanie")
user_input = st.sidebar.text_area("Wklej tickery:", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD")
tickers = [t.strip().upper() for t in user_input.replace(",", " ").split() if t.strip()]

st.markdown("<h1 class='neon-text'>🚀 NEON KOMBAJN ULTRA AI</h1>", unsafe_allow_html=True)

if tickers:
    results = [fetch_ultra_data(t) for t in tickers if fetch_ultra_data(t)]
    
    # TOP 10
    st.subheader("🔥 RADAR WYBIĆ ULTRA")
    top_10 = sorted(results, key=lambda x: x['vol_rel'], reverse=True)[:10]
    cols = st.columns(min(len(top_10), 5))
    for i, item in enumerate(top_10):
        with cols[i % 5]:
            st.markdown(f"""
            <div style="border:1px solid #333; padding:10px; border-radius:10px; background:#0a0a18;">
                <div style="color:#39FF14; font-weight:bold;">{item['symbol']}</div>
                <div style="font-size:1.2rem;">{item['price']:.2f}</div>
                <div style="font-size:0.8rem; color:#888;">Trend Score: {item['trend_score']}</div>
                <div class="{item['s_class']}">{item['signal']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # LISTA GŁÓWNA
    for data in results:
        with st.container():
            st.markdown(f"<div class='neon-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.5, 1.2, 1, 2])
            
            with c1:
                st.markdown(f"<div class='neon-title'>{data['symbol']}</div>", unsafe_allow_html=True)
                st.markdown(f"Cena: **{data['price']:.2f}**")
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
                st.write(f"Świeca: **{data['pattern']}**")

            with c2:
                st.write("Wskaźniki Ultra:")
                st.write(f"Trend Score: **{data['trend_score']}**")
                st.write(f"RSI (14): **{data['rsi']:.1f}**")
                st.write(f"Zmienność (ATR): **{data['atr']:.2f}**")

            with c3:
                st.markdown(f"<div class='{data['s_class']}'>{data['signal']}</div>", unsafe_allow_html=True)
                st.write(f"Pivot: {data['pivot']:.2f}")
                st.write(f"Vol Rel: {data['vol_rel']:.2f}x")

            with c4:
                if st.button(f"ANALIZA AI ULTRA 🤖", key=f"ai_{data['symbol']}"):
                    with st.spinner("AI przetwarza dane Ultra..."):
                        prompt = f"Analiza {data['symbol']}: Cena {data['price']}, Trend Score {data['trend_score']}, RSI {data['rsi']:.1f}, Świeca {data['pattern']}, Vol {data['vol_rel']:.2f}x. Wykonaj profesjonalny raport w 4 punktach: Trend, Momentum, Wolumen i Werdykt. Bądź techniczny i surowy."
                        try:
                            resp = openai.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś terminalem giełdowym Bloomberg AI."}, {"role": "user", "content": prompt}])
                            st.info(f"**WERDYKT ULTRA AI:**\n\n{resp.choices[0].message.content}")
                        except: st.error("Sprawdź OPENAI_API_KEY w Secrets.")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Wklej symbole w panelu bocznym.")
