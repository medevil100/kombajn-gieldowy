# analyzer.py – silnik analityczny (kombajn danych)

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import math

# =========================
# STRUKTURY
# =========================
@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class TrendInfo:
    short: str
    mid: str
    long: str
    score: int

@dataclass
class Pivot:
    P: float
    R1: float
    S1: float

@dataclass
class TpSl:
    tp: float
    sl: float

@dataclass
class CoreMetrics:
    ema10: float
    ema50: float
    ema200: float
    rsi14: float
    atr14: float
    vol_rel20: float
    high52w: float
    low52w: float
    trend: TrendInfo
    pivot: Pivot
    tpsl: TpSl
    breakout_score: float
    signal: str


# =========================
# FUNKCJE POMOCNICZE
# =========================
def ema(values: List[float], period: int) -> float:
    if not values:
        return math.nan
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def sma(values: List[float], period: int) -> float:
    if len(values) < period:
        return math.nan
    return sum(values[-period:]) / period

def rsi(values: List[float], period: int = 14) -> float:
    if len(values) <= period:
        return math.nan
    gains = 0.0
    losses = 0.0
    for i in range(len(values) - period, len(values)):
        diff = values[i] - values[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)

def atr(candles: List[Candle], period: int = 14) -> float:
    if len(candles) <= period:
        return math.nan
    trs = []
    for i in range(1, len(candles)):
        h = candles[i].high
        l = candles[i].low
        pc = candles[i - 1].close
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return math.nan
    return sma(trs, period)

def calc_trend(close: float, ema10_v: float, ema50_v: float, ema200_v: float) -> TrendInfo:
    s = 1 if close > ema10_v else -1 if close < ema10_v else 0
    m = 1 if close > ema50_v else -1 if close < ema50_v else 0
    l = 1 if close > ema200_v else -1 if close < ema200_v else 0
    score = 1 * s + 2 * m + 3 * l

    def t(x: int) -> str:
        return "WZROST" if x > 0 else "SPADEK" if x < 0 else "NEUTRAL"

    return TrendInfo(short=t(s), mid=t(m), long=t(l), score=score)

def calc_pivots(prev_high: float, prev_low: float, prev_close: float) -> Pivot:
    P = (prev_high + prev_low + prev_close) / 3
    R1 = 2 * P - prev_low
    S1 = 2 * P - prev_high
    return Pivot(P=P, R1=R1, S1=S1)

def calc_tpsl(last: float, high52w: float, low52w: float, pivot: Pivot) -> TpSl:
    tp = high52w or pivot.R1 or last * 1.05
    sl = low52w or pivot.S1 or last * 0.95
    return TpSl(tp=tp, sl=sl)

def breakout_score(last: float,
                   high52w: float,
                   volume: float,
                   volumes: List[float],
                   rsi14_v: float) -> float:
    dist = (last - high52w) / high52w if high52w else 0.0
    vol20 = sma(volumes, 20)
    vol_rel = volume / vol20 if vol20 == vol20 else 1.0
    mom = rsi14_v / 100 if rsi14_v == rsi14_v else 0.5
    return 3 * dist + 2 * vol_rel + mom

def signal_from_trend_score(score: int) -> str:
    if score >= 4:
        return "KUP"
    if score <= -2:
        return "SPRZEDAJ"
    return "TRZYMAJ"


# =========================
# GŁÓWNA FUNKCJA ANALIZY
# =========================
def analyze_candles(candles: List[Dict[str, float]]) -> CoreMetrics:
    """
    candles: lista słowników:
      {
        "open": float,
        "high": float,
        "low": float,
        "close": float,
        "volume": float
      }
    """
    if len(candles) < 2:
        raise ValueError("Za mało świec do analizy")

    cs = [Candle(**c) for c in candles]
    closes = [c.close for c in cs]
    highs = [c.high for c in cs]
    lows = [c.low for c in cs]
    volumes = [c.volume for c in cs]

    last_close = closes[-1]
    last_volume = volumes[-1]
    prev = cs[-2]

    ema10_v = ema(closes, 10)
    ema50_v = ema(closes, 50)
    ema200_v = ema(closes, 200)
    rsi14_v = rsi(closes, 14)
    atr14_v = atr(cs, 14)
    vol_rel20_v = sma(volumes, 20)
    high52w_v = max(highs)
    low52w_v = min(lows)

    trend_v = calc_trend(last_close, ema10_v, ema50_v, ema200_v)
    pivot_v = calc_pivots(prev.high, prev.low, prev.close)
    tpsl_v = calc_tpsl(last_close, high52w_v, low52w_v, pivot_v)
    breakout_v = breakout_score(last_close, high52w_v, last_volume, volumes, rsi14_v)
    signal_v = signal_from_trend_score(trend_v.score)

    return CoreMetrics(
        ema10=ema10_v,
        ema50=ema50_v,
        ema200=ema200_v,
        rsi14=rsi14_v,
        atr14=atr14_v,
        vol_rel20=vol_rel20_v,
        high52w=high52w_v,
        low52w=low52w_v,
        trend=trend_v,
        pivot=pivot_v,
        tpsl=tpsl_v,
        breakout_score=breakout_v,
        signal=signal_v,
    )


# =========================
# FUNKCJA POD AI
# =========================
def build_ai_payload(symbol: str,
                     candles: List[Dict[str, float]]) -> Dict[str, Any]:
    """
    Zwraca gotowy pakiet danych do AI:
    - surowe świece
    - wskaźniki
    - sygnały
    """
    metrics = analyze_candles(candles)

    return {
        "symbol": symbol,
        "last_close": candles[-1]["close"],
        "metrics": {
            "ema10": metrics.ema10,
            "ema50": metrics.ema50,
            "ema200": metrics.ema200,
            "rsi14": metrics.rsi14,
            "atr14": metrics.atr14,
            "vol_rel20": metrics.vol_rel20,
            "high52w": metrics.high52w,
            "low52w": metrics.low52w,
            "trend": {
                "short": metrics.trend.short,
                "mid": metrics.trend.mid,
                "long": metrics.trend.long,
                "score": metrics.trend.score,
            },
            "pivot": {
                "P": metrics.pivot.P,
                "R1": metrics.pivot.R1,
                "S1": metrics.pivot.S1,
            },
            "tpsl": {
                "tp": metrics.tpsl.tp,
                "sl": metrics.tpsl.sl,
            },
            "breakout_score": metrics.breakout_score,
            "signal": metrics.signal,
        },
        "raw_candles": candles[-100:],  # ograniczamy rozmiar pod AI
    }
