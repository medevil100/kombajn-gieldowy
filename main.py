
### ⚔️ TERMINAL v15 ULTRA — CZĘŚĆ 1/3
### UI + konfiguracja + sidebar + podstawowe funkcje

import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import concurrent.futures
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import ta  # TA-Lib style indicators

# ============================================================
# KONFIGURACJA APLIKACJI
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v15 ULTRA", page_icon="⚔️")

# ============================================================
# UI — NEON + GLASSMORPHISM
# ============================================================

st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at top, #101020 0%, #020204 45%, #000000 100%);
    color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
}

section.main > div {
    background: rgba(5, 10, 25, 0.72);
    border-radius: 18px;
    border: 1px solid rgba(0, 234, 255, 0.18);
    box-shadow:
        0 0 25px rgba(0, 234, 255, 0.18),
        0 0 60px rgba(0, 0, 0, 0.9);
    backdrop-filter: blur(18px);
    padding: 12px 18px;
}

[data-testid="stSidebar"] {
    background: linear-gradient(160deg, rgba(5, 10, 25, 0.95), rgba(0, 0, 0, 0.98));
    border-right: 1px solid rgba(0, 234, 255, 0.25);
    box-shadow: 10px 0 30px rgba(0, 0, 0, 0.9);
}

h1, h2, h3, h4 {
    color: #00eaff !important;
    text-shadow:
        0 0 8px rgba(0, 234, 255, 0.9),
        0 0 18px rgba(0, 120, 255, 0.8),
        0 0 32px rgba(0, 234, 255, 0.7);
}

div[data-testid="stMetric"] {
    background: radial-gradient(circle at top, rgba(0, 234, 255, 0.18), rgba(0, 10, 30, 0.9));
    border: 1px solid rgba(0, 234, 255, 0.6);
    border-radius: 14px;
    padding: 10px;
    box-shadow:
        0 0 18px rgba(0, 234, 255, 0.7),
        0 0 40px rgba(0, 0, 0, 1);
}

button[kind="primary"], .stButton > button {
    background: linear-gradient(120deg, #00eaff, #0077ff);
    color: #020204 !important;
    border-radius: 999px;
    border: 1px solid rgba(0, 234, 255, 0.9);
    box-shadow:
        0 0 12px rgba(0, 234, 255, 0.9),
        0 0 30px rgba(0, 120, 255, 0.9);
    font-weight: 600;
    letter-spacing: 0.03em;
}

button[kind="primary"]:hover, .stButton > button:hover {
    transform: translateY(-1px) scale(1.01);
    box-shadow:
        0 0 18px rgba(0, 234, 255, 1),
        0 0 40px rgba(0, 120, 255, 1);
}

[data-testid="stDataFrame"] {
    background: rgba(5, 10, 25, 0.85);
    border-radius: 14px;
    border: 1px solid rgba(0, 234, 255, 0.25);
    box-shadow:
        0 0 20px rgba(0, 234, 255, 0.25),
        0 0 40px rgba(0, 0, 0, 1);
}

::-webkit-scrollbar {
    width: 8px;
}
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #00eaff, #0077ff);
    border-radius: 10px;
}

[data-baseweb="select"], .stSlider, .stTextArea, .stTextInput {
    background: rgba(5, 10, 25, 0.9) !important;
    border-radius: 10px !important;
    border: 1px solid rgba(0, 234, 255, 0.35) !important;
}

hr {
    border: none;
    height: 1px;
    background: radial-gradient(circle, rgba(0, 234, 255, 0.9), transparent);
    box-shadow: 0 0 18px rgba(0, 234, 255, 0.8);
}
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

OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_KEY)

# ============================================================
# FUNKCJE PODSTAWOWE
# ============================================================

@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        return float(data['Close'].iloc[-1])
    except:
        return 4.0

USD_PLN = get_usd_pln()

def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = [n.get('title', '') for n in t.news[:2]]
        return " | ".join(news) if news else "Brak newsów."
    except:
        return "Lagg."

