import streamlit as st
import yfinance as yf
import pandas as pd
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA ---
st.set_page_config(layout="wide", page_title="NEON MEGA-KOMBAJN ULTRA")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .mega-card { border: 2px solid #222; padding: 25px; border-radius: 15px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 25px; }
    .neon-title { color: #39FF14; font-weight: bold; font-size: 2.8rem; text-shadow: 0 0 10px #39FF14; }
    .price-tag { font-size: 2.2rem; font-weight: bold; color: #ffffff; }
    .neon-bid { color: #00FF00; font-weight: bold; }
    .neon-ask { color: #FF0000; font-weight: bold; }
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 2px solid #39FF14; padding: 10px; border-radius: 8px; text-align: center; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 2px solid #FF3131; padding: 10px; border-radius: 8px; text-align: center; }
    .signal-TRZYMAJ { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; border: 2px solid #00FFFF; padding: 10px; border-radius: 8px; text-align: center; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 2px solid #39FF14; width: 100%; font-weight: bold; height: 4rem; font-size: 1.2rem; }
    .label { color: #888; font-size: 0.9rem; }
    .val { color: #fff; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. KLUCZ API I REFRESH ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st_autorefresh(interval=5 * 60 * 1000, key="mega_kombajn_v1")

# --- 3. PEŁNY SILNIK MATEMATYCZNY ULTRA (PANCERNY) ---
def get_mega_metrics(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        
        last = df['Close'].iloc[-1]
        open_p = df['Open'].iloc[-1]
        high_p = df['High'].iloc[-1]
        low_p = df['Low'].iloc[-1]
        
        # EMA
        e10 = df['Close'].ewm(span=10).mean().iloc[-1]
        e50 = df['Close'].ewm(span=50).mean().iloc[-1]
        e200 = df['Close'].ewm(span=200).mean().iloc[-1]
        
        # MACD
        exp12 = df['Close'].ewm(span=12, adjust=False).mean()
        exp26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal_line = macd.ewm(span=9, adjust=False).mean()
        macd_h = (macd - signal_line).iloc[-1]
        
        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
        
        # ATR i Zmienność
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        volatility = df['High'].tail(10).max() - df['Low'].tail(10).min()
        
        # Trend Score
        t1, t2, t3 = ("W" if last > e10 else "S"), ("W" if last > e50 else "S"), ("W" if last > e200 else "S")
        score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        # Formacje / Presja / Momentum
        body = last - open_p
        rng = high_p - low_p
        pattern = "MOCNA BYCZA" if body > 0 and abs(body) > 0.6 * rng else "MOCNA NIEDŹWIEDZIA" if body < 0 and abs(body) > 0.6 * rng else "NEUTRALNA"
        pressure = "BYKI DOMINUJĄ" if last > (open_p + last)/2 else "NIEDŹWIEDZIE DOMINUJĄ"
        momentum = last - df['Close'].iloc[-5]
        
        return {
            "p": last, "bid": tk.info.get('bid', '-'), "ask": tk.info.get('ask', '-'),
            "trends": f"{t1}|{t2}|{t3}", "score": score, "rsi": rsi, "atr": atr, "macd_h": macd_h,
            "vol": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean(),
            "piv": (high_p + low_p + last) / 3, "h52": df['High'].max(), "l52": df['Low'].min(),
            "pat": pattern, "pres": pressure, "mom": momentum, "volat": volatility,
            "sig": ("KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ")
        }
    except: return None

# --- 4. UI ---
st.sidebar.title("💠 MEGA STEROWANIE")
t_in = st.sidebar.text_area("Lista tickerów:", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD", height=200)
tickers = [x.strip().upper() for x in t_in.replace(",", " ").split() if x.strip()]

st.markdown("<h1 class='neon-title'>🚀 NEON MEGA-KOMBAJN v.PRO</h1>", unsafe_allow_html=True)

if tickers:
    for sym in tickers:
        d = get_mega_metrics(sym)
        if not d: continue
        
        with st.container():
            st.markdown("<div class='mega-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.8, 1.5, 1.5, 2.5])
            
            with c1:
                st.markdown(f"<div class='neon-title' style='font-size:2.5rem;'>{sym}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='price-tag'>{d['p']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"Bid: <span class='neon-bid'>{d['bid']}</span> | Ask: <span class='neon-ask'>{d['ask']}</span>", unsafe_allow_html=True)
                st.markdown(f"<div class='label'>Świeca: <span class='val'>{d['pat']}</span></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='label'>Presja: <span class='val'>{d['pres']}</span></div>", unsafe_allow_html=True)

            with c2:
                st.markdown("🔍 **ANALIZA TRENDU**")
                st.write(f"Trend: **{d['trends']}**")
                st.write(f"Trend Score: **{d['score']}**")
                st.write(f"Momentum (5d): **{d['mom']:.2f}**")
                st.write(f"Pivot Point: **{d['piv']:.2f}**")
                
            with c3:
                st.markdown("📊 **WSKAŹNIKI ULTRA**")
                st.write(f"RSI (14): **{d['rsi']:.1f}**")
                st.write(f"ATR (14): **{d['atr']:.2f}**")
                st.write(f"MACD Hist: **{d['macd_h']:.4f}**")
                st.write(f"Vol Rel: **{d['vol']:.2f}x**")
                st.write(f"Zmienność: **{d['volat']:.2f}**")

            with c4:
                st.markdown(f"<div class='signal-{d['sig']}'>{d['sig']}</div>", unsafe_allow_html=True)
                if st.button(f"PEŁNA DIAGNOZA AI 🤖", key=f"ai_{sym}"):
                    if client:
                        with st.spinner("Przetwarzanie danych..."):
                            prompt = f"Analiza {sym}: Cena {d['p']}, Score {d['score']}, RSI {d['rsi']:.1f}, Vol {d['vol']:.2f}x, ATR {d['atr']:.2f}, MACD Hist {d['macd_h']:.4f}, Świeca {d['pat']}, Presja {d['pres']}. Werdykt techniczny Bloomberg, surowo."
                            try:
                                resp = client.chat.completions.create(
                                    model="gpt-4o", 
                                    messages=[{"role": "system", "content": "Surowy algorytm giełdowy."}, {"role": "user", "content": prompt}]
                                )
                                st.info(f"**DIAGNOZA AI:**\n\n{resp.choices[0].message.content}")
                            except: st.error("Błąd API.")
                    else: st.error("Brak klucza OpenAI!")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Dodaj tickery w sidebarze.")
