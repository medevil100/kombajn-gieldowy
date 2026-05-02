import math
import json
import requests
import yfinance as yf
import streamlit as st

# =========================
# WSKAŹNIKI
# =========================

def ema(values, period):
    if not values:
        return math.nan
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def sma(values, period):
    if len(values) < period:
        return math.nan
    return sum(values[-period:]) / period

def rsi(values, period=14):
    if len(values) <= period:
        return math.nan
    gains = 0
    losses = 0
    for i in range(len(values) - period, len(values)):
        diff = values[i] - values[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)

def atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sma(trs, period)

def macd_calc(values):
    if len(values) < 26:
        return math.nan, math.nan, math.nan
    ema12 = ema(values, 12)
    ema26 = ema(values, 26)
    macd = ema12 - ema26
    signal = ema([macd] * 9, 9)
    hist = macd - signal
    return macd, signal, hist

# =========================
# ANALIZA ULTRA
# =========================

def analyze_ultra(symbol, candles):
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    last = closes[-1]
    prev = candles[-2]

    ema10 = ema(closes, 10)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14_v = rsi(closes, 14)
    atr14_v = atr(candles, 14)
    macd_v, macd_sig, macd_hist = macd_calc(closes)
    vol20 = sma(volumes, 20)
    vol_rel = volumes[-1] / vol20 if vol20 else 1

    s = 1 if last > ema10 else -1
    m = 1 if last > ema50 else -1
    l = 1 if last > ema200 else -1
    trend_score = s + 2*m + 3*l

    P = (prev["high"] + prev["low"] + prev["close"]) / 3
    R1 = 2 * P - prev["low"]
    S1 = 2 * P - prev["high"]

    high52 = max(highs)
    low52 = min(lows)

    tp = high52
    sl = low52

    dist = (last - high52) / high52 if high52 else 0
    breakout = 3 * dist + 2 * vol_rel + (rsi14_v / 100)

    pressure = "KUPUJĄCY DOMINUJĄ" if last > (prev["open"] + prev["close"]) / 2 else "SPRZEDAJĄCY DOMINUJĄ"

    momentum = last - closes[-5]
    volatility = max(highs[-10:]) - min(lows[-10:])

    body = candles[-1]["close"] - candles[-1]["open"]
    rng = candles[-1]["high"] - candles[-1]["low"]
    if body > 0 and abs(body) > 0.6 * rng:
        candle_pattern = "MOCNA BYCZA ŚWIECA"
    elif body < 0 and abs(body) > 0.6 * rng:
        candle_pattern = "MOCNA NIEDŹWIEDZIA ŚWIECA"
    else:
        candle_pattern = "BRAK"

    if breakout > 5:
        setup = "BREAKOUT LONG"
    elif breakout < -2:
        setup = "BREAKOUT SHORT"
    else:
        setup = "NEUTRAL"

    if atr14_v < last * 0.01:
        risk = "NISKIE"
    elif atr14_v < last * 0.02:
        risk = "ŚREDNIE"
    else:
        risk = "WYSOKIE"

    if trend_score >= 4 and breakout > 3:
        signal = "KUP"
    elif trend_score <= -2:
        signal = "SPRZEDAJ"
    else:
        signal = "TRZYMAJ"

    return {
        "symbol": symbol,
        "last": last,
        "trend_score": trend_score,
        "ema10": ema10,
        "ema50": ema50,
        "ema200": ema200,
        "rsi14": rsi14_v,
        "atr14": atr14_v,
        "macd": macd_v,
        "macd_signal": macd_sig,
        "macd_hist": macd_hist,
        "volume_rel": vol_rel,
        "breakout": breakout,
        "pivot_P": P,
        "pivot_R1": R1,
        "pivot_S1": S1,
        "tp": tp,
        "sl": sl,
        "pressure": pressure,
        "momentum": momentum,
        "volatility": volatility,
        "candle_pattern": candle_pattern,
        "setup": setup,
        "risk": risk,
        "signal": signal,
        "raw_candles": candles[-100:],
    }

# =========================
# AI — gpt‑4o‑mini
# =========================

def call_ai_gpt40mini(payload: dict) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {st.secrets['OPENAI_API_KEY']}",
    }
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Jesteś profesjonalnym analitykiem giełdowym. "
                    "Odpowiadasz po polsku. "
                    "Tworzysz krótki komentarz inwestycyjny na podstawie danych technicznych."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "temperature": 0.25,
        "max_tokens": 500,
    }
    r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# =========================
