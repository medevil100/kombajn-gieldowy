import streamlit as st
import yfinance as yf
import pandas as pd
import openai
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA (Musi być na samym początku) ---
st.set_page_config(layout="wide", page_title="NEON HUB ULTRA")

# --- 2. STYLIZACJA ---
st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .neon-card { border: 2px solid #222; padding: 20px; border-radius: 12px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 20px; }
    .neon-title { color: #39FF14; font-weight: bold; font-size: 2rem; text-shadow: 0 0 10px #39FF14; }
    .signal-KUP { color: #39FF14; font-weight: bold; border: 1px solid #39FF14; padding: 5px; border-radius: 5px; text-align: center; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; border: 1px solid #FF3131; padding: 5px; border-radius: 5px; text-align: center; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 2px solid #39FF14; width: 100%; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 3. KLUCZ API I REFRESH ---
if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]

st_autorefresh(interval=5 * 60 * 1000, key="hub_core_v1")

# --- 4. FUNKCJE OBLICZEŃ (SILNIK ULTRA) ---
def get_metrics(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        
        last = df['Close'].iloc[-1]
        e10 = df['Close'].ewm(span=10).mean().iloc[-1]
        e50 = df['Close'].ewm(span=50).mean().iloc[-1]
        e200 = df['Close'].ewm(span=200).mean().iloc[-1]
        
        # Trend
        t = ["W" if last > e else "S" for e in [e10, e50, e200]]
        score = (1 if t[0]=="W" else -1) + (2 if t[1]=="W" else -2) + (3 if t[2]=="W" else -3)
        
        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
        
        sig = "KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ"
        
        return {
            "p": last, "s": score, "r": rsi, "t": "|".join(t), "sig": sig, 
            "piv": (df['High'].iloc[-1]+df['Low'].iloc[-1]+last)/3,
            "bid": tk.info.get('bid', '-'), "ask": tk.info.get('ask', '-')
        }
    except: return None

# --- 5. INTERFEJS ---
st.sidebar.title("💠 PANEL")
t_in = st.sidebar.text_area("Tickery:", "CDR.WA, PKO.WA, AAPL, NVDA", height=150)
tickers = [x.strip().upper() for x in t_in.replace(",", " ").split() if x.strip()]

st.markdown("<h1 class='neon-title'>🚀 NEON TERMINAL ULTRA</h1>", unsafe_allow_html=True)

if tickers:
    for sym in tickers:
        data = get_metrics(sym)
        if not data: continue
        
        with st.container():
            st.markdown("<div class='neon-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
            with c1:
                st.markdown(f"### {sym}")
                st.write(f"Cena: **{data['p']:.2f}**")
                st.write(f"B: {data['bid']} | A: {data['ask']}")
            with c2:
                st.write(f"Trend: **{data['t']}**")
                st.write(f"Score: **{data['s']}**")
            with c3:
                st.markdown(f"<div class='signal-{data['sig']}'>{data['sig']}</div>", unsafe_allow_html=True)
                st.write(f"RSI: {data['r']:.1f}")
            with c4:
                if st.button(f"ANALIZA AI 🤖", key=f"ai_{sym}"):
                    try:
                        prompt = f"Analiza {sym}: Cena {data['p']}, Score {data['s']}, RSI {data['r']:.1f}. Werdykt Bloomberg, surowo."
                        resp = openai.chat.completions.create(
                            model="gpt-4o", 
                            messages=[{"role": "system", "content": "Analityk Bloomberg."}, {"role": "user", "content": prompt}]
                        )
                        st.info(resp.choices[0].message.content)
                    except: st.error("Błąd AI. Sprawdź Secrets.")
            st.markdown("</div>", unsafe_allow_html=True)
