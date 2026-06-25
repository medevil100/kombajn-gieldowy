
import json
import traceback
import textwrap
import unicodedata
from datetime import datetime
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
# LISTY TICKERÓW DO SKANERA
# ---------------------------------------------------------

USA_POPULAR = [
        "HUMA", "TCRX", "GOSS", "PLRX", "TTOO", "BNOX", "IMUX", "SLS", "DRMA", "BDRX",
        "MREO", "XLO", "TCON", "VIRI", "ACRS", "AURA", "KTRA", "NRSN", "ANIX",
        "CRVS", "ADVM", "APM", "SABS", "HILS", "RNAZ", "SLNO", "IMNN", "BCTX", "ATHE",
        "MNOV", "BOLT", "INFI", "APLT", "CLRB", "ENLV", "EVGN", "GRTS", "HSTO", "IMMP"

]

GPW_POPULAR = [
   "BBT.WA", "BML.WA", "BOS.WA", "BRA.WA", "CNT.WA", "CRB.WA", "DCR.WA", "FON.WA",
"GEN.WA", "HUG.WA", "IMS.WA", "INC.WA", "KOM.WA", "LTG.WA", "MIR.WA", "MNC.WA",
"ONC.WA", "PLT.WA", "QRS.WA", "VOX.WA", "STX.WA", "NVG.WA", "KCH.WA", "APS.WA"

]

# ---------------------------------------------------------
# TŁUMACZENIA
# ---------------------------------------------------------

PL_LABELS = {
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

    "currentPrice": "Aktualna cena",
    "marketCap": "Kapitalizacja rynkowa",
    "enterpriseValue": "Wartość przedsiębiorstwa",
    "trailingPE": "P/E historyczne",
    "forwardPE": "P/E prognozowane",
    "priceToBook": "Cena / wartość księgowa",
    "priceToSalesTrailing12Months": "Cena / sprzedaż TTM",
    "profitMargins": "Marża netto",
    "operatingMargins": "Marża operacyjna",
    "grossMargins": "Marża brutto",
    "returnOnAssets": "ROA",
    "returnOnEquity": "ROE",
    "revenueGrowth": "Wzrost przychodów",
    "earningsGrowth": "Wzrost zysków",
    "totalRevenue": "Przychody całkowite",
    "totalDebt": "Dług całkowity",
    "totalCash": "Gotówka całkowita",
    "freeCashflow": "Wolne przepływy pieniężne",
    "operatingCashflow": "Operacyjne przepływy pieniężne",
    "dividendYield": "Stopa dywidendy",
    "dividendYieldPercent": "Stopa dywidendy %",
    "beta": "Beta",
    "fiftyTwoWeekHigh": "Maksimum 52 tyg.",
    "fiftyTwoWeekLow": "Minimum 52 tyg.",

    "targetHighPrice": "Najwyższa cena docelowa",
    "targetLowPrice": "Najniższa cena docelowa",
    "targetMeanPrice": "Średnia cena docelowa",
    "targetMedianPrice": "Mediana ceny docelowej",
    "recommendationMean": "Średnia rekomendacja",
    "recommendationKey": "Rekomendacja",
    "numberOfAnalystOpinions": "Liczba opinii analityków",

    "title": "Tytuł",
    "publisher": "Wydawca",
    "link": "Link",
    "providerPublishTime": "Czas publikacji",
    "type": "Typ",
    "content": "Treść",
}

FINANCIAL_LABELS = {
    "Total Revenue": "Przychody całkowite",
    "Operating Revenue": "Przychody operacyjne",
    "Cost Of Revenue": "Koszt przychodów",
    "Gross Profit": "Zysk brutto",
    "Operating Expense": "Koszty operacyjne",
    "Operating Income": "Zysk operacyjny",
    "Net Income": "Zysk netto",
    "Net Income Common Stockholders": "Zysk netto dla akcjonariuszy",
    "Basic EPS": "Podstawowy EPS",
    "Diluted EPS": "Rozwodniony EPS",
    "EBIT": "EBIT",
    "EBITDA": "EBITDA",
    "Interest Expense": "Koszty odsetkowe",
    "Interest Income": "Przychody odsetkowe",
    "Pretax Income": "Zysk przed opodatkowaniem",
    "Tax Provision": "Podatek dochodowy",
    "Research And Development": "Badania i rozwój",
    "Selling General And Administration": "Sprzedaż i administracja",

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
    "Stockholders Equity": "Kapitał własny",
    "Retained Earnings": "Zyski zatrzymane",
    "Common Stock": "Akcje zwykłe",
    "Treasury Stock": "Akcje własne",
    "Working Capital": "Kapitał obrotowy",
    "Net Tangible Assets": "Aktywa materialne netto",

    "Operating Cash Flow": "Przepływy operacyjne",
    "Investing Cash Flow": "Przepływy inwestycyjne",
    "Financing Cash Flow": "Przepływy finansowe",
    "Free Cash Flow": "Wolne przepływy pieniężne",
    "Capital Expenditure": "Nakłady inwestycyjne",
    "Repurchase Of Capital Stock": "Skup akcji własnych",
    "Repayment Of Debt": "Spłata długu",
    "Issuance Of Debt": "Emisja długu",
    "Dividends Paid": "Wypłacone dywidendy",
    "End Cash Position": "Gotówka na koniec okresu",
    "Beginning Cash Position": "Gotówka na początek okresu",
    "Changes In Cash": "Zmiana gotówki",
}

