import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import feedparser
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v11.0 — THE SWARM (ZBIORCZA ANALIZA AI)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v11.0", page_icon="⚔️")

# --- AUTO REFRESH (Bezpieczne 10 min) ---
st_autorefresh(interval=600000, key="datarefresh")

st.markdown("<style>.stApp { background-color: #030305; color: #e0e0e0; }</style>", unsafe_allow_html=True)

# --- CLIENT & SECRETS ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

@st.cache_data(ttl=3600)
def get_usd_pln():
    try: return yf.download("USDPLN=X", period="1d", interval="1m")['Close'].iloc[-1]
    except: return 4.0
USD_PLN = get_usd_pln()

def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = [n.get('title', '') for n in t.news[:2]]
        return " | ".join(news) if news else "Brak newsów."
    except: return "Lagg."

# --- SIDEBAR: TRACKER ---
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area("SYMBOL,ILOŚĆ,CENA", "NVDA,1,900\nSTX.WA,100,5.0")

# --- MAIN UI ---
st.title("⚔️ TERMINAL v11.0 — THE SWARM")

# GŁÓWNA LISTA SKANERA
st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy", default_list)
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

if st.button("🚀 URUCHOM AGRESYWNY SKAN CAŁEJ LISTY"):
    results = []
    progress = st.progress(0)
    
    for i, s in enumerate(symbols):
        try:
            t = yf.Ticker(s)
            df = t.history(period="1mo")
            if df.empty: continue
            
            last_p = df['Close'].iloc[-1]
            # RSI
            delta = df['Close'].diff()
            rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
            # Momentum 10d
            mom = ((last_p - df['Close'].iloc[-10]) / df['Close'].iloc[-10]) * 100
            
            news = get_beast_news(s)
            
            results.append({
                "Symbol": s,
                "Cena": round(last_p, 2),
                "RSI": round(rsi, 1),
                "Mom% 10d": round(mom, 2),
                "News": news
            })
        except: continue
        progress.progress((i + 1) / len(symbols))

    if results:
        df_res = pd.DataFrame(results)
        
        # Wyświetlanie Tabeli
        st.subheader("📊 Dane techniczne i Sentyment")
        st.table(df_res)

        # --- ZBIORCZY WYROK AI ---
        if client:
            st.divider()
            st.subheader("🤖 GENESIS AI: WYROK ZBIORCZY")
            
            # Przekazujemy całą tabelę do AI
            summary = df_res.to_string()
            prompt = f"""
            PRZEANALIZUJ CAŁĄ LISTĘ:
            {summary}
            
            ZADANIE:
            1. Wybierz 2-3 spółki, które mają najlepszą korelację 'Niskie RSI + Dobre Newsy'.
            2. Wskaż, które spółki to 'pułapki' (wysokie RSI, brak newsów).
            3. Uwzględnij kurs USD/PLN ({USD_PLN}) - czy opłaca się dziś pchać w USA czy zostać w PLN (WA)?
            
            Bądź brutalny. Mów konkretnie: SYMBOL - POWÓD.
            """
            
            with st.spinner("AI przetwarza całą listę..."):
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "Jesteś agresywnym zarządzającym funduszem."}, {"role": "user", "content": prompt}],
                    temperature=0.2
                )
                st.warning("RAPORT STRATEGICZNY:")
                st.write(res.choices[0].message.content)

# --- PORTFOLIO DASHBOARD ---
st.divider()
st.subheader("📈 Twoje Pozycje")
# (Tutaj logika kalkulacji portfolio z v10.3)
