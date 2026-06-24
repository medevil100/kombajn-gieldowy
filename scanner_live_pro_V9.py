
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

from openai import OpenAI
from tavily import TavilyClient
from typing import Optional, Dict, Any, Tuple, List


# ============================
# CONFIG
# ============================

st.set_page_config(
    page_title="💠 CYBER DESK PRO",
    page_icon="💠",
    layout="wide"
)

NEON_CSS = """
<style>
body { background-color: #020617; color: #E5E7EB; }
section.main { background: radial-gradient(circle at top, #0f172a 0, #020617 55%); }
.block-container { padding-top: 0.8rem; }
h1, h2, h3, h4 { color: #38bdf8 !important; }
.stMetric label, .stMetric span { color: #e5e7eb !important; }
div[data-testid="stMetricValue"] { color: #22c55e !important; }
.stButton>button {
    background: linear-gradient(90deg,#22c55e,#0ea5e9);
    border: none;
    color: #0b1120;
    font-weight: 700;
}
.stButton>button:hover {
    background: linear-gradient(90deg,#0ea5e9,#22c55e);
}
</style>
"""
st.markdown(NEON_CSS, unsafe_allow_html=True)

st.title("💠 CYBER DESK PRO — Czat + Trading + Skaner")
st.caption(
    "GPT‑4o + Tavily + yfinance · narzędzie informacyjne, nie rekomendacja inwestycyjna."
)


# ============================
# API KEYS / CLIENTS
# ============================

try:
    OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
    TAVILY_KEY = st.secrets["TAVILY_API_KEY"]

    openai_client = OpenAI(api_key=OPENAI_KEY)
    tavily_client = TavilyClient(api_key=TAVILY_KEY)

except Exception:
    st.error(
        "❌ Brak kluczy w `.streamlit/secrets.toml`. "
        "Wymagane: `OPENAI_API_KEY`, `TAVILY_API_KEY`."
    )
    st.stop()


# ============================
# SESSION STATE
# ============================

if "watchlist_raw" not in st.session_state:
    st.session_state.watchlist_raw = ""

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "scanner_input" not in st.session_state:
    st.session_state.scanner_input = ""

if "engine_data" not in st.session_state:
    st.session_state.engine_data = None

if "last_main_ticker" not in st.session_state:
    st.session_state.last_main_ticker = ""


# ============================
# CORE HELPERS
# ============================

def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def detect_market(ticker: str) -> Tuple[str, str]:
    ticker = normalize_ticker(ticker)
    if ticker.endswith(".WA"):
        return "GPW", "PLN"
    return "USA/Global", "USD"


def validate_yahoo_interval_period(interval: str, period: str) -> Tuple[bool, str]:
    """
    Yahoo Finance ma ograniczenia dla interwałów intraday.
    """
    if interval == "1m" and period not in ["1d", "5d"]:
        return False, "Dla interwału 1m wybierz okres 1d lub 5d."

    if interval in ["5m", "15m"] and period == "3mo":
        return False, "Dla interwałów 5m/15m okres 3mo bywa niedostępny w Yahoo. Wybierz 1d, 5d lub 1mo."

    return True, ""


@st.cache_data(ttl=60, show_spinner=False)
def get_price_data_cached(
    ticker: str,
    interval: str = "5m",
    period: str = "5d"
) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
    """
    Cache 60 sekund: ceny są dość świeże, ale nie przeciążamy Yahoo.
    """
    ticker = normalize_ticker(ticker)

    try:
        df = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            prepost=False,
            actions=False,
            auto_adjust=False
        )

        if df is None or df.empty:
            return None, None

        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        if df.empty:
            return None, None

        last = df.iloc[-1]

        price_data = {
            "price": float(last["Close"]),
            "open": float(last["Open"]),
            "high": float(last["High"]),
            "low": float(last["Low"]),
            "volume": int(last["Volume"]) if pd.notna(last.get("Volume", np.nan)) else 0
        }

        return df, price_data

    except Exception:
        return None, None


def get_price_data(
    ticker: str,
    interval: str = "5m",
    period: str = "5d"
) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
    return get_price_data_cached(ticker, interval, period)


def safe_float(val):
    try:
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None


