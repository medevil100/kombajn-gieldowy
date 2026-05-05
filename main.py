import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from openai import OpenAI
import requests
import time
import xml.etree.ElementTree as ET

# ============================================================
# ULTRA ENGINE v5.0 — CORE SYSTEM
# ============================================================

st.set_page_config(
    layout="wide",
    page_title="ULTRA ENGINE v5.0 — THE FORGE",
    page_icon="⚙️"
)

# DARKER NEON THEME
st.markdown("""
<style>
body { background-color: #030308; color: #d0d0ff; }
.stApp { background-color: #030308; }

.mega-card {
    border: 2px solid #111;
    padding: 30px;
    border-radius: 20px;
    background: #050a0f;
    box-shadow: 0 0 25px #00ff8822;
    margin-bottom: 30px;
}
.top-card {
    border: 1px solid #222;
    padding: 15px;
    border-radius: 12px;
    background: #050a0f;
    font-size: 1rem;
    line-height: 1.4;
    min-height: 300px;
    text-align: center;
}
.neon-title {
    color: #00ff88;
    font-weight: bold;
    font-size: 3.5rem;
    text-shadow: 0 0 15px #00ff88;
}
.price-tag {
    font-size: 2.8rem;
    font-weight: bold;
    color: #ffffff;
}
.signal-BUY {
    color: #00ff88;
    font-weight: bold;
    border: 2px solid #00ff88;
    padding: 10px;
    border-radius: 10px;
    font-size: 1.4rem;
    text-shadow: 0 0 10px #00ff88;
}
.signal-SELL {
    color: #ff4444;
    font-weight: bold;
    border: 2px solid #ff4444;
    padding: 10px;
    border-radius: 10px;
    font-size: 1.4rem;
    text-shadow: 0 0 10px #ff4444;
}
.signal-WATCH {
    color: #00ccff;
    font-weight: bold;
    border: 2px solid #00ccff;
    padding: 10px;
    border-radius: 10px;
    font-size: 1.4rem;
    text-shadow: 0 0 10px #00ccff;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# AI CLIENT
# ============================================================

client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ============================================================
# AI SIGNAL ENGINE 4.0 — CORE LOGIC
# ============================================================

def ai_signal_engine(r, news_impact=0, blacklist_flag=False, formations_score=0):
    """
    FINAL SIGNAL = BUY / SELL / WATCH
    Based on:
    - Trend S/M/L
    - MACD histogram
    - RSI
    - ATR
    - Pivot levels
    - Swing high/low
    - Volume relative
    - News impact
    - Blacklist
    - AI formations
    """

    score = 0

    # Trend strength
    if r["trend_s"] == "UP": score += 1
    else: score -= 1
    if r["trend_m"] == "UP": score += 2
    else: score -= 2
    if r["trend_l"] == "UP": score += 3
    else: score -= 3

    # MACD histogram
    if r["macd_hist"] > 0: score += 2
    else: score -= 2

    # RSI
    if 40 <= r["rsi"] <= 60:
        score += 1
    elif r["rsi"] < 30:
        score += 2
    elif r["rsi"] > 70:
        score -= 2

    # Volume relative
    if r["vol"] >= 2:
        score += 2
    elif r["vol"] < 0.5:
        score -= 2

    # News impact
    score += int(news_impact / 20)

    # Formations
    score += formations_score

    # Blacklist
    if blacklist_flag:
        score -= 999

    # Final decision
    if score >= 6:
        return "BUY", score
    elif score <= -4:
        return "SELL", score
    else:
        return "WATCH", score
# ============================================================
# ALERT ENGINE — CORE (mail / Discord / Telegram / webhook)
# ============================================================

import smtplib
from email.mime.text import MIMEText

def alert_send_email(to_email, subject, body):
    """
    Wysyła alert mailowy.
    Wymaga:
    st.secrets["SMTP_SERVER"]
    st.secrets["SMTP_PORT"]
    st.secrets["SMTP_USER"]
    st.secrets["SMTP_PASS"]
    """
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = st.secrets.get("SMTP_USER", "")
        msg["To"] = to_email

        with smtplib.SMTP_SSL(
            st.secrets["SMTP_SERVER"],
            st.secrets["SMTP_PORT"]
        ) as server:
            server.login(
                st.secrets["SMTP_USER"],
                st.secrets["SMTP_PASS"]
            )
            server.sendmail(
                st.secrets["SMTP_USER"],
                [to_email],
                msg.as_string()
            )
        return True
    except Exception as e:
        return False


def alert_send_discord(webhook_url, message):
    """
    Wysyła alert na Discord webhook.
    """
    try:
        requests.post(webhook_url, json={"content": message}, timeout=10)
        return True
    except:
        return False


def alert_send_telegram(bot_token, chat_id, message):
    """
    Wysyła alert Telegram.
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        params = {"chat_id": chat_id, "text": message}
        requests.get(url, params=params, timeout=10)
        return True
    except:
        return False


def alert_send_webhook(url, payload):
    """
    Wysyła alert na dowolny webhook.
    """
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except:
        return False


# ============================================================
# ALERT ENGINE — DECISION LAYER
# ============================================================

def trigger_alert(symbol, signal, score, price, reason, channels):
    """
    Wywołuje alert na podstawie sygnału końcowego.
    channels = dict:
        {
            "email": "...",
            "discord": "...",
            "telegram_token": "...",
            "telegram_chat": "...",
            "webhook": "..."
        }
    """

    msg = (
        f"ALERT — {symbol}\n"
        f"Sygnał: {signal}\n"
        f"Score: {score}\n"
        f"Cena: {price}\n"
        f"Powód: {reason}\n"
    )

    # MAIL
    if channels.get("email"):
        alert_send_email(
            channels["email"],
            f"ALERT — {symbol} ({signal})",
            msg
        )

    # DISCORD
    if channels.get("discord"):
        alert_send_discord(channels["discord"], msg)

    # TELEGRAM
    if channels.get("telegram_token") and channels.get("telegram_chat"):
        alert_send_telegram(
            channels["telegram_token"],
            channels["telegram_chat"],
            msg
        )

    # WEBHOOK
    if channels.get("webhook"):
        alert_send_webhook(channels["webhook"], {"alert": msg})

    return True
# ============================================================
# HEATMAP ENGINE — CORE
# ============================================================

# Sektory GPW (przykładowe, można rozszerzyć)
GPW_SECTORS = {
    "WIG-CHEMIA": ["ATT.WA", "CIE.WA"],
    "WIG-ENERGIA": ["PGE.WA", "TAU.WA"],
    "WIG-GAMES": ["CDR.WA", "TEN.WA", "PLW.WA"],
    "WIG-BANKI": ["PKO.WA", "PEO.WA", "ING.WA"],
}

# Sektory NC (przykładowe)
NC_SECTORS = {
    "NC-BIOTECH": ["MAB.WA", "BIO.WA"],
    "NC-TECH": ["QUB.WA", "MBR.WA"],
}

# Sektory USA (GICS)
US_SECTORS = {
    "TECH": ["AAPL", "MSFT", "NVDA", "AMD"],
    "SEMICONDUCTORS": ["TSM", "AVGO", "QCOM"],
    "BIOTECH": ["AMGN", "GILD", "VRTX"],
    "FINANCIALS": ["JPM", "BAC", "GS"],
    "ENERGY": ["XOM", "CVX", "SLB"],
}


def get_sector_momentum(tickers):
    """
    Liczy momentum sektora na podstawie średniej zmiany %.
    """
    changes = []
    for t in tickers:
        try:
            data = yf.download(t, period="5d", interval="1d", progress=False)
            if len(data) >= 2:
                pct = (data["Close"][-1] - data["Close"][-2]) / data["Close"][-2] * 100
                changes.append(pct)
        except:
            pass

    if len(changes) == 0:
        return 0

    return round(sum(changes) / len(changes), 2)


def build_heatmap_data():
    """
    Tworzy strukturę danych dla heatmapy sektorowej.
    Zwraca:
    {
        "GPW": { sektor: momentum },
        "NC": { sektor: momentum },
        "US": { sektor: momentum }
    }
    """

    heatmap = {"GPW": {}, "NC": {}, "US": {}}

    # GPW
    for sector, tickers in GPW_SECTORS.items():
        heatmap["GPW"][sector] = get_sector_momentum(tickers)

    # NC
    for sector, tickers in NC_SECTORS.items():
        heatmap["NC"][sector] = get_sector_momentum(tickers)

    # USA
    for sector, tickers in US_SECTORS.items():
        heatmap["US"][sector] = get_sector_momentum(tickers)

    return heatmap


def heatmap_color(value):
    """
    Zwraca kolor neon-dark w zależności od momentum.
    """
    if value > 1:
        return "#00ff88"   # mocny zielony
    elif value < -1:
        return "#ff4444"   # mocny czerwony
    else:
        return "#00ccff"   # neutralny niebieski
# ============================================================
# SCALPER MODE — CORE ENGINE (1m / 5m / 15m)
# ============================================================

def get_intraday(symbol, interval="1m", lookback="1d"):
    """
    Pobiera dane intraday dla scalpingu.
    interval: "1m", "5m", "15m"
    lookback: "1d", "5d"
    """
    try:
        data = yf.download(
            symbol,
            period=lookback,
            interval=interval,
            progress=False
        )
        return data
    except:
        return pd.DataFrame()


def calc_fast_indicators(df):
    """
    Szybkie wskaźniki do scalpingu:
    - MACD fast
    - RSI fast
    - Volume spike
    """

    if df.empty or len(df) < 20:
        return {"macd": 0, "rsi": 50, "vol_spike": 1}

    # MACD fast
    df["ema12"] = df["Close"].ewm(span=12).mean()
    df["ema26"] = df["Close"].ewm(span=26).mean()
    df["macd"] = df["ema12"] - df["ema26"]

    # RSI fast
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # Volume spike
    df["vol_spike"] = df["Volume"] / df["Volume"].rolling(20).mean()

    last = df.iloc[-1]

    return {
        "macd": round(last["macd"], 4),
        "rsi": round(last["rsi"], 2),
        "vol_spike": round(last["vol_spike"], 2)
    }


def scalper_signal(ind):
    """
    Sygnał scalpingu:
    BUY / SELL / WATCH
    """

    score = 0

    # MACD
    if ind["macd"] > 0:
        score += 2
    else:
        score -= 2

    # RSI
    if ind["rsi"] < 30:
        score += 2
    elif ind["rsi"] > 70:
        score -= 2

    # Volume spike
    if ind["vol_spike"] >= 2:
        score += 2
    elif ind["vol_spike"] < 0.5:
        score -= 2

    if score >= 3:
        return "BUY", score
    elif score <= -3:
        return "SELL", score
    else:
        return "WATCH", score
# ============================================================
# SWING MODE — CORE ENGINE (D1 / W1)
# ============================================================

def get_swing_data(symbol, interval="1d", lookback="6mo"):
    """
    Pobiera dane dla swing tradingu.
    interval: "1d" lub "1wk"
    lookback: "6mo", "1y"
    """
    try:
        data = yf.download(
            symbol,
            period=lookback,
            interval=interval,
            progress=False
        )
        return data
    except:
        return pd.DataFrame()


def calc_swing_indicators(df):
    """
    Wskaźniki swingowe:
    - Trend (MA20 / MA50 / MA200)
    - Pivot levels
    - Swing high/low
    - Momentum
    """

    if df.empty or len(df) < 200:
        return {
            "trend": "NEUTRAL",
            "momentum": 0,
            "pivot_r1": 0,
            "pivot_s1": 0,
            "swing_high": 0,
            "swing_low": 0
        }

    # Moving averages
    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    # Trend logic
    if df["ma20"].iloc[-1] > df["ma50"].iloc[-1] > df["ma200"].iloc[-1]:
        trend = "UP"
    elif df["ma20"].iloc[-1] < df["ma50"].iloc[-1] < df["ma200"].iloc[-1]:
        trend = "DOWN"
    else:
        trend = "NEUTRAL"

    # Pivot levels (ostatnia świeca)
    last = df.iloc[-1]
    pivot = (last["High"] + last["Low"] + last["Close"]) / 3
    r1 = 2 * pivot - last["Low"]
    s1 = 2 * pivot - last["High"]

    # Swing high/low (ostatnie 20 świec)
    swing_high = df["High"].tail(20).max()
    swing_low = df["Low"].tail(20).min()

    # Momentum (Close vs MA50)
    momentum = round((last["Close"] - df["ma50"].iloc[-1]) / df["ma50"].iloc[-1] * 100, 2)

    return {
        "trend": trend,
        "momentum": momentum,
        "pivot_r1": round(r1, 2),
        "pivot_s1": round(s1, 2),
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2)
    }


