import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from openai import OpenAI

import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
# TELEGRAM API
# =====================================================================
def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

# =====================================================================
# RSI
# =====================================================================
def oblicz_rsi(df, period=14):
    try:
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception:
        return None

# =====================================================================
# MACD
# =====================================================================
def oblicz_macd(df):
    df["EMA12"] = df["Close"].ewm(span=12).mean()
    df["EMA26"] = df["Close"].ewm(span=26).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["Signal"] = df["MACD"].ewm(span=9).mean()
    return df

# =====================================================================
# AI KOMENTARZ
# =====================================================================
def generuj_komentarz_ai(client, ticker, price, volume, change, rsi, waluta):
    try:
        prompt = (
            f"Jesteś profesjonalnym traderem akcji (Long). Spółka {ticker} wygenerowała sygnał wzrostowy: "
            f"cena {float(price):.2f} {waluta}, wzrost o +{float(change):.2f}%, wolumen {float(volume):.1f}x ponad średnią, RSI {float(rsi):.1f}. "
            f"Napisz jedno bardzo krótkie zdanie techniczne (max 10 słów) podsumowania okazji."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=35,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Wykryto nagły skok momentum rynkowego."

# =====================================================================
# ANALIZA SPÓŁKI
# =====================================================================
def analizuj_spolke(
    ticker, interval, max_price_pln, max_price_usd,
    price_threshold, volume_threshold,
    telegram_token, telegram_chat_id,
    client
):
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    df = yf.download(ticker, period="5d", interval=interval, progress=False)
    if df.empty or len(df) < 15:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    df["RSI"] = oblicz_rsi(df)
    df = oblicz_macd(df)

    ostatnia = df.iloc[-1]
    poprzednia = df.iloc[-2]

    cena = float(ostatnia["Close"])
    cena_prev = float(poprzednia["Close"])
    rsi = float(ostatnia["RSI"]) if not pd.isna(ostatnia["RSI"]) else np.nan

    if cena <= 0 or pd.isna(rsi):
        return None

    is_gpw = ticker.endswith(".WA")
    waluta = "PLN" if is_gpw else "USD"

    if is_gpw and cena > max_price_pln:
        return None
    if not is_gpw and cena > max_price_usd:
        return None

    delisted_suffixes = ("Q", "Y", "F")
    otc_prefixes = ("OTC:", "PINK:", "PK:")
    ticker_upper = ticker.upper()

    if ticker_upper.endswith(delisted_suffixes):
        return None
    if ticker_upper.startswith(otc_prefixes):
        return None

    is_penny = False
    if is_gpw and 0.10 <= cena <= 15.0:
        is_penny = True
    if not is_gpw and 0.10 <= cena <= 5.0:
        is_penny = True

    zmiana = ((cena - cena_prev) / cena_prev) * 100

    wolumen = float(ostatnia["Volume"])
    sredni = float(df["Volume"].mean())
    if sredni == 0:
        return None
    skok = wolumen / sredni

    if is_penny:
        prog_wol = 30.0
        prog_rsi = 75.0
    else:
        prog_wol = 5.0
        prog_rsi = 60.0

    sygnal_push = (
        skok >= prog_wol and
        zmiana >= price_threshold and
        rsi <= prog_rsi and
        ostatnia["Close"] > ostatnia["Open"]
    )

    sl = cena * 0.95
    tp = cena * 1.15

    if sygnal_push:
        ocena = "🟢 Kupuj (Momentum)"
        score = 3
    elif zmiana > 0:
        ocena = "🟡 Trzymaj"
        score = 2
    else:
        ocena = "🔴 Unikaj"
        score = 1

    if sygnal_push:
        komentarz = generuj_komentarz_ai(client, ticker, cena, skok, zmiana, rsi, waluta)
        flag = "🇵🇱" if is_gpw else "🇺🇸"

        alert = (
            f"🚨🚨 <b>ALERT PUSH – ŚMIECIOWY MOMENTUM {flag}: {ticker}</b>\n"
            f"💰 Cena: {cena:.2f} {waluta} (+{zmiana:.2f}%)\n"
            f"📊 Wolumen: <b>{skok:.1f}x</b>\n"
            f"📈 Momentum świecy: TAK\n"
            f"🛡️ RSI: <b>{rsi:.1f}</b>\n"
            f"🛑 SL: {sl:.2f} {waluta}\n"
            f"🎯 TP: {tp:.2f} {waluta}\n\n"
            f"📝 <b>AI:</b> {komentarz}"
        )

        send_telegram_message(telegram_token, telegram_chat_id, alert)

    return {
        "Ticker": ticker,
        "Cena": f"{cena:.2f} {waluta}",
        "Zmiana %": round(zmiana, 2),
        "Wolumen (Multiplier)": f"{skok:.2f}x",
        "RSI": f"{rsi:.1f}",
        "Stop Loss (SL na dole)": f"{sl:.2f} {waluta}",
        "Take Profit (TP)": f"{tp:.2f} {waluta}",
        "Status / Ocena": ocena,
        "score": score,
        "MACD": float(ostatnia["MACD"]),
        "Signal": float(ostatnia["Signal"]),
        "Open": float(ostatnia["Open"]),
        "High": float(ostatnia["High"]),
        "Low": float(ostatnia["Low"]),
        "Close": float(ostatnia["Close"]),
    }

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
        if "SL" in val:
            return "color: red; font-weight: bold;"
        if "TP" in val:
            return "color: lime; font-weight: bold;"
        return ""

   def highlight(row):
    style = {}
    if "Kupuj" in row["Status / Ocena"]:
        style["Status / Ocena"] = "color: lime; font-weight: bold;"
    elif "Trzymaj" in row["Status / Ocena"]:
        style["Status / Ocena"] = "color: gold; font-weight: bold;"
    else:
        style["Status / Ocena"] = "color: red; font-weight: bold;"

    style["Stop Loss (SL na dole)"] = "color: red; font-weight: bold;"
    style["Take Profit (TP)"] = "color: lime; font-weight: bold;"
    return style

st.dataframe(
    df_wyniki.style.apply(highlight, axis=1),
    use_container_width=True
)


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
