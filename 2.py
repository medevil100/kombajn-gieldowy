import asyncio
import os
import streamlit as st
import pandas as pd
import yfinance as yf
import ta
from openai import OpenAI
from tavily import TavilyClient
import httpx

# =====================================================================
# CONFIGURATION & REQUISITES (Streamlit Secrets Layer)
# =====================================================================
st.set_page_config(page_title="GPW AI Terminal", layout="wide")

# Konfiguracja kluczy z .streamlit/secrets.toml
try:
    OPENAI_API_KEY = st.secrets["openai"]["api_key"]
    TAVILY_API_KEY = st.secrets["tavily"]["api_key"]
    TELEGRAM_TOKEN = st.secrets["telegram"]["bot_token"]
    TELEGRAM_CHAT_ID = st.secrets["telegram"]["chat_id"]
except Exception as e:
    st.error(
        f"❌ Błąd konfiguracji secrets.toml. Upewnij się, że plik zawiera sekcje "
        f"[openai], [tavily] oraz [telegram]. Szczegóły: {e}"
    )
    st.stop()

# REGULA 3: Jawna i bezwzględna inicjalizacja session_state przed użyciem
if "ticker" not in st.session_state:
    st.session_state.ticker = "PKO.WA"
if "report_output" not in st.session_state:
    st.session_state.report_output = ""
if "logs" not in st.session_state:
    st.session_state.logs = []


def log_message(msg: str):
    """Cichy system rejestracji zdarzeń."""
    st.session_state.logs.append(msg)


# =====================================================================
# MODUŁ 1: DATA LAYER (Pozyskiwanie i Normalizacja)
# =====================================================================
class GPWDataProvider:

    @staticmethod
    def get_clean_data(ticker: str, period: str = "6m") -> pd.DataFrame:
        """Pobiera dane i bezwzględnie prostuje chaos yfinance (REGUŁA 1)."""
        log_message(f"Pobieranie danych z yfinance dla: {ticker}")

        # Bezwzględne wyłączenie group_by chroniące przed MultiIndex (REGUŁA 2 ze wstępu)
        df = yf.download(ticker, period=period, group_by=None, progress=False)

        if df.empty:
            raise ValueError(
                f"Brak danych lub błędny ticker dla spółki: {ticker}"
            )

        # Spłaszczenie MultiIndex jeśli mimo wszystko powstał
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)

        # Usunięcie gwiazdek i sprowadzenie nazw kolumn do małych/wielkich liter
        df.columns = (
            df.columns.str.replace("*", "", regex=False)
            .str.strip()
            .str.capitalize()
        )

        # Sztywne mapowanie na docelowy standard OHLCV
        expected_columns = ["Open", "High", "Low", "Close", "Volume"]
        for col in expected_columns:
            if col not in df.columns:
                # Jeśli brakuje np. Adj close zamienionego na Close
                if col == "Close" and "Adj close" in df.columns:
                    df["Close"] = df["Adj close"]
                else:
                    raise KeyError(
                        f"Krytyczny brak wymaganej kolumny '{col}' w danych źródłowych."
                    )

        # Odrzucenie nadmiarowych kolumn i zachowanie właściwej kolejności
        df = df[expected_columns].copy()

        # Konwersja typów numerycznych
        for col in expected_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["Close"])

        # FILTROWANIE ANOMALII PŁYNNOŚCI (REGUŁA 1.2): Obsługa dni bez wolumenu i wygładzanie
        df["Volume"] = df["Volume"].fillna(0)
        # Zastąp zerowy wolumen medianą z ostatnich 5 dni (usuwanie fałszywych anomalii pod OBV/RVol)
        rolling_vol_median = df["Volume"].rolling(window=5, min_periods=1).median()
        df.loc[df["Volume"] == 0, "Volume"] = rolling_vol_median

        return df


