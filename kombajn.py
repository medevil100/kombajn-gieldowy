# kombajn.py – NEON BREAKOUT SCANNER (jednomodułowy)
# Real-time (mock), TOP10 wybicia, trendy S/M/L, 52W, pivot, TP/SL, AI analiza, Streamlit UI

import time
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import streamlit as st

# =========================
# KONFIGURACJA
# =========================
REFRESH_INTERVALS = [1, 2, 3, 5, 10]  # minuty
DEFAULT_REFRESH = 1
MAX_CANDLES = 200
TOP_LIMIT = 10

# =========================
# STRUKTURY DANYCH
# =========================
@dataclass
class Pivot:
    P: float = 0.0
    R1: float = 0.0
    S1: float = 0.0


@dataclass
class TrendInfo:
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
class TickerData:
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: float = 0.0
    time: float = 0.0
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
    trend: TrendInfo = field(default_factory=TrendInfo)
    tpsl: TpSl = field(default_factory=TpSl)
    breakout_score: float = 0.0
    ai: Optional[AiResult] = None


# =========================
# FUNKCJE MATEMATYCZNE
# =========================
def ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2 / (period + 1)
    ema_val = values[0]
    for v in values[1:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val


def sma(values: List[float], period: int) -> float:
    if len(values) < period:
        return float("nan")
    s = values[-period:]
    return sum(s) / period


def rsi(values: List[float], period: int = 14) -> float:
    if len(values) <= period:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(len(values) - period, len(values)):
        diff = values[i] - values[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


# =========================
# LOGIKA WSKAŹNIKÓW
# =========================
def calc_trend(close: float, ema10_v: float, ema50_v: float, ema200_v: float) -> TrendInfo:
    s = 1 if close > ema10_v else -1 if close < ema10_v else 0
    m = 1 if close > ema50_v else -1 if close < ema50_v else 0
    l = 1 if close > ema200_v else -1 if close < ema200_v else 0
    score = 1 * s + 2 * m + 3 * l

    def to_trend(x: int) -> str:
        if x > 0:
            return "UP"
        if x < 0:
            return "DOWN"
        return "NEUTRAL"

    return TrendInfo(short=to_trend(s), mid=to_trend(m), long=to_trend(l), score=score)


def calc_pivots(prev_high: float, prev_low: float, prev_close: float) -> Pivot:
    P = (prev_high + prev_low + prev_close) / 3
    R1 = 2 * P - prev_low
    S1 = 2 * P - prev_high
    return Pivot(P=P, R1=R1, S1=S1)


def calc_tpsl(t: TickerData) -> TpSl:
    tp = t.high52w or t.pivot.R1 or t.last * 1.05
    sl = t.low52w or t.pivot.S1 or t.last * 0.95
    return TpSl(tp=tp, sl=sl)


def calc_breakout_score(t: TickerData) -> float:
    dist52 = (t.last - t.high52w) / t.high52w if t.high52w else 0.0
    vol_sma20 = sma(t.volumes, 20)
    vol_rel = t.volume / vol_sma20 if vol_sma20 and vol_sma20 == vol_sma20 else 1.0
    mom = t.rsi14 / 100 if t.rsi14 == t.rsi14 else 0.5
    return 3 * dist52 + 2 * vol_rel + 1 * mom


def signal_from_trend_score(score: int) -> str:
    if score >= 4:
        return "BUY"
    if score <= -2:
        return "SELL"
    return "HOLD"


# =========================
# MOCK DANYCH HISTORYCZNYCH (DO PODMIANY NA API)
# =========================
def mock_history(symbol: str) -> List[Dict]:
    candles = []
    now = time.time()
    price = random.uniform(50, 150)
    for i in range(MAX_CANDLES):
        high = price * (1 + random.random() * 0.01)
        low = price * (1 - random.random() * 0.01)
        close = random.uniform(low, high)
        volume = random.uniform(1000, 5000)
        candles.append(
            {
                "time": now - (MAX_CANDLES - i) * 60,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        price = close
    return candles


def init_ticker(symbol: str) -> TickerData:
    candles = mock_history(symbol)
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    ema10_v = ema(closes, 10)
    ema50_v = ema(closes, 50)
    ema200_v = ema(closes, 200)
    rsi14_v = rsi(closes, 14)

    last_close = closes[-1]
    prev = candles[-2] if len(candles) > 1 else candles[-1]
    pivot = calc_pivots(prev["high"], prev["low"], prev["close"])

    high52w = max(highs)
    low52w = min(lows)

    trend = calc_trend(last_close, ema10_v, ema50_v, ema200_v)
    tpsl = calc_tpsl(
        TickerData(
            symbol=symbol,
            last=last_close,
            high52w=high52w,
            low52w=low52w,
            pivot=pivot,
        )
    )

    tmp = TickerData(
        symbol=symbol,
        bid=last_close * 0.999,
        ask=last_close * 1.001,
        last=last_close,
        volume=volumes[-1],
        time=time.time(),
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        ema10=ema10_v,
        ema50=ema50_v,
        ema200=ema200_v,
        rsi14=rsi14_v,
        high52w=high52w,
        low52w=low52w,
        pivot=pivot,
        trend=trend,
        tpsl=tpsl,
    )
    tmp.breakout_score = calc_breakout_score(tmp)
    return tmp


# =========================
# MOCK REAL-TIME (DO PODMIANY NA WEBSOCKET/API)
# =========================
def update_realtime(t: TickerData) -> None:
    delta = (random.random() - 0.5) * 0.5
    new_last = max(0.01, t.last + delta)
    t.last = new_last
    t.bid = new_last * 0.999
    t.ask = new_last * 1.001
    t.volume += random.uniform(100, 1000)
    t.time = time.time()

    t.closes.append(new_last)
    if len(t.closes) > MAX_CANDLES:
        t.closes.pop(0)

    t.ema10 = ema(t.closes, 10)
    t.ema50 = ema(t.closes, 50)
    t.ema200 = ema(t.closes, 200)
    t.rsi14 = rsi(t.closes, 14)
    t.trend = calc_trend(t.last, t.ema10, t.ema50, t.ema200)
    t.tpsl = calc_tpsl(t)
    t.breakout_score = calc_breakout_score(t)


# =========================
# AI ANALIZA (MOCK – KRÓTKO, KONKRETNIE)
# =========================
def analyze_with_ai(t: TickerData) -> AiResult:
    signal = signal_from_trend_score(t.trend.score)
    tp = t.tpsl.tp
    sl = t.tpsl.sl
    notes = [
        f"Trend S/M/L: {t.trend.short}/{t.trend.mid}/{t.trend.long}",
        f"RSI14: {t.rsi14:.1f}",
        f"Cena vs 52W High: {t.last:.2f} / {t.high52w:.2f}",
    ]
    return AiResult(signal=signal, tp=tp, sl=sl, notes=notes)


# =========================
# INICJALIZACJA STANU STREAMLIT
# =========================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]

if "tickers" not in st.session_state:
    st.session_state.tickers: Dict[str, TickerData] = {
        s: init_ticker(s) for s in st.session_state.watchlist
    }

if "ai_selected" not in st.session_state:
    st.session_state.ai_selected = set()

if "refresh_minutes" not in st.session_state:
    st.session_state.refresh_minutes = DEFAULT_REFRESH

# =========================
# UI – NEON DASHBOARD
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

st.title("💹 NEON BREAKOUT SCANNER – kombajn.py")

col_left, col_mid, col_right = st.columns([2, 2, 2])

with col_left:
    refresh = st.selectbox(
        "Interwał odświeżania (minuty)",
        REFRESH_INTERVALS,
        index=REFRESH_INTERVALS.index(st.session_state.refresh_minutes),
    )
    st.session_state.refresh_minutes = refresh

with col_mid:
    if st.button("🔄 ODSWIEŻ TERAZ"):
        for t in st.session_state.tickers.values():
            update_realtime(t)

with col_right:
    show_top10_only = st.checkbox("Pokaż tylko TOP 10 wybicia", value=False)

# AI wybór
st.subheader("AI – wybierz spółki do analizy")
ai_cols = st.columns(len(st.session_state.watchlist))
for i, symbol in enumerate(st.session_state.watchlist):
    with ai_cols[i]:
        checked = symbol in st.session_state.ai_selected
        new_val = st.checkbox(symbol, value=checked, key=f"ai_{symbol}")
        if new_val:
            st.session_state.ai_selected.add(symbol)
        else:
            st.session_state.ai_selected.discard(symbol)

if st.button("🤖 ANALIZUJ WYBRANE (AI)"):
    for sym in st.session_state.ai_selected:
        t = st.session_state.tickers.get(sym)
        if t:
            t.ai = analyze_with_ai(t)

# Aktualizacja real-time przy każdym rerunie
for t in st.session_state.tickers.values():
    update_realtime(t)

# TOP10
all_tickers = list(st.session_state.tickers.values())
sorted_by_breakout = sorted(all_tickers, key=lambda x: x.breakout_score, reverse=True)
top10 = sorted_by_breakout[:TOP_LIMIT]
symbols_top10 = [t.symbol for t in top10]

st.markdown(f"**TOP10 wybicia:** {', '.join(symbols_top10)}")

# Tabela
st.subheader("Tabela spółek")

def signal_badge(sig: str) -> str:
    if sig == "BUY":
        return '<span class="neon-buy">BUY</span>'
    if sig == "SELL":
        return '<span class="neon-sell">SELL</span>'
    return '<span class="neon-hold">HOLD</span>'


rows_html = []
rows_html.append(
    "<tr>"
    "<th>TICKER</th><th>Bid / Ask</th><th>Last</th>"
    "<th>Trend S</th><th>Trend M</th><th>Trend L</th>"
    "<th>Signal</th><th>52W Low</th><th>52W High</th>"
    "<th>Pivot P</th><th>TP</th><th>SL</th><th>Breakout</th><th>AI</th>"
    "</tr>"
)

for t in (top10 if show_top10_only else all_tickers):
    sig = signal_from_trend_score(t.trend.score)
    ai_sig = t.ai.signal if t.ai else "-"
    ai_color = (
        "neon-buy" if ai_sig == "BUY" else "neon-sell" if ai_sig == "SELL" else "neon-hold"
    )
    rows_html.append(
        "<tr>"
        f"<td>{t.symbol}</td>"
        f"<td>{t.bid:.2f} / {t.ask:.2f}</td>"
        f"<td>{t.last:.2f}</td>"
        f"<td>{t.trend.short}</td>"
        f"<td>{t.trend.mid}</td>"
        f"<td>{t.trend.long}</td>"
        f"<td>{signal_badge(sig)}</td>"
        f"<td>{t.low52w:.2f}</td>"
        f"<td>{t.high52w:.2f}</td>"
        f"<td>{t.pivot.P:.2f}</td>"
        f"<td><span class='neon-tp'>{t.tpsl.tp:.2f}</span></td>"
        f"<td><span class='neon-sl'>{t.tpsl.sl:.2f}</span></td>"
        f"<td>{t.breakout_score:.2f}</td>"
        f"<td><span class='{ai_color}'>{ai_sig}</span></td>"
        "</tr>"
    )

table_html = (
    "<table border='1' style='border-collapse:collapse;width:100%;font-size:13px;'>"
    + "".join(rows_html)
    + "</table>"
)
st.markdown(table_html, unsafe_allow_html=True)

# Auto-refresh (prosty – użytkownik odświeża stronę / F5; można dodać st_autorefresh)
st.caption(f"Odświeżanie logiczne co rerun, interwał docelowy: {st.session_state.refresh_minutes} min (manualne).")
