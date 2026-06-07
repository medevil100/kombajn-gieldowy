# =========================================================
# 🔥 KOMBAJN MAX PRO — CZĘŚĆ 1/3
# Importy + CSS + Sesja + Sidebar + Internet PRO
# =========================================================

import os
import json
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from typing import Dict, Any, List, Optional

import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
import requests
from openai import OpenAI


# =========================================================
# 🎨 KONFIGURACJA STRONY + MOTYW NEON DARK
# =========================================================

st.set_page_config(
    layout="wide",
    page_title="🔥 KOMBAJN MAX PRO — AI + Internet + Heatmapa + Wykresy"
)

# CSS — wersja MAX PRO
st.markdown("""
<style>

:root {
    --neon-green: #00ff88;
    --neon-red: #ff3355;
    --bg-dark: #050509;
    --bg-panel: #0B0B12;
}

/* Tło */
body, .stApp {
    background-color: var(--bg-dark) !important;
    color: #E5E5E5 !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: var(--bg-panel) !important;
    border-right: 1px solid #1c1c24 !important;
}

/* Kontener */
.block-container {
    padding-top: 1rem;
}

/* Przyciski primary */
button[kind="primary"] {
    background-color: #111 !important;
    border: 1px solid var(--neon-green) !important;
    color: var(--neon-green) !important;
    box-shadow: 0 0 10px var(--neon-green) !important;
}
button[kind="primary"]:hover {
    background-color: var(--neon-green) !important;
    color: #000 !important;
    box-shadow: 0 0 20px var(--neon-green) !important;
}

/* Przyciski zwykłe */
button {
    background-color: #111 !important;
    border: 1px solid #444 !important;
    color: #ccc !important;
}
button:hover {
    border-color: var(--neon-green) !important;
    color: var(--neon-green) !important;
}

/* Zakładki */
.stTabs [data-baseweb="tab"] {
    background-color: #111 !important;
    color: #aaa !important;
    border: 1px solid #222 !important;
    border-radius: 6px !important;
    padding: 8px 16px !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--neon-green) !important;
    border-color: var(--neon-green) !important;
}
.stTabs [aria-selected="true"] {
    background-color: #000 !important;
    color: var(--neon-green) !important;
    border: 1px solid var(--neon-green) !important;
    box-shadow: 0 0 15px var(--neon-green) !important;
}

/* Inputy */
input, textarea, select {
    background-color: #0B0B12 !important;
    color: #E5E5E5 !important;
    border: 1px solid #333 !important;
    border-radius: 6px !important;
}
input:focus, textarea:focus, select:focus {
    border-color: var(--neon-green) !important;
    box-shadow: 0 0 10px var(--neon-green) !important;
}

/* Metric */
.stMetric {
    background-color: #0B0B12 !important;
    border: 1px solid #222 !important;
    border-radius: 8px !important;
    padding: 10px !important;
}
.stMetric > div {
    color: var(--neon-green) !important;
}

/* Dataframe */
.dataframe tbody tr:hover {
    background-color: #111 !important;
}
.dataframe td {
    border: 1px solid #222 !important;
}

</style>
""", unsafe_allow_html=True)

st.title("🔥 KOMBAJN MAX PRO — AI + Internet + Heatmapa + Wykresy + Patterny + News")


# =========================================================
# 🤖 OPENAI — konfiguracja
# =========================================================

AI_MODEL = "gpt-4o-mini"
api_key = os.getenv("OPENAI_API_KEY", "")

if not api_key:
    st.error("❌ Brak klucza OPENAI_API_KEY — AI nie będzie działać.")

client = OpenAI(api_key=api_key)


# =========================================================
# 🧠 SESJA — pamięć aplikacji
# =========================================================

session_defaults = {
    "symbols": [],
    "ai_top5_comment": "",
    "ai_deep_dive_cache": {},
    "ai_multi_comment": "",
    "news_scores": {},
    "ai_news_deep_cache": {},
    "ai_news_radar_comment": "",
    "internet_chat": [],
}

for key, value in session_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# 🧭 PANEL BOCZNY — dodawanie tickerów
# =========================================================

st.sidebar.header("⚙️ Ustawienia")