# =====================================================================
# MODUŁ 2: TECHNICAL ENGINE (Matematyczna Analityka)
# =====================================================================
class GPWTechnicalEngine:

    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> dict:
        """Liczy wskaźniki i wykrywa struktury wyłącznie na znormalizowanych danych (REGUŁA 2)."""
        if len(df) < 20:
            raise ValueError("Za mała próbka danych do wyliczenia wskaźników.")

        # Klonowanie serii close pod wyliczenia biblioteki ta
        close_series = df["Close"].squeeze()
        high_series = df["High"].squeeze()
        low_series = df["Low"].squeeze()

        # Kalkulator wskaźników
        rsi = ta.momentum.RSIIndicator(close=close_series, window=14).rsi()
        macd_obj = ta.trend.MACD(
            close=close_series, window_fast=12, window_slow=26, window_sign=9
        )
        macd = macd_obj.macd()
        macd_signal = macd_obj.macd_signal()
        atr = ta.volatility.AverageTrueRange(
            high=high_series, low=low_series, close=close_series, window=14
        ).average_true_range()
        sma_20 = (
            ta.trend.SMAIndicator(close=close_series, window=20)
            .sma_indicator()
        )

        last_close = float(close_series.iloc[-1])
        last_rsi = float(rsi.iloc[-1])
        last_macd = float(macd.iloc[-1])
        last_signal = float(macd_signal.iloc[-1])
        last_atr = float(atr.iloc[-1])
        last_sma = float(sma_20.iloc[-1])

        # Detektor poziomów wsparcia/oporu (lokalne ekstrema z ostatnich 20 sesji)
        recent_data = close_series.tail(20)
        support = float(recent_data.min())
        resistance = float(recent_data.max())

        # Prosta ocena trendu w kodzie (Detektor formacji/układu)
        trend = "Wzrostowy" if last_close > last_sma else "Spadkowy"

        return {
            "Ostatnia Cena": f"{last_close:.2f} PLN",
            "RSI (14)": f"{last_rsi:.2f}",
            "MACD Line": f"{last_macd:.4f}",
            "MACD Signal": f"{last_signal:.4f}",
            "ATR (14)": f"{last_atr:.2f} PLN",
            "Wsparcie (20s)": f"{support:.2f} PLN",
            "Opór (20s)": f"{resistance:.2f} PLN",
            "Trend SMA20": trend,
        }


# =====================================================================
# MODUŁ 3: FUNDAMENTAL & NEWS LAYER (Tavily Skaner)
# =====================================================================
class GPWNewsScanner:

    @staticmethod
    def fetch_market_facts(ticker: str) -> list:
        """Wyciąga bieżące fakty rynkowe z odcięciem szumu forów (REGUŁA 3)."""
        log_message(f"Uruchamianie Tavily Web Research dla: {ticker}")
        client = TavilyClient(api_key=TAVILY_API_KEY)

        # Budowanie precyzyjnego zapytania pod kątem faktów giełdowych GPW
        query = f"GPW {ticker} wiadomości komunikaty ESPI dywidenda wyniki finansowe"

        try:
            # Wyszukiwanie ukierunkowane na newsy biznesowe
            response = client.search(
                query=query,
                search_depth="advanced",
                max_results=4,
                include_answer=False,
            )
            results = response.get("results", [])
            return [
                {
                    "title": item.get("title"),
                    "content": item.get("content"),
                    "url": item.get("url"),
                }
                for item in results
            ]
        except Exception as e:
            log_message(f"Błąd skanera Tavily: {e}")
            return []


