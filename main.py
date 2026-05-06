import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import base64
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v7.4 — FULL AUTO + AUDIO + COLORS
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v7.4", page_icon="⚔️")

# --- AUTO REFRESH SETUP ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 10, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

# --- STYLIZACJA ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
</style>
""", unsafe_allow_html=True)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def play_sound():
    """Odtwarza dyskretny sygnał dźwiękowy (Alert)"""
    audio_html = """
    <audio autoplay>
      <source src="https://soundjay.com" type="audio/mpeg">
    </audio>
    """
    st.components.v1.html(audio_html, height=0)

def get_news_sentiment(symbol):
    if not client: return "Brak AI"
    try:
        t = yf.Ticker(symbol)
        news = t.news[:2]
        if not news: return "NEUTRALNY: Brak nowych wieści"
        headlines = [n.get('title', '') for n in news]
        prompt = f"Oceń sentyment: {headlines}. Odpowiedz TYLKO formatem: 'TYP: OPIS' (TYP to BYCZY, NIEDŹWIEDZI lub NEUTRALNY)."
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=40)
        return res.choices[0].message.content
    except: return "NEUTRALNY: Błąd"

def get_full_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty: return None
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # TECHNIKA
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        vol_ratio = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1] if df['volume'].rolling(20).mean().iloc[-1] != 0 else 1

        # SYGNAŁ
        score = 0
        if rsi < 35: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 1.8: score += 2
        sig = "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 70 else "CZEKAJ"

        return {
            "Symbol": symbol,
            "Cena": round(last_close, 3),
            "RSI": round(rsi, 2) if not np.isnan(rsi) else 50.0,
            "Vol x": round(vol_ratio, 2),
            "Sygnał": sig,
            "AI Sentiment": get_news_sentiment(symbol)
        }
    except: return None

# --- UI ---
st.title(f"⚔️ TERMINAL v7.4 — Auto-Refresh ({refresh_minutes} min)")

default_list = "HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, IOVA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
symbols = [s.strip() for s in st.sidebar.text_area("Symbole", default_list).split(",")]

# SKANOWANIE
results = []
for s in symbols:
    data = get_full_analysis(s)
    if data: results.append(data)

if results:
    df_res = pd.DataFrame(results)

    # Funkcje kolorowania
    def style_row(row):
        styles = [''] * len(row)
        # Kolor Sygnału
        if row['Sygnał'] == 'KUP': styles[4] = 'color: #00ff88; font-weight: bold'
        if row['Sygnał'] == 'SPRZEDAJ': styles[4] = 'color: #ff4444; font-weight: bold'
        # Kolor Sentymentu
        sent = row['AI Sentiment'].upper()
        if "BYCZY" in sent: styles[5] = 'color: #00ff88'
        elif "NIEDŹWIEDZI" in sent: styles[5] = 'color: #ff4444'
        elif "NEUTRALNY" in sent: styles[5] = 'color: #ffa500'
        return styles

    # Sprawdzenie czy puścić dźwięk (czy jest KUP)
    if any(df_res['Sygnał'] == 'KUP'):
        play_sound()
        st.success("🔔 Wykryto sygnał KUP! (Dźwięk alertu)")

    st.dataframe(df_res.style.apply(style_row, axis=1), use_container_width=True)
else:
    st.warning("Oczekiwanie na dane...")
