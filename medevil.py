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
# SESJA
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
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None

# =====================================================================
# ŁADOWANIE KLUCZY
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
# OKNO TICKERÓW
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
# SUWAKI
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

use_deep_analysis = st.checkbox("🧠 Włącz pogłębioną analizę (newsy + AI)", value=True)
show_full_news = st.checkbox("📰 Pokaż pełne newsy w wynikach", value=False)

# =====================================================================
# FUNKCJE POMOCNICZE
# =====================================================================
def send_telegram_message(message: str) -> bool:
    czysty_token = str(TELEGRAM_TOKEN).strip()
    czysty_chat_id = str(TELEGRAM_CHAT_ID).strip()
    url = f"https://api.telegram.org/bot{czysty_token}/sendMessage"
    payload = {"chat_id": czysty_chat_id, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=5)
        return resp.status_code == 200
    except Exception:
        return False

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

def pobierz_newsy_tavily(ticker: str) -> str:
    try:
        from_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")
        query = f"{ticker} stock news OR akcje"
        response = tavily.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_domains=["reuters.com", "bloomberg.com", "cnbc.com", "money.pl", "pb.pl"],
            time_range={"from": from_date, "to": to_date}
        )
        if not response or "results" not in response:
            return "Brak newsów."
        news_text = ""
        for result in response["results"][:5]:
            title = result.get("title", "")
            snippet = result.get("content", "")
            news_text += f"• {title}\n  {snippet}\n\n"
        return news_text.strip()
    except Exception as e:
        return f"Błąd pobierania newsów: {e}"

def analizuj_newsy_openai(ticker: str, news: str, cena: float, waluta: str) -> dict:
    if not news or news == "Brak newsów.":
        return {"ocena": "Brak danych", "komentarz": "Brak świeżych wiadomości."}
    prompt = (
        f"Jesteś analitykiem finansowym. Dla spółki {ticker} (cena {cena:.2f} {waluta}) "
        f"pojawiły się następujące wiadomości z ostatnich 24 godzin:\n\n{news}\n\n"
        "Na podstawie tych informacji oceń krótkoterminowy wpływ na kurs (0-10 skala, "
        "gdzie 0 – bardzo negatywny, 10 – bardzo pozytywny) i napisz 2-3 zdania "
        "podsumowujące, czy to dobra okazja do zakupu (long). Odpowiedz zwięźle."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.5,
        )
        text = response.choices[0].message.content.strip()
        # Próbujemy wyciągnąć ocenę liczbową (zakładamy, że jest w tekście)
        # Prosta heurystyka: szukamy liczby 0-10
        import re
        match = re.search(r'\b([0-9]|10)\b', text)
        score = int(match.group(1)) if match else None
        return {"ocena": score, "komentarz": text}
    except Exception as e:
        return {"ocena": None, "komentarz": f"Błąd AI: {e}"}