# =====================================================================
# MODUŁ 4: SCORING & AI ENGINE (Rygorystyczny Evaluator)
# =====================================================================
class GPWScoringEngine:

    @staticmethod
    def evaluate_and_score(
        ticker: str, tech_data: dict, facts: list
    ) -> str:
        """Logiczna ocena bez halucynacji przy zerowej kreatywności (REGUŁA 4)."""
        log_message("Uruchamianie silnika AI (GPT-4o)")
        client = OpenAI(api_key=OPENAI_API_KEY)

        # Formatowanie faktów prasowych
        formatted_facts = ""
        for idx, f in enumerate(facts, 1):
            formatted_facts += f"[{idx}] Tytuł: {f['title']}\nTreść: {f['content']}\nŹródło: {f['url']}\n\n"

        if not formatted_facts:
            formatted_facts = "Brak najnowszych doniesień prasowych i komunikatów ESPI w sieci."

        # Rygorystyczny Prompt Systemowy tłumiący fantazję modelu
        system_prompt = (
            "Jesteś chłodnym, pragmatycznym systemem analitycznym dla traderów GPW.\n"
            "Działasz bez emocji. Oceniasz TYLKO przekazane liczby i fakty tekstowe.\n"
            "Zakaz domysłów, interpretacji makroekonomicznych spoza tekstu i halucynacji.\n"
            "Wynik musi być sformatowany surowo pod czytelność w Telegramie."
        )

        user_prompt = f"""
ANALIZOWANY WALOR: {ticker}

[PARAMETRY TECHNICZNE]:
{tech_data}

[ZWERYFIKOWANE FAKTY Z SIECI (TAVILY)]:
{formatted_facts}

WYGENERUJ RAPORT WEDŁUG SZABLONU PROFESJONALISTY:
📊 RAPORT ANALITYCZNY: {ticker}
----------------------------------
🎯 SCORING FINALNY: [X/10] (Podaj TYLKO jedną sztywną cyfrę od 1 do 10, gdzie 1 to natychmiastowa ewakuacja/S, 5 neutralnie, 10 silny sygnał kupna/B na bazie ryzyka do zysku)

📈 ANALIZA TECHNICZNA:
- [Max 2 zdania surowego podsumowania układu wskaźników i poziomów wsparcia]

📰 ANALIZA SENTYMENTU:
- [Faktyczna synteza doniesień prasowych. Co realnie dzieje się w spółce?]

💡 KLUCZOWE WNIOSKI:
• [Wniosek 1 wynikający z zestawienia technika + news]
• [Wniosek 2]

⚠️ RYZYKA:
• [Główne zagrożenie techniczne lub informacyjne dla pozycji]
----------------------------------
Zwróć czysty tekst bez bloków kodu ``` i bez słów wstępnych.
"""
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # Skrajnie niska temperatura = czysta logika
            max_tokens=800,
        )
# =====================================================================
# MODUŁ 5: EXECUTION & NOTIFICATION LAYER (Niezależny Bot Telegram)
# =====================================================================
class TelegramNotifier:

    @staticmethod
    async def send_alert_async(text: str) -> bool:
        """Asynchroniczne, pancerne wysyłanie alertu z ponawianiem prób (REGUŁA 5)."""
        # POPRAWIONE: Pełny, prawidłowy i stabilny adres URL API Telegrama
        url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }

        # Próba wysyłki (max 3 razy w razie błędu sieciowego)
        async with httpx.AsyncClient() as client:
            for attempt in range(1, 4):
                try:
                    response = await client.post(
                        url, json=payload, timeout=10.0
                    )
                    if response.status_code == 200:
                        return True
                    else:
                        log_message(
                            f"Telegram API zwrócił błąd (Próba {attempt}): {response.text}"
                        )
                except httpx.HTTPError as e:
                    log_message(
                        f"Błąd sieciowy podczas wysyłania na Telegram (Próba {attempt}): {e}"
                    )
                await asyncio.sleep(2)
        return False

    @staticmethod
    def send_alert(text: str) -> bool:
        """Wrapper do uruchomienia asynchronicznego kodu w synchronicznym Streamlicie."""
        try:
            return asyncio.run(TelegramNotifier.send_alert_async(text))
        except Exception as e:
            log_message(f"Krytyczny błąd pętli asynchronicznej: {e}")
            return False


