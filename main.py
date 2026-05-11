import os
import pandas as pd
import yfinance as yf
from openai import OpenAI

# ============================================================
# ======================  KONFIGURACJA AI  ===================
# ============================================================

AI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================================
# ======================  DANE RYNKOWE  ======================
# ============================================================

def get_price_data(symbol: str, period: str = "5d", interval: str = "1h") -> pd.DataFrame:
    """
    Pobiera dane OHLCV z yfinance.
    """
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

def get_bid_ask(symbol: str):
    """
    Pobiera bid/ask i liczy spread w %.
    """
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
    except Exception:
        return None, None, None

def compute_entry_risk(volume: float, spread_pct: float | None):
    """
    Ocena wejścia: płynność, jakość spreadu, slippage.
    """
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

# ============================================================
# ======================  SL / TP / TREND  ===================
# ============================================================

def compute_sl_tp(last_price: float | None, atr: float | None, trend: str):
    """
    Wyznacza strefy SL/TP na bazie ATR i kierunku trendu.
    """
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
    """
    Złożona ocena trendu: TrendScore + opis + ryzyko odwrócenia.
    """
    try:
        mom = max(0.0, min(100.0, float(momentum_score)))
    except Exception:
        mom = 50.0
    try:
        vol = max(0.0, min(100.0, float(volatility_score)))
    except Exception:
        vol = 50.0
    try:
        ts = max(0.0, min(100.0, float(trend_strength)))
    except Exception:
        ts = 50.0
    try:
        ch = float(change_pct)
    except Exception:
        ch = 0.0

    vol_trend = ((volume_current - volume_prev) / volume_prev * 100.0) if volume_prev else 0.0
    ema_div = abs(ema20_last - ema50_last) / last_price * 100 if last_price else 0.0
    atr_pct = atr / last_price * 100 if last_price else 0.0

    comp_change = 50 + max(-5, min(5, ch)) * 10
    comp_vol_trend = 50 + max(-50, min(50, vol_trend))
    comp_volatility = 100 - vol
    comp_ema_div = min(100, (min(5, ema_div) / 5) * 100)
    comp_atr_stab = 100 - min(100, (min(5, atr_pct) / 5) * 100)

    trend_score = (
        ts * 0.25
        + mom * 0.25
        + comp_change * 0.15
        + comp_vol_trend * 0.10
        + comp_volatility * 0.10
        + comp_ema_div * 0.10
        + comp_atr_stab * 0.05
    )
    trend_score = max(0, min(100, trend_score))

    if trend_score >= 75:
        health = "SILNY TREND"
    elif trend_score >= 55:
        health = "ZDROWY TREND"
    elif trend_score >= 35:
        health = "SŁABY TREND"
    else:
        health = "RYZYKO ODWRÓCENIA"

    if trend_score >= 70:
        confidence = "WYSOKIE"
    elif trend_score >= 45:
        confidence = "ŚREDNIE"
    else:
        confidence = "NISKIE"

    if trend_score < 40 and vol > 60:
        reversal_risk = "WYSOKIE"
    elif trend_score < 55 and vol > 50:
        reversal_risk = "ŚREDNIE"
    else:
        reversal_risk = "NISKIE"

    return {
        "TrendScore": trend_score,
        "TrendHealth": health,
        "TrendConfidence": confidence,
        "TrendReversalRisk": reversal_risk,
        "TrendFlags": [],
        "TrendComment": "",
    }

# ============================================================
# ======================  METRYKI GŁÓWNE  ====================
# ============================================================

def compute_metrics(symbol: str) -> dict:
    """
    Główna funkcja licząca metryki dla instrumentu.
    """
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
            "Bid": None,
            "Ask": None,
            "SpreadPct": None,
            "Liquidity": "NIEZNANA",
            "SpreadRating": "NIEZNANY",
            "Slippage": "NIEZNANE",
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

    bid, ask, spread_pct = get_bid_ask(symbol)
    liquidity, spread_rating, slippage = compute_entry_risk(volume=vol_last, spread_pct=spread_pct)

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
        "Bid": bid,
        "Ask": ask,
        "SpreadPct": spread_pct,
        "Liquidity": liquidity,
        "SpreadRating": spread_rating,
        "Slippage": slippage,
    }

