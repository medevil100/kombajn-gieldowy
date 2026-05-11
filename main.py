import os
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

# --- PAGE CONFIG ---
st.set_page_config(page_title="Heatmap PRO", layout="wide")

# --- GLOBAL CSS (Bloomberg Dark Mode) ---
st.markdown("""
<style>
body, .stApp {
    background-color: #0d0d0d !important;
    color: #e6e6e6 !important;
    font-family: "Segoe UI", sans-serif;
}
[data-testid="stDataFrame"] {
    background-color: #0d0d0d !important;
    border: 1px solid #333 !important;
    border-radius: 6px !important;
    padding: 10px !important;
}
.dataframe tbody tr th, .dataframe tbody tr td {
    background-color: #111 !important;
    color: #e6e6e6 !important;
    font-size: 17px !important;
    padding: 10px 14px !important;
    border-color: #222 !important;
}
.dataframe thead th {
    background-color: #1a1a1a !important;
    color: #f2f2f2 !important;
    font-size: 18px !important;
    border-bottom: 2px solid #444 !important;
    padding: 12px !important;
}
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
</style>
""", unsafe_allow_html=True)

# --- OpenAI config ---
AI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================================
# ======================  FUNKCJE  ============================
# ============================================================

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

# --- METRYKI GŁÓWNE: compute_metrics ---
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
            "TrendFlags": [],
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
}
# ============================================================
# ========================  MAIN  =============================
# ============================================================

def main():
    st.title("🔥 HEATMAPA PRO — Prop‑Desk Kombajn: AI + Wykres + Skaner + Alerty + Patterny + News")

    # --- SESSION STATE ---
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

    # --- SIDEBAR ---
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

    # --- TABS ---
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

    # ============================================================
    # ======================  HEATMAP  ============================
    # ============================================================

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

        st.markdown("---")
        st.subheader("📊 Pełna Heatmapa")

        st.dataframe(
            style_heatmap(df),
            use_container_width=True
        )

    # ============================================================
    # ======================  WYKRES PRO  =========================
    # ============================================================

    with tab_chart:
        st.subheader("📈 Wykres PRO dla wybranej spółki")

        symbol_for_chart = st.selectbox(
            "Wybierz spółkę do wykresu:",
            st.session_state.symbols
        )

        plot_pro_chart(symbol_for_chart)

    # ============================================================
    # ======================  SKANER  =============================
    # ============================================================

    with tab_scanner:
        st.subheader("📡 BUY / SELL Radar — Skaner Sygnałów")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        scan_df = pd.DataFrame(rows)
        scan_df = scan_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        # --- BUY ---
        buy_df = scan_df[
            (scan_df["Signal"] == "BUY") &
            (scan_df["Trend"] == "UP") &
            (scan_df["SetupScore"] >= 60) &
            (scan_df["MomentumScore"] >= 55)
        ]

        # --- SELL ---
        sell_df = scan_df[
            (scan_df["Signal"] == "SELL") &
            (scan_df["Trend"] == "DOWN") &
            (scan_df["SetupScore"] >= 50)
        ]

        # --- NEUTRAL ---
        neutral_df = scan_df[
            ~scan_df.index.isin(buy_df.index) &
            ~scan_df.index.isin(sell_df.index)
        ]

        # --- BUY RADAR ---
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

        # --- SELL RADAR ---
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

        # --- NEUTRAL RADAR ---
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
    # ============================================================
    # ========================  ALERTY  ===========================
    # ============================================================

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

    # ============================================================
    # ========================  PATTERNY  =========================
    # ============================================================

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

    # ============================================================
    # ======================  AI DEEP DIVE  =======================
    # ============================================================

    with tab_deep:
        st.subheader("🧠 AI Deep Dive — TECH + NEWS + Entry Risk / SL‑TP + Trend")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        deep_df = pd.DataFrame(rows)
        deep_df = deep_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        symbol_for_deep = st.selectbox(
            "Wybierz spółkę do analizy AI:",
            deep_df["Symbol"].tolist()
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
                 if spread_pct is not None else "brak danych")
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
                with st.spinner("AI analizuje news‑ryzyko i potencjał wybicia..."):
                    comment_news = ai_news_deep_dive(
                        symbol_for_deep, metrics, bid, ask, spread_pct
                    )
                    st.session_state.ai_news_deep_cache[symbol_for_deep] = comment_news

        if symbol_for_deep in st.session_state.ai_deep_dive_cache:
            st.subheader(f"🧠 AI TECH — {symbol_for_deep}")
            st.markdown(st.session_state.ai_deep_dive_cache[symbol_for_deep])

        if symbol_for_deep in st.session_state.ai_news_deep_cache:
            st.subheader(f"📰 AI NEWS — {symbol_for_deep}")
            st.markdown(st.session_state.ai_news_deep_cache[symbol_for_deep])

    # ============================================================
    # =======================  MULTI-AI  ==========================
    # ============================================================

    with tab_multi:
        st.subheader("🤝 Multi‑AI Panel — 4 style tradingu na TOP setupach")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        multi_df = pd.DataFrame(rows)
        multi_df = multi_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        top_n = min(5, len(multi_df))
        top_df = multi_df.head(top_n)

        if st.button("🤝 Generuj Multi‑AI werdykt dla TOP setupów"):
            with st.spinner("AI generuje panel 4 stylów tradingu..."):
                st.session_state.ai_multi_comment = multi_ai_verdict(top_df)

        if st.session_state.ai_multi_comment:
            st.subheader("🤝 Multi‑AI Panel — komentarze")
            st.markdown(st.session_state.ai_multi_comment)

    # ============================================================
    # =======================  NEWS RADAR  ========================
    # ============================================================

    with tab_news:
        st.subheader("📰 News Radar — NewsScore + ryzyko newsowe / potencjał wybicia")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        news_df = pd.DataFrame(rows)
        news_df = news_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        if st.session_state.news_scores:
            news_df["NewsScore"] = news_df["Symbol"].map(
                st.session_state.news_scores
            ).fillna(0.0)

        col_n1, col_n2 = st.columns(2)

        with col_n1:
            if st.button("📰 Generuj / odśwież NewsScore (wszystkie spółki)"):
                with st.spinner("AI liczy NewsScore..."):
                    st.session_state.news_scores = ai_news_score_for_df(news_df)
                    news_df["NewsScore"] = news_df["Symbol"].map(
                        st.session_state.news_scores
                    ).fillna(0.0)

        with col_n2:
            if st.button("📡 Generuj News Radar (AI raport)"):
                with st.spinner("AI generuje News Radar..."):
                    if "NewsScore" not in news_df.columns and st.session_state.news_scores:
                        news_df["NewsScore"] = news_df["Symbol"].map(
                            st.session_state.news_scores
                        ).fillna(0.0)
                    st.session_state.ai_news_radar_comment = ai_news_radar(news_df)

        st.markdown("---")
        st.subheader("📊 Tabela z NewsScore")

        if st.session_state.news_scores:
            news_df["NewsScore"] = news_df["Symbol"].map(
                st.session_state.news_scores
            ).fillna(0.0)

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

# ============================================================
# =====================  RUN MAIN  ============================
# ============================================================

if __name__ == "__main__":
    main()
