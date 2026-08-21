import time
import requests
import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tavily import TavilyClient

# =====================================================================
# KONFIGURACJA STRONY
# =====================================================================
st.set_page_config(page_title="Snajper Rynkowy Custom", page_icon="🎯", layout="wide")
st.title("🎯 Twój Autorski Skaner Groszówek: Market Sniper")

# =====================================================================
# SESJA – przechowywanie ustawień i historii
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

# Ustawienia zapisywane w sesji (z niższymi progami na start)
if "ui_interval" not in st.session_state:
    st.session_state.ui_interval = "30m"
if "ui_vol_threshold" not in st.session_state:
    st.session_state.ui_vol_threshold = 1.5   # niższy próg dla testów
if "ui_price_threshold" not in st.session_state:
    st.session_state.ui_price_threshold = 0.5  # niższy próg dla testów
if "ui_sl" not in st.session_state:
    st.session_state.ui_sl = 0.05
if "ui_tp" not in st.session_state:
    st.session_state.ui_tp = 0.15
if "use_deep_analysis" not in st.session_state:
    st.session_state.use_deep_analysis = True
if "auto_scan" not in st.session_state:
    st.session_state.auto_scan = "Tylko ręcznie"
if "market_database" not in st.session_state:
    st.session_state.market_database = ["APS.WA", "STX.WA"]  # przykładowe tickery – możesz zmienić
if "filter_gpw" not in st.session_state:
    st.session_state.filter_gpw = True
if "filter_usa" not in st.session_state:
    st.session_state.filter_usa = True
if "rsi_min" not in st.session_state:
    st.session_state.rsi_min = 10   # szeroki zakres, aby nie odrzucać
if "rsi_max" not in st.session_state:
    st.session_state.rsi_max = 90
if "macd_sign" not in st.session_state:
    st.session_state.macd_sign = "Dowolny"

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
# LISTA OBSERWACYJNA Z ZAPISEM W SESJI
# =====================================================================
st.subheader("📝 Zarządzanie Twoją Listą Obserwacyjną")
domyslna_lista = ", ".join(st.session_state.market_database)
user_input = st.text_area(
    "Wklej tutaj swoje spółki rozdzielone przecinkami (USA lub GPW z końcówką .WA):",
    value=domyslna_lista,
    height=100
)
st.session_state.market_database = [t.strip().upper() for t in user_input.split(",") if t.strip()]

# =====================================================================
# FILTRY RYNKOWE
# =====================================================================
col_f1, col_f2 = st.columns(2)
with col_f1:
    st.session_state.filter_gpw = st.checkbox("🇵🇱 GPW (z .WA)", value=st.session_state.filter_gpw)
with col_f2:
    st.session_state.filter_usa = st.checkbox("🇺🇸 USA (bez .WA)", value=st.session_state.filter_usa)

MARKET_DATABASE = []
for t in st.session_state.market_database:
    is_gpw = t.endswith(".WA")
    if is_gpw and st.session_state.filter_gpw:
        MARKET_DATABASE.append(t)
    elif not is_gpw and st.session_state.filter_usa:
        MARKET_DATABASE.append(t)

if not MARKET_DATABASE:
    st.warning("⚠️ Brak spółek po zastosowaniu filtrów – sprawdź listę lub filtry.")

# =====================================================================
# SUWAKI – z zapisem w sesji
# =====================================================================
col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns(5)
with col_p1:
    st.session_state.ui_interval = st.selectbox(
        "Interwał świecy:",
        ["1m", "5m", "15m", "30m", "1h"],
        index=["1m", "5m", "15m", "30m", "1h"].index(st.session_state.ui_interval)
    )
with col_p2:
    st.session_state.ui_vol_threshold = st.slider(
        "Próg skoku obrotu (x średniej):", 0.5, 10.0,
        st.session_state.ui_vol_threshold, step=0.5
    )
with col_p3:
    st.session_state.ui_price_threshold = st.slider(
        "Próg wzrostu ceny (%):", 0.1, 5.0,
        st.session_state.ui_price_threshold, step=0.1
    )