# ============================================================
# ======================  PATTERNY  ==========================
# ============================================================

def detect_patterns_for_symbol(symbol: str):
    """
    Proste patterny: wybicie 20‑dniowego szczytu / dołka.
    """
    df = get_price_data(symbol, "5d", "1h")
    if df.empty or len(df) < 20:
        return []

    patterns = []
    close = df["Close"]

    if close.iloc[-1] > close.rolling(20).max().iloc[-2]:
        patterns.append("📈 Wybicie 20‑okresowego szczytu")

    if close.iloc[-1] < close.rolling(20).min().iloc[-2]:
        patterns.append("📉 Wybicie 20‑okresowego dołka")

    return patterns

def detect_patterns_all(symbols: list[str]) -> dict:
    """
    Patterny dla wszystkich symboli.
    """
    out = {}
    for s in symbols:
        pats = detect_patterns_for_symbol(s)
        if pats:
            out[s] = pats
    return out

# ============================================================
# ======================  NEWS (POD INVESTIK)  ===============
# ============================================================

def get_news_for_symbol(symbol: str) -> list[dict]:
    """
    Na razie newsy z yfinance.Ticker(symbol).news.
    Później możesz tu podmienić źródło na Investik Pro.
    """
    try:
        t = yf.Ticker(symbol)
        news = getattr(t, "news", [])
        if not news:
            return []
        out = []
        for n in news[:5]:
            out.append(
                {
                    "title": n.get("title", ""),
                    "publisher": n.get("publisher", ""),
                    "link": n.get("link", ""),
                }
            )
        return out
    except Exception:
        return []

import streamlit as st
import plotly.graph_objects as go

# ============================================================
# ======================  CIEMNY NEON CSS  ===================
# ============================================================

st.markdown("""
<style>
body, .stApp {
    background-color: #020617 !important;
    color: #e5e5ff !important;
    font-family: "Segoe UI", system-ui, sans-serif;
}
[data-testid="stSidebar"] {
    background-color: #020617 !important;
    border-right: 1px solid #111827 !important;
}
h1, h2, h3, h4 {
    color: #f9fafb !important;
    text-shadow: 0 0 8px #4c1d95;
}
.stButton>button {
    background: linear-gradient(90deg, #111827, #020617) !important;
    color: #e5e5ff !important;
    border-radius: 4px !important;
    border: 1px solid #4c1d95 !important;
}
.stButton>button:hover {
    background: linear-gradient(90deg, #312e81, #111827) !important;
    border-color: #7c3aed !important;
}
</style>
""", unsafe_allow_html=True)

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
# ======================  UI — MAIN LAYOUT  ==================
# ============================================================

