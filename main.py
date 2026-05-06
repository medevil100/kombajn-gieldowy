import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
import feedparser
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# ============================================================
# ULTRA ENGINE v8.3 — TURBO (DEEP DATA SCAN)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v8.3 TURBO", page_icon="⚡")

# --- AUTO REFRESH ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 10, 2)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

st.markdown("<style>.stApp { background-color: #030305; color: #e0e0e0; }</style>", unsafe_allow_html=True)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def get_deep_news(symbol):
    """Agresywne szukanie newsów: Investing RSS -> Yahoo News"""
    news_text = []
    try:
        # 1. Próba Investing RSS
        feed = feedparser.parse("https://investing.com")
        relevant = [e.title for e in feed.entries if symbol.split('.')[0].upper() in e.title.upper()]
        news_text.extend(relevant)
        
        # 2. Próba Yahoo News (zawsze dostępne dla USA)
        t = yf.Ticker(symbol)
        y_news = [n.get('title', '') for n in t.news[:3]]
        news_text.extend(y_news)
        
        if not news_text: return "NEUTRALNY: Brak świeżych wieści rynkowych"
        
        # Analiza przez AI
        prompt = f"Oceń sentyment dla {symbol} na podstawie nagłówków: {news_text[:4]}. Odpowiedz TYLKO: 'TYP: OPIS' (max 10 słów)."
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=60)
        return res.choices[0].message.content
    except: return "NEUTRALNY: News unavailable"

def get_earnings_turbo(symbol):
    """Podkręcone szukanie daty wyników"""
    try:
        t = yf.Ticker(symbol)
        # Próba 1: Kalendarz
        cal = t.calendar
        if cal is not None:
            if 'Earnings Date' in cal:
                d = cal['Earnings Date'][0]
                return d.strftime('%Y-%m-%d')
            if not cal.empty:
                return str(cal.iloc[0,0]).split(' ')[0]
        return "N/A"
    except: return "N/A"

def get_full_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty: return None
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # --- LOGIKA VOL SHOCK ---
        avg_vol = df['volume'].tail(20).mean()
        last_vol = df['volume'].iloc[-1]
        vol_ratio = last_vol / avg_vol if avg_vol != 0 else 1
        
        # --- TECHNIKA ---
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        momentum = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # --- SYGNAŁ ---
        score = 0
        if rsi < 38: score += 2  # Lekko poluzowane RSI
        if last_close > sma50: score += 1
        if vol_ratio > 2.5: score += 3 # Silniejsza waga wolumenu (Turbo)
        if momentum > 10: score += 1
        
        sig = "🔥 MOCNE KUP" if score >= 5 else "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 72 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "Sygnał": sig,
            "RSI": round(rsi, 1), "Vol Shock": f"{round(vol_ratio,1)}x",
            "Mom % (10d)": round(momentum, 2), "Earnings": get_earnings_turbo(symbol),
            "AI Verdict": get_deep_news(symbol)
        }
    except: return None

# --- UI ---
st.title("⚡ TERMINAL v8.3 — TURBO EDITION")

default_list = "IOVA, HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
symbols = [s.strip() for s in st.sidebar.text_area("Symbole", default_list).split(",") if s.strip()]

results = []
with st.spinner("Turbo-skanowanie rynków..."):
    for s in symbols:
        res = get_full_analysis(s)
        if res: results.append(res)

if results:
    df_res = pd.DataFrame(results)
    
    def style_turbo(row):
        color = ''
        sent = str(row['AI Verdict']).upper()
        if "MOCNE" in str(row['Sygnał']) or "BYCZY" in sent: color = 'color: #00ff88; font-weight: bold'
        elif "SPRZEDAJ" in str(row['Sygnał']) or "NIEDŹWIEDZI" in sent: color = 'color: #ff4444'
        elif "NEUTRALNY" in sent: color = 'color: #ffa500'
        return [color] * len(row)

    st.dataframe(df_res.style.apply(style_turbo, axis=1), use_container_width=True)

    # WYKRES
    st.divider()
    fig = px.scatter(df_res, x="RSI", y="Mom % (10d)", size="Cena", color="Sygnał", 
                     hover_name="Symbol", title="Analiza Turbo: Momentum vs RSI")
    st.plotly_chart(fig, use_container_width=True)

    # GENESIS AI
    if client:
        st.subheader("🤖 GENESIS AI: Deep Analysis")
        summary = df_res.to_string()
        prompt = f"Analiza Turbo: {summary}. Wyłap 'Volume Shock' i 'Earnings Play'. Bądź brutalnie konkretny."
        try:
            res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
            st.info(res_ai.choices[0].message.content)
        except: st.error("AI Error")