st.sidebar.info(
    "Format tickerów:\n"
    "- GPW: STX.WA, PKO.WA, CDR.WA\n"
    "- USA: AAPL, TSLA, NVDA\n"
    "- MIX: AAPL,STX.WA,TSLA,PKO.WA"
)

symbols_input = st.sidebar.text_input(
    "Dodaj spółki (oddzielone przecinkami):",
    "",
    key="sidebar_add_symbols"
)

if st.sidebar.button("Dodaj", key="sidebar_add_btn"):
    for raw in symbols_input.split(","):
        sym = raw.strip().upper()
        if sym and sym not in st.session_state.symbols:
            st.session_state.symbols.append(sym)

if st.sidebar.button("Wyczyść", key="sidebar_clear_btn"):
    for key in session_defaults:
        st.session_state[key] = session_defaults[key]


# =========================================================
# 🌐 INTERNET PRO — Google News RSS + Yahoo Finance + Pogoda
# =========================================================

def search_google_news(query: str) -> str:
    """Pobiera newsy z Google News RSS."""
    try:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        data = urllib.request.urlopen(url, timeout=8).read()
        root = ET.fromstring(data)

        items = root.findall(".//item")
        if not items:
            return "Brak newsów."

        out = []
        for item in items[:5]:
            title = item.find("title").text
            source = item.find("source").text if item.find("source") is not None else ""
            out.append(f"- {title} ({source})")

        return "\n".join(out)

    except Exception as e:
        return f"News error: {e}"


def search_stock(symbol: str) -> str:
    """Pobiera dane giełdowe z Yahoo Finance."""
    try:
        t = yf.Ticker(symbol)
        info = t.info

        price = info.get("currentPrice")
        change = info.get("regularMarketChangePercent")
        vol = info.get("volume")
        cap = info.get("marketCap")

        if price is None:
            return "Brak danych giełdowych."

        return (
            f"Cena: {price}\n"
            f"Zmiana: {change:+.2f}%\n"
            f"Wolumen: {vol:,}\n"
            f"Kapitalizacja: {cap:,}\n"
        )
    except Exception as e:
        return f"Stock error: {e}"


def search_weather(city: str) -> str:
    """Pogoda z wttr.in."""
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        data = requests.get(url, timeout=8).json()
        cond = data["current_condition"][0]
        temp = cond["temp_C"]
        desc = cond["weatherDesc"][0]["value"]
        hum = cond["humidity"]
        wind = cond["windspeedKmph"]

        return f"{city}: {temp}°C, {desc}, wilgotność {hum}%, wiatr {wind} km/h"
    except:
        return "Brak danych pogodowych."


def internet_search(query: str) -> str:
    """Router: ticker → dane giełdowe, słowo → newsy, pogoda → pogoda."""
    q = query.lower()

    if "pogoda" in q or "weather" in q:
        city = q.replace("pogoda", "").replace("weather", "").strip()
        return search_weather(city)

    if len(query) <= 6 and query.replace(".", "").isalpha():
        return search_stock(query.upper())

    return search_google_news(query)


def ai_with_internet_answer(user_message: str, chat_history: list) -> str:
    """AI + Internet PRO — łączy dane z internetu z odpowiedzią AI."""
    web_ctx = internet_search(user_message)

    messages = [
        {
            "role": "system",
            "content": (
                "Masz pełny dostęp do internetu poprzez dane dostarczone w sekcji (INTERNET). "
                "Nigdy nie mów, że nie masz dostępu do internetu. "
                "Nigdy nie mów, że nie możesz sprawdzić danych. "
                "Jeśli dane są słabe — odpowiadasz ogólnie, ale ZAWSZE odpowiadasz. "
                "Jeśli dane są dobre — używasz ich. "
                "Nie odmawiasz. Nie przekierowujesz. Nie sugerujesz innych stron. "
                "Twoja odpowiedź ma być konkretna, krótka i po polsku."
            ),
        },
        {"role": "assistant", "content": f"(INTERNET):\n{web_ctx}"},
    ]

    for m in chat_history:
        messages.append(m)

    messages.append({"role": "user", "content": user_message})

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
    )
    return res.choices[0].message.content


    res = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
    )
    return res.choices[0].message.content