# INPUTY
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area("SYMBOL,ILOŚĆ,CENA", "NVDA,1,900\nSTX.WA,100,5.0")

st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy", default_list)
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

st.title(f"⚔️ TERMINAL v15 ULTRA — REFRESH: {refresh_val} MIN")
# ============================================================
# CZĘŚĆ 2/3 — ANALIZA SYMBOLI: WSKAŹNIKI + SCORING + SYGNAŁY
# ============================================================

def analyze_symbol(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="3mo")

        if df.empty or len(df) < 20:
            return None

        last_p = df['Close'].iloc[-1]

        # ============================
        # RSI (TA-Lib style via ta)
        # ============================
        rsi_series = ta.momentum.RSIIndicator(close=df['Close'], window=14).rsi()
        rsi_value = float(rsi_series.iloc[-1])

        # ============================
        # Momentum 10d
        # ============================
        if len(df) > 10:
            mom = ((last_p - df['Close'].iloc[-10]) / df['Close'].iloc[-10]) * 100
        else:
            mom = np.nan

        # ============================
        # EMA 20 / EMA 50
        # ============================
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        ema_trend = int(ema20 > ema50)

        # ============================
        # MACD
        # ============================
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        macd_last = float(macd.iloc[-1])
        signal_last = float(signal.iloc[-1])
        macd_trend = int(macd_last > signal_last)

        # ============================
        # Volatility 10d
        # ============================
        vol10 = df['Close'].pct_change().rolling(10).std().iloc[-1] * 100

        # ============================
        # Volume Surge
        # ============================
        vol_avg = df['Volume'].rolling(20).mean().iloc[-1]
        vol_now = df['Volume'].iloc[-1]
        vol_surge = round((vol_now / vol_avg) * 100, 1) if vol_avg > 0 else np.nan

        # ============================
        # Distance from High/Low 20d
        # ============================
        high20 = df['High'].rolling(20).max().iloc[-1]
        low20 = df['Low'].rolling(20).min().iloc[-1]

        dist_high20 = round((last_p / high20 - 1) * 100, 2) if high20 > 0 else np.nan
        dist_low20 = round((last_p / low20 - 1) * 100, 2) if low20 > 0 else np.nan

        # ============================
        # NEWS
        # ============================
        news = get_beast_news(symbol)

        # ============================================================
        # SCORING 0–100
        # ============================================================
        score = 0

        # RSI
        if rsi_value < 30:
            score += 25
        elif rsi_value < 40:
            score += 15
        elif rsi_value > 70:
            score -= 20

        # Momentum
        if not np.isnan(mom):
            if mom > 5:
                score += 15
            elif mom < -5:
                score += 10

        # EMA trend
        if ema_trend == 1:
            score += 15
        else:
            score -= 5

        # MACD
        if macd_trend == 1:
            score += 15

        # Volume surge
        if not np.isnan(vol_surge):
            if vol_surge > 150:
                score += 15
            elif vol_surge > 100:
                score += 8

        # Pozycja względem low/high
        if not np.isnan(dist_low20) and dist_low20 < 5:
            score += 10
        if not np.isnan(dist_high20) and dist_high20 > -5:
            score -= 10
         # Normalizacja
    
        score = max(0, min(100, score))

        # ============================================================
        # SYGNAŁ BUY / SELL / NEUTRAL
        # ============================================================
        if score >= 70:
            signal_tag = "BUY"
        elif score <= 30:
            signal_tag = "SELL"
        else:
            signal_tag = "NEUTRAL"

        # ============================================================
        # ZWROT DANYCH
        # ============================================================
        return {
            "Symbol": symbol,
            "Cena": round(last_p, 2),
            "RSI": round(rsi_value, 1),
            "Mom% 10d": round(mom, 2) if not np.isnan(mom) else np.nan,
            "EMA20>EMA50": ema_trend,
            "MACD>Signal": macd_trend,
            "Volatility10d": round(vol10, 2),
            "VolumeSurge%": vol_surge,
            "DistHigh20%": dist_high20,
            "DistLow20%": dist_low20,
            "Score": int(score),
            "Signal": signal_tag,
            "News": news
        }

    except Exception as e:
        return None
