import json
import traceback
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import requests

# ---------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------

st.set_page_config(
    page_title="Kombajn Giełdowy",
    page_icon="📈",
    layout="wide"
)

# ---------------------------------------------------------
# TŁUMACZENIA POLSKIE DLA JSON
# ---------------------------------------------------------

PL_LABELS = {
    # profil
    "symbol": "Symbol",
    "longName": "Pełna nazwa",
    "shortName": "Krótka nazwa",
    "sector": "Sektor",
    "industry": "Branża",
    "country": "Kraj",
    "website": "Strona internetowa",
    "longBusinessSummary": "Opis działalności",
    "currency": "Waluta",
    "exchange": "Giełda",
    "quoteType": "Typ instrumentu",

    # metryki
    "currentPrice": "Aktualna cena",
    "regularMarketPrice": "Cena rynkowa",
    "marketCap": "Kapitalizacja rynkowa",
    "enterpriseValue": "Wartość przedsiębiorstwa",
    "trailingPE": "P/E historyczne",
    "forwardPE": "P/E prognozowane",
    "priceToBook": "Cena / wartość księgowa",
    "priceToSalesTrailing12Months": "Cena / sprzedaż TTM",
    "profitMargins": "Marża netto",
    "operatingMargins": "Marża operacyjna",
    "grossMargins": "Marża brutto",
    "returnOnAssets": "ROA - zwrot z aktywów",
    "returnOnEquity": "ROE - zwrot z kapitału własnego",
    "revenueGrowth": "Wzrost przychodów",
    "earningsGrowth": "Wzrost zysków",
    "totalRevenue": "Przychody całkowite",
    "totalDebt": "Dług całkowity",
    "totalCash": "Gotówka całkowita",
    "freeCashflow": "Wolne przepływy pieniężne",
    "operatingCashflow": "Operacyjne przepływy pieniężne",
    "dividendYield": "Stopa dywidendy",
    "dividendYieldPercent": "Stopa dywidendy w %",
    "beta": "Beta",
    "fiftyTwoWeekHigh": "Maksimum z 52 tygodni",
    "fiftyTwoWeekLow": "Minimum z 52 tygodni",

    # price target
    "targetHighPrice": "Najwyższa cena docelowa",
    "targetLowPrice": "Najniższa cena docelowa",
    "targetMeanPrice": "Średnia cena docelowa",
    "targetMedianPrice": "Mediana ceny docelowej",
    "recommendationMean": "Średnia rekomendacja",
    "recommendationKey": "Rekomendacja",
    "numberOfAnalystOpinions": "Liczba opinii analityków",

    # newsy
    "title": "Tytuł",
    "publisher": "Wydawca",
    "link": "Link",
    "providerPublishTime": "Czas publikacji",
    "type": "Typ",
    "content": "Treść",

    # techniczne / systemowe
    "_errors": "Błędy",
    "profile": "Profil",
    "metrics": "Wskaźniki",
    "price_target": "Cele cenowe",
    "income": "Rachunek zysków i strat",
    "balance": "Bilans",
    "cash": "Przepływy pieniężne",
}

