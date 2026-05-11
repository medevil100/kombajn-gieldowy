import os
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

st.set_page_config(page_title="Heatmap PRO", layout="wide")

# --- OpenAI config ---
AI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Pobieranie danych cenowych ---
def get_price_data(symbol, period="5d", interval="1h"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

# --- Pobieranie BID / ASK / SPREAD% ---
def get_bid_ask(symbol: str):
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        bid = info.get("bid", None)
        ask = info.get("ask", None)

        if bid is None or ask is None or bid == 0 or ask == 0:
            return None, None, None

        mid = (bid + ask) / 2
        if not mid:
            return float(bid), float(ask), None

        spread_pct = (ask - bid) / mid * 100
        return float(bid), float(ask), float(spread_pct)
    except Exception:
        return None, None, None

# --- Obliczenia metryk technicznych ---
def compute_metrics(symbol):
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

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = ((last - prev) / prev * 100) if prev != 0 else 0.0

    # ATR
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_series = tr.rolling(14).mean()
    atr = float(atr_series.iloc[-1]) if not atr_series.dropna().empty else 0.0

    # Trend (EMA)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema20_last = float(ema20.iloc[-1])
    ema50_last = float(ema50.iloc[-1])

    if last > ema20_last > ema50_last:
        trend = "UP"
    elif last < ema20_last < ema50_last:
        trend = "DOWN"
    else:
        trend = "SIDE"

    # Sygnał techniczny
    if trend == "UP" and change > 0:
        signal = "BUY"
    elif trend == "DOWN" and change < 0:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    # MomentumScore
    vol_last = float(volume.iloc[-1])
    vol_prev = float(volume.iloc[-2]) if len(volume) > 1 else vol_last
    vol_change = ((vol_last - vol_prev) / vol_prev * 100) if vol_prev != 0 else 0.0

    raw_momentum = change * 0.7 + vol_change * 0.3
    momentum_score = max(0.0, min(100.0, 50.0 + raw_momentum))

    # VolatilityScore (ATR / cena)
    vol_ratio = (atr / last * 100) if last != 0 else 0.0
    volatility_score = max(0.0, min(100.0, vol_ratio * 2))

    # TrendStrength
    trend_diff = abs(ema20_last - ema50_last) / last * 100 if last != 0 else 0.0
    trend_strength = max(0.0, min(100.0, trend_diff * 5))

    # RiskScore
    risk_raw = volatility_score
    risk_score = max(0.0, min(100.0, risk_raw))

    # SetupScore v1
    setup = 0.0
    if signal == "BUY":
        setup += 30
    elif signal == "SELL":
        setup += 20

    setup += momentum_score * 0.3
    setup += trend_strength * 0.3
    setup -= risk_score * 0.2

    setup_score = max(0.0, min(100.0, setup))

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

# --- ENTRY RISK (płynność, spread, slippage) ---
def compute_entry_risk(volume, spread_pct):
    if volume >= 2_000_000:
        liquidity = "HIGH"
    elif volume >= 500_000:
        liquidity = "MEDIUM"
    else:
        liquidity = "LOW"

    if spread_pct is None:
        spread_rating = "UNKNOWN"
    elif spread_pct < 0.5:
        spread_rating = "GOOD"
    elif spread_pct < 2:
        spread_rating = "OK"
    else:
        spread_rating = "BAD"

    if liquidity == "HIGH" and (spread_pct is not None and spread_pct < 1):
        slippage = "LOW"
    elif liquidity == "MEDIUM" or (spread_pct is not None and 1 <= spread_pct <= 3):
        slippage = "MEDIUM"
    else:
        slippage = "HIGH"

    return liquidity, spread_rating, slippage

# --- SL / TP strefy ---
def compute_sl_tp(last_price, atr, trend):
    if last_price is None or atr is None or last_price == 0:
        return None, None

    sl_zone = (last_price - atr * 1.5, last_price - atr * 1.0)
    tp_zone = (last_price + atr * 2.0, last_price + atr * 3.0)

    if trend == "UP":
        tp_zone = (tp_zone[0] * 1.01, tp_zone[1] * 1.02)
    elif trend == "DOWN":
        sl_zone = (sl_zone[0] * 0.98, sl_zone[1] * 0.99)

    return sl_zone, tp_zone

# --- Formatowanie paska NewsScore ---
def format_news_score(value):
    try:
        score = float(value)
    except Exception:
        score = 0.0

    score = max(0.0, min(100.0, score))
    length = 40
    filled = int(round(score / 100 * length))
    bar = "█" * filled + "░" * (length - filled)

    if score < 30:
        icon = "🟢"
    elif score < 60:
        icon = "🟠"
        # icon stays
    else:
        icon = "🔴"

    return f"{icon} {score:.0f} |{bar}|"

# --- Stylowanie tabeli (Heatmap + NewsScore) ---
def style_heatmap(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)

    for i, row in df.iterrows():
        ss = row["SetupScore"]
        intensity = min(max(ss / 100.0, 0.0), 1.0)
        base_color = "0,255,0" if ss >= 50 else "255,0,0"
        row_bg = f"background-color: rgba({base_color},{0.15 + 0.35*intensity})"

        for col in df.columns:
            styles.loc[i, col] = row_bg

        c = row["Change"]
        if c > 0:
            styles.loc[i, "Change"] = f"background-color: rgba(0,255,0,{min(abs(c)/10,1)})"
        elif c < 0:
            styles.loc[i, "Change"] = f"background-color: rgba(255,0,0,{min(abs(c)/10,1)})"
        else:
            styles.loc[i, "Change"] = "background-color: rgba(128,128,128,0.3)"

        if row["Trend"] == "UP":
            styles.loc[i, "Trend"] = "background-color: rgba(0,255,0,0.4)"
        elif row["Trend"] == "DOWN":
            styles.loc[i, "Trend"] = "background-color: rgba(255,0,0,0.4)"
        else:
            styles.loc[i, "Trend"] = "background-color: rgba(128,128,128,0.3)"

        if row["Signal"] == "BUY":
            styles.loc[i, "Signal"] = "background-color: rgba(0,255,0,0.6)"
        elif row["Signal"] == "SELL":
            styles.loc[i, "Signal"] = "background-color: rgba(255,0,0,0.6)"
        else:
            styles.loc[i, "Signal"] = "background-color: rgba(128,128,128,0.3)"

        if "NewsScore" in df.columns:
            ns = row.get("NewsScore", 0.0)
            try:
                ns = float(ns)
            except Exception:
                ns = 0.0
            ns = max(0.0, min(100.0, ns))

            if ns <= 50:
                t = ns / 50.0
                r = int(0 + t * (255 - 0))
                g = int(255 - t * (255 - 165))
                b = 0
            else:
                t = (ns - 50) / 50.0
                r = 255
                g = int(165 - t * 165)
                b = 0

            styles.loc[i, "NewsScore"] = f"background-color: rgba({r},{g},{b},0.35)"

    fmt_dict = {
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
        fmt_dict["NewsScore"] = format_news_score

    return df.style.apply(lambda _: styles, axis=None).format(fmt_dict)

# --- AI Verdict dla TOP 5 (techniczny) ---
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
   - gdzie ryzyko jest najwyższe,
   - co musi się stać, żeby setup był „A+”.

Pisz konkretnie, bez lania wody, po polsku.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Oto dane spółek:\n{context}"},
    ]

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
    )
    return res.choices[0].message.content

