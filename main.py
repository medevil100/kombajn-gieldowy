import streamlit as st
import pandas as pd
import numpy as np
import requests
from openai import OpenAI

# ============================================================
# ULTRA ENGINE v6.0 — REAL DATA + AI BRAIN
# ============================================================

st.set_page_config(
    layout="wide",
    page_title="ULTRA ENGINE v6.0 — THE SWORD",
    page_icon="⚔️"
)

# ----------------- STYLE -----------------
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
    min-height: 120px;
    text-align: center;
}
.neon-title {
    color: #00ff88;
    font-weight: bold;
    font-size: 3.0rem;
    text-shadow: 0 0 15px #00ff88;
}
.price-tag {
    font-size: 2.2rem;
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
# CLIENTS
# ============================================================

ALPHA_KEY = st.secrets.get("ALPHAVANTAGE_API_KEY", "")
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ============================================================
# ALPHA VANTAGE DATA ENGINE (REAL OHLCV)
# ============================================================

BASE_URL = "https://www.alphavantage.co/query"

def av_get_daily(symbol, outputsize="compact"):
    if not ALPHA_KEY:
        return pd.DataFrame()

    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": outputsize,
        "apikey": ALPHA_KEY
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        data = r.json()
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return pd.DataFrame()

        rows = []
        for t, v in ts.items():
            rows.append({
                "time": t,
                "open": float(v["1. open"]),
                "high": float(v["2. high"]),
                "low": float(v["3. low"]),
                "close": float(v["4. close"]),
                "volume": float(v["6. volume"])
            })
        df = pd.DataFrame(rows)
        df = df.sort_values("time")
        df.set_index("time", inplace=True)
        return df
    except:
        return pd.DataFrame()

def av_get_intraday(symbol, interval="5min"):
    if not ALPHA_KEY:
        return pd.DataFrame()

    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "outputsize": "compact",
        "apikey": ALPHA_KEY
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        data = r.json()
        key = f"Time Series ({interval})"
        ts = data.get(key, {})
        if not ts:
            return pd.DataFrame()

        rows = []
        for t, v in ts.items():
            rows.append({
                "time": t,
                "open": float(v["1. open"]),
                "high": float(v["2. high"]),
                "low": float(v["3. low"]),
                "close": float(v["4. close"]),
                "volume": float(v["5. volume"])
            })
        df = pd.DataFrame(rows)
        df = df.sort_values("time")
        df.set_index("time", inplace=True)
        return df
    except:
        return pd.DataFrame()

# ============================================================
# INDICATORS
# ============================================================

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal).mean()
    hist = macd - sig
    return macd, sig, hist

def calc_daily_indicators(df):
    if df is None or df.empty or len(df) < 30:
        return {
            "trend_s": "NEUTRAL",
            "trend_m": "NEUTRAL",
            "trend_l": "NEUTRAL",
            "macd_hist": 0.0,
            "rsi": 50.0,
            "vol": 1.0
        }

    df = df.copy()
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)

    df["ma20"] = close.rolling(20).mean()
    df["ma50"] = close.rolling(50).mean()
    df["ma200"] = close.rolling(200).mean()

    last_close = float(close.iloc[-1])
    ma20 = float(df["ma20"].iloc[-1]) if not np.isnan(df["ma20"].iloc[-1]) else last_close
    ma50 = float(df["ma50"].iloc[-1]) if not np.isnan(df["ma50"].iloc[-1]) else last_close
    ma200 = float(df["ma200"].iloc[-1]) if not np.isnan(df["ma200"].iloc[-1]) else last_close

    trend_s = "UP" if last_close > ma20 else "DOWN"
    trend_m = "UP" if last_close > ma50 else "DOWN"
    trend_l = "UP" if last_close > ma200 else "DOWN"

    macd, sig, hist = calc_macd(close)
    macd_hist = float(hist.iloc[-1])

    rsi = calc_rsi(close)
    rsi_val = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0

    vol_rel = float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-1]) if vol.rolling(20).mean().iloc[-1] != 0 else 1.0

    return {
        "trend_s": trend_s,
        "trend_m": trend_m,
        "trend_l": trend_l,
        "macd_hist": round(macd_hist, 4),
        "rsi": round(rsi_val, 2),
        "vol": round(vol_rel, 2)
    }

def calc_fast_indicators(df):
    if df is None or df.empty or len(df) < 20:
        return {"macd": 0.0, "rsi": 50.0, "vol_spike": 1.0}

    df = df.copy()
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)

    macd, sig, hist = calc_macd(close)
    rsi = calc_rsi(close)
    vol_spike = vol / vol.rolling(20).mean()

    last_macd = float(macd.iloc[-1])
    last_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
    last_vs = float(vol_spike.iloc[-1]) if not np.isnan(vol_spike.iloc[-1]) else 1.0

    return {
        "macd": last_macd,
        "rsi": last_rsi,
        "vol_spike": last_vs
    }

# ============================================================
# SIGNAL ENGINE
# ============================================================

def ai_signal_engine(r):
    score = 0

    score += 1 if r["trend_s"] == "UP" else -1
    score += 2 if r["trend_m"] == "UP" else -2
    score += 3 if r["trend_l"] == "UP" else -3

    score += 2 if r["macd_hist"] > 0 else -2

    if 40 <= r["rsi"] <= 60:
        score += 1
    elif r["rsi"] < 30:
        score += 2
    elif r["rsi"] > 70:
        score -= 2

    if r["vol"] >= 2:
        score += 2
    elif r["vol"] < 0.5:
        score -= 2

    if score >= 6:
        return "BUY", score
    elif score <= -4:
        return "SELL", score
    else:
        return "WATCH", score