def compute_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Liczy wskaźniki częściowo.
    Nie blokuje wszystkiego, jeśli jest mniej niż 50 świec.
    """
    result = {
        "rsi": None,
        "ma20": None,
        "ma50": None,
        "macd": None,
        "signal": None,
        "hv": None,
        "bb_upper": None,
        "bb_lower": None,
        "trend": "NOT ENOUGH DATA"
    }

    if df is None or df.empty or "Close" not in df.columns:
        return result

    close = df["Close"].dropna()

    if len(close) < 2:
        return result

    # RSI
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        result["rsi"] = safe_float(rsi.iloc[-1])

    # MA20
    if len(close) >= 20:
        ma20 = close.rolling(20).mean()
        result["ma20"] = safe_float(ma20.iloc[-1])

        std20 = close.rolling(20).std()
        result["bb_upper"] = safe_float((ma20 + 2 * std20).iloc[-1])
        result["bb_lower"] = safe_float((ma20 - 2 * std20).iloc[-1])

        log_ret = np.log(close / close.shift(1))
        hv = log_ret.rolling(20).std() * np.sqrt(252)
        result["hv"] = safe_float(hv.iloc[-1])

    # MA50
    if len(close) >= 50:
        ma50 = close.rolling(50).mean()
        result["ma50"] = safe_float(ma50.iloc[-1])

    # MACD
    if len(close) >= 26:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        result["macd"] = safe_float(macd.iloc[-1])
        result["signal"] = safe_float(signal.iloc[-1])

    # Trend
    if result["ma20"] is not None and result["ma50"] is not None:
        if result["ma20"] > result["ma50"]:
            result["trend"] = "UP"
        elif result["ma20"] < result["ma50"]:
            result["trend"] = "DOWN"
        else:
            result["trend"] = "FLAT"
    elif result["ma20"] is not None:
        last_price = safe_float(close.iloc[-1])
        if last_price is not None:
            if last_price > result["ma20"]:
                result["trend"] = "SHORT UP / ABOVE MA20"
            elif last_price < result["ma20"]:
                result["trend"] = "SHORT DOWN / BELOW MA20"
            else:
                result["trend"] = "FLAT NEAR MA20"

    return result


def plot_candles(df: pd.DataFrame, ticker: str):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Cena"
    ))

    # Opcjonalnie MA20/MA50 na wykresie, jeśli jest dość danych
    if len(df) >= 20:
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df["Close"].rolling(20).mean(),
            mode="lines",
            name="MA20",
            line=dict(color="#38bdf8", width=1)
        ))

    if len(df) >= 50:
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df["Close"].rolling(50).mean(),
            mode="lines",
            name="MA50",
            line=dict(color="#f97316", width=1)
        ))

    fig.update_layout(
        title=f"{ticker} — wykres",
        height=440,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
        font=dict(color="#E5E7EB"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    st.plotly_chart(fig, use_container_width=True)


def format_indicator_value(v):
    if v is None:
        return "brak"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


# ============================
# TAVILY NEWS
# ============================

def build_news_query(ticker: str) -> str:
    ticker = normalize_ticker(ticker)

    if ticker.endswith(".WA"):
        base = ticker.replace(".WA", "")
        return (
            f"{base} GPW akcje najnowsze informacje wyniki ESPI PAP Biznes "
            f"komunikat spółki kurs akcji inwestorzy"
        )

    return (
        f"{ticker} stock latest important news earnings guidance SEC filing "
        f"analyst rating price moving event"
    )


@st.cache_data(ttl=600, show_spinner=False)
def tavily_news_for_ticker_cached(ticker: str, max_results: int = 6) -> str:
    """
    Tavily: możliwie świeże informacje.
    Cache 10 minut, bo newsy nie muszą być pobierane przy każdym rerunie.
    """
    ticker = normalize_ticker(ticker)

    if not ticker:
        return "Brak tickera — nie można pobrać newsów."

    query = build_news_query(ticker)

    try:
        # Pierwsza próba: tryb news z ostatnich 7 dni.
        try:
            res = tavily_client.search(
                query=query,
                search_depth="advanced",
                topic="news",
                days=7,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False
            )
        except TypeError:
            # Fallback dla starszej wersji tavily-python, gdy topic/days nie są obsługiwane.
            res = tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=True
            )

        items = res.get("results", []) if isinstance(res, dict) else []
        answer = res.get("answer", "") if isinstance(res, dict) else ""

        # Druga próba: jeśli news mode nic nie zwróci, robimy zwykły advanced search.
        if not items:
            res = tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=True,
                include_raw_content=False
            )
            items = res.get("results", []) if isinstance(res, dict) else []
            answer = res.get("answer", "") if isinstance(res, dict) else ""

        if not items:
            return "Brak świeżych newsów z Tavily dla tego tickera."

        lines = []

        if answer:
            lines.append(f"**Podsumowanie Tavily:** {answer}")
            lines.append("")

        lines.append("**Najnowsze znalezione informacje:**")

        for it in items:
            title = it.get("title", "Bez tytułu")
            url = it.get("url", "")
            content = it.get("content", "") or ""
            published = (
                it.get("published_date")
                or it.get("publishedDate")
                or it.get("date")
                or ""
            )

            snippet = content[:260].replace("\n", " ").strip()

            if published:
                line = f"- **{title}** ({published}) — {snippet}"
            else:
                line = f"- **{title}** — {snippet}"

            if url:
                line += f"  \n  Źródło: {url}"

            lines.append(line)

        return "\n\n".join(lines)

    except Exception as e:
        return f"Błąd Tavily: {str(e)}"


def tavily_news_for_ticker(ticker: str, max_results: int = 6) -> str:
    return tavily_news_for_ticker_cached(ticker, max_results)


# ============================
# OPENAI HELPERS
# ============================

def openai_chat(messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
    try:
        r = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Błąd OpenAI: {str(e)}"


def ai_live_signal(ticker: str, price: float, indicators: Dict[str, Any]) -> str:
    prompt = f"""
