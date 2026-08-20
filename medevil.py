import time
import requests
import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
from openai import OpenAI
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tavily import TavilyClient

# =====================================================================
# KONFIGURACJA STRONY STREAMLIT
# =====================================================================
st.set_page_config(page_title="Snajper Rynkowy Custom", page_icon="🎯", layout="wide")
st.title("🎯 Twój Autorski Skaner Groszówek: Market Sniper")

# =====================================================================
# SESJA – HISTORIA ALERTÓW, OSTATNI SKAN, BLOKADA
# =====================================================================
if "alerts_history" not in st.session_state:
    st.session_state.alerts_history = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nie skanowano"
if "last_scanned_tickers" not in st.session_state:
    st.session_state.last_scanned_tickers = []
if "skan_w_toku" not in st.session_state:
    st.session_state.skan_w_toku = False
if "last_auto_scan" not in st.session_state:
    st.session_state.last_auto_scan = datetime.now()

# =====================================================================
# ŁADOWANIE KLUCZY Z SECRETS.TOML
# =====================================================================
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]

    MAX_PRICE_PLN = float(st.secrets.get("MAX_PRICE_PLN", 50.0))
    MAX_PRICE_USD = float(st.secrets.get("MAX_PRICE_USD", 5.0))
    VOLUME_THRESHOLD = float(st.secrets.get("VOLUME_THRESHOLD", 3.0))
    PRICE_THRESHOLD = float(st.secrets.get("PRICE_THRESHOLD", 1.0))
except KeyError as e:
    st.error(f"❌ Brak kluczowych zmiennych autoryzacyjnych w secrets.toml: {e}")
    st.stop()
except Exception as e:
    st.error(f"❌ Błąd kluczy w secrets.toml: {e}")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# =====================================================================
# DYNAMICZNE OKNO NA TWOJE TICKERY
# =====================================================================
st.subheader("📝 Zarządzanie Twoją Listą Obserwacyjną")
domyslna_lista = "APS.WA, STX.WA"
user_input = st.text_area(
    "Wklej tutaj swoje spółki rozdzielone przecinkami (USA lub GPW z końcówką .WA):",
    value=domyslna_lista,
    height=100
)
MARKET_DATABASE = [t.strip().upper() for t in user_input.split(",") if t.strip()]

# =====================================================================
# SUWAKI – PARAMETRY W LOCIE
# =====================================================================
col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns(5)
with col_p1:
    ui_interval = st.selectbox("Interwał świecy:", ["1m", "5m", "15m", "30m", "1h"], index=3)
with col_p2:
    ui_vol_threshold = st.slider("Próg skoku obrotu (x średniej):", 1.0, 10.0, VOLUME_THRESHOLD, step=0.5)
with col_p3:
    ui_price_threshold = st.slider("Próg wzrostu ceny (%):", 0.1, 5.0, PRICE_THRESHOLD, step=0.1)
with col_p4:
    ui_sl = st.slider("Stop Loss (% od ceny):", 1, 20, 5, step=1) / 100.0
with col_p5:
    ui_tp = st.slider("Take Profit (% od ceny):", 5, 50, 15, step=5) / 100.0

# =====================================================================
# OPCJA WŁĄCZANIA DODATKOWEJ ANALIZY (Tavily + głębsze AI)
# =====================================================================
use_deep_analysis = st.checkbox("🧠 Włącz analizę z użyciem newsów (Tavily)", value=True)

