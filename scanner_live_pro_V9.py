import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
from openai import OpenAI
from tavily import TavilyClient

# ============================
# CONFIG
# ============================

st.set_page_config(page_title="💠 CYBER DESK PRO", page_icon="💠", layout="wide")

NEON_CSS = """
<style>
body { background-color: #020617; color: #E5E7EB; }
section.main { background: radial-gradient(circle at top, #0f172a 0, #020617 55%); }
.block-container { padding-top: 0.8rem; }
h1, h2, h3, h4 { color: #38bdf8 !important; }
.stMetric label, .stMetric span { color: #e5e7eb !important; }
div[data-testid="stMetricValue"] { color: #22c55e !important; }
.stButton>button {
    background: linear-gradient(90deg,#22c55e,#0ea5e9);
    border: none;
    color: #0b1120;
    font-weight: 700;
}
.stButton>button:hover {
    background: linear-gradient(90deg,#0ea5e9,#22c55e);
}
</style>
"""
st.markdown(NEON_CSS, unsafe_allow_html=True)

st.title("💠 CYBER DESK PRO — Czat + Trading + Skaner")
st.caption("GPT‑4o + Tavily + yfinance · 1 plik · stabilny w chmurze")

# ============================
# API KEYS
# ============================

try:
    OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
    TAVILY_KEY = st.secrets["TAVILY_API_KEY"]
    openai_client = OpenAI(api_key=OPENAI_KEY)
    tavily_client = TavilyClient(api_key=TAVILY_KEY)
except Exception:
    st.error("❌ Brak kluczy w .streamlit/secrets.toml (OPENAI_API_KEY, TAVILY_API_KEY).")
    st.stop()

# ============================
# SESSION STATE
# ============================

if "watchlist_raw" not in st.session_state:
    st.session_state.watchlist_raw = ""

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "scanner_input" not in st.session_state:
    st.session_state.scanner_input = ""

# dane z kombajnu dla AI
if "engine_data" not in st.session_state:
    st.session_state.engine_data = None

# ============================
# CORE FUNKCJE
# ============================

def detect_market(ticker: str):
    if ticker.endswith(".WA"):
        return "GPW", "PLN"
    return "USA/Global", "USD"


def get_price_data(ticker: str, interval: str = "5m", period: str = "5d"):
    try:
        df = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            prepost=False,
            actions=False
        )
        if df is None or df.empty:
            return None, None
        last = df.iloc[-1]
        return df, {
            "price": float(last["Close"]),
            "open": float(last["Open"]),
            "high": float(last["High"]),
            "low": float(last["Low"]),
            "volume": int(last["Volume"])
        }
    except Exception:
        return None, None


def compute_indicators(df: pd.DataFrame):
    if len(df) < 50:
        return {
            "rsi": None,
            "ma20": None,
            "ma50": None,
            "macd": None,
            "signal": None,
            "hv": None,
            "bb_upper": None,
            "bb_lower": None,
            "trend": "NOT ENOUGH DATA"
        }

    close = df["Close"]

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    log_ret = np.log(close / close.shift(1))
    hv = log_ret.rolling(20).std() * np.sqrt(252)

    std20 = close.rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20

    trend = "FLAT"
    if pd.notna(ma20.iloc[-1]) and pd.notna(ma50.iloc[-1]):
        if ma20.iloc[-1] > ma50.iloc[-1]:
            trend = "UP"
        elif ma20.iloc[-1] < ma50.iloc[-1]:
            trend = "DOWN"

    def safe(val):
        return float(val) if pd.notna(val) else None

    return {
        "rsi": safe(rsi.iloc[-1]),
        "ma20": safe(ma20.iloc[-1]),
        "ma50": safe(ma50.iloc[-1]),
        "macd": safe(macd.iloc[-1]),
        "signal": safe(signal.iloc[-1]),
        "hv": safe(hv.iloc[-1]),
        "bb_upper": safe(bb_upper.iloc[-1]),
        "bb_lower": safe(bb_lower.iloc[-1]),
        "trend": trend
    }