Jesteś doświadczonym daytraderem i analitykiem technicznym.

Dane:
Ticker: {ticker}
Cena: {price}
RSI: {indicators.get("rsi")}
MA20: {indicators.get("ma20")}
MA50: {indicators.get("ma50")}
MACD: {indicators.get("macd")}
Signal: {indicators.get("signal")}
HV: {indicators.get("hv")}
BB_UPPER: {indicators.get("bb_upper")}
BB_LOWER: {indicators.get("bb_lower")}
TREND: {indicators.get("trend")}

Zwróć po polsku:
1. Sygnał: BUY / SELL / FLAT
2. Krótkie uzasadnienie 1-3 zdania.
3. Poziom pewności: niski / średni / wysoki.

Zasady:
- nie wymyślaj danych,
- jeśli danych jest mało, napisz to,
- to nie jest rekomendacja inwestycyjna.
"""

    messages = [
        {
            "role": "system",
            "content": "Odpowiadasz krótko, konkretnie, po polsku. Nie zmyślasz danych."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    return openai_chat(messages, temperature=0.25)


def ai_scenarios(
    ticker: str,
    price: float,
    indicators: Dict[str, Any],
    news_text: str
) -> str:
    prompt = f"""
Przygotuj 3 scenariusze dla {ticker} na kolejne 7 dni.

Cena: {price}

Dane techniczne:
{indicators}

Świeże newsy:
{news_text}

Format odpowiedzi:

### BULL
- Warunek aktywacji:
- Możliwy ruch:
- Co obserwować:

### BASE
- Warunek:
- Możliwy ruch:
- Co obserwować:

### BEAR
- Warunek aktywacji:
- Możliwy ruch:
- Co obserwować:

Zasady:
- pisz po polsku,
- nie wymyślaj konkretnych poziomów cenowych, jeśli nie wynikają z danych,
- jeżeli newsy są ubogie, zaznacz to,
- to nie jest rekomendacja inwestycyjna.
"""

    messages = [
        {
            "role": "system",
            "content": "Jesteś analitykiem finansowym. Tworzysz scenariusze, nie rekomendacje."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    return openai_chat(messages, temperature=0.35)


def build_tech_context_from_engine(
    engine: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], str]:
    if not engine:
        return None, "Brak danych technicznych z kombajnu."

    ticker = engine.get("ticker")
    price_data = engine.get("price_data", {})
    ind = engine.get("indicators", {})

    if not ticker or not price_data:
        return None, "Brak pełnych danych technicznych z kombajnu."

    tech_part = f"""