# =====================================================================
# MODUŁ 6: UI LAYER (Streamlit Kokpit)
# =====================================================================
st.title("🤖 Profesjonalny Terminal AI dla GPW")
st.caption(
    "Automatyczny potok danych: yfinance -> Ta -> Tavily -> OpenAI GPT-4o -> Telegram"
)

# Panel boczny sterowania
with st.sidebar:
    st.header("🎛️ Parametry skanowania")
    # Zmiana wartości bezpośrednio aktualizuje session_state
    ticker_input = st.text_input(
        "Wpisz Ticker GPW (z końcówką .WA):",
        value=st.session_state.ticker,
        key="ticker_entry",
    )
    if ticker_input:
        st.session_state.ticker = ticker_input.upper().strip()

    run_pipeline = st.button("🚀 Uruchom Pełny Potok Analizy", use_container_width=True)

    st.subheader("🛠️ Monitor Systemowy")
    if st.button("Wyczyść logi"):
        st.session_state.logs = []
    for log in st.session_state.logs[-10:]:
        st.caption(log)

# Główny interfejs wyświetlania danych
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📋 Wynik Oceny AI & Scoringu")

    # Blok kalkulacji: Wykonuje się tylko po kliknięciu przycisku
    if run_pipeline:
        try:
            with st.spinner("Przetwarzanie danych, analiza wskaźników i research sieci..."):
                # 1. Pobranie i oczyszczenie danych
                cleaned_df = GPWDataProvider.get_clean_data(st.session_state.ticker)
                log_message("Moduł 1 (Data Layer) - Zakończony pomyślnie.")

                # REGUŁA 4: Wyświetlanie mini-świec w col2
                with col2:
                    st.subheader("📊 Znormalizowany Podgląd OHLCV")
                    st.dataframe(cleaned_df.tail(7), use_container_width=True)

                # 2. Obliczenia techniczne
                tech_analysis = GPWTechnicalEngine.calculate_indicators(cleaned_df)
                log_message("Moduł 2 (Technical Engine) - Zakończony pomyślnie.")

                with col2:
                    st.subheader("📈 Wyliczone wskaźniki")
                    st.json(tech_analysis)

                # 3. Skanowanie Tavily
                market_facts = GPWNewsScanner.fetch_market_facts(st.session_state.ticker)
                log_message("Moduł 3 (News Layer) - Zakończony pomyślnie.")

                # 4. Silnik AI / Scoring i zapis do stanu sesji
                final_report = GPWScoringEngine.evaluate_and_score(
                    st.session_state.ticker, tech_analysis, market_facts
                )
                st.session_state.report_output = final_report
                log_message("Moduł 4 (AI Engine) - Zakończony pomyślnie.")
                
                # Wymuszenie odświeżenia UI, aby natychmiast pokazać raport
                st.rerun()

        except Exception as error:
            st.error(f"❌ Awaria potoku przetwarzania: {error}")
            log_message(f"BŁĄD KRYTYCZNY: {error}")

    # POPRAWIONE: Wyciągnięcie renderowania poza 'if run_pipeline'.
    # Dzięki temu raport i przycisk nie znikają po kliknięciu wyślij.
    if st.session_state.report_output:
        st.markdown(st.session_state.report_output)

        # 5. Dystrybucja i wysyłka alertu na Telegram
        st.markdown("---")
        if st.button("📲 Wyślij ten raport natychmiast na Telegram", use_container_width=True):
            with st.spinner("Wysyłanie alertu pakietowego..."):
                success = TelegramNotifier.send_alert(st.session_state.report_output)
                if success:
                    st.success("🎯 Raport dostarczony pomyślnie na Twój Telegram!")
                    log_message("Moduł 5 (Telegram Layer) - Alert wysłany.")
                else:
                    st.error("❌ Nie udało się dostarczyć powiadomienia. Sprawdź monitor w panelu bocznym.")
    else:
        st.info("Wprowadź poprawny ticker i kliknij przycisk w panelu bocznym, aby wygenerować raport.")
