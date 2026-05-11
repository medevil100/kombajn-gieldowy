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

# --- ENTRY RISK ---
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

# --- SL / TP ---
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

# --- TREND EVALUATION (MODEL C) ---
def compute_trend_evaluation(
    last_price: float,
    change_pct: float,
    momentum_score: float,
    volatility_score: float,
    trend_strength: float,
    volume_current: float,
    volume_prev: float,
    ema20_last: float,
    ema50_last: float,
    atr: float,
):
    try:
        mom = max(0.0, min(100.0, float(momentum_score)))
    except:
        mom = 50.0

    try:
        vol = max(0.0, min(100.0, float(volatility_score)))
    except:
        vol = 50.0

    try:
        ts = max(0.0, min(100.0, float(trend_strength)))
    except:
        ts = 50.0

    try:
        ch = float(change_pct)
    except:
        ch = 0.0

    if volume_prev and volume_prev > 0:
        vol_trend = (volume_current - volume_prev) / volume_prev * 100.0
    else:
        vol_trend = 0.0

    if last_price:
        ema_div = abs(ema20_last - ema50_last) / last_price * 100.0
    else:
        ema_div = 0.0

    if last_price and atr:
        atr_pct = atr / last_price * 100.0
    else:
        atr_pct = 0.0

    ch_clamped = max(-5.0, min(5.0, ch))
    comp_change = 50.0 + (ch_clamped / 5.0) * 50.0

    vt_clamped = max(-50.0, min(50.0, vol_trend))
    comp_vol_trend = 50.0 + (vt_clamped / 50.0) * 50.0

    comp_volatility = 100.0 - vol

    ema_div_clamped = max(0.0, min(5.0, ema_div))
    comp_ema_div = (ema_div_clamped / 5.0) * 100.0

    atr_clamped = max(0.0, min(5.0, atr_pct))
    comp_atr_stab = 100.0 - (atr_clamped / 5.0) * 100.0

    trend_score = (
        ts * 0.25
        + mom * 0.25
        + comp_change * 0.15
        + comp_vol_trend * 0.10
        + comp_volatility * 0.10
        + comp_ema_div * 0.10
        + comp_atr_stab * 0.05
    )

    trend_score = max(0.0, min(100.0, trend_score))

    if trend_score >= 75:
        health = "STRONG"
    elif trend_score >= 55:
        health = "HEALTHY"
    elif trend_score >= 35:
        health = "WEAK"
    else:
        health = "REVERSAL RISK"

    if trend_score >= 70:
        confidence = "HIGH"
    elif trend_score >= 45:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    if trend_score < 40 and vol > 60:
        reversal_risk = "HIGH"
    elif trend_score < 55 and vol > 50:
        reversal_risk = "MEDIUM"
    else:
        reversal_risk = "LOW"

    flags = []
    if mom >= 60 and ts >= 60:
        flags.append("Momentum zgodne z trendem.")
    elif mom < 40 and ts >= 60:
        flags.append("Silny trend, ale momentum słabnie.")
    elif mom >= 60 and ts < 40:
        flags.append("Silne momentum, ale trend strukturalnie słaby.")

    if vol_trend > 20:
        flags.append("Wolumen rośnie i potwierdza ruch.")
    elif vol_trend < -20:
        flags.append("Wolumen spada — ruch może być słabszy.")

    if vol > 70:
        flags.append("Bardzo wysoka zmienność — większe ryzyko szarpania.")
    elif vol < 30:
        flags.append("Niska zmienność — trend stabilny.")

    if reversal_risk == "HIGH":
        comment = "Trend jest kruchy: wysoka zmienność i niska jakość trendu sugerują ryzyko odwrócenia."
    elif health == "STRONG":
        comment = "Trend wygląda bardzo solidnie: momentum, struktura i wolumen wspierają kierunek ruchu."
    elif health == "HEALTHY":
        comment = "Trend jest zdrowy — obserwuj momentum i wolumen."
    elif health == "WEAK":
        comment = "Trend jest osłabiony — część metryk nie potwierdza kierunku."
    else:
        comment = "Struktura trendu słaba, zmienność wysoka — ryzyko odwrócenia zauważalne."

    return {
        "TrendScore": float(trend_score),
        "TrendHealth": health,
        "TrendConfidence": confidence,
        "TrendReversalRisk": reversal_risk,
        "TrendFlags": flags,
        "TrendComment": comment,
    }

