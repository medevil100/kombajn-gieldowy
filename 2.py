import asyncio
import os
import streamlit as st
import pandas as pd
import yfinance as yf
import ta
from openai import OpenAI
from tavily import TavilyClient
import httpx

st.set_page_config(page_title="GPW AI Terminal", layout="wide")

# =====================================================================
# SZTYWNA KONFIGURACJA KLUCZY (BEZ PLIKÓW .env I secrets.toml)
# ====================================================================

# 🔴 TUTAJ WKLEJ SWÓJ KLUCZ OPENAI POMIĘDZY CUDZYSŁOWY:
OPENAI_API_KEY = "TWÓJ_KLUCZ_OPENAI_TUTAJ"

# Blokada startu w przypadku braku klucza OpenAI
if OPENAI_API_KEY == "TWÓJ_KLUCZ_OPENAI_TUTAJ" or not OPENAI_API_KEY:
    st.error("❌ Musisz podmienić 'TWÓJ_KLUCZ_OPENAI_TUTAJ' w linii 18 kodu na swój prawdziwy klucz API OpenAI.")
    st.stop()

# REGUŁA 3: Jawna i bezwzględna inicjalizacja session_state przed użyciem
if "ticker" not in st.session_state:
    st.session_state.ticker = "PKO.WA"
if "report_output" not in st.session_state:
    st.session_state.report_output = ""
if "logs" not in st.session_state:
    st.session_state.logs = []

def log_message(msg: str):
    st.session_state.logs.append(msg)

# =====================================================================
# MODUŁ 1: DATA LAYER (Pozyskiwanie i Normalizacja)
# =====================================================================
class GPWDataProvider:
    @staticmethod
    def get_clean_data(ticker: str, period: str = "6m") -> pd.DataFrame:
        log_message(f"Pobieranie danych z yfinance dla: {ticker}")
        df = yf.download(ticker, period=period, group_by=None, progress=False)

        if df.empty:
            raise ValueError(f"Brak danych lub błędny ticker dla spółki: {ticker}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)

        df.columns = df.columns.str.replace("*", "", regex=False).str.strip().str.capitalize()

        expected_columns = ["Open", "High", "Low", "Close", "Volume"]
        for col in expected_columns:
            if col not in df.columns:
                if col == "Close" and "Adj close" in df.columns:
                    df["Close"] = df["Adj close"]
                else:
                    raise KeyError(f"Krytyczny brak wymaganej kolumny '{col}' w danych źródłowych.")

        df = df[expected_columns].copy()
        for col in expected_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["Close"])
        df["Volume"] = df["Volume"].fillna(0)
        rolling_vol_median = df["Volume"].rolling(window=5, min_periods=1).median()
        df.loc[df["Volume"] == 0, "Volume"] = rolling_vol_median

        return df

# =====================================================================
# MODUŁ 2: TECHNICAL ENGINE (Matematyczna Analityka)
# =====================================================================
class GPWTechnicalEngine:
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> dict:
        if len(df) < 20:
            raise ValueError("Za mała próbka danych do wyliczenia wskaźników.")

        close_series = df["Close"].squeeze()
        high_series = df["High"].squeeze()
        low_series = df["Low"].squeeze()

        rsi = ta.momentum.RSIIndicator(close=close_series, window=14).rsi()
        macd_obj = ta.trend.MACD(close=close_series, window_fast=12, window_slow=26, window_sign=9)
        macd = macd_obj.macd()
        macd_signal = macd_obj.macd_signal()
        atr = ta.volatility.AverageTrueRange(high=high_series, low=low_series, close=close_series, window=14).average_true_range()
        sma_20 = ta.trend.SMAIndicator(close=close_series, window=20).sma_indicator()

        last_close = float(close_series.iloc[-1])
        last_rsi = float(rsi.iloc[-1])
        last_macd = float(macd.iloc[-1])
        last_signal = float(macd_signal.iloc[-1])
        last_atr = float(atr.iloc[-1])

        recent_data = close_series.tail(20)
        support = float(recent_data.min())
        resistance = float(recent_data.max())
        trend = "Wzrostowy" if last_close > float(sma_20.iloc[-1]) else "Spadkowy"

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
        log_message(f"Uruchamianie Tavily Web Research dla: {ticker}")
        client = TavilyClient(api_key=TAVILY_API_KEY)
        query = f"GPW {ticker} wiadomości komunikaty ESPI dywidenda wyniki finansowe"

        try:
            response = client.search(query=query, search_depth="advanced", max_results=4, include_answer=False)
            return [{"title": item.get("title"), "content": item.get("content"), "url": item.get("url")} for item in response.get("results", [])]
        except Exception as e:
            log_message(f"Błąd skanera Tavily: {e}")
            return []

