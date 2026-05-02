import streamlit as st
import yfinance as yf
import pandas as pd
import math
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA ---
st.set_page_config(layout="wide", page_title="NEON ULTRA TERMINAL PRO", page_icon="🚀")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .neon-card { border: 2px solid #222; padding: 25px; border-radius: 15px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 25px; }
    .neon-title { color: #39FF14; font-weight: bold; font-size: 2.5rem; text-shadow: 0 0 10px #39FF14; margin-bottom: 10px; }
    .main-price { font-size: 2.5rem; font-weight: bold; color: #ffffff; }
    .neon-bid { color: #00FF00; font-weight: bold; font-size: 1.2rem; }
    .neon-ask { color: #FF0000; font-weight: bold; font-size: 1.2rem; }
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 2px solid #39FF14; padding: 10px; border-radius: 8px; text-align: center; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 2px solid #FF3131; padding: 10px; border-radius: 8px; text-align: center; }
    .signal-TRZYMAJ { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; border: 2px solid #00FFFF; padding: 10px; border-radius: 8px; text-align: center; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 2px solid #39FF14; width: 100%; font-weight: bold; height: 4rem; font-size: 1.2rem; box-shadow: 0 0 10px #39FF1444; }
    </style>
""", unsafe_allow_html=True)

# --- 2. KLUCZ API I REFRESH ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st_autorefresh(interval=5 * 60 * 1000, key="ultra_v_full_power")

# --- 3. PEŁNY SILNIK ULTRA (MATEMATYKA) ---
def get_ultra_metrics(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        
        last = df['Close'].iloc[-1]
        opens = df['Open'].iloc[-1]
        
        # EMA
        e10 = df['Close'].ewm(span=10).mean().iloc[-1]
        e50 = df['Close'].ewm(span=50).mean().iloc[-1]
        e200 = df['Close'].ewm(span=200).mean().iloc[-1]
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        
        # RSI & ATR
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
        
        high_low = df['High'] - df['Low']
        high_cp = abs(df['High'] - df['Close'].shift())
        low_cp = abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Formacje i Presja
        body = last - opens
        rng = df['High'].iloc[-1] - df['Low'].iloc[-1]
        pattern = "MOCNA BYCZA" if body > 0 and abs(body) > 0.6 * rng else "MOCNA NIEDŹWIEDZIA" if body < 0 and abs(body) > 0.6 * rng else "NEUTRALNA"
        pressure = "KUPUJĄCY DOMINUJĄ" if last > (opens + df['Close'].iloc[-1]) / 2 else "SPRZEDAJĄCY DOMINUJĄ"
        
        # Trend Score
        t1, t2, t3 = ("W" if last > e10 else "S"), ("W" if last > e50 else "S"), ("W" if last > e200 else "S")
        score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        return {
            "price": last, "bid": tk.info.get('bid', 'N/A'), "ask": tk.info.get('ask', 'N/A'),
            "trends": f"{t1}|{t2}|{t3}", "score": score, "rsi": rsi, "atr": atr,
            "macd": macd_line.iloc[-1], "macd_h": (macd_line - signal_line).iloc[-1],
            "vol": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean(),
            "pattern": pattern, "pressure": pressure, "h52": df['High'].max(), "l52": df['Low'].min(),
            "pivot": (df['High'].iloc[-1]+df['Low'].iloc[-1]+last)/3, "signal": ("KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ")
        }
    except: return None

# --- 4. INTERFEJS ---
st.sidebar.title("💠 PANEL ULTRA")
tickers_in = st.sidebar.text_area("Lista tickerów:", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD", height=200)
tickers = [t.strip().upper() for t in tickers_in.replace(",", " ").split() if t.strip()]

st.markdown("<h1 class='neon-title'>🚀 NEON TERMINAL ULTRA PRO</h1>", unsafe_allow_html=True)

if tickers:
    for t in tickers:
        data = get_ultra_metrics(t)
        if not data: continue
            
        with st.container():
            st.markdown(f"<div class='neon-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.5, 1.2, 1.2, 2.2])
            
            with c1:
                st.markdown(f"<div class='neon-title' style='font-size:2rem;'>{t}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='main-price'>{data['price']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
                st.write(f"Świeca: **{data['pattern']}**")

            with c2:
                st.write(f"Trend (K/Ś/D): **{data['trends']}**")
                st.write(f"Trend Score: **{data['score']}**")
                st.write(f"RSI: **{data['rsi']:.1f}**")
                st.write(f"ATR (14): **{data['atr']:.2f}**")
                st.write(f"MACD Hist: **{data['macd_h']:.4f}**")
            
            with c3:
                st.markdown(f"<div class='signal-{data['signal']}'>{data['signal']}</div>", unsafe_allow_html=True)
                st.write(f"Vol: **{data['vol']:.2f}x**")
                st.write(f"Pivot: **{data['pivot']:.2f}**")
                st.write(f"Presja: **{data['pressure']}**")

            with c4:
                if st.button(f"ANALIZA AI 🤖", key=f"ai_{t}"):
                    with st.spinner("Generowanie raportu..."):
                        prompt = f"Analiza {t}: Cena {data['price']}, Score {data['score']}, RSI {data['rsi']:.1f}, Vol {data['vol']:.2f}x, ATR {data['atr']:.2f}, MACD Hist {data['macd_h']:.4f}, Świeca {data['pattern']}. Podaj twardy raport Bloomberg AI."
                        try:
                            resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś terminalem giełdowym."}, {"role": "user", "content": prompt}])
                            st.info(f"**WERDYKT AI:**\n\n{resp.choices[0].message.content}")
                        except: st.error("Błąd AI.")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Dodaj tickery w sidebarze.")