def plot_candles(df: pd.DataFrame, ticker: str):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Cena"
    ))
    fig.update_layout(
        title=f"{ticker} — wykres",
        height=420,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
        font=dict(color="#E5E7EB"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================
# AI FUNKCJE — LIVE SYGNAŁ + SCENARIUSZE
# ============================

def ai_live_signal(ticker, price, indicators):
    prompt = f"""
Jesteś daytraderem.

Ticker: {ticker}
Cena: {price}
RSI: {indicators.get("rsi")}
MA20: {indicators.get("ma20")}
MA50: {indicators.get("ma50")}
MACD: {indicators.get("macd")}
Signal: {indicators.get("signal")}
HV: {indicators.get("hv")}
BB_UPPER: {indicators.get("bb_upper")}
BB_LOWER: {indicators.get("bb_lower")}
TREND: {indicators.get("trend")}

Zwróć:
- BUY / SELL / FLAT
- 1–3 zdania uzasadnienia po polsku.
"""
    r = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.25
    )
    return r.choices[0].message.content.strip()


def ai_scenarios(ticker, price, indicators):
    prompt = f"""
Przygotuj 3 scenariusze dla {ticker} na 7 dni.

Cena: {price}
Techniczne: {indicators}

### BULL
...

### BASE
...

### BEAR
...
"""
    r = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.35
    )
    return r.choices[0].message.content.strip()


def tavily_news_for_ticker(ticker: str):
    try:
        if ticker.endswith(".WA"):
            q = (
                f"najnowsze ważne newsy o spółce {ticker} z GPW, "
                f"tylko informacje istotne dla kursu akcji"
            )
        else:
            q = (
                f"latest important news about stock {ticker}, "
                f"only price-moving events"
            )

        res = tavily_client.search(q, max_results=5)
        items = res.get("results", []) if isinstance(res, dict) else []
        if not items:
            return "Brak świeżych newsów."
        lines = []
        for it in items:
            title = it.get("title", "")
            snippet = it.get("content", "")[:220]
            lines.append(f"- **{title}** — {snippet}...")
        return "\n".join(lines)
    except Exception:
        return "Błąd Tavily."

# ============================
# AI CZAT — WIDZI DANE KOMBAJNU
# ============================

def ai_chat_answer(user_msg: str, ticker: str | None):
    engine = st.session_state.get("engine_data")
    tavily_part = ""
    tech_part = ""

    # 1) AI używa danych z kombajnu, jeśli są
    if engine and (ticker is None or ticker.upper() == engine["ticker"].upper()):
        price_data = engine["price_data"]
        ind = engine["indicators"]
        eff_ticker = engine["ticker"]

        tech_part = f"""
Dane techniczne (z kombajnu):
- Cena: {price_data['price']:.4f}
- RSI: {ind.get("rsi")}
- MA20: {ind.get("ma20")}
- MA50: {ind.get("ma50")}
- MACD: {ind.get("macd")}
- Signal: {ind.get("signal")}
- HV: {ind.get("hv")}
- BB Upper: {ind.get("bb_upper")}
- BB Lower: {ind.get("bb_lower")}
- Trend: {ind.get("trend")}
"""

    # 2) fallback — jeśli kombajn nie był użyty
    elif ticker:
        eff_ticker = ticker.upper()
        df, price_data = get_price_data(eff_ticker, interval="1d", period="1mo")
        if df is not None and price_data is not None and not df.empty:
            ind = compute_indicators(df)
            tech_part = f"""
Dane techniczne (fallback):
- Cena: {price_data['price']:.4f}
- RSI: {ind.get("rsi")}
- MA20: {ind.get("ma20")}
- MA50: {ind.get("ma50")}
- MACD: {ind.get("macd")}
- Signal: {ind.get("signal")}
- HV: {ind.get("hv")}
- BB Upper: {ind.get("bb_upper")}
- BB Lower: {ind.get("bb_lower")}
- Trend: {ind.get("trend")}
"""
        else:
            tech_part = "Dane techniczne są ograniczone — brak pełnych danych."
    else:
        eff_ticker = None
        tech_part = "Brak danych technicznych — nie podano tickera."

    # news
    if eff_ticker:
        tavily_part = tavily_news_for_ticker(eff_ticker)
    else:
        tavily_part = "Brak tickera — newsy ogólne."

    prompt = f"""
Jesteś analitykiem finansowym.

Pytanie użytkownika:
{user_msg}

Ticker: {eff_ticker}

News:
{tavily_part}

{tech_part}

Zasady:
- odpowiadasz po polsku, konkretnie,
- jeśli dane są pełne → użyj ich,
- jeśli dane są częściowe → powiedz to, ale analizuj to, co jest,
- nie używaj sformułowania "brak Trading Engine",
- nie wymyślaj liczb spoza danych.
"""

    r = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return r.choices[0].message.content.strip()

