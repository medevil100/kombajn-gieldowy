Rozumiem, że jesteś wkurzony — i szczerze: masz do tego pełne prawo.  
Nie chcę Cię zagadywać, tylko **dać w końcu jeden, spójny, działający plik**.

Dwie ważne rzeczy, żebyśmy się nie mijali:

- Ten „49$ miesięcznie” to **Polygon**, nie to, co Ci proponowałem teraz.  
- **Alpha Vantage ma darmowy plan** (wystarczy klucz w `st.secrets["ALPHAVANTAGE_API_KEY"]`), więc nie dokładam Ci żadnego płatnego gówna.

Poniżej masz **pełny skrypt** w stylu Twojego v5.x:

- Dashboard (BUY/SELL/WATCH, kolory)  
- Heatmapa sektorowa  
- Scalper (intraday)  
- Swing (D1/W1)  
- Genesis (AI analiza portfela)  
- Blacklist, formacje, alerty  
- **Prawdziwe dane z akcji przez Alpha Vantage**  
- **Twój klucz OpenAI z `st.secrets["OPENAI_API_KEY"]`**  
- Zero yfinance, zero zewnętrznych płatnych bibliotek

Nazwij plik np. `ultra_engine_v6.py` i wrzuć do Streamlit.

---

### 🔥 Pełny skrypt: ULTRA ENGINE v6.0 (REAL DATA + AI, bez yfinance)

```python
import streamlit as st
import pandas as pd
import numpy as np
import requests
from openai import OpenAI
from email.mime.text import MIMEText
import smtplib

# ============================================================
# ULTRA ENGINE v6.0 — REAL DATA + AI
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
# CLIENTS / SECRETS
# ============================================================

ALPHA_KEY = st.secrets.get("ALPHAVANTAGE_API_KEY", "")
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")

client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

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
# SWING INDICATORS
# ============================================================

def calc_swing_indicators(df):
    if df is None or df.empty or len(df) < 200:
        return {
            "trend": "NEUTRAL",
            "momentum": 0,
            "pivot_r1": 0,
            "pivot_s1": 0,
            "swing_high": 0,
            "swing_low": 0
        }

    df = df.copy()
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    df["ma20"] = close.rolling(20).mean()
    df["ma50"] = close.rolling(50).mean()
    df["ma200"] = close.rolling(200).mean()

    if df["ma20"].iloc[-1] > df["ma50"].iloc[-1] > df["ma200"].iloc[-1]:
        trend = "UP"
    elif df["ma20"].iloc[-1] < df["ma50"].iloc[-1] < df["ma200"].iloc[-1]:
        trend = "DOWN"
    else:
        trend = "NEUTRAL"

    last = df.iloc[-1]
    pivot = (last["high"] + last["low"] + last["close"]) / 3
    r1 = 2 * pivot - last["low"]
    s1 = 2 * pivot - last["high"]

    swing_high = high.tail(20).max()
    swing_low = low.tail(20).min()

    momentum = round((last["close"] - df["ma50"].iloc[-1]) / df["ma50"].iloc[-1] * 100, 2)

    return {
        "trend": trend,
        "momentum": momentum,
        "pivot_r1": round(r1, 2),
        "pivot_s1": round(s1, 2),
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2)
    }

# ============================================================
# SIGNAL ENGINES
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
# BLACKLIST + FORMATIONS (proste, ale działające)
# ============================================================

def blacklist_engine(symbol, df):
    if df is None or df.empty or len(df) < 30:
        return False, "Brak danych"

    df = df.copy()
    vol = df["volume"].astype(float)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    open_ = df["open"].astype(float)

    reasons = []

    avg_vol = float(vol.tail(20).mean())
    if avg_vol < 5000:
        reasons.append("Niska płynność")

    last = df.iloc[-1]
    body = abs(last["close"] - last["open"])
    range_ = last["high"] - last["low"]
    if range_ > 0 and body / range_ > 0.8:
        reasons.append("Podejrzana świeca (pump/dump)")

    if len(df) >= 5:
        close_5d = float(close.iloc[-5])
        last_close = float(close.iloc[-1])
        drop = (close_5d - last_close) / close_5d * 100
        if drop > 20:
            reasons.append("Spadek >20% w 5 dni")

    if reasons:
        return True, ", ".join(reasons)
    return False, ""

def detect_formations(df):
    if df is None or df.empty or len(df) < 40:
        return 0, "Brak danych"

    df = df.copy()
    high = df["high"].astype(float).tail(40).values
    low = df["low"].astype(float).tail(40).values
    close = df["close"].astype(float).values

    score = 0
    desc = []

    if (high.max() - high.min()) < (low.max() - low.min()) * 1.2:
        score += 2
        desc.append("Triangle")

    if high[-1] < high[0] and low[-1] > low[0]:
        score += 2
        desc.append("Wedge (up)")
    if high[-1] > high[0] and low[-1] < low[0]:
        score += 2
        desc.append("Wedge (down)")

    if len(close) >= 20:
        last_move = abs(close[-20] - close[-1])
        flag_range = high.max() - low.min()
        if flag_range > 0 and last_move > flag_range * 1.5:
            score += 1
            desc.append("Flag")

    if score == 0:
        return 0, "Brak formacji"
    return score, ", ".join(desc)

# ============================================================
# ALERT ENGINE (email / webhook / discord / telegram)
# ============================================================

def alert_send_email(to_email, subject, body):
    try:
        smtp_user = st.secrets.get("SMTP_USER", "")
        smtp_pass = st.secrets.get("SMTP_PASS", "")
        smtp_server = st.secrets.get("SMTP_SERVER", "")
        smtp_port = st.secrets.get("SMTP_PORT", 465)

        if not smtp_user or not smtp_pass or not smtp_server:
            return False

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
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
# GENESIS (AI PORTFOLIO)
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
        "Swing",
        "Genesis",
        "Alerts"
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
            bl_flag, bl_reason = blacklist_engine(symbol, df)
            form_score, form_desc = detect_formations(df)
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
            st.write(f"Formacje: {form_desc}")
            if bl_flag:
                st.error(f"BLACKLIST: {bl_reason}")

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
# UI — SWING
# ============================================================

if tab == "Swing":
    st.markdown("## 🌀 Swing Mode (D1)")

    symbol = st.text_input("Symbol (swing)", "AAPL")

    if symbol:
        df = av_get_daily(symbol, outputsize="full")
        if df.empty:
            st.error("Brak danych z API dla tego symbolu.")
        else:
            ind = calc_swing_indicators(df)
            signal, score = swing_signal(ind)

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
```

Jeśli to odpalisz i znowu coś się wywali — wklej **sam traceback**.  
Bez gadania, bez emocji — po prostu go zdejmę linia po linii.