# --- Wykres PRO ---
def plot_pro_chart(symbol: str):
    df = get_price_data(symbol, "3mo", "1d")
    if df.empty:
        st.warning("Brak danych do wykresu.")
        return

    close = df["Close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    fig = go.Figure()
    fig.add_candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Cena",
    )
    fig.add_trace(go.Scatter(x=df.index, y=ema20, mode="lines", name="EMA20", line=dict(color="cyan")))
    fig.add_trace(go.Scatter(x=df.index, y=ema50, mode="lines", name="EMA50", line=dict(color="magenta")))
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean().abs()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.dropna()

    st.subheader("RSI(14)")
    st.line_chart(rsi)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_df = pd.DataFrame({"MACD": macd_line, "Signal": signal_line}).dropna()

    st.subheader("MACD")
    st.line_chart(macd_df)

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_series = tr.rolling(14).mean().dropna()

    st.subheader("ATR(14)")
    st.line_chart(atr_series)
# --- ALERTY ---
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

# --- PATTERNY ---
def detect_patterns_for_symbol(symbol: str):
    df = get_price_data(symbol, "3mo", "1d")
    if df.empty or len(df) < 30:
        return []

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    patterns = []

    rolling_max = close.rolling(20).max()
    rolling_min = close.rolling(20).min()
    last = close.iloc[-1]
    prev_max = rolling_max.iloc[-2]
    prev_min = rolling_min.iloc[-2]

    if last > prev_max:
        patterns.append("Breakout UP (wybicie powyżej 20-dniowego maksimum).")
    if last < prev_min:
        patterns.append("Breakout DOWN (wybicie poniżej 20-dniowego minimum).")

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_width = (std20 * 2).iloc[-1] / last * 100 if last != 0 else 0
    if bb_width < 3:
        patterns.append("Bollinger Squeeze (bardzo niska zmienność, możliwe wybicie).")

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

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    if ema20.iloc[-2] < ema50.iloc[-2] and ema20.iloc[-1] > ema50.iloc[-1]:
        patterns.append("Golden Cross (EMA20 przebiła EMA50 w górę).")
    if ema20.iloc[-2] > ema50.iloc[-2] and ema20.iloc[-1] < ema50.iloc[-1]:
        patterns.append("Death Cross (EMA20 przebiła EMA50 w dół).")

    return patterns