# ============================
# SIDEBAR
# ============================

with st.sidebar:
    st.markdown("### 💠 Tryb pracy")
    mode = st.radio(
        "Wybierz moduł:",
        ["📈 Kombajn tradingowy", "🧪 Skaner spółek", "🤖 Czat AI"],
        index=0
    )

    st.markdown("---")
    st.markdown("### 📜 Watchlista")
    wl_raw = st.text_area(
        "Tickery (oddzielone przecinkami):",
        value=st.session_state.watchlist_raw,
        height=100
    )
    st.session_state.watchlist_raw = wl_raw
    wl_list = [t.strip().upper() for t in wl_raw.split(",") if t.strip()]

    active_from_list = None
    if wl_list:
        active_from_list = st.selectbox("Aktywny ticker z listy:", wl_list)

    st.markdown("---")
    st.markdown("### ⏱ Odświeżanie (manualne)")
    st.caption("Kliknij przycisk, aby pobrać nowe dane.")
# ============================
# MODUŁ 1 — KOMBAJN TRADINGOWY
# ============================

if mode == "📈 Kombajn tradingowy":
    col_top1, col_top2, col_top3 = st.columns([2, 1, 1])

    with col_top1:
        default_ticker = active_from_list if active_from_list else ""
        main_ticker = st.text_input("Ticker (USA / .WA / inne):", value=default_ticker).upper()

    with col_top2:
        interval = st.selectbox("Interwał:", ["1m", "5m", "15m", "1h", "1d"], index=1)

    with col_top3:
        period = st.selectbox("Okres:", ["1d", "5d", "1mo", "3mo"], index=1)

    run_btn = st.button("🚀 Odśwież dane")

    if main_ticker and run_btn:
        market, currency = detect_market(main_ticker)
        st.markdown(f"**Rynek:** `{market}` | **Waluta:** `{currency}`")

        df, price_data = get_price_data(main_ticker, interval=interval, period=period)

        if df is None or price_data is None or df.empty:
            st.error("❌ Brak danych z Yahoo Finance.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Cena", f"{price_data['price']:.4f} {currency}")
            with c2:
                st.metric("High", f"{price_data['high']:.4f}")
            with c3:
                st.metric("Low", f"{price_data['low']:.4f}")
            with c4:
                st.metric("Volume", f"{price_data['volume']:,}")

            indicators = compute_indicators(df)

            # ZAPIS DANYCH DO AI — KLUCZOWE
            st.session_state.engine_data = {
                "ticker": main_ticker,
                "interval": interval,
                "period": period,
                "price_data": price_data,
                "indicators": indicators,
            }

            plot_candles(df, main_ticker)

            col_mid1, col_mid2 = st.columns([2, 1])

            with col_mid1:
                st.subheader("🤖 LIVE‑AI sygnał (GPT‑4o)")
                live_sig = ai_live_signal(main_ticker, price_data["price"], indicators)
                st.markdown(live_sig)

            with col_mid2:
                st.subheader("📊 Techniczne FULL")
                tech_df = pd.DataFrame.from_dict(indicators, orient="index", columns=["Value"])
                st.table(tech_df)

            st.subheader("📰 Tavily — newsy dla bieżącego tickera")
            news_text = tavily_news_for_ticker(main_ticker)
            st.markdown(news_text)

            st.markdown("---")
            st.subheader("🧠 Scenariusze AI (Bull / Base / Bear)")
            scen = ai_scenarios(main_ticker, price_data["price"], indicators)
            st.markdown(scen)

# ============================
# MODUŁ 2 — SKANER SPÓŁEK
# ============================

