import streamlit as st
import time
import requests
import yfinance as yf
import pandas as pd
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
# INICJALIZACJA SESSION_STATE – WSZYSTKIE KLUCZE
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

# Ustawienia użytkownika – domyślne
if "ui_interval" not in st.session_state:
    st.session_state.ui_interval = "30m"
if "ui_vol_threshold" not in st.session_state:
    st.session_state.ui_vol_threshold = 1.5
if "ui_price_threshold" not in st.session_state:
    st.session_state.ui_price_threshold = 0.5
if "ui_sl" not in st.session_state:
    st.session_state.ui_sl = 0.05
if "ui_tp" not in st.session_state:
    st.session_state.ui_tp = 0.15
if "use_deep_analysis" not in st.session_state:
    st.session_state.use_deep_analysis = True
if "auto_scan" not in st.session_state:
    st.session_state.auto_scan = "Tylko ręcznie"
if "market_database" not in st.session_state:
    st.session_state.market_database = ["APS.WA", "STX.WA"]
if "filter_gpw" not in st.session_state:
    st.session_state.filter_gpw = True
if "filter_usa" not in st.session_state:
    st.session_state.filter_usa = True
if "rsi_min" not in st.session_state:
    st.session_state.rsi_min = 10
if "rsi_max" not in st.session_state:
    st.session_state.rsi_max = 90
if "macd_sign" not in st.session_state:
    st.session_state.macd_sign = "Dowolny"

# =====================================================================
# ŁADOWANIE KLUCZY Z SECRETS
# =====================================================================
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]

    MAX_PRICE_PLN = float(st.secrets.get("MAX_PRICE_PLN", 50.0))
    MAX_PRICE_USD = float(st.secrets.get("MAX_PRICE_USD", 5.0))
except KeyError as e:
    st.error(f"❌ Brak kluczowych zmiennych autoryzacyjnych w secrets.toml: {e}")
    st.stop()
except Exception as e:
    st.error(f"❌ Błąd kluczy w secrets.toml: {e}")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# =====================================================================
# LISTA OBSERWACYJNA
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
# SUWAKI
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
# DODATKOWE WARUNKI
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
# OPCJA NEWSÓW
# =====================================================================
st.session_state.use_deep_analysis = st.checkbox(
    "🧠 Włącz analizę z użyciem newsów (Tavily)",
    value=st.session_state.use_deep_analysis
)

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

def oblicz_sma(df, period):
    return df["Close"].rolling(window=period).mean()

def oblicz_macd(df):
    try:
        exp12 = df["Close"].ewm(span=12, adjust=False).mean()
        exp26 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal
    except Exception:
        return None, None

def oblicz_atr(df, period=14):
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

def oblicz_momentum(df, period=5):
    try:
        return (df["Close"] / df["Close"].shift(period) - 1) * 100
    except Exception:
        return None

def oblicz_bollinger(df, period=20, std=2):
    try:
        sma = df["Close"].rolling(period).mean()
        std_dev = df["Close"].rolling(period).std()
        upper = sma + std * std_dev
        lower = sma - std * std_dev
        return upper, sma, lower
    except Exception:
        return None, None, None

def oblicz_obv(df):
    try:
        obv = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()
        return obv
    except Exception:
        return None

def oblicz_adx(df, period=14):
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
    except Exception:
        return "", 0