def render_ui():
    st.title("🔥 KOMBAJN v4.0 — Ultra Dark Neon + Trend + SL/TP + Bid/Ask + AI + News")

    # ---------------- SESSION STATE ----------------
    if "symbols" not in st.session_state:
        st.session_state.symbols = []
    if "sector_map" not in st.session_state:
        st.session_state.sector_map = {}
    if "ai_turbo" not in st.session_state:
        st.session_state.ai_turbo = ""

    # ---------------- SIDEBAR ----------------
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
        st.session_state.sector_map = {}
        st.session_state.ai_turbo = ""

    st.sidebar.markdown("---")
    st.sidebar.subheader("🏭 Przypisanie sektorów")

    for sym in st.session_state.symbols:
        current = st.session_state.sector_map.get(sym, "Inne")
        options = ["Technologia", "Finanse", "Energia", "Surowce", "Zdrowie", "Konsumpcja", "Inne"]
        idx = options.index(current) if current in options else len(options) - 1
        new_sector = st.sidebar.selectbox(
            f"Sektor dla {sym}:",
            options,
            index=idx,
            key=f"sector_{sym}"
        )
        st.session_state.sector_map[sym] = new_sector

    if not st.session_state.symbols:
        st.warning("Dodaj spółki w sidebarze, aby rozpocząć.")
        return

    # ---------------- TABS ----------------
    tab_heatmap, tab_chart, tab_scanner, tab_sector, tab_premarket = st.tabs([
        "📊 Heatmapa PRO",
        "📈 Wykres PRO",
        "📡 Skaner sygnałów",
        "🏭 Heatmapa sektorowa",
        "🌅 Pre‑Market Radar",
    ])

    # ============================================================
    # ======================  HEATMAPA PRO  ======================
    # ============================================================

    with tab_heatmap:
        st.subheader("📊 Heatmapa PRO + Trend + SL/TP + Bid/Ask")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        df = df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        top_n = min(5, len(df))
        if top_n > 0:
            cols = st.columns(top_n)
            for idx, (_, row) in enumerate(df.head(top_n).iterrows()):
                with cols[idx]:
                    if row["SetupScore"] >= 70:
                        icon = "🟢"
                    elif row["SetupScore"] >= 50:
                        icon = "🟡"
                    else:
                        icon = "🔴"

                    st.markdown(f"### {icon} {row['Symbol']}")
                    st.write(f"**Cena:** {row['LastPrice']:.2f}  |  **Zmiana:** {row['Change']:.2f}%")
                    st.write(f"**Trend:** {row['Trend']} ({row['TrendHealth']}, pewność: {row['TrendConfidence']})")

                    if row["SL_Low"] and row["TP_High"]:
                        st.markdown(
                            f"**SL:** <span style='color:#f97316;'>{row['SL_Low']:.2f} – {row['SL_High']:.2f}</span>",
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f"**TP:** <span style='color:#22c55e;'>{row['TP_Low']:.2f} – {row['TP_High']:.2f}</span>",
                            unsafe_allow_html=True
                        )

                    if row["Bid"] and row["Ask"]:
                        st.write(
                            f"**Bid/Ask:** {row['Bid']:.2f} / {row['Ask']:.2f}  "
                            f"| Spread: {row['SpreadPct']:.2f}% ({row['SpreadRating']}, {row['Liquidity']}, slippage: {row['Slippage']})"
                        )

                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}  |  **Zmienność:** {row['VolatilityScore']:.1f}")
                    st.write(f"**SetupScore:** {row['SetupScore']:.1f}  |  **TrendScore:** {row['TrendScore']:.1f}")

        st.markdown("---")
        st.dataframe(style_heatmap(df), use_container_width=True)

    # ============================================================
    # ======================  WYKRES PRO  ========================
    # ============================================================

    with tab_chart:
        st.subheader("📈 Wykres PRO")
        symbol_for_chart = st.selectbox(
            "Wybierz spółkę:",
            st.session_state.symbols
        )
        plot_pro_chart(symbol_for_chart)

    # ============================================================
    # ======================  SKANER SYGNAŁÓW  ===================
    # ============================================================

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
        st.dataframe(buy_df if not buy_df.empty else pd.DataFrame({"Info": ["Brak sygnałów BUY"]}), use_container_width=True)

        st.markdown("## 🔴 SELL Radar")
        st.dataframe(sell_df if not sell_df.empty else pd.DataFrame({"Info": ["Brak sygnałów SELL"]}), use_container_width=True)

        st.markdown("## 🟡 Neutral")
        st.dataframe(neutral_df, use_container_width=True)

    # ============================================================
    # ======================  SEKTORÓWKA  ========================
    # ============================================================

    with tab_sector:
        st.subheader("🏭 Heatmapa sektorowa")

        df_sector = df.copy()
        df_sector["Sector"] = df_sector["Symbol"].apply(lambda s: st.session_state.sector_map.get(s, "Inne"))

        sector_view = (
            df_sector.groupby("Sector")["SetupScore"]
            .mean()
            .sort_values(ascending=False)
            .reset_index()
        )

        st.dataframe(sector_view, use_container_width=True)

    # ============================================================
    # ======================  PRE‑MARKET  ========================
    # ============================================================

    with tab_premarket:
        st.subheader("🌅 Pre‑Market Radar")

        pre_rows = []
        for s in st.session_state.symbols:
            ch = get_premarket(s)
            if ch is not None:
                pre_rows.append({"Symbol": s, "PreMarketChange": ch})

        if not pre_rows:
            st.info("Brak danych pre‑market.")
        else:
            pre_df = pd.DataFrame(pre_rows).sort_values("PreMarketChange", ascending=False)
            st.dataframe(pre_df, use_container_width=True)
