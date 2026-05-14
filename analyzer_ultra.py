import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import plotly.express as px
from datetime import datetime
from xtb import XTBClient

# ---------------------------------------------------------
# KONFIGURACJA
# ---------------------------------------------------------
st.set_page_config(
    page_title="GPW Momentum Screener",
    layout="wide"
)

st.title("📈 GPW Momentum Screener – akcje (day + swing)")

# ---------------------------------------------------------
# LOGOWANIE DO XTB
# ---------------------------------------------------------
st.sidebar.header("🔐 Logowanie do XTB")

login = st.sidebar.text_input("Login XTB", "")
password = st.sidebar.text_input("Hasło XTB", "", type="password")
mode = st.sidebar.selectbox("Tryb:", ["Demo", "Real"])

if st.sidebar.button("Połącz z XTB"):
    st.session_state["xtb"] = XTBClient(
        user_id=login,
        password=password,
        mode="demo" if mode == "Demo" else "real"
    )
    st.session_state["xtb"].login()
    st.sidebar.success("Połączono z XTB")

if "xtb" not in st.session_state:
    st.warning("Zaloguj się do XTB, aby pobrać dane.")
    st.stop()

xtb = st.session_state["xtb"]

# ---------------------------------------------------------
# FUNKCJE POBIERANIA DANYCH
# ---------------------------------------------------------
def get_symbols_gpw():
    symbols = xtb.get_all_symbols()
    return [
        s["symbol"]
        for s in symbols
        if s["categoryName"] == "STOCKS" and "PL" in s["currency"]
    ]

def get_ohlc(symbol: str, period="D1", candles=200):
    data = xtb.get_chart_range_request(
        symbol=symbol,
        period=period,
        start=datetime(2020, 1, 1),
        end=datetime.now()
    )
    df = pd.DataFrame(data)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.tail(candles)

# ---------------------------------------------------------
# WSKAŹNIKI
# ---------------------------------------------------------
def compute_indicators(df):
    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=14)
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    df["mom5"] = df["close"].pct_change(5)
    df["mom20"] = df["close"].pct_change(20)
    df["mom60"] = df["close"].pct_change(60)
    return df

# ---------------------------------------------------------
# SCORING
# ---------------------------------------------------------
def score_swing(row):
    score = 0
    score += row["mom20"] * 0.6 if pd.notna(row["mom20"]) else 0
    score += row["mom60"] * 0.4 if pd.notna(row["mom60"]) else 0
    score += (1 - abs(row["rsi"] - 50) / 50) * 0.5 if pd.notna(row["rsi"]) else 0
    if row["price"] > row["sma20"]: score += 0.3
    if row["price"] > row["sma50"]: score += 0.2
    return score

def score_day(row):
    score = 0
    score += row["mom5"] * 0.5 if pd.notna(row["mom5"]) else 0
    score += row["mom20"] * 0.3 if pd.notna(row["mom20"]) else 0
    score += (1 - abs(row["rsi"] - 50) / 50) * 0.7 if pd.notna(row["rsi"]) else 0
    if row["price"] > row["sma20"]: score += 0.2
    return score

def comment(row, profile):
    parts = []
    if profile == "Swing":
        parts.append(f"Momentum 20/60: {row['mom20']:.2%} / {row['mom60']:.2%}")
    else:
        parts.append(f"Momentum 5/20: {row['mom5']:.2%} / {row['mom20']:.2%}")

    parts.append(f"RSI: {row['rsi']:.1f}")

    pos = []
    pos.append("SMA20↑" if row["price"] > row["sma20"] else "SMA20↓")
    if profile == "Swing":
        pos.append("SMA50↑" if row["price"] > row["sma50"] else "SMA50↓")

    parts.append(", ".join(pos))
    return " | ".join(parts)

# ---------------------------------------------------------
# UI – MENU
# ---------------------------------------------------------
menu = st.sidebar.radio("Menu:", ["Ranking", "Szczegóły spółki"])
profile = st.sidebar.selectbox("Profil:", ["Swing", "Day"])

# ---------------------------------------------------------
# RANKING
# ---------------------------------------------------------
if menu == "Ranking":
    st.subheader(f"Ranking spółek – profil {profile}")

    limit = st.slider("Ilość spółek:", 5, 50, 20)

    symbols = get_symbols_gpw()
    rows = []

    for sym in symbols:
        df = get_ohlc(sym)
        df = compute_indicators(df)
        last = df.iloc[-1]

        row = {
            "symbol": sym,
            "price": last["close"],
            "rsi": last["rsi"],
            "mom5": last["mom5"],
            "mom20": last["mom20"],
            "mom60": last["mom60"],
            "sma20": last["sma20"],
            "sma50": last["sma50"],
        }

        row["score"] = score_swing(row) if profile == "Swing" else score_day(row)
        row["comment"] = comment(row, profile)

        rows.append(row)

    df_rank = pd.DataFrame(rows).sort_values("score", ascending=False).head(limit)

    st.dataframe(df_rank, use_container_width=True)

    st.markdown("### Komentarze")
    for _, r in df_rank.iterrows():
        st.write(f"**{r['symbol']}** — {r['comment']}")

# ---------------------------------------------------------
# SZCZEGÓŁY SPÓŁKI
# ---------------------------------------------------------
if menu == "Szczegóły spółki":
    symbols = get_symbols_gpw()
    symbol = st.selectbox("Wybierz spółkę:", symbols)

    if symbol:
        df = get_ohlc(symbol)
        df = compute_indicators(df)
        df["time"] = df["time"].astype(str)

        col1, col2 = st.columns(2)

        with col1:
            fig = px.line(df, x="time", y="close", title=f"Cena – {symbol}")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.line(df, x="time", y="rsi", title="RSI")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df.tail(20), use_container_width=True)
