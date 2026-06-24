import os
import sys
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

from plotly.subplots import make_subplots

# ============================================================
# OPCJONALNE BIBLIOTEKI AI / SEARCH
# ============================================================

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None


# ============================================================
# YFINANCE FUNDAMENTALS
# Zastępuje wcześniejszą funkcję OpenBB.
# Nazwa zostaje fetch_openbb_fundamentals, żeby nie zmieniać reszty aplikacji.
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_openbb_fundamentals(ticker: str) -> dict:
    """
    Pobiera dane fundamentalne bezpośrednio z Yahoo Finance przez yfinance.
    Funkcja zastępuje OpenBB, ale zachowuje podobną strukturę wyniku.
    """

    ticker = str(ticker).strip().upper()

    results = {
        "metrics": None,
        "profile": None,
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

        # ------------------------------------------------------------
        # INFO / PROFILE / METRICS
        # ------------------------------------------------------------
        try:
            info = stock.info

            if not isinstance(info, dict):
                info = {}

        except Exception as e:
            info = {}
            results["_errors"].append(f"info: {str(e)}")

        # Profil spółki
        results["profile"] = {
            "symbol": ticker,
            "longName": info.get("longName"),
            "shortName": info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "city": info.get("city"),
            "state": info.get("state"),
            "website": info.get("website"),
            "longBusinessSummary": info.get("longBusinessSummary"),
            "fullTimeEmployees": info.get("fullTimeEmployees"),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "quoteType": info.get("quoteType"),
            "market": info.get("market"),
        }

        # Podstawowe wskaźniki fundamentalne
        results["metrics"] = {
            "symbol": ticker,
            "marketCap": info.get("marketCap"),
            "enterpriseValue": info.get("enterpriseValue"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "pegRatio": info.get("pegRatio"),
            "priceToBook": info.get("priceToBook"),
            "bookValue": info.get("bookValue"),
            "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months"),
            "enterpriseToRevenue": info.get("enterpriseToRevenue"),
            "enterpriseToEbitda": info.get("enterpriseToEbitda"),
            "profitMargins": info.get("profitMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "grossMargins": info.get("grossMargins"),
            "ebitdaMargins": info.get("ebitdaMargins"),
            "returnOnAssets": info.get("returnOnAssets"),
            "returnOnEquity": info.get("returnOnEquity"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "grossProfits": info.get("grossProfits"),
            "totalRevenue": info.get("totalRevenue"),
            "ebitda": info.get("ebitda"),
            "netIncomeToCommon": info.get("netIncomeToCommon"),
            "totalCash": info.get("totalCash"),
            "totalDebt": info.get("totalDebt"),
            "debtToEquity": info.get("debtToEquity"),
            "currentRatio": info.get("currentRatio"),
            "quickRatio": info.get("quickRatio"),
            "freeCashflow": info.get("freeCashflow"),
            "operatingCashflow": info.get("operatingCashflow"),
            "dividendRate": info.get("dividendRate"),
            "dividendYield": info.get("dividendYield"),
            "payoutRatio": info.get("payoutRatio"),
            "beta": info.get("beta"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "fiftyDayAverage": info.get("fiftyDayAverage"),
            "twoHundredDayAverage": info.get("twoHundredDayAverage"),
            "sharesOutstanding": info.get("sharesOutstanding"),
            "floatShares": info.get("floatShares"),
            "heldPercentInsiders": info.get("heldPercentInsiders"),
            "heldPercentInstitutions": info.get("heldPercentInstitutions"),
        }

        # Price target / rekomendacje analityków
        results["price_target"] = {
            "symbol": ticker,
            "currentPrice": info.get("currentPrice"),
            "targetHighPrice": info.get("targetHighPrice"),
            "targetLowPrice": info.get("targetLowPrice"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "targetMedianPrice": info.get("targetMedianPrice"),
            "recommendationMean": info.get("recommendationMean"),
            "recommendationKey": info.get("recommendationKey"),
            "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
        }

        # ------------------------------------------------------------
        # INCOME STATEMENT
        # ------------------------------------------------------------
        try:
            income = stock.financials

            if income is not None and not income.empty:
                results["income"] = income.to_dict()
            else:
                results["income"] = None
                results["_errors"].append("income: brak danych z Yahoo Finance.")

        except Exception as e:
            results["income"] = None
            results["_errors"].append(f"income: {str(e)}")

        # ------------------------------------------------------------
        # BALANCE SHEET
        # ------------------------------------------------------------
        try:
            balance = stock.balance_sheet

            if balance is not None and not balance.empty:
                results["balance"] = balance.to_dict()
            else:
                results["balance"] = None
                results["_errors"].append("balance: brak danych z Yahoo Finance.")

        except Exception as e:
            results["balance"] = None
            results["_errors"].append(f"balance: {str(e)}")

        # ------------------------------------------------------------
        # CASH FLOW
        # ------------------------------------------------------------
        try:
            cash = stock.cashflow

            if cash is not None and not cash.empty:
                results["cash"] = cash.to_dict()
            else:
                results["cash"] = None
                results["_errors"].append("cash: brak danych z Yahoo Finance.")

        except Exception as e:
            results["cash"] = None
            results["_errors"].append(f"cash: {str(e)}")

    except Exception as e:
        results["_errors"].append(f"yfinance general error: {str(e)}")

    return results


# ============================================================
# FUNKCJA DO CZYSZCZENIA POD st.json
# ============================================================

def clean_for_json(data):
    """
    Zamienia nietypowe typy danych, np. Timestamp, NaN, numpy types,
    na format bezpieczny dla st.json.
    """
    return json.loads(json.dumps(data, default=str))


# =========================================================
# CONFIG & NEON UI
# =========================================================

st.set_page_config(
    page_title="CYBER DESK PRO - KI_ULTRA v7.0",
    page_icon="⚡",
    layout="wide"
)

st.markdown(
    """
    <style>
    body, .stApp { 
        background-color: #050816; 
        color: #E0E0FF; 
    }

    [data-testid="stSidebar"] {
        background: #0a0f24;
    }

    .stButton>button { 
        background: #0ea5e9; 
        color: white; 
        border-radius: 6px; 
        border: 1px solid #38bdf8;
        font-weight: 600;
    }

    .stButton>button:hover { 
        background: #22c55e; 
        border: 1px solid #22c55e;
    }

    .stTextInput>div>div>input { 
        background-color: #020617; 
        color: #e5e7eb; 
    }

    .stTextArea textarea { 
        background-color: #020617; 
        color: #e5e7eb; 
    }

    .metric-green {
        color: #22c55e;
        font-size: 1.15rem;
        font-weight: 700;
        text-shadow: 0 0 8px rgba(34,197,94,0.7);
    }

    .metric-yellow {
        color: #eab308;
        font-size: 1.15rem;
        font-weight: 700;
        text-shadow: 0 0 8px rgba(234,179,8,0.7);
    }

    .metric-red {
        color: #ef4444;
        font-size: 1.15rem;
        font-weight: 700;
        text-shadow: 0 0 8px rgba(239,68,68,0.7);
    }

    .small-muted {
        color: #94a3b8;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# SECRETS / API KEYS
# =========================================================

def get_secret_or_env(*names):
    """
    Obsługuje różne nazwy sekretów:
    OpenAI: OPENAI_API_KEY albo sk
    Tavily: TAVILY_API_KEY albo tavli
    """
    for name in names:
        try:
            value = st.secrets.get(name)
            if value:
                return value
        except Exception:
            pass

        try:
            value = os.getenv(name)
            if value:
                return value
        except Exception:
            pass

    return None


def get_openai_client():
    if OpenAI is None:
        return None

    key = get_secret_or_env("OPENAI_API_KEY", "sk", "OPENAI_KEY")

    if not key:
        return None

    try:
        return OpenAI(api_key=key)
    except Exception:
        return None


def get_tavily_key():
    return get_secret_or_env("TAVILY_API_KEY", "tavli", "TAVILY_KEY")


# =========================================================
# HELPERS
# =========================================================

def to_scalar(x):
    try:
        if isinstance(x, pd.Series):
            x = x.dropna()
            if x.empty:
                return np.nan
            return float(x.iloc[-1])

        if isinstance(x, (np.ndarray, list, tuple)):
            arr = np.asarray(x).ravel()
            if len(arr) == 0:
                return np.nan
            return float(arr[-1])

        return float(x)
    except Exception:
        return np.nan


def safe_last(series):
    try:
        if series is None:
            return np.nan
        series = pd.to_numeric(series, errors="coerce").dropna()
        return series.iloc[-1] if len(series) else np.nan
    except Exception:
        return np.nan


def fmt_num(value, digits=2):
    try:
        value = float(value)
        if np.isnan(value):
            return "brak"
        return f"{value:.{digits}f}"
    except Exception:
        return "brak"


def clean_for_json(obj):
    """
    Zamiana numpy/pandas types na typy JSON-friendly.
    """
    if isinstance(obj, dict):
        return {str(k): clean_for_json(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [clean_for_json(v) for v in obj]

    if isinstance(obj, tuple):
        return [clean_for_json(v) for v in obj]

    if isinstance(obj, (np.integer,)):
        return int(obj)

    if isinstance(obj, (np.floating,)):
        if np.isnan(obj):
            return None
        return float(obj)

    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()

    if pd.isna(obj):
        return None

    return obj


def normalize_yfinance_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Naprawia MultiIndex z yfinance i ujednolica kolumny:
    Open, High, Low, Close, Volume.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        level0 = list(df.columns.get_level_values(0))
        level1 = list(df.columns.get_level_values(1))
        price_cols = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}

        if any(c in price_cols for c in level0):
            df.columns = df.columns.get_level_values(0)
        elif any(c in price_cols for c in level1):
            df.columns = df.columns.get_level_values(1)
        else:
            df.columns = [
                "_".join([str(x) for x in tup if str(x) != ""])
                for tup in df.columns.to_flat_index()
            ]

    df.columns = [str(c).strip() for c in df.columns]

    rename_map = {}
    for c in df.columns:
        cl = c.lower().replace("_", " ").strip()

        if cl == "open":
            rename_map[c] = "Open"
        elif cl == "high":
            rename_map[c] = "High"
        elif cl == "low":
            rename_map[c] = "Low"
        elif cl == "close":
            rename_map[c] = "Close"
        elif cl == "adj close":
            rename_map[c] = "Adj Close"
        elif cl == "volume":
            rename_map[c] = "Volume"

    df = df.rename(columns=rename_map)
    df = df.loc[:, ~df.columns.duplicated()]

    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    if "Volume" not in df.columns:
        df["Volume"] = 0

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    return df


# =========================================================
# LOAD DATA
# =========================================================

@st.cache_data(show_spinner=False, ttl=300)
def load_price_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False
        )

        df = normalize_yfinance_df(df)
        return df

    except Exception:
        return pd.DataFrame()


# =========================================================
# INDICATORS ENGINE
# =========================================================

def compute_indicators(close, volume, high=None, low=None):
    close = pd.to_numeric(close, errors="coerce").dropna()

    if close is None or len(close) < 30:
        return {
            "rsi": np.nan,
            "ma_fast": np.nan,
            "ma_slow": np.nan,
            "upper_bb": None,
            "lower_bb": None,
            "last_upper_bb": np.nan,
            "last_lower_bb": np.nan,
            "last_macd": np.nan,
            "last_macd_signal": np.nan,
            "vol": np.nan,
            "volume": np.nan,
            "atr": np.nan,
            "adx": np.nan,
            "rvol": np.nan,
            "trend": "Unknown"
        }

    volume = pd.to_numeric(volume, errors="coerce").reindex(close.index).fillna(0)

    if high is None:
        high = close.copy()
    else:
        high = pd.to_numeric(high, errors="coerce").reindex(close.index).fillna(close)

    if low is None:
        low = close.copy()
    else:
        low = pd.to_numeric(low, errors="coerce").reindex(close.index).fillna(close)

    # RSI 14
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = to_scalar(safe_last(rsi_series))

    # MA 10/30
    ma_fast_series = close.rolling(10).mean()
    ma_slow_series = close.rolling(30).mean()
    ma_fast = to_scalar(safe_last(ma_fast_series))
    ma_slow = to_scalar(safe_last(ma_slow_series))

    # Bollinger Bands 20
    ma_bb = close.rolling(20).mean()
    std_bb = close.rolling(20).std()
    upper_bb = ma_bb + 2 * std_bb
    lower_bb = ma_bb - 2 * std_bb
    last_upper_bb = to_scalar(safe_last(upper_bb))
    last_lower_bb = to_scalar(safe_last(lower_bb))

    # MACD 12/26/9
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    last_macd = to_scalar(safe_last(macd))
    last_macd_signal = to_scalar(safe_last(macd_signal))

    # Volatility
    vol_series = close.pct_change().rolling(20).std()
    vol = to_scalar(safe_last(vol_series))

    # Volume
    last_volume = to_scalar(safe_last(volume))

    # ATR 14
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ],
        axis=1
    ).max(axis=1)

    atr = to_scalar(safe_last(tr.rolling(14).mean()))

    # ADX 14
    plus_dm_raw = high.diff()
    minus_dm_raw = -low.diff()

    plus_dm = plus_dm_raw.where((plus_dm_raw > minus_dm_raw) & (plus_dm_raw > 0), 0)
    minus_dm = minus_dm_raw.where((minus_dm_raw > plus_dm_raw) & (minus_dm_raw > 0), 0)

    atr_adx = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_adx + 1e-9))
    minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_adx + 1e-9))

    dx_series = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx = to_scalar(safe_last(dx_series.rolling(14).mean()))

    # RVOL
    avg_vol_20 = volume.rolling(20).mean()
    rvol = to_scalar(safe_last(volume / (avg_vol_20 + 1e-9)))

    # Trend
    if not np.isnan(ma_fast) and not np.isnan(ma_slow):
        if ma_fast > ma_slow:
            trend = "Uptrend"
        elif ma_fast < ma_slow:
            trend = "Downtrend"
        else:
            trend = "Sideways"
    else:
        trend = "Unknown"

    return {
        "rsi": rsi,
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
        "upper_bb": upper_bb,
        "lower_bb": lower_bb,
        "last_upper_bb": last_upper_bb,
        "last_lower_bb": last_lower_bb,
        "last_macd": last_macd,
        "last_macd_signal": last_macd_signal,
        "vol": vol,
        "volume": last_volume,
        "atr": atr,
        "adx": adx,
        "rvol": rvol,
        "trend": trend
    }


# =========================================================
# SCORING PRO
# =========================================================

def compute_scoring_pro(ind, sentiment):
    score = 0

    if ind.get("trend") == "Uptrend":
        score += 20
    elif ind.get("trend") == "Sideways":
        score += 10

    adx = ind.get("adx", np.nan)
    if not np.isnan(adx):
        if adx > 40:
            score += 20
        elif adx > 20:
            score += 10

    rsi_value = ind.get("rsi", np.nan)
    if not np.isnan(rsi_value):
        if 30 <= rsi_value <= 50:
            score += 15
        elif rsi_value < 30:
            score += 10
        elif rsi_value > 70:
            score -= 5

    rvol = ind.get("rvol", np.nan)
    if not np.isnan(rvol):
        if rvol > 1.5:
            score += 15
        elif rvol > 1.0:
            score += 10

    macd_value = ind.get("last_macd", np.nan)
    macd_signal = ind.get("last_macd_signal", np.nan)
    if not np.isnan(macd_value) and not np.isnan(macd_signal):
        if macd_value > macd_signal:
            score += 10
        else:
            score -= 5

    if not np.isnan(ind.get("last_lower_bb", np.nan)):
        score += 5

    if not np.isnan(ind.get("last_upper_bb", np.nan)):
        score += 5

    if not np.isnan(ind.get("atr", np.nan)):
        score += 5

    if sentiment == "Bullish":
        score += 15
    elif sentiment == "Bearish":
        score -= 15

    return max(0, min(int(score), 100))


# =========================================================
# TAVILY NEWS
# =========================================================

@st.cache_data(show_spinner=False, ttl=1800)
def tavily_news(query: str, max_results: int = 10):
    key = get_tavily_key()

    if not key:
        return []

    # Prefer official Tavily client
    if TavilyClient is not None:
        try:
            client = TavilyClient(api_key=key)
            response = client.search(
                query=query,
                max_results=max_results,
                search_depth="advanced"
            )
            return response.get("results", [])
        except Exception:
            pass

    # REST fallback
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            json={
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced"
            },
            timeout=15
        )

        if r.status_code != 200:
            return []

        j = r.json()
        return j.get("results", [])

    except Exception:
        return []


def fetch_news_sentiment(ticker: str):
    headlines = []

    search_query = ticker

    if ticker.upper().endswith(".WA"):
        base_ticker = ticker.split(".")[0]
        search_query = f'"{base_ticker}" stock GPW Giełda Warszawa wyniki akcje inwestorzy'

    tavily_results = tavily_news(search_query, max_results=15)

    for item in tavily_results:
        title = item.get("title", "")
        if title:
            headlines.append(title)

    try:
        news = yf.Ticker(ticker).news
        for n in news:
            title = n.get("title", "")
            if title:
                headlines.append(title)
    except Exception:
        pass

    seen = set()
    uniq = []

    for h in headlines:
        if h not in seen:
            seen.add(h)
            uniq.append(h)

    headlines = uniq

    if not headlines:
        return "Mixed", [], "Brak newsów."

    score = 0

    positive_words = [
        "beat", "strong", "growth", "upgrade", "record", "surge", "profit",
        "increase", "bullish", "raises", "outperform",
        "wzrost", "zysk", "rekord", "poprawa", "lepsze", "mocne"
    ]

    negative_words = [
        "miss", "weak", "downgrade", "fall", "plunge", "cut", "loss",
        "bearish", "lawsuit", "investigation", "warning",
        "spadek", "strata", "słabe", "gorsze", "obniżka", "ryzyko"
    ]

    for t in headlines:
        tl = t.lower()

        if any(w in tl for w in positive_words):
            score += 1

        if any(w in tl for w in negative_words):
            score -= 1

    sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"

    return sentiment, headlines[:15], ""


# =========================================================
# OPENBB ENGINE
# =========================================================

def openbb_to_df(result):
    try:
        if result is None:
            return pd.DataFrame()

        if hasattr(result, "to_df"):
            return result.to_df()

        if isinstance(result, pd.DataFrame):
            return result

        return pd.DataFrame(result)

    except Exception:
        return pd.DataFrame()


def try_openbb_call(path: str, **kwargs):
    """
    Bezpieczne dynamiczne wywołanie np.
    path='equity.fundamental.metrics'
    """
    if not OPENBB_OK or obb is None:
        raise RuntimeError(f"OpenBB niedostępny: {OPENBB_ERROR}")

    obj = obb

    for part in path.split("."):
        obj = getattr(obj, part)

    result = obj(**kwargs)
    return openbb_to_df(result)


def fetch_openbb_fundamentals(ticker: str):
    """
    Bezpieczne pobieranie fundamentów z OpenBB.
    Zwraca dane albo błędy, bez wywalania aplikacji.
    """
    data = {}
    errors = []

    if not OPENBB_OK:
        return {
            "error": f"OpenBB nie jest dostępny/import się nie udał: {OPENBB_ERROR}"
        }

    ticker = ticker.upper().strip()

    if ticker.endswith(".WA"):
        providers = ["yfinance"]
    else:
        providers = ["fmp", "yfinance", "finviz"]

    calls = [
        ("metrics", "equity.fundamental.metrics"),
        ("profile", "equity.profile"),
        ("price_target", "equity.estimates.price_target"),
        ("income", "equity.fundamental.income"),
        ("balance", "equity.fundamental.balance"),
        ("cash", "equity.fundamental.cash"),
    ]

    for name, path in calls:
        loaded = False

        for provider in providers:
            try:
                df = try_openbb_call(
                    path,
                    symbol=ticker,
                    provider=provider
                )

                if df is not None and not df.empty:
                    data[name] = {
                        "provider": provider,
                        "data": clean_for_json(df.tail(5).to_dict(orient="records"))
                    }
                    loaded = True
                    break

            except Exception as e:
                errors.append(f"{name} / {provider}: {str(e)[:250]}")

        if not loaded:
            data[name] = None

    data["_errors"] = errors[:20]

    return data


# =========================================================
# AI ANALYSIS
# =========================================================

def generate_ai_analysis(ticker, interval, ind, score, sentiment, headlines):
    client = get_openai_client()

    if client is None:
        return "Brak klienta OpenAI. Sprawdź sekret OPENAI_API_KEY albo sk."

    prompt = f"""
Jesteś profesjonalnym analitykiem technicznym. Pisz po polsku.

Przeanalizuj instrument: {ticker}
Interwał: {interval}

Dane techniczne:
- Trend: {ind.get("trend")}
- RSI: {fmt_num(ind.get("rsi"), 2)}
- MA fast 10: {fmt_num(ind.get("ma_fast"), 2)}
- MA slow 30: {fmt_num(ind.get("ma_slow"), 2)}
- MACD: {fmt_num(ind.get("last_macd"), 4)}
- MACD signal: {fmt_num(ind.get("last_macd_signal"), 4)}
- ATR: {fmt_num(ind.get("atr"), 4)}
- ADX: {fmt_num(ind.get("adx"), 2)}
- RVOL: {fmt_num(ind.get("rvol"), 2)}
- Score PRO: {score}/100
- Sentyment newsów: {sentiment}

Nagłówki newsów:
{chr(10).join(["- " + h for h in headlines[:10]])}

Przygotuj:
1. Decyzja: KUP / SPRZEDAJ / TRZYMAJ
2. Uzasadnienie techniczne
3. Interpretacja newsów
4. Ryzyko 1-10
5. Poziomy orientacyjne: entry, SL, TP1, TP2
6. Krótkie zastrzeżenie, że to nie jest rekomendacja inwestycyjna.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Jesteś profesjonalnym analitykiem rynku. Pisz konkretnie po polsku."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.25,
            max_tokens=1200
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Błąd OpenAI: {e}"


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("### ⚡ CYBER DESK PRO - KI_ULTRA v7.0")
    st.caption("Trading + OpenAI + Tavily + OpenBB 4.x")

    app_mode = st.selectbox(
        "Tryb pracy:",
        [
            "📈 Trading",
            "📰 Skaner wiadomości",
            "📊 OpenBB Fundamentals (4.x)",
            "🌍 Macro PRO"
        ]
    )

    with st.expander("Status API / bibliotek"):
        openai_key = get_secret_or_env("OPENAI_API_KEY", "sk", "OPENAI_KEY")
        tavily_key = get_secret_or_env("TAVILY_API_KEY", "tavli", "TAVILY_KEY")

        st.write("OpenAI:", "✅ klucz wykryty" if openai_key else "❌ brak klucza")
        st.write("Tavily:", "✅ klucz wykryty" if tavily_key else "❌ brak klucza")
        st.write("Tavily package:", "✅ OK" if TavilyClient is not None else "⚠️ brak tavily-python")
        st.write("Źródło danych:", "✅ Yahoo Finance / yfinance")


# =========================================================
# MODE: TRADING
# =========================================================

if app_mode == "📈 Trading":
    st.title("📈 Trading Desk PRO")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        ticker = st.text_input(
            "Ticker:",
            "AAPL",
            help="Przykłady: AAPL, MSFT, TSLA, NVDA, STX.WA, BTC-USD"
        ).upper().strip()

    with col_b:
        interval = st.selectbox(
            "Interwał:",
            ["1d", "1h", "30m", "15m", "5m"],
            index=0
        )

    with col_c:
        period = st.selectbox(
            "Zakres:",
            ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
            index=2
        )

    if st.button("🚀 Uruchom analizę"):
        with st.spinner("Pobieranie danych cenowych..."):
            df = load_price_data(ticker, period, interval)

        if df.empty:
            st.error("Brak danych z Yahoo Finance. Sprawdź ticker albo interwał.")
            st.stop()

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        ind = compute_indicators(
            close=close,
            volume=volume,
            high=high,
            low=low
        )

        with st.spinner("Pobieranie newsów i sentymentu..."):
            sentiment, headlines, msg = fetch_news_sentiment(ticker)

        score = compute_scoring_pro(ind, sentiment)

        # Metrics
        m1, m2, m3, m4, m5 = st.columns(5)

        with m1:
            st.metric("Cena", fmt_num(close.iloc[-1], 2))

        with m2:
            st.metric("Score PRO", f"{score}/100")

        with m3:
            st.metric("Trend", ind["trend"])

        with m4:
            st.metric("RSI", fmt_num(ind["rsi"], 2))

        with m5:
            st.metric("Sentyment", sentiment)

        m6, m7, m8, m9 = st.columns(4)

        with m6:
            st.metric("ADX", fmt_num(ind["adx"], 2))

        with m7:
            st.metric("RVOL", fmt_num(ind["rvol"], 2))

        with m8:
            st.metric("MACD", fmt_num(ind["last_macd"], 4))

        with m9:
            st.metric("ATR", fmt_num(ind["atr"], 4))

        # Chart
        fig = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.5, 0.15, 0.18, 0.17],
            subplot_titles=("Cena", "Wolumen", "RSI", "MACD")
        )

        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                increasing_line_color="#22c55e",
                decreasing_line_color="#ef4444",
                name="Cena"
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=close.rolling(10).mean(),
                mode="lines",
                name="MA10",
                line=dict(color="#38bdf8", width=1.2)
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=close.rolling(30).mean(),
                mode="lines",
                name="MA30",
                line=dict(color="#eab308", width=1.2)
            ),
            row=1,
            col=1
        )

        if ind["upper_bb"] is not None:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=ind["upper_bb"],
                    mode="lines",
                    name="Upper BB",
                    line=dict(color="#a855f7", width=1, dash="dot")
                ),
                row=1,
                col=1
            )

        if ind["lower_bb"] is not None:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=ind["lower_bb"],
                    mode="lines",
                    name="Lower BB",
                    line=dict(color="#a855f7", width=1, dash="dot")
                ),
                row=1,
                col=1
            )

        vol_colors = np.where(df["Close"] >= df["Open"], "#22c55e", "#ef4444")

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["Volume"],
                name="Volume",
                marker_color=vol_colors
            ),
            row=2,
            col=1
        )

        # RSI series
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=rsi_series,
                mode="lines",
                name="RSI",
                line=dict(color="#eab308", width=1.2)
            ),
            row=3,
            col=1
        )

        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=3, col=1)

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_series = ema12 - ema26
        macd_signal = macd_series.ewm(span=9, adjust=False).mean()
        macd_hist = macd_series - macd_signal

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=macd_series,
                mode="lines",
                name="MACD",
                line=dict(color="#22c55e", width=1.2)
            ),
            row=4,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=macd_signal,
                mode="lines",
                name="MACD Signal",
                line=dict(color="#ef4444", width=1.2)
            ),
            row=4,
            col=1
        )

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=macd_hist,
                name="MACD Hist",
                marker_color=np.where(macd_hist >= 0, "#22c55e", "#ef4444")
            ),
            row=4,
            col=1
        )

        fig.update_layout(
            template="plotly_dark",
            height=900,
            showlegend=True,
            xaxis_rangeslider_visible=False,
            margin=dict(l=20, r=20, t=60, b=20)
        )

        st.plotly_chart(fig, use_container_width=True)

        # News
        st.subheader("📰 Newsy")
        if headlines:
            for h in headlines:
                st.write("- " + h)
        else:
            st.info(msg or "Brak newsów.")

        # Indicator table
        with st.expander("Pokaż szczegóły wskaźników"):
            ind_display = {
                k: v for k, v in ind.items()
                if k not in ["upper_bb", "lower_bb"]
            }
            st.json(clean_for_json(ind_display))

        # AI
        st.subheader("🤖 Analiza AI")

        if st.button("Wygeneruj analizę AI"):
            with st.spinner("Generowanie analizy AI..."):
                ai_text = generate_ai_analysis(
                    ticker=ticker,
                    interval=interval,
                    ind=ind,
                    score=score,
                    sentiment=sentiment,
                    headlines=headlines
                )

            st.markdown(ai_text)