def detect_patterns_all(symbols):
    out = {}
    for s in symbols:
        pats = detect_patterns_for_symbol(s)
        if pats:
            out[s] = pats
    return out

# --- AI DEEP DIVE (TECHNICZNY, PROP-DESK MIDDLE MODE) ---
def ai_deep_dive(symbol: str, metrics: dict):
    text = (
        f"Symbol: {symbol}\n"
        f"SetupScore: {metrics['SetupScore']:.1f}\n"
        f"Change: {metrics['Change']:+.2f}%\n"
        f"Trend: {metrics['Trend']}\n"
        f"Signal: {metrics['Signal']}\n"
        f"MomentumScore: {metrics['MomentumScore']:.1f}\n"
        f"VolatilityScore: {metrics['VolatilityScore']:.1f}\n"
        f"RiskScore: {metrics['RiskScore']:.1f}\n"
        f"ATR: {metrics['ATR']:.4f}\n"
        f"Volume: {metrics['Volume']:.0f}\n"
    )

    system_prompt = """
Jesteś analitykiem prop‑desk. Mówisz po polsku.
Masz DANE LICZBOWE spółki i masz OBOWIĄZEK używać ich w analizie.
Nie wolno Ci pisać ogólników, banałów ani tekstów typu „warto obserwować sektor”.
Każdy punkt musi odnosić się do KONKRETNYCH wartości z danych.

Dane wejściowe zawierają:
- SetupScore
- Change %
- Trend
- Signal
- MomentumScore
- VolatilityScore
- RiskScore
- ATR
- Volume

Twoje zadanie:

1) Ocena setupu:
   - momentum, trend, zmienność, wolumen, sygnał.
   - używaj liczb: „MomentumScore 63 → presja kupujących rośnie”.

2) Mocne i słabe strony:
   - 2–3 punkty, każdy z liczbą.

3) Scenariusze:
   - byczy, niedźwiedzi, neutralny.
   - każdy w 1–2 zdaniach, każdy musi odnosić się do danych.

4) Strefy:
   - strefa ryzyka (opisowo, na podstawie ATR, zmienności, trendu),
   - strefa potencjału (na podstawie momentum, trendu, wolumenu).

ZAKAZY:
- Zero ogólników.
- Zero lania wody.
- Zero fantazji o sektorach.
- Zero porad inwestycyjnych.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
    )
    return res.choices[0].message.content

# --- MULTI-AI (4 style tradingu) ---
def multi_ai_verdict(top_df: pd.DataFrame) -> str:
    if top_df.empty:
        return "Brak spółek do analizy."

    context_lines = []
    for _, row in top_df.iterrows():
        context_lines.append(
            f"{row['Symbol']}: SetupScore={row['SetupScore']:.1f}, "
            f"Change={row['Change']:+.2f}%, Trend={row['Trend']}, "
            f"Signal={row['Signal']}, Momentum={row['MomentumScore']:.1f}, "
            f"Volatility={row['VolatilityScore']:.1f}, Risk={row['RiskScore']:.1f}"
        )
    context = "\n".join(context_lines)

    system_prompt = """