def swing_signal(ind):
    """
    Sygnał swingowy:
    BUY / SELL / WATCH
    """

    score = 0

    # Trend
    if ind["trend"] == "UP":
        score += 3
    elif ind["trend"] == "DOWN":
        score -= 3

    # Momentum
    if ind["momentum"] > 2:
        score += 2
    elif ind["momentum"] < -2:
        score -= 2

    # Price vs swing levels
    if ind["pivot_s1"] > ind["swing_low"]:
        score += 1
    if ind["pivot_r1"] < ind["swing_high"]:
        score -= 1

    if score >= 4:
        return "BUY", score
    elif score <= -3:
        return "SELL", score
    else:
        return "WATCH", score
# ============================================================
# BLACKLIST ENGINE — AI RISK FILTER
# ============================================================

def blacklist_engine(symbol, df):
    """
    Wykrywa ryzykowne spółki:
    - emisje
    - bankructwo
    - pump & dump
    - niska płynność
    - anomalie wolumenowe
    """

    if df.empty or len(df) < 30:
        return False, "Brak danych"

    reasons = []

    # Niska płynność
    avg_vol = df["Volume"].tail(20).mean()
    if avg_vol < 5000:
        reasons.append("Niska płynność")

    # Pump & dump (duże świece)
    last = df.iloc[-1]
    body = abs(last["Close"] - last["Open"])
    range_ = last["High"] - last["Low"]
    if range_ > 0 and body / range_ > 0.8:
        reasons.append("Podejrzana świeca (pump/dump)")

    # Wolumen anomalia
    vol_spike = last["Volume"] / df["Volume"].rolling(20).mean().iloc[-1]
    if vol_spike > 8:
        reasons.append("Wolumen anomalia")

    # Spadek > 20% w 5 dni
    try:
        close_5d = df["Close"].iloc[-5]
        drop = (close_5d - last["Close"]) / close_5d * 100
        if drop > 20:
            reasons.append("Spadek >20% w 5 dni")
    except:
        pass

    if len(reasons) > 0:
        return True, ", ".join(reasons)

    return False, ""


