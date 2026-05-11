
import os
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from openai import OpenAI

# ====================== KONFIGURACJA AI ======================

MODEL_TURBO = "gpt-4o"
MODEL_NEWS = "gpt-4o-mini"
MODEL_RISK = "gpt-4.1"
MODEL_PATTERN = "gpt-4o-mini"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====================== AUTO-SEKTORY ======================

AUTO_SECTOR_MAP = {
    "PKN.WA": "Energia", "PKO.WA": "Finanse", "PEO.WA": "Finanse",
    "CDR.WA": "Gaming", "11B.WA": "Gaming", "DNP.WA": "Technologia",
    "KGH.WA": "Surowce", "JSW.WA": "Surowce", "LPP.WA": "Konsumpcja cyclical",
    "NVDA": "AI / Semiconductors", "AMD": "AI / Semiconductors",
    "SMCI": "AI / Semiconductors", "AVGO": "AI / Semiconductors",
    "ASML": "AI / Semiconductors", "TSM": "AI / Semiconductors",
    "QCOM": "AI / Semiconductors",
    "HIVE": "Crypto miners", "MARA": "Crypto miners",
    "RIOT": "Crypto miners", "CLSK": "Crypto miners",
    "IREN": "Crypto miners", "WULF": "Crypto miners",
}

def get_auto_sector(symbol):
    if symbol in AUTO_SECTOR_MAP:
        return AUTO_SECTOR_MAP[symbol]
    if symbol.endswith(".WA"):
        return "GPW / Inne"
    return "Inne"

# ====================== PRESETY ======================

def preset_gpw_spekula():
    return ["HRT.WA","CFS.WA","PRT.WA","ATT.WA","STX.WA","PUR.WA","BCS.WA",
            "KCH.WA","GTN.WA","LBW.WA","PGV.WA","HPE.WA","DNS.WA","ZUK.WA",
            "VVD.WA","MLN.WA","MER.WA","APS.WA","NVG.WA"]

def preset_usa_biotech():
    return ["IOVA","PLRX","HUMA","TCRX","GOSS","MREO","ADTX"]

def preset_ai_semiconductors():
    return ["NVDA","AMD","SMCI","AVGO","ASML","TSM","QCOM"]

def preset_crypto_miners():
    return ["HIVE","MARA","RIOT","CLSK","IREN","WULF"]

# ====================== DANE RYNKOWE ======================

