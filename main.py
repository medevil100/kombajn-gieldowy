# app.py - TERMINAL v15 ULTRA (zmodyfikowane)
import logging
import re
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import ta

# ============================================================
# KONFIGURACJA APLIKACJI
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v15 ULTRA", page_icon="⚔️")

# ============================================================
# LOGGER
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("terminal")

# ============================================================
# UI — (CSS pozostawione bez zmian, wklej swoje style)
# ============================================================
st.markdown("""
<style>
/* TWÓJ CSS BEZ ZMIAN */
</style>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

st.sidebar.header("🤖 MODEL AI")
model_choice = st.sidebar.selectbox(
    "Wybierz model",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini"],
    index=0
)

st.sidebar.header("🎨 Styl tabeli")
table_style = st.sidebar.radio(
    "Wybierz styl:",
    ["Kolor wiersza (RSI)", "Gradient RSI", "Ikony ↑↓"],
    index=0
)

# ============================================================
# OPENAI CLIENT
# ============================================================
OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_KEY)

# ============================================================
# FUNKCJE POMOCNICZE
# ============================================================

@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        return float(data['Close'].iloc[-1])
    except Exception as e:
        logger.info(f"Nie udało się pobrać kursu USD/PLN: {e}")
        return 4.0

USD_PLN = get_usd_pln()

def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = [n.get('title', '') for n in t.news[:2]]
        return " | ".join(news) if news else "Brak newsów."
    except Exception as e:
        logger.info(f"get_beast_news error for {symbol}: {e}")
        return "Brak danych."

def safe_last(series):
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) > 0 else np.nan

def is_pln(sym):
    # traktuj tickery z końcówką .WA jako PLN; możesz rozszerzyć regułę
    return sym.upper().endswith(".WA")

# ============================================================
# ANALIZA SYMBOLI
# ============================================================

def analyze_symbol(symbol):
    try:
        logger.info(f"Analizuję {symbol}")
        t = yf.Ticker(symbol)
        df = t.history(period="3mo")

        if df.empty or len(df) < 10:
            logger.info(f"Za mało danych dla {symbol}")
            return None

        last_p = safe_last(df['Close'])
        if np.isnan(last_p):
            return None

        # RSI
        try:
            rsi_series = ta.momentum.RSIIndicator(close=df['Close'], window=14).rsi()
            rsi_value = float(rsi_series.dropna().iloc[-1]) if len(rsi_series.dropna())>0 else np.nan
        except Exception:
            rsi_value = np.nan

        # Momentum 10d
        if len(df['Close'].dropna()) > 10:
            mom = ((last_p - df['Close'].iloc[-10]) / df['Close'].iloc[-10]) * 100
        else:
            mom = np.nan

        # EMA trend
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1] if len(df['Close'].dropna())>=20 else np.nan
        ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1] if len(df['Close'].dropna())>=50 else np.nan
        ema_trend = int(not np.isnan(ema20) and not np.isnan(ema50) and ema20 > ema50)

        # MACD
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_last = float(macd.dropna().iloc[-1]) if len(macd.dropna())>0 else np.nan
        signal_last = float(signal.dropna().iloc[-1]) if len(signal.dropna())>0 else np.nan
        macd_trend = int(not np.isnan(macd_last) and not np.isnan(signal_last) and macd_last > signal_last)

        # Volatility
        vol10 = df['Close'].pct_change().rolling(10).std().iloc[-1] * 100 if len(df['Close'].dropna())>=10 else np.nan

        # Volume surge
        vol_now = safe_last(df['Volume'])
        vol_avg = df['Volume'].rolling(20).mean().iloc[-1] if len(df['Volume'].dropna())>=20 else np.nan
        vol_surge = round((vol_now / vol_avg) * 100, 1) if vol_avg and not np.isnan(vol_avg) and vol_avg > 0 else np.nan

        # High/Low 20
        high20 = df['High'].rolling(20).max().iloc[-1] if len(df['High'].dropna())>=20 else np.nan
        low20 = df['Low'].rolling(20).min().iloc[-1] if len(df['Low'].dropna())>=20 else np.nan

        dist_high20 = round((last_p / high20 - 1) * 100, 2) if not np.isnan(high20) and high20>0 else np.nan
        dist_low20 = round((last_p / low20 - 1) * 100, 2) if not np.isnan(low20) and low20>0 else np.nan

        news = get_beast_news(symbol)

        # scoring
        score = 0
        if not np.isnan(rsi_value):
            if rsi_value < 30: score += 25
            elif rsi_value < 40: score += 15
            elif rsi_value > 70: score -= 20

        if not np.isnan(mom):
            if mom > 5: score += 15
            elif mom < -5: score += 10

        score += 15 if ema_trend else -5
        if macd_trend: score += 15

        if not np.isnan(vol_surge):
            if vol_surge > 150: score += 15
            elif vol_surge > 100: score += 8

        if not np.isnan(dist_low20) and dist_low20 < 5: score += 10
        if not np.isnan(dist_high20) and dist_high20 > -5: score -= 10

        score = max(0, min(100, score))

        if score >= 70: signal_tag = "BUY"
        elif score <= 30: signal_tag = "SELL"
        else: signal_tag = "NEUTRAL"

        return {
            "Symbol": symbol,
            "Cena": round(last_p, 2),
            "RSI": round(rsi_value, 1) if not np.isnan(rsi_value) else np.nan,
            "Mom% 10d": round(mom, 2) if not np.isnan(mom) else np.nan,
            "EMA20>EMA50": ema_trend,
            "MACD>Signal": macd_trend,
            "Volatility10d": round(vol10, 2) if not np.isnan(vol10) else np.nan,
            "VolumeSurge%": vol_surge,
            "DistHigh20%": dist_high20,
            "DistLow20%": dist_low20,
            "Score": int(score),
            "Signal": signal_tag,
            "News": news
        }

    except Exception as e:
        logger.exception(f"Błąd w analyze_symbol dla {symbol}: {e}")
        return None

# ============================================================
# INPUTY
# ============================================================
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area("SYMBOL,ILOŚĆ,CENA", "NVDA,1,900\nSTX.WA,100,5.0")

st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy", default_list)
symbols = [s.strip().upper() for s in re.split(r'[,\s]+', symbols_input) if s.strip()]

st.title(f"⚔️ TERMINAL v15 ULTRA — REFRESH: {refresh_val} MIN")

# ============================================================
# WYNIKI SKANOWANIA (równoległe)
# ============================================================
st.subheader("📊 Wyniki Skanowania")

def scan_symbols_parallel(symbols, max_workers=6):
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(analyze_symbol, s): s for s in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception as e:
                logger.info(f"Błąd podczas skanowania {sym}: {e}")
    return results

results_list = scan_symbols_parallel(symbols, max_workers=6)
results = pd.DataFrame(results_list)

# Stylizacja
def highlight_row_rsi(row):
    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi): return [""] * len(row)
    if rsi < 30: return ["background-color: rgba(0,120,0,0.25)"] * len(row)
    if rsi > 70: return ["background-color: rgba(120,0,0,0.25)"] * len(row)
    return [""] * len(row)

def gradient_rsi(val):
    if pd.isna(val): return ""
    v = max(0, min(float(val), 100))
    r = int(180 * (v / 100))
    g = int(180 * (1 - v / 100))
    return f"background-color: rgba({r},{g},40,0.25)"

def add_icons(df):
    df = df.copy()
    df["RSI"] = df["RSI"].apply(lambda x: f"{x} 🔻" if x < 30 else (f"{x} 🔺" if x > 70 else f"{x} ➖"))
    df["Mom% 10d"] = df["Mom% 10d"].apply(lambda x: f"{x}% 📈" if x > 0 else f"{x}% 📉")
    return df

if results.empty:
    st.info("Brak wyników do wyświetlenia. Sprawdź listę tickerów.")
else:
    if table_style == "Kolor wiersza (RSI)":
        st.dataframe(results.style.apply(highlight_row_rsi, axis=1))
    elif table_style == "Gradient RSI":
        st.dataframe(results.style.map(gradient_rsi, subset=['RSI']))
    elif table_style == "Ikony ↑↓":
        st.dataframe(add_icons(results))

    # Export CSV
    csv = results.to_csv(index=False).encode('utf-8')
    st.download_button("Pobierz wyniki CSV", data=csv, file_name="scan_results.csv", mime="text/csv")

# ============================================================
# AI — ANALIZA (ograniczony prompt)
# ============================================================
st.divider()
st.subheader(f"🤖 GENESIS AI ({model_choice}) — WYROK ZBIORCZY")

if not results.empty:
    top_for_ai = results.sort_values("Score", ascending=False).head(10).to_dict(orient="records")
else:
    top_for_ai = []

prompt = {
    "data": top_for_ai,
    "usd_pln": USD_PLN,
    "task": "Przeanalizuj Score, RSI, Momentum, Trend EMA, MACD, Volume Surge i News. Wybierz Top 3 okazje oraz 3 zagrożenia. Podaj SYMBOL - POWÓD."
}

with st.spinner("AI analizuje rynek..."):
    try:
        # Uwaga: klient OpenAI może mieć inną metodę wywołania w zależności od wersji SDK
        res_ai = client.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "Jesteś brutalnym zarządzającym funduszem hedgingowym."},
                {"role": "user", "content": str(prompt)}
            ],
            temperature=0.2
        )
        st.warning("RAPORT STRATEGICZNY:")
        st.write(res_ai.choices[0].message.content)
    except Exception as e:
        logger.info(f"Błąd AI: {e}")
        st.error(f"Błąd AI: {e}")

st.subheader("🏆 Ranking AI")

# ============================================================
# WYKRESY ŚWIECOWE
# ============================================================
st.subheader("📉 Wykresy świecowe + wolumen")

selected_symbol = st.selectbox("Wybierz ticker do wykresu", symbols)

if selected_symbol:
    t = yf.Ticker(selected_symbol)
    df_chart = t.history(period="3mo")

    if not df_chart.empty:
        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=df_chart.index,
            open=df_chart['Open'],
            high=df_chart['High'],
            low=df_chart['Low'],
            close=df_chart['Close'],
            name="Cena"
        ))

        fig.add_trace(go.Bar(
            x=df_chart.index,
            y=df_chart['Volume'],
            name="Wolumen",
            marker_color="#4444ff",
            opacity=0.3,
            yaxis="y2"
        ))

        fig.update_layout(
            template="plotly_dark",
            height=600,
            xaxis_rangeslider_visible=False,
            yaxis=dict(title="Cena"),
            yaxis2=dict(title="Wolumen", overlaying="y", side="right")
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Brak danych do wykresu dla wybranego symbolu.")

# ============================================================
# PORTFOLIO
# ============================================================
st.divider()
st.subheader(f"📈 Twoje Pozycje (Kurs USD/PLN: {round(USD_PLN, 2)})")

def parse_portfolio(text):
    tickers = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r'[,\s]+', line) if p.strip()]
        if len(parts) < 3:
            logger.info(f"Pominięto linię portfolio (niepoprawny format): {line}")
            continue
        sym, qty, b_p = parts[0].upper(), parts[1], parts[2]
        try:
            tickers[sym] = {"qty": float(qty), "buy": float(b_p)}
        except Exception:
            logger.info(f"Nie udało się sparsować linię portfolio: {line}")
            continue
    return tickers

try:
    port_data = []
    tickers = parse_portfolio(portfolio_input)

    for sym, info in tickers.items():
        t = yf.Ticker(sym)
        df_p = t.history(period="1d")
        if df_p.empty:
            logger.info(f"Brak danych dla {sym} w portfolio")
            continue

        price = safe_last(df_p["Close"])
        if np.isnan(price):
            continue

        qty = info["qty"]
        buy = info["buy"]

        cur_val = price * qty * (USD_PLN if not is_pln(sym) else 1)
        buy_val = buy * qty * (USD_PLN if not is_pln(sym) else 1)

        port_data.append({
            "Symbol": sym,
            "Cena (waluta)": price,
            "Wartość PLN": round(cur_val, 2),
            "Zysk PLN": round(cur_val - buy_val, 2)
        })

    if port_data:
        dfp = pd.DataFrame(port_data)
        st.table(dfp)
        st.metric("SUMA ZYSKU (PLN)", f"{round(sum(d['Zysk PLN'] for d in port_data), 2)} PLN")
    else:
        st.info("Brak pozycji do wyświetlenia w portfolio.")

except Exception as e:
    logger.exception(f"Błąd w sekcji portfolio: {e}")
    st.info("Oczekiwanie na poprawne dane portfolio... (Format: SYMBOL,ILOŚĆ,CENA)")

# ============================================================
# KONIEC PLIKU
# ============================================================
