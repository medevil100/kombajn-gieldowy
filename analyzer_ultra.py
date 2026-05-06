import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import feedparser
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v11.1 — THE SWARM + DYNAMIC REFRESH
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v11.1", page_icon="⚔️")

# --- SIDEBAR: KONTROLA ODŚWIEŻANIA ---
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
# Przeliczamy minuty na milisekundy dla wtyczki autorefresh
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

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

# --- SIDEBAR: TRACKER & LISTA ---
st.sidebar.divider()
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area("SYMBOL,ILOŚĆ,CENA", "NVDA,1,900\nSTX.WA,100,5.0")

st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy", default_list)
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

# --- MAIN UI ---
st.title(f"⚔️ TERMINAL v11.1 — REFRESH: {refresh_val} MIN")

if st.button("🚀 URUCHOM AGRESYWNY SKAN CAŁEJ LISTY"):
    results = []
    progress = st.progress(0)
    
    for i, s in enumerate(symbols):
        try:
            t = yf.Ticker(s)
            df = t.history(period="1mo")
            if df.empty: continue
            
            last_p = df['Close'].iloc[-1]
            delta = df['Close'].diff()
            rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
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
        st.subheader("📊 Dane techniczne i Sentyment")
        st.table(df_res)

        if client:
            st.divider()
            st.subheader("🤖 GENESIS AI: WYROK ZBIORCZY")
            summary = df_res.to_string()
            prompt = f"""
            PRZEANALIZUJ LISTĘ: {summary}
            USD/PLN: {USD_PLN}
            
            ZADANIE: Wybierz Top 3 okazje (Niskie RSI + Newsy). Wskaż pułapki.
            Podaj konkretny wyrok: SYMBOL - POWÓD.
            """
            with st.spinner("AI myśli..."):
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "Jesteś brutalnym zarządzającym funduszem."}, {"role": "user", "content": prompt}],
                    temperature=0.2
                )
                st.warning("RAPORT STRATEGICZNY:")
                st.write(res.choices[0].message.content)

# --- PORTFOLIO LOGIC (Zredukowane dla stabilności) ---
st.divider()
st.subheader("📈 Twoje Pozycje (Szybki Podgląd)")
try:
    port_data = []
    for line in portfolio_input.split('\n'):
        if not line or ',' not in line: continue
        sym, qty, b_p = line.split(',')
        t_p = yf.Ticker(sym.strip()).history(period="1d")['Close'].iloc[-1]
        mult = USD_PLN if ".WA" not in sym.upper() else 1
        profit = (t_p - float(b_p)) * float(qty) * mult
        port_data.append({"Symbol": sym, "Profit PLN": round(profit, 2)})
    st.table(pd.DataFrame(port_data))
except:
    st.write("Wpisz dane portfolio w boczny panel.")