# =========================================================
# MODE: NEWS SCANNER
# =========================================================

elif app_mode == "📰 Skaner wiadomości":
    st.title("📰 Skaner wiadomości")

    ticker_n = st.text_input(
        "Ticker do newsów:",
        "AAPL",
        key="news_ticker_input"
    ).upper().strip()

    if st.button("Pobierz newsy", key="fetch_news_button"):
        if not ticker_n:
            st.error("Wpisz poprawny ticker.")
        else:
            with st.spinner("Pobieranie newsów..."):
                try:
                    sentiment, headlines, msg = fetch_news_sentiment(ticker_n)

                    st.metric("Sentyment", sentiment)

                    if headlines:
                        for h in headlines:
                            st.write("- " + str(h))
                    else:
                        st.info(msg or "Brak newsów.")

                except Exception as e:
                    st.error(f"Błąd pobierania newsów: {e}")


# =========================================================
# MODE: YFINANCE FUNDAMENTALS
# =========================================================

elif app_mode in ["📊 Yahoo Finance Fundamentals", "📊 OpenBB Fundamentals (4.x)"]:
    st.title("📊 Dane fundamentalne z Yahoo Finance")

    st.info(
        "Ten moduł korzysta bezpośrednio z Yahoo Finance przez yfinance. "
        "OpenBB został usunięty dla większej stabilności na Streamlit Cloud."
    )

    st.caption(
        "Przykłady tickerów: AAPL, MSFT, NVDA, TSLA, BTC-USD. "
        "Dla GPW używaj sufiksu .WA, np. CDR.WA, PKO.WA, KGH.WA."
    )

    ticker_f = st.text_input(
        "Wpisz ticker do fundamentów:",
        "AAPL",
        key="fundamental_ticker_input"
    ).upper().strip()

    if "fundamental_data" not in st.session_state:
        st.session_state.fundamental_data = None

    if "fundamental_ticker" not in st.session_state:
        st.session_state.fundamental_ticker = None

    if st.button("Pobierz Fundamenty", key="fetch_fundamentals_button"):
        if not ticker_f:
            st.error("Wpisz poprawny ticker.")
        else:
            with st.spinner("Pobieranie danych fundamentalnych z Yahoo Finance..."):
                try:
                    fund_data = fetch_yfinance_fundamentals(ticker_f)

                    st.session_state.fundamental_data = fund_data
                    st.session_state.fundamental_ticker = ticker_f

                except Exception as e:
                    st.session_state.fundamental_data = None
                    st.session_state.fundamental_ticker = None
                    st.error(f"Błąd pobierania fundamentów: {e}")

    if st.session_state.fundamental_data is not None:
        fund_data = st.session_state.fundamental_data

        st.subheader(f"Fundamenty: {st.session_state.fundamental_ticker}")

        errors = fund_data.get("_errors", [])

        if errors:
            with st.expander("Ostrzeżenia / braki danych"):
                for err in errors:
                    st.warning(str(err))

        metrics = fund_data.get("metrics") or {}
        profile = fund_data.get("profile") or {}
        price_target = fund_data.get("price_target") or {}

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Cena",
                metrics.get("currentPrice") if metrics.get("currentPrice") is not None else "brak"
            )

        with col2:
            st.metric(
                "Market Cap",
                metrics.get("marketCap") if metrics.get("marketCap") is not None else "brak"
            )

        with col3:
            st.metric(
                "P/E",
                metrics.get("trailingPE") if metrics.get("trailingPE") is not None else "brak"
            )

        st.write("### Profil spółki")
        st.json(clean_for_json(profile))

        st.write("### Wskaźniki")
        st.json(clean_for_json(metrics))

        st.write("### Price Target / Analitycy")
        st.json(clean_for_json(price_target))

        with st.expander("Rachunek zysków i strat"):
            st.json(clean_for_json(fund_data.get("income")))

        with st.expander("Bilans"):
            st.json(clean_for_json(fund_data.get("balance")))

        with st.expander("Cash Flow"):
            st.json(clean_for_json(fund_data.get("cash")))

        with st.expander("Pełne dane JSON"):
            st.json(clean_for_json(fund_data))