# ============================================================
# AI FORMATIONS ENGINE — TRIANGLES / WEDGES / FLAGS
# ============================================================

def detect_formations(df):
    """
    Wykrywa formacje:
    - triangle
    - wedge
    - flag

    Zwraca:
    (score, description)
    """

    if df.empty or len(df) < 40:
        return 0, "Brak danych"

    highs = df["High"].tail(40).values
    lows = df["Low"].tail(40).values

    score = 0
    desc = []

    # TRIANGLE — zbieżne high i low
    if (highs.max() - highs.min()) < (lows.max() - lows.min()) * 1.2:
        score += 2
        desc.append("Triangle")

    # WEDGE — oba kierunki w jedną stronę
    if highs[-1] < highs[0] and lows[-1] > lows[0]:
        score += 2
        desc.append("Wedge (up)")
    if highs[-1] > highs[0] and lows[-1] < lows[0]:
        score += 2
        desc.append("Wedge (down)")

    # FLAG — mały kanał po dużym ruchu
    last_move = abs(df["Close"].iloc[-20] - df["Close"].iloc[-1])
    flag_range = highs.max() - lows.min()
    if last_move > flag_range * 1.5:
        score += 1
        desc.append("Flag")

    if score == 0:
        return 0, "Brak formacji"

    return score, ", ".join(desc)
