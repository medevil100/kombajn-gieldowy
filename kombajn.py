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
    .neon-buy { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 1px solid #39FF14; padding: 2px; border-radius: 3px; font-size: 0.8rem; }
    .neon-sell { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 1px solid #FF3131; padding: 2px; border-radius: 3px; font-size: 0.8rem; }
    .neon-bid { color: #00FF00; font-weight: bold; font-size: 0.8rem; }
    .neon-ask { color: #FF0000; font-weight: bold; font-size: 0.8rem; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 1px solid #39FF14; box-shadow: 0 0 10px #39FF14; width: 100%; }
    .top-card { border: 1px solid #333; padding: 10px; border-radius: 5px; background: #0a0a0a; margin-bottom: 10px; }
    hr { border: 0.5px solid #333; }
    </style>
""", unsafe_allow_html=True)

# --- 8. ODŚWIEŻANIE ---
refresh_min = st.sidebar.slider("Odświeżanie (min)", 1, 10, 5)
st_autorefresh(interval=refresh_min * 60 * 1000, key="market_refresh")

if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]

# --- FUNKCJE ANALITYCZNE ---
def fetch_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")
        if df.empty: return None
        info = ticker.info
        last_price = df['Close'].iloc[-1]
        
        bid = info.get('bid', 'N/A')
        ask = info.get('ask', 'N/A')
        
        sma20 = ta.sma(df['Close'], length=20).iloc[-1]
        sma50 = ta.sma(df['Close'], length=50).iloc[-1]
        sma200 = ta.sma(df['Close'], length=200).iloc[-1]
        
        t_short = "W" if last_price > sma20 else "S"
        t_mid = "W" if last_price > sma50 else "S"
        t_long = "W" if last_price > sma200 else "S"
        
        if last_price > sma50 and sma20 > sma50: signal = ("KUP", "neon-buy")
        elif last_price < sma50: signal = ("SPRZEDAJ", "neon-sell")
        else: signal = ("TRZYMAJ", "neon-hold")
        
        h52 = df['High'].tail(252).max()
        l52 = df['Low'].tail(252).min()
        pivot = (df['High'].iloc[-1] + df['Low'].iloc[-1] + df['Close'].iloc[-1]) / 3
        vol_score = df['Volume'].iloc[-1] / df['Volume'].tail(20).mean()
        
        return {
            "symbol": symbol, "price": last_price, "bid": bid, "ask": ask,
            "trends": (t_short, t_mid, t_long), "signal": signal,
            "h52": h52, "l52": l52, "pivot": pivot, "score": vol_score
        }
    except: return None

# --- UI BOCZNY ---
st.sidebar.title("💠 Sterowanie")
user_input = st.sidebar.text_area("Wklej spółki:", "HRT.WA,CFS.WA,PRT.WA,ATT.WA,STX.WA,PUR.WA,BCS.WA,KCH.WA,GTN.WALBW.WA,PGV.WA,HPE.WA,DNS.WA.ZUK.WA,VVD.WA,HIVE,MLN.WA,MER.WA,APS.WA,NVG.WA,IOVA,PLRX,HUMA,TCRX,GOSS,MREO,ADTX")
tickers = [t.strip().upper() for t in user_input.replace(",", " ").split() if t.strip()]

# --- WIDOK GŁÓWNY ---
st.markdown("<h1 class='neon-text'>TERMINAL ANALIZY AI</h1>", unsafe_allow_html=True)

if tickers:
    results = [fetch_stock_data(t) for t in tickers if fetch_stock_data(t)]
    
    # --- NOWA SEKCJA TOP 10 Z DANYMI ---
    st.subheader("🔥 TOP 10 - RADAR WYBIĆ")
    top_10 = sorted(results, key=lambda x: x['score'], reverse=True)[:10]
    
    # Wyświetlamy w dwóch rzędach po 5 dla czytelności
    for i in range(0, len(top_10), 5):
        cols = st.columns(5)
        for j, item in enumerate(top_10[i:i+5]):
            with cols[j]:
                st.markdown(f"""
                <div class="top-card">
                    <h3 style="margin:0; color:#39FF14;">{item['symbol']}</h3>
                    <div style="font-size:1.1rem; font-weight:bold;">{item['price']:.2f}</div>
                    <div style="color:gray; font-size:0.8rem;">Vol: {item['score']:.1%}</div>
                    <div class="neon-bid">B: {item['bid']}</div>
                    <div class="neon-ask">A: {item['ask']}</div>
                    <div style="font-size:0.8rem; margin-top:5px;">Trend: {item['trends'][0]}{item['trends'][1]}{item['trends'][2]}</div>
                    <div class="{item['signal'][1]}" style="margin-top:5px;">{item['signal'][0]}</div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA GŁÓWNA Z PRZYCISKIEM ANALIZY ---
    for data in results:
        with st.container():
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
            with c1:
                st.markdown(f"### {data['symbol']}")
                st.write(f"Cena: **{data['price']:.2f}**")
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
            with c2:
                st.write("Trend (K/Ś/D):")
                st.markdown(f"**{data['trends'][0]} | {data['trends'][1]} | {data['trends'][2]}**")
                st.markdown(f"<div class='{data['signal'][1]}'>{data['signal'][0]}</div>", unsafe_allow_html=True)
            with c3:
                st.markdown(f"TP: <span style='color:#39FF14'>{(data['price']*1.05):.2f}</span>", unsafe_allow_html=True)
                st.markdown(f"SL: <span style='color:#FF3131'>{(data['price']*0.97):.2f}</span>", unsafe_allow_html=True)
                st.write(f"Pivot: **{data['pivot']:.2f}**")
            with c4:
                if st.button(f"PEŁNA ANALIZA AI 🤖", key=f"ai_{data['symbol']}"):
                    with st.spinner("Generowanie raportu..."):
                        prompt = f"Analiza {data['symbol']}: Cena {data['price']}, Pivot {data['pivot']}, Trend {data['trends']}, Vol {data['score']:.2f}. Podaj konkretny raport: Trend, Wolumen, Zasięg do {data['h52']}, Rekomendacja."
                        try:
                            resp = openai.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś analitykiem technicznym."}, {"role": "user", "content": prompt}])
                            st.info(f"**RAPORT AI:**\n\n{resp.choices[0].message.content}")
                        except Exception as e: st.error(f"Błąd: {e}")
            st.divider()