elif app_mode == "📊 OpenBB Fundamentals (4.x)":
    st.title("📊 Dane fundamentalne z Yahoo Finance")

    st.info(
        "Ten moduł korzysta bezpośrednio z Yahoo Finance przez bibliotekę yfinance. "
        "OpenBB został usunięty dla większej stabilności na Streamlit Cloud."
    )

    st.caption(
        "Przykłady tickerów: AAPL, MSFT, NVDA, TSLA, BTC-USD. "
        "Dla GPW używaj sufiksu .WA, np. CDR.WA, PKO.WA, KGH.WA."
    )

    ticker_f = st.text_input(
        "Wpisz ticker do fundamentów:",
        "AAPL",
        key="fundamental_ticker_input"
    ).upper().strip()

    if "fundamental_data" not in st.session_state:
        st.session_state.fundamental_data = None

    if "fundamental_ticker" not in st.session_state:
        st.session_state.fundamental_ticker = None

    if st.button("Pobierz fundamenty", key="fetch_fundamentals_button"):
        if not ticker_f:
            st.error("Wpisz poprawny ticker.")
        else:
            with st.spinner("Pobieranie danych fundamentalnych z Yahoo Finance..."):
                fund_data = fetch_openbb_fundamentals(ticker_f)

            st.session_state.fundamental_data = fund_data
            st.session_state.fundamental_ticker = ticker_f