FINANCIAL_LABELS = {
    # Income statement
    "Total Revenue": "Przychody całkowite",
    "Operating Revenue": "Przychody operacyjne",
    "Cost Of Revenue": "Koszt przychodów",
    "Gross Profit": "Zysk brutto",
    "Operating Expense": "Koszty operacyjne",
    "Operating Income": "Zysk operacyjny",
    "Net Income": "Zysk netto",
    "Net Income Common Stockholders": "Zysk netto dla akcjonariuszy zwykłych",
    "Diluted NI Availto Com Stockholders": "Rozwodniony zysk netto dla akcjonariuszy",
    "Basic EPS": "Podstawowy EPS",
    "Diluted EPS": "Rozwodniony EPS",
    "Basic Average Shares": "Średnia liczba akcji podstawowa",
    "Diluted Average Shares": "Średnia liczba akcji rozwodniona",
    "EBIT": "EBIT",
    "EBITDA": "EBITDA",
    "Interest Expense": "Koszty odsetkowe",
    "Interest Income": "Przychody odsetkowe",
    "Pretax Income": "Zysk przed opodatkowaniem",
    "Tax Provision": "Podatek dochodowy",
    "Research And Development": "Badania i rozwój",
    "Selling General And Administration": "Koszty sprzedaży i administracji",

    # Balance sheet
    "Total Assets": "Aktywa całkowite",
    "Current Assets": "Aktywa obrotowe",
    "Cash Cash Equivalents And Short Term Investments": "Gotówka i inwestycje krótkoterminowe",
    "Cash And Cash Equivalents": "Gotówka i ekwiwalenty",
    "Receivables": "Należności",
    "Inventory": "Zapasy",
    "Total Liabilities Net Minority Interest": "Zobowiązania całkowite",
    "Current Liabilities": "Zobowiązania krótkoterminowe",
    "Total Debt": "Dług całkowity",
    "Net Debt": "Dług netto",
    "Long Term Debt": "Dług długoterminowy",
    "Stockholders Equity": "Kapitał własny akcjonariuszy",
    "Retained Earnings": "Zyski zatrzymane",
    "Common Stock": "Akcje zwykłe",
    "Treasury Stock": "Akcje własne",
    "Working Capital": "Kapitał obrotowy",
    "Net Tangible Assets": "Aktywa materialne netto",

    # Cash flow
    "Operating Cash Flow": "Przepływy pieniężne z działalności operacyjnej",
    "Investing Cash Flow": "Przepływy pieniężne z działalności inwestycyjnej",
    "Financing Cash Flow": "Przepływy pieniężne z działalności finansowej",
    "Free Cash Flow": "Wolne przepływy pieniężne",
    "Capital Expenditure": "Nakłady inwestycyjne",
    "Repurchase Of Capital Stock": "Skup akcji własnych",
    "Repayment Of Debt": "Spłata długu",
    "Issuance Of Debt": "Emisja długu",
    "Dividends Paid": "Wypłacone dywidendy",
    "End Cash Position": "Stan gotówki na koniec okresu",
    "Beginning Cash Position": "Stan gotówki na początek okresu",
    "Changes In Cash": "Zmiana stanu gotówki",
}


# ---------------------------------------------------------
# FUNKCJE POMOCNICZE
# ---------------------------------------------------------

def normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().upper()


def safe_secret_get(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def translate_key_to_polish(key):
    key_str = str(key)

    if key_str in PL_LABELS:
        return PL_LABELS[key_str]

    if key_str in FINANCIAL_LABELS:
        return FINANCIAL_LABELS[key_str]

    return key_str


def translate_json_keys_to_polish(data):
    """
    Tłumaczy klucze słownika JSON na język polski.
    Działa rekurencyjnie, czyli także w zagnieżdżonych danych finansowych.
    """
    if isinstance(data, dict):
        return {
            translate_key_to_polish(k): translate_json_keys_to_polish(v)
            for k, v in data.items()
        }

    if isinstance(data, list):
        return [translate_json_keys_to_polish(v) for v in data]

    return data


def clean_for_json(data):
    """
    Czyści dane do pokazania przez st.json:
    - usuwa NaN / inf
    - konwertuje daty, numpy typy i pandas typy
    - zamienia obiekty nieobsługiwane przez JSON na tekst
    """
    if isinstance(data, dict):
        return {str(k): clean_for_json(v) for k, v in data.items()}

    if isinstance(data, list):
        return [clean_for_json(v) for v in data]

    if isinstance(data, tuple):
        return [clean_for_json(v) for v in data]

    if isinstance(data, pd.Timestamp):
        return data.isoformat()

    if isinstance(data, np.integer):
        return int(data)

    if isinstance(data, np.floating):
        if np.isnan(data) or np.isinf(data):
            return None
        return float(data)

    if isinstance(data, float):
        if np.isnan(data) or np.isinf(data):
            return None
        return data

    try:
        if data is None:
            return None

        if not isinstance(data, (dict, list, tuple, str)):
            if pd.isna(data):
                return None
    except Exception:
        pass

    try:
        json.dumps(data)
        return data
    except Exception:
        return str(data)


def polish_json(data):
    """
    Funkcja do wyświetlania JSON po polsku.
    Najpierw czyści dane, potem tłumaczy klucze.
    """
    return translate_json_keys_to_polish(clean_for_json(data))


def convert_keys_to_str(d):
    if isinstance(d, dict):
        return {str(k): convert_keys_to_str(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_keys_to_str(i) for i in d]
    else:
        return clean_for_json(d)


def safe_float(value):
    try:
        if value is None:
            return None
        if pd.isna(value):
            return None
        value = float(value)
        if np.isnan(value) or np.isinf(value):
            return None
        return value
    except Exception:
        return None


def format_number(value):
    value = safe_float(value)

    if value is None:
        return "brak"

    abs_value = abs(value)

    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f} bln"

    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} mld"

    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f} mln"

    if abs_value >= 1_000:
        return f"{value:,.0f}".replace(",", " ")

    return f"{value:.2f}"


