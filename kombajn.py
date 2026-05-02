import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from streamlit_autorefresh import st_autorefresh
import openai
import os
import math

# =========================
# SILNIK ULTRA — MATEMATYKA
# =========================

def calculate_rsi(closes, period=14):
    if len(closes) <= period: return 50
    delta = pd.Series(closes).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs.iloc[-1]))

def calculate_atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close'].shift(1)
    tr = pd.concat([high - low, abs(high - close), abs(low - close)], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

# --- DESIGN I STYLE NEONOWE ---
st.set_page_config(layout="wide", page_title="NEON ULTRA TERMINAL AI")

st.markdown("""
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .stApp { background-color: #050510; }
    .neon-card { border: 1px solid #222; padding: 20px; border-radius: 12px; background: #0a0a18; box-shadow: 0 0 15px #39FF1422; margin-bottom: 20px; }
    .neon-title { color: #39FF14; text-shadow: 0 0 10px #39FF14; font-weight: bold; font-size: 24px; }
    .signal-KUP { color: #39FF14; font-weight: bold; text-shadow: 0 0 10px #39FF14; border: 1px solid #39FF14; padding: 5px; border-radius: 5px; text-align: center; }
    .signal-SPRZEDAJ { color: #FF3131; font-weight: bold; text-shadow: 0 0 10px #FF3131; border: 1px solid #FF3131; padding: 5px; border-radius: 5px; text-align: center; }
    .signal-TRZYMAJ { color: #00FFFF; font-weight: bold; text-shadow: 0 0 10px #00FFFF; border: 1px solid #00FFFF; padding: 5px; border-radius: 5px; text-align: center; }
    .neon-bid { color: #00FF00; font-weight: bold; text-shadow: 0 0 5px #00FF00; }
    .neon-ask { color: #FF0000; font-weight: bold; text-shadow: 0 0 5px #FF0000; }
    .tp-label { color: #39FF14; font-weight: bold; }
    .sl-label { color: #FF3131; font-weight: bold; }
    .stButton>button { background-color: #1a1a1a; color: #39FF14; border: 1px solid #39FF14; box-shadow: 0 0 10px #39FF14; width: 100%; }
    .top-card { border: 1px solid #333; padding: 10px; border-radius: 5px; background: #0a0a0a; margin-bottom: 10px; text-align: center; }
    hr { border: 0.5px solid #333; }
    </style>
""", unsafe_allow_html=True)

# --- KONFIGURACJA ODŚWIEŻANIA ---
refresh_min = st.sidebar.slider("Odświeżanie (min)", 1, 10, 5)
st_autorefresh(interval=refresh_min * 60 * 1000, key="ultra_refresh")

if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]

