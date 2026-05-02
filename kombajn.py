import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from streamlit_autorefresh import st_autorefresh
import openai
import os

# --- 1. KONFIGURACJA STRONY I DESIGN NEONOWY ---
st.set_page_config(layout="wide", page_title="Neon AI Market Terminal")

st.markdown("""
    <style>
    body { background-color: #000000; color: #FFFFFF; }
    .stApp { background-color: #000000; }
    .neon-text { text-shadow: 0 0 10px #39FF14, 0 0 20px #39FF14; color: #39FF14; font-weight: bold; }
    .neon-buy { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 1px solid #39FF14; padding: 5px; border-radius: 5px; }
    .neon-sell { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 1px solid #FF3131; padding: 5px; border-radius: 5px; }
    .neon-hold { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; border: 1px solid #00FFFF; padding: 5px; border-radius: 5px; }
    .tp-label { color: #39FF14; font-weight: bold; }
    .sl-label { color: #FF3131; font-weight: bold; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 1px solid #39FF14; box-shadow: 0 0 5px #39FF14; }
    </style>
""", unsafe_allow_html=True)

# --- 8. ODŚWIEŻANIE (1-10 MINUT) ---
refresh_min = st.sidebar.slider("Interwał odświeżania (min)", 1, 10, 5)
st_autorefresh(interval=refresh_min * 60 * 1000, key="market_refresh")

# --- KONFIGURACJA KLUCZA (GITHUB SECRETS) ---
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- FUNKCJE ANALITYCZNE ---
def fetch_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")
        if df.empty: return None
        
        info = ticker.info
        last_price = df['Close'].iloc[-1]
        
        # 3. Realny Bid i Ask
        bid = info.get('bid', 'N/A')
        ask = info.get('ask', 'N/A')
        
        # 4. Trendy (Krótki/Średni/Długi) na bazie SMA
        sma20 = ta.sma(df['Close'], length=20).iloc[-1]
        sma50 = ta.sma(df['Close'], length=50).iloc[-1]
        sma200 = ta.sma(df['Close'], length=200).iloc[-1]
        
        t_short = "↑" if last_price > sma20 else "↓"
        t_mid = "↑" if last_price > sma50 else "↓"
        t_long = "↑" if last_price > sma200 else "↓"
        
        # 9. Kup/Trzymaj/Sprzedaj
        if last_price > sma50 and sma20 > sma50: signal = ("KUP", "neon-buy")
        elif last_price < sma50: signal = ("SPRZEDAJ", "neon-sell")
        else: signal = ("TRZYMAJ", "neon-hold")
        
        # 6. Szczyty/Dołki 52 tyg i Pivot
        h52 = df['High'].tail(252).max()
        l52 = df['Low'].tail(252).min()
        pivot = (df['High'].iloc[-1] + df['Low'].iloc[-1] + df['Close'].iloc[-1]) / 3
        
        # 2. Szansa na wybicie (Wolumen > 1.5x średniej)
        vol_avg = df['Volume'].tail(20).mean()
        breakout_score = df['Volume'].iloc[-1] / vol_avg
        
        return {
            "symbol": symbol, "price": last_price, "bid": bid, "ask": ask,
            "trends": f"{t_short} | {t_mid} | {t_long}", "signal": signal,
            "h52": h52, "l52": l52, "pivot": pivot, "score": breakout_score
        }
    except: return None

# --- UI - PANEL BOCZNY ---
st.sidebar.title("💠 Sterowanie")
user_input = st.sidebar.text_area("Wklej spółki (np. CDR.WA, AAPL, NVDA):", "CDR.WA, PKO.WA, ALE.WA, AAPL, NVDA, TSLA")
tickers = [t.strip().upper() for t in user_input.replace(",", " ").split() if t.strip()]

# --- WIDOK GŁÓWNY ---
st.markdown("<h1 class='neon-text'>TERMINAL ANALIZY RZECZYWISTEJ</h1>", unsafe_allow_html=True)

if tickers:
    results = [fetch_stock_data(t) for t in tickers if fetch_stock_data(t)]
    
    # 2. TOP 10 WYBICIE
    st.subheader("🔥 Top 10 Spółek - Szansa na Wybicie")
    top_10 = sorted(results, key=lambda x: x['score'], reverse=True)[:10]
    cols = st.columns(len(top_10))
    for i, item in enumerate(top_10):
        cols[i].metric(item['symbol'], f"{item['price']:.2f}", f"{item['score']:.1%} Vol")

    st.divider()

    # LISTA ANALIZY
    for data in results:
        with st.container():
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            
            with c1:
                st.markdown(f"### {data['symbol']}")
                st.write(f"Cena: **{data['price']:.2f}**")
                st.write(f"Bid: `{data['bid']}` | Ask: `{data['ask']}`")
            
            with c2:
                st.write("Trend (K/Ś/D):")
                st.write(f"**{data['trends']}**")
                st.markdown(f"<span class='{data['signal'][1]}'>{data['signal'][0]}</span>", unsafe_allow_html=True)
                
            with c3:
                # 5. TP i SL (TP +5%, SL -3%)
                st.markdown(f"TP: <span class='tp-label'>{(data['price']*1.05):.2f}</span>", unsafe_allow_html=True)
                st.markdown(f"SL: <span class='sl-label'>{(data['price']*0.97):.2f}</span>", unsafe_allow_html=True)
                st.write(f"Pivot: **{data['pivot']:.2f}**")
                
            with c4:
                # 7. AI ANALIZA (BEZ LANIA WODY)
                if st.button(f"Analiza AI: {data['symbol']}", key=data['symbol']):
                    prompt = f"Analiza {data['symbol']}: Cena {data['price']}, Pivot {data['pivot']}, Trend {data['trends']}. Czy wybicie realne? Max 2 zdania."
                    try:
                        resp = openai.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                        st.info(resp.choices[0].message.content)
                    except: st.warning("Podepnij klucz OPENAI_API_KEY w Settings GitHub.")

            st.write(f"H52: {data['h52']:.2f} | L52: {data['l52']:.2f}")
            st.divider()
