import time
import schedule
import threading
import requests
import yfinance as yf
import pandas as pd
import streamlit as st
from openai import OpenAI
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# =====================================================================
# KONFIG STREAMLIT
# =====================================================================
st.set_page_config(page_title="Snajper + Kombajn", page_icon="🎯", layout="wide")
st.title("🎯 Snajper Rynkowy + Kombajn Giełdowy")

# =====================================================================
# STAN SESJI
# =====================================================================
if "alerts_history" not in st.session_state:
    st.session_state.alerts_history = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nie skanowano"
if "last_scanned_tickers" not in st.session_state:
    st.session_state.last_scanned_tickers = []
if "scanned_details" not in st.session_state:
    st.session_state.scanned_details = []

# =====================================================================
# SECRETS / KLUCZE
# =====================================================================
try:
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

    INTERVAL = "60m"  # 1 godzina
    PRICE_THRESHOLD = 1.5
    VOLUME_THRESHOLD = 1.4
    MAX_PRICE_PLN = 15.0
    MAX_PRICE_USD = 5.0
    RSI_SAFE_LOW = 25
    RSI_SAFE_HIGH = 75

except Exception as e:
    st.error(f"❌ Błąd kluczy w secrets.toml: {e}")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# DYNAMICZNA LISTA TWOICH SPÓŁEK
# =====================================================================
st.subheader("📝 Zarządzanie Twoją Listą Obserwacyjną")

domyslna_lista = (
    "APS.WA, STX.WA,"
)

user_input = st.text_area(
    "Wklej tutaj swoje spółki rozdzielone przecinkami (USA lub GPW z końcówką .WA):",
    value=domyslna_lista,
    height=100
)

MARKET_DATABASE = [t.strip().upper() for t in user_input.split(",") if t.strip()]

# =====================================================================
# TELEGRAM
# =====================================================================
def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

# =====================================================================
# RSI
# =====================================================================
def oblicz_rsi(df: pd.DataFrame, period: int = 14):
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
# WYKRYWANIE FORMACJI ŚWIECOWYCH
# =====================================================================
def wykryj_formacje(df):
    if len(df) < 3:
        return "Brak danych"

    o1, h1, l1, c1 = df.iloc[-1][["Open","High","Low","Close"]]
    o2, h2, l2, c2 = df.iloc[-2][["Open","High","Low","Close"]]
    o3, h3, l3, c3 = df.iloc[-3][["Open","High","Low","Close"]]

    # Hammer
    if (c1 > o1) and ((h1 - max(o1, c1)) < (abs(c1 - o1) * 0.3)) and ((min(o1, c1) - l1) > (abs(c1 - o1) * 2)):
        return "🔨 Hammer (odwrócenie w górę)"

    # Bullish Engulfing
    if (c1 > o1) and (c2 < o2) and (o1 < c2) and (c1 > o2):
        return "🟢 Bullish Engulfing"

    # Bearish Engulfing
    if (c1 < o1) and (c2 > o2) and (o1 > c2) and (c1 < o2):
        return "🔴 Bearish Engulfing"

    # Doji
    if abs(c1 - o1) <= (0.1 * (h1 - l1)):
        return "⚪ Doji (niepewność)"

    return "Brak formacji"

# =====================================================================
# AI PREDYKCJA KIERUNKU ŚWIECY
# =====================================================================
def predykcja_ai(ticker, zmiana, rsi, wolumen):
    try:
        prompt = (
            f"Analizujesz spółkę {ticker}. "
            f"Zmiana ceny: {zmiana:.2f}%. "
            f"RSI: {rsi:.1f}. "
            f"Wolumen: {wolumen:.1f}x ponad średnią. "
            f"Przewidź kierunek kolejnej świecy: UP, DOWN lub SIDEWAYS. "
            f"Podaj tylko jedno słowo."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.0
        )

        kierunek = response.choices[0].message.content.strip().upper()

        if "UP" in kierunek:
            return "📈 AI: UP"
        if "DOWN" in kierunek:
            return "📉 AI: DOWN"
        return "➡️ AI: SIDEWAYS"

    except Exception:
        return "AI: brak predykcji"