Jesteś panelem 4 różnych 'AI-traderów':
1) Konserwatywny risk manager
2) Agresywny momentum trader
3) Swing trader
4) Mean-reversion trader

Dostajesz listę spółek z metrykami (SetupScore, Trend, Signal, Momentum, Volatility, Risk).
Dla każdej spółki:
- każdy z 4 traderów daje 1–2 zdania swojego spojrzenia.
Na końcu:
- krótki konsensus: które tickery są najciekawsze dla którego stylu.

Pisz krótko, w formie:
[TYP TRADERA] komentarz...
Po polsku.
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

# --- AI NEWS: NewsScore dla wszystkich spółek ---
def ai_news_score_for_df(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}

    lines = []
    for _, row in df.iterrows():
        lines.append(
            f"{row['Symbol']}: "
            f"SetupScore={row['SetupScore']:.1f}, "
            f"Change={row['Change']:+.2f}%, "
            f"Trend={row['Trend']}, "
            f"Signal={row['Signal']}, "
            f"Momentum={row['MomentumScore']:.1f}, "
            f"Volatility={row['VolatilityScore']:.1f}, "
            f"Risk={row['RiskScore']:.1f}, "
            f"Volume={row['Volume']:.0f}"
        )
    context = "\n".join(lines)

    system_prompt = """
Jesteś analitykiem newsowym w stylu Bloomberg. Mówisz po polsku.
Masz listę spółek z danymi technicznymi i masz OBOWIĄZEK używać tych danych.
Twoim zadaniem jest wyliczyć NewsScore (0–100) jako MIX:
- ryzyko newsowe,
- potencjał wybicia pod newsy.

Używaj WYŁĄCZNIE danych:
- Change
- MomentumScore
- VolatilityScore
- RiskScore
- Volume
- Trend
- Signal

Logika:
- wysokie momentum → wyższy potencjał newsowy,
- wysoka zmienność → wyższe ryzyko gapów,
- duży wolumen → większa szansa na reakcję na newsy,
- silny trend → większa podatność na katalizatory,
- duży spadek lub wzrost → możliwe plotki.

Zwróć TYLKO linie:
TICKER: SCORE

Bez komentarzy, bez tekstu, bez wyjaśnień.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Dane spółek:\n{context}"},
    ]

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
    )
    content = res.choices[0].message.content

    scores = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        try:
            sym, val = line.split(":", 1)
            sym = sym.strip().upper()
            val = val.strip().replace("%", "").replace(",", ".")
            score = float(val)
            score = max(0.0, min(100.0, score))
            scores[sym] = score
        except Exception:
            continue

    return scores

# --- AI NEWS: Deep Dive News dla jednej spółki ---
def ai_news_deep_dive(symbol: str, metrics: dict, bid: float | None, ask: float | None, spread_pct: float | None):
    liquidity, spread_rating, slippage = compute_entry_risk(
        metrics["Volume"], spread_pct
    )
    sl_zone, tp_zone = compute_sl_tp(
        metrics["LastPrice"], metrics["ATR"], metrics["Trend"]
    )

    text = (
        f"Symbol: {symbol}\n"
        f"SetupScore: {metrics['SetupScore']:.1f}\n"
        f"Change: {metrics['Change']:+.2f}%\n"
        f"Trend: {metrics['Trend']}\n"
        f"Signal: {metrics['Signal']}\n"
        f"MomentumScore: {metrics['MomentumScore']:.1f}\n"
        f"VolatilityScore: {metrics['VolatilityScore']:.1f}\n"
        f"RiskScore: {metrics['RiskScore']:.1f}\n"
        f"ATR: {metrics['ATR']:.4f}\n"
        f"Volume: {metrics['Volume']:.0f}\n"
        f"Bid: {bid if bid is not None else 'brak danych'}\n"
        f"Ask: {ask if ask is not None else 'brak danych'}\n"
        f"SpreadPct: {spread_pct if spread_pct is not None else 'brak danych'}\n"
        f"Liquidity: {liquidity}\n"
        f"SpreadRating: {spread_rating}\n"
        f"SlippageRisk: {slippage}\n"
        f"SLzone: {sl_zone}\n"
        f"TPzone: {tp_zone}\n"
    )

    system_prompt = """
