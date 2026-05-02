import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from streamlit_autorefresh import st_autorefresh
import openai
import os

# --- 1. KONFIGURACJA I DESIGN (POWIĘKSZONY) ---
#st.set_page_config(layout="wide", page_title="Neon Ultra Terminal PRO")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    
    /* Główne karty spółek */
    .neon-card { border: 2px solid #222; padding: 25px; border-radius: 15px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 25px; }
    
    /* Karty Top 10 */
    .top-card { border: 1px solid #333; padding: 15px; border-radius: 12px; background: #0c0c1e; font-size: 1rem; line-height: 1.6; min-height: 250px; }
    
    /* Napisy i Nagłówki */
    .neon-title { color: #39FF14; font-weight: bold; font-size: 1.8rem; margin-bottom: 10px; text-shadow: 0 0 10px #39FF14; }
    .main-price { font-size: 1.5rem; font-weight: bold; color: #ffffff; }
    
    /* Bid / Ask */
    .neon-bid { color: #00FF00; font-weight: bold; font-size: 1.1rem; }
    .neon-ask { color: #FF0000; font-weight: bold; font-size: 1.1rem; }
    
    /* Sygnały */
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; font-size: 1.2rem; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; font-size: 1.2rem; }
    .signal-TRZYMAJ { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; font-size: 1.2rem; }
    
    /* Przyciski */
    .stButton>button { 
        background-color: #1a1a1a; 
        color: #39FF14; 
        border: 2px solid #39FF14; 
        width: 100%; 
        font-size: 1.1rem; 
        font-weight: bold; 
        height: 3rem;
        box-shadow: 0 0 10px #39FF1444;
    }
    
    /* Sidebar */
    .css-1d391kg { width: 350px; }
    </style>
""", unsafe_allow_html=True)

# --- ODŚWIEŻANIE ---
refresh_min = st.sidebar.slider("Odświeżanie (min)", 1, 10, 5)
st_autorefresh(interval=refresh_min * 60 * 1000, key="ultra_refresh")

if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]

# --- SILNIK ANALIZY ---
def fetch_ultra_data(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        info = tk.info
        last = df['Close'].iloc[-1]
        
        ema10 = df['Close'].ewm(span=10).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['Close'].ewm(span=200).mean().iloc[-1]
        
        t1, t2, t3 = ("W" if last > ema10 else "S"), ("W" if last > ema50 else "S"), ("W" if last > ema200 else "S")
        trend_score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi_val = 100 - (100 / (1 + (gain / loss).iloc[-1]))
        
        body = last - df['Open'].iloc[-1]
        rng = df['High'].iloc[-1] - df['Low'].iloc[-1]
        pattern = "BYCZA" if body > 0 and abs(body) > 0.6 * rng else "NIEDŹWIEDZIA" if body < 0 and abs(body) > 0.6 * rng else "NEUTRALNA"
        
        sig = "KUP" if trend_score >= 4 and rsi_val < 70 else "SPRZEDAJ" if trend_score <= -4 else "TRZYMAJ"
        s_class = f"signal-{sig}"

        return {
            "symbol": symbol, "price": last, "bid": info.get('bid', 'N/A'), "ask": info.get('ask', 'N/A'),
            "trends": f"{t1}|{t2}|{t3}", "score": trend_score, "rsi": rsi_val, "vol": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean(),
            "pattern": pattern, "signal": sig, "s_class": s_class, "pivot": (df['High'].iloc[-1] + df['Low'].iloc[-1] + last) / 3
        }
    except: return None

# --- UI GŁÓWNE ---
st.sidebar.title("💠 Sterowanie")
user_input = st.sidebar.text_area("Wklej tickery:", "HRT.WA,CFS.WA,PRT.WA,ATT.WA,STX.WA,PUR.WA,BCS.WA,KCH.WA,GTN.WALBW.WA,PGV.WA,HPE.WA,DNS.WA.ZUK.WA,VVD.WA,HIVE,MLN.WA,MER.WA,APS.WA,NVG.WA,IOVA,PLRX,HUMA,TCRX,GOSS,MREO,ADTX", height=200)
tickers = [t.strip().upper() for t in user_input.replace(",", " ").split() if t.strip()]

st.markdown("<h1 style='color:#39FF14; font-size:3rem;'>🚀 NEON KOMBAJN ULTRA AI</h1>", unsafe_allow_html=True)

if tickers:
    results = [fetch_ultra_data(t) for t in tickers if fetch_ultra_data(t)]
    
    st.subheader("🔥 TOP 10 - RADAR WYBIĆ")
    top_10 = sorted(results, key=lambda x: x['vol'], reverse=True)[:10]
    
    for i in range(0, len(top_10), 5):
        cols = st.columns(5)
        for j, item in enumerate(top_10[i:i+5]):
            with cols[j]:
                st.markdown(f"""
                <div class="top-card">
                    <div class="neon-title">{item['symbol']}</div>
                    <div class="main-price">{item['price']:.2f}</div>
                    <span class="neon-bid">B: {item['bid']}</span> | <span class="neon-ask">A: {item['ask']}</span><hr>
                    <b>Świeca:</b> {item['pattern']}<br>
                    <b>Trend:</b> {item['trends']}<br>
                    <b>Score:</b> {item['score']} | <b>RSI:</b> {item['rsi']:.1f}<br>
                    <b>Vol:</b> {item['vol']:.2f}x<br><br>
                    <div class="{item['s_class']}">{item['signal']}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 ZAPISZ RAPORT DO CSV"):
        df_save = pd.DataFrame(results)
        st.download_button("KLIKNIJ ABY POBRAĆ", df_save.to_csv(index=False), "analiza_ultra.csv", "text/csv")

    st.divider()

    # --- LISTA GŁÓWNA ---
    for data in results:
        with st.container():
            st.markdown(f"<div class='neon-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.5, 1.2, 1, 2.5])
            with c1:
                st.markdown(f"<div class='neon-title'>{data['symbol']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='main-price'>{data['price']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
            with c2:
                st.write(f"Trend: **{data['trends']}** (Score: {data['score']})")
                st.write(f"RSI: **{data['rsi']:.1f}** | Świeca: **{data['pattern']}**")
            with c3:
                st.markdown(f"<div class='{data['s_class']}'>{data['signal']}</div>", unsafe_allow_html=True)
                st.write(f"Pivot: {data['pivot']:.2f}")
            with c4:
                if st.button(f"PEŁNA ANALIZA AI 🤖", key=f"ai_{data['symbol']}"):
                    prompt = f"Analiza {data['symbol']}: Cena {data['price']}, Pivot {data['pivot']:.2f}, Trend {data['score']}, RSI {data['rsi']:.1f}, Vol {data['vol']:.2f}x. Podaj werdykt Bloomberg AI bez lania wody."
                    resp = openai.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś wojskowym terminalem giełdowm. Mówisz twardo i konkretnie."}, {"role": "user", "content": prompt}])
                    st.info(resp.choices[0].message.content)
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Wklej tickery w panelu bocznym.")