def format_percent(value):
    value = safe_float(value)

    if value is None:
        return "brak"

    if abs(value) <= 1:
        value *= 100

    return f"{value:.2f}%"


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    rsi = rsi.where(avg_loss != 0, 100)
    rsi = rsi.where(avg_gain != 0, 0)
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50)

    return rsi


def get_domain_from_url(url: str):
    try:
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return None


# ---------------------------------------------------------
# TAVILY NEWS API
# ---------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def fetch_tavily_news(query: str):
    api_key = safe_secret_get("TAVILY_API_KEY")

    if not api_key:
        return []

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": 10,
        }

        response = requests.post(
            "https://api.tavily.com/search",
            json=payload,
            headers=headers,
            timeout=15,
        )

        response.raise_for_status()
        data = response.json()
        results = data.get("results", []) or []

        cleaned = []

        for item in results:
            link = item.get("url")
            publisher = item.get("source") or get_domain_from_url(link) or "Nieznane źródło"

            cleaned.append({
                "title": item.get("title") or "Bez tytułu",
                "publisher": publisher,
                "link": link,
                "content": item.get("content"),
            })

        return cleaned

    except Exception:
        return []


# ---------------------------------------------------------
# POBIERANIE CEN
# ---------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch_prices(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    ticker = normalize_ticker(ticker)

    if not ticker:
        return pd.DataFrame()

    # Ograniczenia Yahoo Finance dla krótkich interwałów.
    if interval == "1m" and period not in ["1d", "5d", "7d"]:
        period = "7d"

    if interval in ["2m", "5m", "15m", "30m", "60m", "90m", "1h"]:
        if period in ["1y", "2y", "5y", "10y", "max"]:
            period = "60d"

    try:
        df = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if df is None or df.empty:
            stock = yf.Ticker(ticker)
            df = stock.history(
                period=period,
                interval=interval,
                auto_adjust=False,
            )

        if df is None or df.empty:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        required_cols = ["Open", "High", "Low", "Close"]

        for col in required_cols:
            if col not in df.columns:
                return pd.DataFrame()

        df = df.dropna(how="all")
        df = df[~df.index.duplicated(keep="last")]

        return df

    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------
# WSKAŹNIKI TECHNICZNE
# ---------------------------------------------------------

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame()

    df = df.copy()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["SMA20"] = df["Close"].rolling(20, min_periods=1).mean()
    df["SMA50"] = df["Close"].rolling(50, min_periods=1).mean()
    df["SMA200"] = df["Close"].rolling(200, min_periods=1).mean()
    df["RSI14"] = calculate_rsi(df["Close"], 14)

    return df


# ---------------------------------------------------------
# WYKRES
# ---------------------------------------------------------

def make_price_chart(df: pd.DataFrame, ticker: str):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=(f"Wykres ceny: {ticker}", "RSI")
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Cena"
        ),
        row=1,
        col=1
    )

    sma_colors = {
        "SMA20": "#00BFFF",
        "SMA50": "#FFA500",
        "SMA200": "#FF4B4B",
    }

    for col in ["SMA20", "SMA50", "SMA200"]:
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[col],
                    name=col,
                    line=dict(width=1.3, color=sma_colors.get(col))
                ),
                row=1,
                col=1
            )

    if "RSI14" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["RSI14"],
                name="RSI14",
                line=dict(width=1.3, color="#B388FF")
            ),
            row=2,
            col=1
        )

        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(
        height=750,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=20, r=20, t=70, b=20),
    )

    fig.update_yaxes(title_text="Cena", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)

    return fig


