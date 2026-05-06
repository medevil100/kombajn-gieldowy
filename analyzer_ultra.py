import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
import feedparser
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ULTRA ENGINE v10.0 — THE COMMAND CENTER
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v10.0", page_icon="⚔️")

# --- AUTO REFRESH ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 15, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

st.markdown("<style>.stApp { background-color: #030305; color: #e0e0e0; }</style>", unsafe_allow_html=True)

# --- SECRETS & CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# --- KONWERTER WALUT (USD -> PLN) ---
def get_usd_pln():
    try:
        return yf.Ticker("USDPLN=X").history(period="1d")['Close'].iloc[-1]
    except: return 4.0 # Fallback

USD_PLN = get_usd_pln()

# --- MODUŁ NEWSÓW ---
def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news_text = [n.get('title', '') for n in t.news[:3]]
        google_url = f"https://google.com{symbol}+stock+news&hl=en-US"
        feed = feedparser.parse(google_url)
        news_text.extend([e.title for e in feed.entries[:3]])
        return " | ".join(list(set(news_text)))[:500]
    except: return "Brak danych."

# --- UI SIDEBAR: PORTFOLIO TRACKER ---
st.sidebar.header("💰 PORTFOLIO TRACKER (PLN)")
portfolio_input = st.sidebar.text_area("Format: SYMBOL,ILOŚĆ,CENA (np. NVDA,10,800)", "NVDA,1,900\nSTX.WA,100,5.0")

def calculate_portfolio(input_text):
    data = []
    for line in input_text.split('\n'):
        if not line: continue
        try:
            sym, qty, buy_price = line.split(',')
            qty, buy_price = float(qty), float(buy_price)
            t = yf.Ticker(sym.strip())
            curr_price = t.history(period="1d")['Close'].iloc[-1]
            
            # Przeliczanie na PLN
            is_usd = ".WA" not in sym.upper()
            val_pln = (curr_price * qty * USD_PLN) if is_usd else (curr_price * qty)
            cost_pln = (buy_price * qty * USD_PLN) if is_usd else (buy_price * qty)
            profit = val_pln - cost_pln
            
            data.append({"Symbol": sym, "Ilość": qty, "Wartość PLN": round(val_pln, 2), "Zysk PLN": round(profit, 2)})
        except: continue
    return pd.DataFrame(data)

# --- ANALIZA KORELACJI Z IOVA ---
def get_iova_correlation(symbol):
    try:
        data = yf.download([symbol, "NVDA"], period="1mo", interval="1d")['Close']
        corr = data.pct_change().corr().iloc[0, 1]
        return round(corr, 2)
    except: return 0.0

# --- UI MAIN ---
st.title("⚔️ TERMINAL v10.0 — COMMAND CENTER")

# 1. WYKRES PORTFOLIO
port_df = calculate_portfolio(portfolio_input)
if not port_df.empty:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("ŁĄCZNY ZYSK/STRATA", f"{port_df['Zysk PLN'].sum()} PLN")
    with col2:
        st.dataframe(port_df, use_container_width=True)

# 2. CHAT AI "DEEP PROBE" v10.2 (ANTI-BLOCK EDITION)
st.divider()
query_sym = st.text_input("🔍 ANALIZA EKSPERCKA (np. ATT.WA, STX.WA, NVDA)", "").upper().strip()

