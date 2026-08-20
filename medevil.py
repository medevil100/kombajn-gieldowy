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
# MODUŁ KOMUNIKACJI – TELEGRAM
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
# WSKAŹNIKI TECHNICZNE
# =====================================================================
def oblicz_rsi(df: pd.DataFrame, period: int = 14):
    try:
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except:
        return None

def oblicz_macd(df: pd.DataFrame, fast=12, slow=26, signal=9):
    try:
        exp1 = df["Close"].ewm(span=fast, adjust=False).mean()
        exp2 = df["Close"].ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line
        return macd, signal_line, histogram
    except:
        return None, None, None

def oblicz_atr(df: pd.DataFrame, period: int = 14):
    try:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    except:
        return None

def oblicz_srednie_kroczace(df: pd.DataFrame, okresy=[20, 50]):
    wyniki = {}
    for ok in okresy:
        try:
            wyniki[f"MA{ok}"] = df["Close"].rolling(window=ok).mean()
        except:
            wyniki[f"MA{ok}"] = None
    return wyniki

# =====================================================================
# POMOCNICZA FUNKCJA DO BEZPIECZNEGO POBRANIA WARTOŚCI
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
    except:
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
# ANALIZA AI NA PODSTAWIE DANYCH RYNKOWYCH + WSKAŹNIKI
# =====================================================================
def analizuj_rynkowo_ai(ticker: str, dane: dict, news: str = "") -> str:
    """
    dane: słownik z kluczami: cena, waluta, zmiana, wolumen_x, rsi,
          macd_hist, atr, ma20, ma50, sl, tp, sygnal
    """
    prompt = f"Jesteś profesjonalnym analitykiem technicznym. Oceń sytuację spółki {ticker} na podstawie poniższych danych:\n"
    for k, v in dane.items():
        if k in ["cena", "waluta", "zmiana", "wolumen_x", "rsi", "macd_hist", "atr", "ma20", "ma50", "sl", "tp"]:
            prompt += f"- {k}: {v}\n"
    prompt += f"- Sygnał kupna (techniczny): {'TAK' if dane['sygnal'] else 'NIE'}\n"

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
# ANALIZA POJEDYNCZEJ SPÓŁKI – Z PEŁNYMI WSKAŹNIKAMI
# =====================================================================
def analizuj_jedna_spolke(ticker: str, now: str, vol_threshold, price_threshold, sl_pct, tp_pct, deep_analysis):
    try:
        df = yf.download(ticker, period="5d", interval=ui_interval, progress=False)
        if df.empty or len(df) < 30:  # potrzeba więcej danych dla MA50
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Oblicz wszystkie wskaźniki
        df["RSI"] = oblicz_rsi(df)
        macd, signal, hist = oblicz_macd(df)
        df["MACD"] = macd
        df["MACD_signal"] = signal
        df["MACD_hist"] = hist
        df["ATR"] = oblicz_atr(df)
        ma = oblicz_srednie_kroczace(df, [20, 50])
        if ma.get("MA20") is not None:
            df["MA20"] = ma["MA20"]
        if ma.get("MA50") is not None:
            df["MA50"] = ma["MA50"]

        # Sprawdź, czy ostatnie dane są kompletne
        ostatnia = df.iloc[-1]
        poprzednia = df.iloc[-2]

        # Pobieramy wartości
        aktualna_cena = pobierz_wartosc(ostatnia["Close"])
        cena_poprzednia = pobierz_wartosc(poprzednia["Close"])
        aktualny_wolumen = pobierz_wartosc(ostatnia["Volume"])
        sredni_wolumen = pobierz_wartosc(df["Volume"].mean())
        current_rsi = pobierz_wartosc(ostatnia["RSI"])
        macd_hist = pobierz_wartosc(ostatnia["MACD_hist"]) if "MACD_hist" in ostatnia else None
        atr = pobierz_wartosc(ostatnia["ATR"]) if "ATR" in ostatnia else None
        ma20 = pobierz_wartosc(ostatnia["MA20"]) if "MA20" in ostatnia else None
        ma50 = pobierz_wartosc(ostatnia["MA50"]) if "MA50" in ostatnia else None

        # Walidacja – nie wszystkie muszą być obecne, ale kluczowe tak
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
        # ZBIERAMY DANE DO ANALIZY AI
        # ====================================================
        dane_do_ai = {
            "cena": f"{aktualna_cena:.2f} {waluta}",
            "zmiana": f"{zmiana_ceny:.2f}%",
            "wolumen_x": f"{skok_wolumenu:.2f}x",
            "rsi": f"{current_rsi:.1f}",
            "sl": f"{sl_na_dole:.2f}",
            "tp": f"{tp_na_gorze:.2f}",
            "sygnal": sygnal_trafiony,
        }
        # Dodajemy opcjonalne wskaźniki
        if macd_hist is not None:
            dane_do_ai["macd_hist"] = f"{macd_hist:.3f}"
        if atr is not None:
            dane_do_ai["atr"] = f"{atr:.3f}"
        if ma20 is not None:
            dane_do_ai["ma20"] = f"{ma20:.2f}"
        if ma50 is not None:
            dane_do_ai["ma50"] = f"{ma50:.2f}"

        # Pobieramy newsy (jeśli włączono)
        news = ""
        if deep_analysis:
            news = pobierz_newsy_tavily(ticker)

        # Generujemy analizę AI
        analiza_ai = analizuj_rynkowo_ai(ticker, dane_do_ai, news)

        # Przygotowanie danych do wyświetlenia
        ticker_info = {
            "Ticker": ticker,
            "Cena": f"{aktualna_cena:.2f} {waluta}",
            "Zmiana %": round(zmiana_ceny, 2),
            "Wolumen (x)": f"{skok_wolumenu:.2f}x",
            "RSI": f"{current_rsi:.1f}",
            "SL": f"{sl_na_dole:.2f}",
            "TP": f"{tp_na_gorze:.2f}",
            "Status": ocena_trendu,
            "Sygnał": sygnal_trafiony,
            "score": sort_score,
            "Analiza AI": analiza_ai,
            "Newsy (pełne)": news if news else "Brak",
            # Dodatkowe wskaźniki do wyświetlenia w tabeli (opcjonalnie)
            "MACD hist": f"{macd_hist:.3f}" if macd_hist is not None else "brak",
            "ATR": f"{atr:.3f}" if atr is not None else "brak",
            "MA20": f"{ma20:.2f}" if ma20 is not None else "brak",
            "MA50": f"{ma50:.2f}" if ma50 is not None else "brak",
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
                f"🛑 SL: {sl_na_dole:.2f} {waluta} | 🎯 TP: {tp_na_gorze:.2f} {waluta}\n"
                f"📈 MACD hist: {macd_hist:.3f}" if macd_hist is not None else ""
                f"📉 ATR: {atr:.3f}" if atr is not None else ""
                f"\n\n🧠 <b>Analiza AI:</b>\n{analiza_ai}"
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
# GŁÓWNY JOB SKANERA
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
# WYNIKI – TABELA Z KOLOROWANIEM (użyjemy stylera Pandas)
# =====================================================================
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd aktualnego cyklu skanowania (Posortowany)")
    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    # Sortowanie
    if "score" in df_wyniki.columns:
        df_wyniki = df_wyniki.sort_values(by="score", ascending=False)
        df_wyniki = df_wyniki.drop(columns=["score"])

    # Usuwamy zbędne kolumny
    for col in ["Sygnał", "Alert_Data"]:
        if col in df_wyniki.columns:
            df_wyniki = df_wyniki.drop(columns=[col])

    # Skracamy długie teksty dla czytelności
    if "Analiza AI" in df_wyniki.columns:
        df_wyniki["Analiza AI"] = df_wyniki["Analiza AI"].apply(
            lambda x: x[:150] + "..." if isinstance(x, str) and len(x) > 150 else x
        )

    # ===== KOLOROWANIE (dla kolumn liczbowych) =====
    # Tworzymy styler, który koloruje tło komórek w zależności od wartości
    def koloruj_zmiane(val):
        if isinstance(val, (int, float)):
            if val > 2:
                return 'background-color: #90EE90'  # zielony
            elif val < -2:
                return 'background-color: #FFCCCB'  # czerwony
        return ''

    def koloruj_rsi(val):
        if isinstance(val, (int, float)):
            if 30 <= val <= 70:
                return 'background-color: #FFFF99'  # żółty
            elif val > 70:
                return 'background-color: #FFA07A'  # pomarańczowy (przegrzany)
            elif val < 30:
                return 'background-color: #87CEEB'  # niebieski (wyprzedany)
        return ''

    # Zastosowanie stylera do wybranych kolumn
    # Uwaga: kolumny muszą być numeryczne, więc konwertujemy odpowiednie
    if "Zmiana %" in df_wyniki.columns:
        df_wyniki["Zmiana %"] = pd.to_numeric(df_wyniki["Zmiana %"], errors='coerce')
        df_wyniki = df_wyniki.style.applymap(koloruj_zmiane, subset=["Zmiana %"])

    if "RSI" in df_wyniki.columns:
        # RSI może być stringiem z wartością, wyciągamy liczbę
        # Najpierw przekonwertujmy na float
        df_wyniki_copy = df_wyniki.data.copy() if hasattr(df_wyniki, 'data') else df_wyniki
        if "RSI" in df_wyniki_copy.columns:
            df_wyniki_copy["RSI_num"] = df_wyniki_copy["RSI"].str.extract(r'(\d+\.?\d*)').astype(float)
            df_wyniki_copy = df_wyniki_copy.style.applymap(koloruj_rsi, subset=["RSI_num"])
            # Ukryj kolumnę pomocniczą
            df_wyniki = df_wyniki_copy.hide(axis='columns', subset=['RSI_num'])
        else:
            df_wyniki = df_wyniki.style

    # Wyświetlenie
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