# --- METRYKI ---
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
            "TrendScore": 0.0,
            "TrendHealth": "UNKNOWN",
            "TrendConfidence": "UNKNOWN",
            "TrendReversalRisk": "UNKNOWN",
            "TrendComment": "",
        }

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = ((last - prev) / prev * 100) if prev != 0 else 0.0

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

    if trend == "UP" and change > 0:
        signal = "BUY"
    elif trend == "DOWN" and change < 0:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    vol_last = float(volume.iloc[-1])
    vol_prev = float(volume.iloc[-2]) if len(volume) > 1 else vol_last
    vol_change = ((vol_last - vol_prev) / vol_prev * 100) if vol_prev != 0 else 0.0

    raw_momentum = change * 0.7 + vol_change * 0.3
    momentum_score = max(0.0, min(100.0, 50.0 + raw_momentum))

    vol_ratio = (atr / last * 100) if last != 0 else 0.0
    volatility_score = max(0.0, min(100.0, vol_ratio * 2))

    trend_diff = abs(ema20_last - ema50_last) / last * 100 if last != 0 else 0.0
    trend_strength = max(0.0, min(100.0, trend_diff * 5))

    risk_score = max(0.0, min(100.0, volatility_score))

    setup = 0.0
    if signal == "BUY":
        setup += 30
    elif signal == "SELL":
        setup += 20

    setup += momentum_score * 0.3
    setup += trend_strength * 0.3
    setup -= risk_score * 0.2

    setup_score = max(0.0, min(100.0, setup))

    trend_eval = compute_trend_evaluation(
        last_price=last,
        change_pct=change,
        momentum_score=momentum_score,
        volatility_score=volatility_score,
        trend_strength=trend_strength,
        volume_current=vol_last,
        volume_prev=vol_prev,
        ema20_last=ema20_last,
        ema50_last=ema50_last,
        atr=atr,
    )

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
        "TrendScore": trend_eval["TrendScore"],
        "TrendHealth": trend_eval["TrendHealth"],
        "TrendConfidence": trend_eval["TrendConfidence"],
        "TrendReversalRisk": trend_eval["TrendReversalRisk"],
        "TrendComment": trend_eval["TrendComment"],
        "TrendFlags": trend_eval["TrendFlags"],
    }

# --- Formatowanie paska NewsScore ---
def format_news_score(value):
    try:
        score = float(value)
    except:
        score = 0.0

    score = max(0.0, min(100.0, score))
    length = 40
    filled = int(round(score / 100 * length))
    bar = "█" * filled + "░" * (length - filled)

    if score < 30:
        icon = "🟢"
    elif score < 60:
        icon = "🟠"
    else:
        icon = "🔴"

    return f"{icon} {score:.0f} |{bar}|"

# --- Stylowanie tabeli ---
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
            except:
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
        "TrendScore": "{:.1f}",
    }

    if "NewsScore" in df.columns:
        fmt_dict["NewsScore"] = format_news_score

    return df.style.apply(lambda _: styles, axis=None).format(fmt_dict)

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

# --- AI VERDICT TOP5 (TECH) ---
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
            f"Risk={row['RiskScore']:.1f}, "
            f"TrendScore={row.get('TrendScore',0):.1f}"
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
- TrendScore

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