def analizuj_rynkowo_ai(ticker, cena, waluta, zmiana, wolumen_x, rsi, sl, tp,
                        sygnal, sma20, sma50, macd, atr, momentum,
                        bb_upper, bb_mid, bb_lower, obv, adx, news="", sentiment=0):
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
        f"- ATR: {atr:.2f}\n"
        f"- Momentum: {momentum:.2f}%\n"
        f"- BB Górne: {bb_upper:.2f}, BB Dolne: {bb_lower:.2f}\n"
        f"- OBV: {obv:.0f}\n"
        f"- ADX: {adx:.1f}\n"
        f"- SL: {sl:.2f}, TP: {tp:.2f}\n"
        f"- Sygnał kupna: {sygnal_str}\n"
    )
    if news:
        prompt += f"\nNewsy (24h):\n{news[:500]}\nSentyment: {sent_str}\n"
    prompt += "\nNapisz krótkie (do 100 słów) podsumowanie: czy to dobra okazja do zakupu (long), jaki jest potencjalny zasięg wzrostu, czy istnieje ryzyko, oraz ogólna rekomendacja."
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
# ANALIZA POJEDYNCZEJ SPÓŁKI
# =====================================================================
def analizuj_jedna_spolke(ticker, now, vol_threshold, price_threshold,
                          sl_pct, tp_pct, deep_analysis,
                          rsi_min, rsi_max, macd_sign):
    try:
        interval = st.session_state.ui_interval
        if interval in ["1m", "5m", "15m", "30m"]:
            period = "5d"
        elif interval == "1h":
            period = "1mo"
        else:
            period = "3mo"

        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return {"Ticker": ticker, "Status": "❌ Brak danych", "score": 0,
                    "Analiza AI": "Brak danych z Yahoo Finance."}
        if len(df) < 20:
            return {"Ticker": ticker, "Status": "❌ Za mało świec", "score": 0,
                    "Analiza AI": f"Potrzebuję co najmniej 20 świec, mam tylko {len(df)}."}

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Wskaźniki
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
            return {"Ticker": ticker, "Status": "❌ RSI nieobliczalny", "score": 0,
                    "Analiza AI": "Nie udało się obliczyć RSI."}

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
        bb_lower_val = pobierz_wartosc(ostatnia["BB_Lower"])
        obv_val = pobierz_wartosc(ostatnia["OBV"])
        adx_val = pobierz_wartosc(ostatnia["ADX"])

        if any(v is None for v in [aktualna_cena, cena_poprzednia, aktualny_wolumen, sredni_wolumen, current_rsi]):
            return {"Ticker": ticker, "Status": "❌ Brak kluczowych danych", "score": 0,
                    "Analiza AI": "Niektóre dane są puste."}
        if aktualna_cena <= 0 or cena_poprzednia <= 0 or sredni_wolumen <= 0:
            return {"Ticker": ticker, "Status": "❌ Nieprawidłowe wartości", "score": 0,
                    "Analiza AI": "Cena lub wolumen są zerowe."}

        is_gpw = ticker.endswith(".WA")
        waluta = "PLN" if is_gpw else "USD"

        if is_gpw and aktualna_cena > MAX_PRICE_PLN:
            return {"Ticker": ticker, "Status": f"⛔ Cena > {MAX_PRICE_PLN} PLN", "score": 0,
                    "Analiza AI": f"Cena {aktualna_cena:.2f} przekracza limit."}
        if not is_gpw and aktualna_cena > MAX_PRICE_USD:
            return {"Ticker": ticker, "Status": f"⛔ Cena > {MAX_PRICE_USD} USD", "score": 0,
                    "Analiza AI": f"Cena {aktualna_cena:.2f} przekracza limit."}

        zmiana_ceny = ((aktualna_cena - cena_poprzednia) / cena_poprzednia) * 100.0
        skok_wolumenu = aktualny_wolumen / sredni_wolumen

        sygnal_techniczny = (zmiana_ceny >= price_threshold and skok_wolumenu >= vol_threshold)
        rsi_warunek = (rsi_min <= current_rsi <= rsi_max)
        macd_warunek = True
        if macd_sign == ">0":
            macd_warunek = macd_val > 0
        elif macd_sign == "<0":
            macd_warunek = macd_val < 0

        sygnal_trafiony = sygnal_techniczny and rsi_warunek and macd_warunek

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
            "_df": df,                     # <-- KLUCZ DLA WYKRESÓW
            "_waluta": waluta
        }

        if sygnal_trafiony:
            flag_rynek = "🇵🇱" if is_gpw else "🇺🇸"
            wiadomosc = (
                f"🚨 <b>ALERT: {ticker} {flag_rynek}</b>\n"
                f"💰 Cena: {aktualna_cena:.2f} {waluta} (+{zmiana_ceny:.2f}%)\n"
                f"📊 Wolumen: {skok_wolumenu:.1f}x\n"
                f"🛡️ RSI: {current_rsi:.1f}\n"
                f"🛑 SL: {sl_na_dole:.2f} | 🎯 TP: {tp_na_gorze:.2f}\n"
                f"🧠 {analiza_ai}"
            )
            if news:
                wiadomosc += f"\n📰 {news[:200]}"
            send_telegram_message(wiadomosc)

            st.session_state.alerts_history.append({
                "Czas": now,
                "Ticker": ticker,
                "Cena": f"{aktualna_cena:.2f} {waluta}",
                "Zmiana": f"+{zmiana_ceny:.2f}%",
                "Wolumen": f"{skok_wolumenu:.1f}x",
                "RSI": f"{current_rsi:.1f}",
                "Analiza AI": analiza_ai[:150] + "..."
            })

        return ticker_info
    except Exception as e:
        return {"Ticker": ticker, "Status": f"❌ Błąd: {str(e)}", "score": 0,
                "Analiza AI": f"Wystąpił błąd: {e}"}

