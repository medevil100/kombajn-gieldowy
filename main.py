import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v7.7 — BUGFIXED & STABLE
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v7.7", page_icon="⚔️")

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
        if not news: return "NEUTRALNY: Brak wieści"
        headlines = [n.get('title', '') for n in news]
        prompt = f"Oceń sentyment: {headlines}. Odpowiedz TYLKO: 'BYCZY', 'NIEDŹWIEDZI' lub 'NEUTRALNY' + krótki opis."
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
        momentum = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # SYGNAŁ
        score = 0
        if rsi < 35: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 1.8: score += 2
        sig = "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 70 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "RSI": round(rsi, 2),
            "Vol x": round(vol_ratio, 2), "Sygnał": sig,
            "AI Sentiment": get_news_sentiment(symbol), "Momentum %": round(momentum, 2)
        }
    except: return None

st.title(f"⚔️ TERMINAL v7.7 — LIVE")

default_list = "HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, IOVA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
symbols = [s.strip() for s in st.sidebar.text_area("Symbole", default_list).split(",")]

results = []
for s in symbols:
    data = get_full_analysis(s)
    if data: results.append(data)

if results:
    df_res = pd.DataFrame(results)

    # --- NAPRAWIONA FUNKCJA STYLIZOWANIA ---
    def style_table(row):
        color = ''
        sent = str(row['AI Sentiment']).upper()
        
        if row['Sygnał'] == 'KUP' or "BYCZY" in sent:
            color = 'color: #00ff88'
        elif row['Sygnał'] == 'SPRZEDAJ' or "NIEDŹWIEDZI" in sent:
            color = 'color: #ff4444'
        elif "NEUTRALNY" in sent:
            color = 'color: #ffa500'
            
        return [color] * len(row) # Zwraca styl dla każdej kolumny w wierszu

    if any(df_res['Sygnał'] == 'KUP'):
        play_sound()
        st.success("🔔 Sygnał KUP!")

    st.dataframe(df_res.style.apply(style_table, axis=1), use_container_width=True)

    # --- WYKRES ---
    st.divider()
    fig = px.bar(df_res, x='Symbol', y='Momentum %', color='Momentum %', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # --- AI ---
    if client:
        try:
            res_ai = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "user", "content": f"Analiza: {df_res.to_string()}. Wybierz 2 okazje."}]
            )
            st.info(res_ai.choices[0].message.content)
        except: st.error("AI Error")
else:
    st.warning("Pobieranie...")