Dane techniczne z kombajnu:
- Ticker: {ticker}
- Interwał: {engine.get("interval")}
- Okres: {engine.get("period")}
- Cena: {price_data.get("price")}
- Open: {price_data.get("open")}
- High: {price_data.get("high")}
- Low: {price_data.get("low")}
- Volume: {price_data.get("volume")}
- RSI: {ind.get("rsi")}
- MA20: {ind.get("ma20")}
- MA50: {ind.get("ma50")}
- MACD: {ind.get("macd")}
- Signal: {ind.get("signal")}
- HV: {ind.get("hv")}
- BB Upper: {ind.get("bb_upper")}
- BB Lower: {ind.get("bb_lower")}
- Trend: {ind.get("trend")}
"""
    return ticker, tech_part


def ai_chat_answer(user_msg: str, ticker: Optional[str]) -> str:
    ticker = normalize_ticker(ticker) if ticker else None

    engine = st.session_state.get("engine_data")
    engine_ticker, engine_tech = build_tech_context_from_engine(engine)

    eff_ticker = ticker or engine_ticker

    tech_part = ""

    # Jeśli użytkownik pyta o ticker zgodny z kombajnem albo nie podał tickera, używamy kombajnu.
    if engine and engine_ticker and (ticker is None or ticker == engine_ticker):
        tech_part = engine_tech

    # Fallback: pobierz dane dzienne dla tickera.
    elif ticker:
        df, price_data = get_price_data(ticker, interval="1d", period="3mo")
        if df is not None and price_data is not None and not df.empty:
            ind = compute_indicators(df)
            tech_part = f"""
Dane techniczne fallback z Yahoo:
- Ticker: {ticker}
- Interwał: 1d
- Okres: 3mo
- Cena: {price_data.get("price")}
- Open: {price_data.get("open")}
- High: {price_data.get("high")}
- Low: {price_data.get("low")}
- Volume: {price_data.get("volume")}
- RSI: {ind.get("rsi")}
- MA20: {ind.get("ma20")}
- MA50: {ind.get("ma50")}
- MACD: {ind.get("macd")}
- Signal: {ind.get("signal")}
- HV: {ind.get("hv")}
- BB Upper: {ind.get("bb_upper")}
- BB Lower: {ind.get("bb_lower")}
- Trend: {ind.get("trend")}
"""
        else:
            tech_part = "Dane techniczne są ograniczone — Yahoo Finance nie zwróciło pełnych danych."
    else:
        tech_part = "Brak tickera — analiza techniczna ograniczona."

    if eff_ticker:
        news_part = tavily_news_for_ticker(eff_ticker, max_results=6)
    else:
        news_part = "Brak tickera — nie pobieram newsów spółki."

    context_prompt = f"""
Pytanie użytkownika:
{user_msg}

Ticker analizowany: {eff_ticker}

Świeże informacje z Tavily:
{news_part}

{tech_part}

Zasady:
- odpowiadasz po polsku,
- konkretnie i praktycznie,
- jeśli dane są pełne, użyj ich,
- jeśli dane są częściowe, powiedz to jasno,
- nie wymyślaj liczb spoza danych,
- odróżniaj fakty od scenariuszy,
- nie używaj sformułowania "brak Trading Engine",
- nie dawaj gwarancji zysku,
- to nie jest rekomendacja inwestycyjna.
"""

    messages = [
        {
            "role": "system",
            "content": (
                "Jesteś polskojęzycznym analitykiem finansowym. "
                "Analizujesz dane techniczne, newsy i ryzyko. "
                "Nie zmyślasz danych."
            )
        }
    ]

    # Historia rozmowy — ostatnie 10 wpisów, żeby nie pompować tokenów.
    for speaker, msg in st.session_state.chat_history[-10:]:
        if speaker == "Ty":
            messages.append({"role": "user", "content": msg})
        else:
            messages.append({"role": "assistant", "content": msg})

    messages.append({"role": "user", "content": context_prompt})

    return openai_chat(messages, temperature=0.3)


# ============================
# SCANNER HELPERS
# ============================

def extract_ticker_df(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Naprawia problem yfinance:
    - przy wielu tickerach zwykle jest MultiIndex,
    - przy jednym tickerze zwykle są zwykłe kolumny.
    """
    ticker = normalize_ticker(ticker)

    if data is None or data.empty:
        return pd.DataFrame()

    try:
        if isinstance(data.columns, pd.MultiIndex):
            level0 = list(data.columns.get_level_values(0))
            level1 = list(data.columns.get_level_values(1))

            if ticker in level0:
                return data[ticker].dropna()

            if ticker in level1:
                return data.xs(ticker, level=1, axis=1).dropna()

            return pd.DataFrame()

        # Single ticker case
        needed = {"Open", "High", "Low", "Close", "Volume"}
        if needed.issubset(set(data.columns)):
            return data.dropna()

        return pd.DataFrame()

    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def download_scanner_data(tickers_tuple: Tuple[str, ...]) -> pd.DataFrame:
    tickers_list = list(tickers_tuple)

    data = yf.download(
        tickers=" ".join(tickers_list),
        period="3mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False
    )

    return data


