import streamlit as st
import yfinance as yf
import pandas as pd
import openai
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(layout="wide", page_title="NEON HUB ULTRA AI", page_icon="🚀")

# --- 2. DESIGN NEONOWY ---
st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .neon-card { border: 2px solid #222; padding: 25px; border-radius: 15px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 25px; }
    .neon-title { color: #39FF14; font-weight: bold; font-size: 2.5rem; text-shadow: 0 0 10px #39FF14; margin-bottom: 10px; }
    .main-price { font-size: 2rem; font-weight: bold; color: #ffffff; }
    .neon-bid { color: #00FF00; font-weight: bold; font-size: 1.1rem; }
    .neon-ask { color: #FF0000; font-weight: bold; font-size: 1.1rem; }
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 1px solid #39FF14; padding: 10px; border-radius: 5px; text-align: center; font-size: 1.3rem; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 1px solid #FF3131; padding: 10px; border-radius: 5px; text-align: center; font-size: 1.3rem; }
    .signal-TRZYMAJ { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; border: 1px solid #00FFFF; padding: 10px; border-radius: 5px; text-align: center; font-size: 1.3rem; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 2px solid #39FF14; width: 100%; font-weight: bold; height: 4rem; font-size: 1.2rem; box-shadow: 0 0 10px #39FF1444; }
    hr { border: 0.5px solid #333; }
    </style>
""", unsafe_allow_html=True)

# --- 3. KLUCZ API I REFRESH ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.sidebar.error("⚠️ Brak klucza OPENAI_API_KEY w Secrets!")

st_autorefresh(interval=5 * 60 * 1000, key="hub_ultra_vfinal")

# --- 4. SILNIK OBLICZENIOWY ULTRA ---
def get_ultra_metrics(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        
        last = df['Close'].iloc[-1]
        # Średnie wykładnicze (EMA)
        e10 = df['Close'].ewm(span=10).mean().iloc[-1]
        e50 = df['Close'].ewm(span=50).mean().iloc[-1]
        e200 = df['Close'].ewm(span=200).mean().iloc[-1]
        
        # RSI 14
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(window=14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
        
        # Trend Score & Litery
        t1, t2, t3 = ("W" if last > e10 else "S"), ("W" if last > e50 else "S"), ("W" if last > e200 else "S")
        score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        # Sygnał
        sig = "KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ"
        
        return {
            "price": last, "score": score, "rsi": rsi, "trends": f"{t1}|{t2}|{t3}", 
            "signal": sig, "pivot": (df['High'].iloc[-1]+df['Low'].iloc[-1]+last)/3,
            "bid": tk.info.get('bid', 'N/A'), "ask": tk.info.get('ask', 'N/A'),
            "h52": df['High'].max(), "vol": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean()
        }
    except: return None

# --- 5. INTERFEJS GŁÓWNY ---
st.sidebar.title("💠 PANEL STEROWANIA")
tickers_in = st.sidebar.text_area("Wklej tickery (oddziel spacją):", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD", height=200)
tickers = [t.strip().upper() for t in tickers_in.replace(",", " ").split() if t.strip()]

st.markdown("<h1 class='neon-title'>🚀 NEON HUB ULTRA AI</h1>", unsafe_allow_html=True)

if tickers:
    for t in tickers:
        data = get_ultra_data = get_ultra_metrics(t)
        if not data:
            st.warning(f"Brak danych dla {t}")
            continue
            
        with st.container():
            st.markdown(f"<div class='neon-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.5, 1.2, 1, 2.5])
            
            with c1:
                st.markdown(f"<div class='neon-title' style='font-size:2rem;'>{t}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='main-price'>{data['price']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
            
            with c2:
                st.write(f"Trend (K/Ś/D): **{data['trends']}**")
                st.write(f"Trend Score: **{data['score']}**")
                st.write(f"RSI (14): **{data['rsi']:.1f}**")
                
            with c3:
                st.markdown(f"<div class='signal-{data['signal']}'>{data['signal']}</div>", unsafe_allow_html=True)
                st.write(f"Vol: {data['vol']:.2f}x")
                st.write(f"Pivot: {data['pivot']:.2f}")

            with c4:
                if st.button(f"PEŁNA ANALIZA AI 🤖", key=f"ai_{t}"):
                    if client is None:
                        st.error("⚠️ Błąd: Podepnij klucz w Secrets!")
                    else:
                        with st.spinner("Generowanie raportu technicznego..."):
                            prompt = f"Analiza {t}: Kurs {data['price']}, Score {data['score']}, RSI {data['rsi']:.1f}, Vol {data['vol']:.2f}x. Podaj werdykt Bloomberg AI: Trend, Momentum, Werdykt. Surowo, bez lania wody."
                            try:
                                resp = client.chat.completions.create(
                                    model="gpt-4o", 
                                    messages=[
                                        {"role": "system", "content": "Jesteś wojskowym terminalem giełdowym Bloomberg. Mówisz surowo i technicznie."},
                                        {"role": "user", "content": prompt}
                                    ]
                                )
                                st.info(f"**WERDYKT AI:**\n\n{resp.choices[0].message.content}")
                            except Exception as e:
                                st.error(f"Błąd API: {e}")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Wklej symbole w panelu bocznym.")