# ============================================================
# ======================  AI FUNKCJE  =========================
# ============================================================

def ai_turbo_v2(df: pd.DataFrame) -> str:
    """
    AI Turbo 2.0 — styl „Prop‑Desk Techniczny”.
    4 style: Scalper / Day‑Trader / Swing / Position.
    Oparte wyłącznie na danych technicznych z df.
    """
    records = df[[
        "Symbol", "LastPrice", "Change", "MomentumScore",
        "VolatilityScore", "TrendStrength", "TrendScore",
        "SetupScore", "RiskScore"
    ]].to_dict(orient="records")

    prompt = f"""
Jesteś traderem z prop‑desku. Mówisz technicznie, bez lania wody, bez fundamentów.
Masz dane dla instrumentów (każdy rekord to jedna spółka):

{records}

Dla KAŻDEGO symbolu przygotuj 4‑stylowy werdykt:
- SCALPER
- DAY-TRADER
- SWING
- POSITION

Zasady:
- Styl: „Prop‑Desk Techniczny” — konkretnie, agresywnie, ale profesjonalnie.
- Zero fundamentów, zero ogólników, zero „stabilny wzrost przychodów”.
- Opierasz się TYLKO na polach: Change, MomentumScore, VolatilityScore, TrendStrength, TrendScore, SetupScore, RiskScore.
- Maksymalnie 1 krótka linia na każdy styl.
- Używaj języka technicznego: momentum, wybicie, trend, zmienność, ryzyko, przewaga kupujących/sprzedających.
- Nie pisz podsumowania na końcu.

Format odpowiedzi (dokładnie taki):

SYMBOL
SCALPER: ...
DAY-TRADER: ...
SWING: ...
POSITION: ...

Odpowiadaj po polsku.
"""

    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


def ai_news_summary(symbol: str, raw_news: str) -> str:
    """
    AI News — analiza newsów pod trading (sentyment + wpływ na handel).
    """
    prompt = f"""
Jesteś traderem intraday z prop‑desku. Analizujesz newsy dla {symbol}.

Newsy (tytuły, skróty):

{raw_news}

Zadanie:
- Określ, czy newsy są pro‑wzrostowe, pro‑spadkowe czy neutralne.
- Oceń, czy zwiększają ryzyko (gap, zmienność, niepewność).
- Napisz krótko, jak to wpływa na:
  - scalping,
  - day‑trading,
  - swing.

Zasady:
- Zero fundamentów typu „długoterminowy rozwój spółki”.
- Skup się na zmienności, kierunku reakcji, ryzyku.
- Maksymalnie 4–6 krótkich zdań.
- Odpowiadaj po polsku, technicznie, bez lania wody.
"""

    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


