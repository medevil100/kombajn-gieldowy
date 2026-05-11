
import os
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from openai import OpenAI

# ====================== KONFIGURACJA AI ======================

MODEL_TURBO = "gpt-4o"          # AI Turbo 3.0
MODEL_NEWS = "gpt-4o-mini"      # AI News
MODEL_RISK = "gpt-4.1"          # AI Risk Check
MODEL_PATTERN = "gpt-4o-mini"   # AI Pattern Insight

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====================== AUTO-SEKTORY ======================

AUTO_SECTOR_MAP = {
    # --- GPW (przykłady) ---
    "PKN.WA": "Energia",
    "PKO.WA": "Finanse",
    "PEO.WA": "Finanse",
    "CDR.WA": "Gaming",
    "11B.WA": "Gaming",
    "DNP.WA": "Technologia",
    "KGH.WA": "Surowce",
    "JSW.WA": "Surowce",
    "LPP.WA": "Konsumpcja cyclical",

    # --- USA tech / AI / semi ---
    "NVDA": "AI / Semiconductors",
    "AMD": "AI / Semiconductors",
    "SMCI": "AI / Semiconductors",
    "AVGO": "AI / Semiconductors",
    "ASML": "AI / Semiconductors",
    "TSM": "AI / Semiconductors",
    "QCOM": "AI / Semiconductors",

    # --- Crypto miners ---
    "HIVE": "Crypto miners",
    "MARA": "Crypto miners",
    "RIOT": "Crypto miners",
    "CLSK": "Crypto miners",
    "IREN": "Crypto miners",
    "WULF": "Crypto miners",
}

def get_auto_sector(symbol: str) -> str:
    if symbol in AUTO_SECTOR_MAP:
        return AUTO_SECTOR_MAP[symbol]
    if symbol.endswith(".WA"):
        return "GPW / Inne"
    if symbol in ["SPY", "QQQ", "DIA"]:
        return "ETF Akcyjne"
    if symbol in ["GLD", "SLV"]:
        return "ETF Surowcowe"
    if symbol in ["BTC-USD", "ETH-USD"]:
        return "Krypto"
    return "Inne"

# ====================== PRESETY (STATYCZNE, STABILNE) ======================

def preset_gpw_spekula():
    return [
        "HRT.WA", "CFS.WA", "PRT.WA", "ATT.WA", "STX.WA",
        "PUR.WA", "BCS.WA", "KCH.WA", "GTN.WA", "LBW.WA",
        "PGV.WA", "HPE.WA", "DNS.WA", "ZUK.WA", "VVD.WA",
        "MLN.WA", "MER.WA", "APS.WA", "NVG.WA"
    ]

def preset_usa_biotech():
    return ["IOVA", "PLRX", "HUMA", "TCRX", "GOSS", "MREO", "ADTX"]

def preset_ai_semiconductors():
    return ["NVDA", "AMD", "SMCI", "AVGO", "ASML", "TSM", "QCOM"]

def preset_crypto_miners():
    return ["HIVE", "MARA", "RIOT", "CLSK", "IREN", "WULF"]

# ====================== DANE RYNKOWE ======================

def get_price_data(symbol: str, period: str = "5d", interval: str = "1h") -> pd.DataFrame:
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
        if not bid or not ask:
            return None, None, None
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid * 100 if mid else None
        return float(bid), float(ask), float(spread_pct)
    except Exception:
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

    if liquidity == "WYSOKA" and spread_pct and spread_pct < 1:
        slippage = "NISKIE"
    elif liquidity == "ŚREDNIA" or (spread_pct and 1 <= spread_pct <= 3):
        slippage = "ŚREDNIE"
    else:
        slippage = "WYSOKIE"

    return liquidity, spread_rating, slippage

def get_premarket(symbol: str):
    """
    Pseudo-pre-market: różnica między regularMarketPrice a regularMarketPreviousClose.
    Działa też tam, gdzie nie ma typowego pre-market (GPW).
    """
    try:
        info = yf.Ticker(symbol).info
        last = info.get("regularMarketPreviousClose", None)
        now = info.get("regularMarketPrice", None)
        if now and last:
            return (now - last) / last * 100
        return None
    except Exception:
        return None