# =====================================================================
# GŁÓWNY JOB SKANERA
# =====================================================================
def job_skanera(status_placeholder=None, progress_bar=None):
    if st.session_state.skan_w_toku:
        if status_placeholder:
            status_placeholder.warning("⏳ Skan już trwa.")
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

    total = len(MARKET_DATABASE)
    lista = []
    processed = 0

    if total == 0:
        if status_placeholder:
            status_placeholder.error("❌ Lista jest pusta.")
        st.session_state.skan_w_toku = False
        return

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                analizuj_jedna_spolke,
                ticker, now, vol_thr, price_thr, sl_pct, tp_pct,
                deep, rsi_min, rsi_max, macd_sign
            ): ticker
            for ticker in MARKET_DATABASE
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    lista.append(res)
            except Exception as e:
                st.sidebar.warning(f"Błąd wątku: {e}")
            processed += 1
            if progress_bar:
                progress_bar.progress(processed / total)

    lista.sort(key=lambda x: x.get("score", 0), reverse=True)
    st.session_state.last_scanned_tickers = lista
    st.session_state.skan_w_toku = False
    st.session_state.last_auto_scan = datetime.now()

# =====================================================================
# BACKTEST
# =====================================================================
def backtest_strategy(ticker, vol_threshold, price_threshold, sl_pct, tp_pct,
                      rsi_min, rsi_max, macd_sign):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty or len(df) < 20:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df["RSI"] = oblicz_rsi(df, 14)
        df["MACD"], _ = oblicz_macd(df)
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
                trades.append((exit_price - entry) / entry)

        if not trades:
            return {"win_rate": 0, "avg_return": 0, "total": 0}
        wins = sum(1 for r in trades if r > 0)
        return {"win_rate": wins/len(trades)*100, "avg_return": np.mean(trades)*100, "total": len(trades)}
    except Exception:
        return None

# =====================================================================
# INTERFEJS UŻYTKOWNIKA – SIDEBAR, PRZYCISKI, AUTO-SKAN
# =====================================================================
st.sidebar.header("⏱️ Sterowanie Radarem")
st.session_state.auto_scan = st.sidebar.selectbox(
    "Automatyczne odświeżanie:",
    ["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"],
    index=["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"].index(st.session_state.auto_scan)
)

if st.sidebar.button("🔌 Wyślij testowy alert"):
    if send_telegram_message("🤖 <b>TEST:</b> Powiadomienia działają!"):
        st.sidebar.success("Test dostarczony!")

st.sidebar.info(f"⏱️ Ostatni udany skan: {st.session_state.last_scan_time}")

col_btn1, col_btn2, col_btn3 = st.columns(3)
with col_btn1:
    uruchom_skan = st.button("🚀 Uruchom Skaner")
with col_btn2:
    if st.button("🗑️ Wyczyść Historię"):
        st.session_state.alerts_history = []
        st.rerun()
with col_btn3:
    if st.button("📥 Eksportuj CSV") and st.session_state.last_scanned_tickers:
        df_exp = pd.DataFrame(st.session_state.last_scanned_tickers)
        for c in ["_df", "_waluta", "score", "Sygnał"]:
            if c in df_exp.columns:
                df_exp = df_exp.drop(columns=[c])
        csv = df_exp.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Pobierz CSV", data=csv,
                           file_name=f"skaner_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                           mime="text/csv")

status_ph = st.empty()
prog_bar = st.empty()

if uruchom_skan:
    status_ph.write("⌛ Trwa skanowanie...")
    prog_bar.progress(0)
    job_skanera(status_ph, prog_bar)
    status_ph.success(f"⚙️ Status: Ostatni skan: {st.session_state.last_scan_time}")

# AUTO-SKAN
if st.session_state.auto_scan != "Tylko ręcznie":
    interwal = {"Co 1 minutę": 60, "Co 5 minut": 300, "Co 15 minut": 900}[st.session_state.auto_scan]
    if (datetime.now() - st.session_state.last_auto_scan).total_seconds() >= interwal:
        if not st.session_state.skan_w_toku:
            status_ph.write("⌛ Automatyczny skan...")
            prog_bar.progress(0)
            job_skanera(status_ph, prog_bar)
            status_ph.success(f"⚙️ Auto-skan zakończony | {st.session_state.last_scan_time}")
        else:
            status_ph.info("⏳ Skan już trwa.")