if query_sym and st.button("URUCHOM ANALIZĘ"):
    with st.spinner(f"Przeszukuję dane dla {query_sym}..."):
        try:
            t = yf.Ticker(query_sym)
            # Używamy lżejszych metod pobierania danych, aby uniknąć Rate Limit
            history = t.history(period="1mo")
            
            # Pobieramy newsy bez t.info (bezpieczniejsze)
            news = get_beast_news(query_sym)
            
            # Tworzymy uproszczony profil finansowy z tego, co mamy w historii
            last_price = history['Close'].iloc[-1] if not history.empty else "Brak"
            month_ago = history['Close'].iloc[0] if not history.empty else "Brak"
            perf = round(((last_close - month_ago) / month_ago) * 100, 2) if isinstance(last_price, float) else "N/A"
            
            # Finanse - próbujemy pobrać, ale jeśli wywali błąd, nie przerywamy skryptu
            fin_context = "Brak szczegółowych danych fundamentalnych (Yahoo Blocked)."
            try:
                # Pobieramy tylko to, co niezbędne
                fast = t.fast_info
                fin_context = f"Cena: {last_price}, Kapitalizacja: {round(fast.get('market_cap', 0)/1e6, 2)}M, Waluta: {fast.get('currency')}"
            except:
                pass

            prompt = f"""
            ANALIZUJ SPÓŁKĘ: {query_sym}
            STATUS RYNKOWY: {fin_context}
            PERFORMANS 30 DNI: {perf}%
            NEWSY: {news}
            
            ZADANIE:
            1. Wykryj na podstawie newsów, czy spółka ma realne problemy czy to szum.
            2. Wydaj werdykt: OKAZJA czy PUŁAPKA.
            3. Napisz w 3 punktach, co teraz zrobić.
            ZASADA: Bądź brutalny, krótki i konkretny.
            """
            
            res = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[
                    {"role": "system", "content": "Jesteś bezlitosnym analitykiem. Twoim celem jest ochrona kapitału. Nie lej wody."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            st.warning(f"WYROK DLA {query_sym}:")
            st.write(res.choices[0].message.content)
            
        except Exception as e:
            st.error("Yahoo tymczasowo zablokowało zapytania o fundamenty. Spróbuj za 5 minut lub sprawdź techniczne RSI w skanerze poniżej.")


        prompt = f"""
        ANALIZUJ SPÓŁKĘ: {query_sym}
        DANE FINANSOWE: {fin_data}
        OSTATNIE NEWSY: {news}
        
        ZADANIE:
        1. Oceń fundamenty. Jeśli Dług/Kapitał > 100, ostrzeż o ryzyku.
        2. Czy wskaźnik P/E sugeruje, że jest tanio czy drogo na tle branży?
        3. Na podstawie newsów wydaj werdykt: OKAZJA czy PUŁAPKA.
        
        ZASADA: Nie lej wody. Nie pisz 'warto obserwować'. Pisz jak zarządzający funduszem, który musi podjąć decyzję w 30 sekund.
        """
        
        try:
            res = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[
                    {"role": "system", "content": "Jesteś brutalnym analitykiem fundamentalnym. Twój raport musi być krótki, techniczny i decyzyjny."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2 # Niska temperatura = zero lania wody, same fakty
            )
            st.warning(f"WYROK DLA {query_sym}:")
            st.write(res.choices[0].message.content)
        except Exception as e:
            st.error(f"Błąd AI: {e}")


# 3. GŁÓWNY SKANER
st.divider()
default_list = "IOVA, STX.WA, PGV.WA, HUMA, ATT.WA, NVDA, AAPL"
symbols = [s.strip() for s in st.sidebar.text_area("Lista Skanera", default_list).split(",") if s.strip()]

results = []
for s in symbols:
    try:
        t = yf.Ticker(s)
        df = t.history(period="1y")
        last_c = df['Close'].iloc[-1]
        corr = get_nvda_correlation(s)
        results.append({
            "Symbol": s, 
            "Cena": round(last_c, 2), 
            "NVDA Corr": corr,
            "RSI": round(100 - (100 / (1 + (df['Close'].diff().clip(lower=0).rolling(14).mean() / -df['Close'].diff().clip(upper=0).rolling(14).mean()))).iloc[-1], 2),
            "Sygnał": "KUP" if corr > 0.7 and last_c < df['Close'].rolling(50).mean().iloc[-1] else "CZEKAJ"
        })
    except: continue

if results:
    st.subheader("📊 Skaner Rynkowy & Korelacja z AI Liderem (NVDA)")
    st.table(pd.DataFrame(results))