# =========================================================
# 📊 DANE RYNKOWE + METRYKI MAX PRO
# =========================================================

def get_price_data(symbol, period="5d", interval="1h"):
    """Pobiera dane OHLCV z Yahoo Finance."""
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()


def get_bid_ask(symbol: str):
    """Pobiera bid/ask + spread z Yahoo Finance."""
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        bid = info.get("bid")
        ask = info.get("ask")

        if not bid or not ask:
            return None, None, None

        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid * 100
        return float(bid), float(ask), float(spread_pct)
    except:
        return None, None, None


def compute_metrics(symbol):
    """Liczy wszystkie metryki: trend, momentum, ATR, ryzyko, setup score."""
    df = get_price_data(symbol, "5d", "1h")
    if df.empty or len(df) < 3:
        return {
            "Symbol": symbol,
            "LastPrice": 0.0,
            "Change": 0.0,
            "Volume": 0.0,
            "ATR": 0.0,
            "Trend": "NONE",
            "Signal": "NEUTRAL",
            "MomentumScore": 0.0,
            "VolatilityScore": 0.0,
            "TrendStrength": 0.0,
            "RiskScore": 50.0,
            "SetupScore": 0.0,
        }

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    last = close.iloc[-1]
    prev = close.iloc[-2]
    change = ((last - prev) / prev * 100) if prev != 0 else 0.0

    # ATR
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(14).mean()
    atr = atr_series.iloc[-1] if not atr_series.dropna().empty else 0.0

    # Trend
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    if last > ema20.iloc[-1] > ema50.iloc[-1]:
        trend = "UP"
    elif last < ema20.iloc[-1] < ema50.iloc[-1]:
        trend = "DOWN"
    else:
        trend = "SIDE"

    # Sygnał
    if trend == "UP" and change > 0:
        signal = "BUY"
    elif trend == "DOWN" and change < 0:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    # Momentum
    vol_last = volume.iloc[-1]
    vol_prev = volume.iloc[-2] if len(volume) > 1 else vol_last
    vol_change = ((vol_last - vol_prev) / vol_prev * 100) if vol_prev != 0 else 0.0

    raw_momentum = change * 0.7 + vol_change * 0.3
    momentum_score = max(0, min(100, 50 + raw_momentum))

    # Volatility
    vol_ratio = (atr / last * 100) if last != 0 else 0.0
    volatility_score = max(0, min(100, vol_ratio * 2))

    # Trend strength
    trend_diff = abs(ema20.iloc[-1] - ema50.iloc[-1]) / last * 100 if last != 0 else 0.0
    trend_strength = max(0, min(100, trend_diff * 5))

    # Risk
    risk_score = volatility_score

    # Setup score
    setup = 0
    if signal == "BUY":
        setup += 30
    elif signal == "SELL":
        setup += 20

    setup += momentum_score * 0.3
    setup += trend_strength * 0.3
    setup -= risk_score * 0.2
    setup_score = max(0, min(100, setup))

    return {
        "Symbol": symbol,
        "LastPrice": last,
        "Change": change,
        "Volume": vol_last,
        "ATR": atr,
        "Trend": trend,
        "Signal": signal,
        "MomentumScore": momentum_score,
        "VolatilityScore": volatility_score,
        "TrendStrength": trend_strength,
        "RiskScore": risk_score,
        "SetupScore": setup_score,
    }


# =========================================================
# 🎨 HEATMAPA MAX PRO
# =========================================================

def format_news_score(value):
    """Ładny pasek NewsScore."""
    try:
        score = float(value)
    except:
        score = 0.0

    score = max(0, min(100, score))
    length = 40
    filled = int(score / 100 * length)
    bar = "█" * filled + "░" * (length - filled)

    if score < 30:
        icon = "🟢"
    elif score < 60:
        icon = "🟠"
    else:
        icon = "🔴"

    return f"{icon} {score:.0f} |{bar}|"


