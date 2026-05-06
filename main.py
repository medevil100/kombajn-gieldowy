import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v8.0 — PROFESSIONAL ANALYTICS (BOLLINGER + ATR + AI)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v8.0", page_icon="⚔️")

# --- AUTO REFRESH ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 10, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

st.markdown("<style>.stApp { background-color: #050505; color: #e0e0e0; }</style>", unsafe_allow_html=True)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def play_sound():
    st.components.v1.html("""<audio autoplay><source src="https://soundjay.com"></audio>""", height=0)

def get_news_sentiment(symbol):
    if not client: return "NEUTRALNY: Brak AI"
    try:
        t = yf.Ticker(symbol)
        news = t.news[:2]
        if not news: return "NEUTRALNY: Brak nowych wieści"
        headlines = [n.get('title', '') for n in news]
        prompt = f"Oceń sentyment: {headlines}. Odpowiedz TYLKO: 'BYCZY', 'NIEDŹWIEDZI' lub 'NEUTRALNY' + krótki opis."
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=50)
        return res.choices[0].message.content
    except: return "NEUTRALNY: Błąd analizy"

def get_full_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty or len(df) < 50: return None
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # --- ROZBUDOWANA TECHNIKA ---
        # 1. RSI
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        
        # 2. Wstęgi Bollingera
        ma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        upper_b = ma20 + (std20 * 2)
        dist_upper = ((upper_b.iloc[-1] - last_close) / last_close) * 100

        # 3. ATR (Zmienność)
        tr = pd.concat([df['high']-df['low'], np.abs(df['high']-df['close'].shift()), np.abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # 4. Trend (SMA Cross)
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else sma50
        
        # 5. Wolumen i Momentum
        vol_ratio = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1] if df['volume'].rolling(20).mean().iloc[-1] != 0 else 1
        momentum = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # --- LOGIKA SYGNAŁU ---
        score = 0
        if rsi < 35: score += 2
        if last_close > sma50: score += 1
        if last_close > upper_b.iloc[-1]: score += 2  # Wybicie górą (siła)
        if vol_ratio > 2.0: score += 2
        
        sig = "MOCNE KUP" if score >= 5 else "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 75 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "Sygnał": sig,
            "RSI": round(rsi, 2), "Vol x": round(vol_ratio, 2),
            "Trend": "ZŁOTY KRZYŻ" if sma50 > sma200 and df['close'].rolling(50).mean().iloc[-2] <= df['close'].rolling(200).mean().iloc[-2] else ("↑ Byk" if last_close > sma200 else "↓ Miś"),
            "Do Wstęgi %": round(dist_upper, 2), "ATR": round(atr, 3),
            "AI Sentiment": get_news_sentiment(symbol), "Momentum %": round(momentum, 2)
        }
    except: return None

# --- UI ---
st.title(f"⚔️ TERMINAL v8.0 — ADVANCED MONITOR")

default_list = "HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, IOVA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
symbols = [s.strip() for s in st.sidebar.text_area("Symbole", default_list).split(",") if s.strip()]

results = []
with st.spinner("Przetwarzanie wskaźników pro..."):
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
    fig = px.bar(df_res, x='Symbol', y='Momentum %', color='Momentum %', color_continuous_scale='RdYlGn', title="Siła Relatywna (Momentum)")
    fig.update_layout(template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # --- GENESIS AI v8.0 (PROFESSIONAL DEEP DIVE) ---
    if client:
        st.subheader("🤖 GENESIS AI: Raport Strategiczny")
        prompt = f"""
        Jesteś głównym strategiem funduszu hedge. Przeanalizuj dane:
        {df_res.to_string()}

        WYMOGI RAPORTU:
        1. Wytypuj 'Lidera Wybicia' (szukaj ujemnego 'Do Wstęgi %' i wysokiego 'Vol x').
        2. Wytypuj 'Okazję z Dna' (niskie RSI + stabilizacja ceny).
        3. Wyjaśnij jak ATR wpływa na ryzyko wybranych spółek.
        4. Oceń, czy 'Złoty Krzyż' (jeśli występuje) jest wiarygodny przy obecnym sentymencie AI.
        
        Mów konkretami: 'Breakout', 'Overbought', 'Mean Reversion', 'Volatility Crush'.
        """
        try:
            res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
            st.info(res_ai.choices[0].message.content)
        except: st.error("AI Error")
else:
    st.warning("Oczekiwanie na dane...")
