import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from streamlit_autorefresh import st_autorefresh
import openai
import os

# --- 1. KONFIGURACJA I DESIGN NEONOWY ---
st.set_page_config(layout="wide", page_title="Neon AI Market Terminal")

st.markdown("""
    <style>
    body { background-color: #000000; color: #FFFFFF; }
    .stApp { background-color: #000000; }
    .neon-text { text-shadow: 0 0 10px #39FF14, 0 0 20px #39FF14; color: #39FF14; font-weight: bold; }
    .neon-buy { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 1px solid #39FF14; padding: 5px; border-radius: 5px; text-align: center; }
    .neon-sell { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 1px solid #FF3131; padding: 5px; border-radius: 5px; text-align: center; }
    .neon-hold { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; border: 1px solid #00FFFF; padding: 5px; border-radius: 5px; text-align: center; }
    .neon-bid { color: #00FF00; font-weight: bold; text-shadow: 0 0 5px #00FF00; }
    .neon-ask { color: #FF0000; font-weight: bold; text-shadow: 0 0 5px #FF0000; }
    .tp-label { color: #39FF14; font-weight: bold; }
    .sl-label { color: #FF3131; font-weight: bold; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 1px solid #39FF14; box-shadow: 0 0 10px #39FF14; width: 100%; }
    hr { border: 0.5px solid #333; }
    </style>
""", unsafe_allow_html=True)

# --- 8. ODŚWIEŻANIE ---
refresh_min = st.sidebar.slider("Odświeżanie (min)", 1, 10, 5)
st_autorefresh(interval=refresh_min * 60 * 1000, key="market_refresh")

# KLUCZ API (System Streamlit Secrets)
if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
else:
    st.sidebar.error("⚠️ Brak OPENAI_API_KEY w Secrets!")

# --- FUNKCJE ANALITYCZNE ---
def fetch_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")
        if df.empty: return None
        
        info = ticker.info
        last_price = df['Close'].iloc[-1]
        
        # 3. Bid/Ask
        bid = info.get('bid', 'N/A')
        ask = info.get('ask', 'N/A')
        
        # 4. Trendy (SMA 20, 50, 200) - Zamiana na LITERY (W / S)
        sma20 = ta.sma(df['Close'], length=20).iloc[-1]
        sma50 = ta.sma(df['Close'], length=50).iloc[-1]
        sma200 = ta.sma(df['Close'], length=200).iloc[-1]
        
        t_short = "W" if last_price > sma20 else "S"
        t_mid = "W" if last_price > sma50 else "S"
        t_long = "W" if last_price > sma200 else "S"
        
        # 9. Sygnał
        if last_price > sma50 and sma20 > sma50: signal = ("KUP", "neon-buy")
        elif last_price < sma50: signal = ("SPRZEDAJ", "neon-sell")
        else: signal = ("TRZYMAJ", "neon-hold")
        
        # 6. Szczyty/Dołki i Pivot
        h52 = df['High'].tail(252).max()
        l52 = df['Low'].tail(252).min()
        pivot = (df['High'].iloc[-1] + df['Low'].iloc[-1] + df['Close'].iloc[-1]) / 3
        
        # 2. Skok wolumenu
        vol_avg = df['Volume'].tail(20).mean()
        vol_score = df['Volume'].iloc[-1] / vol_avg
        
        return {
            "symbol": symbol, "price": last_price, "bid": bid, "ask": ask,
            "trends": (t_short, t_mid, t_long), "signal": signal,
            "h52": h52, "l52": l52, "pivot": pivot, "score": vol_score
        }
    except: return None

# --- UI BOCZNY ---
st.sidebar.title("💠 Sterowanie")
user_input = st.sidebar.text_area("Wklej spółki (oddziel spacją):", "CDR.WA PKO.WA ALE.WA AAPL NVDA TSLA BTC-USD")
tickers = [t.strip().upper() for t in user_input.replace(",", " ").split() if t.strip()]

# --- WIDOK GŁÓWNY ---
st.markdown("<h1 class='neon-text'>TERMINAL ANALIZY AI</h1>", unsafe_allow_html=True)

if tickers:
    results = []
    for t in tickers:
        data = fetch_stock_data(t)
        if data: results.append(data)
    
    # 2. TOP 10 WYBICIE
    st.subheader("🔥 Top 10 Szans (Skok Wolumenu)")
    top_10 = sorted(results, key=lambda x: x['score'], reverse=True)[:10]
    cols_top = st.columns(len(top_10))
    for i, item in enumerate(top_10):
        cols_top[i].metric(item['symbol'], f"{item['price']:.2f}", f"{item['score']:.1%} Vol")

    st.divider()

    # LISTA GŁÓWNA
    for data in results:
        with st.container():
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
            
            with c1:
                st.markdown(f"### {data['symbol']}")
                st.write(f"Cena: **{data['price']:.2f}**")
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
                st.write(f"Szczyt 52tyg: {data['h52']:.2f}")

            with c2:
                st.write("Trend (K/Ś/D):")
                # Wyświetlanie liter zamiast strzałek
                st.markdown(f"**{data['trends'][0]} | {data['trends'][1]} | {data['trends'][2]}**")
                st.markdown(f"<div class='{data['signal'][1]}'>{data['signal'][0]}</div>", unsafe_allow_html=True)
            
            with c3:
                st.markdown(f"TP: <span class='tp-label'>{(data['price']*1.05):.2f}</span>", unsafe_allow_html=True)
                st.markdown(f"SL: <span class='sl-label'>{(data['price']*0.97):.2f}</span>", unsafe_allow_html=True)
                st.write(f"Pivot: **{data['pivot']:.2f}**")

            with c4:
                # 7. AI ANALIZA (BEZ LANIA WODY)
                if st.button(f"ANALIZA AI 🤖", key=f"ai_{data['symbol']}"):
                    if "OPENAI_API_KEY" not in st.secrets:
                        st.error("Błąd: Dodaj klucz w Settings -> Secrets!")
                    else:
                        with st.spinner("Werdykt AI..."):
                            prompt = f"Analiza {data['symbol']}: Cena {data['price']}, Pivot {data['pivot']}, Trend {data['trends']}, Vol Score {data['score']:.2f}. Podaj konkretny werdykt: WYBICIE TAK/NIE, powód techniczny i decyzja: KUPUJ/CZEKAJ. Max 2 zdania."
                            try:
                                resp = openai.chat.completions.create(
                                    model="gpt-4o", 
                                    messages=[
                                        {"role": "system", "content": "Mówisz krótko, konkretnie i bez uprzejmości jak terminal giełdowy."}, 
                                        {"role": "user", "content": prompt}
                                    ]
                                )
                                st.info(f"**AI:** {resp.choices[0].message.content}")
                            except Exception as e:
                                st.error(f"Błąd API: {e}")
            
            st.divider()
else:
    st.info("Wklej tickery w panelu bocznym.")