# ---------------------------------------------------------
# FUNKCJE POMOCNICZE
# ---------------------------------------------------------

def normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().upper()


def parse_tickers(text: str):
    if not text:
        return []
    text = text.replace(";", ",").replace("\n", ",")
    tickers = [normalize_ticker(x) for x in text.split(",")]
    return [x for x in tickers if x]


def safe_secret_get(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


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


def clean_for_json(data):
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


def convert_keys_to_str(d):
    if isinstance(d, dict):
        return {str(k): convert_keys_to_str(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_keys_to_str(i) for i in d]
    else:
        return clean_for_json(d)


def translate_key_to_polish(key):
    key = str(key)
    if key in PL_LABELS:
        return PL_LABELS[key]
    if key in FINANCIAL_LABELS:
        return FINANCIAL_LABELS[key]
    return key


def translate_json_keys_to_polish(data):
    if isinstance(data, dict):
        return {translate_key_to_polish(k): translate_json_keys_to_polish(v) for k, v in data.items()}
    if isinstance(data, list):
        return [translate_json_keys_to_polish(v) for v in data]
    return data


def polish_json(data):
    return translate_json_keys_to_polish(clean_for_json(data))


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


def get_domain_from_url(url: str):
    try:
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return None


def ascii_text(text):
    text = str(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    replacements = {
        "ł": "l", "Ł": "L", "ą": "a", "Ą": "A", "ć": "c", "Ć": "C",
        "ę": "e", "Ę": "E", "ń": "n", "Ń": "N", "ó": "o", "Ó": "O",
        "ś": "s", "Ś": "S", "ź": "z", "Ź": "Z", "ż": "z", "Ż": "Z"
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "ignore").decode("latin-1")


def make_simple_pdf(title, lines):
    """
    Prosty generator PDF bez dodatkowych bibliotek.
    Polskie znaki są upraszczane do ASCII, żeby PDF działał bez fontów zewnętrznych.
    """
    title = ascii_text(title)
    lines = [ascii_text(x) for x in lines]

    content_lines = []
    content_lines.append("BT")
    content_lines.append("/F1 18 Tf")
    content_lines.append("50 790 Td")
    content_lines.append(f"({pdf_escape(title)}) Tj")
    content_lines.append("0 -30 Td")
    content_lines.append("/F1 10 Tf")

    y_lines = []
    for line in lines:
        wrapped = textwrap.wrap(str(line), width=95) or [""]
        for w in wrapped:
            y_lines.append(w)

    current = 0
    for line in y_lines[:58]:
        if current > 0:
            content_lines.append("0 -14 Td")
        content_lines.append(f"({pdf_escape(line)}) Tj")
        current += 1

    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", "ignore")

    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    pdf = b"%PDF-1.4\n"
    offsets = [0]

    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"

    for off in offsets[1:]:
        pdf += f"{off:010d} 00000 n \n".encode()

    pdf += b"trailer\n"
    pdf += f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    pdf += b"startxref\n"
    pdf += str(xref_pos).encode() + b"\n%%EOF"

    return pdf


def pdf_escape(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# ---------------------------------------------------------
# WSKAŹNIKI TECHNICZNE
# ---------------------------------------------------------

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


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame()

    df = df.copy()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    close = df["Close"]

    df["SMA20"] = close.rolling(20, min_periods=1).mean()
    df["SMA50"] = close.rolling(50, min_periods=1).mean()
    df["SMA200"] = close.rolling(200, min_periods=1).mean()

    df["EMA12"] = close.ewm(span=12, adjust=False).mean()
    df["EMA26"] = close.ewm(span=26, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()

    df["RSI14"] = calculate_rsi(close, 14)

    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIGNAL"]

    bb_mid = close.rolling(20, min_periods=1).mean()
    bb_std = close.rolling(20, min_periods=1).std()
    df["BB_MID"] = bb_mid
    df["BB_UPPER"] = bb_mid + 2 * bb_std
    df["BB_LOWER"] = bb_mid - 2 * bb_std

    return df


def simple_signal(df: pd.DataFrame) -> dict:
    result = {
        "signal": "BRAK DANYCH",
        "score": 0,
        "comment": "",
        "last_close": None,
        "rsi": None,
        "sma20": None,
        "sma50": None,
        "macd": None,
    }

    if df is None or df.empty or "Close" not in df.columns:
        result["comment"] = "Brak danych cenowych."
        return result

    df = add_indicators(df)
    valid_df = df.dropna(subset=["Close"])

    if valid_df.empty:
        result["comment"] = "Brak poprawnych wartości Close."
        return result

    last = valid_df.iloc[-1]

    close = safe_float(last.get("Close"))
    rsi = safe_float(last.get("RSI14"))
    sma20 = safe_float(last.get("SMA20"))
    sma50 = safe_float(last.get("SMA50"))
    ema50 = safe_float(last.get("EMA50"))
    macd = safe_float(last.get("MACD"))
    macd_signal = safe_float(last.get("MACD_SIGNAL"))

    result["last_close"] = close
    result["rsi"] = rsi
    result["sma20"] = sma20
    result["sma50"] = sma50
    result["macd"] = macd

    if close is None:
        result["comment"] = "Brak ostatniej ceny."
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

    if ema50 is not None:
        if close > ema50:
            score += 1
            comments.append("Cena powyżej EMA50.")
        else:
            score -= 1
            comments.append("Cena poniżej EMA50.")

    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            score += 1
            comments.append("MACD pozytywny.")
        else:
            score -= 1
            comments.append("MACD negatywny.")

    if rsi is not None:
        if rsi < 30:
            score += 1
            comments.append("RSI wskazuje możliwe wyprzedanie.")
        elif rsi > 70:
            score -= 1
            comments.append("RSI wskazuje możliwe wykupienie.")
        else:
            comments.append("RSI neutralne.")

    if score >= 3:
        signal = "POZYTYWNY"
    elif score <= -3:
        signal = "NEGATYWNY"
    else:
        signal = "NEUTRALNY"

    result["signal"] = signal
    result["score"] = score
    result["comment"] = " ".join(comments)

    return result


# ---------------------------------------------------------
# POBIERANIE DANYCH
# ---------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch_prices(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    ticker = normalize_ticker(ticker)

    if not ticker:
        return pd.DataFrame()

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
            df = stock.history(period=period, interval=interval, auto_adjust=False)

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
# OCENA FUNDAMENTALNA
# ---------------------------------------------------------

def fundamental_score(metrics: dict) -> dict:
    score = 50
    comments = []

    pe = safe_float(metrics.get("trailingPE"))
    pb = safe_float(metrics.get("priceToBook"))
    margin = safe_float(metrics.get("profitMargins"))
    roe = safe_float(metrics.get("returnOnEquity"))
    roa = safe_float(metrics.get("returnOnAssets"))
    cash = safe_float(metrics.get("totalCash"))
    debt = safe_float(metrics.get("totalDebt"))
    rev_growth = safe_float(metrics.get("revenueGrowth"))
    earn_growth = safe_float(metrics.get("earningsGrowth"))
    fcf = safe_float(metrics.get("freeCashflow"))
    beta = safe_float(metrics.get("beta"))

    if pe is not None:
        if 0 < pe < 12:
            score += 8
            comments.append("Atrakcyjne P/E.")
        elif 12 <= pe <= 25:
            score += 3
            comments.append("P/E neutralne.")
        elif pe > 35:
            score -= 8
            comments.append("Wysokie P/E.")
        elif pe <= 0:
            score -= 10
            comments.append("P/E ujemne lub zerowe.")

    if pb is not None:
        if 0 < pb < 1:
            score += 7
            comments.append("P/B poniżej 1.")
        elif 1 <= pb <= 3:
            score += 3
            comments.append("P/B umiarkowane.")
        elif pb > 5:
            score -= 6
            comments.append("Wysokie P/B.")

    if margin is not None:
        if margin > 0.20:
            score += 10
            comments.append("Wysoka marża netto.")
        elif margin > 0.08:
            score += 5
            comments.append("Dobra marża netto.")
        elif margin < 0:
            score -= 12
            comments.append("Ujemna marża netto.")
        else:
            score -= 3
            comments.append("Niska marża netto.")

    if roe is not None:
        if roe > 0.18:
            score += 10
            comments.append("Bardzo dobre ROE.")
        elif roe > 0.10:
            score += 5
            comments.append("Poprawne ROE.")
        elif roe < 0:
            score -= 10
            comments.append("Ujemne ROE.")

    if roa is not None:
        if roa > 0.08:
            score += 5
            comments.append("Dobre ROA.")
        elif roa < 0:
            score -= 5
            comments.append("Ujemne ROA.")

    if cash is not None and debt is not None:
        if debt <= 0:
            score += 5
            comments.append("Brak istotnego długu.")
        elif cash > debt:
            score += 8
            comments.append("Gotówka większa niż dług.")
        elif cash > 0 and debt > cash * 3:
            score -= 8
            comments.append("Dług znacząco większy od gotówki.")
        else:
            score -= 2
            comments.append("Dług większy od gotówki.")

    if rev_growth is not None:
        if rev_growth > 0.15:
            score += 7
            comments.append("Silny wzrost przychodów.")
        elif rev_growth > 0:
            score += 3
            comments.append("Dodatni wzrost przychodów.")
        else:
            score -= 5
            comments.append("Spadek przychodów.")

    if earn_growth is not None:
        if earn_growth > 0.15:
            score += 7
            comments.append("Silny wzrost zysków.")
        elif earn_growth > 0:
            score += 3
            comments.append("Dodatni wzrost zysków.")
        else:
            score -= 5
            comments.append("Spadek zysków.")

    if fcf is not None:
        if fcf > 0:
            score += 5
            comments.append("Dodatnie wolne przepływy pieniężne.")
        else:
            score -= 7
            comments.append("Ujemne wolne przepływy pieniężne.")

    if beta is not None:
        if beta < 0.7:
            score += 3
            comments.append("Niska zmienność beta.")
        elif beta > 1.5:
            score -= 4
            comments.append("Wysoka zmienność beta.")

    score = max(0, min(100, int(round(score))))

    if score >= 75:
        label = "BARDZO DOBRA"
    elif score >= 60:
        label = "DOBRA"
    elif score >= 45:
        label = "NEUTRALNA"
    elif score >= 30:
        label = "SŁABA"
    else:
        label = "BARDZO SŁABA"

    return {
        "score": score,
        "label": label,
        "comments": comments
    }


# ---------------------------------------------------------
# STATYSTYKI I TABELE
# ---------------------------------------------------------

def performance_stats(df: pd.DataFrame):
    if df is None or df.empty or "Close" not in df.columns:
        return {}

    df = add_indicators(df)
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()

    if len(close) < 2:
        return {}

    returns = close.pct_change().dropna()
    last = safe_float(close.iloc[-1])
    first = safe_float(close.iloc[0])
    total_return = ((last / first) - 1) if last and first else None

    volatility = returns.std() * np.sqrt(252) if len(returns) > 2 else None

    cumulative = (1 + returns).cumprod()
    peak = cumulative.cummax()
    drawdown = (cumulative / peak) - 1
    max_dd = drawdown.min() if not drawdown.empty else None

    rsi = safe_float(df["RSI14"].iloc[-1]) if "RSI14" in df.columns else None

    return {
        "Ostatnia cena": last,
        "Zwrot": total_return,
        "Zmienność roczna": volatility,
        "Max drawdown": max_dd,
        "RSI": rsi,
    }


def statement_to_dataframe(data):
    if not data:
        return pd.DataFrame()

    try:
        df = pd.DataFrame(data)
        df.index = [translate_key_to_polish(x) for x in df.index]
        df = df.applymap(lambda x: safe_float(x) if safe_float(x) is not None else x)
        return df
    except Exception:
        return pd.DataFrame()


def metrics_to_table(metrics):
    rows = [
        ("Aktualna cena", format_number(metrics.get("currentPrice"))),
        ("Kapitalizacja", format_number(metrics.get("marketCap"))),
        ("Wartość przedsiębiorstwa", format_number(metrics.get("enterpriseValue"))),
        ("P/E historyczne", format_number(metrics.get("trailingPE"))),
        ("P/E prognozowane", format_number(metrics.get("forwardPE"))),
        ("P/B", format_number(metrics.get("priceToBook"))),
        ("P/S", format_number(metrics.get("priceToSalesTrailing12Months"))),
        ("Marża netto", format_percent(metrics.get("profitMargins"))),
        ("Marża operacyjna", format_percent(metrics.get("operatingMargins"))),
        ("Marża brutto", format_percent(metrics.get("grossMargins"))),
        ("ROA", format_percent(metrics.get("returnOnAssets"))),
        ("ROE", format_percent(metrics.get("returnOnEquity"))),
        ("Wzrost przychodów", format_percent(metrics.get("revenueGrowth"))),
        ("Wzrost zysków", format_percent(metrics.get("earningsGrowth"))),
        ("Przychody", format_number(metrics.get("totalRevenue"))),
        ("Gotówka", format_number(metrics.get("totalCash"))),
        ("Dług", format_number(metrics.get("totalDebt"))),
        ("FCF", format_number(metrics.get("freeCashflow"))),
        ("Przepływy operacyjne", format_number(metrics.get("operatingCashflow"))),
        ("Dywidenda", format_percent(metrics.get("dividendYield"))),
        ("Beta", format_number(metrics.get("beta"))),
        ("Max 52 tyg.", format_number(metrics.get("fiftyTwoWeekHigh"))),
        ("Min 52 tyg.", format_number(metrics.get("fiftyTwoWeekLow"))),
    ]

    return pd.DataFrame(rows, columns=["Wskaźnik", "Wartość"])


# ---------------------------------------------------------
# WYKRESY
# ---------------------------------------------------------

def make_price_chart(df: pd.DataFrame, ticker: str):
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.52, 0.16, 0.16, 0.16],
        subplot_titles=(f"Wykres ceny: {ticker}", "Wolumen", "MACD", "RSI")
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

    for col, color in {
        "SMA20": "#00BFFF",
        "SMA50": "#FFA500",
        "SMA200": "#FF4B4B",
        "EMA12": "#00FF7F",
        "EMA26": "#FFD700",
        "EMA50": "#FF69B4",
    }.items():
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[col],
                    name=col,
                    line=dict(width=1.2, color=color)
                ),
                row=1,
                col=1
            )

    if "BB_UPPER" in df.columns and "BB_LOWER" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["BB_UPPER"],
                name="Bollinger góra",
                line=dict(width=1, color="rgba(180,180,180,0.5)")
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["BB_LOWER"],
                name="Bollinger dół",
                line=dict(width=1, color="rgba(180,180,180,0.5)"),
                fill="tonexty",
                fillcolor="rgba(180,180,180,0.08)"
            ),
            row=1,
            col=1
        )

    if "Volume" in df.columns:
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["Volume"],
                name="Wolumen",
                marker_color="rgba(0,191,255,0.5)"
            ),
            row=2,
            col=1
        )

    if "MACD" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MACD"],
                name="MACD",
                line=dict(width=1.2, color="#00BFFF")
            ),
            row=3,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MACD_SIGNAL"],
                name="Sygnał MACD",
                line=dict(width=1.2, color="#FFA500")
            ),
            row=3,
            col=1
        )

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["MACD_HIST"],
                name="Histogram MACD",
                marker_color="rgba(180,180,180,0.5)"
            ),
            row=3,
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
            row=4,
            col=1
        )

        fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)

    fig.update_layout(
        height=1000,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=20, r=20, t=80, b=20),
    )

    fig.update_yaxes(title_text="Cena", row=1, col=1)
    fig.update_yaxes(title_text="Wolumen", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=4, col=1)

    return fig