if st.session_state.fundamental_data is not None:
    fund_data = st.session_state.fundamental_data
        st.subheader(f"Fundamenty: {st.session_state.fundamental_ticker}")

        errors = fund_data.get("_errors", [])

        if errors:
            with st.expander("Ostrzeżenia / braki danych"):
                for err in errors:
                    st.warning(err)

        col1, col2, col3 = st.columns(3)

        metrics = fund_data.get("metrics") or {}
        profile = fund_data.get("profile") or {}
        price_target = fund_data.get("price_target") or {}

        with col1:
            st.metric(
                "Cena",
                metrics.get("currentPrice") or "brak"
            )

        with col2:
            st.metric(
                "Market Cap",
                metrics.get("marketCap") or "brak"
            )

        with col3:
            st.metric(
                "P/E",
                metrics.get("trailingPE") or "brak"
            )

        st.write("### Profil spółki")
        st.json(clean_for_json(profile))

        st.write("### Wskaźniki")
        st.json(clean_for_json(metrics))

        st.write("### Price Target / Analitycy")
        st.json(clean_for_json(price_target))

        with st.expander("Rachunek zysków i strat"):
            st.json(clean_for_json(fund_data.get("income")))

        with st.expander("Bilans"):
            st.json(clean_for_json(fund_data.get("balance")))

        with st.expander("Cash Flow"):
            st.json(clean_for_json(fund_data.get("cash")))

        with st.expander("Pełne dane JSON"):
            st.json(clean_for_json(fund_data))
