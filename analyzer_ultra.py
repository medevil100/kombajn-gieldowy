import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
import feedparser
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v9.2 — THE HARD TRUTH (FIXED DATA INJECTION)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v9.2", page_icon="⚔️")

# --- AUTO REFRESH ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 15, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

st.markdown("<style>.stApp { background-color: #030305; color: #e0e0e0; }</style>", unsafe_allow_html=True)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# --- BAZA WIEDZY SPECJALISTYCZNEJ (Fakty wymuszone) ---
SPECIAL_DATA = {
    "IOVA": {"event": "🔥 WYNIKI: 07.05 (BMO)", "info": "Raport Q1 przed sesją USA. Gra pod Amtagvi."},
    "STX.WA": {"event": "💰 DYWIDENDA: 0.73 PLN", "info": "Rekordowa wypłata. Stopa >20%. Akumulacja pod dochód."},
    "PGV.WA": {"event": "🚀 POMPA VOL", "info": "Potężny Vol Shock 6x. Agresywne zbieranie z rynku."},
    "HUMA": {"event": "⚠️ PRZEGRZANIE", "info": "RSI > 75 bez wolumenu. Klasyczna pułapka."}
}

def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news_text = [n.get('title', '') for n in t.news[:2]]
        clean_sym = symbol.split('.')[0]
        feed = feedparser.parse(f"https://google.com{clean_sym}+stock+news&hl=en-US")
        news_text.extend([e.title for e in feed.entries[:3]])
        news_text = list(set([n for n in news_text if n]))
        
        if not news_text: return "Brak świeżych depesz."
        
        if client:
            prompt = f"Oceń sentyment dla {symbol}: {news_text[:4]}. Krótko: TYP: OPIS (max 8 słów)."
            res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=50)
            return res.choices[0].message.content
        return "AI Offline"
    except: return "Lokalny szum informacyjny."

def get_full_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty or len(df) < 30: return None
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # Wskaźniki
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        vol_ratio = df['volume'].iloc[-1] / df['volume'].tail(20).mean() if df['volume'].tail(20).mean() != 0 else 1
        mom = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # Wstrzykiwanie danych specjalnych
        spec = SPECIAL_DATA.get(symbol.upper(), {"event": "N/A", "info": "Brak danych krytycznych"})

        score = 0
        if rsi < 40: score += 2
        if vol_ratio > 2.5: score += 3 
        if mom > 10: score += 1
        sig = "🔥 MOCNE KUP" if score >= 5 else "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 72 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "Sygnał": sig,
            "RSI": round(rsi, 1), "Vol Shock": f"{round(vol_ratio,1)}x",
            "Wydarzenie": spec["event"], "Kontekst": spec["info"],
            "AI Verdict": get_beast_news(symbol)
        }
    except: return None

# --- UI ---
st.title("⚡ TERMINAL v9.2 — THE HARD TRUTH")

default_list = "IOVA, STX.WA, PGV.WA, HUMA, HRT.WA, CFS.WA, PRT.WA, ATT.WA, PUR.WA, BCS.WA, KCH.WA, HPE.WA, VVD.WA, HIVE, APS.WA, NVG.WA, PLRX, TCRX, GOSS, MREO, ADTX"
symbols = [s.strip() for s in st.sidebar.text_area("Lista", default_list).split(",") if s.strip()]

results = [get_full_analysis(s) for s in symbols if get_full_analysis(s)]

if results:
    df_res = pd.DataFrame(results)
    
    def style_table(row):
        color = ''
        if "MOCNE" in str(row['Sygnał']): color = 'color: #00ff88; font-weight: bold'
        elif "SPRZEDAJ" in str(row['Sygnał']): color = 'color: #ff4444'
        return [color] * len(row)

    st.dataframe(df_res.style.apply(style_table, axis=1), use_container_width=True)

    if client:
        st.subheader("🤖 GENESIS AI: Brutalny Wyrok")
        prompt = f"""
        DANE: {df_res.to_string()}
        
        ZADANIA:
        1. STX.WA: Skomentuj dywidendę 0.73 zł. Czy przy obecnym RSI to 'Darmowy pieniądz' czy pułapka?
        2. IOVA: Jutro wyniki. Na podstawie Vol Shock i Mom%, oceń czy insiderzy już wiedzą, że będzie dobrze?
        3. PGV.WA: Vol Shock 6x - czy to jest Peak (koniec) czy Breakout (początek)?
        
        Bądź brutalny. Zakaz lania wody. Pisz jak trader, nie jak doradca.
        """
        res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "Jesteś bezlitosnym selekcjonerem akcji. Mówisz tylko o konkretach."}, {"role": "user", "content": prompt}])
        st.info(res_ai.choices[0].message.content)