# =====================================================================
# AI KOMENTARZ
# =====================================================================
def generuj_komentarz_ai(ticker, price, volume, change, rsi, waluta):
    try:
        prompt = (
            f"Spółka {ticker}: cena {price:.2f} {waluta}, zmiana {change:.2f}%, wolumen {volume:.1f}x, RSI {rsi:.1f}. "
            f"Napisz jedno krótkie zdanie techniczne (max 10 słów)."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=35,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Wykryto skok momentum."

# =====================================================================
# WIELOWĄTKOWA ANALIZA SPÓŁKI
# =====================================================================
def analizuj_jedna_spolke(ticker: str, now: str):
    try:
        df = yf.download(ticker, period="5d", interval=INTERVAL, progress=False)
        if df.empty or len(df) < 15:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        df["RSI"] = oblicz_rsi(df)
        ostatnia = df.iloc[-1]
        poprzednia = df.iloc[-2]

        def to_float(val):
            if isinstance(val, pd.Series):
                return float(val.iloc[0])
            return float(val)

        cena = to_float(ostatnia["Close"])
        cena_prev = to_float(poprzednia["Close"])
        rsi = to_float(ostatnia["RSI"])

        if cena <= 0 or pd.isna(rsi):
            return None

        is_gpw = ticker.endswith(".WA")
        waluta = "PLN" if is_gpw else "USD"

        if is_gpw and cena > MAX_PRICE_PLN:
            return None
        if not is_gpw and cena > MAX_PRICE_USD:
            return None

        zmiana = ((cena - cena_prev) / cena_prev) * 100
        wolumen = to_float(ostatnia["Volume"])
        sredni = to_float(df["Volume"].mean())

        if sredni == 0:
            return None

        wolumen_x = wolumen / sredni

        sygnal_techniczny = (zmiana >= PRICE_THRESHOLD and wolumen_x >= VOLUME_THRESHOLD)
        rsi_ok = (RSI_SAFE_LOW <= rsi <= RSI_SAFE_HIGH)

        sygnal = sygnal_techniczny and rsi_ok

        # Formacje
        formacja = wykryj_formacje(df)

        # Predykcja AI
        pred = predykcja_ai(ticker, zmiana, rsi, wolumen_x)

        # Rekomendacja (AI wpływa)
        if "UP" in pred:
            rekomendacja = "🟢 KUP"
        elif "DOWN" in pred:
            rekomendacja = "🔴 SPRZEDAJ"
        else:
            rekomendacja = "🟡 TRZYMAJ"

        info = {
            "Ticker": ticker,
            "Cena": cena,
            "Waluta": waluta,
            "RSI": rsi,
            "Zmiana %": zmiana,
            "Wolumen x": wolumen_x,
            "Formacja": formacja,
            "Predykcja AI": pred,
            "Rekomendacja": rekomendacja,
        }

        if sygnal:
            komentarz = generuj_komentarz_ai(ticker, cena, wolumen_x, zmiana, rsi, waluta)
            alert = (
                f"🟢 *OKAZJA RYNKOWA:* `{ticker}`\n"
                f"💰 Cena: {cena:.2f} {waluta}\n"
                f"📈 Zmiana: +{zmiana:.2f}%\n"
                f"📊 Wolumen: {wolumen_x:.1f}x\n"
                f"🛡️ RSI: {rsi:.1f}\n"
                f"🔮 Predykcja: {pred}\n"
                f"🤖 AI: {komentarz}"
            )
            send_telegram_message(alert)
            info["Alert"] = alert

        return info

    except Exception:
        return None

# =====================================================================
# JOB SKANERA
# =====================================================================
def job_skanera(status_placeholder=None, progress_bar=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_scan_time = now
    st.session_state.scanned_details = []
    st.session_state.last_scanned_tickers = []

    total = len(MARKET_DATABASE)
    przetworzone = 0
    detale = []
    podglad = []
    alerty = []

    with ThreadPoolExecutor(max_workers=15) as executor:
        zadania = {
            executor.submit(analizuj_jedna_spolke, t, now): t
            for t in MARKET_DATABASE
        }
        for future in as_completed(zadania):
            przetworzone += 1
            ticker = zadania[future]

            if status_placeholder and progress_bar:
                status_placeholder.markdown(
                    f"🔍 Analiza ({przetworzone}/{total}): `{ticker}`"
                )
                progress_bar.progress(przetworzone / total)

            wynik = future.result()
            if wynik:
                detale.append(wynik)
                podglad.append(
                    f"{wynik['Ticker']} ({wynik['Cena']:.2f} {wynik['Waluta']}) → {wynik['Rekomendacja']}"
                )
                if "Alert" in wynik:
                    alerty.append(wynik["Alert"])

    st.session_state.scanned_details = detale
    st.session_state.last_scanned_tickers = podglad

    if alerty:
        st.session_state.alerts_history.extend(alerty)
    else:
        send_telegram_message(
            f"🤖 *Status Cyklu*\n"
            f"⏱️ {now}\n"
            f"📊 Spółek: {total}\n"
            f"🔍 Brak nowych okazji."
        )

# =====================================================================
# AUTO-SKAN
# =====================================================================
schedule.clear()
schedule.every(15).minutes.do(job_skanera)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if "worker_started" not in st.session_state:
    st.session_state.worker_started = True
    threading.Thread(target=run_scheduler, daemon=True).start()

# =====================================================================
# UI
# =====================================================================
st.write("---")
st.success(f"⚙️ Radar aktywny | Ostatni skan: {st.session_state.last_scan_time}")

status_live = st.empty()
pasek_live = st.empty()

if st.button("🚀 SKANUJ TERAZ"):
    job_skanera(status_live, pasek_live)
    st.rerun()

# =====================================================================
# TABELA KOMBAJNU
# =====================================================================
st.write("---")
st.subheader("📊 KOMBAJN — pełna lista przeskanowanych spółek")

if st.session_state.scanned_details:

    df = pd.DataFrame(st.session_state.scanned_details)

    html = """
    <table style="width:100%; border-collapse: collapse;">
        <tr style="background-color:#222; color:white;">
            <th>Ticker</th>
            <th>Cena</th>
            <th>Waluta</th>
            <th>RSI</th>
            <th>Zmiana %</th>
            <th>Wolumen x</th>
            <th>Formacja</th>
            <th>Predykcja AI</th>
            <th>Rekomendacja</th>
        </tr>
    """

    for _, row in df.iterrows():

        if "🟢" in row["Rekomendacja"]:
            kolor = "#00ff00"
        elif "🔴" in row["Rekomendacja"]:
            kolor = "#ff0000"
        else:
            kolor = "#ffff00"

        html += f"""
        <tr style="background-color:#111; color:white;">
            <td>{row['Ticker']}</td>
            <td>{row['Cena']:.2f}</td>
            <td>{row['Waluta']}</td>
            <td>{row['RSI']:.1f}</td>
            <td>{row['Zmiana %']:.2f}</td>
            <td>{row['Wolumen x']:.2f}</td>
            <td>{row['Formacja']}</td>
            <td>{row['Predykcja AI']}</td>
            <td style="background-color:{kolor}; font-weight:bold;">{row['Rekomendacja']}</td>
        </tr>
        """

    html += "</table>"

    st.markdown(html, unsafe_allow_html=True)
else:
    st.info("Brak danych — skaner jeszcze nie wykonał cyklu.")

# =====================================================================
# SZYBKI PODGLĄD TICKERA
# =====================================================================
st.write("---")
st.subheader("🔎 Szybki podgląd dowolnego tickera")

quick = st.text_input("Ticker (USA lub GPW .WA):")

if quick:
    df_q = yf.download(quick.strip().upper(), period="5d", interval="30m", progress=False)
    if df_q.empty:
        st.error("Brak danych.")
    else:
        if isinstance(df_q.columns, pd.MultiIndex):
            df_q.columns = df_q.columns.droplevel(1)

        df_q["RSI"] = oblicz_rsi(df_q)
        last = df_q.iloc[-1]

        cena = float(last["Close"])
        rsi = float(last["RSI"])

        st.write(f"**Cena:** {cena:.2f}")
        st.write(f"**RSI:** {rsi:.1f}")
