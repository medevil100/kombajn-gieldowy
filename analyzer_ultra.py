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

@st.cache_data(ttl=3600)
def get_usd_pln():
    try: 
        # Pobieramy dane i wyciągamy tylko ostatnią wartość jako float
        data = yf.Ticker("USDPLN=X").history(period="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])
        return 4.0 # Fallback jeśli puste
    except: 
        return 4.0
USD_PLN = get_usd_pln()

# ... (reszta kodu bez zmian) ...

# --- PORTFOLIO LOGIC (NAPRAWIONA DLA GOSS I INNYCH USA) ---
st.divider()
st.subheader(f"📈 Twoje Pozycje (Kurs USD/PLN: {round(USD_PLN, 2)})")
try:
    port_data = []
    for line in portfolio_input.split('\n'):
        if not line or ',' not in line: continue
        parts = line.split(',')
        sym = parts[0].strip().upper()
        qty = float(parts[1])
        b_p = float(parts[2])
        
        # Pobieramy aktualną cenę spółki
        t_ticker = yf.Ticker(sym)
        t_hist = t_ticker.history(period="1d")
        if t_hist.empty: continue
        t_p = float(t_hist['Close'].iloc[-1])
        
        # Logika waluty: jeśli brak ".WA", traktuj jako USD
        is_usd = ".WA" not in sym
        current_val_pln = (t_p * qty * USD_PLN) if is_usd else (t_p * qty)
        cost_val_pln = (b_p * qty * USD_PLN) if is_usd else (b_p * qty)
        profit = current_val_pln - cost_val_pln
        
        port_data.append({
            "Symbol": sym, 
            "Cena (waluta)": t_p,
            "Wartość PLN": round(current_val_pln, 2),
            "Zysk PLN": round(profit, 2)
        })
    
    if port_data:
        st.table(pd.DataFrame(port_data))
        st.metric("SUMA ZYSKU (PLN)", f"{round(sum(d['Zysk PLN'] for d in port_data), 2)} PLN")
except Exception as e:
    st.info("Oczekiwanie na poprawne dane portfolio... (Format: SYMBOL,ILOŚĆ,CENA)")

