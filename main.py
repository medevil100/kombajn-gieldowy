import streamlit as st
import yfinance as yf
import pandas as pd
import math
import openai
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA ---
st.set_page_config(layout="wide", page_title="NEON HUB ULTRA AI")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .neon-card { border: 2px solid #222; padding: 25px; border-radius: 15px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 25px; }
    .neon-title { color: #39FF14; font-weight: bold; font-size: 2.5rem; text-shadow: 0 0 10px #39FF14; }
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 1px solid #39FF14; padding: 5px; border-radius: 5px; text-align: center; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 1px solid #FF3131; padding: 5px; border-radius: 5px; text-align: center; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 2px solid #39FF14; width: 100%; font-weight: bold; height: 3.5rem; }
    </style>
""", unsafe_allow_html=True)

# --- 2. SILNIK MATEMATYCZNY (Z analyzer_ultra.py) ---
def get_ultra_metrics(df):
    closes = df['Close'].tolist()
    last = closes[-1]
    # Proste obliczenia EMA i RSI na bazie Twojego silnika
    e10 = df['Close'].ewm(span=10).mean().iloc[-1]
    e50 = df['Close'].ewm(span=50).mean().iloc[-1]
    e200 = df['Close'].ewm(span=200).mean().iloc[-1]
    
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
    loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
    rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
    
    t1, t2, t3 = ("W" if last > e10 else "S"), ("W" if last > e50 else "S"), ("W" if last > e200 else "S")
    score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
    
    # Sygnał
    sig = "KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ"
    return {"price": last, "score": score, "rsi": rsi, "trends": f"{t1}|{t2}|{t3}", "signal": sig, "pivot": (df['High'].iloc[-1]+df['Low'].iloc[-1]+last)/3}

# --- 3. LOGIKA GŁÓWNA ---
if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]

st_autorefresh(interval=5 * 60 * 1000, key="hub_refresh")

st.sidebar.title("💠 PANEL HUB")
tickers_in = st.sidebar.text_area("Wklej tickery:", "CDR.WA, PKO.WA, AAPL, NVDA", height=200)
tickers = [t.strip().upper() for t in tickers_in.replace(",", " ").split() if t.strip()]

st.markdown("<h1 class='neon-title'>🚀 NEON HUB: TERMINAL + ULTRA</h1>", unsafe_allow_html=True)

if tickers:
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            df = tk.history(period="1y")
            if df.empty: continue
            data = get_ultra_metrics(df)
            info = tk.info
            
            with st.container():
                st.markdown(f"<div class='neon-card'>", unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns([1.5, 1.2, 1, 2.5])
                with c1:
                    st.markdown(f"<div class='neon-title'>{t}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:2rem; font-weight:bold;'>{data['price']:.2f}</div>", unsafe_allow_html=True)
                    st.markdown(f"Bid: <span style='color:#00FF00;'>{info.get('bid','-')}</span> | Ask: <span style='color:#FF0000;'>{info.get('ask','-')}</span>", unsafe_allow_html=True)
                with c2:
                    st.write(f"Trend (K/Ś/D): **{data['trends']}**")
                    st.write(f"Trend Score: **{data['score']}**")
                    st.write(f"RSI: **{data['rsi']:.1f}**")
                with c3:
                    st.markdown(f"<div class='signal-{data['signal']}'>{data['signal']}</div>", unsafe_allow_html=True)
                    st.write(f"Pivot: {data['pivot']:.2f}")
                with c4:
                    if st.button(f"PEŁNA ANALIZA AI 🤖", key=f"ai_{t}"):
                        prompt = f"Analiza {t}: Kurs {data['price']}, Score {data['score']}, RSI {data['rsi']:.1f}. Werdykt techniczny Bloomberg, surowo."
                        resp = openai.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś terminalem giełdowym."}, {"role": "user", "content": prompt}])
                        st.info(resp.choices[0].message.content)
                st.markdown("</div>", unsafe_allow_html=True)
        except Exception as e: st.error(f"Błąd {t}: {e}")