# ---------------------------------------------------------
# FUNDAMENTY – POBIERANIE
# ---------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yfinance_fundamentals(ticker: str) -> dict:
    ticker = normalize_ticker(ticker)

    results = {
        "profile": None,
        "metrics": None,
        "price_target": None,
        "income": None,
        "balance": None,
        "cash": None,
        "_errors": []
    }

    if not ticker:
        results["_errors"].append("Brak tickera.")
        return results

    try:
        stock = yf.Ticker(ticker)

        try:
            info = stock.info
            if not isinstance(info, dict):
                info = {}
        except Exception as e:
            info = {}
            results["_errors"].append(f"info: {e}")

        dividend_yield = info.get("dividendYield")
        dividend_yield_float = safe_float(dividend_yield)

        results["profile"] = {
            "symbol": ticker,
            "longName": info.get("longName"),
            "shortName": info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "website": info.get("website"),
            "longBusinessSummary": info.get("longBusinessSummary"),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "quoteType": info.get("quoteType"),
        }

        results["metrics"] = {
            "symbol": ticker,
            "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
            "marketCap": info.get("marketCap"),
            "enterpriseValue": info.get("enterpriseValue"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "priceToBook": info.get("priceToBook"),
            "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months"),
            "profitMargins": info.get("profitMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "grossMargins": info.get("grossMargins"),
            "returnOnAssets": info.get("returnOnAssets"),
            "returnOnEquity": info.get("returnOnEquity"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "totalRevenue": info.get("totalRevenue"),
            "totalDebt": info.get("totalDebt"),
            "totalCash": info.get("totalCash"),
            "freeCashflow": info.get("freeCashflow"),
            "operatingCashflow": info.get("operatingCashflow"),
            "dividendYield": dividend_yield,
            "dividendYieldPercent": dividend_yield_float * 100 if dividend_yield_float is not None and abs(dividend_yield_float) <= 1 else dividend_yield_float,
            "beta": info.get("beta"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        }

        results["price_target"] = {
            "targetHighPrice": info.get("targetHighPrice"),
            "targetLowPrice": info.get("targetLowPrice"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "targetMedianPrice": info.get("targetMedianPrice"),
            "recommendationMean": info.get("recommendationMean"),
            "recommendationKey": info.get("recommendationKey"),
            "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
        }

        try:
            income = stock.financials
            if income is not None and not income.empty:
                results["income"] = convert_keys_to_str(income.to_dict())
        except Exception as e:
            results["_errors"].append(f"income: {e}")

        try:
            balance = stock.balance_sheet
            if balance is not None and not balance.empty:
                results["balance"] = convert_keys_to_str(balance.to_dict())
        except Exception as e:
            results["_errors"].append(f"balance: {e}")

        try:
            cash = stock.cashflow
            if cash is not None and not cash.empty:
                results["cash"] = convert_keys_to_str(cash.to_dict())
        except Exception as e:
            results["_errors"].append(f"cash: {e}")

    except Exception as e:
        results["_errors"].append(f"general yfinance error: {e}")

    return clean_for_json(results)


# ---------------------------------------------------------
# NEWSY YAHOO
# ---------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def fetch_yfinance_news(ticker: str):
    ticker = normalize_ticker(ticker)

    if not ticker:
        return []

    try:
        stock = yf.Ticker(ticker)
        news = stock.news or []
        cleaned = []

        for item in news[:10]:
            title = item.get("title")
            publisher = item.get("publisher")
            link = item.get("link")
            publish_time = item.get("providerPublishTime")
            news_type = item.get("type")

            content = item.get("content") or {}

            if not title:
                title = content.get("title")

            if not publisher:
                provider = content.get("provider") or {}
                publisher = provider.get("displayName") or provider.get("name")

            if not link:
                canonical_url = content.get("canonicalUrl") or {}
                click_url = content.get("clickThroughUrl") or {}
                link = canonical_url.get("url") or click_url.get("url")

            if not publish_time:
                publish_time = content.get("pubDate") or content.get("displayTime")

            if not news_type:
                news_type = content.get("contentType")

            cleaned.append({
                "title": title or "Bez tytułu",
                "publisher": publisher or get_domain_from_url(link) or "Nieznane źródło",
                "link": link,
                "providerPublishTime": publish_time,
                "type": news_type,
            })

        return cleaned

    except Exception:
        return []


# ---------------------------------------------------------
# SYGNAŁ TECHNICZNY
# ---------------------------------------------------------

def simple_signal(df: pd.DataFrame) -> dict:
    result = {
        "signal": "BRAK DANYCH",
        "comment": "",
        "last_close": None,
        "rsi": None,
        "sma20": None,
        "sma50": None,
    }

    if df is None or df.empty or "Close" not in df.columns:
        result["comment"] = "Brak danych cenowych."
        return result

    df = add_indicators(df)

    if df.empty:
        result["comment"] = "Brak danych po przeliczeniu wskaźników."
        return result

    valid_df = df.dropna(subset=["Close"])

    if valid_df.empty:
        result["comment"] = "Brak poprawnych wartości Close."
        return result

    last = valid_df.iloc[-1]

    close = safe_float(last.get("Close"))
    rsi = safe_float(last.get("RSI14"))
    sma20 = safe_float(last.get("SMA20"))
    sma50 = safe_float(last.get("SMA50"))

    result["last_close"] = close
    result["rsi"] = rsi
    result["sma20"] = sma20
    result["sma50"] = sma50

    if close is None:
        result["comment"] = "Brak ostatniej ceny zamknięcia."
        return result

    score = 0
    comments = []

    if sma20 is not None:
        if close > sma20:
            score += 1
            comments.append("Cena powyżej SMA20.")
        else:
            score -= 1
            comments.append("Cena poniżej SMA20.")

    if sma50 is not None:
        if close > sma50:
            score += 1
            comments.append("Cena powyżej SMA50.")
        else:
            score -= 1
            comments.append("Cena poniżej SMA50.")

    if rsi is not None:
        if rsi < 30:
            score += 1
            comments.append("RSI wskazuje możliwe wyprzedanie.")
        elif rsi > 70:
            score -= 1
            comments.append("RSI wskazuje możliwe wykupienie.")
        else:
            comments.append("RSI neutralne.")
    else:
        comments.append("Za mało danych do pełnego RSI.")

    if score >= 2:
        result["signal"] = "POZYTYWNY"
    elif score <= -2:
        result["signal"] = "NEGATYWNY"
    else:
        result["signal"] = "NEUTRALNY"

    result["comment"] = " ".join(comments)

    return result


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

st.sidebar.title("📈 Kombajn Giełdowy")

app_mode = st.sidebar.selectbox(
    "Wybierz moduł aplikacji:",
    [
        "🏠 Strona główna",
        "📈 Analiza techniczna",
        "📊 Fundamenty spółki",
        "📰 Wiadomości rynkowe",
    ]
)

# ---------------------------------------------------------
# STRONA GŁÓWNA
# ---------------------------------------------------------

if app_mode == "🏠 Strona główna":
    st.title("📈 Kombajn Giełdowy")

    st.write(
        """
        To jest czysta, lekka wersja aplikacji bez OpenBB.

        Źródła danych:

        • ceny: Yahoo Finance przez bibliotekę `yfinance`  
        • fundamenty: Yahoo Finance  
        • wiadomości: Yahoo Finance + Tavily opcjonalnie  

        Przykłady tickerów:

        • USA: `AAPL`, `MSFT`, `NVDA`, `TSLA`  
        • GPW: `CDR.WA`, `PKO.WA`, `KGH.WA`  
        • krypto: `BTC-USD`, `ETH-USD`
        """
    )

    st.success("Aplikacja działa i jest gotowa do analizy.")

    st.info(
        "To narzędzie ma charakter edukacyjny i informacyjny. "
        "Nie jest rekomendacją inwestycyjną."
    )


# ---------------------------------------------------------
# ANALIZA TECHNICZNA
# ---------------------------------------------------------

elif app_mode == "📈 Analiza techniczna":
    st.title("📈 Analiza techniczna")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        ticker = normalize_ticker(st.text_input("Wpisz ticker:", "AAPL"))

    with col_b:
        period_label = st.selectbox(
            "Zakres danych:",
            [
                "1 dzień",
                "5 dni",
                "7 dni",
                "1 miesiąc",
                "3 miesiące",
                "6 miesięcy",
                "1 rok",
                "2 lata",
                "5 lat",
                "maksymalnie"
            ],
            index=6
        )

        period_map = {
            "1 dzień": "1d",
            "5 dni": "5d",
            "7 dni": "7d",
            "1 miesiąc": "1mo",
            "3 miesiące": "3mo",
            "6 miesięcy": "6mo",
            "1 rok": "1y",
            "2 lata": "2y",
            "5 lat": "5y",
            "maksymalnie": "max",
        }

        period = period_map[period_label]

    with col_c:
        interval_label = st.selectbox(
            "Interwał świec:",
            [
                "1 minuta",
                "5 minut",
                "15 minut",
                "30 minut",
                "1 godzina",
                "1 dzień",
                "1 tydzień",
                "1 miesiąc"
            ],
            index=5
        )

        interval_map = {
            "1 minuta": "1m",
            "5 minut": "5m",
            "15 minut": "15m",
            "30 minut": "30m",
            "1 godzina": "1h",
            "1 dzień": "1d",
            "1 tydzień": "1wk",
            "1 miesiąc": "1mo",
        }

        interval = interval_map[interval_label]

    if st.button("Analizuj"):
        try:
            if not ticker:
                st.error("Wpisz ticker.")
            else:
                with st.spinner("Pobieranie danych i analiza..."):
                    df = fetch_prices(ticker, period, interval)

                if df.empty:
                    st.error(
                        "Brak danych z Yahoo Finance. Sprawdź ticker albo interwał.\n\n"
                        "Dla GPW używaj np. `CDR.WA`, `PKO.WA`, `KGH.WA`."
                    )
                else:
                    df_ind = add_indicators(df)
                    signal = simple_signal(df_ind)

                    st.subheader(f"Wynik analizy: {ticker}")

                    c1, c2, c3 = st.columns(3)

                    c1.metric("Sygnał", signal["signal"])
                    c2.metric("Cena", format_number(signal["last_close"]))
                    c3.metric("RSI", round(signal["rsi"], 2) if signal["rsi"] is not None else "brak")

                    st.info(signal["comment"])

                    fig = make_price_chart(df_ind, ticker)
                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("Dane tabelaryczne — ostatnie 100 wierszy"):
                        st.dataframe(df_ind.tail(100), use_container_width=True)

        except Exception:
            st.error("Analiza została przerwana błędem.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())


# ---------------------------------------------------------
# FUNDAMENTY
# ---------------------------------------------------------

elif app_mode == "📊 Fundamenty spółki":
    st.title("📊 Fundamenty spółki")

    st.caption("Dla GPW używaj sufiksu `.WA`, np. `CDR.WA`, `PKO.WA`, `KGH.WA`.")

    ticker_f = normalize_ticker(st.text_input("Ticker do fundamentów:", "AAPL"))

    if st.button("Pobierz fundamenty"):
        try:
            if not ticker_f:
                st.error("Wpisz ticker.")
            else:
                with st.spinner("Pobieranie fundamentów..."):
                    fund_data = fetch_yfinance_fundamentals(ticker_f)

                errors = fund_data.get("_errors", [])

                if errors:
                    with st.expander("Ostrzeżenia / log"):
                        for err in errors:
                            st.warning(str(err))

                metrics = fund_data.get("metrics") or {}
                profile = fund_data.get("profile") or {}

                st.subheader(profile.get("longName") or profile.get("shortName") or ticker_f)

                c1, c2, c3, c4 = st.columns(4)

                c1.metric("Cena", format_number(metrics.get("currentPrice")))
                c2.metric("Kapitalizacja", format_number(metrics.get("marketCap")))
                c3.metric("P/E trailing", format_number(metrics.get("trailingPE")))
                c4.metric("Dywidenda", format_percent(metrics.get("dividendYield")))

                st.write("### Profil spółki")
                st.json(polish_json(profile))

                st.write("### Wskaźniki finansowe")
                st.json(polish_json(metrics))

                # ---------------------------------------------------------
                # PODSUMOWANIE FUNDAMENTALNE
                # ---------------------------------------------------------

                st.write("### Podsumowanie fundamentalne")

                summary = []

                pb = safe_float(metrics.get("priceToBook"))
                pe = safe_float(metrics.get("trailingPE"))
                margin = safe_float(metrics.get("profitMargins"))
                roe = safe_float(metrics.get("returnOnEquity"))
                roa = safe_float(metrics.get("returnOnAssets"))
                cash = safe_float(metrics.get("totalCash"))
                debt = safe_float(metrics.get("totalDebt"))
                beta = safe_float(metrics.get("beta"))
                dy = safe_float(metrics.get("dividendYield"))

                if dy is not None and abs(dy) <= 1:
                    dy_percent = dy * 100
                else:
                    dy_percent = dy

                if pb is not None:
                    if pb < 1:
                        summary.append("• **Spółka wyceniana poniżej wartości księgowej — P/B < 1.** Potencjalnie tania, ale wymaga sprawdzenia jakości aktywów.")
                    elif pb < 2:
                        summary.append("• **P/B w rozsądnym zakresie.** Wycena względem wartości księgowej wygląda neutralnie.")
                    else:
                        summary.append("• **P/B wysokie.** Rynek płaci dużą premię względem wartości księgowej.")

                if pe is not None:
                    if pe <= 0:
                        summary.append("• **P/E ujemne lub zerowe.** Spółka może być nierentowna albo ma nietypowe dane księgowe.")
                    elif pe < 10:
                        summary.append("• **Niskie P/E < 10.** Spółka może być tania, ale warto sprawdzić, czy nie wynika to ze słabych perspektyw.")
                    elif pe < 20:
                        summary.append("• **P/E w umiarkowanym zakresie.** Wycena wygląda neutralnie.")
                    else:
                        summary.append("• **Wysokie P/E.** Rynek zakłada mocny wzrost albo spółka może być droga.")

                if margin is not None:
                    if margin > 0.2:
                        summary.append("• **Wysokie marże.** Biznes wygląda bardzo rentownie.")
                    elif margin > 0.1:
                        summary.append("• **Przyzwoite marże.** Rentowność wygląda poprawnie.")
                    elif margin > 0:
                        summary.append("• **Niskie marże.** Biznes ma ograniczoną rentowność.")
                    else:
                        summary.append("• **Ujemna marża.** Spółka generuje stratę netto.")

                if roe is not None:
                    if roe > 0.15:
                        summary.append("• **Wysokie ROE.** Spółka efektywnie wykorzystuje kapitał własny.")
                    elif roe > 0.08:
                        summary.append("• **ROE w normie.** Efektywność kapitału jest umiarkowana.")
                    elif roe > 0:
                        summary.append("• **Niskie ROE.** Efektywność kapitału jest słaba.")
                    else:
                        summary.append("• **Ujemne ROE.** Spółka może mieć problem z rentownością.")

                if roa is not None:
                    if roa > 0.08:
                        summary.append("• **Dobre ROA.** Aktywa pracują efektywnie.")
                    elif roa > 0.03:
                        summary.append("• **ROA umiarkowane.** Efektywność aktywów jest przeciętna.")
                    elif roa > 0:
                        summary.append("• **Niskie ROA.** Aktywa generują mały zwrot.")
                    else:
                        summary.append("• **Ujemne ROA.** Aktywa nie generują dodatniego wyniku.")

                if cash is not None and debt is not None:
                    if cash > debt:
                        summary.append("• **Więcej gotówki niż długu.** Struktura finansowa wygląda bezpiecznie.")
                    elif cash > 0 and debt > cash * 3:
                        summary.append("• **Dług znacząco przewyższa gotówkę.** Warto sprawdzić zadłużenie i płynność.")
                    elif cash <= 0 and debt > 0:
                        summary.append("• **Spółka ma dług i bardzo mało gotówki.** Warto dokładnie sprawdzić płynność.")
                    else:
                        summary.append("• **Dług przewyższa gotówkę, ale nie skrajnie.** Wymaga dalszej analizy.")

                if dy_percent is not None:
                    if dy_percent > 10:
                        summary.append("• **Bardzo wysoka dywidenda.** Może być trudna do utrzymania.")
                    elif dy_percent > 5:
                        summary.append("• **Wysoka dywidenda.** Atrakcyjna dla inwestorów dochodowych.")
                    elif dy_percent > 0:
                        summary.append("• **Umiarkowana dywidenda.** Spółka dzieli się zyskiem.")
                    else:
                        summary.append("• **Brak dywidendy albo dywidenda zerowa.**")

                if beta is not None:
                    if beta < 0.7:
                        summary.append("• **Niska beta.** Spółka defensywna, zwykle mniej zmienna od rynku.")
                    elif beta < 1.2:
                        summary.append("• **Beta neutralna.** Zmienność zbliżona do rynku.")
                    else:
                        summary.append("• **Wysoka beta.** Spółka bardziej zmienna i ryzykowna.")

                if summary:
                    for line in summary:
                        st.write(line)
                else:
                    st.info("Brak danych do analizy fundamentalnej.")

                st.warning(
                    "Podsumowanie jest automatyczne i uproszczone. "
                    "Nie traktuj go jako rekomendacji inwestycyjnej."
                )

                # ---------------------------------------------------------
                # PRICE TARGET
                # ---------------------------------------------------------

                st.write("### Cele cenowe analityków")

                pt = fund_data.get("price_target") or {}

                if not pt or all(v is None for v in pt.values()):
                    st.info("Brak prognoz analityków dla tej spółki.")
                else:
                    cpt1, cpt2, cpt3 = st.columns(3)

                    cpt1.metric("Średni cel", format_number(pt.get("targetMeanPrice")))
                    cpt2.metric("Najniższy cel", format_number(pt.get("targetLowPrice")))
                    cpt3.metric("Najwyższy cel", format_number(pt.get("targetHighPrice")))

                    st.json(polish_json(pt))

                # ---------------------------------------------------------
                # SPRAWOZDANIA FINANSOWE
                # ---------------------------------------------------------

                with st.expander("Rachunek zysków i strat"):
                    income_data = fund_data.get("income")
                    if income_data:
                        st.json(polish_json(income_data))
                    else:
                        st.info("Brak danych.")

                with st.expander("Bilans"):
                    balance_data = fund_data.get("balance")
                    if balance_data:
                        st.json(polish_json(balance_data))
                    else:
                        st.info("Brak danych.")

                with st.expander("Przepływy pieniężne"):
                    cash_data = fund_data.get("cash")
                    if cash_data:
                        st.json(polish_json(cash_data))
                    else:
                        st.info("Brak danych.")

        except Exception:
            st.error("Nie udało się pobrać fundamentów.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())


# ---------------------------------------------------------
# WIADOMOŚCI
# ---------------------------------------------------------

elif app_mode == "📰 Wiadomości rynkowe":
    st.title("📰 Wiadomości rynkowe")

    ticker_n = normalize_ticker(st.text_input("Ticker do wyszukania wiadomości:", "AAPL"))

    col1, col2 = st.columns(2)

    with col1:
        use_tavily = st.checkbox("Użyj Tavily — szersze newsy", value=True)

    with col2:
        query_extra = st.text_input("Dodatkowy kontekst, np. Poland, GPW:", "")

    if st.button("Pobierz najnowsze wiadomości"):
        try:
            if not ticker_n:
                st.error("Wpisz ticker.")
            else:
                if use_tavily:
                    q = ticker_n

                    if query_extra.strip():
                        q += f" {query_extra.strip()}"

                    with st.spinner("Pobieranie newsów z Tavily..."):
                        tav_news = fetch_tavily_news(q)

                    if tav_news:
                        st.subheader("🔎 Tavily — szersze newsy")

                        for item in tav_news:
                            title = item.get("title") or "Bez tytułu"
                            publisher = item.get("publisher") or "Nieznane źródło"
                            link = item.get("link")

                            st.write(f"### {title}")
                            st.caption(f"Źródło: {publisher}")

                            if link:
                                st.markdown(f"[Otwórz artykuł]({link})")

                            st.divider()

                        with st.expander("Dane newsów Tavily jako JSON po polsku"):
                            st.json(polish_json(tav_news))
                    else:
                        st.info("Brak wyników z Tavily albo brak klucza API `TAVILY_API_KEY`.")

                with st.spinner("Pobieranie newsów z Yahoo Finance..."):
                    yahoo_news = fetch_yfinance_news(ticker_n)

                if not yahoo_news:
                    st.info("Brak newsów z Yahoo Finance dla tego tickera.")
                else:
                    st.subheader("📰 Yahoo Finance — wiadomości")

                    for item in yahoo_news:
                        title = item.get("title") or "Bez tytułu"
                        publisher = item.get("publisher") or "Nieznane źródło"
                        link = item.get("link")

                        st.write(f"### {title}")
                        st.caption(f"Źródło: {publisher}")

                        if link:
                            st.markdown(f"[Otwórz artykuł]({link})")

                        st.divider()

                    with st.expander("Dane newsów Yahoo Finance jako JSON po polsku"):
                        st.json(polish_json(yahoo_news))

        except Exception:
            st.error("Nie udało się pobrać newsów.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())
