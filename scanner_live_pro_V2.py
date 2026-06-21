import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from openai import OpenAI
from tavily import TavilyClient
import yfinance as yf
import plotly.graph_objects as go

# ============================
# KI‑ULTRA v9.0 + PORTFEL + ALERTY + AUTO‑SCAN
# ============================

st.set_page_config(page_title="KI‑ULTRA v9.0", page_icon="⚡", layout="wide")

NEON_CSS = """
<style>
body { background-color: #020617; color: #E5E7EB; }
section.main { background: radial-gradient(circle at top, #0f172a 0, #020617 55%); }
.block-container { padding-top: 1.5rem; }
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

st.title("⚡ KI‑ULTRA v9.0 — Multi‑Market Neon Engine")
st.caption("Penny Stocks USA + GPW .WA + Dowolny rynek z Yahoo | GPT‑4.1 | Tavily | Neon Desk")

# ============================
# KLUCZE
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
# STAN APLIKACJI
# ============================

if "portfolio" not in st.session_state:
    st.session_state.portfolio = []  # {ticker, qty, buy_price, currency}

if "alerts" not in st.session_state:
    st.session_state.alerts = []  # {ticker, type, value, direction}

# ============================
# FUNKCJE POMOCNICZE
# ============================

def detect_market(ticker: str):
    if ticker.endswith(".WA"):
        return "GPW", "PLN"
    return "USA/Global", "USD"

def get_price_data(ticker: str, interval: str = "1d", period: str = "6mo"):
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df.empty:
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

    high = df["High"]
    low = df["Low"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    log_ret = np.log(close / close.shift(1))
    hv = log_ret.rolling(20).std() * np.sqrt(252)

    return {
        "rsi": float(rsi.iloc[-1]),
        "ma20": float(ma20.iloc[-1]) if not np.isnan(ma20.iloc[-1]) else None,
        "ma50": float(ma50.iloc[-1]) if not np.isnan(ma50.iloc[-1]) else None,
        "macd": float(macd.iloc[-1]),
        "signal": float(signal.iloc[-1]),
        "atr": float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else None,
        "hv": float(hv.iloc[-1]) if not np.isnan(hv.iloc[-1]) else None,
    }

def get_fundamentals_yahoo(ticker: str):
    try:
        info = yf.Ticker(ticker).info
        return {
            "Market Cap": info.get("marketCap"),
            "P/E": info.get("trailingPE"),
            "EPS": info.get("trailingEps"),
            "Beta": info.get("beta"),
            "Dividend Yield": info.get("dividendYield"),
            "Sector": info.get("sector"),
            "Industry": info.get("industry"),
        }
    except Exception:
        return {}

def analyze_sentiment_pro(results):
    score = 0
    weighted = 0
    for r in results:
        title = (r.get("title") or "").lower()
        content = (r.get("content") or "").lower()
        text = title + " " + content

        pos_words = ["beat", "strong", "growth", "upgrade", "record", "profit", "surge"]
        neg_words = ["miss", "downgrade", "fall", "loss", "weak", "fraud", "bankruptcy"]

        local = 0
        for w in pos_words:
            if w in text:
                local += 1
        for w in neg_words:
            if w in text:
                local -= 1

        score += local
        weighted += local * (2 if "earnings" in text or "results" in text else 1)

    if weighted > 1:
        return "Bullish"
    if weighted < -1:
        return "Bearish"
    return "Neutral"

def plot_chart_pro(df: pd.DataFrame, ticker: str):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Cena"
    ))
    fig.add_trace(go.Bar(
        x=df.index,
        y=df["Volume"],
        name="Wolumen",
        marker_color="rgba(56,189,248,0.4)",
        yaxis="y2"
    ))
    fig.update_layout(
        title=f"Wykres {ticker}",
        height=550,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
        font=dict(color="#E5E7EB"),
        yaxis=dict(title="Cena"),
        yaxis2=dict(title="Wolumen", overlaying="y", side="right", showgrid=False)
    )
    st.plotly_chart(fig, use_container_width=True)

def detect_market_regime(df: pd.DataFrame):
    close = df["Close"]
    if len(close) < 20:
        return "Unknown"
    x = np.arange(len(close))
    y = close.values
    a, b = np.polyfit(x, y, 1)
    slope = a / y.mean()
    if slope > 0.01:
        return "Bull"
    if slope < -0.01:
        return "Bear"
    return "Sideways"

def liquidity_scanner(df: pd.DataFrame, price_data: dict):
    avg_vol = df["Volume"].tail(20).mean()
    dollar_vol = avg_vol * price_data["price"]
    return {
        "avg_volume_20": float(avg_vol),
        "dollar_volume_20": float(dollar_vol),
    }

def auto_fix_missing_data(openai_client, ticker, fundamentals, indicators):
    missing = {}
    for k, v in fundamentals.items():
        if v is None:
            missing[k] = v
    for k, v in indicators.items():
        if v is None:
            missing[k] = v
    if not missing:
        return fundamentals, indicators

    prompt = f"""