# ============================================================
# CZĘŚĆ 3/3 — TABELA + HEATMAPA + AI + WYKRESY + PORTFOLIO
# ============================================================

# Stylizacja RSI
def highlight_row_rsi(row):
    rsi = row["RSI"]
    if pd.isna(rsi):
        return [""] * len(row)
    if rsi < 30:
        return ["background-color: rgba(0, 120, 0, 0.25)"] * len(row)
    elif rsi > 70:
        return ["background-color: rgba(120, 0, 0, 0.25)"] * len(row)
    else:
        return [""] * len(row)

def gradient_rsi(val):
    if pd.isna(val):
        return ""
    try:
        v = float(val)
    except:
        return ""
    v = max(0, min(v, 100))
    pct = v / 100.0
    r = int(180 * pct)
    g = int(180 * (1 - pct))
    return f"background-color: rgba({r},{g},40,0.25)"

def add_icons(df):
    df = df.copy()
    df["RSI"] = df["RSI"].apply(
        lambda x: f"{x} 🔻" if x < 30 else (f"{x} 🔺" if x > 70 else f"{x} ➖")
    )
    df["Mom% 10d"] = df["Mom% 10d"].apply(
lambda x: f"{x}% 📈" if x > 0 else f"{x}% 📉"
    )
    return df
# ============================================================
        # --- LINIA 366 (Początek sekcji wyświetlania) ---
        st.subheader("📊 Wyniki Skanowania")
        
        # Sprawdź czy zmienna nazywa się table_style czy tabele
        if table_style == "Standard":
            st.dataframe(results)
            
        elif table_style == "Gradient RSI":
            # Stylizacja gradientowa dla kolumny RSI
            st.dataframe(results.style.map(gradient_rsi, subset=['RSI']))

        elif table_style == "Ikony i Kolory":
            # Wykorzystuje Twoje funkcje add_icons i highlight_row_rsi
            df_with_icons = add_icons(results)
            st.dataframe(df_with_icons.style.apply(highlight_row_rsi, axis=1))

        # --- SEKCJA AI (Linia ok. 400+) ---
        st.divider()
        st.subheader(f"🤖 GENESIS AI ({model_choice}) — WYROK ZBIORCZY")

        prompt = {
            "data": results.to_dict(orient='records'),
            "usd_pln": USD_PLN,
            "task": "Przeanalizuj Score, RSI, Momentum, Trend EMA, MACD, Volume Surge i News. Wybierz Top 3 okazje oraz 3 zagrożenia. Podaj SYMBOL - POWÓD."
        }

        with st.spinner("AI analizuje rynek..."):
            try:
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
                st.error(f"Błąd AI: {e}")

        st.subheader("🏆 Ranking AI")
        # Dalsza część Twojego kodu...

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

# ============================================================
# PORTFOLIO
# ============================================================

st.divider()
st.subheader(f"📈 Twoje Pozycje (Kurs USD/PLN: {round(USD_PLN, 2)})")

try:
    port_data = []
    tickers = {}

    for line in portfolio_input.split("\n"):
        if not line or "," not in line:
            continue
        sym, qty, b_p = line.split(",")
        sym = sym.strip().upper()
        tickers[sym] = {
            "qty": float(qty),
            "buy": float(b_p)
        }

    for sym in tickers:
        t = yf.Ticker(sym)
        df_p = t.history(period="1d")
        if df_p.empty:
            continue

        price = float(df_p["Close"].iloc[-1])
        qty = tickers[sym]["qty"]
        buy = tickers[sym]["buy"]

        is_usd = ".WA" not in sym

        cur_val = price * qty * (USD_PLN if is_usd else 1)
        buy_val = buy * qty * (USD_PLN if is_usd else 1)

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

except:
    st.info("Oczekiwanie na poprawne dane portfolio... (Format: SYMBOL,ILOŚĆ,CENA)")