def style_heatmap(df):
    """Kolorowanie heatmapy PRO."""
    styles = pd.DataFrame("", index=df.index, columns=df.columns)

    for i, row in df.iterrows():
        ss = row["SetupScore"]
        intensity = min(max(ss / 100, 0), 1)
        base_color = "0,255,0" if ss >= 50 else "255,0,0"
        row_bg = f"background-color: rgba({base_color},{0.15 + 0.35*intensity})"

        for col in df.columns:
            styles.loc[i, col] = row_bg

        # Change
        c = row["Change"]
        if c > 0:
            styles.loc[i, "Change"] = f"background-color: rgba(0,255,0,{min(abs(c)/10,1)})"
        elif c < 0:
            styles.loc[i, "Change"] = f"background-color: rgba(255,0,0,{min(abs(c)/10,1)})"
        else:
            styles.loc[i, "Change"] = "background-color: rgba(128,128,128,0.3)"

        # Trend
        if row["Trend"] == "UP":
            styles.loc[i, "Trend"] = "background-color: rgba(0,255,0,0.4)"
        elif row["Trend"] == "DOWN":
            styles.loc[i, "Trend"] = "background-color: rgba(255,0,0,0.4)"
        else:
            styles.loc[i, "Trend"] = "background-color: rgba(128,128,128,0.3)"

        # Signal
        if row["Signal"] == "BUY":
            styles.loc[i, "Signal"] = "background-color: rgba(0,255,0,0.6)"
        elif row["Signal"] == "SELL":
            styles.loc[i, "Signal"] = "background-color: rgba(255,0,0,0.6)"
        else:
            styles.loc[i, "Signal"] = "background-color: rgba(128,128,128,0.3)"

        # NewsScore
        if "NewsScore" in df.columns:
            ns = float(row.get("NewsScore", 0))
            ns = max(0, min(100, ns))

            if ns <= 50:
                t = ns / 50
                r = int(0 + t * 255)
                g = int(255 - t * (255 - 165))
                b = 0
            else:
                t = (ns - 50) / 50
                r = 255
                g = int(165 - t * 165)
                b = 0

            styles.loc[i, "NewsScore"] = f"background-color: rgba({r},{g},{b},0.35)"

    fmt = {
        "Change": "{:+.2f}%",
        "Volume": "{:,.0f}",
        "ATR": "{:.4f}",
        "MomentumScore": "{:.1f}",
        "VolatilityScore": "{:.1f}",
        "TrendStrength": "{:.1f}",
        "RiskScore": "{:.1f}",
        "SetupScore": "{:.1f}",
    }

    if "NewsScore" in df.columns:
        fmt["NewsScore"] = format_news_score

    return df.style.apply(lambda _: styles, axis=None).format(fmt)


# =========================================================
# 📈 WYKRES MAX PRO — świeczki + EMA + RSI + MACD + ATR
# =========================================================

def plot_pro_chart(symbol: str):
    df = get_price_data(symbol, "3mo", "1d")
    if df.empty:
        st.warning("Brak danych do wykresu.")
        return

    close = df["Close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Cena"
    ))

    fig.add_trace(go.Scatter(x=df.index, y=ema20, mode="lines", name="EMA20", line=dict(color="cyan")))
    fig.add_trace(go.Scatter(x=df.index, y=ema50, mode="lines", name="EMA50", line=dict(color="magenta")))

    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean().abs()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    st.subheader("RSI(14)")
    st.line_chart(rsi.dropna())

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    st.subheader("MACD")
    st.line_chart(pd.DataFrame({"MACD": macd_line, "Signal": signal_line}).dropna())

    # ATR
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(14).mean()
    st.subheader("ATR(14)")
    st.line_chart(atr_series.dropna())


# =========================================================
# 🚨 ALERTY MAX PRO
# =========================================================

def generate_alerts(df: pd.DataFrame):
    alerts = []
    for _, row in df.iterrows():
        sym = row["Symbol"]
        ss = row["SetupScore"]
        mom = row["MomentumScore"]
        trend = row["Trend"]
        ch = row["Change"]
        vol = row["VolatilityScore"]

        if ss >= 70 and trend == "UP":
            alerts.append(f"🔥 {sym}: mocny setup (SetupScore {ss:.1f}, trend UP).")
        if mom >= 60:
            alerts.append(f"⚡ {sym}: wysokie momentum ({mom:.1f}).")
        if abs(ch) >= 3:
            alerts.append(f"📈 {sym}: duża zmiana intraday ({ch:+.2f}%).")
        if vol >= 70:
            alerts.append(f"⚠️ {sym}: bardzo wysoka zmienność (VolatilityScore {vol:.1f}).")

    return alerts