def ai_risk_check(df: pd.DataFrame) -> str:
    """
    AI Risk Check — ocena ryzyka wejścia na podstawie:
    SL/TP, spreadu, płynności, trendu, zmienności, setupu.
    """
    records = df[[
        "Symbol", "LastPrice", "Change", "MomentumScore",
        "VolatilityScore", "TrendStrength", "TrendScore",
        "SetupScore", "RiskScore", "SL_Low", "SL_High",
        "TP_Low", "TP_High", "SpreadPct", "Liquidity",
        "SpreadRating", "Slippage"
    ]].to_dict(orient="records")

    prompt = f"""
Jesteś risk managerem na prop‑desku. Masz dane o setupach i ryzyku:

{records}

Dla KAŻDEGO symbolu:
- oceń, czy wejście jest:
  - AGRESYWNE OK
  - TYLKO DLA DOŚWIADCZONYCH
  - LEPIEJ ODPUSCIĆ
- weź pod uwagę:
  - SetupScore, TrendScore, MomentumScore,
  - VolatilityScore, RiskScore,
  - SL/TP (odległość, sensowność),
  - SpreadPct, Liquidity, SpreadRating, Slippage.

Format odpowiedzi:

SYMBOL
RYZYKO: ...
KOMENTARZ: ...

Zasady:
- Styl „Prop‑Desk Techniczny”.
- Krótko, konkretnie, bez lania wody.
- Odpowiadaj po polsku.
"""

    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


def ai_pattern_insight(symbols: list[str]) -> str:
    """
    AI Pattern Insight — łączy patterny + momentum + trend.
    """
    pattern_map = detect_patterns_all(symbols)
    rows = [compute_metrics(s) for s in symbols]
    df = pd.DataFrame(rows)

    data = {
        "patterns": pattern_map,
        "metrics": df[[
            "Symbol", "LastPrice", "Change", "MomentumScore",
            "VolatilityScore", "TrendStrength", "TrendScore",
            "SetupScore", "RiskScore", "Trend", "Signal"
        ]].to_dict(orient="records"),
    }

    prompt = f"""
Jesteś traderem technicznym na prop‑desku.
Masz patterny i metryki dla instrumentów:

{data}

Zadanie:
- Dla KAŻDEGO symbolu, który ma pattern:
  - powiedz, czy pattern jest wart zagrania (TAK / NIE / TYLKO NA MAŁĄ POZYCJĘ),
  - określ, czy lepiej pod to grać:
    - scalping,
    - day‑trading,
    - swing,
  - wskaż główne ryzyko (fałszywe wybicie, brak wolumenu, wysoka zmienność itd.).

Format:

SYMBOL
PATTERN: ...
WERDYKT: ...
RYZYKO: ...

Zasady:
- Styl „Prop‑Desk Techniczny”.
- Zero lania wody, tylko technika.
- Odpowiadaj po polsku.
"""

    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

# ============================================================
# ======================  AI PANEL (4 MODUŁY)  ===============
# ============================================================