Uzupełnij brakujące dane dla spółki {ticker}.
Fundamenty: {fundamentals}
Techniczne: {indicators}
Brakujące: {missing}

Podaj realistyczne wartości (dla danego rynku), w czystym JSON (dict Python).
"""

    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    try:
        data = eval(r.choices[0].message.content)
        for k, v in data.items():
            if k in fundamentals:
                fundamentals[k] = v
            if k in indicators:
                indicators[k] = v
    except Exception:
        pass
    return fundamentals, indicators

def ticker_intelligence(openai_client, ticker, fundamentals):
    prompt = f"""
Oceń typ spółki {ticker} (np. blue chip, mid cap, small cap, penny stock, growth, value, spekulacyjna).
Dane: {fundamentals}
Zwróć jedno krótkie zdanie po polsku.
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return r.choices[0].message.content

def ai_risk_score(openai_client, ticker, fundamentals, indicators, sentiment, market_regime):
    prompt = f"""
Oceń ryzyko inwestycyjne spółki {ticker} w skali 0–100.

Fundamenty: {fundamentals}
Techniczne: {indicators}
Sentyment newsów: {sentiment}
Reżim rynku: {market_regime}

Zasady:
- 0 = bardzo niskie ryzyko
- 100 = ekstremalne ryzyko
- Penny stocks zwykle 70–95
Zwróć tylko liczbę.
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    try:
        return float(r.choices[0].message.content.strip())
    except Exception:
        return None

def ai_fair_value(openai_client, ticker, price, fundamentals, indicators, sentiment, market_regime):
    prompt = f"""
Oszacuj wartość godziwą (fair value) dla spółki {ticker}.

Cena bieżąca: {price}
Fundamenty: {fundamentals}
Techniczne: {indicators}
Sentyment: {sentiment}
Reżim rynku: {market_regime}

Zwróć:
- jedną liczbę fair value
- krótkie uzasadnienie (2–3 zdania)
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return r.choices[0].message.content

def ai_trend_forecast(openai_client, ticker, price, indicators, sentiment, market_regime):
    prompt = f"""
Prognozuj kierunek ceny spółki {ticker} na 7 dni.

Cena: {price}
Techniczne: {indicators}
Sentyment: {sentiment}
Reżim rynku: {market_regime}

Zwróć:
- kierunek (UP / DOWN / SIDEWAYS)
- krótkie uzasadnienie (2–3 zdania)
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return r.choices[0].message.content

def pump_and_dump_detector(openai_client, ticker, df, indicators, sentiment):
    recent = df.tail(30)["Close"].tolist()
    prompt = f"""
Wykryj, czy na spółce {ticker} może występować schemat pump & dump.

Ostatnie ceny (30 sesji): {recent}
Techniczne: {indicators}
Sentyment: {sentiment}

Zwróć:
- TAK/NIE
- krótkie uzasadnienie (2–3 zdania)
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return r.choices[0].message.content

