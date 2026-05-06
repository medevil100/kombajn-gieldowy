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
# ULTRA ENGINE v8.5 — THE ORACLE FINAL (MULTI-NEWS + EARNINGS)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v8.5 ORACLE", page_icon="⚔️")

# --- AUTO REFRESH (1-10 MIN) ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 10, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

# --- STYLE ---
st.markdown("<style>.stApp { background-color: #030305; color: #e0e0e0; }</style>", unsafe_allow_html=True)

# --- CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def play_sound():
    st.components.v1.html("""<audio autoplay><source src="https://soundjay.com"></audio>""", height=0)

def get_aggregated_news(symbol):
    """Agresywne szukanie: Yahoo + Google News RSS"""
    news_text = []
    try:
        # 1. Yahoo Finance News
        t = yf.Ticker(symbol)
        news_text.extend([n.get('title', '') for n in t.news[:2]])

        # 2. Google News RSS (zabezpieczenie przed brakiem danych)
        clean_sym = symbol.split('.')[0]
        google_url = f"https://news.google.com/rss/search?q={clean_sym}+stock+news&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(google_url)
        news_text.extend([e.title for e in feed.entries[:3]])
        
        # Filtrowanie i analiza AI
        news_text = list(set([n for n in news_text if n]))
        if not news_text: return "NEUTRALNY: Brak komunikatów"
        
        if client:
            prompt = f"Przeanalizuj newsy dla {symbol}: {news_text[:5]}. Czy są 'Bycze' pod wyniki? Odpowiedz: 'TYP: OPIS'."
            res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=60)
            return res.choices[0].message.content
        return "AI Offline"
    except: return "NEUTRALNY: News lag"

def get_earnings_date(symbol):
    """Kalendarz wyników finansowych (Earnings)"""
    try:
        t = yf.Ticker(symbol)
        cal = t.calendar
        if cal is not None and not cal.empty:
            # Poprawione pobieranie daty (Earnings Date)
            e_date = cal.loc['Earnings Date'] if 'Earnings Date' in cal.index else cal.iloc[0, 0]
            if isinstance(e_date, list): e_date = e_date[0]
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
        
        # Technika
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        
        # Vol Shock & Momentum
        avg_vol = df['volume'].tail(20).mean()
        vol_ratio = df['volume'].iloc[-1] / avg_vol if avg_vol != 0 else 1
        momentum = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # Sygnał
        score = 0
        if rsi < 40: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 2.5: score += 3
        if momentum > 10: score += 1
        
        sig = "🔥 MOCNE KUP" if score >= 5 else "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 70 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "Sygnał": sig,
            "RSI": round(rsi, 1), "Vol Shock": f"{round(vol_ratio,1)}x",
            "Mom% (10d)": round(momentum, 2), "Earnings": get_earnings_date(symbol),
            "AI Verdict": get_aggregated_news(symbol)
        }
    except: return None

# --- INTERFEJS ---
st.title(f"⚔️ TERMINAL v8.5 — THE ORACLE")

default_list = "IOVA, HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
watchlist = st.sidebar.text_area("Symbole", default_list)
symbols = [s.strip() for s in watchlist.split(",") if s.strip()]

if st.button("ODŚWIEŻ RĘCZNIE"): st.rerun()

results = []
with st.spinner("Turbo-skanowanie rynków i newsów..."):
    for s in symbols:
        data = get_full_analysis(s)
        if data: results.append(data)

if results:
    df_res = pd.DataFrame(results)
    
    def style_row(row):
        color = ''
        sent = str(row['AI Verdict']).upper()
        if "MOCNE" in str(row['Sygnał']) or "BYCZY" in sent: color = 'color: #00ff88; font-weight: bold'
        elif "SPRZEDAJ" in str(row['Sygnał']) or "NIEDŹWIEDZI" in sent: color = 'color: #ff4444'
        elif "NEUTRALNY" in sent: color = 'color: #ffa500'
        return [color] * len(row)

    if any("KUP" in str(s) for s in df_res['Sygnał']): play_sound()

    st.dataframe(df_res.style.apply(style_row, axis=1), use_container_width=True)

    # Ranking Momentum
    st.divider()
    df_sorted = df_res.sort_values(by="Mom% (10d)", ascending=True)
    fig = px.bar(df_sorted, x="Mom% (10d)", y="Symbol", orientation='h', color="Mom% (10d)", color_continuous_scale='RdYlGn', text="Sygnał")
    fig.update_layout(template="plotly_dark", height=500, title="Ranking Siły Relatywnej")
    st.plotly_chart(fig, use_container_width=True)

    # Genesis AI
    if client:
        st.subheader("🤖 GENESIS AI: Raport Strategiczny")
        prompt = f"Analiza: {df_res.to_string()}. Skoncentruj się na 'Earnings Play' dla spółek takich jak IOVA. Kto jest liderem?"
        try:
            res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
            st.info(res_ai.choices[0].message.content)
        except Exception as e: st.error(f"AI Error: {e}")