def render_ai_panel():
    """
    Zakładka AI PANEL z 4 sub‑zakładkami:
    - AI Turbo 2.0
    - AI News
    - AI Risk Check
    - AI Pattern Insight
    """
    if "symbols" not in st.session_state or not st.session_state.symbols:
        st.warning("Najpierw dodaj spółki w sidebarze, żeby użyć AI Panelu.")
        return

    st.subheader("🤖 AI PANEL — Prop‑Desk Techniczny")

    tab_turbo, tab_news, tab_risk, tab_pattern = st.tabs([
        "⚡ AI Turbo 2.0",
        "📰 AI News",
        "🛡️ AI Risk Check",
        "📐 AI Pattern Insight",
    ])

    # ---------------- AI TURBO 2.0 ----------------
    with tab_turbo:
        st.markdown("### ⚡ AI Turbo 2.0 — Scalper / Day / Swing / Position")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        top_n = st.slider("Ile najlepszych setupów analizować?", 1, min(10, len(df)), min(5, len(df)))
        target_df = df.head(top_n)

        st.dataframe(target_df, use_container_width=True)

        if st.button("Uruchom AI Turbo 2.0"):
            with st.spinner("AI Turbo 2.0 analizuje setupy..."):
                txt = ai_turbo_v2(target_df)
            st.markdown("#### Werdykt AI")
            st.markdown(txt)

    # ---------------- AI NEWS ----------------
    with tab_news:
        st.markdown("### 📰 AI News — sentyment i wpływ na trading")

        symbol_news = st.selectbox(
            "Wybierz spółkę do analizy newsów:",
            st.session_state.symbols,
            key="ai_news_symbol"
        )

        if st.button("Pobierz newsy i zrób analizę AI"):
            with st.spinner("Pobieram newsy..."):
                news_list = get_news_for_symbol(symbol_news)

            if not news_list:
                st.info("Brak newsów (tu możesz później podpiąć Investik Pro).")
            else:
                st.markdown("#### Surowe newsy")
                for n in news_list:
                    st.markdown(f"- **{n['title']}** ({n['publisher']})")

                raw_text = "\n".join([n["title"] for n in news_list])

                with st.spinner("AI analizuje newsy..."):
                    summary = ai_news_summary(symbol_news, raw_text)

                st.markdown("#### Werdykt AI (newsowy)")
                st.markdown(summary)

    # ---------------- AI RISK CHECK ----------------
    with tab_risk:
        st.markdown("### 🛡️ AI Risk Check — ocena ryzyka wejścia")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False).reset_index(drop=True)

        st.dataframe(df, use_container_width=True)

        if st.button("Przeanalizuj ryzyko wejścia (AI)"):
            with st.spinner("AI ocenia ryzyko..."):
                txt = ai_risk_check(df)
            st.markdown("#### Werdykt AI (ryzyko)")
            st.markdown(txt)

    # ---------------- AI PATTERN INSIGHT ----------------
    with tab_pattern:
        st.markdown("### 📐 AI Pattern Insight — patterny + momentum + trend")

        st.markdown("Sprawdzam patterny (wybicia) i łączę je z metrykami technicznymi.")

        if st.button("Analiza patternów (AI)"):
            with st.spinner("AI analizuje patterny..."):
                txt = ai_pattern_insight(st.session_state.symbols)
            st.markdown("#### Werdykt AI (patterny)")
            st.markdown(txt)

# ============================================================
# ======================  FINALNE MAIN  ======================
# ============================================================