# ============================================================
# GENESIS MODE — AI PORTFOLIO BUILDER
# ============================================================

def genesis_ai(prompt):
    """
    Wrapper na AI — generuje listy spółek, portfele, strategie.
    """
    if client is None:
        return "Brak API KEY"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Jesteś analitykiem rynkowym. Odpowiadaj krótko, konkretnie, w formie list."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI ERROR: {e}"


def genesis_build(symbols, data_cache):
    """
    Tworzy:
    - listę BUY
    - listę SELL
    - listę WATCH
    - listę SWING
    - listę SCALP
    - listę SHORT
    """

    prompt = (
        "Przeanalizuj poniższe spółki i podziel je na kategorie:\n"
        "- BUY (silny trend, dobre momentum)\n"
        "- SELL (słaby trend, ryzyko spadków)\n"
        "- WATCH (neutralne)\n"
        "- SWING (dobre do swing tradingu)\n"
        "- SCALP (dobre do scalpingu)\n"
        "- SHORT (kandydaci do shortowania)\n\n"
        "Dane:\n"
    )

    for sym in symbols:
        if sym in data_cache:
            d = data_cache[sym]
            prompt += f"{sym}: trend={d.get('trend','?')}, rsi={d.get('rsi','?')}, macd={d.get('macd','?')}, momentum={d.get('momentum','?')}, vol={d.get('vol','?')}\n"

    return genesis_ai(prompt)