# =========================================================
# MODE: MACRO
# =========================================================

elif app_mode == "🌍 Macro PRO":
    st.title("🌍 Macro PRO")

    st.caption("Moduł makro oparty o proxy instrumenty z Yahoo Finance.")

    macro_symbols = {
        "S&P 500": "^GSPC",
        "Nasdaq 100": "^NDX",
        "VIX": "^VIX",
        "US 10Y Yield": "^TNX",
        "Dollar Index": "DX-Y.NYB",
        "Gold": "GC=F",
        "Oil WTI": "CL=F",
        "Bitcoin": "BTC-USD"
    }

    selected = st.multiselect(
        "Wybierz instrumenty makro:",
        list(macro_symbols.keys()),
        default=["S&P 500", "VIX", "US 10Y Yield", "Dollar Index", "Gold"]
    )

    period_macro = st.selectbox(
        "Zakres:",
        ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
        index=3
    )

    if st.button("Pobierz dane makro"):
        fig = go.Figure()

        table_rows = []

        for name in selected:
            symbol = macro_symbols[name]

            df_m = load_price_data(symbol, period_macro, "1d")

            if df_m.empty:
                table_rows.append(
                    {
                        "Instrument": name,
                        "Ticker": symbol,
                        "Status": "Brak danych"
                    }
                )
                continue

            close = df_m["Close"].dropna()

            if close.empty:
                continue

            normalized = close / close.iloc[0] * 100

            fig.add_trace(
                go.Scatter(
                    x=normalized.index,
                    y=normalized,
                    mode="lines",
                    name=name
                )
            )

            change_pct = (close.iloc[-1] / close.iloc[0] - 1) * 100

            table_rows.append(
                {
                    "Instrument": name,
                    "Ticker": symbol,
                    "Ostatnia wartość": fmt_num(close.iloc[-1], 2),
                    "Zmiana %": fmt_num(change_pct, 2),
                    "Status": "OK"
                }
            )

        fig.update_layout(
            template="plotly_dark",
            title="Makro proxy - indeksowane do 100",
            height=650,
            yaxis_title="Indeks 100 = początek okresu"
        )

        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            pd.DataFrame(table_rows),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# FOOTER
# =========================================================

st.markdown(
    """
    <hr style='border: 1px solid #1f2937; margin-top: 40px;'>
    <div style='text-align: center; color: #6b7280; font-size: 0.8rem;'>
    CYBER DESK PRO - KI_ULTRA v7.0 • Trading / News / OpenBB / Macro
    <br>
    Narzędzie edukacyjne i analityczne. Nie stanowi rekomendacji inwestycyjnej.
    </div>
    """,
    unsafe_allow_html=True
)