def ai_signal_pro(openai_client, ticker, price, indicators, sentiment, market_regime, risk_score):
    prompt = f"""
Jesteś profesjonalnym analitykiem.

Oceń spółkę {ticker}.

Cena: {price}
Techniczne: {indicators}
Sentyment: {sentiment}
Reżim rynku: {market_regime}
Ryzyko (0–100): {risk_score}

Zasady:
- Na początku odpowiedzi podaj JEDNO słowo: BUY, SELL lub HOLD.
- Po myślniku podaj 3–4 zdania konkretnego uzasadnienia po polsku.
- Uwzględnij RSI, MA20/MA50, MACD, zmienność, ryzyko i sentyment.
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.25
    )
    return r.choices[0].message.content

def ai_summary_pro(openai_client, ticker, price_data, fundamentals, indicators, sentiment, market_regime, news_raw):
    prompt = f"""
Przygotuj profesjonalny raport finansowy dla spółki {ticker} w formacie Markdown.

Dane:
Cena: {price_data}
Fundamenty: {fundamentals}
Techniczne: {indicators}
Sentyment newsów: {sentiment}
Reżim rynku: {market_regime}
News (surowe): {news_raw}

Struktura:
1. Nagłówek z nazwą spółki i krótkim opisem.
2. Tabela Markdown z kluczowymi wskaźnikami (Price, Market Cap, P/E, EPS, Beta, Dividend Yield, RSI, MA20, MA50, MACD, ATR, HV).
3. 3–5 punktów komentarza analitycznego po polsku (bullet points).
"""
    r = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return r.choices[0].message.content

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
        df_p, price_p = get_price_data(t, interval="1d", period="3mo")
        if not price_p:
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

# ============================
# ALERTY AI
# ============================

def add_alert(ticker, alert_type, value, direction):
    st.session_state.alerts.append({
        "ticker": ticker,
        "type": alert_type,
        "value": value,
        "direction": direction
    })

def check_alerts(current_ticker, price_data, indicators, df):
    triggered = []
    for a in st.session_state.alerts:
        if a["ticker"] != current_ticker:
            continue
        if a["type"] == "price":
            cur = price_data["price"]
            if a["direction"] == "above" and cur > a["value"]:
                triggered.append(f"PRICE {current_ticker}: {cur:.4f} > {a['value']}")
            if a["direction"] == "below" and cur < a["value"]:
                triggered.append(f"PRICE {current_ticker}: {cur:.4f} < {a['value']}")
        if a["type"] == "rsi":
            rsi = indicators.get("rsi")
            if rsi is None:
                continue
            if a["direction"] == "above" and rsi > a["value"]:
                triggered.append(f"RSI {current_ticker}: {rsi:.2f} > {a['value']}")
            if a["direction"] == "below" and rsi < a["value"]:
                triggered.append(f"RSI {current_ticker}: {rsi:.2f} < {a['value']}")
        if a["type"] == "volume":
            vol = df["Volume"].iloc[-1]
            if a["direction"] == "above" and vol > a["value"]:
                triggered.append(f"VOLUME {current_ticker}: {vol:.0f} > {a['value']}")
            if a["direction"] == "below" and vol < a["value"]:
                triggered.append(f"VOLUME {current_ticker}: {vol:.0f} < {a['value']}")
    return triggered

# ============================
# AUTO‑SCAN 50 TICKERÓW
# ============================

def scan_tickers(tickers_list):
    rows = []
    for t in tickers_list:
        t = t.strip().upper()
        if not t:
            continue
        df_s, price_s = get_price_data(t, interval="1d", period="3mo")
        if not price_s or df_s is None or df_s.empty:
            continue
        ind_s = compute_indicators(df_s)
        liq_s = liquidity_scanner(df_s, price_s)
        rsi = ind_s.get("rsi")
        hv = ind_s.get("hv")
        dv = liq_s["dollar_volume_20"]
        rows.append({
            "Ticker": t,
            "Price": price_s["price"],
            "RSI": rsi,
            "HV": hv,
            "DollarVol20": dv
        })
    if not rows:
        return pd.DataFrame()
    df_scan = pd.DataFrame(rows)
    df_scan["Score"] = (100 - df_scan["RSI"].fillna(50)) * (df_scan["DollarVol20"].fillna(0) + 1).rank(pct=True)
    df_scan = df_scan.sort_values("Score", ascending=False)
    return df_scan

# ============================
# INTERFEJS GŁÓWNY
# ============================

top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
with top_col1:
    ticker = st.text_input("Ticker (USA, GPW .WA, inne):", value="AAPL").upper()
with top_col2:
    interval = st.selectbox("Interwał:", ["1d", "1h"], index=0)
with top_col3:
    period = st.selectbox("Okres:", ["3mo", "6mo", "1y"], index=1)

go_button = st.button("🚀 Start analizy", type="primary")

if go_button:
    dzis = datetime.today().strftime('%Y-%m-%d')
    market, currency = detect_market(ticker)

    st.markdown(f"**Rynek wykryty:** `{market}` | **Waluta domyślna:** `{currency}`")

    df, price_data = get_price_data(ticker, interval=interval, period=period)
    if price_data is None or df is None or df.empty:
        st.error("❌ Brak danych cenowych z Yahoo Finance.")
        st.stop()

    indicators = compute_indicators(df)
    fundamentals = get_fundamentals_yahoo(ticker)
    fundamentals, indicators = auto_fix_missing_data(openai_client, ticker, fundamentals, indicators)

    st.subheader("📰 News Sentiment PRO (Tavily)")
    query = f"{ticker} stock financial results earnings {dzis[:4]}"
    try:
        wyniki = tavily_client.search(query=query, topic="finance", max_results=8)
        results = wyniki.get("results", [])
    except Exception as e:
        st.error(f"Błąd Tavily: {e}")
        results = []

    headlines = []
    raw_news_chunks = []
    if results:
        for r in results:
            title = r.get("title") or ""
            content = r.get("content") or ""
            if title:
                headlines.append(title)
            if content:
                raw_news_chunks.append(content)
        st.write("Nagłówki:")
        for h in headlines[:6]:
            st.write("- ", h)
    else:
        st.write("Brak newsów z Tavily.")

    sentiment = analyze_sentiment_pro(results)
    st.metric("Sentyment newsów", sentiment)

    news_raw = "\n\n".join(raw_news_chunks) if raw_news_chunks else "Brak treści newsów."

    st.subheader("📊 Chart Engine PRO")
    st.metric("Aktualna cena", f"{price_data['price']:.4f} {currency}")
    plot_chart_pro(df, ticker)

    st.subheader("🌊 Volatility & Liquidity Engine")
    liq = liquidity_scanner(df, price_data)
    vol_liq_df = pd.DataFrame.from_dict(
        {
            "ATR": indicators.get("atr"),
            "HV (20d)": indicators.get("hv"),
            "Avg Volume 20": liq["avg_volume_20"],
            "Dollar Volume 20": liq["dollar_volume_20"],
        },
        orient="index",
        columns=["Value"]
    )
    st.table(vol_liq_df)

    market_regime = detect_market_regime(df)
    st.metric("Market Regime", market_regime)

    st.subheader("🏛️ Fundamenty (Extended)")
    st.table(pd.DataFrame.from_dict(fundamentals, orient="index", columns=["Value"]))

    st.subheader("🧠 Ticker Intelligence")
    ti_text = ticker_intelligence(openai_client, ticker, fundamentals)
    st.markdown(ti_text)

    st.subheader("⚠️ AI Risk Score (0–100)")
    risk_score = ai_risk_score(openai_client, ticker, fundamentals, indicators, sentiment, market_regime)
    st.metric("Ryzyko inwestycyjne", f"{risk_score:.1f}" if risk_score is not None else "Brak danych")

    st.subheader("💵 AI Fair Value")
    fv_text = ai_fair_value(openai_client, ticker, price_data["price"], fundamentals, indicators, sentiment, market_regime)
    st.markdown(fv_text)

    st.subheader("📈 AI Trend Forecast (7 dni)")
    trend_text = ai_trend_forecast(openai_client, ticker, price_data["price"], indicators, sentiment, market_regime)
    st.markdown(trend_text)

    st.subheader("🚨 Pump & Dump Detector")
    pad_text = pump_and_dump_detector(openai_client, ticker, df, indicators, sentiment)
    st.markdown(pad_text)

    st.subheader("🤖 AI Summary PRO (GPT‑4.1)")
    summary_text = ai_summary_pro(openai_client, ticker, price_data, fundamentals, indicators, sentiment, market_regime, news_raw)
    st.markdown(summary_text)

    st.subheader("📌 AI Signal PRO (BUY/SELL/HOLD)")
    signal_text = ai_signal_pro(openai_client, ticker, price_data["price"], indicators, sentiment, market_regime, risk_score)
    st.markdown(signal_text)

    # ============================
    # AUTO‑SCAN 50 TICKERÓW
    # ============================

    st.markdown("---")
    st.header("🔎 AUTO‑SCAN 50 tickerów")

    scan_input = st.text_area(
        "Wklej listę tickerów (oddzielone przecinkami, np. AAPL, NVDA, TSLA, NVG.WA):",
        value="AAPL, NVDA, TSLA"
    )

    if st.button("🚀 Skanuj listę"):
        tickers_list = scan_input.split(",")
        scan_df = scan_tickers(tickers_list)
        if scan_df.empty:
            st.warning("Brak wyników skanu.")
        else:
            st.subheader("📋 Ranking okazji (Score: RSI + płynność)")
            st.dataframe(
                scan_df.style.format(
                    {"Price": "{:.4f}", "RSI": "{:.2f}", "HV": "{:.4f}", "DollarVol20": "{:.0f}", "Score": "{:.2f}"}
                )
            )

    # ============================
    # PORTFEL PRO
    # ============================

    st.markdown("---")
    st.header("📂 PORTFEL PRO")

    col_p1, col_p2, col_p3, col_p4 = st.columns([2,1,1,1])
    with col_p1:
        p_ticker = st.text_input("Ticker do portfela:", value=ticker).upper()
    with col_p2:
        p_qty = st.number_input("Ilość", min_value=1, value=100)
    with col_p3:
        p_buy = st.number_input("Cena zakupu", min_value=0.0, value=float(price_data["price"]), format="%.4f")
    with col_p4:
        p_cur = st.selectbox("Waluta pozycji", [currency, "USD", "PLN"], index=0)

    if st.button("➕ Dodaj do portfela"):
        add_to_portfolio(p_ticker, p_qty, p_buy, p_cur)
        st.success(f"Dodano {p_ticker} do portfela.")

    port_df = build_portfolio_df()
    if not port_df.empty:
        st.subheader("📊 Aktualny portfel")
        st.dataframe(
            port_df.style.format(
                {"Buy": "{:.4f}", "Current": "{:.4f}", "P/L": "{:.2f}", "P/L %": "{:.2f}", "Weight %": "{:.2f}"}
            )
        )
        st.metric("Wartość portfela", f"{(port_df['Current']*port_df['Qty']).sum():.2f}")
    else:
        st.info("Portfel jest pusty.")

    # ============================
    # ALERTY AI
    # ============================

    st.markdown("---")
    st.header("⏰ ALERTY AI")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        a_type = st.selectbox("Typ alertu", ["price", "rsi", "volume"])
    with c2:
        a_dir = st.selectbox("Kierunek", ["above", "below"])
    with c3:
        default_val = float(price_data["price"]) if a_type == "price" else 50.0
        a_val = st.number_input("Wartość progu", min_value=0.0, value=default_val, format="%.4f")
    with c4:
        if st.button("➕ Dodaj alert"):
            add_alert(ticker, a_type, a_val, a_dir)
            st.success("Alert dodany.")

    if st.session_state.alerts:
        st.subheader("Aktywne alerty")
        st.write(pd.DataFrame(st.session_state.alerts))

        triggered = check_alerts(ticker, price_data, indicators, df)
        if triggered:
            st.subheader("🚨 WYZWOLONE ALERTY")
            for tmsg in triggered:
                st.error(tmsg)
    else:
        st.info("Brak aktywnych alertów.")
