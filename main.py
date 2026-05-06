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
# ULTRA ENGINE v8.2 — THE ORACLE (NEWS + EARNINGS)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v8.2", page_icon="⚔️")

# --- AUTO REFRESH (1-10 MIN) ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 10, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

st.markdown("<style>.stApp { background-color: #050505; color: #e0e0e0; }</style>", unsafe_allow_html=True)

# --- CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def play_sound():
    st.components.v1.html("""<audio autoplay><source src="https://soundjay.com"></audio>""", height=0)

def get_investing_news(symbol):
    """Pobiera newsy z Investing.com przez RSS i analizuje sentyment"""
    if not client: return "Brak AI"
    try:
        # Ogólny kanał wiadomości giełdowych Investing.com
        feed = feedparser.parse("https://investing.com")
        # Szukamy nagłówków zawierających ticker
        relevant = [e.title for e in feed.entries if symbol.split('.')[0].upper() in e.title.upper()]
        
        if not relevant:
            # Fallback do Yahoo Finance News przez yfinance
            t = yf.Ticker(symbol)
            relevant = [n.get('title', '') for n in t.news[:2]]
        
        if not relevant: return "NEUTRALNY: Brak wieści"
        
        prompt = f"Oceń sentyment dla {symbol}: {relevant}. Odpowiedz krótko: 'TYP: OPIS'."
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=50)
        return res.choices[0].message.content
    except: return "NEUTRALNY: Błąd RSS"

def get_earnings_date(symbol):
    """Pobiera datę najbliższych wyników finansowych"""
    try:
        t = yf.Ticker(symbol)
        calendar = t.calendar
        if calendar is not None and not calendar.empty:
            # Pobieramy datę z kalendarza (Earnings Date)
            e_date = calendar.iloc[0, 0]
            if isinstance(e_date, datetime):
                return e_date.strftime('%Y-%m-%d')
        return "N/A"
    except: return "N/A"

def get_full_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty or len(df) < 50: return None
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # TECHNIKA
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        ma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        upper_b = ma20 + (std20 * 2)
        
        vol_ratio = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1] if df['volume'].rolling(20).mean().iloc[-1] != 0 else 1
        momentum = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # EARNINGS
        earnings_date = get_earnings_date(symbol)

        # SYGNAŁ
        score = 0
        if rsi < 35: score += 2
        if last_close > upper_b.iloc[-1]: score += 2  # Wybicie
        if vol_ratio > 2.0: score += 2
        sig = "MOCNE KUP" if score >= 5 else "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 75 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "Sygnał": sig,
            "RSI": round(rsi, 2), "Vol x": round(vol_ratio, 2),
            "Momentum %": round(momentum, 2), "Earnings": earnings_date,
            "AI Sentiment": get_investing_news(symbol)
        }
    except: return None

# --- UI ---
st.title(f"⚔️ TERMINAL v8.2 — THE ORACLE")

default_list = "IOVA, HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
symbols = [s.strip() for s in st.sidebar.text_area("Symbole", default_list).split(",") if s.strip()]

results = []
with st.spinner("Skanowanie rynków i kalendarza wyników..."):
    for s in symbols:
        data = get_full_analysis(s)
        if data: results.append(data)

if results:
    df_res = pd.DataFrame(results)

    def style_table(row):
        color = ''
        sent = str(row['AI Sentiment']).upper()
        if "MOCNE KUP" in str(row['Sygnał']) or "BYCZY" in sent: color = 'color: #00ff88; font-weight: bold'
        elif "SPRZEDAJ" in str(row['Sygnał']) or "NIEDŹWIEDZI" in sent: color = 'color: #ff4444'
        elif "NEUTRALNY" in sent: color = 'color: #ffa500'
        return [color] * len(row)

    if any("KUP" in str(s) for s in df_res['Sygnał']): play_sound()

    st.dataframe(df_res.style.apply(style_table, axis=1), use_container_width=True)

    # --- WYKRES MOMENTUM ---
    st.divider()
    fig = px.bar(df_res, x='Symbol', y='Momentum %', color='Momentum %', color_continuous_scale='RdYlGn', title="Siła Relatywna")
    fig.update_layout(template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # --- GENESIS AI v8.2 ---
    if client:
        st.subheader("🤖 GENESIS AI: Raport Strategiczny")
        prompt = f"""
        Przeanalizuj dane: {df_res.to_string()}
        
        1. Czy zbliżające się daty 'Earnings' (wyniki) korelują z obecnym skokiem Momentum lub Vol x?
        2. Wybierz 2 najciekawsze setupy.
        3. Oceń newsy i sentyment. Czy dzisiejsze ruchy to plotki przed wynikami?
        Używaj: 'Insider buying', 'Gap up', 'Earnings play'.
        """
        try:
            res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
            st.info(res_ai.choices[0].message.content)
        except: st.error("AI Error")
else:
    st.warning("Oczekiwanie na dane...")
