import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st
from openai import OpenAI

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils import analizuj_spolke, oblicz_rsi, oblicz_macd

# =====================================================================
# KONFIGURACJA STRONY – DARK TERMINAL
# =====================================================================
st.set_page_config(page_title="Snajper Rynkowy – Groszówki", page_icon="🎯", layout="wide")
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🎯 Snajper Rynkowy – Groszówki (Dark Terminal)")

# =====================================================================
# SESJA
# =====================================================================
if "alerts_history" not in st.session_state:
    st.session_state.alerts_history = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nie skanowano"
if "last_scanned_tickers" not in st.session_state:
    st.session_state.last_scanned_tickers = []

# =====================================================================
# SECRETS – KLUCZE I PARAMETRY
# =====================================================================
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

    MAX_PRICE_PLN = float(st.secrets.get("MAX_PRICE_PLN", 50.0))
    MAX_PRICE_USD = float(st.secrets.get("MAX_PRICE_USD", 5.0))
    VOLUME_THRESHOLD = float(st.secrets.get("VOLUME_THRESHOLD", 3.0))
    PRICE_THRESHOLD = float(st.secrets.get("PRICE_THRESHOLD", 1.0))
except KeyError as e:
    st.error(f"❌ Brak kluczowych zmiennych w secrets.toml: {e}")
    st.stop()
except Exception as e:
    st.error(f"❌ Błąd odczytu secrets.toml: {e}")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# LISTA OBSERWACYJNA – TWOJE ŚMIECIOWKI
# =====================================================================
st.subheader("📝 Twoja Lista Groszówek (GPW + USA)")

domyslna_lista = "APS.WA, STX.WA, KCH.WA"
user_input = st.text_area(
    "Wklej swoje spółki rozdzielone przecinkami (USA lub GPW z końcówką .WA):",
    value=domyslna_lista,
    height=100,
)

MARKET_DATABASE = [t.strip().upper() for t in user_input.split(",") if t.strip()]

# =====================================================================
# SUWAKI – PARAMETRY W LOCIE
# =====================================================================
col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    ui_interval = st.selectbox("Interwał świecy:", ["1m", "5m", "15m", "30m", "1h"], index=2)
with col_p2:
    ui_vol_threshold = st.slider("Próg skoku obrotu (x średniej):", 1.0, 10.0, VOLUME_THRESHOLD, step=0.5)
with col_p3:
    ui_price_threshold = st.slider("Próg wzrostu ceny (%):", 0.1, 10.0, PRICE_THRESHOLD, step=0.1)

# =====================================================================
# SIDEBAR – STEROWANIE RADAREM
# =====================================================================
st.sidebar.header("⏱️ Sterowanie Radarem")
auto_scan = st.sidebar.selectbox(
    "Automatyczne odświeżanie:",
    ["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"],
)

if st.sidebar.button("🔌 Wyślij testowy alert Telegram"):
    from utils import send_telegram_message
    try:
        send_telegram_message(
            TELEGRAM_TOKEN,
            TELEGRAM_CHAT_ID,
            "🤖 <b>TEST SYSTEMU:</b> Dark Terminal Snajpera działa poprawnie!"
        )
        st.sidebar.success("Test wysłany!")
    except Exception as e:
        st.sidebar.error(f"Błąd wysyłania testu: {e}")

st.sidebar.info(f"⏱️ Ostatni udany skan: {st.session_state.last_scan_time}")

# =====================================================================
# GŁÓWNY JOB SKANERA – WIELOWĄTKOWOŚĆ
# =====================================================================
def job_skanera(status_placeholder=None, progress_bar=None):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_scan_time = now

    total_spolki = len(MARKET_DATABASE)
    lista_podgladu = []
    przetworzone = 0

    if total_spolki == 0:
        if status_placeholder:
            status_placeholder.error("❌ Lista spółek obserwowanych jest pusta.")
        return

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                analizuj_spolke,
                ticker,
                ui_interval,
                MAX_PRICE_PLN,
                MAX_PRICE_USD,
                ui_price_threshold,
                ui_vol_threshold,
                TELEGRAM_TOKEN,
                TELEGRAM_CHAT_ID,
                client
            ): ticker
            for ticker in MARKET_DATABASE
        }

        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    lista_podgladu.append(res)
            except Exception:
                pass
            przetworzone += 1
            if progress_bar:
                progress_bar.progress(przetworzone / total_spolki)

    st.session_state.last_scanned_tickers = lista_podgladu

# =====================================================================
# PRZYCISKI GŁÓWNE
# =====================================================================
col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    uruchom_skan = st.button("🚀 Uruchom Skaner")
with col_btn2:
    if st.button("🗑️ Wyczyść Historię"):
        st.session_state.alerts_history = []
        st.session_state.last_scanned_tickers = []
        st.rerun()

status_ph = st.empty()
prog_bar = st.empty()

if uruchom_skan:
    status_ph.write("⌛ Trwa pobieranie i analiza danych groszówek...")
    prog_bar.progress(0)
    job_skanera(status_ph, prog_bar)
    status_ph.success(
        f"⚙️ Status: Dark Terminal aktywny | Ostatni skan: {st.session_state.last_scan_time}"
    )