# ====================== SL / TP ======================

def compute_sl_tp(last, atr, trend):
    if not last or not atr:
        return None, None
    sl = (last - atr * 1.5, last - atr * 1.0)
    tp = (last + atr * 2.0, last + atr * 3.0)
    return sl, tp

# ====================== METRYKI ======================

def compute_metrics(symbol):
    df = get_price_data(symbol)
    if df.empty or len(df) < 3:
        return {
            "Symbol": symbol,
            "LastPrice": 0,
            "Change": 0,
            "Volume": 0,
            "ATR": 0,
            "Trend": "BRAK",
            "Signal": "NEUTRAL",
            "MomentumScore": 0,
            "VolatilityScore": 0,
            "TrendStrength": 0,
            "RiskScore": 50,
            "SetupScore": 0,
            "TrendScore": 0,
            "TrendHealth": "NIEZNANY",
            "TrendConfidence": "NIEZNANE",
            "TrendReversalRisk": "NIEZNANE",
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
            "Sector": get_auto_sector(symbol),
        }

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = (last - prev) / prev * 100 if prev else 0

    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]

    if last > ema20 > ema50:
        trend = "UP"
    elif last < ema20 < ema50:
        trend = "DOWN"
    else:
        trend = "SIDE"

    signal = "BUY" if trend == "UP" and change > 0 else \
             "SELL" if trend == "DOWN" and change < 0 else "NEUTRAL"

    vol_last = float(volume.iloc[-1])
    vol_prev = float(volume.iloc[-2])
    vol_change = (vol_last - vol_prev) / vol_prev * 100 if vol_prev else 0

    momentum = max(0, min(100, 50 + change * 0.7 + vol_change * 0.3))
    vol_score = max(0, min(100, (atr / last * 100) * 2)) if last else 0
    trend_strength = max(0, min(100, abs(ema20 - ema50) / last * 500)) if last else 0

    risk = vol_score
    setup = max(
        0,
        min(
            100,
            (
                momentum * 0.3
                + trend_strength * 0.3
                - risk * 0.2
                + (30 if signal == "BUY" else 20 if signal == "SELL" else 0)
            ),
        ),
    )

    sl, tp = compute_sl_tp(last, atr, trend)

    bid, ask, spread = get_bid_ask(symbol)
    liquidity, spread_rating, slippage = compute_entry_risk(vol_last, spread)

    return {
        "Symbol": symbol,
        "LastPrice": last,
        "Change": change,
        "Volume": vol_last,
        "ATR": atr,
        "Trend": trend,
        "Signal": signal,
        "MomentumScore": momentum,
        "VolatilityScore": vol_score,
        "TrendStrength": trend_strength,
        "RiskScore": risk,
        "SetupScore": setup,
        "TrendScore": trend_strength,
        "TrendHealth": "OK",
        "TrendConfidence": "ŚREDNIE",
        "TrendReversalRisk": "NISKIE",
        "SL_Low": sl[0] if sl else None,
        "SL_High": sl[1] if sl else None,
        "TP_Low": tp[0] if tp else None,
        "TP_High": tp[1] if tp else None,
        "Bid": bid,
        "Ask": ask,
        "SpreadPct": spread,
        "Liquidity": liquidity,
        "SpreadRating": spread_rating,
        "Slippage": slippage,
        "Sector": get_auto_sector(symbol),
    }

# ====================== PATTERNY ======================

def detect_patterns_for_symbol(symbol: str):
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

def detect_patterns_all(symbols):
    out = {}
    for s in symbols:
        pats = detect_patterns_for_symbol(s)
        if pats:
            out[s] = pats
    return out

# ====================== NEWS ======================

def get_news_for_symbol(symbol: str) -> list[dict]:
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

# ====================== WYKRES ======================