# =========================================================
# 📐 PATTERNY MAX PRO — breakout, squeeze, RSI, EMA cross
# =========================================================

def detect_patterns_for_symbol(symbol: str):
    df = get_price_data(symbol, "3mo", "1d")
    if df.empty or len(df) < 30:
        return []

    close = df["Close"].astype(float)
    patterns = []

    # Breakout
    rolling_max = close.rolling(20).max()
    rolling_min = close.rolling(20).min()
    last = close.iloc[-1]

    if last > rolling_max.iloc[-2]:
        patterns.append("Breakout UP (wybicie powyżej 20-dniowego maksimum).")
    if last < rolling_min.iloc[-2]:
        patterns.append("Breakout DOWN (wybicie poniżej 20-dniowego minimum).")

    # Bollinger Squeeze
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_width = (std20 * 2).iloc[-1] / last * 100 if last != 0 else 0
    if bb_width < 3:
        patterns.append("Bollinger Squeeze (bardzo niska zmienność).")

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean().abs()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi_last = rsi.iloc[-1]

    if rsi_last > 70:
        patterns.append(f"RSI overbought ({rsi_last:.1f}).")
    elif rsi_last < 30:
        patterns.append(f"RSI oversold ({rsi_last:.1f}).")

    # EMA cross
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    if ema20.iloc[-1] > ema50.iloc[-1] and ema20.iloc[-2] <= ema50.iloc[-2]:
        patterns.append("EMA20 cross UP (sygnał wybicia).")
    if ema20.iloc[-1] < ema50.iloc[-1] and ema20.iloc[-2] >= ema50.iloc[-2]:
        patterns.append("EMA20 cross DOWN (sygnał słabości).")

    return patterns


def detect_patterns_all(symbols):
    out = {}
    for s in symbols:
        pats = detect_patterns_for_symbol(s)
        if pats:
            out[s] = pats
    return out


# =========================================================
# 🤖 AI MAX PRO — Deep Dive TECH + NEWS + NewsScore + Multi‑AI
# =========================================================

def ai_deep_dive(symbol, metrics):
    """AI TECH — analiza techniczna PRO."""
    prompt = f"""
Analiza techniczna spółki {symbol}.
Dane:
{json.dumps(metrics, indent=2)}

Zrób:
- trend
- momentum
- ryzyko
- scenariusze
- poziomy kluczowe
- sygnał BUY/SELL/WAIT
"""
    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return res.choices[0].message.content


def ai_news_deep_dive(symbol, metrics, bid, ask, spread_pct):
    """AI NEWS — analiza newsowa PRO."""
    prompt = f"""
Analiza newsowa spółki {symbol}.
Dane:
{json.dumps(metrics, indent=2)}
Bid={bid}, Ask={ask}, Spread={spread_pct}

Zrób:
- news momentum
- news ryzyko
- wpływ na płynność
- scenariusze
"""
    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return res.choices[0].message.content


def ai_news_score_for_df(df):
    """Liczy NewsScore (momentum newsowe + zmienność)."""
    out = {}
    for _, row in df.iterrows():
        score = max(0, min(100, row["VolatilityScore"] * 0.4 + row["MomentumScore"] * 0.6))
        out[row["Symbol"]] = score
    return out


def ai_news_radar(df):
    """AI NEWS RADAR — raport newsowy dla całego rynku."""
    prompt = "Analiza newsowa rynku:\n\n"
    for _, row in df.iterrows():
        prompt += f"{row['Symbol']}: NewsScore={row.get('NewsScore',0)}\n"

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return res.choices[0].message.content