# UI + KOLORY
# =========================

st.set_page_config(page_title="NEON KOMBAJN ULTRA", layout="wide")

st.markdown("""
<style>
body { background-color: #050510; color: #e0e0ff; }
.block { background: #0a0a18; padding: 20px; margin-bottom: 25px; border-radius: 12px;
         border: 1px solid #222; box-shadow: 0 0 12px #00eaff33; }
.title { font-size: 26px; font-weight: bold; color: #00eaff; }
.section { font-size: 16px; margin-top: 10px; color: #9ad7ff; }
.value { font-size: 18px; font-weight: bold; color: #ffffff; }
.ai-block { background: #111122; padding: 15px; border-radius: 10px; margin-top: 10px; border: 1px solid #333; }
.signal-KUP { color: #00ff88; font-weight: 700; }
.signal-TRZYMAJ { color: #00aaff; font-weight: 700; }
.signal-SPRZEDAJ { color: #ff0044; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st.title("💹 NEON KOMBAJN ULTRA — z AI")

symbols_input = st.text_input("Tickery:", "AAPL, MSFT, TSLA, NVDA")
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

@st.cache_data(show_spinner=False)
def load_candles(symbol: str):
    data = yf.download(symbol, period="6mo", interval="1d").dropna()

    def to_float(x):
        try:
            return float(x)
        except Exception:
            try:
                return float(x.item())
            except Exception:
                return float(x.astype(float))

    candles = []
    for _, r in data.iterrows():
        candles.append({
            "open": to_float(r["Open"]),
            "high": to_float(r["High"]),
            "low": to_float(r["Low"]),
            "close": to_float(r["Close"]),
            "volume": to_float(r["Volume"]),
        })
    return candles

if "run_id" not in st.session_state:
    st.session_state["run_id"] = 0
st.session_state["run_id"] += 1

for symbol in symbols:
    st.markdown(f"<div class='block'><div class='title'>{symbol}</div>", unsafe_allow_html=True)

    try:
        candles = load_candles(symbol)
        analysis = analyze_ultra(symbol, candles)
    except Exception as e:
        st.error(f"Błąd: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
        continue

    def row(label, value):
        st.markdown(f"<div class='section'>{label}:</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='value'>{value}</div>", unsafe_allow_html=True)

    row("Kurs", f"{analysis['last']:.2f}")
    row("Trend (score)", analysis["trend_score"])
    row("EMA10 / EMA50 / EMA200", f"{analysis['ema10']:.2f} / {analysis['ema50']:.2f} / {analysis['ema200']:.2f}")
    row("RSI14 / ATR14", f"{analysis['rsi14']:.2f} / {analysis['atr14']:.2f}")
    row("MACD / sygnał / histogram", f"{analysis['macd']:.2f} / {analysis['macd_signal']:.2f} / {analysis['macd_hist']:.2f}")
    row("Wolumen relatywny", f"{analysis['volume_rel']:.2f}")
    row("Breakout score", f"{analysis['breakout']:.2f}")
    row("Pivot P / R1 / S1", f"{analysis['pivot_P']:.2f} / {analysis['pivot_R1']:.2f} / {analysis['pivot_S1']:.2f}")
    row("TP / SL", f"{analysis['tp']:.2f} / {analysis['sl']:.2f}")
    row("Presja rynku", analysis["pressure"])
    row("Momentum / zmienność", f"{analysis['momentum']:.2f} / {analysis['volatility']:.2f}")
    row("Formacja świecowa", analysis["candle_pattern"])
    row("Setup", analysis["setup"])
    row("Ryzyko", analysis["risk"])

    sig_class = f"signal-{analysis['signal']}"
    st.markdown("<div class='section'>Sygnał końcowy:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value {sig_class}'>{analysis['signal']}</div>", unsafe_allow_html=True)

    if st.button(f"🤖 Analiza AI dla {symbol}", key=f"ai_{symbol}_{st.session_state['run_id']}"):
        payload = {
            "symbol": symbol,
            "analysis": {k: v for k, v in analysis.items() if k != "raw_candles"},
            "candles_tail": analysis["raw_candles"],
        }
        with st.spinner("AI analizuje..."):
            try:
                ai_text = call_ai_gpt40mini(payload)
            except Exception as e:
                ai_text = f"Błąd AI: {e}"

        st.markdown("<div class='ai-block'>", unsafe_allow_html=True)
        st.markdown("### 🤖 Wynik analizy AI:", unsafe_allow_html=True)
        st.write(ai_text)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)