def scalper_signal(ind):
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
# GENESIS (AI BRAIN)
# ============================================================

def genesis_ai(prompt):
    if client is None:
        return "Brak OPENAI_API_KEY w secrets."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Jesteś brutalnie szczerym analitykiem rynkowym. Odpowiadasz krótko, w punktach, bez lania wody."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI ERROR: {e}"

def genesis_build(symbols, data_cache):
    prompt = (
        "Przeanalizuj poniższe spółki i podziel je na kategorie:\n"
        "- BUY\n- SELL\n- WATCH\n- SWING\n- SCALP\n- SHORT\n\n"
        "Dane (trend_s, trend_m, trend_l, rsi, macd_hist, vol):\n"
    )

    for sym in symbols:
        if sym in data_cache:
            d = data_cache[sym]
            prompt += (
                f"{sym}: trend_s={d['trend_s']}, trend_m={d['trend_m']}, "
                f"trend_l={d['trend_l']}, rsi={d['rsi']}, macd_hist={d['macd_hist']}, vol={d['vol']}\n"
            )

    return genesis_ai(prompt)

# ============================================================
# HEATMAP (REAL DATA)
# ============================================================

SECTORS = {
    "TECH": ["AAPL", "MSFT", "NVDA", "AMD"],
    "FINANCIALS": ["JPM", "BAC", "GS"],
    "ENERGY": ["XOM", "CVX", "SLB"],
    "CONSUMER": ["AMZN", "WMT", "MCD"],
}

def sector_momentum(symbols):
    changes = []
    for s in symbols:
        df = av_get_daily(s, outputsize="compact")
        if len(df) >= 2:
            c = df["close"].astype(float)
            pct = (c.iloc[-1] - c.iloc[-2]) / c.iloc[-2] * 100
            changes.append(pct)
    return round(sum(changes) / len(changes), 2) if changes else 0.0

def build_heatmap_data():
    heat = {}
    for sector, syms in SECTORS.items():
        heat[sector] = sector_momentum(syms)
    return heat

def heatmap_color(value):
    if value > 1:
        return "#00ff88"
    elif value < -1:
        return "#ff4444"
    else:
        return "#00ccff"

# ============================================================
# UI CORE
# ============================================================

st.markdown("<h1 class='neon-title'>ULTRA ENGINE v6.0 — THE SWORD</h1>", unsafe_allow_html=True)

st.sidebar.title("⚙️ ULTRA ENGINE v6.0")
tab = st.sidebar.radio(
    "",
    [
        "Dashboard",
        "Heatmapa",
        "Scalper",
        "Genesis"
    ]
)

# ============================================================
# UI — DASHBOARD
# ============================================================

if tab == "Dashboard":
    st.markdown("## 📊 Dashboard — dzienny miecz")

    symbol = st.text_input("Symbol akcji", "AAPL")

    if symbol:
        df = av_get_daily(symbol, outputsize="compact")
        if df.empty:
            st.error("Brak danych z API dla tego symbolu.")
        else:
            ind = calc_daily_indicators(df)
            signal, score = ai_signal_engine(ind)

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown(
                    f"<div class='top-card'><div class='price-tag'>{symbol}</div><br>Ostatnia cena: {df['close'].iloc[-1]:.2f}</div>",
                    unsafe_allow_html=True
                )

            with col2:
                st.markdown(
                    f"<div class='top-card'><div class='signal-{signal}'>{signal}</div></div>",
                    unsafe_allow_html=True
                )

            with col3:
                st.markdown(
                    f"<div class='top-card'>Score: {score}<br>RSI: {ind['rsi']}<br>MACD hist: {ind['macd_hist']}</div>",
                    unsafe_allow_html=True
                )

            st.markdown("### Szczegóły wskaźników")
            st.write(ind)

# ============================================================
# UI — HEATMAPA
# ============================================================

if tab == "Heatmapa":
    st.markdown("## 🔥 Heatmapa sektorowa (real data)")

    heat = build_heatmap_data()
    cols = st.columns(3)
    i = 0
    for sector, val in heat.items():
        color = heatmap_color(val)
        cols[i].markdown(
            f"<div class='top-card' style='border-color:{color}; color:{color};'>"
            f"{sector}<br><br>{val:.2f}%</div>",
            unsafe_allow_html=True
        )
        i = (i + 1) % 3

# ============================================================
# UI — SCALPER
# ============================================================

if tab == "Scalper":
    st.markdown("## ⚡ Scalper (intraday, real data)")

    symbol = st.text_input("Symbol (intraday)", "AAPL")
    interval = st.selectbox("Interwał", ["5min", "15min"])

    if symbol:
        df = av_get_intraday(symbol, interval=interval)
        if df.empty:
            st.error("Brak intraday z API dla tego symbolu / interwału.")
        else:
            ind = calc_fast_indicators(df)
            signal, score = scalper_signal(ind)

            st.markdown(f"### Sygnał: **{signal}** (score: {score})")
            st.write(ind)

# ============================================================
# UI — GENESIS
# ============================================================

if tab == "Genesis":
    st.markdown("## 🌱 GENESIS — AI Portfolio Blade")

    symbols = st.text_area("Lista symboli (po przecinku)", "AAPL, MSFT, NVDA")

    if st.button("Analizuj portfel"):
        syms = [s.strip() for s in symbols.split(",") if s.strip()]
        cache = {}
        for s in syms:
            df = av_get_daily(s, outputsize="compact")
            if df.empty:
                continue
            cache[s] = calc_daily_indicators(df)

        if not cache:
            st.error("Brak danych dla podanych symboli.")
        else:
            result = genesis_build(syms, cache)
            st.markdown("### Wynik AI:")
            st.write(result)