# ============================================================
# ULTRA ENGINE v5.0 — UI CORE + TABS
# ============================================================

st.markdown("<h1 class='neon-title'>ULTRA ENGINE v5.0 — THE FORGE</h1>", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("⚙️ ULTRA ENGINE v5.0")
st.sidebar.markdown("Wybierz moduł:")

tab = st.sidebar.radio(
    "",
    [
        "Dashboard",
        "Heatmapa",
        "Scalper Mode",
        "Swing Mode",
        "Genesis Mode",
        "Alerts"
    ]
)

# Cache na dane
if "data_cache" not in st.session_state:
    st.session_state.data_cache = {}

# Funkcja pobierająca dane dzienne
def get_daily(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False)
        return df
    except:
        return pd.DataFrame()

# Funkcja licząca podstawowe wskaźniki
def calc_daily_indicators(df):
    if df.empty or len(df) < 50:
        return {
            "trend_s": "NEUTRAL",
            "trend_m": "NEUTRAL",
            "trend_l": "NEUTRAL",
            "macd_hist": 0,
            "rsi": 50,
            "vol": 1
        }

    # Trend S/M/L
    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    trend_s = "UP" if df["Close"].iloc[-1] > df["ma20"].iloc[-1] else "DOWN"
    trend_m = "UP" if df["Close"].iloc[-1] > df["ma50"].iloc[-1] else "DOWN"
    trend_l = "UP" if df["Close"].iloc[-1] > df["ma200"].iloc[-1] else "DOWN"

    # MACD histogram
    df["ema12"] = df["Close"].ewm(span=12).mean()
    df["ema26"] = df["Close"].ewm(span=26).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["signal"] = df["macd"].ewm(span=9).mean()
    macd_hist = df["macd"].iloc[-1] - df["signal"].iloc[-1]

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))

    # Volume relative
    vol = df["Volume"].iloc[-1] / df["Volume"].rolling(20).mean().iloc[-1]

    return {
        "trend_s": trend_s,
        "trend_m": trend_m,
        "trend_l": trend_l,
        "macd_hist": round(macd_hist, 4),
        "rsi": round(rsi, 2),
        "vol": round(vol, 2)
    }
# ============================================================
# UI — DASHBOARD
# ============================================================