# =====================================================================
# ANALIZA POJEDYNCZEJ SPÓŁKI (ROZBUDOWANA)
# =====================================================================
def analizuj_jedna_spolke(ticker, now, vol_threshold, price_threshold, sl_pct, tp_pct, deep_analysis):
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

        sl_na_dole = aktualna_cena * (1 - sl_pct)
        tp_na_gorze = aktualna_cena * (1 + tp_pct)

        # Podstawowe info
        ticker_info = {
            "Ticker": ticker,
            "Cena": f"{aktualna_cena:.2f} {waluta}",
            "Zmiana %": round(zmiana_ceny, 2),
            "Wolumen (x śred.)": f"{skok_wolumenu:.2f}x",
            "RSI": f"{current_rsi:.1f}",
            "SL": f"{sl_na_dole:.2f} {waluta}",
            "TP": f"{tp_na_gorze:.2f} {waluta}",
            "Sygnał": "🟢 TAK" if sygnal_trafiony else "🔴 NIE",
            "score": 3 if sygnal_trafiony else (2 if zmiana_ceny > 0 else 1),
            "news_raw": "",
            "analiza_ai": "",
            "ocena_sentymentu": None,
        }

        # Jeśli sygnał i głęboka analiza
        if sygnal_trafiony and deep_analysis:
            news = pobierz_newsy_tavily(ticker)
            ticker_info["news_raw"] = news
            if news and news != "Brak newsów.":
                analiza = analizuj_newsy_openai(ticker, news, aktualna_cena, waluta)
                ticker_info["analiza_ai"] = analiza.get("komentarz", "")
                ticker_info["ocena_sentymentu"] = analiza.get("ocena")
            else:
                ticker_info["analiza_ai"] = "Brak newsów do analizy."
            # Wysłanie na Telegram
            flag = "🇵🇱" if is_gpw else "🇺🇸"
            msg = (
                f"🚨 <b>ALERT {flag} {ticker}</b>\n"
                f"💰 {aktualna_cena:.2f} {waluta} (+{zmiana_ceny:.2f}%)\n"
                f"📊 Wolumen: {skok_wolumenu:.1f}x\n"
                f"🛡️ RSI: {current_rsi:.1f}\n"
                f"🛑 SL: {sl_na_dole:.2f} | 🎯 TP: {tp_na_gorze:.2f}\n"
                f"📰 Newsy:\n{news[:500]}\n\n"
                f"🧠 AI: {ticker_info['analiza_ai']}"
            )
            send_telegram_message(msg)

            # Zapisz do historii z pełnymi danymi
            st.session_state.alerts_history.append({
                "Czas": now,
                "Ticker": ticker,
                "Cena": f"{aktualna_cena:.2f} {waluta}",
                "Zmiana": f"+{zmiana_ceny:.2f}%",
                "Wolumen": f"{skok_wolumenu:.1f}x",
                "RSI": f"{current_rsi:.1f}",
                "News (skrót)": news[:100] + "..." if len(news) > 100 else news,
                "Analiza AI": ticker_info["analiza_ai"],
                "Ocena (0-10)": ticker_info["ocena_sentymentu"],
            })
        elif sygnal_trafiony:
            # Bez deep analysis – tylko podstawowy alert
            flag = "🇵🇱" if is_gpw else "🇺🇸"
            msg = (
                f"🚨 <b>ALERT {flag} {ticker}</b>\n"
                f"💰 {aktualna_cena:.2f} {waluta} (+{zmiana_ceny:.2f}%)\n"
                f"📊 Wolumen: {skok_wolumenu:.1f}x\n"
                f"🛡️ RSI: {current_rsi:.1f}\n"
                f"🛑 SL: {sl_na_dole:.2f} | 🎯 TP: {tp_na_gorze:.2f}"
            )
            send_telegram_message(msg)
            st.session_state.alerts_history.append({
                "Czas": now,
                "Ticker": ticker,
                "Cena": f"{aktualna_cena:.2f} {waluta}",
                "Zmiana": f"+{zmiana_ceny:.2f}%",
                "Wolumen": f"{skok_wolumenu:.1f}x",
                "RSI": f"{current_rsi:.1f}",
            })

        return ticker_info
    except Exception as e:
        st.sidebar.warning(f"Błąd dla {ticker}: {e}")
        return None

# =====================================================================
# JOB SKANERA
# =====================================================================
def job_skanera(status_placeholder=None, progress_bar=None):
    if st.session_state.skan_w_toku:
        status_placeholder.warning("⏳ Skan już trwa...")
        return

    st.session_state.skan_w_toku = True
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_scan_time = now

    vol_thr = ui_vol_threshold
    price_thr = ui_price_threshold
    sl_pct = ui_sl
    tp_pct = ui_tp
    deep = use_deep_analysis

    total = len(MARKET_DATABASE)
    lista = []
    przetworzone = 0

    if total == 0:
        status_placeholder.error("❌ Lista jest pusta.")
        st.session_state.skan_w_toku = False
        return

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(analizuj_jedna_spolke, ticker, now, vol_thr, price_thr, sl_pct, tp_pct, deep): ticker
            for ticker in MARKET_DATABASE
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    lista.append(res)
            except Exception as e:
                st.sidebar.warning(f"Błąd wątku: {e}")
            przetworzone += 1
            if progress_bar:
                progress_bar.progress(przetworzone / total)

    st.session_state.last_scanned_tickers = lista
    st.session_state.skan_w_toku = False
    st.session_state.last_auto_scan = datetime.now()

# =====================================================================
# SIDEBAR
# =====================================================================
st.sidebar.header("⏱️ Sterowanie Radarem")
auto_scan = st.sidebar.selectbox(
    "Automatyczne odświeżanie:",
    ["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"],
)
if st.sidebar.button("🔌 Test Telegram"):
    if send_telegram_message("🤖 Test OK"):
        st.sidebar.success("Działa!")
    else:
        st.sidebar.error("Błąd.")

