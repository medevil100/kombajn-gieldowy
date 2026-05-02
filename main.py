import streamlit as st
import yfinance as yf
import pandas as pd
import math
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# =================================================================
# 1. KONFIGURACJA I GIGANTYCZNY DESIGN NEONOWY
# =================================================================
st.set_page_config(layout="wide", page_title="NEON MEGA-KOMBAJN ULTRA PRO", page_icon="🚀")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    
    /* Karty Główne */
    .mega-card { border: 2px solid #222; padding: 30px; border-radius: 20px; background: #0a0a18; box-shadow: 0 0 25px #39FF1422; margin-bottom: 30px; }
    
    /* Karty Top 10 */
    .top-card { border: 1px solid #333; padding: 15px; border-radius: 12px; background: #0c0c1e; font-size: 1rem; line-height: 1.5; min-height: 280px; text-align: center; }
    
    /* Napisy i Ceny */
    .neon-title { color: #39FF14; font-weight: bold; font-size: 3.5rem; text-shadow: 0 0 15px #39FF14; margin-bottom: 10px; }
    .price-tag { font-size: 2.8rem; font-weight: bold; color: #ffffff; }
    
    /* Kolory Bid / Ask */
    .neon-bid { color: #00FF00; font-weight: bold; font-size: 1.2rem; text-shadow: 0 0 5px #00FF00; }
    .neon-ask { color: #FF0000; font-weight: bold; font-size: 1.2rem; text-shadow: 0 0 5px #FF0000; }
    
    /* Sygnały */
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 2px solid #39FF14; padding: 10px; border-radius: 10px; text-align: center; font-size: 1.4rem; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 2px solid #FF3131; padding: 10px; border-radius: 10px; text-align: center; font-size: 1.4rem; }
    .signal-TRZYMAJ { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; border: 2px solid #00FFFF; padding: 10px; border-radius: 10px; text-align: center; font-size: 1.4rem; }
    
    /* Przyciski */
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 2px solid #39FF14; width: 100%; font-weight: bold; height: 5rem; font-size: 1.4rem; box-shadow: 0 0 20px #39FF1444; }
    
    hr { border: 0.5px solid #333; }
    .label-grey { color: #888; font-size: 1rem; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. SILNIK MATEMATYCZNY ULTRA (PEŁNA LOGIKA)
# =================================================================

def get_ultra_engine(symbol):
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
        
        # RSI 14
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))
        
        # ATR 14
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Trend Score & Litery
        t1, t2, t3 = ("W" if last > e10 else "S"), ("W" if last > e50 else "S"), ("W" if last > e200 else "S")
        score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        # Formacje / Presja / Zmienność
        body = last - open_p
        rng = high_p - low_p
        pattern = "MOCNA BYCZA" if body > 0 and abs(body) > 0.6 * rng else "MOCNA NIEDŹWIEDZIA" if body < 0 and abs(body) > 0.6 * rng else "NEUTRALNA"
        pressure = "BYKI DOMINUJĄ" if last > (open_p + last)/2 else "NIEDŹWIEDZIE DOMINUJĄ"
        volat = high_p - low_p
        
        # Sygnał
        sig = "KUP" if score >= 4 and rsi < 70 else "SPRZEDAJ" if score <= -3 else "TRZYMAJ"
        
        return {
            "symbol": symbol, "price": last, "bid": tk.info.get('bid', '-'), "ask": tk.info.get('ask', '-'),
            "trends": f"{t1}|{t2}|{t3}", "score": score, "rsi": rsi, "atr": atr, "macd_h": macd_h,
            "vol": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean(),
            "piv": (high_p + low_p + last) / 3, "h52": df['High'].max(), "l52": df['Low'].min(),
            "pat": pattern, "pres": pressure, "volat": volat, "signal": sig
        }
    except: return None

# =================================================================
# 3. KONTROLA I AI
# =================================================================
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st_autorefresh(interval=5 * 60 * 1000, key="mega_ultra_final_300")

st.sidebar.title("💠 KONTROLA ULTRA")
tickers_in = st.sidebar.text_area("Wklej tickery:", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD", height=250)
tickers = [x.strip().upper() for x in tickers_in.replace(",", " ").split() if x.strip()]

st.markdown("<h1 class='neon-title'>🚀 MEGA-KOMBAJN ULTRA v.PRO</h1>", unsafe_allow_html=True)

if tickers:
    results = [get_ultra_engine(t) for t in tickers if get_ultra_engine(t)]
    
    # --- TOP 10 RADAR (Z PEŁNYMI DANYMI) ---
    st.subheader("🔥 RADAR WYBIĆ (PEŁNE DANE)")
    top_10 = sorted(results, key=lambda x: x['vol'], reverse=True)[:10]
    for i in range(0, len(top_10), 5):
        cols = st.columns(5)
        for j, item in enumerate(top_10[i:i+5]):
            with cols[j]:
                st.markdown(f"""
                <div class="top-card">
                    <div style="color:#39FF14; font-weight:bold; font-size:1.6rem; margin-bottom:5px;">{item['symbol']}</div>
                    <div style="font-size:1.8rem; font-weight:bold; color:white;">{item['price']:.2f}</div>
                    <span class="neon-bid">B: {item['bid']}</span> | <span class="neon-ask">A: {item['ask']}</span><hr>
                    <b>Trend:</b> {item['trends']}<br>
                    <b>Score:</b> {item['score']} | <b>RSI:</b> {item['rsi']:.1f}<br>
                    <b>Vol:</b> {item['vol']:.2f}x<br>
                    <b>Świeca:</b> {item['pat']}<br><br>
                    <div class="signal-{item['signal']}">{item['signal']}</div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA GŁÓWNA ---
    for r in results:
        with st.container():
            st.markdown(f"<div class='mega-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.8, 1.5, 1.3, 2.5])
            
            with c1:
                st.markdown(f"<div class='neon-title' style='font-size:3.5rem;'>{r['symbol']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='price-tag'>{r['price']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"Bid: <span class='neon-bid'>{r['bid']}</span> | Ask: <span class='neon-ask'>{r['ask']}</span>", unsafe_allow_html=True)
                st.markdown(f"<div class='label-grey'>Świeca: <span style='color:white;'>{r['pat']}</span></div>", unsafe_allow_html=True)

            with c2:
                st.markdown("🔍 **TREND & PIVOT**")
                st.write(f"Trend (K|Ś|D): **{r['trends']}**")
                st.write(f"Trend Score: **{r['score']}**")
                st.write(f"Pivot Point: **{r['piv']:.2f}**")
                st.write(f"Presja: **{r['pres']}**")
                
            with c3:
                st.markdown("📊 **WSKAŹNIKI**")
                st.write(f"RSI (14): **{r['rsi']:.1f}**")
                st.write(f"ATR (14): **{r['atr']:.2f}**")
                st.write(f"MACD Hist: **{r['macd_h']:.4f}**")
                st.write(f"Vol Rel: **{r['vol']:.2f}x**")

            with c4:
                st.markdown(f"<div class=" + f"'signal-{r['signal']}'>{r['signal']}</div>", unsafe_allow_html=True)
                if st.button(f"PEŁNA DIAGNOZA AI 🤖", key=f"ai_{r['symbol']}"):
                    if client:
                        with st.spinner("SYSTEM ANALIZUJE..."):
                            prompt = f"Analiza {r['symbol']}: Kurs {r['price']}, Trend {r['score']}, RSI {r['rsi']:.1f}, Vol {r['vol']:.2f}x, ATR {r['atr']:.2f}, MACD Hist {r['macd_h']:.4f}, Świeca {r['pat']}, Presja {r['pres']}. Daj surowy raport Bloomberg AI bez definicji."
                            try:
                                resp = client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[
                                        {"role": "system", "content": "Jesteś wojskowym terminalem giełdowym. Zakaz definicji. Zakaz lania wody. Podaj: Trend, Dynamika, Werdykt."},
                                        {"role": "user", "content": prompt}
                                    ], temperature=0.2
                                )
                                st.info(f"**DIAGNOZA AI:**\n\n{resp.choices[0].message.content}")
                            except: st.error("Błąd API.")
                    else: st.error("Brak klucza w Secrets!")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Dodaj tickery w sidebarze.")