# --- POBIERANIE I ANALIZA DANYCH ---
def fetch_ultra_data(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty: return None
        
        info = tk.info
        last = df['Close'].iloc[-1]
        
        # Wskaźniki Ultra
        ema10 = df['Close'].ewm(span=10).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['Close'].ewm(span=200).mean().iloc[-1]
        rsi_val = calculate_rsi(df['Close'])
        atr_val = calculate_atr(df)
        
        # Trend Score & Litery (W/S)
        t1 = "W" if last > ema10 else "S"
        t2 = "W" if last > ema50 else "S"
        t3 = "W" if last > ema200 else "S"
        trend_score = (1 if t1=="W" else -1) + (2 if t2=="W" else -2) + (3 if t3=="W" else -3)
        
        # Formacja świecy
        body = last - df['Open'].iloc[-1]
        rng = df['High'].iloc[-1] - df['Low'].iloc[-1]
        pattern = "BYCZA" if body > 0 and abs(body) > 0.6 * rng else "NIEDŹWIEDZIA" if body < 0 and abs(body) > 0.6 * rng else "NEUTRALNA"
        
        # Sygnał
        if trend_score >= 4 and rsi_val < 70: sig, s_class = "KUP", "signal-KUP"
        elif trend_score <= -4: sig, s_class = "SPRZEDAJ", "signal-SPRZEDAJ"
        else: sig, s_class = "TRZYMAJ", "signal-TRZYMAJ"

        return {
            "symbol": symbol, "price": last, "bid": info.get('bid', 'N/A'), "ask": info.get('ask', 'N/A'),
            "trends": (t1, t2, t3), "trend_score": trend_score, "rsi": rsi_val, "atr": atr_val,
            "pattern": pattern, "signal": sig, "s_class": s_class,
            "h52": df['High'].max(), "l52": df['Low'].max(),
            "pivot": (df['High'].iloc[-1] + df['Low'].iloc[-1] + last) / 3,
            "vol_rel": df['Volume'].iloc[-1] / df['Volume'].tail(20).mean()
        }
    except: return None

# --- UI PANEL BOCZNY ---
st.sidebar.title("💠 Sterowanie")
user_input = st.sidebar.text_area("Wklej tickery (oddziel spacją):", "CDR.WA PKO.WA ALE.WA AAPL NVDA TSLA BTC-USD")
tickers = [t.strip().upper() for t in user_input.replace(",", " ").split() if t.strip()]

st.markdown("<h1 class='neon-text'>🚀 NEON KOMBAJN ULTRA AI</h1>", unsafe_allow_html=True)

if tickers:
    results = [fetch_ultra_data(t) for t in tickers if fetch_ultra_data(t)]
    
    # --- TOP 10 RADAR ---
    st.subheader("🔥 RADAR WYBIĆ ULTRA (VOL)")
    top_10 = sorted(results, key=lambda x: x['vol_rel'], reverse=True)[:10]
    for i in range(0, len(top_10), 5):
        cols = st.columns(5)
        for j, item in enumerate(top_10[i:i+5]):
            with cols[j]:
                st.markdown(f"""
                <div class="top-card">
                    <div style="color:#39FF14; font-weight:bold;">{item['symbol']}</div>
                    <div style="font-size:1.2rem;">{item['price']:.2f}</div>
                    <div style="color:#888; font-size:0.8rem;">Vol: {item['vol_rel']:.2f}x</div>
                    <div class="{item['s_class']}" style="margin-top:5px; font-size:0.7rem;">{item['signal']}</div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA GŁÓWNA ---
    for data in results:
        with st.container():
            st.markdown(f"<div class='neon-card'>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.5, 1.2, 1, 2.2])
            
            with c1:
                st.markdown(f"<div class='neon-title'>{data['symbol']}</div>", unsafe_allow_html=True)
                st.markdown(f"Cena: **{data['price']:.2f}**")
                st.markdown(f"Bid: <span class='neon-bid'>{data['bid']}</span> | Ask: <span class='neon-ask'>{data['ask']}</span>", unsafe_allow_html=True)
                st.write(f"Świeca: **{data['pattern']}**")

            with c2:
                st.write("Wskaźniki Ultra:")
                st.markdown(f"Trend (K/Ś/D): **{data['trends'][0]}|{data['trends'][1]}|{data['trends'][2]}**")
                st.write(f"Trend Score: **{data['trend_score']}**")
                st.write(f"RSI: **{data['rsi']:.1f}** | Vol: **{data['vol_rel']:.2f}x**")

            with c3:
                st.markdown(f"<div class='{data['s_class']}'>{data['signal']}</div>", unsafe_allow_html=True)
                st.markdown(f"TP: <span class='tp-label'>{(data['price']*1.05):.2f}</span>", unsafe_allow_html=True)
                st.markdown(f"SL: <span class='sl-label'>{(data['price']*0.97):.2f}</span>", unsafe_allow_html=True)
                st.write(f"Pivot: {data['pivot']:.2f}")

            with c4:
                if st.button(f"PEŁNA ANALIZA AI 🤖", key=f"ai_{data['symbol']}"):
                    with st.spinner("Generowanie raportu technicznego..."):
                        prompt = f"""
                        ANALIZA TECHNICZNA: {data['symbol']}
                        CENA: {data['price']} | PIVOT: {data['pivot']:.2f} | TREND SCORE: {data['trend_score']}
                        RSI: {data['rsi']:.1f} | VOL REL: {data['vol_rel']:.2f}x | ŚWIECA: {data['pattern']} | SZCZYT 52T: {data['h52']}

                        ZASADY:
                        1. Zakaz używania: "sugeruje", "możliwe", "warto zwrócić uwagę", "inwestorzy".
                        2. Styl: Bezlitosny, surowy terminal danych. Zero lania wody.
                        3. Format:
                           - TREND: [Ocena siły + relacja do Pivotu]
                           - MOMENTUM: [RSI vs Wykupienie + zasięg do Szczytu 52T w %]
                           - WOLUMEN: [Werdykt: Akumulacja / Brak zainteresowania]
                           - REKOMENDACJA: [KUPUJ/SPRZEDAJ/CZEKAJ + poziom SL na ATR {data['atr']:.2f}]
                        """
                        try:
                            resp = openai.chat.completions.create(
                                model="gpt-4o", 
                                messages=[
                                    {"role": "system", "content": "Jesteś wojskowym systemem analizy danych giełdowych Bloomberg. Mówisz krótko, twardo, tylko fakty techniczne."}, 
                                    {"role": "user", "content": prompt}
                                ]
                            )
                            st.info(f"**WERDYKT ULTRA AI:**\n\n{resp.choices[0].message.content}")
                        except: st.error("Sprawdź OPENAI_API_KEY w Secrets.")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Wklej symbole w panelu bocznym.")
