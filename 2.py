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
# SECRETS / KLUCZE (DOPASUJ DO SWOJEGO PLIKU secrets.toml)
# =====================================================================
try:
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    INTERVAL = st.secrets.get("INTERVAL", "15m")
    PRICE_THRESHOLD = float(st.secrets.get("PRICE_THRESHOLD", 5.0))
    VOLUME_THRESHOLD = float(st.secrets.get("VOLUME_THRESHOLD", 3.0))
    MAX_PRICE_PLN = float(st.secrets.get("MAX_PRICE_PLN", 15.0))
    MAX_PRICE_USD = float(st.secrets.get("MAX_PRICE_USD", 5.0))
except KeyError:
    st.error("❌ Brak kluczowych zmiennych autoryzacyjnych w secrets.toml")
    st.stop()
except Exception as e:
    st.error(f"❌ Błąd kluczy w secrets.toml: {e}")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# DYNAMICZNA LISTA TWOICH SPÓŁEK
# =====================================================================
st.subheader("📝 Zarządzanie Twoją Listą Obserwacyjną")

domyslna_lista = (
    "APS.WA, STX.WA, AITON.WA, CALDWELL.WA, NOVAWIS.WA, POLTRONIC.WA"
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
    czysty_token = str(TELEGRAM_TOKEN).strip()
    url = "https://" + "api.telegram.org" + "/bot" + czysty_token + "/sendMessage"
    payload = {
        "chat_id": str(TELEGRAM_CHAT_ID).strip(),
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
# AI KOMENTARZ (PRAWDZIWE AI)
# =====================================================================
def generuj_komentarz_ai(ticker, price, volume, change, rsi, waluta):
    try:
        prompt = (
            f"Jesteś profesjonalnym traderem-snajperem. Spółka {ticker} wygenerowała sygnał Groszówek: "
            f"cena {float(price):.2f} {waluta}, wzrost o +{float(change):.2f}%, wolumen {float(volume):.1f}x ponad średnią, RSI {float(rsi):.1f}. "
            f"Napisz jedno ultra-krótkie zdanie techniczne (max 10 słów) podsumowania okazji."
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
# WIELOWĄTKOWA ANALIZA SPÓŁKI (SNAJPER)
# =====================================================================
def analizuj_jedna_spolke(ticker: str, now: str):
    try:
        df = yf.download(ticker, period="5d", interval=INTERVAL, progress=False)
        if df.empty or len(df) < 15:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        df["RSI"] = oblicz_rsi(df)
        ostatnia_swieca = df.iloc[-1]
        poprzednia_swieca = df.iloc[-2]

        def do_float(val):
            if isinstance(val, pd.Series):
                return float(val.iloc[0])
            return float(val)

        aktualna_cena = do_float(ostatnia_swieca["Close"])
        cena_zamkniecia_poprzednia = do_float(poprzednia_swieca["Close"])
        current_rsi = do_float(ostatnia_swieca["RSI"])

        if aktualna_cena <= 0 or pd.isna(current_rsi):
            return None

        is_gpw = ticker.endswith(".WA")
        waluta = "PLN" if is_gpw else "USD"

        if is_gpw and aktualna_cena > MAX_PRICE_PLN:
            return None
        if not is_gpw and aktualna_cena > MAX_PRICE_USD:
            return None

        zmiana_ceny = ((aktualna_cena - cena_zamkniecia_poprzednia) / cena_zamkniecia_poprzednia) * 100
        aktualny_wolumen = do_float(ostatnia_swieca["Volume"])
        sredni_wolumen = do_float(df["Volume"].mean())

        if sredni_wolumen == 0:
            return None

        skok_wolumenu = aktualny_wolumen / sredni_wolumen

        sygnal_techniczny = (zmiana_ceny >= PRICE_THRESHOLD and skok_wolumenu >= VOLUME_THRESHOLD)
        rsi_bezpieczny = (30.0 <= current_rsi <= 70.0)

        sygnal_trafiony = sygnal_techniczny and rsi_bezpieczny
        status_okazji = "🟢 OKAZJA RYNKOWA" if sygnal_trafiony else "Filtrowane / Brak"

        ticker_info = {
            "Ticker": ticker,
            "Cena": aktualna_cena,
            "Waluta": waluta,
            "RSI": current_rsi,
            "Zmiana %": zmiana_ceny,
            "Wolumen x": skok_wolumenu,
            "Status": status_okazji,
        }

        if sygnal_trafiony:
            komentarz = generuj_komentarz_ai(
                ticker, aktualna_cena, skok_wolumenu, zmiana_ceny, current_rsi, waluta
            )
            alert_text = (
                f"🟢 *REALNA OKAZJA RYNKOWA:* `{ticker}`\n"
                f"💰 Cena: {aktualna_cena:.2f} {waluta}\n"
                f"📈 Zmiana: +{zmiana_ceny:.2f}%\n"
                f"📊 Wolumen: {skok_wolumenu:.1f}x ponad średnią\n"
                f"🛡️ Wskaźnik RSI: `{current_rsi:.1f}` (Strefa Bezpieczna)\n"
                f"🤖 *AI:* {komentarz}"
            )
            send_telegram_message(alert_text)

            ticker_info["Alert"] = {
                "Czas": now,
                "Ticker": ticker,
                "Cena": f"{aktualna_cena:.2f} {waluta}",
                "Zmiana": f"+{zmiana_ceny:.2f}%",
                "Wolumen Multiplier": f"{skok_wolumenu:.1f}x",
                "RSI": f"{current_rsi:.1f}",
                "Komentarz AI": komentarz,
            }

        return ticker_info
    except Exception:
        return None

# =====================================================================
# JOB SKANERA (SNAJPER + KOMBAJN)
# =====================================================================
def job_skanera(status_placeholder=None, progress_bar=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_scan_time = now
    st.session_state.last_scanned_tickers = []
    st.session_state.scanned_details = []

    total_spolki = len(MARKET_DATABASE)
    znalezione_sygnaly = []
    lista_podgladu = []
    detale_spolek = []
    przetworzone = 0

    if total_spolki == 0:
        if status_placeholder:
            status_placeholder.error("❌ Lista spółek jest pusta!")
        return

    with ThreadPoolExecutor(max_workers=15) as executor:
        zadania = {
            executor.submit(analizuj_jedna_spolke, ticker, now): ticker
            for ticker in MARKET_DATABASE
        }
        for future in as_completed(zadania):
            przetworzone += 1
            ticker_name = zadania[future]

            if status_placeholder and progress_bar:
                status_placeholder.markdown(
                    f"🔍 **Analiza Twojej Listy ({przetworzone}/{total_spolki}):** Sprawdzam `{ticker_name}`..."
                )
                progress_bar.progress(przetworzone / total_spolki)

            wynik = future.result()
            if wynik is not None:
                detale_spolek.append(wynik)
                lista_podgladu.append(
                    f"{wynik['Ticker']} ({wynik['Cena']:.2f} {wynik['Waluta']}) -> RSI: {wynik['RSI']:.1f} | {wynik['Status']}"
                )
                if "Alert" in wynik:
                    znalezione_sygnaly.append(wynik["Alert"])

    if status_placeholder and progress_bar:
        status_placeholder.markdown("✅ **Skanowanie Twojej listy zakończone.**")
        progress_bar.empty()

    st.session_state.last_scanned_tickers = lista_podgladu
    st.session_state.scanned_details = detale_spolek

    if znalezione_sygnaly:
        st.session_state.alerts_history.extend(znalezione_sygnaly)
    else:
        is_piatek = (datetime.now().weekday() == 4)
        naglowek = (
            "🤖 *Market Sniper – Podsumowanie Tygodnia (Piątek)*"
            if is_piatek
            else "🤖 *Market Sniper – Status Cyklu*"
        )
        raport_statusu = (
            f"{naglowek}\n"
            f"⏱️ Czas skanu: `{now}`\n"
            f"📊 Twoja lista: `{total_spolki}` spółek.\n"
            f"🔍 Wynik: Skan ukończony. Na Twoich spółkach nie ma jeszcze nowego ruchu."
        )
        send_telegram_message(raport_statusu)

# =====================================================================
# HARMONOGRAM W TLE (AUTO-SKAN)
# =====================================================================
schedule.clear()
schedule.every(15).minutes.do(job_skanera)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if "worker_started" not in st.session_state:
    st.session_state.worker_started = True
    thread = threading.Thread(target=run_scheduler, daemon=True)
    thread.start()

# =====================================================================
# PANEL GŁÓWNY (UI)
# =====================================================================
st.write("---")
st.success(
    f"⚙️ Status: Wielowątkowy radar aktywny | Ostatni skan: {st.session_state.last_scan_time}"
)

status_live = st.empty()
pasek_live = st.empty()

if st.button("🚀 URUCHOM SKANOWANIE TWOJEJ LISTY TERAZ"):
    job_skanera(status_placeholder=status_live, progress_bar=pasek_live)
    st.rerun()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Liczba wklejonych spółek", value=len(MARKET_DATABASE))
with col2:
    st.metric(label="Interwał świecy", value=INTERVAL)
with col3:
    st.metric(label="Próg wzrostu ceny", value=f"{PRICE_THRESHOLD}%")
with col4:
    st.metric(label="Próg skoku obrotu", value=f"{VOLUME_THRESHOLD}x")

st.write("---")
with st.expander(
    f"👁️ Pokaż szczegółowe odczyty RSI dla Twoich spółek ({len(st.session_state.last_scanned_tickers)})"
):
    if st.session_state.last_scanned_tickers:
        for item in st.session_state.last_scanned_tickers:
            st.write(item)
    else:
        st.info(
            "Brak danych. Wklej spółki i kliknij przycisk powyżej, aby odpalić skan."
        )

st.write("---")
st.subheader("📋 Zapamiętane Okazje Snajperskie (Zielone Alerty 🟢)")
if st.session_state.alerts_history:
    st.dataframe(pd.DataFrame(st.session_state.alerts_history), use_container_width=True)
else:
    st.info("Brak zarejestrowanych okazji. Radar czuwa i filtruje rynek.")

# =====================================================================
# KOMBajn: LISTA WSZYSTKICH PRZESKANOWANYCH SPÓŁEK Z REKOMENDACJĄ
# =====================================================================
st.write("---")
st.subheader("📊 Lista wszystkich przeskanowanych spółek z rekomendacją")

if st.session_state.scanned_details:
    df = pd.DataFrame(st.session_state.scanned_details)
    st.dataframe(
        df[["Ticker", "Cena", "Waluta", "RSI", "Zmiana %", "Wolumen x", "Status"]],
        use_container_width=True,
    )
else:
    st.info("Brak danych z ostatniego skanu. Radar czuwa, ale jeszcze nic nie wyłapał.")

# =====================================================================
# SZYBKI PODGLĄD DOWOLNEGO TICKERA
# =====================================================================
st.write("---")
st.subheader("🔎 Szybki podgląd dowolnego tickera (RSI + cena)")

quick_ticker = st.text_input("Ticker (USA lub GPW z .WA):", key="quick_ticker")

if quick_ticker:
    df_q = yf.download(quick_ticker.strip().upper(), period="5d", interval="30m", progress=False)
    if df_q.empty:
        st.error("Brak danych dla podanego tickera.")
    else:
        if isinstance(df_q.columns, pd.MultiIndex):
            df_q.columns = df_q.columns.droplevel(1)

        df_q["RSI"] = oblicz_rsi(df_q)
        ostatnia = df_q.iloc[-1]

        try:
            cena = float(ostatnia["Close"])
            rsi = float(ostatnia["RSI"])
        except Exception:
            st.error("Nie można poprawnie odczytać danych dla tego tickera.")
        else:
            st.write(f"**Cena:** {cena:.2f}")
            st.write(f"**RSI:** {rsi:.1f}")