# =====================================================================
# WYŚWIETLANIE WYNIKÓW
# =====================================================================
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd wyników (posortowany)")

    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    # Bezpieczne usuwanie kolumn
    for col in ["_df", "_waluta", "score", "Sygnał"]:
        if col in df_wyniki.columns:
            df_wyniki = df_wyniki.drop(columns=[col])

    if "Analiza AI" in df_wyniki.columns:
        df_wyniki["Analiza AI"] = df_wyniki["Analiza AI"].apply(
            lambda x: x[:150] + "..." if isinstance(x, str) and len(x) > 150 else x
        )

    # Funkcje kolorowania
    def koloruj_zmiane(val):
        if isinstance(val, (int, float)):
            return 'color: green; font-weight: bold;' if val > 0 else ('color: red; font-weight: bold;' if val < 0 else '')
        return ''

    def koloruj_wolumen(val):
        if isinstance(val, str) and 'x' in val:
            liczba = float(val.replace('x', '').strip())
            if liczba >= 3:
                return 'background-color: #d4edda;'
            elif liczba >= 1.5:
                return 'background-color: #fff3cd;'
            else:
                return 'background-color: #f8d7da;'
        return ''

    def koloruj_rsi(val):
        if isinstance(val, (int, float)):
            if 30 <= val <= 70:
                return 'color: green;'
            elif val < 30:
                return 'color: orange; font-weight: bold;'
            else:
                return 'color: red; font-weight: bold;'
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

    # Stylizacja – tylko dla istniejących kolumn
    styled = df_wyniki.style
    if "Zmiana %" in df_wyniki.columns:
        styled = styled.map(koloruj_zmiane, subset=['Zmiana %'])
    if "Wolumen (x śr.)" in df_wyniki.columns:
        styled = styled.map(koloruj_wolumen, subset=['Wolumen (x śr.)'])
    if "RSI" in df_wyniki.columns:
        styled = styled.map(koloruj_rsi, subset=['RSI'])
    if "Status" in df_wyniki.columns:
        styled = styled.map(koloruj_status, subset=['Status'])

    styled = styled.set_properties(**{'text-align': 'center'}).set_table_styles(
        [{'selector': 'thead th', 'props': [('text-align', 'center')]}]
    )
    st.dataframe(styled, use_container_width=True)

    # =================================================================
    # WYKRESY
    # =================================================================
    st.subheader("📈 Wykresy cenowe (rozwiń)")
    for item in st.session_state.last_scanned_tickers:
        with st.expander(f"📊 {item['Ticker']} – wykres"):
            df = item.get("_df")
            if df is not None and not df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode='lines', name='Zamknięcie', line=dict(color='blue')))
                if "SMA20" in df.columns and df["SMA20"].notna().any():
                    fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], mode='lines', name='SMA20', line=dict(color='orange', dash='dot')))
                if "SMA50" in df.columns and df["SMA50"].notna().any():
                    fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], mode='lines', name='SMA50', line=dict(color='red', dash='dot')))
                if "BB_Upper" in df.columns and df["BB_Upper"].notna().any():
                    fig.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], mode='lines', name='BB Górne', line=dict(color='gray', dash='dash')))
                    fig.add_trace(go.Scatter(x=df.index, y=df["BB_Lower"], mode='lines', name='BB Dolne', line=dict(color='gray', dash='dash'), fill='tonexty'))
                fig.update_layout(title=f"{item['Ticker']} – cena i wskaźniki", xaxis_title="Data", yaxis_title=f"Cena ({item.get('_waluta', 'USD')})", height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("Brak danych do wykresu.")

    # =================================================================
    # SZCZEGÓŁY
    # =================================================================
    st.subheader("📰 Szczegółowe analizy")
    for item in st.session_state.last_scanned_tickers:
        with st.expander(f"{item['Ticker']} – szczegóły"):
            st.write("**🧠 Analiza AI:**")
            st.write(item.get("Analiza AI", "Brak"))
            st.write("**📰 Newsy:**")
            st.write(item.get("Newsy (pełne)", "Brak"))

# =====================================================================
# HISTORIA ALERTÓW
# =====================================================================
if st.session_state.alerts_history:
    st.subheader("📋 Historia alertów")
    st.dataframe(pd.DataFrame(st.session_state.alerts_history), use_container_width=True)

# =====================================================================
# BACKTEST – panel boczny
# =====================================================================
st.sidebar.subheader("🧪 Backtest strategii")
if st.sidebar.button("Uruchom backtest"):
    with st.spinner("Backtest..."):
        wyniki = []
        for ticker in MARKET_DATABASE[:10]:
            res = backtest_strategy(
                ticker,
                st.session_state.ui_vol_threshold,
                st.session_state.ui_price_threshold,
                st.session_state.ui_sl,
                st.session_state.ui_tp,
                st.session_state.rsi_min,
                st.session_state.rsi_max,
                st.session_state.macd_sign
            )
            if res:
                wyniki.append({
                    "Ticker": ticker,
                    "Win rate (%)": round(res["win_rate"], 1),
                    "Średni zwrot (%)": round(res["avg_return"], 2),
                    "Liczba transakcji": res["total"]
                })
        if wyniki:
            df_back = pd.DataFrame(wyniki)
            st.sidebar.dataframe(df_back, use_container_width=True)
            st.sidebar.write(f"📊 Śr. win rate: {df_back['Win rate (%)'].mean():.1f}%")
            st.sidebar.write(f"📈 Śr. zwrot: {df_back['Średni zwrot (%)'].mean():.2f}%")
        else:
            st.sidebar.warning("Brak wyników backtestu.")