def get_price_data(symbol, period="5d", interval="1h"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

def get_bid_ask(symbol):
    try:
        info = yf.Ticker(symbol).info
        bid = info.get("bid")
        ask = info.get("ask")
        if not bid or not ask:
            return None, None, None
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid * 100
        return bid, ask, spread
    except:
        return None, None, None

def compute_entry_risk(volume, spread):
    if volume >= 2_000_000: liquidity = "WYSOKA"
    elif volume >= 500_000: liquidity = "ŚREDNIA"
    else: liquidity = "NISKA"

    if spread is None: spread_rating = "NIEZNANY"
    elif spread < 0.5: spread_rating = "DOBRY"
    elif spread < 2: spread_rating = "OK"
    else: spread_rating = "SŁABY"

    if liquidity == "WYSOKA" and spread and spread < 1:
        slippage = "NISKIE"
    elif liquidity == "ŚREDNIA" or (spread and spread <= 3):
        slippage = "ŚREDNIE"
    else:
        slippage = "WYSOKIE"

    return liquidity, spread_rating, slippage

def get_premarket(symbol):
    try:
        info = yf.Ticker(symbol).info
        prev = info.get("regularMarketPreviousClose")
        now = info.get("regularMarketPrice")
        if prev and now:
            return (now - prev) / prev * 100
        return None
    except:
        return None

# ====================== METRYKI ======================

def compute_metrics(symbol):
    df = get_price_data(symbol)
    if df.empty or len(df) < 3:
        return {
            "Symbol": symbol, "LastPrice": 0, "Change": 0, "Volume": 0,
            "ATR": 0, "Trend": "BRAK", "Signal": "NEUTRAL",
            "MomentumScore": 0, "VolatilityScore": 0, "TrendStrength": 0,
            "RiskScore": 50, "SetupScore": 0, "SL_Low": None, "SL_High": None,
            "TP_Low": None, "TP_High": None, "Bid": None, "Ask": None,
            "SpreadPct": None, "Liquidity": "NIEZNANA",
            "SpreadRating": "NIEZNANY", "Slippage": "NIEZNANE",
            "Sector": get_auto_sector(symbol)
        }

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    last = close.iloc[-1]
    prev = close.iloc[-2]
    change = (last - prev) / prev * 100 if prev else 0

    tr = pd.concat([(high - low),
                    (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]

    if last > ema20 > ema50: trend = "UP"
    elif last < ema20 < ema50: trend = "DOWN"
    else: trend = "SIDE"

    signal = "BUY" if trend == "UP" and change > 0 else \
             "SELL" if trend == "DOWN" and change < 0 else "NEUTRAL"

    vol_last = volume.iloc[-1]
    vol_prev = volume.iloc[-2]
    vol_change = (vol_last - vol_prev) / vol_prev * 100 if vol_prev else 0

    momentum = max(0, min(100, 50 + change * 0.7 + vol_change * 0.3))
    vol_score = max(0, min(100, (atr / last * 100) * 2))
    trend_strength = max(0, min(100, abs(ema20 - ema50) / last * 500))

    risk = vol_score
    setup = max(0, min(100, momentum * 0.3 + trend_strength * 0.3 - risk * 0.2 +
                       (30 if signal == "BUY" else 20 if signal == "SELL" else 0)))

    sl_low = last - atr * 1.5
    sl_high = last - atr * 1.0
    tp_low = last + atr * 2.0
    tp_high = last + atr * 3.0

    bid, ask, spread = get_bid_ask(symbol)
    liquidity, spread_rating, slippage = compute_entry_risk(vol_last, spread)

    return {
        "Symbol": symbol, "LastPrice": last, "Change": change, "Volume": vol_last,
        "ATR": atr, "Trend": trend, "Signal": signal, "MomentumScore": momentum,
        "VolatilityScore": vol_score, "TrendStrength": trend_strength,
        "RiskScore": risk, "SetupScore": setup,
        "SL_Low": sl_low, "SL_High": sl_high,
        "TP_Low": tp_low, "TP_High": tp_high,
        "Bid": bid, "Ask": ask, "SpreadPct": spread,
        "Liquidity": liquidity, "SpreadRating": spread_rating,
        "Slippage": slippage, "Sector": get_auto_sector(symbol)
    }

# ====================== HEATMAPA KOLORY ======================

def heat_color(val):
    if pd.isna(val): return ""
    if val >= 70: return "background-color:#166534;color:white;"
    if val >= 55: return "background-color:#15803d;color:white;"
    if val >= 45: return "background-color:#ca8a04;color:black;"
    return "background-color:#7f1d1d;color:white;"

# ====================== WYKRES ======================

def plot_pro_chart(symbol):
    df = get_price_data(symbol)
    if df.empty:
        st.warning(f"Brak danych dla {symbol}")
        return

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"]
    ))

    ema20 = df["Close"].ewm(span=20).mean()
    ema50 = df["Close"].ewm(span=50).mean()

    fig.add_trace(go.Scatter(x=df.index, y=ema20, mode="lines", name="EMA20"))
    fig.add_trace(go.Scatter(x=df.index, y=ema50, mode="lines", name="EMA50"))

    fig.update_layout(template="plotly_dark", height=600,
                      xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

# ====================== AI RISK v2 ======================

def risk_check_v2(df):
    out = []
    for _, r in df.iterrows():
        sym = r["Symbol"]
        if r["Volume"] == 0 or r["ATR"] == 0:
            out.append(f"### {sym}\n**Brak danych / pomiń**\n")
            continue
        if r["RiskScore"] >= 90 and r["VolatilityScore"] >= 90 and r["Liquidity"] == "NISKA":
            out.append(f"### {sym}\n**Ekstremalne ryzyko / unikać**\n")
            continue
        if r["Trend"] == "DOWN" and r["Signal"] == "SELL":
            out.append(f"### {sym}\n**Kandydat do shorta**\n")
            continue
        if r["Trend"] == "UP" and r["Signal"] == "BUY" and r["Liquidity"] != "NISKA":
            out.append(f"### {sym}\n**Kandydat do longa**\n")
            continue
        if r["Trend"] == "SIDE" or r["Signal"] == "NEUTRAL":
            out.append(f"### {sym}\n**Neutralne / brak przewagi**\n")
            continue
        out.append(f"### {sym}\n**Wysokie ryzyko / brak przewagi**\n")
    return "\n".join(out)

# ====================== CSS ======================

def inject_css():
    st.markdown("""
    <style>
    body, .stApp { background-color:#020617; color:#e5e5ff; }
    </style>
    """, unsafe_allow_html=True)

# ====================== MAIN ======================

def main():
    st.set_page_config(page_title="KOMBAJN 6.2", layout="wide")
    inject_css()
    st.title("🔥 KOMBAJN v6.2 — FINALNY, POPRAWIONY, DZIAŁAJĄCY")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []

    st.sidebar.header("Presety")

    preset = st.sidebar.selectbox("Wybierz preset:", [
        "Brak", "GPW spekuła", "USA biotech",
        "AI / Semiconductors", "Crypto miners"
    ])

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

    st.sidebar.header("Dodaj własne spółki")
    symbols_input = st.sidebar.text_input("Tickery (oddzielone przecinkami):")

    if st.sidebar.button("Dodaj"):
        for raw in symbols_input.split(","):
            sym = raw.strip().upper()
            if sym and sym not in st.session_state.symbols:
                st.session_state.symbols.append(sym)

    if st.sidebar.button("Wyczyść"):
        st.session_state.symbols = []

    if not st.session_state.symbols:
        st.warning("Dodaj spółki lub użyj presetów.")
        return

    tabs = st.tabs([
        "📊 Heatmapa", "📈 Wykres", "🌅 Pre‑Market",
        "🏭 Sektory", "🛡️ Risk Check"
    ])

    # HEATMAPA
    with tabs[0]:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows).sort_values("SetupScore", ascending=False)
        styled = df.style.applymap(heat_color, subset=["SetupScore"])
        st.markdown(styled.to_html(), unsafe_allow_html=True)

    # WYKRES
    with tabs[1]:
        symbol = st.selectbox("Wybierz spółkę:", st.session_state.symbols)
        plot_pro_chart(symbol)

    # PRE-MARKET
    with tabs[2]:
        pre = []
        for s in st.session_state.symbols:
            ch = get_premarket(s)
            if ch is not None:
                pre.append({"Symbol": s, "Change": ch})
        if not pre:
            st.info("Brak danych.")
        else:
            dfp = pd.DataFrame(pre).sort_values("Change", ascending=False)
            st.dataframe(dfp)

    # SEKTORY
    with tabs[3]:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        sec = df.groupby("Sector")["SetupScore"].mean().reset_index()
        st.dataframe(sec)

    # RISK CHECK
    with tabs[4]:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        if st.button("Risk Check"):
            st.markdown(risk_check_v2(df))

if __name__ == "__main__":
    main()
