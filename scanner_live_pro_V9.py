import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI
from tavily import TavilyClient

# ============================
# CONFIG
# ============================

st.set_page_config(page_title="KI‑ULTRA X FINAL v2.1", page_icon="⚡", layout="wide")

NEON_CSS = """
<style>
body { background-color: #020617; color: #E5E7EB; }
section.main { background: radial-gradient(circle at top, #0f172a 0, #020617 55%); }
.block-container { padding-top: 1.0rem; }
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

st.title("⚡ KI‑ULTRA X FINAL v2.1 — Dark‑Neon LIVE Engine")
st.caption("Tick‑by‑Tick | AI‑Scenariusze | LIVE‑AI | Alerty Hybrydowe | Portfel PRO | Autoscan")

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

if "portfolio" not in st.session_state:
    st.session_state.portfolio = []

if "multi_tickers_raw" not in st.session_state:
    st.session_state.multi_tickers_raw = ""

if "active_ticker" not in st.session_state:
    st.session_state.active_ticker = ""

if "scan_input" not in st.session_state:
    st.session_state.scan_input = ""

if "last_price" not in st.session_state:
    st.session_state.last_price = None

if "last_ai_signal" not in st.session_state:
    st.session_state.last_ai_signal = ""

# ============================
# CORE FUNKCJE
# ============================

def detect_market(ticker: str):
    if ticker.endswith(".WA"):
        return "GPW", "PLN"
    return "USA/Global", "USD"


def get_price_data(ticker: str, interval: str = "1m", period: str = "1d"):
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
    close = df["Close"]

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
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

    return {
        "rsi": float(rsi.iloc[-1]),
        "ma20": float(ma20.iloc[-1]) if not np.isnan(ma20.iloc[-1]) else None,
        "ma50": float(ma50.iloc[-1]) if not np.isnan(ma50.iloc[-1]) else None,
        "macd": float(macd.iloc[-1]),
        "signal": float(signal.iloc[-1]),
        "hv": float(hv.iloc[-1]) if not np.isnan(hv.iloc[-1]) else None,
    }


def plot_live_chart(df: pd.DataFrame, ticker: str):
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
        title=f"LIVE {ticker}",
        height=450,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
        font=dict(color="#E5E7EB"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================
# AI FUNKCJE
# ============================

def ai_live_signal(openai_client, ticker, price, indicators):
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

Zwróć:
- jedno słowo: BUY / SELL / FLAT
- 1–2 zdania uzasadnienia po polsku
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return r.choices[0].message.content


def ai_scenarios(openai_client, ticker, price, indicators):
    prompt = f"""
Przygotuj 3 scenariusze ceny dla {ticker} na 7 dni.

Cena: {price}
Techniczne: {indicators}

Zwróć:
### BULL
3 zdania + target

### BASE
3 zdania + target

### BEAR
3 zdania + target
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.35
    )
    return r.choices[0].message.content


def check_hybrid_alerts(ticker, price, indicators, ai_signal):
    alerts = []

    if indicators.get("ma20") and price > indicators["ma20"]:
        alerts.append("Cena powyżej MA20 — momentum rośnie")

    if indicators.get("ma50") and price < indicators["ma50"]:
        alerts.append("Cena poniżej MA50 — presja spadkowa")

    if indicators.get("rsi") and indicators["rsi"] > 70:
        alerts.append("RSI > 70 — wykupienie")

    if indicators.get("rsi") and indicators["rsi"] < 30:
        alerts.append("RSI < 30 — wyprzedanie")

    if indicators.get("macd") and indicators.get("signal"):
        if indicators["macd"] > indicators["signal"]:
            alerts.append("MACD > SIGNAL — sygnał wzrostowy")
        else:
            alerts.append("MACD < SIGNAL — sygnał spadkowy")

    if ai_signal.startswith("BUY"):
        alerts.append("AI: BUY — wykryto momentum wzrostowe")
    if ai_signal.startswith("SELL"):
        alerts.append("AI: SELL — presja spadkowa")
    if ai_signal.startswith("FLAT"):
        alerts.append("AI: FLAT — brak kierunku")

    return alerts

# ============================
# SIDEBAR
# ============================

with st.sidebar:
    st.markdown("### 📜 Lista tickerów (nieznikające)")
    multi_raw = st.text_area(
        "Tickery (oddzielone przecinkami):",
        value=st.session_state.multi_tickers_raw,
        height=120,
        key="multi_tickers_area"
    )
    st.session_state.multi_tickers_raw = multi_raw
    multi_list = [t.strip().upper() for t in multi_raw.split(",") if t.strip()]

    if multi_list:
        active_from_list = st.selectbox(
            "Aktywny ticker:",
            options=multi_list,
            index=0,
            key="multi_ticker_select"
        )
        st.session_state.active_ticker = active_from_list

    refresh_sec = st.slider("⏱ Odświeżanie (sekundy)", 1, 30, 5, key="refresh_sec")
    live_mode = st.toggle("LIVE‑MODE (auto‑refresh)", value=True, key="live_mode")