def make_comparison_chart(price_dict):
    fig = go.Figure()

    for ticker, df in price_dict.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue

        close = pd.to_numeric(df["Close"], errors="coerce").dropna()

        if len(close) < 2:
            continue

        normalized = close / close.iloc[0] * 100

        fig.add_trace(
            go.Scatter(
                x=normalized.index,
                y=normalized,
                mode="lines",
                name=ticker
            )
        )

    fig.update_layout(
        title="Porównanie stóp zwrotu — start = 100",
        height=650,
        template="plotly_dark",
        yaxis_title="Wartość znormalizowana",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    return fig


# ---------------------------------------------------------
# SKANER
# ---------------------------------------------------------

def scan_tickers(tickers, period="1y"):
    rows = []

    progress = st.progress(0)
    status = st.empty()

    for i, ticker in enumerate(tickers):
        status.caption(f"Skanuję: {ticker}")

        df = fetch_prices(ticker, period=period, interval="1d")

        tech = simple_signal(df) if not df.empty else {
            "signal": "BRAK DANYCH",
            "score": 0,
            "last_close": None,
            "rsi": None,
            "comment": ""
        }

        stats = performance_stats(df)
        fund = fetch_yfinance_fundamentals(ticker)
        metrics = fund.get("metrics") or {}
        fscore = fundamental_score(metrics)

        tech_score_normalized = max(0, min(100, 50 + tech.get("score", 0) * 10))
        total_score = round((fscore["score"] * 0.65) + (tech_score_normalized * 0.35), 1)

        rows.append({
            "Ticker": ticker,
            "Cena": tech.get("last_close"),
            "Sygnał techniczny": tech.get("signal"),
            "Score techniczny": tech_score_normalized,
            "Score fundamentalny": fscore["score"],
            "Ocena fundamentalna": fscore["label"],
            "Score łączny": total_score,
            "Zwrot": stats.get("Zwrot"),
            "RSI": tech.get("rsi"),
            "P/E": safe_float(metrics.get("trailingPE")),
            "P/B": safe_float(metrics.get("priceToBook")),
            "ROE": safe_float(metrics.get("returnOnEquity")),
            "Marża netto": safe_float(metrics.get("profitMargins")),
            "Kapitalizacja": safe_float(metrics.get("marketCap")),
        })

        progress.progress((i + 1) / len(tickers))

    status.empty()
    progress.empty()

    df_scan = pd.DataFrame(rows)

    if not df_scan.empty:
        df_scan = df_scan.sort_values("Score łączny", ascending=False)

    return df_scan


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

st.sidebar.title("📈 Kombajn Giełdowy")

app_mode = st.sidebar.selectbox(
    "Wybierz moduł:",
    [
        "🏠 Strona główna",
        "📈 Analiza techniczna",
        "📊 Fundamenty spółki",
        "⚖️ Porównanie spółek",
        "🔎 Skaner GPW/USA",
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
        Rozbudowana wersja aplikacji do analizy giełdowej.

        Dostępne moduły:

        • analiza techniczna z wolumenem, EMA, SMA, RSI, MACD i Bollinger Bands  
        • analiza fundamentalna z automatyczną oceną punktową  
        • porównanie kilku spółek naraz  
        • skaner GPW / USA  
        • wiadomości rynkowe  
        • eksport prostego raportu do PDF  
        """
    )

    st.success("Aplikacja gotowa do pracy.")

    st.warning(
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
                    stats = performance_stats(df_ind)

                    st.subheader(f"Wynik analizy: {ticker}")

                    c1, c2, c3, c4 = st.columns(4)

                    c1.metric("Sygnał", signal["signal"])
                    c2.metric("Cena", format_number(signal["last_close"]))
                    c3.metric("RSI", round(signal["rsi"], 2) if signal["rsi"] is not None else "brak")
                    c4.metric("Score techniczny", signal["score"])

                    st.info(signal["comment"])

                    s1, s2, s3 = st.columns(3)
                    s1.metric("Zwrot w okresie", format_percent(stats.get("Zwrot")))
                    s2.metric("Zmienność roczna", format_percent(stats.get("Zmienność roczna")))
                    s3.metric("Max drawdown", format_percent(stats.get("Max drawdown")))

                    fig = make_price_chart(df_ind, ticker)
                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("Dane tabelaryczne — ostatnie 100 wierszy"):
                        st.dataframe(df_ind.tail(100), use_container_width=True)

                    report_lines = [
                        f"Raport techniczny dla: {ticker}",
                        f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        f"Sygnał: {signal['signal']}",
                        f"Score techniczny: {signal['score']}",
                        f"Cena: {format_number(signal['last_close'])}",
                        f"RSI: {format_number(signal['rsi'])}",
                        f"Komentarz: {signal['comment']}",
                        f"Zwrot w okresie: {format_percent(stats.get('Zwrot'))}",
                        f"Zmienność roczna: {format_percent(stats.get('Zmienność roczna'))}",
                        f"Max drawdown: {format_percent(stats.get('Max drawdown'))}",
                    ]

                    pdf = make_simple_pdf(f"Raport techniczny {ticker}", report_lines)

                    st.download_button(
                        "📄 Pobierz raport PDF",
                        data=pdf,
                        file_name=f"raport_techniczny_{ticker}.pdf",
                        mime="application/pdf"
                    )

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
                pt = fund_data.get("price_target") or {}
                fscore = fundamental_score(metrics)

                st.subheader(profile.get("longName") or profile.get("shortName") or ticker_f)

                c1, c2, c3, c4, c5 = st.columns(5)

                c1.metric("Cena", format_number(metrics.get("currentPrice")))
                c2.metric("Kapitalizacja", format_number(metrics.get("marketCap")))
                c3.metric("P/E", format_number(metrics.get("trailingPE")))
                c4.metric("Dywidenda", format_percent(metrics.get("dividendYield")))
                c5.metric("Ocena", f"{fscore['score']}/100")

                if fscore["score"] >= 75:
                    st.success(f"Ocena fundamentalna: {fscore['label']} — {fscore['score']}/100")
                elif fscore["score"] >= 45:
                    st.info(f"Ocena fundamentalna: {fscore['label']} — {fscore['score']}/100")
                else:
                    st.error(f"Ocena fundamentalna: {fscore['label']} — {fscore['score']}/100")

                with st.expander("Komentarze do oceny", expanded=True):
                    if fscore["comments"]:
                        for comment in fscore["comments"]:
                            st.write(f"• {comment}")
                    else:
                        st.info("Brak wystarczających danych do pełnej oceny.")

                st.write("### Profil spółki")

                p1, p2, p3 = st.columns(3)
                p1.write(f"**Symbol:** {profile.get('symbol') or 'brak'}")
                p1.write(f"**Kraj:** {profile.get('country') or 'brak'}")
                p1.write(f"**Giełda:** {profile.get('exchange') or 'brak'}")

                p2.write(f"**Sektor:** {profile.get('sector') or 'brak'}")
                p2.write(f"**Branża:** {profile.get('industry') or 'brak'}")
                p2.write(f"**Waluta:** {profile.get('currency') or 'brak'}")

                website = profile.get("website")
                if website:
                    p3.markdown(f"**Strona:** [{website}]({website})")
                else:
                    p3.write("**Strona:** brak")

                p3.write(f"**Typ:** {profile.get('quoteType') or 'brak'}")

                with st.expander("Opis działalności", expanded=False):
                    st.write(profile.get("longBusinessSummary") or "Brak opisu.")

                st.write("### Wskaźniki finansowe")
                st.dataframe(metrics_to_table(metrics), use_container_width=True, hide_index=True)

                st.write("### Cele cenowe analityków")

                if not pt or all(v is None for v in pt.values()):
                    st.info("Brak prognoz analityków dla tej spółki.")
                else:
                    cpt1, cpt2, cpt3, cpt4 = st.columns(4)

                    cpt1.metric("Średni cel", format_number(pt.get("targetMeanPrice")))
                    cpt2.metric("Najniższy cel", format_number(pt.get("targetLowPrice")))
                    cpt3.metric("Najwyższy cel", format_number(pt.get("targetHighPrice")))
                    cpt4.metric("Liczba opinii", pt.get("numberOfAnalystOpinions") or "brak")

                    st.dataframe(
                        pd.DataFrame(
                            [
                                ("Średnia cena docelowa", format_number(pt.get("targetMeanPrice"))),
                                ("Mediana ceny docelowej", format_number(pt.get("targetMedianPrice"))),
                                ("Najniższa cena docelowa", format_number(pt.get("targetLowPrice"))),
                                ("Najwyższa cena docelowa", format_number(pt.get("targetHighPrice"))),
                                ("Rekomendacja", pt.get("recommendationKey") or "brak"),
                                ("Średnia rekomendacja", format_number(pt.get("recommendationMean"))),
                                ("Liczba opinii", pt.get("numberOfAnalystOpinions") or "brak"),
                            ],
                            columns=["Pole", "Wartość"]
                        ),
                        use_container_width=True,
                        hide_index=True
                    )

                with st.expander("Rachunek zysków i strat"):
                    income_df = statement_to_dataframe(fund_data.get("income"))
                    if income_df.empty:
                        st.info("Brak danych.")
                    else:
                        st.dataframe(income_df, use_container_width=True)

                with st.expander("Bilans"):
                    balance_df = statement_to_dataframe(fund_data.get("balance"))
                    if balance_df.empty:
                        st.info("Brak danych.")
                    else:
                        st.dataframe(balance_df, use_container_width=True)

                with st.expander("Przepływy pieniężne"):
                    cash_df = statement_to_dataframe(fund_data.get("cash"))
                    if cash_df.empty:
                        st.info("Brak danych.")
                    else:
                        st.dataframe(cash_df, use_container_width=True)

                report_lines = [
                    f"Raport fundamentalny dla: {ticker_f}",
                    f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    f"Nazwa: {profile.get('longName') or profile.get('shortName') or ticker_f}",
                    f"Sektor: {profile.get('sector') or 'brak'}",
                    f"Branza: {profile.get('industry') or 'brak'}",
                    f"Cena: {format_number(metrics.get('currentPrice'))}",
                    f"Kapitalizacja: {format_number(metrics.get('marketCap'))}",
                    f"P/E: {format_number(metrics.get('trailingPE'))}",
                    f"P/B: {format_number(metrics.get('priceToBook'))}",
                    f"ROE: {format_percent(metrics.get('returnOnEquity'))}",
                    f"Marza netto: {format_percent(metrics.get('profitMargins'))}",
                    f"Gotowka: {format_number(metrics.get('totalCash'))}",
                    f"Dlug: {format_number(metrics.get('totalDebt'))}",
                    f"Ocena fundamentalna: {fscore['label']} {fscore['score']}/100",
                    "Komentarze:",
                ]

                report_lines.extend([f"- {x}" for x in fscore["comments"]])

                pdf = make_simple_pdf(f"Raport fundamentalny {ticker_f}", report_lines)

                st.download_button(
                    "📄 Pobierz raport PDF",
                    data=pdf,
                    file_name=f"raport_fundamentalny_{ticker_f}.pdf",
                    mime="application/pdf"
                )

                with st.expander("Surowe dane JSON po polsku"):
                    st.json(polish_json(fund_data))

        except Exception:
            st.error("Nie udało się pobrać fundamentów.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())


# ---------------------------------------------------------
# PORÓWNANIE SPÓŁEK
# ---------------------------------------------------------

elif app_mode == "⚖️ Porównanie spółek":
    st.title("⚖️ Porównanie kilku spółek naraz")

    tickers_text = st.text_area(
        "Wpisz tickery po przecinku:",
        "AAPL, MSFT, NVDA, TSLA"
    )

    period_label = st.selectbox(
        "Zakres danych:",
        ["1 miesiąc", "3 miesiące", "6 miesięcy", "1 rok", "2 lata", "5 lat"],
        index=3
    )

    period_map = {
        "1 miesiąc": "1mo",
        "3 miesiące": "3mo",
        "6 miesięcy": "6mo",
        "1 rok": "1y",
        "2 lata": "2y",
        "5 lat": "5y",
    }

    period = period_map[period_label]

    if st.button("Porównaj"):
        try:
            tickers = parse_tickers(tickers_text)

            if not tickers:
                st.error("Wpisz przynajmniej jeden ticker.")
            else:
                price_dict = {}
                rows = []

                with st.spinner("Pobieranie danych..."):
                    for ticker in tickers:
                        df = fetch_prices(ticker, period=period, interval="1d")
                        if df.empty:
                            continue

                        df_ind = add_indicators(df)
                        price_dict[ticker] = df_ind

                        stats = performance_stats(df_ind)
                        sig = simple_signal(df_ind)

                        rows.append({
                            "Ticker": ticker,
                            "Cena": stats.get("Ostatnia cena"),
                            "Zwrot": stats.get("Zwrot"),
                            "Zmienność roczna": stats.get("Zmienność roczna"),
                            "Max drawdown": stats.get("Max drawdown"),
                            "RSI": stats.get("RSI"),
                            "Sygnał": sig.get("signal"),
                            "Score techniczny": sig.get("score"),
                        })

                if not price_dict:
                    st.error("Nie udało się pobrać danych dla podanych tickerów.")
                else:
                    fig = make_comparison_chart(price_dict)
                    st.plotly_chart(fig, use_container_width=True)

                    comp_df = pd.DataFrame(rows)

                    show_df = comp_df.copy()
                    for col in ["Cena", "RSI", "Score techniczny"]:
                        if col in show_df.columns:
                            show_df[col] = show_df[col].apply(lambda x: round(x, 2) if safe_float(x) is not None else None)

                    for col in ["Zwrot", "Zmienność roczna", "Max drawdown"]:
                        if col in show_df.columns:
                            show_df[col] = show_df[col].apply(format_percent)

                    st.write("### Tabela porównawcza")
                    st.dataframe(show_df, use_container_width=True, hide_index=True)

                    csv = show_df.to_csv(index=False).encode("utf-8-sig")

                    st.download_button(
                        "⬇️ Pobierz porównanie CSV",
                        data=csv,
                        file_name="porownanie_spolek.csv",
                        mime="text/csv"
                    )

                    lines = ["Porownanie spolek", f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}"]

                    for _, row in show_df.iterrows():
                        lines.append(
                            f"{row['Ticker']} | Cena: {row['Cena']} | Zwrot: {row['Zwrot']} | "
                            f"RSI: {row['RSI']} | Sygnal: {row['Sygnał']}"
                        )

                    pdf = make_simple_pdf("Porownanie spolek", lines)

                    st.download_button(
                        "📄 Pobierz raport PDF",
                        data=pdf,
                        file_name="porownanie_spolek.pdf",
                        mime="application/pdf"
                    )

        except Exception:
            st.error("Nie udało się porównać spółek.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())


# ---------------------------------------------------------
# SKANER
# ---------------------------------------------------------

elif app_mode == "🔎 Skaner GPW/USA":
    st.title("🔎 Skaner GPW/USA")

    market = st.selectbox(
        "Wybierz rynek:",
        ["USA popularne", "GPW popularne", "Własna lista"],
        index=0
    )

    if market == "USA popularne":
        default_tickers = ", ".join(USA_POPULAR)
    elif market == "GPW popularne":
        default_tickers = ", ".join(GPW_POPULAR)
    else:
        default_tickers = "AAPL, MSFT, NVDA, CDR.WA, PKO.WA"

    tickers_text = st.text_area(
        "Lista tickerów do skanowania:",
        default_tickers,
        height=130
    )

    period = st.selectbox(
        "Okres do analizy technicznej:",
        ["6mo", "1y", "2y", "5y"],
        index=1
    )

    max_count = st.slider("Maksymalna liczba spółek do skanowania:", 5, 50, 20)

    st.info(
        "Skaner pobiera dane z Yahoo Finance. Przy większej liczbie spółek może chwilę potrwać."
    )

    if st.button("Uruchom skaner"):
        try:
            tickers = parse_tickers(tickers_text)[:max_count]

            if not tickers:
                st.error("Brak tickerów do skanowania.")
            else:
                with st.spinner("Skanowanie spółek..."):
                    scan_df = scan_tickers(tickers, period=period)

                if scan_df.empty:
                    st.error("Nie udało się pobrać wyników.")
                else:
                    st.success("Skanowanie zakończone.")

                    display_df = scan_df.copy()

                    for col in ["Cena", "RSI", "P/E", "P/B"]:
                        if col in display_df.columns:
                            display_df[col] = display_df[col].apply(
                                lambda x: round(x, 2) if safe_float(x) is not None else None
                            )

                    for col in ["ROE", "Marża netto", "Zwrot"]:
                        if col in display_df.columns:
                            display_df[col] = display_df[col].apply(format_percent)

                    if "Kapitalizacja" in display_df.columns:
                        display_df["Kapitalizacja"] = display_df["Kapitalizacja"].apply(format_number)

                    st.write("### Wyniki skanera")
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                    st.write("### TOP 10 według score łącznego")
                    top_df = scan_df.head(10).copy()

                    fig = go.Figure(
                        go.Bar(
                            x=top_df["Ticker"],
                            y=top_df["Score łączny"],
                            marker_color="#00BFFF"
                        )
                    )

                    fig.update_layout(
                        template="plotly_dark",
                        height=450,
                        yaxis_title="Score łączny",
                        xaxis_title="Ticker",
                        margin=dict(l=20, r=20, t=40, b=20),
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    csv = display_df.to_csv(index=False).encode("utf-8-sig")

                    st.download_button(
                        "⬇️ Pobierz wyniki CSV",
                        data=csv,
                        file_name="wyniki_skanera.csv",
                        mime="text/csv"
                    )

                    lines = [
                        "Raport ze skanera",
                        f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        f"Liczba spolek: {len(display_df)}",
                        "TOP wyniki:"
                    ]

                    for _, row in display_df.head(15).iterrows():
                        lines.append(
                            f"{row['Ticker']} | Score laczny: {row['Score łączny']} | "
                            f"Fundamentalny: {row['Score fundamentalny']} | "
                            f"Techniczny: {row['Score techniczny']} | "
                            f"Sygnal: {row['Sygnał techniczny']}"
                        )

                    pdf = make_simple_pdf("Raport skanera", lines)

                    st.download_button(
                        "📄 Pobierz raport PDF",
                        data=pdf,
                        file_name="raport_skanera.pdf",
                        mime="application/pdf"
                    )

        except Exception:
            st.error("Skaner przerwany błędem.")
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
