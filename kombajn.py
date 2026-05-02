```python
# kombajn.py – NEON BREAKOUT SCANNER (PL, AI tylko na kliknięcie, przycisk per spółka)

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import streamlit as st
import pandas as pd

# =========================
# KONFIGURACJA
# =========================
MAX_CANDLES = 200
TOP_LIMIT = 10

# =========================
# STRUKTURY
# =========================
@dataclass
class Pivot:
    P: float = 0.0
    R1: float = 0.0
    S1: float = 0.0

@dataclass
class Trend:
    short: str = "NEUTRAL"
    mid: str = "NEUTRAL"
    long: str = "NEUTRAL"
    score: int = 0

@dataclass
class TpSl:
    tp: float = 0.0
    sl: float = 0.0

@dataclass
class AiResult:
    signal: str
    tp: float
    sl: float
    notes: List[str]

@dataclass
class Ticker:
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: float = 0.0
    closes: List[float] = field(default_factory=list)
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)
    ema10: float = 0.0
    ema50: float = 0.0
    ema200: float = 0.0
    rsi14: float = 0.0
    high52w: float = 0.0
    low52w: float = 0.0
    pivot: Pivot = field(default_factory=Pivot)
    trend: Trend = field(default_factory=Trend)
    tpsl: TpSl = field(default_factory=TpSl)
    breakout: float = 0.0
    ai: Optional[AiResult] = None

# =========================
# FUNKCJE MATEMATYCZNE
# =========================
def ema(values, period):
    if not values:
        return float("nan")
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def sma(values, period):
    if len(values) < period:
        return float("nan")
    return sum(values[-period:]) / period

def rsi(values, period=14):
    if len(values) <= period:
        return float("nan")
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

# =========================
# LOGIKA WSKAŹNIKÓW
# =========================
def calc_trend(close, ema10_v, ema50_v, ema200_v):
    s = 1 if close > ema10_v else -1 if close < ema10_v else 0
    m = 1 if close > ema50_v else -1 if close < ema50_v else 0
    l = 1 if close > ema200_v else -1 if close < ema200_v else 0
    score = 1 * s + 2 * m + 3 * l

    def t(x):
        return "WZROST" if x > 0 else "SPADEK" if x < 0 else "NEUTRAL"

    return Trend(short=t(s), mid=t(m), long=t(l), score=score)

def calc_pivots(h, l, c):
    P = (h + l + c) / 3
    return Pivot(P=P, R1=2 * P - l, S1=2 * P - h)

def calc_tpsl(t: Ticker):
    tp = t.high52w or t.pivot.R1 or t.last * 1.05
    sl = t.low52w or t.pivot.S1 or t.last * 0.95
    return TpSl(tp=tp, sl=sl)

def calc_breakout(t: Ticker):
    dist = (t.last - t.high52w) / t.high52w if t.high52w else 0
    vol20 = sma(t.volumes, 20)
    vol_rel = t.volume / vol20 if vol20 == vol20 else 1
    mom = t.rsi14 / 100 if t.rsi14 == t.rsi14 else 0.5
    return 3 * dist + 2 * vol_rel + mom

def signal_from_score(score: int) -> str:
    if score >= 4:
        return "KUP"
    if score <= -2:
        return "SPRZEDAJ"
    return "TRZYMAJ"

# =========================
# MOCK DANYCH (do podmiany na API)
# =========================
def mock_history(symbol: str):
    candles = []
    price = random.uniform(50, 150)
    for _ in range(MAX_CANDLES):
        high = price * (1 + random.random() * 0.01)
        low = price * (1 - random.random() * 0.01)
        close = random.uniform(low, high)
        vol = random.uniform(1000, 5000)
        candles.append({"high": high, "low": low, "close": close, "volume": vol})
        price = close
    return candles

def init_ticker(symbol: str) -> Ticker:
    c = mock_history(symbol)
    closes = [x["close"] for x in c]
    highs = [x["high"] for x in c]
    lows = [x["low"] for x in c]
    vols = [x["volume"] for x in c]

    ema10_v = ema(closes, 10)
    ema50_v = ema(closes, 50)
    ema200_v = ema(closes, 200)
    rsi14_v = rsi(closes, 14)

    last = closes[-1]
    prev = c[-2]

    pivot = calc_pivots(prev["high"], prev["low"], prev["close"])

    t = Ticker(
        symbol=symbol,
        bid=last * 0.999,
        ask=last * 1.001,
        last=last,
        volume=vols[-1],
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=vols,
        ema10=ema10_v,
        ema50=ema50_v,
        ema200=ema200_v,
        rsi14=rsi14_v,
        high52w=max(highs),
        low52w=min(lows),
        pivot=pivot,
    )

    t.trend = calc_trend(last, ema10_v, ema50_v, ema200_v)
    t.tpsl = calc_tpsl(t)
    t.breakout = calc_breakout(t)
    return t

def update_realtime(t: Ticker):
    delta = (random.random() - 0.5) * 0.5
    new_last = max(0.01, t.last + delta)
    t.last = new_last
    t.bid = new_last * 0.999
    t.ask = new_last * 1.001
    t.volume += random.uniform(100, 1000)

    t.closes.append(new_last)
    if len(t.closes) > MAX_CANDLES:
        t.closes.pop(0)

    t.ema10 = ema(t.closes, 10)
    t.ema50 = ema(t.closes, 50)
    t.ema200 = ema(t.closes, 200)
    t.rsi14 = rsi(t.closes, 14)
    t.trend = calc_trend(t.last, t.ema10, t.ema50, t.ema200)
    t.tpsl = calc_tpsl(t)
    t.breakout = calc_breakout(t)

# =========================
# AI ANALIZA – TYLKO NA KLIKNIĘCIE
# =========================
def ai_analyze(t: Ticker) -> AiResult:
    sig = signal_from_score(t.trend.score)
    notes = [
        f"Trend: {t.trend.short}/{t.trend.mid}/{t.trend.long}",
        f"RSI14: {t.rsi14:.1f}",
        f"Cena vs 52W High: {t.last:.2f} / {t.high52w:.2f}",
    ]
    return AiResult(signal=sig, tp=t.tpsl.tp, sl=t.tpsl.sl, notes=notes)

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="NEON BREAKOUT SCANNER", layout="wide")

st.markdown(
    """
    <style>
    body { background-color: #050510; color: #e0e0ff; }
    .neon-buy { color: #00ff88; font-weight: 700; }
    .neon-hold { color: #00aaff; font-weight: 700; }
    .neon-sell { color: #ff0044; font-weight: 700; }
    .neon-tp { color: #00ff00; font-weight: 700; }
    .neon-sl { color: #ff0000; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("💹 NEON BREAKOUT SCANNER – kombajn.py (AI tylko na kliknięcie)")

symbols_input = st.text_input(
    "Wpisz spółki oddzielone przecinkami:",
    "AAPL, MSFT, TSLA, NVDA, AMZN",
)
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

if "tickers" not in st.session_state:
    st.session_state.tickers: Dict[str, Ticker] = {s: init_ticker(s) for s in symbols}

for s in symbols:
    if s not in st.session_state.tickers:
        st.session_state.tickers[s] = init_ticker(s)

if st.button("🔄 Odśwież dane (symulacja real-time)"):
    for t in st.session_state.tickers.values():
        update_realtime(t)

all_tickers = [st.session_state.tickers[s] for s in symbols]
sorted_list = sorted(all_tickers, key=lambda x: x.breakout, reverse=True)
top10 = sorted_list[:TOP_LIMIT]

st.subheader("🔥 TOP 10 wybicia")
st.write(", ".join([t.symbol for t in top10]))

st.subheader("📊 Tabela spółek")

rows = []
for t in sorted_list:
    rows.append(
        {
            "Spółka": t.symbol,
            "Bid/Ask": f"{t.bid:.2f} / {t.ask:.2f}",
            "Kurs": f"{t.last:.2f}",
            "Trend S": t.trend.short,
            "Trend M": t.trend.mid,
            "Trend L": t.trend.long,
            "Sygnał": signal_from_score(t.trend.score),
            "52W Low": f"{t.low52w:.2f}",
            "52W High": f"{t.high52w:.2f}",
            "Pivot P": f"{t.pivot.P:.2f}",
            "TP": f"{t.tpsl.tp:.2f}",
            "SL": f"{t.tpsl.sl:.2f}",
            "Breakout": f"{t.breakout:.2f}",
            "AI sygnał": t.ai.signal if t.ai else "-",
        }
    )

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True)

st.subheader("🤖 Analiza AI – przycisk przy każdej spółce")

for t in sorted_list:
    c1, c2, c3 = st.columns([1, 1, 4])
    with c1:
        st.markdown(f"**{t.symbol}**")
    with c2:
        if st.button("Analizuj AI", key=f"ai_btn_{t.symbol}"):
            t.ai = ai_analyze(t)
    with c3:
        if t.ai:
            st.markdown(
                f"Sygnał: **{t.ai.signal}**, "
                f"TP: <span class='neon-tp'>{t.ai.tp:.2f}</span>, "
                f"SL: <span class='neon-sl'>{t.ai.sl:.2f}</span>",
                unsafe_allow_html=True,
            )
            for note in t.ai.notes:
                st.markdown(f"- {note}")
        else:
            st.caption("Brak analizy AI (kliknij przycisk).")
```
