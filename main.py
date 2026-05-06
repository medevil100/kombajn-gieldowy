import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np

# ============================================================
# ULTRA ENGINE v7.3 — NEWS SENTIMENT + REFRESH
# ============================================================

st.set_page_config(layout="wide", page_title="MARKET TERMINAL v7.3", page_icon="⚔️")

# --- STYLIZACJA ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
    .sentiment-positive { color: #00ff88; }
    .sentiment-negative { color: #ff4444; }
</style>
""", unsafe_allow_html=True)

# --- SECRETS & CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def get_news_sentiment(symbol):
    """Pobiera wiadomości z yfinance i analizuje sentyment przez OpenAI"""
    if not client: return "Brak AI"
    try:
        t = yf.Ticker(symbol)
        news = t.news[:3]  # Bierzemy 3 ostatnie newsy
        if not news: return "Brak wieści"
        
        headlines = [n.get('title', n.get('content', {}).get('title', '')) for n in news]
        prompt = f"Oceń sentyment tych nagłówków dla spółki {symbol} jednym słowem (Pozytywny/Negatywny/Neutralny) i krótko uzasadnij (max 10 słów). Newsy: {headlines}"
        
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )
        return res.choices[0].message.content
    except:
        return "Błąd analizy"

def get_full_analysis(symbol):
    """Pobiera dane rynkowe, mikro i sentyment"""
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty: return None

        try: info = t.info
        except: info = {}

        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # --- TECHNIKA ---
        delta = df['close'].diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (up/down))).iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        vol_ratio = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1] if df['volume'].rolling(20).mean().iloc[-1] != 0 else 1

        # --- SYGNAŁ ---
        score = 0
        if rsi < 35: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 1.8: score += 2
        sig = "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 70 else "CZEKAJ"

        # --- SENTYMENT NEWSÓW ---
        sentiment = get_news_sentiment(symbol)

        return {
            "Symbol": symbol,
            "Cena": round(last_close, 3),
            "RSI": round(rsi, 2) if not np.isnan(rsi) else 50.0,
            "Trend": "↑ Wzrost" if last_close > sma50 else "↓ Spadek",
            "Vol x": round(vol_ratio, 2),
            "Płynność (QR)": info.get('quickRatio', 'N/A'),
            "Sygnał": sig,
            "AI Sentiment": sentiment
        }
    except:
        return None

# --- INTERFEJS ---
st.title("⚔️ MARKET TERMINAL v7.3")

default_list = "HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, IOVA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
watchlist = st.sidebar.text_area("Symbole", default_list)
symbols = [s.strip() for s in watchlist.split(",")]

# --- PRZYCISK ODŚWIEŻANIA ---
if st.button("🔄 ODSWIEŻ I SKANUJ"):
    results = []
    progress_bar = st.progress(0)
    
    for i, s in enumerate(symbols):
        data = get_full_analysis(s)
        if data:
            results.append(data)
        progress_bar.progress((i + 1) / len(symbols))
    
    if results:
        df_res = pd.DataFrame(results)
        
        def color_signals(val):
            if val == 'KUP': return 'color: #00ff88; font-weight: bold;'
            if val == 'SPRZEDAJ': return 'color: #ff4444; font-weight: bold;'
            return ''

        st.subheader("📊 Analiza Techniczna i Sentyment AI")
        st.dataframe(df_res.style.map(color_signals, subset=['Sygnał']), use_container_width=True)

        # Raport AI (Genesis)
        if client:
            st.divider()
            st.subheader("🤖 GENESIS AI: Raport Strategiczny")
            summary = df_res.to_string()
            prompt = f"Przeanalizuj tabelę i sentymenty: {summary}. Wybierz 2 najciekawsze okazje spekulacyjne dnia."
            with st.spinner("Generowanie raportu..."):
                res_ai = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}]
                )
                st.info(res_ai.choices[0].message.content)
    else:
        st.error("Błąd pobierania danych.")