# --- AI DEEP DIVE TECH ---
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
        f"TrendScore: {metrics.get('TrendScore', 0):.1f}\n"
        f"TrendHealth: {metrics.get('TrendHealth', 'UNKNOWN')}\n"
        f"TrendConfidence: {metrics.get('TrendConfidence', 'UNKNOWN')}\n"
        f"TrendReversalRisk: {metrics.get('TrendReversalRisk', 'UNKNOWN')}\n"
    )

    system_prompt = """
Jesteś analitykiem prop‑desk. Mówisz po polsku.
Masz DANE LICZBOWE spółki i masz OBOWIĄZEK używać ich w analizie.

Dane:
- SetupScore
- Change %
- Trend
- Signal
- MomentumScore
- VolatilityScore
- RiskScore
- ATR
- Volume
- TrendScore (0–100)
- TrendHealth (STRONG / HEALTHY / WEAK / REVERSAL RISK)
- TrendConfidence (HIGH / MEDIUM / LOW)
- TrendReversalRisk (LOW / MEDIUM / HIGH)

Zadanie:
1) Ocena setupu (momentum, trend, zmienność, wolumen, sygnał) z użyciem liczb.
2) Mocne i słabe strony (2–3 punkty, każdy z liczbą).
3) Scenariusze: byczy, niedźwiedzi, neutralny (1–2 zdania, oparte na danych).
4) Ocena trendu:
   - wykorzystaj TrendScore, TrendHealth, TrendReversalRisk,
   - jasno powiedz, czy trend jest zdrowy, przeciążony czy zagrożony odwróceniem.

Zero ogólników, zero lania wody, zero porad inwestycyjnych.
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

# --- MULTI-AI ---
def multi_ai_verdict(top_df: pd.DataFrame) -> str:
    if top_df.empty:
        return "Brak spółek do analizy."

    context_lines = []
    for _, row in top_df.iterrows():
        context_lines.append(
            f"{row['Symbol']}: SetupScore={row['SetupScore']:.1f}, "
            f"Change={row['Change']:+.2f}%, Trend={row['Trend']}, "
            f"Signal={row['Signal']}, Momentum={row['MomentumScore']:.1f}, "
            f"Volatility={row['VolatilityScore']:.1f}, Risk={row['RiskScore']:.1f}, "
            f"TrendScore={row.get('TrendScore',0):.1f}"
        )
    context = "\n".join(context_lines)

    system_prompt = """
Jesteś panelem 4 różnych 'AI-traderów':
1) Konserwatywny risk manager
2) Agresywny momentum trader
3) Swing trader
4) Mean-reversion trader

Dostajesz listę spółek z metrykami (SetupScore, Trend, Signal, Momentum, Volatility, Risk, TrendScore).
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

# --- AI NEWS: NewsScore ---
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
            f"Volume={row['Volume']:.0f}, "
            f"TrendScore={row.get('TrendScore',0):.1f}"
        )
    context = "\n".join(lines)

    system_prompt = """
Jesteś analitykiem newsowym w stylu Bloomberg. Mówisz po polsku.
Masz listę spółek z danymi technicznymi.
Masz wyliczyć NewsScore (0–100) jako mix:
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
- TrendScore

Zwróć TYLKO linie:
TICKER: SCORE
Bez komentarzy.
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
        except:
            continue
    return scores

# --- AI NEWS: Deep Dive News ---
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
        f"TrendScore: {metrics.get('TrendScore', 0):.1f}\n"
        f"TrendHealth: {metrics.get('TrendHealth', 'UNKNOWN')}\n"
        f"TrendConfidence: {metrics.get('TrendConfidence', 'UNKNOWN')}\n"
        f"TrendReversalRisk: {metrics.get('TrendReversalRisk', 'UNKNOWN')}\n"
    )

    system_prompt = """
Jesteś analitykiem newsowym w stylu Bloomberg Terminal. Mówisz po polsku.
Masz dane:
- SetupScore, Change, Trend, Signal
- MomentumScore, VolatilityScore, RiskScore
- ATR, Volume
- Bid, Ask, SpreadPct
- Liquidity, SpreadRating, SlippageRisk
- SLzone, TPzone
- TrendScore, TrendHealth, TrendConfidence, TrendReversalRisk

Zadanie:
1) Kontekst rynkowy (tylko z danych).
2) Ryzyko newsowe (gap, gwałtowne ruchy).
3) Płynność i spread (wejście/wyjście, poślizg).
4) Scenariusze: byczy, niedźwiedzi, neutralny (1–2 zdania każdy).
5) Strefy: SLzone, TPzone w kontekście trendu i zmienności.
6) Wykorzystaj TrendScore / TrendHealth / TrendReversalRisk do oceny, czy newsy mogą wzmocnić czy złamać trend.

