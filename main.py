import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v7.6 — FINAL BEAST WITH STRENGTH CHARTS
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v7.6", page_icon="⚔️")

# --- AUTO REFRESH (1-10 MIN) ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 10, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

# --- STYLE ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
</style>
""", unsafe_allow_html=True)

# --- CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def play_sound():
    audio_html = """<audio autoplay><source src="https://soundjay.com" type="audio/mpeg"></audio>"""
    st.components.v1.html(audio_html, height=0)

def get_news_sentiment(symbol):
    if not client: return "NEUTRALNY: Brak AI"
    try:
        t = yf.Ticker(symbol)
        news = t.news[:2]
        if not news: return "NEUTRALNY: Brak nowych wieści"
        headlines = [n.get('title', '') for n in news]
        prompt = f"Oceń sentyment: {headlines}. Odpowiedz TYLKO formatem: 'TYP: OPIS' (TYP to BYCZY, NIEDŹWIEDZI lub NEUTRALNY)."
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=40)
        return res.choices[0].message.content
    except: return "NEUTRALNY: Błąd połączenia"

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
        
        # Momentum do wykresu (zmiana % z 10 dni)
        momentum = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

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
            "AI Sentiment": get_news_sentiment(symbol),
            "Momentum %": round(momentum, 2)
        }
    except: return None

# --- UI ---
st.title(f"⚔️ TERMINAL v7.6 — LIVE MONITOR")

default_list = "HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, IOVA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
watchlist = st.sidebar.text_area("Symbole (oddziel przecinkiem)", default_list)
symbols = [s.strip() for s in watchlist.split(",")]

results = []
with st.spinner("Skanowanie i analiza siły trendu..."):
    for s in symbols:
        data = get_full_analysis(s)
        if data: results.append(data)

if results:
    df_res = pd.DataFrame(results)

    def style_row(row):
        styles = [''] * len(row)
        if row['Sygnał'] == 'KUP': styles = 'color: #00ff88; font-weight: bold'
        if row['Sygnał'] == 'SPRZEDAJ': styles = 'color: #ff4444; font-weight: bold'
        sent = row['AI Sentiment'].upper()
        if "BYCZY" in sent: styles = 'color: #00ff88'
        elif "NIEDŹWIEDZI" in sent: styles = 'color: #ff4444'
        elif "NEUTRALNY" in sent: styles = 'color: #ffa500'
        return styles

    if any(df_res['Sygnał'] == 'KUP'):
        play_sound()
        st.success("🔔 ALERT: Wykryto okazje KUP!")

    st.dataframe(df_res.style.apply(style_row, axis=1), use_container_width=True)

    # --- WYKRES SIŁY TRENDU ---
    st.divider()
    st.subheader("📊 Relatywna Siła Spółek (Momentum 10-dniowe)")
    fig = px.bar(df_res, x='Symbol', y='Momentum %', color='Momentum %',
                 color_continuous_scale='RdYlGn', title="Im wyższy słupek, tym silniejszy trend wzrostowy")
    fig.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

    # --- GENESIS AI ---
    if client:
        st.subheader("🤖 GENESIS AI: Raport Strategiczny")
        summary_text = df_res.to_string()
        prompt = f"Analiza: {summary_text}. Wybierz 2 najmocniejsze spółki, uwzględniając Momentum % i Sentyment. Krótki wyrok."
        try:
            res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
            st.info(res_ai.choices[0].message.content)
        except Exception as e: st.error(f"AI Error: {e}")
else:
    st.warning("Brak danych.")