def multi_ai_verdict(top_df):
    """Multi‑AI Panel — 4 style tradingu."""
    prompt = "Analiza 4 stylów tradingu:\n\n"
    for _, row in top_df.iterrows():
        prompt += (
            f"{row['Symbol']}: "
            f"SetupScore={row['SetupScore']:.1f}, "
            f"Trend={row['Trend']}, "
            f"Momentum={row['MomentumScore']:.1f}, "
            f"Volatility={row['VolatilityScore']:.1f}\n"
        )

    prompt += """
Wygeneruj analizę w 4 stylach:
1) Scalper — ultra‑krótki horyzont, agresywny.
2) Day‑trader — intraday, momentum + wolumen.
3) Swing‑trader — 2–10 dni, trend + setup.
4) Analityk techniczny — chłodna analiza wykresu.

Każdy styl: 2–4 zdania, konkretnie, bez lania wody.
"""

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return res.choices[0].message.content


def ai_verdict_for_top5(top_df: pd.DataFrame) -> str:
    if top_df.empty:
        return "Brak spółek do analizy."

    lines = []
    for _, row in top_df.iterrows():
        lines.append(
            f"{row['Symbol']}: "
            f"SetupScore={row['SetupScore']:.1f}, "
            f"Change={row['Change']:+.2f}%, "
            f"Trend={row['Trend']}, "
            f"Signal={row['Signal']}, "
            f"Momentum={row['MomentumScore']:.1f}, "
            f"Volatility={row['VolatilityScore']:.1f}, "
            f"Risk={row['RiskScore']:.1f}"
        )
    context = "\n".join(lines)

    system_prompt = """
Jesteś analitykiem prop‑desk. Mówisz po polsku.
Masz listę maksymalnie 5 spółek z metrykami:
- SetupScore
- Change %
- Trend
- Signal
- MomentumScore
- VolatilityScore
- RiskScore

Twoje zadanie:
1) Dla każdej spółki daj krótki werdykt (1–3 zdania): co jest mocne, co słabe, co obserwować.
2) Na końcu daj zbiorczy komentarz:
   - która spółka wygląda najciekawiej jako setup,
   - gdzie ryzyko jest najwyższe.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Dane spółek:\n{context}"},
    ]

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
    )
    return res.choices[0].message.content


# =========================================================
# 🚀 MAIN — GŁÓWNY INTERFEJS KOMBAJNU MAX PRO
# =========================================================

def main():
    if not st.session_state.symbols:
        st.warning("Dodaj spółki, aby kontynuować.")
        return

    tab_heatmap, tab_chart, tab_scanner, tab_alerts, tab_patterns, tab_deep, tab_multi, tab_news, tab_internet = st.tabs([
        "📊 Heatmap PRO + AI + NewsScore",
        "📈 Wykres PRO",
        "📡 Skaner Sygnałów",
        "🚨 Alerty",
        "📐 Patterny",
        "🧠 AI Deep Dive",
        "🤝 Multi-AI Panel",
        "📰 News Radar",
        "🌐 AI + Internet (globalny czat)",
    ])

    # HEATMAPA
    with tab_heatmap:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        st.subheader("🏆 TOP 5 setupów (kafelki)")

        top_n = min(5, len(df))
        if top_n > 0:
            top_df = df.head(top_n)
            cols = st.columns(top_n)

            for idx, (_, row) in enumerate(top_df.iterrows()):
                with cols[idx]:
                    ss = row["SetupScore"]
                    color = "🟢" if ss >= 60 else ("🟡" if ss >= 40 else "🔴")
                    st.markdown(f"### {color} {row['Symbol']}")
                    st.write(f"**SetupScore:** {ss:.1f}")
                    st.write(f"**Change:** {row['Change']:+.2f}%")
                    st.write(f"**Trend:** {row['Trend']}")
                    st.write(f"**Signal:** {row['Signal']}")
                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}")
                    st.write(f"**Volatility:** {row['VolatilityScore']:.1f}")
                    st.write(f"**Risk:** {row['RiskScore']:.1f}")

            st.markdown("---")

            col_ai1, col_ai2 = st.columns(2)

            with col_ai1:
                if st.button("🧠 Generuj komentarz AI dla TOP 5", key="heat_ai_top5"):
                    with st.spinner("AI analizuje TOP 5 setupów..."):
                        st.session_state.ai_top5_comment = ai_verdict_for_top5(top_df)

            with col_ai2:
                if st.button("📰 Generuj NewsScore", key="heat_news_score"):
                    with st.spinner("AI liczy NewsScore..."):
                        st.session_state.news_scores = ai_news_score_for_df(df)

            if st.session_state.ai_top5_comment:
                st.subheader("🧠 Komentarz AI (prop‑desk)")
                st.markdown(st.session_state.ai_top5_comment)

        if st.session_state.news_scores:
            df["NewsScore"] = df["Symbol"].map(st.session_state.news_scores).fillna(0.0)

        st.markdown("---")
        st.subheader("📊 Pełna tabela — Heatmapa PRO")
        st.dataframe(style_heatmap(df), use_container_width=True)

    # WYKRES PRO
    with tab_chart:
        st.subheader("📈 Wykres PRO")
        symbol_for_chart = st.selectbox(
            "Wybierz spółkę do wykresu:",
            st.session_state.symbols,
            key="chart_select",
        )
        plot_pro_chart(symbol_for_chart)

    # SKANER SYGNAŁÓW
    with tab_scanner:
        st.subheader("📡 BUY / SELL Radar")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        scan_df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        buy_df = scan_df[
            (scan_df["Signal"] == "BUY") &
            (scan_df["Trend"] == "UP") &
            (scan_df["SetupScore"] >= 60) &
            (scan_df["MomentumScore"] >= 55)
        ]

        sell_df = scan_df[
            (scan_df["Signal"] == "SELL") &
            (scan_df["Trend"] == "DOWN") &
            (scan_df["SetupScore"] >= 50)
        ]

        st.markdown("## 🟢 BUY Radar")
        if buy_df.empty:
            st.info("Brak mocnych sygnałów BUY.")
        else:
            cols = st.columns(min(5, len(buy_df)))
            for idx, (_, row) in enumerate(buy_df.iterrows()):
                with cols[idx % len(cols)]:
                    st.markdown(f"### 🟢 {row['Symbol']}")
                    st.write(f"SetupScore: {row['SetupScore']:.1f}")
                    st.write(f"Momentum: {row['MomentumScore']:.1f}")
                    st.write(f"Trend: {row['Trend']}")
                    st.write(f"Change: {row['Change']:+.2f}%")

        st.markdown("---")

        st.markdown("## 🔴 SELL Radar")
        if sell_df.empty:
            st.info("Brak mocnych sygnałów SELL.")
        else:
            cols = st.columns(min(5, len(sell_df)))
            for idx, (_, row) in enumerate(sell_df.iterrows()):
                with cols[idx % len(cols)]:
                    st.markdown(f"### 🔴 {row['Symbol']}")
                    st.write(f"SetupScore: {row['SetupScore']:.1f}")
                    st.write(f"Volatility: {row['VolatilityScore']:.1f}")
                    st.write(f"Trend: {row['Trend']}")
                    st.write(f"Change: {row['Change']:+.2f}%")

        st.markdown("---")
        st.subheader("📊 Pełna tabela sygnałów")
        st.dataframe(
            scan_df[["Symbol", "Signal", "Trend", "SetupScore", "MomentumScore", "VolatilityScore", "RiskScore"]],
            use_container_width=True,
        )

    # ALERTY
    with tab_alerts:
        st.subheader("🚨 Alerty z rynku")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        alert_df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        alerts = generate_alerts(alert_df)

        if not alerts:
            st.info("Brak alertów.")
        else:
            for a in alerts:
                st.write("• " + a)

    # PATTERNY
    with tab_patterns:
        st.subheader("📐 Patterny techniczne")

        patterns_all = detect_patterns_all(st.session_state.symbols)

        if not patterns_all:
            st.info("Brak patternów.")
        else:
            for sym, pats in patterns_all.items():
                st.markdown(f"### {sym}")
                for p in pats:
                    st.write("• " + p)
                st.markdown("---")

    # AI DEEP DIVE
    with tab_deep:
        st.subheader("🧠 AI Deep Dive — TECH + NEWS + Entry Risk")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        deep_df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        symbol_for_deep = st.selectbox(
            "Wybierz spółkę do analizy AI:",
            deep_df["Symbol"].tolist(),
            key="deep_select",
        )
        metrics = deep_df[deep_df["Symbol"] == symbol_for_deep].iloc[0].to_dict()

        bid, ask, spread_pct = get_bid_ask(symbol_for_deep)

        st.markdown("### 📉 Ryzyko wejścia")
        st.write(f"Bid: {bid}")
        st.write(f"Ask: {ask}")
        st.write(f"Spread%: {spread_pct}")
        st.write("---")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("🔍 AI TECH Deep Dive", key="deep_ai_tech"):
                with st.spinner("AI analizuje TECH..."):
                    st.session_state.ai_deep_dive_cache[symbol_for_deep] = ai_deep_dive(symbol_for_deep, metrics)

        with col2:
            if st.button("📰 AI NEWS Deep Dive", key="deep_ai_news"):
                with st.spinner("AI analizuje NEWS..."):
                    st.session_state.ai_news_deep_cache[symbol_for_deep] = ai_news_deep_dive(
                        symbol_for_deep, metrics, bid, ask, spread_pct
                    )

        if symbol_for_deep in st.session_state.ai_deep_dive_cache:
            st.subheader("🧠 AI TECH")
            st.markdown(st.session_state.ai_deep_dive_cache[symbol_for_deep])

        if symbol_for_deep in st.session_state.ai_news_deep_cache:
            st.subheader("📰 AI NEWS")
            st.markdown(st.session_state.ai_news_deep_cache[symbol_for_deep])

    # MULTI-AI PANEL
    with tab_multi:
        st.subheader("🤝 Multi-AI Panel — 4 style tradingu")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        multi_df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        top_n = min(5, len(multi_df))
        top_df = multi_df.head(top_n)

        if st.button("🤝 Generuj Multi-AI werdykt", key="multi_ai_btn"):
            with st.spinner("AI generuje panel..."):
                st.session_state.ai_multi_comment = multi_ai_verdict(top_df)

        if st.session_state.ai_multi_comment:
            st.subheader("🤝 Multi-AI Panel")
            st.markdown(st.session_state.ai_multi_comment)

    # NEWS RADAR
    with tab_news:
        st.subheader("📰 News Radar — NewsScore + AI raport")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        news_df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        if st.session_state.news_scores:
            news_df["NewsScore"] = news_df["Symbol"].map(st.session_state.news_scores).fillna(0.0)

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📰 Generuj NewsScore", key="news_score_btn"):
                with st.spinner("AI liczy NewsScore..."):
                    st.session_state.news_scores = ai_news_score_for_df(news_df)
                    news_df["NewsScore"] = news_df["Symbol"].map(st.session_state.news_scores).fillna(0.0)

        with col2:
            if st.button("📡 Generuj News Radar", key="news_radar_btn"):
                with st.spinner("AI generuje NewsRadar..."):
                    st.session_state.ai_news_radar_comment = ai_news_radar(news_df)

        st.markdown("---")

        if st.session_state.news_scores:
            st.subheader("📊 Tabela z NewsScore")
            st.dataframe(style_heatmap(news_df), use_container_width=True)

        if st.session_state.ai_news_radar_comment:
            st.subheader("📰 AI News Radar — komentarz")
            st.markdown(st.session_state.ai_news_radar_comment)

    # GLOBALNY CZAT AI + INTERNET PRO
    with tab_internet:
        st.subheader("🌐 Globalny czat AI + Internet PRO")

        for m in st.session_state.internet_chat:
            if m["role"] == "user":
                st.markdown(f"**Ty:** {m['content']}")
            else:
                st.markdown(f"**AI:** {m['content']}")

        st.markdown("---")

        user_msg = st.text_input(
            "Twoje pytanie (AI + Internet):",
            key="internet_input_box",
        )

        col1, col2 = st.columns(2)

        with col1:
            send = st.button("Wyślij", type="primary", key="internet_send")

        with col2:
            clear = st.button("Wyczyść czat", key="internet_clear")

        if send and user_msg.strip():
            st.session_state.internet_chat.append({"role": "user", "content": user_msg})
            answer = ai_with_internet_answer(user_msg, st.session_state.internet_chat)
            st.session_state.internet_chat.append({"role": "assistant", "content": answer})
            st.rerun()

        if clear:
            st.session_state.internet_chat = []
            st.rerun()


if __name__ == "__main__":
    main()