def scan_tickers(tickers_list: List[str]) -> pd.DataFrame:
    if not tickers_list:
        return pd.DataFrame()

    tickers_list = [normalize_ticker(t) for t in tickers_list if t.strip()]
    tickers_list = list(dict.fromkeys(tickers_list))  # remove duplicates, keep order

    rows = []

    # Próba zbiorcza przez yf.download
    try:
        data = download_scanner_data(tuple(tickers_list))

        for t in tickers_list:
            try:
                df_s = extract_ticker_df(data, t)

                if df_s.empty:
                    continue

                if "Close" not in df_s.columns or "Volume" not in df_s.columns:
                    continue

                df_s = df_s.dropna(subset=["Close"])

                if df_s.empty:
                    continue

                last_close = safe_float(df_s["Close"].iloc[-1])
                if last_close is None:
                    continue

                avg_vol = df_s["Volume"].tail(20).mean()
                dollar_vol = float(avg_vol * last_close) if pd.notna(avg_vol) else 0.0

                ind_s = compute_indicators(df_s)

                score = 0.0

                # RSI: najlepsza punktacja wokół 50-60, kara za skrajności.
                if ind_s.get("rsi") is not None:
                    score += max(0, 70 - abs(55 - ind_s["rsi"]))

                # Płynność
                score += min(dollar_vol / 1_000_000, 50)

                # Trend bonus
                if ind_s.get("trend") == "UP":
                    score += 10
                elif ind_s.get("trend") == "SHORT UP / ABOVE MA20":
                    score += 5

                rows.append({
                    "Ticker": t,
                    "Price": last_close,
                    "RSI": ind_s.get("rsi"),
                    "Trend": ind_s.get("trend"),
                    "HV": ind_s.get("hv"),
                    "DollarVol20": dollar_vol,
                    "Score": score
                })

            except Exception:
                continue

    except Exception:
        # Fallback pojedynczy
        for t in tickers_list:
            try:
                df_s, price_s = get_price_data(t, interval="1d", period="3mo")
                if df_s is None or price_s is None or df_s.empty:
                    continue

                ind_s = compute_indicators(df_s)

                avg_vol = df_s["Volume"].tail(20).mean()
                dollar_vol = avg_vol * price_s["price"] if pd.notna(avg_vol) else 0.0

                score = 0.0

                if ind_s.get("rsi") is not None:
                    score += max(0, 70 - abs(55 - ind_s["rsi"]))

                score += min(dollar_vol / 1_000_000, 50)

                if ind_s.get("trend") == "UP":
                    score += 10
                elif ind_s.get("trend") == "SHORT UP / ABOVE MA20":
                    score += 5

                rows.append({
                    "Ticker": t,
                    "Price": price_s["price"],
                    "RSI": ind_s.get("rsi"),
                    "Trend": ind_s.get("trend"),
                    "HV": ind_s.get("hv"),
                    "DollarVol20": dollar_vol,
                    "Score": score
                })

            except Exception:
                continue

    if not rows:
        return pd.DataFrame()

    df_scan = pd.DataFrame(rows)
    df_scan = df_scan.sort_values("Score", ascending=False)

    return df_scan.head(10)