# ============================
# GŁÓWNY PANEL
# ============================

top1, top2, top3 = st.columns([2,1,1])

with top1:
    default_ticker = st.session_state.active_ticker if st.session_state.active_ticker else ""
    ticker = st.text_input("Ticker (USA / .WA / inne):", value=default_ticker, key="main_ticker").upper()

with top2:
    interval = st.selectbox("Interwał:", ["1m", "5m", "15m", "1h", "1d"], index=0, key="interval_select")

with top3:
    period = st.selectbox("Okres:", ["1d", "5d", "1mo", "3mo"], index=0, key="period_select")

go_button = st.button("🚀 Start / Refresh", type="primary", key="start_button")

# AUTO‑REFRESH
if live_mode:
    st.query_params.update({"_": int(time.time())})
    time.sleep(refresh_sec)
    st.rerun()

# ANALIZA
if ticker:
    market, currency = detect_market(ticker)
    st.markdown(f"**Rynek:** `{market}` | **Waluta:** `{currency}`")

    df, price_data = get_price_data(ticker, interval=interval, period=period)

    if df is None or price_data is None or df.empty:
        st.error("❌ Brak danych z Yahoo Finance.")
    else:
        st.session_state.last_price = price_data["price"]

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Cena", f"{price_data['price']:.4f} {currency}")
        with c2:
            st.metric("High", f"{price_data['high']:.4f}")
        with c3:
            st.metric("Volume", f"{price_data['volume']:,}")

        indicators = compute_indicators(df)
        plot_live_chart(df, ticker)

        col_ai1, col_ai2 = st.columns([2,1])
        with col_ai1:
            st.subheader("🤖 LIVE‑AI sygnał")
            live_sig = ai_live_signal(openai_client, ticker, price_data["price"], indicators)
            st.session_state.last_ai_signal = live_sig
            st.markdown(live_sig)

        with col_ai2:
            st.subheader("📊 Techniczne")
            tech_df = pd.DataFrame.from_dict(indicators, orient="index", columns=["Value"])
            st.table(tech_df)

        st.subheader("🚨 ALERTY HYBRYDOWE (AI + Cena + Techniczne)")
        alerts = check_hybrid_alerts(ticker, price_data["price"], indicators, live_sig)
        if alerts:
            for a in alerts:
                st.warning(a)
        else:
            st.info("Brak alertów.")

# ============================
# AUTO‑SCAN
# ============================

st.markdown("---")
st.header("🔎 AUTO‑SCAN (lista tickerów)")

scan_input = st.text_area(
    "Wklej listę tickerów (oddzielone przecinkami):",
    value=st.session_state.scan_input,
    height=120,
    key="autoscan_area"
)
st.session_state.scan_input = scan_input

def scan_tickers(tickers_list):
    rows = []
    for raw in tickers_list:
        t = raw.strip().upper()
        if not t:
            continue

        df_s, price_s = get_price_data(t, interval="1d", period="3mo")
        if df_s is None or price_s is None or df_s.empty:
            continue

        ind_s = compute_indicators(df_s)
        avg_vol = df_s["Volume"].tail(20).mean()
        dollar_vol = avg_vol * price_s["price"]

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
    return df_scan

if st.button("🚀 Skanuj listę", key="autoscan_button"):
    tickers_list = scan_input.split(",")
    scan_df = scan_tickers(tickers_list)

    if scan_df.empty:
        st.warning("Brak wyników skanu.")
    else:
        st.subheader("📋 Ranking (Score: RSI + płynność)")
        st.dataframe(
            scan_df.style.format(
                {"Price": "{:.4f}", "RSI": "{:.2f}", "HV": "{:.4f}", "DollarVol20": "{:.0f}", "Score": "{:.2f}"}
            )
        )

# ============================
# AI‑SCENARIUSZE
# ============================

st.markdown("---")
st.header("🧠 AI‑SCENARIUSZE — Bull / Base / Bear")

sc_ticker = st.text_input("Ticker do scenariuszy:", value=ticker, key="sc_ticker").upper()

if sc_ticker:
    df_sc, price_sc = get_price_data(sc_ticker, interval="1h", period="5d")

    if df_sc is not None and price_sc is not None and not df_sc.empty:
        ind_sc = compute_indicators(df_sc)
        st.subheader(f"Scenariusze AI dla {sc_ticker}")
        scenarios_text = ai_scenarios(openai_client, sc_ticker, price_sc["price"], ind_sc)
        st.markdown(scenarios_text)
    else:
        st.warning("Brak danych do scenariuszy.")

# ============================
# PORTFEL PRO
# ============================

def add_to_portfolio(ticker, qty, buy_price, currency):
    st.session_state.portfolio.append({
        "ticker": ticker,
        "qty": qty,
        "buy_price": buy_price,
        "currency": currency
    })