with col_p4:
    st.session_state.ui_sl = st.slider(
        "Stop Loss (% od ceny):", 1, 20,
        int(st.session_state.ui_sl * 100), step=1
    ) / 100.0
with col_p5:
    st.session_state.ui_tp = st.slider(
        "Take Profit (% od ceny):", 5, 50,
        int(st.session_state.ui_tp * 100), step=5
    ) / 100.0

# =====================================================================
# DODATKOWE WARUNKI ALERTÓW – zapis do sesji
# =====================================================================
st.subheader("⚙️ Dodatkowe warunki sygnału")
col_c1, col_c2, col_c3 = st.columns(3)
with col_c1:
    rsi_min = st.slider("Min RSI", 10, 80, st.session_state.rsi_min, step=5)
    st.session_state.rsi_min = rsi_min
with col_c2:
    rsi_max = st.slider("Max RSI", 20, 90, st.session_state.rsi_max, step=5)
    st.session_state.rsi_max = rsi_max
with col_c3:
    macd_sign = st.selectbox("MACD", ["Dowolny", ">0", "<0"], 
                             index=["Dowolny", ">0", "<0"].index(st.session_state.macd_sign))
    st.session_state.macd_sign = macd_sign

# =====================================================================
# OPCJA ANALIZY Z NEWSAMI
# =====================================================================
st.session_state.use_deep_analysis = st.checkbox(
    "🧠 Włącz analizę z użyciem newsów (Tavily)",
    value=st.session_state.use_deep_analysis
)

# =====================================================================
# TELEGRAM
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
# WSKAŹNIKI TECHNICZNE (rozszerzone)
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

def oblicz_sma(df: pd.DataFrame, period: int):
    return df["Close"].rolling(window=period).mean()

def oblicz_macd(df: pd.DataFrame):
    try:
        exp12 = df["Close"].ewm(span=12, adjust=False).mean()
        exp26 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal
    except Exception:
        return None, None