def color_rows(row):
    score = row["Score"]
    if score >= 80:
        color = "background-color: rgba(22,163,74,0.35);"
    elif score >= 50:
        color = "background-color: rgba(234,179,8,0.35);"
    else:
        color = "background-color: rgba(220,38,38,0.35);"
    return [color] * len(row)


# ============================
# SIDEBAR
# ============================

with st.sidebar:
    st.markdown("### 💠 Tryb pracy")

    mode = st.radio(
        "Wybierz moduł:",
        ["📈 Kombajn tradingowy", "🧪 Skaner spółek", "🤖 Czat AI"],
        index=0
    )

    st.markdown("---")
    st.markdown("### 📜 Watchlista")

    wl_raw = st.text_area(
        "Tickery, oddzielone przecinkami:",
        value=st.session_state.watchlist_raw,
        height=100
    )

    st.session_state.watchlist_raw = wl_raw
    wl_list = [normalize_ticker(t) for t in wl_raw.split(",") if t.strip()]

    active_from_list = None

    if wl_list:
        active_from_list = st.selectbox("Aktywny ticker z listy:", wl_list)

    st.markdown("---")
    st.markdown("### ⏱ Odświeżanie")
    st.caption("Ceny cache: 60 sek. Newsy Tavily cache: 10 min.")


# ============================
# MODULE 1 — TRADING ENGINE
# ============================

if mode == "📈 Kombajn tradingowy":
    col_top1, col_top2, col_top3 = st.columns([2, 1, 1])

    with col_top1:
        default_ticker = active_from_list if active_from_list else st.session_state.last_main_ticker
        main_ticker = st.text_input(
            "Ticker USA / GPW .WA / inne:",
            value=default_ticker
        )
        main_ticker = normalize_ticker(main_ticker)

    with col_top2:
        interval = st.selectbox(
            "Interwał:",
            ["1m", "5m", "15m", "1h", "1d"],
            index=1
        )

    with col_top3:
        period = st.selectbox(
            "Okres:",
            ["1d", "5d", "1mo", "3mo"],
            index=1
        )

    run_btn = st.button("🚀 Odśwież dane")

    if run_btn:
        if not main_ticker:
            st.warning("Podaj ticker.")
        else:
            valid, msg = validate_yahoo_interval_period(interval, period)

            if not valid:
                st.warning(msg)
            else:
                with st.spinner("Pobieram dane, newsy i generuję analizę AI..."):
                    market, currency = detect_market(main_ticker)
                    df, price_data = get_price_data(main_ticker, interval=interval, period=period)

                    if df is None or price_data is None or df.empty:
                        st.error("❌ Brak danych z Yahoo Finance.")
                    else:
                        indicators = compute_indicators(df)
                        news_text = tavily_news_for_ticker(main_ticker, max_results=6)
                        live_sig = ai_live_signal(main_ticker, price_data["price"], indicators)
                        scen = ai_scenarios(main_ticker, price_data["price"], indicators, news_text)

                        st.session_state.last_main_ticker = main_ticker

                        st.session_state.engine_data = {
                            "ticker": main_ticker,
                            "market": market,
                            "currency": currency,
                            "interval": interval,
                            "period": period,
                            "price_data": price_data,
                            "indicators": indicators,
                            "news_text": news_text,
                            "live_signal": live_sig,
                            "scenarios": scen,
                            "df": df
                        }

    engine = st.session_state.get("engine_data")

    if engine:
        ticker = engine["ticker"]
        market = engine.get("market", "")
        currency = engine.get("currency", "")
        price_data = engine["price_data"]
        indicators = engine["indicators"]
        df = engine.get("df")

        st.markdown(f"**Ticker:** `{ticker}` | **Rynek:** `{market}` | **Waluta:** `{currency}`")
        st.caption(f"Interwał: {engine.get('interval')} | Okres: {engine.get('period')}")

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Cena", f"{price_data['price']:.4f} {currency}")
        with c2:
            st.metric("High", f"{price_data['high']:.4f}")
        with c3:
            st.metric("Low", f"{price_data['low']:.4f}")
        with c4:
            st.metric("Volume", f"{price_data['volume']:,}")

        if isinstance(df, pd.DataFrame) and not df.empty:
            plot_candles(df, ticker)

        col_mid1, col_mid2 = st.columns([2, 1])

        with col_mid1:
            st.subheader("🤖 LIVE‑AI sygnał")
            st.markdown(engine.get("live_signal", "Brak sygnału."))

        with col_mid2:
            st.subheader("📊 Techniczne FULL")
            tech_df = pd.DataFrame.from_dict(
                indicators,
                orient="index",
                columns=["Value"]
            )
            st.table(tech_df)

        st.subheader("📰 Tavily — świeże newsy dla bieżącego tickera")
        st.markdown(engine.get("news_text", "Brak newsów."))

        st.markdown("---")
        st.subheader("🧠 Scenariusze AI — Bull / Base / Bear")
        st.markdown(engine.get("scenarios", "Brak scenariuszy."))

    else:
        st.info("Podaj ticker i kliknij „Odśwież dane”.")