Jesteś analitykiem newsowym w stylu Bloomberg Terminal. Mówisz po polsku.
Masz DANE LICZBOWE spółki i masz OBOWIĄZEK używać ich w analizie.
Nie wolno Ci pisać ogólników, banałów ani tekstów typu „warto obserwować branżę”.
Każdy punkt musi odnosić się do KONKRETNYCH wartości z danych.

Dane wejściowe zawierają:
- SetupScore
- Change %
- Trend
- Signal
- MomentumScore
- VolatilityScore
- RiskScore
- ATR
- Volume
- Bid
- Ask
- SpreadPct
- Liquidity
- SpreadRating
- SlippageRisk
- SLzone
- TPzone

Twoje zadanie:

1) Kontekst rynkowy (tylko na podstawie danych):
   - momentum, zmienność, trend, wolumen, setup.
   - używaj liczb.

2) Earnings / wydarzenia (wnioskowanie z danych):
   - jeśli wolumen niski → brak sygnałów pod newsy,
   - jeśli wolumen rośnie → możliwe przygotowanie pod newsy,
   - jeśli zmienność wysoka → ryzyko gapów,
   - jeśli zmienność niska → brak presji.

3) Ryzyko newsowe:
   - oceniaj na podstawie VolatilityScore, Change, Volume, Trend.
   - używaj liczb.

4) Płynność i spread:
   - jeśli bid/ask brak → napisz to,
   - jeśli jest → oceń spread%:
       - <0.5% → płynność bardzo dobra,
       - 0.5–2% → płynność umiarkowana,
       - >2% → ryzyko poślizgu,
   - oceń ryzyko wejścia/wyjścia na podstawie Liquidity i SlippageRisk.

5) Scenariusze:
   - byczy, niedźwiedzi, neutralny,
   - każdy w 1–2 zdaniach,
   - każdy musi odnosić się do danych.

6) Strefy:
   - strefa ryzyka (SLzone),
   - strefa potencjału (TPzone),
   - opisz je w kontekście trendu i zmienności.

ZAKAZY:
- Zero ogólników.
- Zero lania wody.
- Zero fantazji o sektorach.
- Zero porad inwestycyjnych.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
    )
    return res.choices[0].message.content