Zero ogólników, zero lania wody, zero porad inwestycyjnych.
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
            f"TrendScore={row.get('TrendScore',0):.1f}, "
            f"Change={row['Change']:+.2f}%, "
            f"Volume={row['Volume']:.0f}"
        )
    context = "\n".join(lines)

    system_prompt = """
Jesteś analitykiem newsowym w stylu Bloomberg. Mówisz po polsku.
Masz:
- NewsScore
- SetupScore
- Trend, Signal
- MomentumScore, VolatilityScore, RiskScore
- TrendScore
- Change, Volume

Zadanie:
1) TOP 5 z najwyższym NewsScore — dlaczego są wysoko (z liczbami).
2) Kandydaci pod event/earnings (wysokie momentum + wolumen / zmienność).
3) Ryzyko gapów (wysoka VolatilityScore + wysoki NewsScore).
4) Krótkie podsumowanie: gdzie największe ryzyko, gdzie największy potencjał wybicia.

Zero ogólników, zero lania wody, zero porad inwestycyjnych.
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

    # --- HEATMAP ---
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
                    st.write(f"**TrendScore:** {row.get('TrendScore',0):.1f}")

           st.markdown("""
<style>

    /* --- GLOBAL BLOOMBERG DARK MODE --- */
    body, .stApp {
        background-color: #0d0d0d !important;
        color: #e6e6e6 !important;
        font-family: "Segoe UI", sans-serif;
    }

    /* --- TABELA: pełna szerokość + ciemny styl --- */
    [data-testid="stDataFrame"] {
        background-color: #0d0d0d !important;
        border: 1px solid #333 !important;
        border-radius: 6px !important;
        padding: 10px !important;
    }

    /* --- Komórki tabeli --- */
    .dataframe tbody tr th, .dataframe tbody tr td {
        background-color: #111 !important;
        color: #e6e6e6 !important;
        font-size: 17px !important;
        padding: 10px 14px !important;
        border-color: #222 !important;
    }

    /* --- Nagłówki tabeli --- */
    .dataframe thead th {
        background-color: #1a1a1a !important;
        color: #f2f2f2 !important;
        font-size: 18px !important;
        border-bottom: 2px solid #444 !important;
        padding: 12px !important;
    }

    /* --- Scrollbar Bloomberg --- */
    ::-webkit-scrollbar {
        width: 12px;
        height: 12px;
    }
    ::-webkit-scrollbar-track {
        background: #0d0d0d;
    }
    ::-webkit-scrollbar-thumb {
        background: #444;
        border-radius: 6px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #666;
    }

    /* --- Podświetlenia (Twoje kolory heatmapy zostają) --- */
    .stDataFrame td {
        transition: background-color 0.2s ease-in-out;
    }
    .stDataFrame td:hover {
        background-color: #333 !important;
    }

</style>
""", unsafe_allow_html=True)
 

    # --- WYKRES PRO ---
    with tab_chart:
        st.subheader("📈 Wykres PRO dla wybranej spółki")
        symbol_for_chart = st.selectbox(
            "Wybierz spółkę do wykresu:", st.session_state.symbols
        )
        plot_pro_chart(symbol_for_chart)

    # --- SKANER ---
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
                    "MomentumScore", "VolatilityScore", "RiskScore", "TrendScore"
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
            st.info("Brak wykrytych patternów (lub za mało danych).")
        else:
            for sym, pats in patterns_all.items():
                st.markdown(f"### {sym}")
                for p in pats:
                    st.write("• " + p)
                st.markdown("---")

    # --- AI DEEP DIVE ---
    with tab_deep:
        st.subheader("🧠 AI Deep Dive — TECH + NEWS + Entry Risk / SL-TP + Trend")

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

        st.markdown("### 📈 Ocena trendu")
        st.write(f"**TrendScore:** {metrics.get('TrendScore', 0):.1f} / 100")
        st.write(f"**Trend Health:** {metrics.get('TrendHealth', 'UNKNOWN')}")
        st.write(f"**Trend Confidence:** {metrics.get('TrendConfidence', 'UNKNOWN')}")
        st.write(f"**Ryzyko odwrócenia trendu:** {metrics.get('TrendReversalRisk', 'UNKNOWN')}")

        flags = metrics.get("TrendFlags", None)
        comment_trend = metrics.get("TrendComment", None)

        if flags:
            st.write("**Sygnały dot. trendu:**")
            for f in flags:
                st.write("• " + f)

        if comment_trend:
            st.write("**Komentarz trendowy:**")
            st.write(comment_trend)

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

    # --- MULTI-AI ---
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