# =====================================================================
# MODUŁ 4: SCORING & AI ENGINE (Rygorystyczny Evaluator)
# =====================================================================
class GPWScoringEngine:
    @staticmethod
    def evaluate_and_score(ticker: str, tech_data: dict, facts: list) -> str:
        log_message("Uruchamianie silnika AI (GPT-4o)")
        client = OpenAI(api_key=OPENAI_API_KEY)

        formatted_facts = ""
        for idx, f in enumerate(facts, 1):
            formatted_facts += f"[{idx}] Tytuł: {f['title']}\nTreść: {f['content']}\nŹródło: {f['url']}\n\n"

        if not formatted_facts:
            formatted_facts = "Brak najnowszych doniesień prasowych i komunikatów ESPI w sieci."

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
• [Wniosek 1]
• [Wniosek 2]

⚠️ RYZYKA:
• [Główne zagrożenie techniczne lub informacyjne dla pozycji]
----------------------------------
Zwróć czysty tekst bez bloków kodu i bez słów wstępnych.
"""
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1,
            max_tokens=800,
        )
        return response.choices.message.content.strip()

# =====================================================================
# MODUŁ 5: EXECUTION & NOTIFICATION LAYER (Niezależny Bot Telegram)
# =====================================================================
class TelegramNotifier:
    @staticmethod
    async def send_alert_async(text: str) -> bool:
        url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}

        async with httpx.AsyncClient() as client:
            for attempt in range(1, 4):
                try:
                    response = await client.post(url, json=payload, timeout=10.0)
                    if response.status_code == 200:
                        return True
                    else:
                        log_message(f"Telegram API błąd (Próba {attempt}): {response.text}")
                except httpx.HTTPError as e:
                    log_message(f"Błąd sieciowy Telegram (Próba {attempt}): {e}")
                await asyncio.sleep(2)
        return False

    @staticmethod
    def send_alert(text: str) -> bool:
        try:
            return asyncio.run(TelegramNotifier.send_alert_async(text))
        except Exception as e:
            log_message(f"Krytyczny błąd pętli: {e}")
            return False

# =====================================================================
# MODUŁ 6: UI LAYER (Streamlit Kokpit) - Z POPRAWIONYMI WCIĘCIAMI
# =====================================================================
st.title("🤖 Profesjonalny Terminal AI dla GPW")
st.caption("Automatyczny potok danych: yfinance -> Ta -> Tavily -> OpenAI GPT-4o -> Telegram")

with st.sidebar:
    st.header("🎛️ Parametry skanowania")
    ticker_input = st.text_input("Wpisz Ticker GPW (z końcówką .WA):", value=st.session_state.ticker, key="ticker_entry")
    if ticker_input:
        st.session_state.ticker = ticker_input.upper().strip()

    run_pipeline = st.button("🚀 Uruchom Pełny Potok Analizy", use_container_width=True)

    st.subheader("🛠️ Monitor Systemowy")
    if st.button("Wyczyść logi"):
        st.session_state.logs = []
        
    for log in st.session_state.logs[-10:]:
        st.caption(log)

# Główny interfejs wyświetlania danych (Bez wcięć bocznych)
col1, col2 = st.columns()

with col1:
    st.subheader("📋 Wynik Oceny AI & Scoringu")

    if run_pipeline:
        try:
            with st.spinner("Przetwarzanie danych, analiza wskaźników i research sieci..."):
                cleaned_df = GPWDataProvider.get_clean_data(st.session_state.ticker)
                log_message("Moduł 1 (Data Layer) - OK.")

                with col2:
                    st.subheader("📊 Znormalizowany Podgląd OHLCV")
                    st.dataframe(cleaned_df.tail(7), use_container_width=True)

                tech_analysis = GPWTechnicalEngine.calculate_indicators(cleaned_df)
                log_message("Moduł 2 (Technical Engine) - OK.")

                with col2:
                    st.subheader("📈 Wyliczone wskaźniki")
                    st.json(tech_analysis)

                market_facts = GPWNewsScanner.fetch_market_facts(st.session_state.ticker)
                log_message("Moduł 3 (News Layer) - OK.")

                final_report = GPWScoringEngine.evaluate_and_score(st.session_state.ticker, tech_analysis, market_facts)
                st.session_state.report_output = final_report
                log_message("Moduł 4 (AI Engine) - OK.")
                
                st.rerun()

        except Exception as error:
            st.error(f"❌ Awaria potoku: {error}")
            log_message(f"BŁĄD KRYTYCZNY: {error}")

    if st.session_state.report_output:
        st.markdown(st.session_state.report_output)
        st.markdown("---")
        if st.button("📲 Wyślij ten raport natychmiast na Telegram", use_container_width=True):
            with st.spinner("Wysyłanie..."):
                success = TelegramNotifier.send_alert(st.session_state.report_output)
                if success:
                    st.success("🎯 Raport dostarczony pomyślnie na Twój Telegram!")
                    log_message("Moduł 5 (Telegram Layer) - Alert wysłany.")
                else:
                    st.error("❌ Nie udało się dostarczyć powiadomienia. Sprawdź monitor w panelu bocznym.")
    else:
        st.info("Wprowadź ticker i kliknij 'Uruchom Pełny Potok Analizy' w panelu bocznym.")