# --- AI NEWS: News Radar ---
def ai_news_radar(df: pd.DataFrame) -> str:
    if df.empty:
        return "Brak spółek do analizy."

    lines = []
    for _, row in df.iterrows():
        ns = row.get("NewsScore", 0.0)
        lines.append(
            f"{row['Symbol']}: "
            f"NewsScore={ns:.1f}, "
            f"SetupScore={row['SetupScore']:.1f}, "
            f"Trend={row['Trend']}, "
            f"Signal={row['Signal']}, "
            f"Momentum={row['MomentumScore']:.1f}, "
            f"Volatility={row['VolatilityScore']:.1f}, "
            f"Risk={row['RiskScore']:.1f}, "
            f"Change={row['Change']:+.2f}%, "
            f"Volume={row['Volume']:.0f}"
        )
    context = "\n".join(lines)

    system_prompt = """
Jesteś analitykiem newsowym w stylu Bloomberg. Mówisz po polsku.
Masz listę spółek z:
- NewsScore
- SetupScore
- Trend
- Signal
- MomentumScore
- VolatilityScore
- RiskScore
- Change
- Volume

Twoje zadanie:

1) TOP 5 spółek z najwyższym NewsScore:
   - dla każdej 1–2 zdania DLACZEGO NewsScore jest wysoki,
   - używaj liczb.

2) Earnings / event candidates:
   - spółki z wysokim MomentumScore + rosnącym wolumenem,
   - spółki z wysoką zmiennością.

3) Ryzyko gapów:
   - spółki z wysokim VolatilityScore + wysokim NewsScore.

4) Komentarz sektorowy / makro:
   - tylko jeśli wynika z danych (np. wiele spółek ma wysoką zmienność).

5) Podsumowanie:
   - gdzie jest największe ryzyko,
   - gdzie największy potencjał wybicia.

ZAKAZY:
- Zero ogólników.
- Zero lania wody.
- Zero fantazji o sektorach.
- Zero porad inwestycyjnych.
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
def main():
    st.title("🔥 HEATMAPA PRO — Prop‑Desk Kombajn: AI + Wykres + Skaner + Alerty + Patterny + News")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []
    if "ai_top5_comment" not in st.session_state:
        st.session_state.ai_top5_comment = ""
    if "ai_deep_dive_cache" not in st.session_state:
        st.session_state.ai_deep_dive_cache = {}
    if "ai_multi_comment" not in st.session_state:
        st.session_state.ai_multi_comment = ""
    if "news_scores" not in st.session_state:
        st.session_state.news_scores = {}
    if "ai_news_deep_cache" not in st.session_state:
        st.session_state.ai_news_deep_cache = {}
    if "ai_news_radar_comment" not in st.session_state:
        st.session_state.ai_news_radar_comment = ""

    symbols_input = st.sidebar.text_input("Dodaj spółki (oddzielone przecinkami):", "")

    if st.sidebar.button("Dodaj"):
        for raw in symbols_input.split(","):
            sym = raw.strip().upper()
            if sym and sym not in st.session_state.symbols:
                st.session_state.symbols.append(sym)

    if st.sidebar.button("Wyczyść"):
        st.session_state.symbols = []
        st.session_state.ai_top5_comment = ""
        st.session_state.ai_deep_dive_cache = {}
        st.session_state.ai_multi_comment = ""
        st.session_state.news_scores = {}
        st.session_state.ai_news_deep_cache = {}
        st.session_state.ai_news_radar_comment = ""

    if not st.session_state.symbols:
        st.warning("Dodaj spółki, aby kontynuować.")
        return

    tab_heatmap, tab_chart, tab_scanner, tab_alerts, tab_patterns, tab_deep, tab_multi, tab_news = st.tabs([
        "📊 Heatmap PRO + AI + NewsScore",
        "📈 Wykres PRO",
        "📡 Skaner Sygnałów",
        "🚨 Alerty",
        "📐 Patterny",
        "🧠 AI Deep Dive",
        "🤝 Multi-AI Panel",
        "📰 News Radar",
    ])

    # --- HEATMAP + AI + NewsScore ---
    with tab_heatmap:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        df = df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

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
                    st.write(f"**SetupScore:** {ss:.1f} / 100")
                    st.write(f"**Change:** {row['Change']:+.2f}%")
                    st.write(f"**Trend:** {row['Trend']}")
                    st.write(f"**Signal:** {row['Signal']}")
                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}")
                    st.write(f"**Volatility:** {row['VolatilityScore']:.1f}")
                    st.write(f"**Risk:** {row['RiskScore']:.1f}")

            st.markdown("---")
            col_ai1, col_ai2 = st.columns(2)
            with col_ai1:
                if st.button("🧠 Generuj komentarz AI dla TOP 5"):
                    with st.spinner("AI analizuje TOP 5 setupów..."):
                        st.session_state.ai_top5_comment = ai_verdict_for_top5(top_df)
            with col_ai2:
                if st.button("📰 Generuj NewsScore dla wszystkich spółek"):
                    with st.spinner("AI analizuje news-ryzyko i potencjał wybicia..."):
                        st.session_state.news_scores = ai_news_score_for_df(df)

            if st.session_state.ai_top5_comment:
                st.subheader("🧠 Komentarz AI (prop‑desk view)")
                st.markdown(st.session_state.ai_top5_comment)

        if st.session_state.news_scores:
            df["NewsScore"] = df["Symbol"].map(st.session_state.news_scores).fillna(0.0)

        st.markdown("---")
        st.subheader("📊 Pełna tabela — Heatmapa PRO + NewsScore")
        st.dataframe(style_heatmap(df), use_container_width=True)

    # --- WYKRES PRO ---
    with tab_chart:
        st.subheader("📈 Wykres PRO dla wybranej spółki")
        symbol_for_chart = st.selectbox(
            "Wybierz spółkę do wykresu:", st.session_state.symbols
        )
        plot_pro_chart(symbol_for_chart)

    # --- SKANER SYGNAŁÓW ---
    with tab_scanner:
        st.subheader("📡 BUY / SELL Radar — Skaner Sygnałów")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        scan_df = pd.DataFrame(rows)
        scan_df = scan_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

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

        neutral_df = scan_df[
            ~scan_df.index.isin(buy_df.index) &
            ~scan_df.index.isin(sell_df.index)
        ]

        st.markdown("## 🟢 BUY Radar")
        if buy_df.empty:
            st.info("Brak mocnych sygnałów BUY.")
        else:
            cols = st.columns(min(5, len(buy_df)))
            for idx, (_, row) in enumerate(buy_df.iterrows()):
                with cols[idx % len(cols)]:
                    st.markdown(f"### 🟢 {row['Symbol']}")
                    st.write(f"**SetupScore:** {row['SetupScore']:.1f}")
                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}")
                    st.write(f"**Trend:** {row['Trend']}")
                    st.write(f"**Change:** {row['Change']:+.2f}%")

        st.markdown("---")

        st.markdown("## 🔴 SELL Radar")
        if sell_df.empty:
            st.info("Brak mocnych sygnałów SELL.")
        else:
            cols = st.columns(min(5, len(sell_df)))
            for idx, (_, row) in enumerate(sell_df.iterrows()):
                with cols[idx % len(cols)]:
                    st.markdown(f"### 🔴 {row['Symbol']}")
                    st.write(f"**SetupScore:** {row['SetupScore']:.1f}")
                    st.write(f"**Volatility:** {row['VolatilityScore']:.1f}")
                    st.write(f"**Trend:** {row['Trend']}")
                    st.write(f"**Change:** {row['Change']:+.2f}%")

        st.markdown("---")

        st.markdown("## 🟡 Neutral Radar")
        if neutral_df.empty:
            st.info("Brak neutralnych setupów.")
        else:
            st.dataframe(
                neutral_df[[
                    "Symbol", "SetupScore", "Trend", "Signal",
                    "MomentumScore", "VolatilityScore", "RiskScore"
                ]],
                use_container_width=True
            )

    # --- ALERTY ---
    with tab_alerts:
        st.subheader("🚨 Alerty z rynku (na bazie Heatmap PRO)")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        alert_df = pd.DataFrame(rows)
        alert_df = alert_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        alerts = generate_alerts(alert_df)

        if not alerts:
            st.info("Brak alertów spełniających kryteria.")
        else:
            for a in alerts:
                st.write("• " + a)

        st.markdown("---")
        st.write("Kryteria możesz zmienić w funkcji generate_alerts().")

    # --- PATTERNY ---
    with tab_patterns:
        st.subheader("📐 Patterny techniczne (breakout, squeeze, RSI, EMA cross)")

        patterns_all = detect_patterns_all(st.session_state.symbols)
        if not patterns_all:
            st.info("Brak wykrytych patternów dla obecnych spółek (lub za mało danych).")
        else:
            for sym, pats in patterns_all.items():
                st.markdown(f"### {sym}")
                for p in pats:
                    st.write("• " + p)
                st.markdown("---")

    # --- AI DEEP DIVE ---
    with tab_deep:
        st.subheader("🧠 AI Deep Dive — TECH + NEWS + Entry Risk / SL-TP")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        deep_df = pd.DataFrame(rows)
        deep_df = deep_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        symbol_for_deep = st.selectbox(
            "Wybierz spółkę do analizy AI:", deep_df["Symbol"].tolist()
        )

        metrics = deep_df[deep_df["Symbol"] == symbol_for_deep].iloc[0].to_dict()
        bid, ask, spread_pct = get_bid_ask(symbol_for_deep)
        liquidity, spread_rating, slippage = compute_entry_risk(
            metrics["Volume"], spread_pct
        )
        sl_zone, tp_zone = compute_sl_tp(
            metrics["LastPrice"], metrics["ATR"], metrics["Trend"]
        )

        st.markdown("### 📉 Ryzyko wejścia")
        st.write(f"**Bid:** {bid if bid is not None else 'brak danych'}")
        st.write(f"**Ask:** {ask if ask is not None else 'brak danych'}")
        st.write(f"**Spread%:** {spread_pct:.2f}%"
                 if spread_pct is not None else "**Spread%:** brak danych")
        st.write(f"**Płynność:** {liquidity}")
        st.write(f"**Spread rating:** {spread_rating}")
        st.write(f"**Ryzyko poślizgu:** {slippage}")

        st.markdown("### 🎯 Strefy SL / TP (ATR-based)")
        if sl_zone and tp_zone:
            st.write(f"**SL zone:** {sl_zone[0]:.4f} – {sl_zone[1]:.4f}")
            st.write(f"**TP zone:** {tp_zone[0]:.4f} – {tp_zone[1]:.4f}")
        else:
            st.write("Brak danych do wyznaczenia stref SL/TP.")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if st.button("🔍 Generuj AI Deep Dive (techniczny)"):
                with st.spinner("AI analizuje wybraną spółkę (technicznie)..."):
                    comment = ai_deep_dive(symbol_for_deep, metrics)
                    st.session_state.ai_deep_dive_cache[symbol_for_deep] = comment
        with col_d2:
            if st.button("📰 Generuj AI Deep Dive News"):
                with st.spinner("AI analizuje news-ryzyko i potencjał wybicia..."):
                    comment_news = ai_news_deep_dive(symbol_for_deep, metrics, bid, ask, spread_pct)
                    st.session_state.ai_news_deep_cache[symbol_for_deep] = comment_news

        if symbol_for_deep in st.session_state.ai_deep_dive_cache:
            st.subheader(f"🧠 AI TECH — {symbol_for_deep}")
            st.markdown(st.session_state.ai_deep_dive_cache[symbol_for_deep])

        if symbol_for_deep in st.session_state.ai_news_deep_cache:
            st.subheader(f"📰 AI NEWS — {symbol_for_deep}")
            st.markdown(st.session_state.ai_news_deep_cache[symbol_for_deep])

    # --- MULTI-AI PANEL ---
    with tab_multi:
        st.subheader("🤝 Multi-AI Panel — 4 style tradingu na TOP setupach")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        multi_df = pd.DataFrame(rows)
        multi_df = multi_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)
        top_n = min(5, len(multi_df))
        top_df = multi_df.head(top_n)

        if st.button("🤝 Generuj Multi-AI werdykt dla TOP setupów"):
            with st.spinner("AI generuje panel 4 stylów tradingu..."):
                st.session_state.ai_multi_comment = multi_ai_verdict(top_df)

        if st.session_state.ai_multi_comment:
            st.subheader("🤝 Multi-AI Panel — komentarze")
            st.markdown(st.session_state.ai_multi_comment)

    # --- NEWS RADAR ---
    with tab_news:
        st.subheader("📰 News Radar — NewsScore + ryzyko newsowe / potencjał wybicia")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        news_df = pd.DataFrame(rows)
        news_df = news_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        if st.session_state.news_scores:
            news_df["NewsScore"] = news_df["Symbol"].map(st.session_state.news_scores).fillna(0.0)

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("📰 Generuj / odśwież NewsScore (wszystkie spółki)"):
                with st.spinner("AI liczy NewsScore (mix ryzyka i potencjału)..."):
                    st.session_state.news_scores = ai_news_score_for_df(news_df)
                    news_df["NewsScore"] = news_df["Symbol"].map(st.session_state.news_scores).fillna(0.0)
        with col_n2:
            if st.button("📡 Generuj News Radar (AI raport)"):
                with st.spinner("AI generuje News Radar..."):
                    if "NewsScore" not in news_df.columns and st.session_state.news_scores:
                        news_df["NewsScore"] = news_df["Symbol"].map(st.session_state.news_scores).fillna(0.0)
                    st.session_state.ai_news_radar_comment = ai_news_radar(news_df)

        st.markdown("---")
        st.subheader("📊 Tabela z NewsScore")
        if st.session_state.news_scores:
            news_df["NewsScore"] = news_df["Symbol"].map(st.session_state.news_scores).fillna(0.0)
            st.dataframe(
                style_heatmap(news_df),
                use_container_width=True
            )
        else:
            st.info("Brak NewsScore — kliknij przycisk, aby wygenerować.")

        if st.session_state.ai_news_radar_comment:
            st.markdown("---")
            st.subheader("📰 AI News Radar — komentarz")
            st.markdown(st.session_state.ai_news_radar_comment)


if __name__ == "__main__":
    main()
