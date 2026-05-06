### ⚔️ TERMINAL v14 ULTRA — pełny plik
import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import concurrent.futures
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ============================================================
# TERMINAL v14 ULTRA — DARK PRO + NEON
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v14 ULTRA", page_icon="⚔️")

# --- DARK PRO + NEONY ---
st.markdown("""
<style>
.stApp {
    background-color: #020204;
    color: #e0e0e0;
    font-family: 'Segoe UI', sans-serif;
}

/* Neon headers */
h1, h2, h3, h4 {
    color: #00eaff !important;
    text-shadow: 0 0 10px #00eaff, 0 0 20px #00eaff;
}

/* Neon metrics */
div[data-testid="stMetric"] {
    background: rgba(0, 20, 40, 0.6);
    border: 1px solid #00eaff;
    border-radius: 10px;
    padding: 10px;
    box-shadow: 0 0 15px #00eaff;
}

/* Neon buttons */
button[kind="primary"] {
    background: linear-gradient(90deg, #00eaff, #0077ff);
    color: black !important;
    border-radius: 8px;
    box-shadow: 0 0 15px #00eaff;
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 8px;
}
::-webkit-scrollbar-thumb {
    background: #00eaff;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: AUTO REFRESH ---
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

# --- MODELE OPENAI ---
st.sidebar.header("🤖 MODEL AI")
model_choice = st.sidebar.selectbox(
    "Wybierz model",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini"],
    index=0
)

# --- STYL TABELI ---
st.sidebar.header("🎨 Styl tabeli")
table_style = st.sidebar.radio(
    "Wybierz styl:",
    ["Kolor wiersza (RSI)", "Gradient RSI", "Ikony ↑↓"],
    index=0
)

# --- OPENAI ---
OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_KEY)

# --- USD/PLN ---
@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        return float(data['Close'].iloc[-1])
    except:
        return 4.0

USD_PLN = get_usd_pln()

# --- NEWS ---
def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = [n.get('title', '') for n in t.news[:2]]
        return " | ".join(news) if news else "Brak newsów."
    except:
        return "Lagg."

# --- SIDEBAR INPUTS ---
st.sidebar.divider()
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area("SYMBOL,ILOŚĆ,CENA", "NVDA,1,900\nSTX.WA,100,5.0")

st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy", default_list)
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

# --- MAIN ---
st.title(f"⚔️ TERMINAL v14 ULTRA — REFRESH: {refresh_val} MIN")

# ============================================================
# FUNKCJE STYLIZACJI TABELI
# ============================================================

def highlight_row_rsi(row):
    rsi = row["RSI"]
    if rsi < 30:
        return ["background-color: rgba(0, 120, 0, 0.25)"] * len(row)  # ciemna zieleń
    elif rsi > 70:
        return ["background-color: rgba(120, 0, 0, 0.25)"] * len(row)  # ciemna czerwień
    else:
        return [""] * len(row)

def gradient_rsi(val):
    pct = min(max(val, 0), 100) / 100
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
# AGRESYWNY SKAN — TURBO THREADPOOL
# ============================================================

def analyze_symbol(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1mo")

        if df.empty:
            return None

        last_p = df['Close'].iloc[-1]
        delta = df['Close'].diff()

        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (up / down)))

        mom = ((last_p - df['Close'].iloc[-10]) / df['Close'].iloc[-10]) * 100

        news = get_beast_news(symbol)

        return {
            "Symbol": symbol,
            "Cena": round(last_p, 2),
            "RSI": round(rsi.iloc[-1], 1),
            "Mom% 10d": round(mom, 2),
            "News": news
        }
    except:
        return None

results = []

if st.button("🚀 URUCHOM AGRESYWNY SKAN CAŁEJ LISTY"):
    progress = st.progress(0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(analyze_symbol, s): s for s in symbols}
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            res = f.result()
            if res:
                results.append(res)
            progress.progress((i + 1) / len(symbols))

    if results:
        df_res = pd.DataFrame(results)

        st.subheader("📊 Dane techniczne i Sentyment")

        # --- PRZEŁĄCZNIK STYLU TABELI ---
        if table_style == "Kolor wiersza (RSI)":
            styled_df = df_res.style.apply(highlight_row_rsi, axis=1)
            st.dataframe(styled_df, use_container_width=True)

        elif table_style == "Gradient RSI":
            styled_df = df_res.style.applymap(gradient_rsi, subset=["RSI"])
            st.dataframe(styled_df, use_container_width=True)

        elif table_style == "Ikony ↑↓":
            df_icon = add_icons(df_res)
            st.dataframe(df_icon, use_container_width=True)

        # --- AI WYROK ---
        st.divider()
        st.subheader(f"🤖 GENESIS AI ({model_choice}) — WYROK ZBIORCZY")

        prompt = {
            "data": results,
            "usd_pln": USD_PLN,
            "task": "Wybierz Top 3 okazje (Niskie RSI + Newsy). Wskaż pułapki. Podaj SYMBOL - POWÓD."
        }

        with st.spinner("AI myśli..."):
            res_ai = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "system", "content": "Jesteś brutalnym zarządzającym funduszem."},
                    {"role": "user", "content": str(prompt)}
                ],
                temperature=0.2
            )
            st.warning("RAPORT STRATEGICZNY:")
            st.write(res_ai.choices[0].message.content)

        # --- RANKING AI ---
        st.subheader("🏆 Ranking AI (RSI + Momentum + News)")

        ranking_prompt = {
            "data": results,
            "weights": {
                "rsi_low": 0.45,
                "momentum": 0.35,
                "news_sentiment": 0.20
            },
            "task": "Zbuduj ranking 1–10. Nadaj punkty. Zwróć JSON: [{symbol, score, reason}]."
        }

        with st.spinner("AI liczy ranking..."):
            rank_res = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "system", "content": "Jesteś analitykiem kwantowym funduszu hedgingowego."},
                    {"role": "user", "content": str(ranking_prompt)}
                ],
                temperature=0.1
            )

        st.success("Ranking AI:")
        st.write(rank_res.choices[0].message.content)

# ============================================================
# WYKRESY ŚWIECOWE + WOLUMEN
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