# =====================================================================
# WYNIKI – TABELA POSORTOWANA
# =====================================================================
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd aktualnego cyklu skanowania (Posortowany)")

    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    if "score" in df_wyniki.columns:
        df_wyniki = df_wyniki.sort_values(by="score", ascending=False)

    def kolor_status(val):
        if "Kupuj" in val:
            return "color: lime; font-weight: bold;"
        if "Trzymaj" in val:
            return "color: gold; font-weight: bold;"
        if "Unikaj" in val or "Sprzedaj" in val:
            return "color: red; font-weight: bold;"
        return ""

    def kolor_sl_tp(val):
        return "color: red; font-weight: bold;" if "SL" in val else "color: lime; font-weight: bold;" if "TP" in val else ""

    df_wyniki_styled = (
        df_wyniki.style
        .applymap(kolor_status, subset=["Status / Ocena"])
        .applymap(kolor_sl_tp, subset=["Stop Loss (SL na dole)", "Take Profit (TP)"])
    )

    st.dataframe(df_wyniki_styled, use_container_width=True)

# =====================================================================
# TOP 5 OKAZJI DNIA
# =====================================================================
st.subheader("🏆 TOP 5 Okazji Dnia (Najmocniejsze Sygnały)")

if st.session_state.last_scanned_tickers:
    df_top = pd.DataFrame(st.session_state.last_scanned_tickers)

    if "score" in df_top.columns:
        df_top = df_top.sort_values(by="score", ascending=False)

    df_top5 = df_top.head(5)

    df_top5_styled = (
        df_top5.style
        .applymap(kolor_status, subset=["Status / Ocena"])
        .applymap(kolor_sl_tp, subset=["Stop Loss (SL na dole)", "Take Profit (TP)"])
    )

    st.dataframe(df_top5_styled, use_container_width=True)

# =====================================================================
# SZYBKI PODGLĄD TICKERA
# =====================================================================
st.subheader("🔎 Szybki podgląd pojedynczego tickera (RSI + MACD + Świece)")

quick_ticker = st.text_input("Wpisz ticker do szybkiej analizy:", "")

df_q = None
if quick_ticker:
    df_q = pd.DataFrame()
    try:
        df_q = pd.DataFrame(
            yf.download(quick_ticker, period="5d", interval="15m", progress=False)
        )
    except Exception as e:
        st.error(f"Błąd pobierania danych dla {quick_ticker}: {e}")

if quick_ticker and df_q is not None and not df_q.empty:
    df_q["RSI"] = oblicz_rsi(df_q)
    df_q = oblicz_macd(df_q)

    ostatnia = df_q.iloc[-1]

    st.write(f"**Cena:** {ostatnia['Close']:.2f}")
    st.write(f"**RSI:** {ostatnia['RSI']:.1f}")
    st.write(f"**MACD:** {ostatnia['MACD']:.4f}")
    st.write(f"**Signal:** {ostatnia['Signal']:.4f}")
    st.write(f"**Wolumen:** {ostatnia['Volume']}")
    st.write(
        f"**Świeca:** O:{ostatnia['Open']:.2f} H:{ostatnia['High']:.2f} L:{ostatnia['Low']:.2f} C:{ostatnia['Close']:.2f}"
    )

    if ostatnia["MACD"] > ostatnia["Signal"]:
        st.success("🟢 Trend rosnący (MACD > Signal)")
    else:
        st.error("🔴 Trend spadkowy (MACD < Signal)")

    # =================================================================
    # WYKRES ŚWIECOWY + RSI + MACD
    # =================================================================
    st.subheader("📈 Wykres świecowy + RSI + MACD")

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.55, 0.20, 0.25],
    )

    fig.add_trace(
        go.Candlestick(
            x=df_q.index,
            open=df_q["Open"],
            high=df_q["High"],
            low=df_q["Low"],
            close=df_q["Close"],
            name="Świece",
            increasing_line_color="lime",
            decreasing_line_color="red",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df_q.index,
            y=df_q["RSI"],
            mode="lines",
            name="RSI",
            line=dict(color="orange", width=2),
        ),
        row=2,
        col=1,
    )

    fig.add_hline(y=30, line=dict(color="gray", dash="dot"), row=2, col=1)
    fig.add_hline(y=70, line=dict(color="gray", dash="dot"), row=2, col=1)

    fig.add_trace(
        go.Scatter(
            x=df_q.index,
            y=df_q["MACD"],
            mode="lines",
            name="MACD",
            line=dict(color="cyan", width=2),
        ),
        row=3,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df_q.index,
            y=df_q["Signal"],
            mode="lines",
            name="Signal",
            line=dict(color="white", width=1),
        ),
        row=3,
        col=1,
    )

    fig.update_layout(
        height=900,
        width=1200,
        showlegend=True,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
    )

    st.plotly_chart(fig, use_container_width=True)

# =====================================================================
# AUTO-SCAN – NATIVE RERUN
# =====================================================================
if auto_scan == "Co 1 minutę":
    time.sleep(60)
    st.rerun()
elif auto_scan == "Co 5 minut":
    time.sleep(300)
    st.rerun()
elif auto_scan == "Co 15 minut":
    time.sleep(900)
    st.rerun()
