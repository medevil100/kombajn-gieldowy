import time
import traceback
import requests
import yfinance as yf
import pandas as pd
import streamlit as st
from openai import OpenAI
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import matplotlib.pyplot as plt
import base64
from io import BytesIO

# =====================================================================
# STREAMLIT CONFIG
# =====================================================================
st.set_page_config(page_title="KOMBAJN PRO", page_icon="📈", layout="wide")
st.title("📈 KOMBAJN PRO — AI + Tavily + Mini‑Świece + Telegram")

# =====================================================================
# ERROR DISPLAY
# =====================================================================
def show_error(e):
    st.error(f"❌ Błąd: {e}")
    st.code(traceback.format_exc())

# =====================================================================
# SESSION STATE
# =====================================================================
if "scanned_details" not in st.session_state:
    st.session_state.scanned_details = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nigdy"

# =====================================================================
# SECRETS
# =====================================================================
TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# INPUT TICKERS
# =====================================================================
user_input = st.text_area(
    "Wklej swoje spółki:",
    value="APS.WA, STX.WA, AIT.WA",
    height=120
)

MARKET_DATABASE = [
    t.strip() for t in user_input.replace("\n", ",").replace(" ", ",").split(",")
    if t.strip()
]

# =====================================================================
# YFINANCE — DZIAŁAJĄCE PARAMETRY
# =====================================================================
def pobierz_df(ticker):
    df = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        auto_adjust=True,
        threads=False,
        group_by="ticker",
        progress=False
    )
    if df.empty:
        raise ValueError(f"Brak danych dla {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.xs(ticker, level=1, axis=1)
        except:
            df.columns = df.columns.get_level_values(0)
    return df

# =====================================================================
# MINI WYKRES
# =====================================================================
def mini_chart(df):
    try:
        df = df.tail(20)
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(1.6, 1.0),
            gridspec_kw={"height_ratios": [3, 1]},
            dpi=75
        )
        for i, row in enumerate(df.itertuples()):
            o, h, l, c = row.Open, row.High, row.Low, row.Close
            color = "#00ff00" if c >= o else "#ff0000"
            ax1.vlines(i, l, h, color=color, linewidth=0.8)
            ax1.vlines(i, o, c, color=color, linewidth=2)
        ax1.set_xticks([]); ax1.set_yticks([]); ax1.set_facecolor("#000000")
        ax2.bar(range(len(df)), df["Volume"], color="#666666", width=0.6)
        ax2.set_xticks([]); ax2.set_yticks([]); ax2.set_facecolor("#000000")
        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
        fig.clf(); plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        show_error(e)
        return ""

# =====================================================================
# ANALIZA SPÓŁKI
# =====================================================================
def analizuj(ticker):
    try:
        df = pobierz_df(ticker)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        cena = float(last["Close"])
        zmiana = ((last["Close"] - prev["Close"]) / prev["Close"]) * 100
        wolumen_x = float(last["Volume"]) / df["Volume"].mean()

        chart = mini_chart(df)

        return {
            "Ticker": ticker,
            "Cena": cena,
            "Zmiana %": zmiana,
            "Wolumen x": wolumen_x,
            "MiniWykres": chart
        }
    except Exception as e:
        show_error(e)
        return None

# =====================================================================
# SKANER — UWAGA: BEZ KOLUMN, BEZ RERUN W ŚRODKU
# =====================================================================
def skanuj():
    wyniki = []
    for t in MARKET_DATABASE:
        res = analizuj(t)
        if res:
            wyniki.append(res)
    st.session_state.scanned_details = wyniki
    st.session_state.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# =====================================================================
# PRZYCISK — TERAZ DZIAŁA
# =====================================================================
if st.button("🚀 SKANUJ TERAZ"):
    skanuj()

# =====================================================================
# TABELA
# =====================================================================
st.write("---")
st.write(f"📅 Ostatni skan: {st.session_state.last_scan_time}")

if st.session_state.scanned_details:
    df = pd.DataFrame(st.session_state.scanned_details)
    df["MiniWykres"] = df["MiniWykres"].apply(
        lambda x: f'<img src="data:image/png;base64,{x}" width="120" height="80"/>' if x else "Brak"
    )
    st.markdown(df.to_html(escape=False), unsafe_allow_html=True)
else:
    st.info("Brak danych — kliknij SKANUJ TERAZ.")