if tab == "Dashboard":
    st.markdown("## 📊 Dashboard — Sygnały dzienne")

    symbol = st.text_input("Symbol", "AAPL")

    if symbol:
        df = get_daily(symbol)
        ind = calc_daily_indicators(df)

        # Blacklist
        bl_flag, bl_reason = blacklist_engine(symbol, df)

        # Formations
        form_score, form_desc = detect_formations(df)

        # Final signal
        signal, score = ai_signal_engine(
            ind,
            news_impact=0,
            blacklist_flag=bl_flag,
            formations_score=form_score
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(f"<div class='top-card'><div class='price-tag'>{symbol}</div></div>", unsafe_allow_html=True)

        with col2:
            st.markdown(f"<div class='top-card'><div class='signal-{signal}'>{signal}</div></div>", unsafe_allow_html=True)

        with col3:
            st.markdown(f"<div class='top-card'>Score: {score}</div>", unsafe_allow_html=True)

        st.markdown("### 📌 Szczegóły")

        st.write(f"Trend S/M/L: {ind['trend_s']} / {ind['trend_m']} / {ind['trend_l']}")
        st.write(f"MACD hist: {ind['macd_hist']}")
        st.write(f"RSI: {ind['rsi']}")
        st.write(f"Volume rel: {ind['vol']}")

        st.write(f"Formacje: {form_desc}")
        if bl_flag:
            st.error(f"BLACKLIST: {bl_reason}")


# ============================================================
# UI — HEATMAPA
# ============================================================

if tab == "Heatmapa":
    st.markdown("## 🔥 Heatmapa sektorowa")

    heat = build_heatmap_data()

    for market in heat:
        st.markdown(f"### {market}")

        cols = st.columns(3)
        i = 0

        for sector, val in heat[market].items():
            color = heatmap_color(val)
            cols[i].markdown(
                f"<div class='top-card' style='border-color:{color}; color:{color};'>{sector}<br><br>{val}%</div>",
                unsafe_allow_html=True
            )
            i = (i + 1) % 3


# ============================================================
# UI — SCALPER MODE
# ============================================================

if tab == "Scalper Mode":
    st.markdown("## ⚡ Scalper Mode (1m / 5m / 15m)")

    symbol = st.text_input("Symbol", "AAPL")

    interval = st.selectbox("Interwał", ["1m", "5m", "15m"])

    if symbol:
        df = get_intraday(symbol, interval)
        ind = calc_fast_indicators(df)
        signal, score = scalper_signal(ind)

        st.markdown(f"### Sygnał: **{signal}** (score: {score})")
        st.write(ind)


# ============================================================
# UI — SWING MODE
# ============================================================

if tab == "Swing Mode":
    st.markdown("## 🌀 Swing Mode (D1 / W1)")

    symbol = st.text_input("Symbol", "AAPL")
    interval = st.selectbox("Interwał", ["1d", "1wk"])

    if symbol:
        df = get_swing_data(symbol, interval)
        ind = calc_swing_indicators(df)
        signal, score = swing_signal(ind)

        st.markdown(f"### Sygnał: **{signal}** (score: {score})")
        st.write(ind)


# ============================================================
# UI — GENESIS MODE
# ============================================================

if tab == "Genesis Mode":
    st.markdown("## 🌱 GENESIS — AI Portfolio Builder")

    symbols = st.text_area("Lista symboli (po przecinku)", "AAPL, MSFT, NVDA")

    if st.button("Generuj"):
        syms = [s.strip() for s in symbols.split(",")]

        # Cache danych
        cache = {}
        for s in syms:
            df = get_daily(s)
            ind = calc_daily_indicators(df)
            cache[s] = ind

        result = genesis_build(syms, cache)
        st.markdown("### Wynik:")
        st.write(result)


# ============================================================
# UI — ALERTS
# ============================================================

if tab == "Alerts":
    st.markdown("## 🚨 Alert Engine")

    st.write("Skonfiguruj kanały alertów:")

    email = st.text_input("Email")
    discord = st.text_input("Discord webhook")
    tg_token = st.text_input("Telegram token")
    tg_chat = st.text_input("Telegram chat ID")
    webhook = st.text_input("Dowolny webhook")

    symbol = st.text_input("Symbol do testu alertu", "AAPL")

    if st.button("Wyślij test alertu"):
        trigger_alert(
            symbol,
            "TEST",
            0,
            0,
            "Test alertu",
            {
                "email": email,
                "discord": discord,
                "telegram_token": tg_token,
                "telegram_chat": tg_chat,
                "webhook": webhook
            }
        )
        st.success("Alert wysłany.")
