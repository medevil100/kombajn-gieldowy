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
# ULTRA ENGINE v8.4 — THE BEAST (FINAL CONSOLIDATED)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v8.4 BEAST", page_icon="⚡")

# --- AUTO REFRESH CONFIG ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 10, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

# --- STYLING ---
st.markdown("""
<style>
    .stApp { background-color: #030305; color: #e0e0e0; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
    .status-kup { color: #00ff88; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- SECRETS & CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def play_sound():
    """Alert dźwiękowy dla nowych sygnałów KUP"""
    st.components.v1.html("""<audio autoplay><source src="https://soundjay.com"></audio>""", height=0)

def get_aggregated_news(symbol):
    """Newsy z Investing.com RSS + Yahoo Finance News"""
    news_text = []
    try:
        # Investing.com RSS
        feed = feedparser.parse("https://investing.com")
        relevant = [e.title for e in feed.entries if symbol.split('.')[0].upper() in e.title.upper()]
        news_text.extend(relevant)
        
        # Yahoo Finance News
        t = yf.Ticker(symbol)
        y_news = [n.get('title', '') for n in t.news[:2]]
        news_text.extend(y_news)
        
        if not news_text: return "NEUTRALNY: Brak świeżych komunikatów"
        
        if client:
            prompt = f"Oceń sentyment dla {symbol}: {news_text[:4]}. Odpowiedz TYLKO: 'TYP: OPIS' (max 10 słów)."
            res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=60)
            return res.choices[0].message.content
        return "AI Offline"
    except: return "NEUTRALNY: News lag"

def get_earnings_turbo(symbol):
    """Kalendarz wyników finansowych"""
    try:
        t = yf.Ticker(symbol)
        cal = t.calendar
        if cal is not None and not cal.empty:
            if 'Earnings Date' in cal:
                return cal['Earnings Date'].iloc[0].strftime('%Y-%m-%d')
            return str(cal.iloc[0,0]).split(' ')[0]
        return "N/A"
    except: return "N/A"

def get_full_analysis(symbol):
    """Główny silnik analityczny"""
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty or len(df) < 50: return None
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # Technika
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        
        # Vol Shock & Momentum
        avg_vol = df['volume'].tail(20).mean()
        last_vol = df['volume'].iloc[-1]
        vol_ratio = last_vol / avg_vol if avg_vol != 0 else 1
        momentum = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # Sygnał (Score system)
        score = 0
        if rsi < 38: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 2.5: score += 3 
        if momentum > 10: score += 1
        
        sig = "🔥 MOCNE KUP" if score >= 5 else "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 72 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "Sygnał": sig,
            "RSI": round(rsi, 1), "Vol Shock": f"{round(vol_ratio,1)}x",
            "Mom% (10d)": round(momentum, 2), "Earnings": get_earnings_turbo(symbol),
            "AI Verdict": get_aggregated_news(symbol)
        }
    except: return None

# --- UI INTERFACE ---
st.title("⚡ ULTRA ENGINE v8.4 — THE BEAST")

default_list = "IOVA, HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
symbols = [s.strip() for s in st.sidebar.text_area("Symbole", default_list).split(",") if s.strip()]

if st.button("ODŚWIEŻ RĘCZNIE"):
    st.rerun()

results = []
with st.spinner("Przetwarzanie danych rynkowych..."):
    for s in symbols:
        res = get_full_analysis(s)
        if res: results.append(res)

if results:
    df_res = pd.DataFrame(results)
    
    # Stylizacja tabeli
    def style_table(row):
        color = ''
        sent = str(row['AI Verdict']).upper()
        if "MOCNE" in str(row['Sygnał']) or "BYCZY" in sent: color = 'color: #00ff88; font-weight: bold'
        elif "SPRZEDAJ" in str(row['Sygnał']) or "NIEDŹWIEDZI" in sent: color = 'color: #ff4444'
        elif "NEUTRALNY" in sent: color = 'color: #ffa500'
        return [color] * len(row)

    if any("KUP" in str(s) for s in df_res['Sygnał']): play_sound()

    st.dataframe(df_res.style.apply(style_table, axis=1), use_container_width=True)

    # --- RANKING MOMENTUM ---
    st.divider()
    st.subheader("🏆 Ranking Momentum (Siła Relatywna)")
    df_sorted = df_res.sort_values(by="Mom% (10d)", ascending=True)
    fig = px.bar(df_sorted, x="Mom% (10d)", y="Symbol", orientation='h',
                 color="Mom% (10d)", color_continuous_scale='RdYlGn', text="Sygnał")
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # --- GENESIS AI FINAL ANALYSIS ---
    if client:
        st.subheader("🤖 GENESIS AI: Raport Strategiczny")
        summary = df_res.to_string()
        prompt = f"""
        Działaj jako profesjonalny analityk hedge fund. Przeanalizuj: {summary}
        1. Wytypuj lidera ('The Beast') na podstawie Vol Shock i Momentum.
        2. Czy data Earnings sugeruje rajd spekulacyjny?
        3. Oceń sentyment newsów. Krótko i brutalnie.
        """
        try:
            res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
            st.info(res_ai.choices[0].message.content)
        except Exception as e: st.error(f"AI Error: {e}")
else:
    st.warning("Oczekiwanie na dane... Sprawdź symbole.")
