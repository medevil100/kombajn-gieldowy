import os

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from openai import OpenAI
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None


# =========================================================
# KONFIGURACJA STRONY
# =========================================================

st.set_page_config(
    page_title="AI Trading Terminal PRO",
    page_icon="📈",
    layout="wide"
)


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
<style>
.stApp { 
    background-color: #02030a; 
    color: #e5e7eb; 
}

[data-testid="stSidebar"] {
    background: radial-gradient(circle at top left, #020617, #000000);
    border-right: 1px solid #1f2937;
}

h1, h2, h3 { 
    color: #f9fafb; 
    text-shadow: 0 0 12px rgba(56,189,248,0.35); 
}

.stButton>button { 
    background: linear-gradient(135deg, #0f172a, #0369a1); 
    color: #e5e7eb; 
    border-radius: 999px; 
    border: 1px solid #38bdf8; 
    padding: 0.35rem 0.9rem; 
    font-weight: 600; 
    box-shadow: 0 0 14px rgba(56,189,248,0.35); 
}

.stButton>button:hover { 
    border-color: #22c55e; 
    box-shadow: 0 0 18px rgba(34,197,94,0.55); 
}

.metric-green { 
    color: #22c55e; 
    text-shadow: 0 0 8px rgba(34,197,94,0.7); 
    font-size: 1.2rem;
    font-weight: 700;
}

.metric-yellow { 
    color: #eab308; 
    text-shadow: 0 0 8px rgba(234,179,8,0.7); 
    font-size: 1.2rem;
    font-weight: 700;
}

.metric-red { 
    color: #ef4444; 
    text-shadow: 0 0 8px rgba(239,68,68,0.7); 
    font-size: 1.2rem;
    font-weight: 700;
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
# SEKRETY / KLUCZE API
# =========================================================

def get_secret_or_env(*names):
    """
    Pobiera klucz z kilku możliwych nazw.

    Obsługiwane przykłady:
    OPENAI_API_KEY albo sk
    TAVILY_API_KEY albo tavli
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
# FUNKCJE FORMATUJĄCE
# =========================================================

def safe_float(value, default=np.nan):
    try:
        return float(value)
    except Exception:
        return default


def fmt_num(value, digits=4):
    try:
        value = float(value)
        if np.isnan(value):
            return "brak"
        return f"{value:.{digits}f}"
    except Exception:
        return "brak"


# =========================================================
# NAPRAWA DANYCH YFINANCE
# =========================================================

def normalize_yfinance_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Naprawia problem MultiIndex z yfinance.
    Po tej funkcji kolumny powinny być:
    Open, High, Low, Close, Volume.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        level0 = list(df.columns.get_level_values(0))
        level1 = list(df.columns.get_level_values(1))

        price_cols = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}

        if any(col in price_cols for col in level0):
            df.columns = df.columns.get_level_values(0)
        elif any(col in price_cols for col in level1):
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

    # Usuń duplikaty kolumn
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
# WSKAŹNIKI TECHNICZNE
# =========================================================

def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    delta = series.diff()

    gain = delta.where(delta > 0, 0.0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean()

    rs = gain / (loss + 1e-9)

    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")

    hl = high - low
    hc = (high - close.shift()).abs()
    lc = (low - close.shift()).abs()

    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)

    return tr.rolling(period).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    series = pd.to_numeric(series, errors="coerce")

    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()

    m = ema_fast - ema_slow
    s = m.ewm(span=signal, adjust=False).mean()
    h = m - s

    return m, s, h


def bollinger(series: pd.Series, window: int = 20, mult: float = 2.0):
    series = pd.to_numeric(series, errors="coerce")

    mid = series.rolling(window).mean()
    std = series.rolling(window).std()

    upper = mid + mult * std
    lower = mid - mult * std

    return mid, upper, lower


def trend_signal(close: pd.Series):
    close = pd.to_numeric(close, errors="coerce")

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    latest_sma20 = safe_float(sma20.iloc[-1])
    latest_sma50 = safe_float(sma50.iloc[-1])
    latest_sma200 = safe_float(sma200.iloc[-1])

    if np.isnan(latest_sma20) or np.isnan(latest_sma50) or np.isnan(latest_sma200):
        return "ZA MAŁO DANYCH", "metric-yellow"

    if latest_sma20 > latest_sma50 > latest_sma200:
        return "KUP", "metric-green"

    if latest_sma20 < latest_sma50 < latest_sma200:
        return "SPRZEDAJ", "metric-red"

    return "TRZYMAJ", "metric-yellow"


def build_technical_summary(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]

    return {
        "close": safe_float(last["Close"]),
        "rsi": safe_float(last["RSI"]),
        "sma20": safe_float(last["SMA20"]),
        "sma50": safe_float(last["SMA50"]),
        "sma200": safe_float(last["SMA200"]),
        "atr": safe_float(last["ATR"]),
        "macd": safe_float(last["MACD"]),
        "macd_signal": safe_float(last["MACD_SIGNAL"]),
        "macd_hist": safe_float(last["MACD_HIST"]),
        "bb_upper": safe_float(last["BB_UPPER"]),
        "bb_mid": safe_float(last["BB_MID"]),
        "bb_lower": safe_float(last["BB_LOWER"]),
    }


# =========================================================
# ŁADOWANIE DANYCH
# =========================================================

@st.cache_data(show_spinner=False, ttl=300)
def load(symbol: str, interval: str, period: str) -> pd.DataFrame:
    try:
        df = yf.download(
            tickers=symbol,
            interval=interval,
            period=period,
            progress=False,
            auto_adjust=False,
            threads=False
        )

        df = normalize_yfinance_df(df)

        if df.empty:
            return pd.DataFrame()

        return df

    except Exception:
        return pd.DataFrame()


# =========================================================
# TAVILY NEWS
# =========================================================

@st.cache_data(show_spinner=False, ttl=1800)
def fetch_tavily_news(symbol: str) -> str:
    tavily_key = get_tavily_key()

    if not tavily_key:
        return "Brak klucza Tavily. Dodaj TAVILY_API_KEY albo tavli w Streamlit Secrets."

    if TavilyClient is None:
        return "Brak biblioteki tavily-python. Dodaj tavily-python do requirements.txt."

    try:
        client = TavilyClient(api_key=tavily_key)

        query = (
            f"{symbol} stock latest news earnings revenue guidance analyst rating "
            f"technical analysis market sentiment catalysts risks today"
        )

        response = client.search(
            query=query,
            max_results=5,
            search_depth="advanced"
        )

        results = response.get("results", [])

        if not results:
            return "Brak istotnych newsów."

        lines = []

        for i, item in enumerate(results, start=1):
            title = str(item.get("title", ""))[:250]
            content = str(item.get("content", ""))[:800]
            url = str(item.get("url", ""))[:300]

            lines.append(
                f"NEWS {i}: {title}\n"
                f"Treść: {content}\n"
                f"Źródło: {url}"
            )

        return "\n\n".join(lines)

    except Exception as e:
        return f"Błąd Tavily: {e}"


# =========================================================
# AI
# =========================================================

def build_prompt(style: str):
    return (
        "Jesteś profesjonalnym traderem technicznym i analitykiem rynku. "
        "Analizujesz jeden instrument i podajesz konkretny, praktyczny plan. "
        "Nie obiecujesz zysków. Nie udawaj pewności, jeśli dane są niepełne. "
        "Pisz po polsku.\n\n"

        "Wymagana struktura odpowiedzi:\n\n"

        "#1 DECYZJA\n"
        "- KUP / SPRZEDAJ / TRZYMAJ.\n"
        "- Krótkie uzasadnienie.\n\n"

        "#2 ANALIZA TECHNICZNA\n"
        "- RSI.\n"
        "- SMA20 / SMA50 / SMA200.\n"
        "- MACD i MACD signal.\n"
        "- Bollinger Bands.\n"
        "- Trend i momentum.\n\n"

        "#3 PLAN TRANSAKCJI\n"
        "- ENTRY.\n"
        "- SL.\n"
        "- TP1.\n"
        "- TP2.\n"
        "- TP3.\n"
        "- Komentarz do relacji zysku do ryzyka.\n\n"

        "#4 NEWSY I SENTYMENT\n"
        "- Wypunktuj pozytywne katalizatory.\n"
        "- Wypunktuj ryzyka.\n"
        "- Oddziel fakty od interpretacji.\n\n"

        "#5 AUTO-PATTERN DETECTION\n"
        "- Opisz wykryte patterny, np. double top, triangle, flag, range, tylko jeśli są istotne.\n"
        "- Jeśli brak czytelnego patternu, napisz to jasno.\n\n"

        "#6 RYZYKO\n"
        "- Oceń ryzyko w skali 1–10.\n"
        "- Wskaż, co może unieważnić scenariusz.\n\n"

        "#7 ZASTRZEŻENIE\n"
        "- Krótko zaznacz, że to nie jest rekomendacja inwestycyjna.\n\n"

        f"Styl analizy: {style}."
    )


def call_ai(client, model: str, system_prompt: str, user_prompt: str):
    if client is None:
        return "AI OFF – brak OPENAI_API_KEY albo sk w Streamlit Secrets."

    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            temperature=0.25,
            max_tokens=1700
        )

        return r.choices[0].message.content.strip()

    except Exception as e:
        return f"AI ERROR: {e}"


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("⚙️ Ustawienia")

symbol = st.sidebar.text_input(
    "Ticker",
    value="AAPL",
    help="Przykłady: AAPL, MSFT, TSLA, NVDA, BTC-USD, ETH-USD, EURUSD=X"
).upper().strip()

tf = st.sidebar.selectbox(
    "Interwał",
    ["1m", "5m", "15m", "30m", "1h"],
    index=2
)

model = st.sidebar.selectbox(
    "Model GPT",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1"],
    index=0
)

style = st.sidebar.selectbox(
    "Styl AI",
    ["Technicznie", "Swing", "Daytrading"],
    index=0
)

with st.sidebar.expander("Status API"):
    openai_key = get_secret_or_env("OPENAI_API_KEY", "sk", "OPENAI_KEY")
    tavily_key = get_secret_or_env("TAVILY_API_KEY", "tavli", "TAVILY_KEY")

    st.write("OpenAI:", "✅ klucz wykryty" if openai_key else "❌ brak klucza")
    st.write("Tavily:", "✅ klucz wykryty" if tavily_key else "❌ brak klucza")
    st.write("Tavily package:", "✅ OK" if TavilyClient is not None else "❌ brak tavily-python")

with st.sidebar.expander("Nazwy sekretów"):
    st.write("Aplikacja obsługuje:")
    st.code(
        """
OPENAI_API_KEY = "sk-..."
TAVILY_API_KEY = "tvly-..."
        """
    )
    st.write("albo Twoje nazwy:")
    st.code(
        """
sk = "sk-..."
tavli = "tvly-..."
        """
    )

if tf == "1m":
    interval, period = "1m", "5d"
elif tf == "5m":
    interval, period = "5m", "10d"
elif tf == "15m":
    interval, period = "15m", "30d"
elif tf == "30m":
    interval, period = "30m", "60d"
else:
    interval, period = "60m", "1y"


# =========================================================
# GŁÓWNA APLIKACJA
# =========================================================

st.title("AI Trading Terminal PRO")

st.caption(
    "Terminal techniczny: świece, SMA20/50/200, RSI, MACD, Bollinger Bands, ATR, wolumen, trendline, Tavily news i analiza AI."
)

if not symbol:
    st.info("Wpisz ticker, aby rozpocząć.")
    st.stop()


# ---------------------------------------------------------
# DANE
# ---------------------------------------------------------

with st.spinner(f"Pobieranie danych dla {symbol}, interwał {tf}..."):
    df = load(symbol, interval, period)

if df.empty:
    st.warning(
        "Brak danych albo problem z Yahoo Finance. "
        "Sprawdź ticker, interwał lub spróbuj ponownie później."
    )
    st.stop()

if len(df) < 30:
    st.warning("Za mało świec do stabilnej analizy technicznej.")
    st.dataframe(df.tail(), use_container_width=True)
    st.stop()


# ---------------------------------------------------------
# WSKAŹNIKI
# ---------------------------------------------------------

df["RSI"] = rsi(df["Close"])
df["SMA20"] = df["Close"].rolling(20).mean()
df["SMA50"] = df["Close"].rolling(50).mean()
df["SMA200"] = df["Close"].rolling(200).mean()
df["ATR"] = atr(df)
df["MACD"], df["MACD_SIGNAL"], df["MACD_HIST"] = macd(df["Close"])
df["BB_MID"], df["BB_UPPER"], df["BB_LOWER"] = bollinger(df["Close"])

last = df.iloc[-1]

last_close = safe_float(last["Close"])
atr_val = safe_float(last["ATR"])

if np.isnan(atr_val) or atr_val <= 0:
    atr_val = safe_float((df["High"] - df["Low"]).tail(14).mean())

if not np.isnan(atr_val) and atr_val > 0:
    sl = last_close - 1.5 * atr_val
    tp1 = last_close + 1.0 * atr_val
    tp2 = last_close + 2.0 * atr_val
    tp3 = last_close + 3.0 * atr_val
else:
    sl, tp1, tp2, tp3 = np.nan, np.nan, np.nan, np.nan

sig, cls = trend_signal(df["Close"])


# ---------------------------------------------------------
# METRYKI
# ---------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        f"<div class='{cls}'>Trend: {sig}</div>",
        unsafe_allow_html=True
    )

with c2:
    r_val = safe_float(last["RSI"])
    rc = "metric-green" if r_val < 30 else "metric-red" if r_val > 70 else "metric-yellow"
    st.markdown(
        f"<div class='{rc}'>RSI: {fmt_num(r_val, 1)}</div>",
        unsafe_allow_html=True
    )

with c3:
    st.markdown(
        f"<div class='metric-yellow'>ATR: {fmt_num(atr_val, 4)}</div>",
        unsafe_allow_html=True
    )

with c4:
    st.markdown(
        f"<div class='metric-green'>Cena: {fmt_num(last_close, 4)}</div>",
        unsafe_allow_html=True
    )


# ---------------------------------------------------------
# AUTO TRENDLINE
# ---------------------------------------------------------

n_trend = min(80, len(df))
x_idx = np.arange(n_trend)
y_close = df["Close"].iloc[-n_trend:].astype(float).values

if len(y_close) > 1 and not np.isnan(y_close).all():
    coef = np.polyfit(x_idx, y_close, 1)
    trend_line = coef[0] * x_idx + coef[1]
    trend_x = df.index[-n_trend:]
else:
    trend_line = None
    trend_x = None


# ---------------------------------------------------------
# WYKRES
# ---------------------------------------------------------

fig = make_subplots(
    rows=4,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.03,
    row_heights=[0.45, 0.15, 0.2, 0.2],
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
        y=df["SMA20"],
        line=dict(color="#22c55e", width=1.2),
        name="SMA20"
    ),
    row=1,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["SMA50"],
        line=dict(color="#eab308", width=1.2),
        name="SMA50"
    ),
    row=1,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["SMA200"],
        line=dict(color="#ef4444", width=1.2),
        name="SMA200"
    ),
    row=1,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["BB_UPPER"],
        line=dict(color="#eab308", width=0.8, dash="dot"),
        name="BB Upper"
    ),
    row=1,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["BB_MID"],
        line=dict(color="#eab308", width=0.8),
        name="BB Mid"
    ),
    row=1,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["BB_LOWER"],
        line=dict(color="#eab308", width=0.8, dash="dot"),
        name="BB Lower"
    ),
    row=1,
    col=1
)

if trend_line is not None:
    fig.add_trace(
        go.Scatter(
            x=trend_x,
            y=trend_line,
            line=dict(color="#38bdf8", width=1.4, dash="dash"),
            name="Auto Trendline"
        ),
        row=1,
        col=1
    )

# SL/TP na wykresie
if not np.isnan(sl):
    fig.add_hline(
        y=sl,
        line_dash="dot",
        line_color="#ef4444",
        annotation_text="SL",
        row=1,
        col=1
    )

if not np.isnan(tp1):
    fig.add_hline(
        y=tp1,
        line_dash="dot",
        line_color="#22c55e",
        annotation_text="TP1",
        row=1,
        col=1
    )

if not np.isnan(tp2):
    fig.add_hline(
        y=tp2,
        line_dash="dot",
        line_color="#22c55e",
        annotation_text="TP2",
        row=1,
        col=1
    )

if not np.isnan(tp3):
    fig.add_hline(
        y=tp3,
        line_dash="dash",
        line_color="#22c55e",
        annotation_text="TP3",
        row=1,
        col=1
    )

vol = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)

if vol.sum() > 0:
    v_q1, v_q2, v_q3 = vol.quantile([0.33, 0.66, 0.9])
else:
    v_q1, v_q2, v_q3 = 0, 0, 0

colors = []

for v, o, c in zip(vol, df["Open"], df["Close"]):
    if v >= v_q3 and v_q3 > 0:
        colors.append("#ef4444" if c < o else "#22c55e")
    elif v >= v_q2 and v_q2 > 0:
        colors.append("#eab308")
    else:
        colors.append("#22c55e" if c >= o else "#ef4444")

fig.add_trace(
    go.Bar(
        x=df.index,
        y=vol,
        marker_color=colors,
        name="Volume Heatmap"
    ),
    row=2,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["RSI"],
        line=dict(color="#eab308", width=1.2),
        name="RSI"
    ),
    row=3,
    col=1
)

fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=3, col=1)
fig.add_hline(y=50, line_dash="dash", line_color="#64748b", row=3, col=1)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["MACD"],
        line=dict(color="#22c55e", width=1.2),
        name="MACD"
    ),
    row=4,
    col=1
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["MACD_SIGNAL"],
        line=dict(color="#ef4444", width=1.0),
        name="MACD Signal"
    ),
    row=4,
    col=1
)

fig.add_trace(
    go.Bar(
        x=df.index,
        y=df["MACD_HIST"],
        marker_color=np.where(df["MACD_HIST"] >= 0, "#22c55e", "#ef4444"),
        name="MACD Hist"
    ),
    row=4,
    col=1
)

fig.update_layout(
    template="plotly_dark",
    height=900,
    xaxis_rangeslider_visible=False,
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    ),
    margin=dict(l=20, r=20, t=60, b=20)
)

st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# PLAN TRANSAKCJI
# ---------------------------------------------------------

st.subheader("Plan transakcji")

p1, p2, p3, p4 = st.columns(4)

with p1:
    st.markdown(
        f"<div class='metric-red'>SL: {fmt_num(sl, 4)}</div>",
        unsafe_allow_html=True
    )

with p2:
    st.markdown(
        f"<div class='metric-green'>TP1: {fmt_num(tp1, 4)}</div>",
        unsafe_allow_html=True
    )

with p3:
    st.markdown(
        f"<div class='metric-green'>TP2: {fmt_num(tp2, 4)}</div>",
        unsafe_allow_html=True
    )

with p4:
    st.markdown(
        f"<div class='metric-green'>TP3: {fmt_num(tp3, 4)}</div>",
        unsafe_allow_html=True
    )

st.caption(
    "SL/TP są poziomami orientacyjnymi liczonymi z ATR. "
    "Nie stanowią rekomendacji inwestycyjnej."
)


# ---------------------------------------------------------
# NEWSY TAVILY
# ---------------------------------------------------------

st.subheader("📰 Newsy i sentyment Tavily")

with st.spinner("Pobieranie newsów z Tavily..."):
    tavily_news = fetch_tavily_news(symbol)

with st.expander("Pokaż newsy Tavily"):
    st.text(tavily_news)


# ---------------------------------------------------------
# TABELA DANYCH
# ---------------------------------------------------------

with st.expander("Pokaż ostatnie dane i wskaźniki"):
    st.dataframe(
        df.tail(30)[
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
                "RSI",
                "SMA20",
                "SMA50",
                "SMA200",
                "ATR",
                "MACD",
                "MACD_SIGNAL",
                "MACD_HIST",
                "BB_UPPER",
                "BB_MID",
                "BB_LOWER"
            ]
        ],
        use_container_width=True
    )


# ---------------------------------------------------------
# AI ANALIZA
# ---------------------------------------------------------

st.subheader("AI analiza instrumentu")

if st.button("🔮 Wygeneruj analizę AI"):
    client = get_openai_client()

    last_rows = df.tail(20)[["Open", "High", "Low", "Close"]]
    pattern_snippet = last_rows.to_string()

    system_prompt = build_prompt(style)

    user_prompt = (
        f"Analizuj instrument: {symbol}\n"
        f"Interwał: {tf}\n\n"

        f"DANE TECHNICZNE:\n"
        f"Cena: {fmt_num(last_close, 4)}\n"
        f"RSI: {fmt_num(last['RSI'], 1)}\n"
        f"SMA20: {fmt_num(df['SMA20'].iloc[-1], 4)}\n"
        f"SMA50: {fmt_num(df['SMA50'].iloc[-1], 4)}\n"
        f"SMA200: {fmt_num(df['SMA200'].iloc[-1], 4)}\n"
        f"ATR: {fmt_num(atr_val, 4)}\n"
        f"MACD: {fmt_num(df['MACD'].iloc[-1], 4)}\n"
        f"MACD_SIGNAL: {fmt_num(df['MACD_SIGNAL'].iloc[-1], 4)}\n"
        f"MACD_HIST: {fmt_num(df['MACD_HIST'].iloc[-1], 4)}\n"
        f"Bollinger upper: {fmt_num(df['BB_UPPER'].iloc[-1], 4)}\n"
        f"Bollinger mid: {fmt_num(df['BB_MID'].iloc[-1], 4)}\n"
        f"Bollinger lower: {fmt_num(df['BB_LOWER'].iloc[-1], 4)}\n"
        f"Trend techniczny: {sig}\n\n"

        f"PLAN TECHNICZNY:\n"
        f"SL: {fmt_num(sl, 4)}\n"
        f"TP1: {fmt_num(tp1, 4)}\n"
        f"TP2: {fmt_num(tp2, 4)}\n"
        f"TP3: {fmt_num(tp3, 4)}\n\n"

        f"OSTATNIE ŚWIECE OHLC DO AUTO-PATTERN DETECTION:\n"
        f"{pattern_snippet}\n\n"

        f"NEWSY I SENTYMENT Z TAVILY:\n"
        f"{tavily_news}\n"
    )

    with st.spinner("Generowanie analizy AI..."):
        out = call_ai(client, model, system_prompt, user_prompt)

    st.markdown(out)


# ---------------------------------------------------------
# STOPKA
# ---------------------------------------------------------

st.markdown(
    """
<hr style='border: 1px solid #1f2937; margin-top: 40px;'>
<div style='text-align: center; color: #6b7280; font-size: 0.8rem;'>
AI Trading Terminal PRO • Neon Dark • SMA / RSI / MACD / BB / ATR / Trend / Tavily / OpenAI
<br>
To narzędzie edukacyjne i analityczne. Nie stanowi rekomendacji inwestycyjnej.
</div>
""",
    unsafe_allow_html=True
)
```
