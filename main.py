import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from openai import OpenAI
import requests
import time

# ============================================================
# ULTRA ENGINE v5.1.1 — CORE SYSTEM
# ============================================================

st.set_page_config(
    layout="wide",
    page_title="ULTRA ENGINE v5.1.1 — THE FORGE",
    page_icon="⚙️"
)

# DARK NEON THEME
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
    score = 0

    # Trend strength
    score += 1 if r["trend_s"] == "UP" else -1
    score += 2 if r["trend_m"] == "UP" else -2
    score += 3 if r["trend_l"] == "UP" else -3

    # MACD histogram
    score += 2 if r["macd_hist"] > 0 else -2

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

    if score >= 6:
        return "BUY", score
    elif score <= -4:
        return "SELL", score
    else:
        return "WATCH", score

# ============================================================
# ALERT ENGINE — CORE
# ============================================================

import smtplib
from email.mime.text import MIMEText

def alert_send_email(to_email, subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = st.secrets.get("SMTP_USER", "")
        msg["To"] = to_email

        with smtplplib.SMTP_SSL(
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
    except:
        return False

def alert_send_discord(webhook_url, message):
    try:
        requests.post(webhook_url, json={"content": message}, timeout=10)
        return True
    except:
        return False

def alert_send_telegram(bot_token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        params = {"chat_id": chat_id, "text": message}
        requests.get(url, params=params, timeout=10)
        return True
    except:
        return False

def alert_send_webhook(url, payload):
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except:
        return False

def trigger_alert(symbol, signal, score, price, reason, channels):
    msg = (
        f"ALERT — {symbol}\n"
        f"Sygnał: {signal}\n"
        f"Score: {score}\n"
        f"Cena: {price}\n"
        f"Powód: {reason}\n"
    )

    if channels.get("email"):
        alert_send_email(channels["email"], f"ALERT — {symbol}", msg)

    if channels.get("discord"):
        alert_send_discord(channels["discord"], msg)

    if channels.get("telegram_token") and channels.get("telegram_chat"):
        alert_send_telegram(
            channels["telegram_token"],
            channels["telegram_chat"],
            msg
        )

    if channels.get("webhook"):
        alert_send_webhook(channels["webhook"], {"alert": msg})

    return True

# ============================================================
# HEATMAP ENGINE — CORE
# ============================================================

GPW_SECTORS = {
    "WIG-CHEMIA": ["ATT.WA", "CIE.WA"],
    "WIG-ENERGIA": ["PGE.WA", "TAU.WA"],
    "WIG-GAMES": ["CDR.WA", "TEN.WA", "PLW.WA"],
    "WIG-BANKI": ["PKO.WA", "PEO.WA", "ING.WA"],
}

NC_SECTORS = {
    "NC-BIOTECH": ["MAB.WA", "BIO.WA"],
    "NC-TECH": ["QUB.WA", "MBR.WA"],
}

US_SECTORS = {
    "TECH": ["AAPL", "MSFT", "NVDA", "AMD"],
    "SEMICONDUCTORS": ["TSM", "AVGO", "QCOM"],
    "BIOTECH": ["AMGN", "GILD", "VRTX"],
    "FINANCIALS": ["JPM", "BAC", "GS"],
    "ENERGY": ["XOM", "CVX", "SLB"],
}

def get_sector_momentum(tickers):
    changes = []
    for t in tickers:
        try:
            data = yf.download(t, period="5d", interval="1d", progress=False)
            if len(data) >= 2:
                pct = (data["Close"][-1] - data["Close"][-2]) / data["Close"][-2] * 100
                changes.append(pct)
        except:
            pass

    return round(sum(changes) / len(changes), 2) if changes else 0

def build_heatmap_data():
    heatmap = {"GPW": {}, "NC": {}, "US": {}}

    for sector, tickers in GPW_SECTORS.items():
        heatmap["GPW"][sector] = get_sector_momentum(tickers)

    for sector, tickers in NC_SECTORS.items():
        heatmap["NC"][sector] = get_sector_momentum(tickers)

    for sector, tickers in US_SECTORS.items():
        heatmap["US"][sector] = get_sector_momentum(tickers)

    return heatmap

def heatmap_color(value):
    if value > 1:
        return "#00ff88"
    elif value < -1:
        return "#ff4444"
    else:
        return "#00ccff"
# ============================================================
# SCALPER MODE — CORE ENGINE (1m / 5m / 15m)
# ============================================================

def get_intraday(symbol, interval="1m", lookback="1d"):
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
    if df.empty or len(df) < 20:
        return {"macd": 0.0, "rsi": 50.0, "vol_spike": 1.0}

    df = df.copy()

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
        "macd": float(last["macd"]),
        "rsi": float(last["rsi"]),
        "vol_spike": float(last["vol_spike"])
    }


def scalper_signal(ind):
    import pandas as pd

    if not isinstance(ind, dict):
        if hasattr(ind, "to_dict"):
            ind = ind.to_dict()
        else:
            return "WATCH", 0

    macd = float(ind.get("macd", 0) or 0)
    rsi = float(ind.get("rsi", 50) or 50)
    vol_spike = float(ind.get("vol_spike", 1) or 1)

    score = 0

    score += 2 if macd > 0 else -2

    if rsi < 30:
        score += 2
    elif rsi > 70:
        score -= 2

    if vol_spike >= 2:
        score += 2
    elif vol_spike < 0.5:
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
    if df.empty or len(df) < 200:
        return {
            "trend": "NEUTRAL",
            "momentum": 0,
            "pivot_r1": 0,
            "pivot_s1": 0,
            "swing_high": 0,
            "swing_low": 0
        }

    df = df.copy()

    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    if df["ma20"].iloc[-1] > df["ma50"].iloc[-1] > df["ma200"].iloc[-1]:
        trend = "UP"
    elif df["ma20"].iloc[-1] < df["ma50"].iloc[-1] < df["ma200"].iloc[-1]:
        trend = "DOWN"
    else:
        trend = "NEUTRAL"

    last = df.iloc[-1]
    pivot = (last["High"] + last["Low"] + last["Close"]) / 3
    r1 = 2 * pivot - last["Low"]
    s1 = 2 * pivot - last["High"]

    swing_high = df["High"].tail(20).max()
    swing_low = df["Low"].tail(20).min()

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
    score = 0

    if ind["trend"] == "UP":
        score += 3
    elif ind["trend"] == "DOWN":
        score -= 3

    if ind["momentum"] > 2:
        score += 2
    elif ind["momentum"] < -2:
        score -= 2

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
    if df.empty or len(df) < 30:
        return False, "Brak danych"

    reasons = []

    avg_vol = df["Volume"].tail(20).mean()
    if avg_vol < 5000:
        reasons.append("Niska płynność")

    last = df.iloc[-1]
    body = abs(last["Close"] - last["Open"])
    range_ = last["High"] - last["Low"]
    if range_ > 0 and body / range_ > 0.8:
        reasons.append("Podejrzana świeca (pump/dump)")

    vol_spike = last["Volume"] / df["Volume"].rolling(20).mean().iloc[-1]
    if vol_spike > 8:
        reasons.append("Wolumen anomalia")

    try:
        close_5d = df["Close"].iloc[-5]
        drop = (close_5d - last["Close"]) / close_5d * 100
        if drop > 20:
            reasons.append("Spadek >20% w 5 dni")
    except:
        pass

    if reasons:
        return True, ", ".join(reasons)

    return False, ""


# ============================================================
# AI FORMATIONS ENGINE — TRIANGLES / WEDGES / FLAGS
# ============================================================

def detect_formations(df):
    if df.empty or len(df) < 40:
        return 0, "Brak danych"

    highs = df["High"].tail(40).values
    lows = df["Low"].tail(40).values

    score = 0
    desc = []

    if (highs.max() - highs.min()) < (lows.max() - lows.min()) * 1.2:
        score += 2
        desc.append("Triangle")

    if highs[-1] < highs[0] and lows[-1] > lows[0]:
        score += 2
        desc.append("Wedge (up)")
    if highs[-1] > highs[0] and lows[-1] < lows[0]:
        score += 2
        desc.append("Wedge (down)")

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
    prompt = (
        "Przeanalizuj poniższe spółki i podziel je na kategorie:\n"
        "- BUY\n- SELL\n- WATCH\n- SWING\n- SCALP\n- SHORT\n\n"
        "Dane:\n"
    )

    for sym in symbols:
        if sym in data_cache:
            d = data_cache[sym]
            prompt += f"{sym}: trend={d.get('trend','?')}, rsi={d.get('rsi','?')}, macd={d.get('macd','?')}, momentum={d.get('momentum','?')}, vol={d.get('vol','?')}\n"

    return genesis_ai(prompt)
# ============================================================
# UI — CORE LAYOUT + TABS
# ============================================================

st.markdown("<h1 class='neon-title'>ULTRA ENGINE v5.1.1 — THE FORGE</h1>", unsafe_allow_html=True)

st.sidebar.title("⚙️ ULTRA ENGINE v5.1.1")
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

# Cache
if "data_cache" not in st.session_state:
    st.session_state.data_cache = {}

# ============================================================
# DAILY DATA + INDICATORS (patched v1.1)
# ============================================================

def get_daily(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False)
        return df
    except:
        return pd.DataFrame()


def calc_daily_indicators(df):
    import pandas as pd

    if df is None or df.empty or len(df) < 50:
        return {
            "trend_s": "NEUTRAL",
            "trend_m": "NEUTRAL",
            "trend_l": "NEUTRAL",
            "macd_hist": 0.0,
            "rsi": 50.0,
            "vol": 1.0
        }

    df = df.copy()

    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    last_close = float(df["Close"].iloc[-1])

    ma20_last = float(df["ma20"].iloc[-1]) if not pd.isna(df["ma20"].iloc[-1]) else last_close
    ma50_last = float(df["ma50"].iloc[-1]) if not pd.isna(df["ma50"].iloc[-1]) else last_close
    ma200_last = float(df["ma200"].iloc[-1]) if not pd.isna(df["ma200"].iloc[-1]) else last_close

    trend_s = "UP" if last_close > ma20_last else "DOWN"
    trend_m = "UP" if last_close > ma50_last else "DOWN"
    trend_l = "UP" if last_close > ma200_last else "DOWN"

    df["ema12"] = df["Close"].ewm(span=12).mean()
    df["ema26"] = df["Close"].ewm(span=26).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["signal"] = df["macd"].ewm(span=9).mean()
    macd_hist = float(df["macd"].iloc[-1] - df["signal"].iloc[-1])

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi_val = float(100 - (100 / (1 + rs.iloc[-1]))) if not pd.isna(rs.iloc[-1]) else 50.0

    vol_rel = df["Volume"].iloc[-1] / df["Volume"].rolling(20).mean().iloc[-1]
    vol_rel = float(vol_rel) if not pd.isna(vol_rel) else 1.0

    return {
        "trend_s": trend_s,
        "trend_m": trend_m,
        "trend_l": trend_l,
        "macd_hist": round(macd_hist, 4),
        "rsi": round(rsi_val, 2),
        "vol": round(vol_rel, 2)
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

        bl_flag, bl_reason = blacklist_engine(symbol, df)
        form_score, form_desc = detect_formations(df)

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
