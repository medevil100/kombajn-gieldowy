import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
import feedparser
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v10.3 — THE COMMAND CENTER (STABLE & BUG-FREE)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v10.3", page_icon="⚔️")

# --- AUTO REFRESH (Zwiększono domyślnie, by uniknąć blokad) ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 2, 15, 10)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

st.markdown("<style>.stApp { background-color: #030305; color: #e0e0e0; }</style>", unsafe_allow_html=True)

# --- SECRETS & CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# --- BEZPIECZNY KONWERTER WALUT ---
@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.download("USDPLN=X", period="1d", interval="1m")
        return data['Close'].iloc[-1]
    except: return 4.0

USD_PLN = get_usd_pln()

def get_beast_news(symbol):
    news_text = []
    try:
        t = yf.Ticker(symbol)
        # Yahoo News
        news_text.extend([n.get('title', '') for n in t.news[:2]])
        # Google News
        clean_sym = symbol.split('.')[0]
        feed = feedparser.parse(f"https://google.com{clean_sym}+stock+news&hl=en-US")
        news_text.extend([e.title for e in feed.entries[:2]])
        return " | ".join(list(set(news_text)))
    except: return "Brak świeżych depesz."

# --- SIDEBAR: PORTFOLIO TRACKER ---
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area("Format: SYMBOL,ILOŚĆ,KOSZT_KUPNA", "NVDA,1,900\nSTX.WA,100,5.0")

def calculate_portfolio(input_text):
    data = []
    for line in input_text.split('\n'):
        if not line or ',' not in line: continue
        try:
            parts = line.split(',')
            sym = parts[0].strip().upper()
            qty = float(parts[1])
            buy_p = float(parts[2])
            
            t = yf.Ticker(sym)
            curr_p = t.history(period="1d")['Close'].iloc[-1]
            
            is_usd = ".WA" not in sym
            val_pln = (curr_p * qty * USD_PLN) if is_usd else (curr_p * qty)
            cost_pln = (buy_p * qty * USD_PLN) if is_usd else (buy_p * qty)
            
            data.append({"Symbol": sym, "Wartość PLN": round(val_pln, 2), "Zysk PLN": round(val_pln - cost_pln, 2)})
        except: continue
    return pd.DataFrame(data)

# --- UI MAIN ---
st.title("⚔️ TERMINAL v10.3 — COMMAND CENTER")

port_df = calculate_portfolio(portfolio_input)
if not port_df.empty:
    c1, c2 = st.columns([1, 2])
    c1.metric("ŁĄCZNY ZYSK (PLN)", f"{round(port_df['Zysk PLN'].sum(), 2)} PLN")
    c2.dataframe(port_df, use_container_width=True)

# --- DEEP PROBE (BEZPIECZNY) ---
st.divider()
query_sym = st.text_input("🔍 ANALIZA EKSPERCKA AI (np. ATT.WA, IOVA)", "").upper().strip()

if query_sym and st.button("URUCHOM ANALIZĘ"):
    with st.spinner("Prześwietlam..."):
        try:
            t = yf.Ticker(query_sym)
            hist = t.history(period="1mo")
            news_content = get_beast_news(query_sym)
            
            # Parametry techniczne zamiast blokowanych fundamentalnych
            last_p = hist['Close'].iloc[-1] if not hist.empty else 0
            start_p = hist['Close'].iloc[0] if not hist.empty else 0
            change = round(((last_p - start_p) / start_p) * 100, 2) if start_p != 0 else 0
            
            prompt = f"""
            ANALIZA: {query_sym}
            CENA: {last_p}
            ZMIANA 30D: {change}%
            NEWSY: {news_content}
            
            ZADANIE: Wykryj czy to OKAZJA czy PUŁAPKA. Podaj 3 twarde argumenty. Nie lej wody.
            """
            
            if client:
                res = client.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=[{"role": "system", "content": "Jesteś brutalnym analitykiem."}, {"role": "user", "content": prompt}],
                    temperature=0.2
                )
                st.warning(f"WERDYKT DLA {query_sym}:")
                st.write(res.choices[0].message.content)
        except:
            st.error("Błąd pobierania danych. Sprawdź symbol lub spróbuj później.")

# --- SKANER ---
st.divider()
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL"
symbols = [s.strip() for s in st.sidebar.text_area("Skaner", default_list).split(",") if s.strip()]

res_list = []
for s in symbols:
    try:
        t = yf.Ticker(s)
        df = t.history(period="1mo")
        if df.empty: continue
        c = df['Close'].iloc[-1]
        rsi = 100 - (100 / (1 + (df['Close'].diff().clip(lower=0).rolling(14).mean() / -df['Close'].diff().clip(upper=0).rolling(14).mean()))).iloc[-1]
        res_list.append({"Symbol": s, "Cena": round(c, 2), "RSI": round(rsi, 1)})
    except: continue

if res_list:
    st.table(pd.DataFrame(res_list))
