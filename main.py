import streamlit as st
import yfinance as yf
import pandas as pd
import math
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA I GIGANTYCZNY DESIGN ---
st.set_page_config(layout="wide", page_title="NEON MEGA-KOMBAJN ULTRA PRO", page_icon="🚀")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .mega-card { border: 2px solid #222; padding: 30px; border-radius: 20px; background: #0a0a18; box-shadow: 0 0 25px #39FF1422; margin-bottom: 30px; }
    .top-card { border: 1px solid #333; padding: 15px; border-radius: 12px; background: #0c0c1e; font-size: 1rem; line-height: 1.4; min-height: 300px; text-align: center; }
    .neon-title { color: #39FF14; font-weight: bold; font-size: 3.5rem; text-shadow: 0 0 15px #39FF14; }
    .price-tag { font-size: 2.8rem; font-weight: bold; color: #ffffff; }
    .neon-bid { color: #00FF00; font-weight: bold; font-size: 1.2rem; text-shadow: 0 0 5px #00FF00; }
    .neon-ask { color: #FF0000; font-weight: bold; font-size: 1.2rem; text-shadow: 0 0 5px #FF0000; }
    .tp-val { color: #00FF00; font-weight: bold; font-size: 1.3rem; }
    .sl-val { color: #FF3131; font-weight: bold; font-size: 1.3rem; }
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 2px solid #39FF14; padding: 10px; border-radius: 10px; font-size: 1.4rem; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 2px solid #FF3131; padding: 10px; border-radius: 10px; font-size: 1.4rem; }
    .signal-TRZYMAJ { color: #00FFFF; font-weight: bold; border: 2px solid #00FFFF; padding: 10px; border-radius: 10px; font-size: 1.4rem; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 2px solid #39FF14; width: 100%; font-weight: bold; height: 5rem; font-size: 1.4rem; box-shadow: 0 0 20px #39FF1444; }
    </style>
""", unsafe_allow_html=True)

# --- 2. SILNIK MATEMATYCZNY ULTRA + TP/SL ---
def get_ultra_engine(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        last = df['Close'].iloc[-1]
        
        # Obliczenia Ultra
        e10 = df['Close'].ewm(span=10).mean().iloc[-1]
        e50 = df['Close'].ewm(span=50).mean().iloc[-1]
        e200 = df['Close'].ewm(span=200).mean().iloc[-1]
        
        # RSI i ATR (Zmienność do TP/SL)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
        
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # DYNAMIKA TP/SL
        tp = last + (atr * 2)
        sl = last - (atr * 1.5)
        
        t1, t2, t3 = ("W" if last > e10 else "S"), ("W" if last > e50 else "S"), ("W" if last > e200 else "S")
        score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        return {
            "symbol": symbol, "price": last, "bid": tk.info.get('bid', '-'), "ask": tk.info.get('ask', '-'),
            "trends": f"{t1}|{t2}|{t3}", "score": score, "rsi": rsi, "atr": atr, "tp": tp, "sl": sl,
            "vol": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean(),
            "piv": (df['High'].iloc[-1] + df['Low'].iloc[-1] + last) / 3,
            "pat": "MOCNA BYCZA" if (last - df['Open'].iloc[-1]) > 0.6*(df['High'].iloc[-1]-df['Low'].iloc[-1]) else "NEUTRALNA",
            "pres": "BYKI" if last > df['Open'].iloc[-1] else "NIEDŹWIEDZIE", "signal": ("KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ")
        }
    except: return None

# --- 3. AI I UI ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st_autorefresh(interval=5 * 60 * 1000, key="mega_final_fixed_v1")

st.sidebar.title("💠 KONTROLA")
tickers_in = st.sidebar.text_area("Wklej tickery:", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD", height=200)
tickers = [x.strip().upper() for x in tickers_in.replace(",", " ").split() if x.strip()]

st.markdown("<h1 class='neon-title'>🚀 MEGA-KOMBAJN ULTRA v.PRO</h1>", unsafe_allow_html=True)

if tickers:
    results = [get_ultra_engine(t) for t in tickers if get_ultra_engine(t)]
    
    # --- TOP 10 ---
    st.subheader("🔥 RADAR WYBIĆ")
    top_10 = sorted(results, key=lambda x: x['vol'], reverse=True)[:10]
    for i in range(0, len(top_10), 5):
        cols = st.columns(5)
        for j, item in enumerate(top_10[i:i+5]):
            with cols[j]:
                st.markdown(f"""
                <div class="top-card">
                    <div style="color:#39FF14; font-weight:bold; font-size:1.4rem;">{item['symbol']}</div>
                    <div style="font-size:1.6rem; font-weight:bold;">{item['price']:.2f}</div>
                    <span class="neon-bid">B: {item['bid']}</span> | <span class="neon-ask">A: {item['ask']}</span><hr>
                    <b>TP: <span class="tp-val">{item['tp']:.2f}</span></b><br>
                    <b>SL: <span class="sl-val">{item['sl']:.2f}</span></b><hr>
                    <b>Trend:</b> {item['trends']} | <b>Score:</b> {item['score']}<br>
                    <div class="signal-{item['signal']}" style="margin-top:10px; font-size:1rem;">{item['signal']}</div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA GŁÓWNA ---
    for r in results:
        with st.container():
            st.markdown(f"<div class='mega-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.8, 1.5, 1.3, 2.5])
            with c1:
                st.markdown(f"<div class='neon-title' style='font-size:3rem;'>{r['symbol']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='price-tag'>{r['price']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"Bid: <span class='neon-bid'>{r['bid']}</span> | Ask: <span class='neon-ask'>{r['ask']}</span>", unsafe_allow_html=True)
            with c2:
                st.write(f"Trend: **{r['trends']}** (Score: {r['score']})")
                st.write(f"RSI: **{r['rsi']:.1f}** | Świeca: **{r['pat']}**")
                st.write(f"Presja: **{r['pres']}**")
            with c3:
                st.markdown(f"**TP: <span class='tp-val'>{r['tp']:.2f}</span>**", unsafe_allow_html=True)
                st.markdown(f"**SL: <span class='sl-val'>{r['sl']:.2f}</span>**", unsafe_allow_html=True)
                st.write(f"ATR: {r['atr']:.2f} | Pivot: {r['piv']:.2f}")
            with c4:
                st.markdown(f"<div class='signal-{r['signal']}'>{r['signal']}</div>", unsafe_allow_html=True)
                if st.button(f"PEŁNA DIAGNOZA AI 🤖", key=f"ai_{r['symbol']}"):
                    if client:
                        with st.spinner("SYSTEM ANALIZUJE..."):
                            prompt = f"Analiza {r['symbol']}: Kurs {r['price']}, Bid/Ask {r['bid']}/{r['ask']}, Trend {r['score']}, RSI {r['rsi']:.1f}, ATR {r['atr']:.2f}, TP/SL {r['tp']:.2f}/{r['sl']:.2f}, Presja {r['pres']}. Wykonaj surową analizę techniczną. Podaj: 1. Ocena wejścia, 2. Ryzyko, 3. Werdykt. ZAKAZ DEFINICJI."
                            try:
                                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś bezdusznym systemem operacyjnym. Mówisz tylko o faktach i liczbach. Zakaz lania wody."}, {"role": "user", "content": prompt}], temperature=0.1)
                                st.info(f"**DIAGNOZA SYSTEMOWA:**\n\n{resp.choices[0].message.content}")
                            except: st.error("Błąd API.")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Wklej tickery w sidebarze.")