def plot_pro_chart(symbol):
    df = get_price_data(symbol)
    if df.empty:
        st.warning(f"Brak danych dla {symbol}")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Świece",
        )
    )

    ema20 = df["Close"].ewm(span=20).mean()
    ema50 = df["Close"].ewm(span=50).mean()

    fig.add_trace(go.Scatter(x=df.index, y=ema20, mode="lines", name="EMA20"))
    fig.add_trace(go.Scatter(x=df.index, y=ema50, mode="lines", name="EMA50"))

    fig.update_layout(
        template="plotly_dark",
        height=600,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

# ====================== AI FUNKCJE ======================

def ai_turbo_v3(df: pd.DataFrame) -> str:
    records = df.to_dict(orient="records")
    prompt = f"""
Jesteś traderem z prop-desku. Analizujesz TYLKO dane, które naprawdę istnieją w rekordach poniżej.
Zero wymyślania, zero dopowiadania.

Dane:
{records}

Dla KAŻDEGO symbolu zrób techniczną analizę:

SYMBOL
1. Trend i momentum (Trend, TrendScore, MomentumScore, Change).
2. Zmienność i ryzyko (VolatilityScore, ATR, RiskScore).
3. Spread, płynność, slippage (SpreadPct, Liquidity, SpreadRating, Slippage).
4. Setup (SetupScore, Signal, SL/TP jeśli są).
5. Werdykt:
   - AGRESYWNE OK
   - TYLKO DLA DOŚWIADCZONYCH
   - LEPIEJ ODPUSCIĆ

Odpowiadasz po polsku, krótko, technicznie, bez lania wody.
"""
    resp = client.chat.completions.create(
        model=MODEL_TURBO,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content

def ai_news_summary(symbol: str, raw_news: str) -> str:
    prompt = f"""
Jesteś traderem intraday z prop-desku. Analizujesz newsy dla {symbol}.

Newsy:
{raw_news}

Zadanie:
- określ, czy newsy są pro-wzrostowe, pro-spadkowe czy neutralne,
- oceń wpływ na zmienność i ryzyko (gap, ruchy po otwarciu),
- napisz krótko, jak to wpływa na scalping, day-trading i swing.

Po polsku, krótko, technicznie.
"""
    resp = client.chat.completions.create(
        model=MODEL_NEWS,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content

def ai_pattern_insight(symbols: list[str]) -> str:
    pattern_map = detect_patterns_all(symbols)
    rows = [compute_metrics(s) for s in symbols]
    df = pd.DataFrame(rows)
    data = {
        "patterns": pattern_map,
        "metrics": df.to_dict(orient="records"),
    }
    prompt = f"""
Jesteś traderem technicznym na prop-desku.
Masz patterny i metryki:

{data}

Dla KAŻDEGO symbolu z patternem:
- PATTERN: opisz krótko,
- WERDYKT: TAK / NIE / TYLKO MAŁA POZYCJA,
- RYZYKO: główne ryzyko (fałszywe wybicie, brak wolumenu, wysoka zmienność itd.).

Po polsku, krótko, technicznie.
"""
    resp = client.chat.completions.create(
        model=MODEL_PATTERN,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content

# ====================== RISK CHECK v2 ======================

def risk_check_v2(df: pd.DataFrame) -> str:
    output = []

    for _, row in df.iterrows():
        sym = row["Symbol"]
        trend = row["Trend"]
        signal = row["Signal"]
        risk = row["RiskScore"]
        vol = row["VolatilityScore"]
        liq = row["Liquidity"]
        slip = row["Slippage"]
        sl_low = row["SL_Low"]
        sl_high = row["SL_High"]
        tp_low = row["TP_Low"]
        tp_high = row["TP_High"]

        if row["Volume"] == 0 or row["ATR"] == 0 or row["LastPrice"] == 0:
            output.append(
                f"""### {sym}
**Kategoria:** Brak danych / pomiń  
**Powód:** brak wolumenu lub brak zmienności → brak możliwości oceny.  
"""
            )
            continue

        if risk >= 90 and vol >= 90 and liq == "NISKA":
            output.append(
                f"""### {sym}
**Kategoria:** Ekstremalne ryzyko / unikać  
Trend: {trend}  
Ryzyko: {risk:.1f}, Zmienność: {vol:.1f}  
Płynność: {liq}, Slippage: {slip}  
**Komentarz:** ekstremalna zmienność + niska płynność = fatalne wykonanie, lepiej odpuścić.  
"""
            )
            continue

        if trend == "DOWN" and signal == "SELL":
            sl_txt = (
                f"{sl_low:.2f} – {sl_high:.2f}"
                if sl_low is not None and sl_high is not None
                else "brak danych"
            )
            tp_txt = (
                f"{tp_low:.2f} – {tp_high:.2f}"
                if tp_low is not None and tp_high is not None
                else "brak danych"
            )
            output.append(
                f"""### {sym}
**Kategoria:** Kandydat do shorta  
Trend: {trend}  
Sygnał: {signal}  
SL: {sl_txt}  
TP: {tp_txt}  
Ryzyko: {risk:.1f}, Płynność: {liq}, Slippage: {slip}  
**Komentarz:** stabilny trend spadkowy, ale uważać na wykonanie i wielkość pozycji.  
"""
            )
            continue

        if trend == "UP" and signal == "BUY" and liq != "NISKA":
            sl_txt = (
                f"{sl_low:.2f} – {sl_high:.2f}"
                if sl_low is not None and sl_high is not None
                else "brak danych"
            )
            tp_txt = (
                f"{tp_low:.2f} – {tp_high:.2f}"
                if tp_low is not None and tp_high is not None
                else "brak danych"
            )
            output.append(
                f"""### {sym}
**Kategoria:** Kandydat do longa  
Trend: {trend}  
Sygnał: {signal}  
SL: {sl_txt}  
TP: {tp_txt}  
Ryzyko: {risk:.1f}, Płynność: {liq}, Slippage: {slip}  
**Komentarz:** trend wzrostowy, sygnał zgodny, płynność akceptowalna, ale nadal kontroluj ryzyko.  
"""
            )
            continue

        if trend == "SIDE" or signal == "NEUTRAL":
            output.append(
                f"""### {sym}
**Kategoria:** Neutralne / brak przewagi  
Trend: {trend}, Sygnał: {signal}  
Ryzyko: {risk:.1f}, Płynność: {liq}  
**Komentarz:** brak wyraźnej przewagi kierunkowej, lepiej poczekać na klarowniejszy setup.  
"""
            )
            continue

        output.append(
            f"""### {sym}
**Kategoria:** Wysokie ryzyko / brak przewagi  
Trend: {trend}, Sygnał: {signal}  
Ryzyko: {risk:.1f}, Płynność: {liq}, Slippage: {slip}  
**Komentarz:** układ nie daje czytelnej przewagi, traktować jako spekulację wysokiego ryzyka.  
"""
        )

    return "\n".join(output)

# ====================== CSS ======================

def inject_css():
    st.markdown(
        """
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
""",
        unsafe_allow_html=True,
    )

# ====================== MAIN ======================

def main():
    st.set_page_config(page_title="KOMBAJN v6.1 FULL PRO", layout="wide")
    inject_css()
    st.title("🔥 KOMBAJN v6.1 — Trend + SL/TP + Bid/Ask + AI + Auto‑Sektory")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []

    st.sidebar.header("⚙️ Ustawienia")

    preset = st.sidebar.selectbox(
        "Preset listy spółek:",
        [
            "Brak",
            "GPW spekuła",
            "USA biotech",
            "AI / Semiconductors",
            "Crypto miners",
        ],
        index=0,
    )

    if st.sidebar.button("Załaduj preset"):
        if preset == "GPW spekuła":
            for s in preset_gpw_spekula():
                if s not in st.session_state.symbols:
                    st.session_state.symbols.append(s)
        elif preset == "USA biotech":
            for s in preset_usa_biotech():
                if s not in st.session_state.symbols:
                    st.session_state.symbols.append(s)
        elif preset == "AI / Semiconductors":
            for s in preset_ai_semiconductors():
                if s not in st.session_state.symbols:
                    st.session_state.symbols.append(s)
        elif preset == "Crypto miners":
            for s in preset_crypto_miners():
                if s not in st.session_state.symbols:
                    st.session_state.symbols.append(s)

    symbols_input = st.sidebar.text_input("Dodaj tickery (oddzielone przecinkami):")

    if st.sidebar.button("Dodaj"):
        for raw in symbols_input.split(","):
            sym = raw.strip().upper()
            if sym and sym not in st.session_state.symbols:
                st.session_state.symbols.append(sym)

    if st.sidebar.button("Wyczyść"):
        st.session_state.symbols = []

    if not st.session_state.symbols:
        st.warning("Dodaj spółki w sidebarze lub użyj presetów, aby rozpocząć.")
        return

    tabs = st.tabs(
        [
            "📊 Heatmapa PRO",
            "📈 Wykres PRO",
            "📡 Skaner sygnałów",
            "🌅 Pre‑Market Radar",
            "🏭 Sektory (auto)",
            "⚡ AI Turbo 3.0",
            "📰 AI News",
            "🛡️ AI Risk v2",
            "📐 AI Pattern Insight",
        ]
    )

    # --- HEATMAPA PRO ---
    with tabs[0]:
        st.subheader("📊 Heatmapa PRO")
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False)
        # kolorowanie SetupScore
        def color_setup(val):
            if pd.isna(val):
                return ""
            if val >= 70:
                return "background-color: #166534; color: #f9fafb;"
            if val >= 55:
                return "background-color: #15803d; color: #f9fafb;"
            if val >= 45:
                return "background-color: #ca8a04; color: #111827;"
            return "background-color: #7f1d1d; color: #f9fafb;"

        styled = df.style.applymap(color_setup, subset=["SetupScore"])
        st.dataframe(styled, use_container_width=True)

    # --- WYKRES PRO ---
    with tabs[1]:
        st.subheader("📈 Wykres PRO")
        symbol = st.selectbox("Wybierz spółkę:", st.session_state.symbols)
        plot_pro_chart(symbol)

    # --- SKANER SYGNAŁÓW ---
    with tabs[2]:
        st.subheader("📡 BUY / SELL Radar")
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        scan_df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False)

        buy_df = scan_df[
            (scan_df["Signal"] == "BUY")
            & (scan_df["Trend"] == "UP")
            & (scan_df["SetupScore"] >= 55)
        ]
        sell_df = scan_df[
            (scan_df["Signal"] == "SELL")
            & (scan_df["Trend"] == "DOWN")
            & (scan_df["SetupScore"] >= 45)
        ]
        neutral_df = scan_df[
            ~scan_df.index.isin(buy_df.index) & ~scan_df.index.isin(sell_df.index)
        ]

        st.markdown("### 🟢 BUY Radar")
        st.dataframe(
            buy_df if not buy_df.empty else pd.DataFrame({"Info": ["Brak sygnałów BUY"]}),
            use_container_width=True,
        )

        st.markdown("### 🔴 SELL Radar")
        st.dataframe(
            sell_df if not sell_df.empty else pd.DataFrame({"Info": ["Brak sygnałów SELL"]}),
            use_container_width=True,
        )

        st.markdown("### 🟡 Neutral")
        st.dataframe(neutral_df, use_container_width=True)

    # --- PRE-MARKET RADAR ---
    with tabs[3]:
        st.subheader("🌅 Pre‑Market / Change Radar")
        pre_rows = []
        for s in st.session_state.symbols:
            ch = get_premarket(s)
            if ch is not None:
                pre_rows.append({"Symbol": s, "ChangeNowVsPrevClose": ch})
        if not pre_rows:
            st.info("Brak danych (brak różnicy między ceną bieżącą a poprzednim zamknięciem).")
        else:
            pre_df = (
                pd.DataFrame(pre_rows)
                .sort_values("ChangeNowVsPrevClose", ascending=False)
                .reset_index(drop=True)
            )
            def color_change(val):
                if val >= 3:
                    return "background-color: #166534; color: #f9fafb;"
                if val >= 1:
                    return "background-color: #15803d; color: #f9fafb;"
                if val <= -3:
                    return "background-color: #7f1d1d; color: #f9fafb;"
                if val <= -1:
                    return "background-color: #b91c1c; color: #f9fafb;"
                return ""
            styled_pre = pre_df.style.applymap(color_change, subset=["ChangeNowVsPrevClose"])
            st.dataframe(styled_pre, use_container_width=True)

    # --- SEKTORY (AUTO) ---
    with tabs[4]:
        st.subheader("🏭 Heatmapa sektorowa (auto‑sektory)")
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df_sector = pd.DataFrame(rows)
        sector_view = (
            df_sector.groupby("Sector")["SetupScore"]
            .mean()
            .sort_values(ascending=False)
            .reset_index()
        )
        styled_sector = sector_view.style.applymap(
            lambda v: "background-color: #166534; color: #f9fafb;" if v >= 55 else ""
            , subset=["SetupScore"]
        )
        st.dataframe(styled_sector, use_container_width=True)

    # --- AI TURBO 3.0 ---
    with tabs[5]:
        st.subheader("⚡ AI Turbo 3.0 — analiza setupów")
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df_ai = (
            pd.DataFrame(rows)
            .sort_values("SetupScore", ascending=False)
            .reset_index(drop=True)
        )
        top_n = st.slider(
            "Ile najlepszych setupów analizować?",
            1,
            min(10, len(df_ai)),
            min(5, len(df_ai)),
        )
        target_df = df_ai.head(top_n)
        st.dataframe(target_df, use_container_width=True)
        if st.button("Uruchom AI Turbo 3.0"):
            with st.spinner("AI Turbo 3.0 analizuje setupy..."):
                txt = ai_turbo_v3(target_df)
            st.markdown("#### Werdykt AI")
            st.markdown(txt)

    # --- AI NEWS ---
    with tabs[6]:
        st.subheader("📰 AI News — sentyment i wpływ na trading")
        symbol_news = st.selectbox(
            "Wybierz spółkę do analizy newsów:",
            st.session_state.symbols,
            key="ai_news_symbol_main",
        )
        if st.button("Pobierz newsy i zrób analizę AI"):
            with st.spinner("Pobieram newsy..."):
                news_list = get_news_for_symbol(symbol_news)
            if not news_list:
                st.info("Brak newsów.")
            else:
                st.markdown("#### Surowe newsy")
                for n in news_list:
                    st.markdown(f"- **{n['title']}** ({n['publisher']})")
                raw_text = "\n".join([n["title"] for n in news_list])
                with st.spinner("AI analizuje newsy..."):
                    summary = ai_news_summary(symbol_news, raw_text)
                st.markdown("#### Werdykt AI (newsowy)")
                st.markdown(summary)

    # --- AI RISK v2 ---
    with tabs[7]:
        st.subheader("🛡️ AI Risk Check v2 — jedna kategoria na spółkę")
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df_risk = (
            pd.DataFrame(rows)
            .sort_values("RiskScore", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(df_risk, use_container_width=True)
        if st.button("Risk Check v2"):
            with st.spinner("Analizuję ryzyko..."):
                txt = risk_check_v2(df_risk)
            st.markdown("#### Werdykt ryzyka")
            st.markdown(txt)

    # --- AI PATTERN INSIGHT ---
    with tabs[8]:
        st.subheader("📐 AI Pattern Insight — patterny + momentum + trend")
        if st.button("Analiza patternów (AI)"):
            with st.spinner("AI analizuje patterny..."):
                txt = ai_pattern_insight(st.session_state.symbols)
            st.markdown("#### Werdykt AI (patterny)")
            st.markdown(txt)


if __name__ == "__main__":
    main()


Jeśli coś jeszcze strzeli błąd — wklej sam traceback, bez reszty, i wtedy poprawimy już punktowo, a nie od nowa.
