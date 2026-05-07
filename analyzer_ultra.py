import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
from streamlit_autorefresh import st_autorefresh
import ta  # do RSI i innych wskaźników

# ============================================================
# ULTRA ENGINE v11.2 — THE SWARM + DYNAMIC REFRESH + SCORING
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v11.2", page_icon="⚔️")

# --- SIDEBAR: KONTROLA ODŚWIEŻANIA ---
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

st.markdown(
    "<style>.stApp { background-color: #030305; color: #e0e0e0; }</style>",
    unsafe_allow_html=True
)

# --- CLIENT & SECRETS ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
        return 4.0
    except:
        return 4.0

USD_PLN = get_usd_pln()

def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = [n.get("title", "") for n in t.news[:2]]
        return " | ".join(news) if news else "Brak newsów."
    except:
        return "Lagg."

# --- SIDEBAR: TRACKER & LISTA ---
st.sidebar.divider()
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area(
    "SYMBOL,ILOŚĆ,CENA",
    "NVDA,1,900\nSTX.WA,100,5.0"
)

st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy", default_list)
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

# --- MAIN UI ---
st.title(f"⚔️ TERMINAL v11.2 — REFRESH: {refresh_val} MIN")

# ============================================================
# AGRESYWNY SKAN LISTY
# ============================================================

if st.button("🚀 URUCHOM AGRESYWNY SKAN CAŁEJ LISTY"):
    results = []
    progress = st.progress(0)

    for i, s in enumerate(symbols):
        try:
            t = yf.Ticker(s)
            df = t.history(period="1mo")
            if df.empty or len(df) < 15:
                progress.progress((i + 1) / len(symbols))
                continue

            last_p = df["Close"].iloc[-1]

            # RSI z biblioteki ta (poprawne)
            rsi_series = ta.momentum.RSIIndicator(close=df["Close"], window=14).rsi()
            rsi = float(rsi_series.iloc[-1])

            # Momentum 10 dni
            if len(df) > 10:
                mom = ((last_p - df["Close"].iloc[-10]) / df["Close"].iloc[-10]) * 100
            else:
                mom = np.nan

            news = get_beast_news(s)

            # Prosty scoring: niskie RSI + dodatnie momentum
            score = 0
            if rsi < 30:
                score += 40
            elif rsi < 40:
                score += 20
            elif rsi > 70:
                score -= 30

            if not np.isnan(mom):
                if mom > 5:
                    score += 30
                elif mom < -5:
                    score -= 10

            score = max(0, min(100, score))

            results.append({
                "Symbol": s,
                "Cena": round(last_p, 2),
                "RSI": round(rsi, 1),
                "Mom% 10d": round(mom, 2) if not np.isnan(mom) else np.nan,
                "Score": int(score),
                "News": news
            })
        except:
            pass

        progress.progress((i + 1) / len(symbols))

    if results:
        df_res = pd.DataFrame(results).sort_values("Score", ascending=False)
        st.subheader("📊 Dane techniczne, Scoring i Sentyment")
        st.table(df_res)

        # ====================================================
        # AI: WYROK ZBIORCZY NA BAZIE SCORE + NEWS
        # ====================================================
        if client:
            st.divider()
            st.subheader("🤖 GENESIS AI: WYROK ZBIORCZY")

            summary = df_res.to_string(index=False)
            prompt = f"""
Jesteś brutalnym zarządzającym funduszem hedgingowym.

DANE RYNKOWE:
{summary}

KURS USD/PLN: {USD_PLN}

ZADANIE:
1. Wybierz TOP 3 OKAZJE (wysoki Score, niskie RSI, sensowne newsy).
2. Wskaż 3 NAJWIĘKSZE PUŁAPKI (wysokie RSI, słabe momentum, niepokojące newsy).
3. Dla każdej pozycji podaj:
   - SYMBOL
   - WERDYKT: KUP / OBSERWUJ / UCIEKAJ
   - KRÓTKI POWÓD (konkretnie, bez lania wody).

Odpowiedz w formie listy punktów.
"""

            with st.spinner("AI myśli..."):
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Jesteś brutalnym, bezlitosnym zarządzającym funduszem hedgingowym. Nienawidzisz ogólników."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
                st.warning("RAPORT STRATEGICZNY:")
                st.write(res.choices[0].message.content)
    else:
        st.warning("Brak wyników — sprawdź listę tickerów lub połączenie z Yahoo Finance.")

# ============================================================
# PORTFOLIO
# ============================================================

st.divider()
st.subheader(f"📈 Twoje Pozycje (Kurs USD/PLN: {round(USD_PLN, 2)})")

try:
    port_data = []
    for line in portfolio_input.split("\n"):
        if not line or "," not in line:
            continue

        parts = line.split(",")
        sym = parts[0].strip().upper()
        qty = float(parts[1])
        b_p = float(parts[2])

        t_ticker = yf.Ticker(sym)
        t_hist = t_ticker.history(period="1d")
        if t_hist.empty:
            continue

        t_p = float(t_hist["Close"].iloc[-1])

        is_usd = ".WA" not in sym
        current_val_pln = (t_p * qty * USD_PLN) if is_usd else (t_p * qty)
        cost_val_pln = (b_p * qty * USD_PLN) if is_usd else (b_p * qty)
        profit = current_val_pln - cost_val_pln

        port_data.append({
            "Symbol": sym,
            "Cena (waluta)": round(t_p, 2),
            "Wartość PLN": round(current_val_pln, 2),
            "Zysk PLN": round(profit, 2)
        })

    if port_data:
        dfp = pd.DataFrame(port_data)
        st.table(dfp)
        st.metric("SUMA ZYSKU (PLN)", f"{round(sum(d['Zysk PLN'] for d in port_data), 2)} PLN")
    else:
        st.info("Brak poprawnych pozycji w portfelu.")
except Exception:
    st.info("Oczekiwanie na poprawne dane portfolio... (Format: SYMBOL,ILOŚĆ,CENA)")