# =====================================================================
# MODUŁ KOMUNIKACJI – TELEGRAM (Z LOGOWANIEM BŁĘDÓW)
# =====================================================================
def send_telegram_message(message: str) -> bool:
    czysty_token = str(TELEGRAM_TOKEN).strip()
    czysty_chat_id = str(TELEGRAM_CHAT_ID).strip()
    url = f"https://api.telegram.org/bot{czysty_token}/sendMessage"
    payload = {
        "chat_id": czysty_chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            return True
        else:
            st.sidebar.error(f"Telegram błąd {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        st.sidebar.error(f"Telegram błąd połączenia: {e}")
        return False

# =====================================================================
# RSI – OBLICZENIA
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
# POMOCNICZA FUNKCJA DO BEZPIECZNEGO POBRANIA WARTOŚCI (SKALAR)
# =====================================================================
def pobierz_wartosc(series_or_float):
    try:
        if isinstance(series_or_float, (pd.Series, pd.DataFrame)):
            if len(series_or_float) == 1:
                val = series_or_float.item()
            else:
                val = series_or_float.iloc[0]
        else:
            val = series_or_float
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None

# =====================================================================
# FUNKCJA: POBRANIE NEWSÓW Z TAVILY (OSTATNIE 24H)
# =====================================================================
def pobierz_newsy_tavily(ticker: str) -> str:
    try:
        query = f"{ticker} stock news OR akcje"
        response = tavily.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_domains=["reuters.com", "bloomberg.com", "cnbc.com", "money.pl", "pb.pl"],
            days=1
        )
        if not response or "results" not in response:
            return ""
        news_text = ""
        for result in response["results"][:5]:
            title = result.get("title", "")
            snippet = result.get("content", "")
            news_text += f"• {title}\n  {snippet}\n\n"
        return news_text.strip()
    except Exception as e:
        st.sidebar.warning(f"Tavily błąd dla {ticker}: {e}")
        return ""

# =====================================================================
# NOWA FUNKCJA: ANALIZA AI NA PODSTAWIE DANYCH RYNKOWYCH (+ opcjonalne newsy)
# =====================================================================
def analizuj_rynkowo_ai(ticker: str, cena: float, waluta: str, zmiana: float,
                        wolumen_x: float, rsi: float, sl: float, tp: float,
                        sygnal: bool, news: str = "") -> str:
    """
    Generuje analizę techniczną na podstawie danych rynkowych.
    Jeśli podano newsy – dołącza je jako dodatkowy kontekst.
    """
    sygnal_str = "TAK" if sygnal else "NIE"
    prompt = (
        f"Jesteś profesjonalnym analitykiem technicznym. Oceń sytuację spółki {ticker} na podstawie danych:\n"
        f"- Cena: {cena:.2f} {waluta}\n"
        f"- Zmiana ceny: {zmiana:.2f}%\n"
        f"- Wolumen (względem średniej): {wolumen_x:.2f}x\n"
        f"- RSI: {rsi:.1f}\n"
        f"- Stop Loss: {sl:.2f} {waluta}\n"
        f"- Take Profit: {tp:.2f} {waluta}\n"
        f"- Sygnał kupna (techniczny): {sygnal_str}\n"
    )
    if news:
        prompt += f"\nDodatkowe informacje z rynkowych newsów (ostatnie 24h):\n{news[:500]}\n"
        prompt += "Uwzględnij te informacje w swojej ocenie, ale przede wszystkim oprzyj się na danych technicznych."
    else:
        prompt += "\nBrak dostępnych newsów – analizuj wyłącznie dane techniczne."

    prompt += (
        "\n\nNapisz krótkie (do 100 słów) podsumowanie: czy to dobra okazja do zakupu (long), "
        "jaki jest potencjalny zasięg wzrostu, czy istnieje ryzyko, oraz ogólna rekomendacja. "
        "Używaj języka zrozumiałego dla inwestora detalicznego."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd analizy AI: {e}"

# =====================================================================
# ANALIZA POJEDYNCZEJ SPÓŁKI – Z PEŁNĄ ANALIZĄ AI (dane rynkowe + newsy)
# =====================================================================
def analizuj_jedna_spolke(ticker: str, now: str, vol_threshold, price_threshold, sl_pct, tp_pct, deep_analysis):
    try:
        df = yf.download(ticker, period="5d", interval=ui_interval, progress=False)
        if df.empty or len(df) < 15:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df["RSI"] = oblicz_rsi(df)
        if df["RSI"].isna().all():
            return None

        ostatnia = df.iloc[-1]
        poprzednia = df.iloc[-2]

        aktualna_cena = pobierz_wartosc(ostatnia["Close"])
        cena_poprzednia = pobierz_wartosc(poprzednia["Close"])
        aktualny_wolumen = pobierz_wartosc(ostatnia["Volume"])
        sredni_wolumen = pobierz_wartosc(df["Volume"].mean())
        current_rsi = pobierz_wartosc(ostatnia["RSI"])

        if any(v is None for v in [aktualna_cena, cena_poprzednia, aktualny_wolumen, sredni_wolumen, current_rsi]):
            return None
        if aktualna_cena <= 0 or cena_poprzednia <= 0 or sredni_wolumen <= 0:
            return None

        is_gpw = ticker.endswith(".WA")
        waluta = "PLN" if is_gpw else "USD"

        if is_gpw and aktualna_cena > MAX_PRICE_PLN:
            return None
        if not is_gpw and aktualna_cena > MAX_PRICE_USD:
            return None

        zmiana_ceny = ((aktualna_cena - cena_poprzednia) / cena_poprzednia) * 100.0
        skok_wolumenu = aktualny_wolumen / sredni_wolumen

        sygnal_techniczny = (zmiana_ceny >= price_threshold and skok_wolumenu >= vol_threshold)
        rsi_bezpieczny = (30.0 <= current_rsi <= 70.0)
        sygnal_trafiony = sygnal_techniczny and rsi_bezpieczny

        if sygnal_trafiony:
            ocena_trendu = "🟢 Kupuj (Up)"
            sort_score = 3
        elif zmiana_ceny > 0:
            ocena_trendu = "🟡 Trzymaj"
            sort_score = 2
        else:
            ocena_trendu = "🔴 Unikaj"
            sort_score = 1

        sl_na_dole = aktualna_cena * (1 - sl_pct)
        tp_na_gorze = aktualna_cena * (1 + tp_pct)

        # ====================================================
        # POBRANIE NEWSÓW (jeśli włączono) i ANALIZA AI
        # ====================================================
        news = ""
        if deep_analysis:
            news = pobierz_newsy_tavily(ticker)

        # Generujemy analizę AI na podstawie danych rynkowych (+ ewentualnie newsy)
        analiza_ai = analizuj_rynkowo_ai(
            ticker, aktualna_cena, waluta, zmiana_ceny,
            skok_wolumenu, current_rsi, sl_na_dole, tp_na_gorze,
            sygnal_trafiony, news
        )

        # Przygotowanie danych do wyświetlenia
        ticker_info = {
            "Ticker": ticker,
            "Cena": f"{aktualna_cena:.2f} {waluta}",
            "Zmiana %": round(zmiana_ceny, 2),
            "Wolumen (x średniej)": f"{skok_wolumenu:.2f}x",
            "RSI": f"{current_rsi:.1f}",
            "SL": f"{sl_na_dole:.2f} {waluta}",
            "TP": f"{tp_na_gorze:.2f} {waluta}",
            "Status": ocena_trendu,
            "Sygnał": sygnal_trafiony,
            "score": sort_score,
            "Analiza AI": analiza_ai,                     # <-- główna analiza
            "Newsy (pełne)": news if news else "Brak",
        }

        # ====================================================
        # WYSYŁKA NA TELEGRAM (tylko przy sygnale)
        # ====================================================
        if sygnal_trafiony:
            flag_rynek = "🇵🇱" if is_gpw else "🇺🇸"
            wiadomosc = (
                f"🚨 <b>ALERT SNAJPERA AKCJI {flag_rynek}: {ticker}</b>\n"
                f"💰 Cena: {aktualna_cena:.2f} {waluta} (+{zmiana_ceny:.2f}%)\n"
                f"📊 Wolumen: <b>{skok_wolumenu:.1f}x</b> ponad średnią\n"
                f"🛡️ RSI: <b>{current_rsi:.1f}</b>\n"
                f"🛑 SL: {sl_na_dole:.2f} {waluta} | 🎯 TP: {tp_na_gorze:.2f} {waluta}\n\n"
                f"🧠 <b>Analiza AI:</b>\n{analiza_ai}"
            )
            if news:
                wiadomosc += f"\n\n📰 <b>Newsy (24h):</b>\n{news[:500]}"
            send_telegram_message(wiadomosc)

            # Zapis do historii
            historia = {
                "Czas": now,
                "Ticker": ticker,
                "Cena": f"{aktualna_cena:.2f} {waluta}",
                "Zmiana": f"+{zmiana_ceny:.2f}%",
                "Wolumen": f"{skok_wolumenu:.1f}x",
                "RSI": f"{current_rsi:.1f}",
                "Analiza AI": analiza_ai[:150] + "..." if len(analiza_ai) > 150 else analiza_ai,
            }
            st.session_state.alerts_history.append(historia)

        return ticker_info
    except Exception as e:
        st.sidebar.warning(f"Błąd dla {ticker}: {e}")
        return None

# =====================================================================
# GŁÓWNY JOB SKANERA – Z BLOKADĄ I PRZEKAZYWANIEM PARAMETRÓW
# =====================================================================
def job_skanera(status_placeholder=None, progress_bar=None):
    if st.session_state.skan_w_toku:
        if status_placeholder:
            status_placeholder.warning("⏳ Skan już trwa, poczekaj na zakończenie.")
        return

    st.session_state.skan_w_toku = True
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_scan_time = now

    vol_thr = ui_vol_threshold
    price_thr = ui_price_threshold
    sl_pct = ui_sl
    tp_pct = ui_tp
    deep = use_deep_analysis

    total_spolki = len(MARKET_DATABASE)
    lista_podgladu = []
    przetworzone = 0

    if total_spolki == 0:
        if status_placeholder:
            status_placeholder.error("❌ Lista spółek obserwowanych jest pusta.")
        st.session_state.skan_w_toku = False
        return

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                analizuj_jedna_spolke,
                ticker,
                now,
                vol_thr,
                price_thr,
                sl_pct,
                tp_pct,
                deep
            ): ticker
            for ticker in MARKET_DATABASE
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    lista_podgladu.append(res)
            except Exception as e:
                st.sidebar.warning(f"Błąd w wątku: {e}")
            przetworzone += 1
            if progress_bar:
                progress_bar.progress(przetworzone / total_spolki)

    st.session_state.last_scanned_tickers = lista_podgladu
    st.session_state.skan_w_toku = False
    st.session_state.last_auto_scan = datetime.now()

# =====================================================================
# STEROWANIE RADAREM – SIDEBAR
# =====================================================================
st.sidebar.header("⏱️ Sterowanie Radarem")
auto_scan = st.sidebar.selectbox(
    "Automatyczne odświeżanie:",
    ["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"],
)

if st.sidebar.button("🔌 Wyślij testowy alert"):
    if send_telegram_message("🤖 <b>TEST SYSTEMU:</b> Powiadomienia działają!"):
        st.sidebar.success("Test dostarczony!")

st.sidebar.info(f"⏱️ Ostatni udany skan: {st.session_state.last_scan_time}")

# =====================================================================
# PRZYCISKI GŁÓWNE – URUCHOMIENIE SKANERA I CZYSZCZENIE HISTORII
# =====================================================================
col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    uruchom_skan = st.button("🚀 Uruchom Skaner")
with col_btn2:
    if st.button("🗑️ Wyczyść Historię"):
        st.session_state.alerts_history = []
        st.rerun()

status_ph = st.empty()
prog_bar = st.empty()

if uruchom_skan:
    status_ph.write("⌛ Trwa pobieranie i analiza danych giełdowych...")
    prog_bar.progress(0)
    job_skanera(status_ph, prog_bar)
    status_ph.success(f"⚙️ Status: Wielowątkowy radar aktywny | Ostatni skan: {st.session_state.last_scan_time}")

# AUTO-SKAN – BEZ TIME.SLEEP
if auto_scan != "Tylko ręcznie":
    interwal = {"Co 1 minutę": 60, "Co 5 minut": 300, "Co 15 minut": 900}[auto_scan]
    if (datetime.now() - st.session_state.last_auto_scan).total_seconds() >= interwal:
        if not st.session_state.skan_w_toku:
            status_ph.write("⌛ Automatyczny skan...")
            prog_bar.progress(0)
            job_skanera(status_ph, prog_bar)
            status_ph.success(f"⚙️ Automatyczny skan zakończony | {st.session_state.last_scan_time}")
        else:
            status_ph.info("⏳ Skan już trwa, pomijam automatyczne wywołanie.")

# =====================================================================
# WYNIKI – TABELA POSORTOWANA Z PEŁNYMI DANYMI
# =====================================================================
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd aktualnego cyklu skanowania (Posortowany)")
    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    if "score" in df_wyniki.columns:
        df_wyniki = df_wyniki.sort_values(by="score", ascending=False)
        df_wyniki = df_wyniki.drop(columns=["score"])

    # Usuwamy zbędne kolumny (jeśli istnieją)
    for col in ["Sygnał", "Alert_Data"]:
        if col in df_wyniki.columns:
            df_wyniki = df_wyniki.drop(columns=[col])

    # Skracamy długie teksty dla czytelności tabeli
    if "Analiza AI" in df_wyniki.columns:
        df_wyniki["Analiza AI"] = df_wyniki["Analiza AI"].apply(
            lambda x: x[:150] + "..." if isinstance(x, str) and len(x) > 150 else x
        )

    st.dataframe(df_wyniki, use_container_width=True)

    # =====================================================================
    # ROZWIJANE SZCZEGÓŁY – PEŁNA ANALIZA I NEWSY
    # =====================================================================
    st.subheader("📰 Szczegółowe analizy (rozwiń dla tickera)")
    for item in st.session_state.last_scanned_tickers:
        with st.expander(f"{item['Ticker']} – szczegóły analizy"):
            st.write("**🧠 Analiza AI (pełna):**")
            st.write(item.get("Analiza AI", "Brak"))
            st.write("**📰 Newsy (pełne):**")
            st.write(item.get("Newsy (pełne)", "Brak"))

# =====================================================================
# HISTORIA ALERTÓW – ZIELONE OKAZJE
# =====================================================================
if st.session_state.alerts_history:
    st.subheader("📋 Zapamiętane Okazje Snajperskie (Zielone Alerty 🟢)")
    st.dataframe(pd.DataFrame(st.session_state.alerts_history), use_container_width=True)