def oblicz_atr(df: pd.DataFrame, period: int = 14):
    try:
        high = df["High"]
        low = df["Low"]
        close = df["Close"].shift(1)
        tr1 = high - low
        tr2 = (high - close).abs()
        tr3 = (low - close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    except Exception:
        return None

def oblicz_momentum(df: pd.DataFrame, period: int = 5):
    try:
        return (df["Close"] / df["Close"].shift(period) - 1) * 100
    except Exception:
        return None

def oblicz_bollinger(df: pd.DataFrame, period: int = 20, std: int = 2):
    try:
        sma = df["Close"].rolling(period).mean()
        std_dev = df["Close"].rolling(period).std()
        upper = sma + std * std_dev
        lower = sma - std * std_dev
        return upper, sma, lower
    except Exception:
        return None, None, None

def oblicz_obv(df: pd.DataFrame):
    try:
        obv = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()
        return obv
    except Exception:
        return None

def oblicz_adx(df: pd.DataFrame, period: int = 14):
    try:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        minus_dm = abs(minus_dm)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(period).mean()
        return adx
    except Exception:
        return None

# =====================================================================
# POMOCNICZA FUNKCJA DO POBRANIA WARTOŚCI
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
# TAVILY – NEWS + SENTYMENT
# =====================================================================
def pobierz_newsy_tavily(ticker: str) -> tuple:
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
            return "", 0
        news_text = ""
        pozytywne = ["wzrost", "zysk", "rekord", "kupno", "kontrakt", "dobry", "przebicie", "partnerstwo"]
        negatywne = ["spadek", "strata", "obniżenie", "sprzedaż", "problem", "ryzyko", "kary", "spowolnienie"]
        sent_score = 0
        for result in response["results"][:5]:
            title = result.get("title", "")
            snippet = result.get("content", "")
            news_text += f"• {title}\n  {snippet}\n\n"
            for p in pozytywne:
                if p in title.lower() or p in snippet.lower():
                    sent_score += 1
            for n in negatywne:
                if n in title.lower() or n in snippet.lower():
                    sent_score -= 1
        sentiment = 1 if sent_score > 0 else (-1 if sent_score < 0 else 0)
        return news_text.strip(), sentiment
    except Exception as e:
        st.sidebar.warning(f"Tavily błąd dla {ticker}: {e}")
        return "", 0

# =====================================================================
# ANALIZA AI
# =====================================================================
def analizuj_rynkowo_ai(ticker: str, cena: float, waluta: str, zmiana: float,
                        wolumen_x: float, rsi: float, sl: float, tp: float,
                        sygnal: bool, sma20: float, sma50: float,
                        macd: float, atr: float, momentum: float,
                        bb_upper: float, bb_mid: float, bb_lower: float,
                        obv: float, adx: float, news: str = "", sentiment: int = 0) -> str:
    sygnal_str = "TAK" if sygnal else "NIE"
    sent_str = "pozytywny" if sentiment > 0 else ("negatywny" if sentiment < 0 else "neutralny")
    prompt = (
        f"Jesteś profesjonalnym analitykiem technicznym. Oceń sytuację spółki {ticker} na podstawie danych:\n"
        f"- Cena: {cena:.2f} {waluta}\n"
        f"- Zmiana ceny: {zmiana:.2f}%\n"
        f"- Wolumen (względem średniej): {wolumen_x:.2f}x\n"
        f"- RSI: {rsi:.1f}\n"
        f"- SMA20: {sma20:.2f} {waluta}\n"
        f"- SMA50: {sma50:.2f} {waluta}\n"
        f"- MACD: {macd:.3f}\n"
        f"- ATR (zmienność): {atr:.2f} {waluta}\n"
        f"- Momentum (5 świec): {momentum:.2f}%\n"
        f"- Bollinger Górne: {bb_upper:.2f}, Środkowe: {bb_mid:.2f}, Dolne: {bb_lower:.2f}\n"
        f"- OBV: {obv:.0f}\n"
        f"- ADX: {adx:.1f}\n"
        f"- Stop Loss: {sl:.2f} {waluta}\n"
        f"- Take Profit: {tp:.2f} {waluta}\n"
        f"- Sygnał kupna (techniczny): {sygnal_str}\n"
    )
    if news:
        prompt += f"\nDodatkowe informacje z rynkowych newsów (ostatnie 24h):\n{news[:500]}\n"
        prompt += f"Sentyment newsów: {sent_str}\n"
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
# ANALIZA POJEDYNCZEJ SPÓŁKI (z dynamicznym okresem i diagnostyką)
# =====================================================================
def analizuj_jedna_spolke(ticker: str, now: str, vol_threshold, price_threshold,
                          sl_pct, tp_pct, deep_analysis,
                          rsi_min, rsi_max, macd_sign):
    """
    Zwraca słownik z danymi lub słownik z błędem.
    """
    try:
        # Dynamiczny okres pobierania
        interval = st.session_state.ui_interval
        if interval in ["1m", "5m", "15m", "30m"]:
            period = "5d"
        elif interval == "1h":
            period = "1mo"
        else:
            period = "3mo"

        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return {
                "Ticker": ticker,
                "Status": "❌ Brak danych",
                "score": 0,
                "Analiza AI": "Brak danych z Yahoo Finance."
            }
        if len(df) < 20:
            return {
                "Ticker": ticker,
                "Status": "❌ Za mało świec",
                "score": 0,
                "Analiza AI": f"Potrzebuję co najmniej 20 świec, mam tylko {len(df)}."
            }

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Oblicz wskaźniki
        df["RSI"] = oblicz_rsi(df)
        df["SMA20"] = oblicz_sma(df, 20)
        df["SMA50"] = oblicz_sma(df, 50) if len(df) >= 50 else None
        macd, signal = oblicz_macd(df)
        df["MACD"] = macd
        df["Signal"] = signal
        df["ATR"] = oblicz_atr(df)
        df["Momentum"] = oblicz_momentum(df)
        bb_upper, bb_mid, bb_lower = oblicz_bollinger(df)
        df["BB_Upper"] = bb_upper
        df["BB_Mid"] = bb_mid
        df["BB_Lower"] = bb_lower
        df["OBV"] = oblicz_obv(df)
        df["ADX"] = oblicz_adx(df)

        if df["RSI"].isna().all():
            return {
                "Ticker": ticker,
                "Status": "❌ RSI nieobliczalny",
                "score": 0,
                "Analiza AI": "Nie udało się obliczyć RSI – dane mogą być niekompletne."
            }

        ostatnia = df.iloc[-1]
        poprzednia = df.iloc[-2]

        aktualna_cena = pobierz_wartosc(ostatnia["Close"])
        cena_poprzednia = pobierz_wartosc(poprzednia["Close"])
        aktualny_wolumen = pobierz_wartosc(ostatnia["Volume"])
        sredni_wolumen = pobierz_wartosc(df["Volume"].mean())
        current_rsi = pobierz_wartosc(ostatnia["RSI"])
        sma20 = pobierz_wartosc(ostatnia["SMA20"])
        sma50 = pobierz_wartosc(ostatnia["SMA50"]) if "SMA50" in ostatnia else None
        macd_val = pobierz_wartosc(ostatnia["MACD"])
        atr_val = pobierz_wartosc(ostatnia["ATR"])
        momentum_val = pobierz_wartosc(ostatnia["Momentum"])
        bb_upper_val = pobierz_wartosc(ostatnia["BB_Upper"])
        bb_mid_val = pobierz_wartosc(ostatnia["BB_Mid"])
        bb_lower_val = pobierz_wartosc(ostatnia["BB_Lower"])
        obv_val = pobierz_wartosc(ostatnia["OBV"])
        adx_val = pobierz_wartosc(ostatnia["ADX"])

        # Sprawdzenie, czy wszystkie potrzebne wartości są dostępne
        if any(v is None for v in [aktualna_cena, cena_poprzednia, aktualny_wolumen, sredni_wolumen, current_rsi]):
            return {
                "Ticker": ticker,
                "Status": "❌ Brak kluczowych danych (cena/wolumen/RSI)",
                "score": 0,
                "Analiza AI": "Niektóre dane są puste – sprawdź ticker."
            }
        if aktualna_cena <= 0 or cena_poprzednia <= 0 or sredni_wolumen <= 0:
            return {
                "Ticker": ticker,
                "Status": "❌ Nieprawidłowe wartości (cena <=0 lub wolumen =0)",
                "score": 0,
                "Analiza AI": "Cena lub wolumen są zerowe – dane niepoprawne."
            }

        is_gpw = ticker.endswith(".WA")
        waluta = "PLN" if is_gpw else "USD"

        # Filtry cenowe
        if is_gpw and aktualna_cena > MAX_PRICE_PLN:
            return {
                "Ticker": ticker,
                "Status": f"⛔ Cena > {MAX_PRICE_PLN} PLN",
                "score": 0,
                "Analiza AI": f"Cena {aktualna_cena:.2f} przekracza limit {MAX_PRICE_PLN} PLN."
            }
        if not is_gpw and aktualna_cena > MAX_PRICE_USD:
            return {
                "Ticker": ticker,
                "Status": f"⛔ Cena > {MAX_PRICE_USD} USD",
                "score": 0,
                "Analiza AI": f"Cena {aktualna_cena:.2f} przekracza limit {MAX_PRICE_USD} USD."
            }

        zmiana_ceny = ((aktualna_cena - cena_poprzednia) / cena_poprzednia) * 100.0
        skok_wolumenu = aktualny_wolumen / sredni_wolumen

        # Sygnał
        sygnal_techniczny = (zmiana_ceny >= price_threshold and skok_wolumenu >= vol_threshold)
        rsi_warunek = (rsi_min <= current_rsi <= rsi_max)
        macd_warunek = True
        if macd_sign == ">0":
            macd_warunek = macd_val > 0 if macd_val is not None else False
        elif macd_sign == "<0":
            macd_warunek = macd_val < 0 if macd_val is not None else False

        sygnal_trafiony = sygnal_techniczny and rsi_warunek and macd_warunek

        # Ustalamy status
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

        news = ""
        sentiment = 0
        if deep_analysis:
            news, sentiment = pobierz_newsy_tavily(ticker)

        analiza_ai = analizuj_rynkowo_ai(
            ticker, aktualna_cena, waluta, zmiana_ceny,
            skok_wolumenu, current_rsi, sl_na_dole, tp_na_gorze,
            sygnal_trafiony,
            sma20 if sma20 is not None else 0.0,
            sma50 if sma50 is not None else 0.0,
            macd_val if macd_val is not None else 0.0,
            atr_val if atr_val is not None else 0.0,
            momentum_val if momentum_val is not None else 0.0,
            bb_upper_val if bb_upper_val is not None else 0.0,
            bb_mid_val if bb_mid_val is not None else 0.0,
            bb_lower_val if bb_lower_val is not None else 0.0,
            obv_val if obv_val is not None else 0.0,
            adx_val if adx_val is not None else 0.0,
            news, sentiment
        )

        ticker_info = {
            "Ticker": ticker,
            "Cena": f"{aktualna_cena:.2f} {waluta}",
            "Zmiana %": round(zmiana_ceny, 2),
            "Wolumen (x śr.)": f"{skok_wolumenu:.2f}x",
            "RSI": f"{current_rsi:.1f}",
            "SMA20": f"{sma20:.2f}" if sma20 is not None else "—",
            "SMA50": f"{sma50:.2f}" if sma50 is not None else "—",
            "MACD": f"{macd_val:.3f}" if macd_val is not None else "—",
            "ATR": f"{atr_val:.2f}" if atr_val is not None else "—",
            "Momentum": f"{momentum_val:.2f}%" if momentum_val is not None else "—",
            "BB_Upper": f"{bb_upper_val:.2f}" if bb_upper_val is not None else "—",
            "BB_Lower": f"{bb_lower_val:.2f}" if bb_lower_val is not None else "—",
            "ADX": f"{adx_val:.1f}" if adx_val is not None else "—",
            "Sentyment": "😊" if sentiment > 0 else ("😟" if sentiment < 0 else "😐"),
            "SL": f"{sl_na_dole:.2f} {waluta}",
            "TP": f"{tp_na_gorze:.2f} {waluta}",
            "Status": ocena_trendu,
            "Sygnał": sygnal_trafiony,
            "score": sort_score,
            "Analiza AI": analiza_ai,
            "Newsy (pełne)": news if news else "Brak",
            "_df": df,
            "_cena_akt": aktualna_cena,
            "_waluta": waluta
        }

        if sygnal_trafiony:
            flag_rynek = "🇵🇱" if is_gpw else "🇺🇸"
            wiadomosc = (
                f"🚨 <b>ALERT SNAJPERA AKCJI {flag_rynek}: {ticker}</b>\n"
                f"💰 Cena: {aktualna_cena:.2f} {waluta} (+{zmiana_ceny:.2f}%)\n"
                f"📊 Wolumen: <b>{skok_wolumenu:.1f}x</b> ponad średnią\n"
                f"🛡️ RSI: <b>{current_rsi:.1f}</b>\n"
                f"📈 SMA20: {sma20:.2f} | SMA50: {sma50:.2f}\n"
                f"📉 MACD: {macd_val:.3f} | ATR: {atr_val:.2f}\n"
                f"🛑 SL: {sl_na_dole:.2f} {waluta} | 🎯 TP: {tp_na_gorze:.2f} {waluta}\n\n"
                f"🧠 <b>Analiza AI:</b>\n{analiza_ai}"
            )
            if news:
                wiadomosc += f"\n\n📰 <b>Newsy (24h):</b>\n{news[:500]}"
            send_telegram_message(wiadomosc)

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
        return {
            "Ticker": ticker,
            "Status": f"❌ Błąd: {str(e)}",
            "score": 0,
            "Analiza AI": f"Wystąpił błąd: {e}"
        }

# =====================================================================
# BACKTEST STRATEGII
# =====================================================================
def backtest_strategy(ticker, vol_threshold, price_threshold, sl_pct, tp_pct,
                      rsi_min, rsi_max, macd_sign, lookback_days=60):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty or len(df) < 20:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df["RSI"] = oblicz_rsi(df, 14)
        df["SMA20"] = oblicz_sma(df, 20)
        macd, signal = oblicz_macd(df)
        df["MACD"] = macd
        df["ATR"] = oblicz_atr(df, 14)
        df["Momentum"] = oblicz_momentum(df, 5)
        df["Volume_Avg"] = df["Volume"].rolling(20).mean()

        trades = []
        for i in range(20, len(df) - 1):
            row = df.iloc[i]
            if row["Volume_Avg"] == 0:
                continue
            skok_wol = row["Volume"] / row["Volume_Avg"]
            zmiana = ((row["Close"] - df.iloc[i-1]["Close"]) / df.iloc[i-1]["Close"]) * 100
            syg_tech = (zmiana >= price_threshold and skok_wol >= vol_threshold)
            rsi_ok = (rsi_min <= row["RSI"] <= rsi_max) if not pd.isna(row["RSI"]) else False
            macd_ok = True
            if macd_sign == ">0":
                macd_ok = row["MACD"] > 0 if not pd.isna(row["MACD"]) else False
            elif macd_sign == "<0":
                macd_ok = row["MACD"] < 0 if not pd.isna(row["MACD"]) else False

            if syg_tech and rsi_ok and macd_ok:
                entry = row["Close"]
                sl = entry * (1 - sl_pct)
                tp = entry * (1 + tp_pct)
                exit_price = None
                for j in range(i+1, min(i+6, len(df))):
                    high = df.iloc[j]["High"]
                    low = df.iloc[j]["Low"]
                    if high >= tp:
                        exit_price = tp
                        break
                    if low <= sl:
                        exit_price = sl
                        break
                if exit_price is None:
                    exit_price = df.iloc[min(i+5, len(df)-1)]["Close"]
                ret = (exit_price - entry) / entry
                trades.append(ret)

        if not trades:
            return {"win_rate": 0, "avg_return": 0, "total": 0}

        wins = sum(1 for r in trades if r > 0)
        win_rate = wins / len(trades) * 100
        avg_return = np.mean(trades) * 100
        return {"win_rate": win_rate, "avg_return": avg_return, "total": len(trades)}
    except Exception as e:
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

    vol_thr = st.session_state.ui_vol_threshold
    price_thr = st.session_state.ui_price_threshold
    sl_pct = st.session_state.ui_sl
    tp_pct = st.session_state.ui_tp
    deep = st.session_state.use_deep_analysis
    rsi_min = st.session_state.rsi_min
    rsi_max = st.session_state.rsi_max
    macd_sign = st.session_state.macd_sign

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
                deep,
                rsi_min,
                rsi_max,
                macd_sign
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

    # Sortowanie wyników (najpierw sygnały, potem reszta)
    lista_podgladu.sort(key=lambda x: x.get("score", 0), reverse=True)
    st.session_state.last_scanned_tickers = lista_podgladu
    st.session_state.skan_w_toku = False
    st.session_state.last_auto_scan = datetime.now()

# =====================================================================
# SIDEBAR
# =====================================================================
st.sidebar.header("⏱️ Sterowanie Radarem")
st.session_state.auto_scan = st.sidebar.selectbox(
    "Automatyczne odświeżanie:",
    ["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"],
    index=["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"].index(st.session_state.auto_scan)
)

if st.sidebar.button("🔌 Wyślij testowy alert"):
    if send_telegram_message("🤖 <b>TEST SYSTEMU:</b> Powiadomienia działają!"):
        st.sidebar.success("Test dostarczony!")

st.sidebar.info(f"⏱️ Ostatni udany skan: {st.session_state.last_scan_time}")

if st.sidebar.button("🗑️ Wyczyść cache danych"):
    yf.pdr_override()
    st.sidebar.success("Cache wyczyszczony (jeśli był).")

# =====================================================================
# PRZYCISKI GŁÓWNE
# =====================================================================
col_btn1, col_btn2, col_btn3 = st.columns(3)
with col_btn1:
    uruchom_skan = st.button("🚀 Uruchom Skaner")
with col_btn2:
    if st.button("🗑️ Wyczyść Historię"):
        st.session_state.alerts_history = []
        st.rerun()
with col_btn3:
    if st.button("📥 Eksportuj wyniki CSV"):
        if st.session_state.last_scanned_tickers:
            df_exp = pd.DataFrame(st.session_state.last_scanned_tickers)
            for c in ["_df", "_cena_akt", "_waluta", "score", "Sygnał"]:
                if c in df_exp.columns:
                    df_exp = df_exp.drop(columns=[c])
            csv = df_exp.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Pobierz CSV",
                data=csv,
                file_name=f"skaner_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
        else:
            st.warning("Brak wyników do eksportu.")

status_ph = st.empty()
prog_bar = st.empty()

if uruchom_skan:
    status_ph.write("⌛ Trwa pobieranie i analiza danych giełdowych...")
    prog_bar.progress(0)
    job_skanera(status_ph, prog_bar)
    status_ph.success(f"⚙️ Status: Wielowątkowy radar aktywny | Ostatni skan: {st.session_state.last_scan_time}")

# AUTO-SKAN
if st.session_state.auto_scan != "Tylko ręcznie":
    interwal = {"Co 1 minutę": 60, "Co 5 minut": 300, "Co 15 minut": 900}[st.session_state.auto_scan]
    if (datetime.now() - st.session_state.last_auto_scan).total_seconds() >= interwal:
        if not st.session_state.skan_w_toku:
            status_ph.write("⌛ Automatyczny skan...")
            prog_bar.progress(0)
            job_skanera(status_ph, prog_bar)
            status_ph.success(f"⚙️ Automatyczny skan zakończony | {st.session_state.last_scan_time}")
        else:
            status_ph.info("⏳ Skan już trwa, pomijam automatyczne wywołanie.")

# =====================================================================
# WYŚWIETLANIE WYNIKÓW Z KOLOROWANIEM (poprawione .map)
# =====================================================================
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd aktualnego cyklu skanowania (Posortowany)")

    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    # Jeśli brak kolumny "Status", dodaj domyślną
    if "Status" not in df_wyniki.columns:
        df_wyniki["Status"] = "Brak danych"

    if "score" in df_wyniki.columns:
        df_wyniki = df_wyniki.sort_values(by="score", ascending=False)
        df_wyniki = df_wyniki.drop(columns=["score"])

    for col in ["Sygnał", "_df", "_cena_akt", "_waluta"]:
        if col in df_wyniki.columns:
            df_wyniki = df_wyniki.drop(columns=[col])

    if "Analiza AI" in df_wyniki.columns:
        df_wyniki["Analiza AI"] = df_wyniki["Analiza AI"].apply(
            lambda x: x[:150] + "..." if isinstance(x, str) and len(x) > 150 else x
        )

    # Funkcje kolorowania
    def koloruj_zmiane(val):
        try:
            if isinstance(val, (int, float)):
                if val > 0:
                    return 'color: green; font-weight: bold;'
                elif val < 0:
                    return 'color: red; font-weight: bold;'
            return ''
        except:
            return ''

    def koloruj_wolumen(val):
        try:
            if isinstance(val, str) and 'x' in val:
                liczba = float(val.replace('x', '').strip())
                if liczba >= 3:
                    return 'background-color: #d4edda;'
                elif liczba >= 1.5:
                    return 'background-color: #fff3cd;'
                else:
                    return 'background-color: #f8d7da;'
            return ''
        except:
            return ''

    def koloruj_rsi(val):
        try:
            if isinstance(val, (int, float)):
                if 30 <= val <= 70:
                    return 'color: green;'
                elif val < 30:
                    return 'color: orange; font-weight: bold;'
                else:
                    return 'color: red; font-weight: bold;'
            return ''
        except:
            return ''

    def koloruj_status(val):
        if isinstance(val, str):
            if 'Kupuj' in val:
                return 'background-color: #d4edda; color: #155724; font-weight: bold;'
            elif 'Trzymaj' in val:
                return 'background-color: #fff3cd; color: #856404;'
            elif 'Unikaj' in val:
                return 'background-color: #f8d7da; color: #721c24;'
            elif '❌' in val or '⛔' in val:
                return 'background-color: #f5c6cb; color: #721c24;'
        return ''

    # Stylizacja
    styled = df_wyniki.style \
        .map(koloruj_zmiane, subset=['Zmiana %']) \
        .map(koloruj_wolumen, subset=['Wolumen (x śr.)']) \
        .map(koloruj_rsi, subset=['RSI']) \
        .map(koloruj_status, subset=['Status']) \
        .set_properties(**{'text-align': 'center'}) \
        .set_table_styles([{'selector': 'thead th', 'props': [('text-align', 'center')]}])

    st.dataframe(styled, use_container_width=True)

    # MINI-WYKRESY
    st.subheader("📈 Wykresy cenowe i wskaźniki (rozwiń)")
    for item in st.session_state.last_scanned_tickers:
        with st.expander(f"📊 {item['Ticker']} – wykres"):
            df = item.get("_df")
            if df is not None and not df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df.index, y=df["Close"],
                    mode='lines', name='Zamknięcie',
                    line=dict(color='blue')
                ))
                if "SMA20" in df.columns and df["SMA20"].notna().any():
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df["SMA20"],
                        mode='lines', name='SMA20',
                        line=dict(color='orange', dash='dot')
                    ))
                if "SMA50" in df.columns and df["SMA50"].notna().any():
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df["SMA50"],
                        mode='lines', name='SMA50',
                        line=dict(color='red', dash='dot')
                    ))
                if "BB_Upper" in df.columns and df["BB_Upper"].notna().any():
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df["BB_Upper"],
                        mode='lines', name='BB Górne',
                        line=dict(color='gray', dash='dash')
                    ))
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df["BB_Lower"],
                        mode='lines', name='BB Dolne',
                        line=dict(color='gray', dash='dash'),
                        fill='tonexty'
                    ))
                fig.update_layout(
                    title=f"{item['Ticker']} – cena i wskaźniki",
                    xaxis_title="Data",
                    yaxis_title=f"Cena ({item.get('_waluta', 'USD')})",
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("Brak danych do wykresu.")

    # SZCZEGÓŁY
    st.subheader("📰 Szczegółowe analizy (rozwiń dla tickera)")
    for item in st.session_state.last_scanned_tickers:
        with st.expander(f"{item['Ticker']} – szczegóły analizy"):
            st.write("**🧠 Analiza AI (pełna):**")
            st.write(item.get("Analiza AI", "Brak"))
            st.write("**📰 Newsy (pełne):**")
            st.write(item.get("Newsy (pełne)", "Brak"))

# =====================================================================
# HISTORIA ALERTÓW
# =====================================================================
if st.session_state.alerts_history:
    st.subheader("📋 Zapamiętane Okazje Snajperskie (Zielone Alerty 🟢)")
    st.dataframe(pd.DataFrame(st.session_state.alerts_history), use_container_width=True)

# =====================================================================
# BACKTEST – panel boczny
# =====================================================================
st.sidebar.subheader("🧪 Backtest strategii")
if st.sidebar.button("Uruchom backtest dla obecnej listy"):
    with st.spinner("Backtest w toku..."):
        wyniki_back = []
        for ticker in MARKET_DATABASE[:10]:
            res = backtest_strategy(
                ticker,
                st.session_state.ui_vol_threshold,
                st.session_state.ui_price_threshold,
                st.session_state.ui_sl,
                st.session_state.ui_tp,
                st.session_state.rsi_min,
                st.session_state.rsi_max,
                st.session_state.macd_sign,
                lookback_days=60
            )
            if res:
                wyniki_back.append({
                    "Ticker": ticker,
                    "Win rate (%)": round(res["win_rate"], 1),
                    "Średni zwrot (%)": round(res["avg_return"], 2),
                    "Liczba transakcji": res["total"]
                })
        if wyniki_back:
            df_back = pd.DataFrame(wyniki_back)
            st.sidebar.dataframe(df_back, use_container_width=True)
            avg_win = df_back["Win rate (%)"].mean()
            avg_ret = df_back["Średni zwrot (%)"].mean()
            st.sidebar.write(f"📊 Średni win rate: {avg_win:.1f}%")
            st.sidebar.write(f"📈 Średni zwrot: {avg_ret:.2f}%")
        else:
            st.sidebar.warning("Brak wyników backtestu – może za mało danych lub sygnałów.")
