
import os
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

# ============================================================
# ======================  KONFIGURACJA STRONY  ===============
# ============================================================

st.set_page_config(page_title="KOMBAJN v2.1", layout="wide")

# ============================================================
# ======================  ULTRA DARK NEON CSS  ===============
# ============================================================

st.markdown("""
<style>
body, .stApp {
    background-color: #05060a !important;
    color: #e5e5f5 !important;
    font-family: "Segoe UI", system-ui, sans-serif;
}
[data-testid="stSidebar"] {
    background-color: #05060a !important;
    border-right: 1px solid #181b24 !important;
}
[data-testid="stDataFrame"] {
    background-color: #05060a !important;
    border: 1px solid #181b24 !important;
    border-radius: 6px !important;
    padding: 6px !important;
}
.dataframe tbody tr th, .dataframe tbody tr td {
    background-color: #090b12 !important;
    color: #e5e5f5 !important;
    font-size: 14px !important;
    padding: 5px 8px !important;
    border-color: #181b24 !important;
}
.dataframe thead th {
    background-color: #101322 !important;
    color: #f5f5ff !important;
    font-size: 14px !important;
    border-bottom: 2px solid #262a3a !important;
    padding: 6px 8px !important;
}
h1, h2, h3, h4 {
    color: #f5f5ff !important;
}
.stButton>button {
    background: linear-gradient(90deg, #1f2937, #111827) !important;
    color: #e5e5ff !important;
    border-radius: 4px !important;
    border: 1px solid #4c1d95 !important;
}
.stButton>button:hover {
    background: linear-gradient(90deg, #312e81, #1f2937) !important;
    border-color: #7c3aed !important;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# ======================  OPENAI CONFIG  ======================
# ============================================================

AI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================================
# ======================  FUNKCJE BAZOWE  =====================
# ============================================================

def get_price_data(symbol, period="5d", interval="1h"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

def get_bid_ask(symbol: str):
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        bid = info.get("bid", None)
        ask = info.get("ask", None)
        if bid is None or ask is None or bid == 0 or ask == 0:
            return None, None, None
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid * 100 if mid else None
        return float(bid), float(ask), float(spread_pct)
    except:
        return None, None, None

def compute_entry_risk(volume, spread_pct):
    if volume >= 2_000_000:
        liquidity = "WYSOKA"
    elif volume >= 500_000:
        liquidity = "ŚREDNIA"
    else:
        liquidity = "NISKA"

    if spread_pct is None:
        spread_rating = "NIEZNANY"
    elif spread_pct < 0.5:
        spread_rating = "DOBRY"
    elif spread_pct < 2:
        spread_rating = "OK"
    else:
        spread_rating = "SŁABY"

    if liquidity == "WYSOKA" and (spread_pct is not None and spread_pct < 1):
        slippage = "NISKIE"
    elif liquidity == "ŚREDNIA" or (spread_pct is not None and 1 <= spread_pct <= 3):
        slippage = "ŚREDNIE"
    else:
        slippage = "WYSOKIE"

    return liquidity, spread_rating, slippage

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

def compute_trend_evaluation(
    last_price, change_pct, momentum_score, volatility_score,
    trend_strength, volume_current, volume_prev, ema20_last, ema50_last, atr
):
    try: mom = max(0.0, min(100.0, float(momentum_score)))
    except: mom = 50.0
    try: vol = max(0.0, min(100.0, float(volatility_score)))
    except: vol = 50.0
    try: ts = max(0.0, min(100.0, float(trend_strength)))
    except: ts = 50.0
    try: ch = float(change_pct)
    except: ch = 0.0

    vol_trend = ((volume_current - volume_prev) / volume_prev * 100.0) if volume_prev else 0.0
    ema_div = abs(ema20_last - ema50_last) / last_price * 100 if last_price else 0.0
    atr_pct = atr / last_price * 100 if last_price else 0.0

    comp_change = 50 + max(-5, min(5, ch)) * 10
    comp_vol_trend = 50 + max(-50, min(50, vol_trend))
    comp_volatility = 100 - vol
    comp_ema_div = min(100, (min(5, ema_div) / 5) * 100)
    comp_atr_stab = 100 - min(100, (min(5, atr_pct) / 5) * 100)

    trend_score = (
        ts * 0.25 + mom * 0.25 + comp_change * 0.15 +
        comp_vol_trend * 0.10 + comp_volatility * 0.10 +
        comp_ema_div * 0.10 + comp_atr_stab * 0.05
    )
    trend_score = max(0, min(100, trend_score))

    if trend_score >= 75: health = "SILNY TREND"
    elif trend_score >= 55: health = "ZDROWY TREND"
    elif trend_score >= 35: health = "SŁABY TREND"
    else: health = "RYZYKO ODWRÓCENIA"

    if trend_score >= 70: confidence = "WYSOKIE"
    elif trend_score >= 45: confidence = "ŚREDNIE"
    else: confidence = "NISKIE"

    if trend_score < 40 and vol > 60: reversal_risk = "WYSOKIE"
    elif trend_score < 55 and vol > 50: reversal_risk = "ŚREDNIE"
    else: reversal_risk = "NISKIE"

    return {
        "TrendScore": trend_score,
        "TrendHealth": health,
        "TrendConfidence": confidence,
        "TrendReversalRisk": reversal_risk,
        "TrendFlags": [],
        "TrendComment": "",
    }

# ============================================================
# ======================  METRYKI GŁÓWNE  =====================
# ============================================================

def compute_metrics(symbol):
    df = get_price_data(symbol, "5d", "1h")
    if df.empty or len(df) < 3:
        return {
            "Symbol": symbol,
            "LastPrice": 0.0,
            "Change": 0.0,
            "Volume": 0.0,
            "ATR": 0.0,
            "Trend": "BRAK",
            "Signal": "NEUTRAL",
            "MomentumScore": 0.0,
            "VolatilityScore": 0.0,
            "TrendStrength": 0.0,
            "RiskScore": 50.0,
            "SetupScore": 0.0,
            "TrendScore": 0.0,
            "TrendHealth": "NIEZNANY",
            "TrendConfidence": "NIEZNANE",
            "TrendReversalRisk": "NIEZNANE",
            "TrendComment": "",
            "TrendFlags": [],
            "SL_Low": None,
            "SL_High": None,
            "TP_Low": None,
            "TP_High": None,
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

    sl_zone, tp_zone = compute_sl_tp(last, atr, trend)

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
        "SL_Low": sl_zone[0] if sl_zone else None,
        "SL_High": sl_zone[1] if sl_zone else None,
        "TP_Low": tp_zone[0] if tp_zone else None,
        "TP_High": tp_zone[1] if tp_zone else None,
    }

# ============================================================
# ======================  HEATMAP STYLE  ======================
# ============================================================

def style_heatmap(df):
    def color_row(row):
        styles = []
        for col in df.columns:
            if col in ["SetupScore", "TrendScore"]:
                val = row[col]
                if val >= 70:
                    styles.append("background-color: #16a34a; color: #020617;")
                elif val >= 50:
                    styles.append("background-color: #eab308; color: #020617;")
                else:
                    styles.append("background-color: #dc2626; color: #f9fafb;")
            else:
                styles.append("")
        return styles
    return df.style.apply(color_row, axis=1)

# ============================================================
# ======================  WYKRES PRO  =========================
# ============================================================

def plot_pro_chart(symbol):
    df = get_price_data(symbol, "5d", "1h")
    if df.empty:
        st.warning(f"Brak danych dla {symbol}")
        return

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name="Świece"
    ))

    ema20 = df["Close"].ewm(span=20, adjust=False).mean()
    ema50 = df["Close"].ewm(span=50, adjust=False).mean()

    fig.add_trace(go.Scatter(x=df.index, y=ema20, mode="lines", name="EMA20", line=dict(color="#22c55e")))
    fig.add_trace(go.Scatter(x=df.index, y=ema50, mode="lines", name="EMA50", line=dict(color="#38bdf8")))

    fig.update_layout(
        template="plotly_dark",
        height=600,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
    )

    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# ======================  ALERTY  =============================
# ============================================================

def generate_alerts(df):
    alerts = []
    for _, row in df.iterrows():
        if row["Signal"] == "BUY" and row["SetupScore"] >= 60:
            alerts.append(f"🟢 BUY: {row['Symbol']} (Setup {row['SetupScore']:.1f}, Trend {row['TrendHealth']})")
        if row["Signal"] == "SELL" and row["SetupScore"] >= 50:
            alerts.append(f"🔴 SELL: {row['Symbol']} (Setup {row['SetupScore']:.1f}, Trend {row['TrendHealth']})")
    return alerts

# ============================================================
# ======================  PATTERNY  ===========================
# ============================================================

def detect_patterns_for_symbol(symbol):
    df = get_price_data(symbol, "5d", "1h")
    if df.empty or len(df) < 20:
        return []

    patterns = []
    close = df["Close"]

    if close.iloc[-1] > close.rolling(20).max().iloc[-2]:
        patterns.append("📈 Wybicie 20‑dniowego szczytu")

    if close.iloc[-1] < close.rolling(20).min().iloc[-2]:
        patterns.append("📉 Wybicie 20‑dniowego dołka")

    return patterns

def detect_patterns_all(symbols):
    out = {}
    for s in symbols:
        pats = detect_patterns_for_symbol(s)
        if pats:
            out[s] = pats
    return out

# ============================================================
# ======================  AI FUNKCJE  =========================
# ============================================================

def ai_verdict_for_top5(df):
    syms = ", ".join(df["Symbol"].tolist())
    prompt = f"Analizuj spółki: {syms}. Daj krótki werdykt tradingowy po polsku, konkretnie, jak prop‑trader."
    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

def ai_deep_dive(symbol, metrics):
    prompt = f"Zrób techniczny deep dive dla {symbol} na podstawie danych: {metrics}. Po polsku, konkretnie."
    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

def ai_news_score_for_df(df):
    scores = {}
    for _, row in df.iterrows():
        prompt = f"Na podstawie ostatnich newsów oceń NewsScore (0-100) dla {row['Symbol']}. Podaj tylko liczbę."
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        try:
            scores[row["Symbol"]] = float(resp.choices[0].message.content.strip())
        except:
            scores[row["Symbol"]] = 50.0
    return scores

def ai_news_deep_dive(symbol, metrics, bid, ask, spread_pct):
    prompt = (
        f"Analiza newsowa dla {symbol}. Dane: {metrics}, bid={bid}, ask={ask}, "
        f"spread={spread_pct}. Po polsku, jak prop‑trader, konkretnie."
    )
    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

def ai_news_radar(df):
    prompt = f"Zrób News Radar dla tych spółek (po polsku, krótko i konkretnie): {df.to_dict()}"
    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

def ai_turbo_v2(df):
    syms = ", ".join(df["Symbol"].tolist())
    prompt = f"""
Jesteś traderem z prop‑desku. Analizujesz: {syms}.
Daj 4‑stylowy werdykt po polsku:

SCALPER:
DAY‑TRADER:
SWING:
POSITION:
"""
    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

# ============================================================
# ======================  SEKTOR / PRE‑MARKET  ================
# ============================================================

SECTOR_MAP = {
    # Możesz uzupełnić pod siebie, np.:
    # "AAPL": "Technologia",
    # "MSFT": "Technologia",
}

def get_sector(symbol):
    return SECTOR_MAP.get(symbol.upper(), "Inne")

def get_premarket(symbol):
    try:
        info = yf.Ticker(symbol).info
        pre = info.get("preMarketPrice", None)
        last = info.get("regularMarketPreviousClose", None)
        if pre and last:
            return (pre - last) / last * 100
        return None
    except:
        return None

def apply_prop_filters(df):
    df = df.copy()
    df["PropScore"] = (
        df["MomentumScore"] * 0.40 +
        df["TrendStrength"] * 0.30 +
        df["SetupScore"] * 0.20 -
        df["VolatilityScore"] * 0.10
    )
    df["PropScore"] = df["PropScore"].clip(0, 100)
    return df.sort_values("PropScore", ascending=False)

# ============================================================
# ==========================  MAIN  ===========================
# ============================================================

def main():
    st.title("🔥 KOMBAJN v2.1 — Ultra Dark Neon + Prop‑Desk AI")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []
    if "ai_turbo" not in st.session_state:
        st.session_state.ai_turbo = ""
    if "news_scores" not in st.session_state:
        st.session_state.news_scores = {}

    st.sidebar.header("⚙️ Ustawienia")

    prop_mode = st.sidebar.selectbox(
        "Tryb pracy:",
        ["Standard", "Prop‑Trader Mode"],
        index=0
    )

    symbols_input = st.sidebar.text_input("Dodaj tickery (oddzielone przecinkami):")

    if st.sidebar.button("Dodaj"):
        for raw in symbols_input.split(","):
            sym = raw.strip().upper()
            if sym and sym not in st.session_state.symbols:
                st.session_state.symbols.append(sym)

    if st.sidebar.button("Wyczyść"):
        st.session_state.symbols = []
        st.session_state.ai_turbo = ""
        st.session_state.news_scores = {}

    if not st.session_state.symbols:
        st.warning("Dodaj spółki w sidebarze, aby rozpocząć.")
        return

    tab_heatmap, tab_chart, tab_scanner, tab_sector, tab_premarket = st.tabs([
        "📊 Heatmapa PRO",
        "📈 Wykres PRO",
        "📡 Skaner sygnałów",
        "🏭 Heatmapa sektorowa",
        "🌅 Pre‑Market Radar",
    ])

    # ---------------- HEATMAPA PRO ----------------
    with tab_heatmap:
        st.subheader("📊 Heatmapa PRO + Trend + SL/TP + AI Turbo")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        df = df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        top_n = min(5, len(df))
        if top_n > 0:
            cols = st.columns(top_n)
            for idx, (_, row) in enumerate(df.head(top_n).iterrows()):
                with cols[idx]:
                    if row["SetupScore"] >= 60:
                        color = "🟢"
                    elif row["SetupScore"] >= 40:
                        color = "🟡"
                    else:
                        color = "🔴"
                    st.markdown(f"### {color} {row['Symbol']}")
                    st.write(f"**Cena:** {row['LastPrice']:.2f}")
                    st.write(f"**Zmiana:** {row['Change']:.2f}%")
                    st.write(f"**Trend:** {row['Trend']} ({row['TrendHealth']})")
                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}")
                    st.write(f"**Zmienność:** {row['VolatilityScore']:.1f}")
                    if row["SL_Low"] and row["TP_High"]:
                        st.write(f"**SL:** {row['SL_Low']:.2f} – {row['SL_High']:.2f}")
                        st.write(f"**TP:** {row['TP_Low']:.2f} – {row['TP_High']:.2f}")

        st.markdown("---")

        col_ai1, col_ai2 = st.columns(2)
        with col_ai1:
            if st.button("⚡ AI Turbo — analiza TOP setupów"):
                with st.spinner("AI Turbo analizuje setupy..."):
                    st.session_state.ai_turbo = ai_verdict_for_top5(df.head(top_n))
        with col_ai2:
            if st.button("⚡ AI Turbo 2.0 (Scalper / Day / Swing / Position)"):
                with st.spinner("AI Turbo 2.0 analizuje setupy..."):
                    st.session_state.ai_turbo = ai_turbo_v2(df.head(top_n))

        if st.session_state.ai_turbo:
            st.subheader("Werdykt AI")
            st.markdown(st.session_state.ai_turbo)

        st.markdown("---")
        st.dataframe(style_heatmap(df), use_container_width=True)

    # ---------------- WYKRES PRO ----------------
    with tab_chart:
        st.subheader("📈 Wykres PRO")
        symbol_for_chart = st.selectbox(
            "Wybierz spółkę:",
            st.session_state.symbols
        )
        plot_pro_chart(symbol_for_chart)

    # ---------------- SKANER SYGNAŁÓW ----------------
    with tab_scanner:
        st.subheader("📡 BUY / SELL Radar")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        scan_df = pd.DataFrame(rows)

        if prop_mode == "Prop‑Trader Mode":
            scan_df = apply_prop_filters(scan_df)

        scan_df = scan_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        buy_df = scan_df[
            (scan_df["Signal"] == "BUY") &
            (scan_df["Trend"] == "UP") &
            (scan_df["SetupScore"] >= (65 if prop_mode == "Prop‑Trader Mode" else 55))
        ]

        sell_df = scan_df[
            (scan_df["Signal"] == "SELL") &
            (scan_df["Trend"] == "DOWN") &
            (scan_df["SetupScore"] >= (55 if prop_mode == "Prop‑Trader Mode" else 45))
        ]

        neutral_df = scan_df[
            ~scan_df.index.isin(buy_df.index) &
            ~scan_df.index.isin(sell_df.index)
        ]

        st.markdown("## 🟢 BUY Radar")
        if buy_df.empty:
            st.info("Brak sygnałów BUY.")
        else:
            st.dataframe(buy_df, use_container_width=True)

        st.markdown("## 🔴 SELL Radar")
        if sell_df.empty:
            st.info("Brak sygnałów SELL.")
        else:
            st.dataframe(sell_df, use_container_width=True)

        st.markdown("## 🟡 Neutral")
        st.dataframe(neutral_df, use_container_width=True)

    # ---------------- HEATMAPA SEKTOROWA ----------------
    with tab_sector:
        st.subheader("🏭 Heatmapa sektorowa")

        df_sector = df.copy()
        df_sector["Sector"] = df_sector["Symbol"].apply(get_sector)

        sector_view = (
            df_sector.groupby("Sector")["SetupScore"]
            .mean()
            .sort_values(ascending=False)
            .reset_index()
        )

        st.dataframe(sector_view, use_container_width=True)

    # ---------------- PRE‑MARKET RADAR ----------------
    with tab_premarket:
        st.subheader("🌅 Pre‑Market Radar")

        pre_rows = []
        for s in st.session_state.symbols:
            ch = get_premarket(s)
            if ch is not None:
                pre_rows.append({"Symbol": s, "PreMarketChange": ch})

        if not pre_rows:
            st.info("Brak danych pre‑market dla podanych spółek.")
        else:
            pre_df = pd.DataFrame(pre_rows).sort_values("PreMarketChange", ascending=False)
            st.dataframe(pre_df, use_container_width=True)

# ============================================================
# ==========================  RUN  ============================
# ============================================================

if __name__ == "__main__":
    main()