def build_portfolio_df():
    rows = []
    for pos in st.session_state.portfolio:
        t = pos["ticker"]
        qty = pos["qty"]
        buy = pos["buy_price"]
        cur = pos["currency"]

        df_p, price_p = get_price_data(t, interval="1m", period="1d")
        if price_p is None:
            continue

        current = price_p["price"]
        pl = (current - buy) * qty
        pl_pct = (current / buy - 1) * 100 if buy != 0 else 0

        rows.append({
            "Ticker": t,
            "Qty": qty,
            "Buy": buy,
            "Current": current,
            "P/L": pl,
            "P/L %": pl_pct,
            "Currency": cur
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Weight %"] = df["Current"] * df["Qty"] / (df["Current"] * df["Qty"]).sum() * 100
    return df

st.markdown("---")
st.header("📂 PORTFEL PRO (LIVE)")

col_p1, col_p2, col_p3, col_p4 = st.columns([2,1,1,1])

with col_p1:
    p_ticker = st.text_input("Ticker do portfela:", value=ticker if ticker else "", key="p_ticker").upper()

with col_p2:
    p_qty = st.number_input("Ilość", min_value=1, value=100, key="p_qty")

with col_p3:
    default_buy = float(st.session_state.last_price) if st.session_state.last_price else 0.0
    p_buy = st.number_input("Cena zakupu", min_value=0.0, value=default_buy, format="%.4f", key="p_buy")

with col_p4:
    p_cur = st.selectbox("Waluta pozycji", ["USD", "PLN"], index=0, key="p_currency")

if st.button("➕ Dodaj do portfela", key="p_add"):
    add_to_portfolio(p_ticker, p_qty, p_buy, p_cur)
    st.success(f"Dodano {p_ticker} do portfela.")

port_df = build_portfolio_df()

if not port_df.empty:
    st.subheader("📊 Aktualny portfel (LIVE ceny)")
    st.dataframe(
        port_df.style.format(
            {
                "Buy": "{:.4f}",
                "Current": "{:.4f}",
                "P/L": "{:.2f}",
                "P/L %": "{:.2f}",
                "Weight %": "{:.2f}"
            }
        )
    )
    st.metric("Wartość portfela", f"{(port_df['Current']*port_df['Qty']).sum():.2f}")
else:
    st.info("Portfel jest pusty.")

# ============================
# SMART‑PRO REFRESH ENGINE
# ============================

if live_mode:

    # pobieramy dane BEZ renderowania UI
    df_tmp, price_tmp = get_price_data(ticker, interval=interval, period=period)

    if price_tmp is not None and df_tmp is not None and not df_tmp.empty:

        current_price = price_tmp["price"]
        current_volume = price_tmp["volume"]
        current_high = price_tmp["high"]
        current_low = price_tmp["low"]
        current_open = price_tmp["open"]
        current_close = price_tmp["price"]  # close = price

        # AI sygnał (lekki, szybki)
        ind_tmp = compute_indicators(df_tmp)
        ai_tmp = ai_live_signal(openai_client, ticker, current_price, ind_tmp)

        # inicjalizacja pamięci
        if "smart_pro_state" not in st.session_state:
            st.session_state.smart_pro_state = {
                "price": current_price,
                "volume": current_volume,
                "high": current_high,
                "low": current_low,
                "open": current_open,
                "close": current_close,
                "ai": ai_tmp
            }
            time.sleep(refresh_sec)
            st.rerun()

        prev = st.session_state.smart_pro_state

        # ============================
        # WARUNKI ODŚWIEŻANIA SMART‑PRO
        # ============================

        refresh_needed = False

        # 1. Zmiana ceny
        if current_price != prev["price"]:
            refresh_needed = True

        # 2. Zmiana wolumenu
        if current_volume != prev["volume"]:
            refresh_needed = True

        # 3. Zmiana świecy (OHLC)
        if current_high != prev["high"] or current_low != prev["low"] or current_open != prev["open"]:
            refresh_needed = True

        # 4. Zmiana sygnału AI
        if ai_tmp != prev["ai"]:
            refresh_needed = True

        # 5. Zmiana momentum (MACD cross)
        if ind_tmp["macd"] > ind_tmp["signal"] and prev["ai"].startswith("SELL"):
            refresh_needed = True
        if ind_tmp["macd"] < ind_tmp["signal"] and prev["ai"].startswith("BUY"):
            refresh_needed = True

        # ============================
        # JEŚLI COŚ SIĘ ZMIENIŁO → ODŚWIEŻ
        # ============================

        if refresh_needed:
            st.session_state.smart_pro_state = {
                "price": current_price,
                "volume": current_volume,
                "high": current_high,
                "low": current_low,
                "open": current_open,
                "close": current_close,
                "ai": ai_tmp
            }
            time.sleep(0.05)  # ultra‑szybka reakcja
            st.rerun()

    # jeśli nic się nie zmieniło → czekamy
    time.sleep(refresh_sec)
    st.rerun()