def main():
    st.set_page_config(page_title="KOMBAJN v4.0", layout="wide")
    st.title("🔥 KOMBAJN v4.0 — Ultra Dark Neon + Trend + SL/TP + Bid/Ask + AI + News")

    # Inicjalizacja state
    if "symbols" not in st.session_state:
        st.session_state.symbols = []
    if "sector_map" not in st.session_state:
        st.session_state.sector_map = {}

    # SIDEBAR
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
        st.session_state.sector_map = {}

    st.sidebar.markdown("---")
    st.sidebar.subheader("🏭 Przypisanie sektorów")

    for sym in st.session_state.symbols:
        current = st.session_state.sector_map.get(sym, "Inne")
        options = ["Technologia", "Finanse", "Energia", "Surowce", "Zdrowie", "Konsumpcja", "Inne"]
        idx = options.index(current) if current in options else len(options) - 1
        new_sector = st.sidebar.selectbox(
            f"Sektor dla {sym}:",
            options,
            index=idx,
            key=f"sector_{sym}"
        )
        st.session_state.sector_map[sym] = new_sector

    if not st.session_state.symbols:
        st.warning("Dodaj spółki w sidebarze, aby rozpocząć.")
        return

    # GŁÓWNE ZAKŁADKI (w tym AI PANEL)
    tab_heatmap, tab_chart, tab_scanner, tab_sector, tab_premarket, tab_ai = st.tabs([
        "📊 Heatmapa PRO",
        "📈 Wykres PRO",
        "📡 Skaner sygnałów",
        "🏭 Heatmapa sektorowa",
        "🌅 Pre‑Market Radar",
        "🤖 AI PANEL",
    ])

    # -------- HEATMAPA PRO --------
    with tab_heatmap:
        st.subheader("📊 Heatmapa PRO + Trend + SL/TP + Bid/Ask")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        df = df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        top_n = min(5, len(df))
        if top_n > 0:
            cols = st.columns(top_n)
            for idx, (_, row) in enumerate(df.head(top_n).iterrows()):
                with cols[idx]:
                    if row["SetupScore"] >= 70:
                        icon = "🟢"
                    elif row["SetupScore"] >= 50:
                        icon = "🟡"
                    else:
                        icon = "🔴"

                    st.markdown(f"### {icon} {row['Symbol']}")
                    st.write(f"**Cena:** {row['LastPrice']:.2f}  |  **Zmiana:** {row['Change']:.2f}%")
                    st.write(f"**Trend:** {row['Trend']} ({row['TrendHealth']}, pewność: {row['TrendConfidence']})")

                    if row["SL_Low"] and row["TP_High"]:
                        st.markdown(
                            f"**SL:** <span style='color:#f97316;'>{row['SL_Low']:.2f} – {row['SL_High']:.2f}</span>",
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f"**TP:** <span style='color:#22c55e;'>{row['TP_Low']:.2f} – {row['TP_High']:.2f}</span>",
                            unsafe_allow_html=True
                        )

                    if row["Bid"] and row["Ask"]:
                        st.write(
                            f"**Bid/Ask:** {row['Bid']:.2f} / {row['Ask']:.2f}  "
                            f"| Spread: {row['SpreadPct']:.2f}% ({row['SpreadRating']}, {row['Liquidity']}, slippage: {row['Slippage']})"
                        )

                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}  |  **Zmienność:** {row['VolatilityScore']:.1f}")
                    st.write(f"**SetupScore:** {row['SetupScore']:.1f}  |  **TrendScore:** {row['TrendScore']:.1f}")

        st.markdown("---")
        st.dataframe(style_heatmap(df), use_container_width=True)

    # -------- WYKRES PRO --------
    with tab_chart:
        st.subheader("📈 Wykres PRO")
        symbol_for_chart = st.selectbox(
            "Wybierz spółkę:",
            st.session_state.symbols
        )
        plot_pro_chart(symbol_for_chart)

    # -------- SKANER --------
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
        st.dataframe(buy_df if not buy_df.empty else pd.DataFrame({"Info": ["Brak sygnałów BUY"]}), use_container_width=True)

        st.markdown("## 🔴 SELL Radar")
        st.dataframe(sell_df if not sell_df.empty else pd.DataFrame({"Info": ["Brak sygnałów SELL"]}), use_container_width=True)

        st.markdown("## 🟡 Neutral")
        st.dataframe(neutral_df, use_container_width=True)

    # -------- SEKTORÓWKA --------
    with tab_sector:
        st.subheader("🏭 Heatmapa sektorowa")

        df_sector = df.copy()
        df_sector["Sector"] = df_sector["Symbol"].apply(lambda s: st.session_state.sector_map.get(s, "Inne"))

        sector_view = (
            df_sector.groupby("Sector")["SetupScore"]
            .mean()
            .sort_values(ascending=False)
            .reset_index()
        )

        st.dataframe(sector_view, use_container_width=True)

    # -------- PRE‑MARKET --------
    with tab_premarket:
        st.subheader("🌅 Pre‑Market Radar")

        pre_rows = []
        for s in st.session_state.symbols:
            ch = get_premarket(s)
            if ch is not None:
                pre_rows.append({"Symbol": s, "PreMarketChange": ch})

        if not pre_rows:
            st.info("Brak danych pre‑market.")
        else:
            pre_df = pd.DataFrame(pre_rows).sort_values("PreMarketChange", ascending=False)
            st.dataframe(pre_df, use_container_width=True)

    # -------- AI PANEL --------
    with tab_ai:
        render_ai_panel()


if __name__ == "__main__":
    main()