# ============================
# MODULE 2 — SCANNER
# ============================

if mode == "🧪 Skaner spółek":
    st.subheader("🧪 Skaner tickerów → TOP 10")

    scan_raw = st.text_area(
        "Wklej listę tickerów, oddzielone przecinkami:",
        value=st.session_state.scanner_input,
        height=120
    )

    st.session_state.scanner_input = scan_raw

    scan_list = [normalize_ticker(t) for t in scan_raw.split(",") if t.strip()]

    st.caption(
        "Score uwzględnia RSI, płynność DollarVol20 oraz trend. "
        "To filtr techniczny, nie rekomendacja."
    )

    if st.button("🚀 Skanuj i pokaż TOP 10"):
        if not scan_list:
            st.warning("Podaj przynajmniej 1 ticker.")
        else:
            with st.spinner("Skanuję tickery..."):
                scan_df = scan_tickers(scan_list)

            if scan_df.empty:
                st.warning("Brak wyników skanu. Sprawdź tickery lub dostępność danych w Yahoo.")
            else:
                st.subheader("📋 TOP 10")

                styled = scan_df.style.apply(color_rows, axis=1).format({
                    "Price": "{:.4f}",
                    "RSI": lambda x: "brak" if pd.isna(x) else f"{x:.2f}",
                    "HV": lambda x: "brak" if pd.isna(x) else f"{x:.4f}",
                    "DollarVol20": "{:.0f}",
                    "Score": "{:.2f}",
                })

                st.dataframe(styled, use_container_width=True)


# ============================
# MODULE 3 — AI CHAT
# ============================

if mode == "🤖 Czat AI":
    st.subheader("🤖 Czat AI — analityk finansowy")
    st.caption("AI używa Tavily, danych technicznych z kombajnu oraz historii rozmowy.")

    col_c1, col_c2 = st.columns([2, 1])

    with col_c2:
        chat_ticker = st.text_input(
            "Opcjonalny ticker, np. NVG.WA, AAPL, HUMA:",
            value=""
        )
        chat_ticker = normalize_ticker(chat_ticker) if chat_ticker else ""

        if st.button("🧹 Wyczyść historię"):
            st.session_state.chat_history = []
            st.rerun()

        engine = st.session_state.get("engine_data")
        if engine:
            st.info(f"Dane z kombajnu dostępne dla: {engine.get('ticker')}")
        else:
            st.warning("Brak danych z kombajnu. Czat użyje fallbacku, jeśli podasz ticker.")

    with col_c1:
        user_msg = st.text_area("Twoja wiadomość:", height=120)

    if st.button("Wyślij do AI"):
        if not user_msg.strip():
            st.warning("Napisz coś najpierw.")
        else:
            with st.spinner("AI analizuje dane i newsy..."):
                answer = ai_chat_answer(
                    user_msg.strip(),
                    chat_ticker if chat_ticker else None
                )

            st.session_state.chat_history.append(("Ty", user_msg.strip()))
            st.session_state.chat_history.append(("AI", answer))

    if st.session_state.chat_history:
        st.markdown("---")
        st.markdown("### Historia rozmowy")

        for speaker, msg in st.session_state.chat_history:
            if speaker == "Ty":
                st.markdown(f"**Ty:** {msg}")
            else:
                st.markdown(f"**AI:** {msg}")
                st.markdown("---")