st.sidebar.info(f"⏱️ Ostatni skan: {st.session_state.last_scan_time}")

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
    status_ph.write("⌛ Trwa skanowanie...")
    prog_bar.progress(0)
    job_skanera(status_ph, prog_bar)
    status_ph.success(f"✅ Skan zakończony | {st.session_state.last_scan_time}")

# AUTO-SKAN (bez sleep)
if auto_scan != "Tylko ręcznie":
    interwal = {"Co 1 minutę": 60, "Co 5 minut": 300, "Co 15 minut": 900}[auto_scan]
    if (datetime.now() - st.session_state.last_auto_scan).total_seconds() >= interwal:
        if not st.session_state.skan_w_toku:
            status_ph.write("⌛ Auto-skan...")
            prog_bar.progress(0)
            job_skanera(status_ph, prog_bar)
            status_ph.success(f"✅ Auto-skan | {st.session_state.last_scan_time}")

# =====================================================================
# WYŚWIETLANIE WYNIKÓW – PEŁNA TABELA I SZCZEGÓŁY
# =====================================================================
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Wyniki skanowania")
    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    # Sortowanie
    if "score" in df_wyniki.columns:
        df_wyniki = df_wyniki.sort_values(by="score", ascending=False)
        df_wyniki = df_wyniki.drop(columns=["score"])

    # Wybór kolumn do wyświetlenia
    cols_to_show = ["Ticker", "Cena", "Zmiana %", "Wolumen (x śred.)", "RSI", "SL", "TP", "Sygnał"]
    if use_deep_analysis:
        cols_to_show += ["ocena_sentymentu", "analiza_ai"]
        if show_full_news:
            cols_to_show += ["news_raw"]

    # Filtrujemy kolumny, które istnieją
    available_cols = [col for col in cols_to_show if col in df_wyniki.columns]
    df_display = df_wyniki[available_cols].copy()

    # Zmiana nazw na bardziej czytelne
    rename_map = {
        "ocena_sentymentu": "Ocena AI (0-10)",
        "analiza_ai": "Komentarz AI",
        "news_raw": "Newsy (24h)",
        "Wolumen (x śred.)": "Wolumen (x)",
    }
    df_display = df_display.rename(columns=rename_map)

    st.dataframe(df_display, use_container_width=True)

    # ========================================================
    # SZCZEGÓŁOWY RAPORT DLA WYBRANEGO TICKERA
    # ========================================================
    st.subheader("🔍 Szczegółowy raport dla wybranego tickera")
    ticker_options = ["-- Wybierz --"] + [t["Ticker"] for t in st.session_state.last_scanned_tickers if "Ticker" in t]
    selected = st.selectbox("Kliknij, aby zobaczyć pełną analizę:", ticker_options)
    if selected != "-- Wybierz --":
        # Znajdź dane
        for item in st.session_state.last_scanned_tickers:
            if item.get("Ticker") == selected:
                st.markdown(f"### 📈 {selected}")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Cena", item.get("Cena", "brak"))
                    st.metric("Zmiana %", f"{item.get('Zmiana %', 0)}%")
                    st.metric("Wolumen (x)", item.get("Wolumen (x śred.)", "brak"))
                with col2:
                    st.metric("RSI", item.get("RSI", "brak"))
                    st.metric("SL", item.get("SL", "brak"))
                    st.metric("TP", item.get("TP", "brak"))

                if "news_raw" in item and item["news_raw"]:
                    st.markdown("#### 📰 Pełne newsy (ostatnie 24h):")
                    st.text_area("", item["news_raw"], height=200)
                else:
                    st.info("Brak newsów dla tego tickera.")

                if "analiza_ai" in item and item["analiza_ai"]:
                    st.markdown("#### 🧠 Analiza AI:")
                    st.write(item["analiza_ai"])
                    if "ocena_sentymentu" in item and item["ocena_sentymentu"] is not None:
                        st.metric("Ocena sentymentu (0-10)", item["ocena_sentymentu"])
                else:
                    st.info("Brak analizy AI (wyłączona lub brak danych).")
                break

# =====================================================================
# HISTORIA ALERTÓW
# =====================================================================
if st.session_state.alerts_history:
    st.subheader("📋 Historia alertów")
    df_hist = pd.DataFrame(st.session_state.alerts_history)
    st.dataframe(df_hist, use_container_width=True)