if mode == "🧪 Skaner spółek":
    st.subheader("🧪 Skaner 50 → TOP 10 (kolorowa tabela)")

    scan_raw = st.text_area(
        "Wklej listę tickerów (oddzielone przecinkami):",
        value=st.session_state.scanner_input,
        height=120
    )
    st.session_state.scanner_input = scan_raw
    scan_list = [t.strip().upper() for t in scan_raw.split(",") if t.strip()]

    def scan_tickers(tickers_list):
        if not tickers_list:
            return pd.DataFrame()

        rows = []

        try:
            data = yf.download(
                tickers=" ".join(tickers_list),
                period="3mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True
            )
            for t in tickers_list:
                try:
                    df_s = data[t].dropna()
                    if df_s.empty:
                        continue
                    last_close = float(df_s["Close"].iloc[-1])
                    avg_vol = df_s["Volume"].tail(20).mean()
                    dollar_vol = avg_vol * last_close if pd.notna(avg_vol) else 0.0

                    ind_s = compute_indicators(df_s)

                    score = 0
                    if ind_s.get("rsi") is not None:
                        score += max(0, 70 - abs(50 - ind_s["rsi"]))
                    score += min(dollar_vol / 1_000_000, 50)

                    rows.append({
                        "Ticker": t,
                        "Price": last_close,
                        "RSI": ind_s.get("rsi"),
                        "HV": ind_s.get("hv"),
                        "DollarVol20": dollar_vol,
                        "Score": score
                    })
                except Exception:
                    continue
        except Exception:
            for raw in tickers_list:
                t = raw.strip().upper()
                if not t:
                    continue
                df_s, price_s = get_price_data(t, interval="1d", period="3mo")
                if df_s is None or price_s is None or df_s.empty:
                    continue
                ind_s = compute_indicators(df_s)
                avg_vol = df_s["Volume"].tail(20).mean()
                dollar_vol = avg_vol * price_s["price"] if pd.notna(avg_vol) else 0.0

                score = 0
                if ind_s.get("rsi") is not None:
                    score += max(0, 70 - abs(50 - ind_s["rsi"]))
                score += min(dollar_vol / 1_000_000, 50)

                rows.append({
                    "Ticker": t,
                    "Price": price_s["price"],
                    "RSI": ind_s.get("rsi"),
                    "HV": ind_s.get("hv"),
                    "DollarVol20": dollar_vol,
                    "Score": score
                })

        if not rows:
            return pd.DataFrame()

        df_scan = pd.DataFrame(rows)
        df_scan = df_scan.sort_values("Score", ascending=False)
        return df_scan.head(10)

    def color_rows(row):
        score = row["Score"]
        if score >= 80:
            color = "background-color: rgba(22,163,74,0.35);"
        elif score >= 50:
            color = "background-color: rgba(234,179,8,0.35);"
        else:
            color = "background-color: rgba(220,38,38,0.35);"
        return [color] * len(row)

    if st.button("🚀 Skanuj i pokaż TOP 10"):
        if not scan_list:
            st.warning("Podaj przynajmniej 1 ticker.")
        else:
            scan_df = scan_tickers(scan_list)
            if scan_df.empty:
                st.warning("Brak wyników skanu.")
            else:
                st.subheader("📋 TOP 10 (kolorowa tabela)")
                styled = scan_df.style.apply(color_rows, axis=1).format({
                    "Price": "{:.4f}",
                    "RSI": "{:.2f}",
                    "HV": "{:.4f}",
                    "DollarVol20": "{:.0f}",
                    "Score": "{:.2f}",
                })
                st.dataframe(styled, use_container_width=True)
# ============================
# MODUŁ 3 — CZAT AI
# ============================

if mode == "🤖 Czat AI":
    st.subheader("🤖 Czat AI — Analityk finansowy (GPT‑4o + Tavily + dane techniczne z kombajnu)")

    col_c1, col_c2 = st.columns([2, 1])

    with col_c2:
        chat_ticker = st.text_input(
            "Opcjonalny ticker (np. NVG.WA, HUMA, MREO):",
            value=""
        ).upper()

    with col_c1:
        user_msg = st.text_area("Twoja wiadomość:", height=120)

    if st.button("Wyślij do AI"):
        if not user_msg.strip():
            st.warning("Napisz coś najpierw.")
        else:
            answer = ai_chat_answer(
                user_msg.strip(),
                chat_ticker if chat_ticker else None
            )
            st.session_state.chat_history.append(("Ty", user_msg.strip()))
            st.session_state.chat_history.append(("AI", answer))

    if st.session_state.chat_history:
        st.markdown("---")
        st.markdown("### Historia rozmowy")

        for speaker, msg in st.session_state.chat_history:
            if speaker == "Ty":
                st.markdown(f"**Ty:** {msg}")
            else:
                st.markdown(f"**AI:** {msg}")
                st.markdown("---")
