import streamlit as st
import yfinance as yf
import pandas as pd
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(layout="wide", page_title="NEON TERMINAL ULTRA PRO", page_icon="🚀")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .neon-card { border: 2px solid #222; padding: 25px; border-radius: 15px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 25px; }
    .neon-title { color: #39FF14; font-weight: bold; font-size: 2.8rem; text-shadow: 0 0 10px #39FF14; margin-bottom: 10px; }
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

st_autorefresh(interval=5 * 60 * 1000, key="ultra_v_final_fixed")

# --- 3. SILNIK MATEMATYCZNY ULTRA (BEZ PANDAS_TA) ---
def get_ultra_metrics(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        
        last = df['Close'].iloc[-1]
        opens = df['Open'].iloc[-1]
        
        # EMA (obliczone w czystym pandas)
        e10 = df['Close'].ewm(span=10).mean().iloc[-1]
        e50 = df['Close'].ewm(span=50).mean().iloc[-1]
        e200 = df['Close'].ewm(span=200).mean().iloc[-1]
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
        
        # ATR
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Trend Score
        t1, t2, t3 = ("W" if last > e10 else "S"), ("W" if last > e50 else "S"), ("W" if last > e200 else "S")
        score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        return {
            "price": last, "bid": tk.info.get('bid', 'N/A'), "ask": tk.info.get('ask', 'N/A'),
            "trends": f"{t1}|{t2}|{t3}", "score": score, "rsi": rsi, "atr": atr,
            "macd_h": (macd_line - signal_line).iloc[-1],
            "vol": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean(),
            "pattern": "MOCNA BYCZA" if last-opens > 0.6*(df['High'].iloc[-1]-df['Low'].iloc[-1]) else "NEUTRALNA",
            "pressure": "KUPUJĄCY" if last > (opens + last) / 2 else "SPRZEDAJĄCY",
            "pivot": (df['High'].iloc[-1]+df['Low'].iloc[-1]+last)/3,
            "signal": ("KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ")
        }
    except: return None

# --- 4. INTERFEJS ---
st.sidebar.title("💠 TERMINAL")
tickers_in = st.sidebar.text_area("Lista tickerów:", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD", height=200)
tickers = [t.strip().upper() for t in tickers_in.replace(",", " ").split() if t.strip()]

st.markdown("<h1 class='neon-title'>🚀 NEON TERMINAL ULTRA PRO</h1>", unsafe_allow_html=True)

if tickers:
    for t in tickers:
        data = get_ultra_metrics(t)
        if not data: continue
        with st.container():
            st.markdown(f"<div class='neon-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.5, 1.2, 1.2, 2.5])
            with c1:
                st.markdown(f"<div class='neon-title' style='font-size:2.5rem;'>{t}</div>", unsafe_allow_html=True)
                st.write(f"Cena: **{data['price']:.2f}**")
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
            with c2:
                st.write(f"Trend: **{data['trends']}** (Score: {data['score']})")
                st.write(f"RSI: **{data['rsi']:.1f}** | ATR: **{data['atr']:.2f}**")
            with c3:
                st.markdown(f"<div class='signal-{data['signal']}'>{data['signal']}</div>", unsafe_allow_html=True)
                st.write(f"Vol: **{data['vol']:.2f}x**")
            with c4:
                if st.button(f"DIAGNOZA AI 🤖", key=f"ai_{t}"):
                    if client:
                        prompt = f"Analiza {t}: Kurs {data['price']}, RSI {data['rsi']:.1f}, Trend {data['score']}. Podaj: 1. Status trendu, 2. Dynamikę, 3. Werdykt. Surowo."
                        resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Surowy algorytm giełdowy."}, {"role": "user", "content": prompt}])
                        st.info(resp.choices[0].message.content)
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Wklej tickery w sidebarze.")
