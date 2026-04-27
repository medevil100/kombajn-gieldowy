# ======================================================================
#  AI ALPHA MONSTER PRO v74 — FULL BUILD (CZĘŚĆ 1/4)
#  Autor: Asam + Copilot
#  Funkcje w tej części:
#   - konfiguracja
#   - CSS neon-dark (poprawiony)
#   - odświeżanie 1–10 minut
#   - system portfolio (BUY/SELL/HOLD, średnia cena, multi-transakcje)
#   - utils
# ======================================================================

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import json
import os
import time
from datetime import datetime
from openai import OpenAI
import requests

# ======================================================================
# 1. KONFIGURACJA
# ======================================================================

st.set_page_config(
    page_title="AI ALPHA MONSTER PRO v74",
    page_icon="🚜",
    layout="wide",
)

# Sesja HTTP (mniej banów z Yahoo)
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
})

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

# ======================================================================
# 2. USTAWIENIA ODŚWIEŻANIA (1–10 minut)
# ======================================================================

st.sidebar.subheader("⏱ Odświeżanie danych")
refresh_minutes = st.sidebar.slider("Co ile minut odświeżać?", 1, 10, 3)
refresh_ms = refresh_minutes * 60 * 1000

st_autorefresh = st.sidebar.checkbox("Auto-refresh", value=True)

if st_autorefresh:
    st.experimental_rerun()

# ======================================================================
# 3. CSS — TWÓJ STYL NEON DARK (POPRAWIONY)
# ======================================================================

st.markdown("""
<style>
.stApp {
    background-color: #010101;
    color: #e0e0e0;
    font-family: 'Inter', sans-serif;
}
.top-mini-tile {
    padding: 15px;
    border-radius: 12px;
    text-align: center;
    background: linear-gradient(145deg, #0d1117, #050505);
    border: 1px solid #30363d;
    margin-bottom: 15px;
    transition: 0.3s ease;
}
.tile-buy {
    border: 2px solid #00ff88 !important;
    box-shadow: 0 0 15px rgba(0,255,136,0.3);
}
.tile-sell {
    border: 2px solid #ff4b4b !important;
    box-shadow: 0 0 15px rgba(255,75,75,0.3);
}
.tile-neutral {
    border: 2px solid #8b949e !important;
    box-shadow: 0 0 15px rgba(139,148,158,0.3);
}
.main-card {
    background: linear-gradient(145deg, #0d1117, #020202);
    padding: 35px;
    border-radius: 25px;
    border: 1px solid #30363d;
    text-align: center;
    min-height: 1100px;
    width: 100%;
    transition: 0.3s ease-in-out;
    margin-bottom: 40px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}
.main-card:hover {
    border-color: #58a6ff;
    box-shadow: 0 0 30px rgba(88, 166, 255, 0.15);
}
.ai-box {
    padding: 20px;
    border-radius: 15px;
    margin-top: 25px;
    background: rgba(0, 255, 136, 0.05);
    border: 1px solid #00ff88;
    color: #00ff88;
    line-height: 1.6;
    text-align: left;
}
.news-link {
    color: #58a6ff;
    text-decoration: none;
    font-size: 0.85rem;
    display: block;
    margin-bottom: 12px;
}
.block-container {
    max-width: 98% !important;
    padding-top: 1.5rem !important;
}
</style>
""", unsafe_allow_html=True)

# ======================================================================
# 4. PORTFEL — BUY/SELL/HOLD, ŚREDNIA CENA, MULTI-TRANSAKCJE
# ======================================================================

PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"positions": [], "history": []}
    try:
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    except:
        return {"positions": [], "history": []}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f, indent=4)

def add_transaction(portfolio, symbol, qty, price):
    """Dodaje transakcję BUY lub SELL."""
    symbol = symbol.upper()
    qty = float(qty)
    price = float(price)

    # zapis do historii
    portfolio["history"].append({
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "timestamp": datetime.utcnow().isoformat()
    })

    # aktualizacja pozycji
    pos = next((x for x in portfolio["positions"] if x["symbol"] == symbol), None)

    if pos is None:
        portfolio["positions"].append({
            "symbol": symbol,
            "qty": qty,
            "avg_price": price
        })
    else:
        new_qty = pos["qty"] + qty
        if new_qty == 0:
            pos["qty"] = 0
            pos["avg_price"] = 0
        elif qty > 0:
            pos["avg_price"] = (pos["avg_price"] * pos["qty"] + price * qty) / new_qty
            pos["qty"] = new_qty
        else:
            pos["qty"] = new_qty

    return portfolio

portfolio = load_portfolio()

# ======================================================================
# 5. UTILS
# ======================================================================

def format_pln(v):
    return f"{v:,.2f} zł".replace(",", " ").replace(".", ",")

def safe_float(v, default=0.0):
    try:
        return float(v)
    except:
        return default
# ======================================================================
# 6. ANALITYKA TECHNICZNA — RSI, MACD, EMA, ATR, PIVOTY, SCORING
# ======================================================================

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = delta.where(delta < 0, 0).abs().rolling(period).mean()
    rs = gain / (loss + 1e-12)
    return 100 - (100 / (1 + rs))

def compute_macd(series):
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    return ema12 - ema26

def compute_ema(series, period):
    return series.ewm(span=period).mean()

def compute_atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ======================================================================
# 7. PIVOTY — KLASYCZNE, CAMARILLA, FIBONACCI
# ======================================================================

def pivots_classic(prev_high, prev_low, prev_close):
    p = (prev_high + prev_low + prev_close) / 3
    r1 = 2*p - prev_low
    s1 = 2*p - prev_high
    r2 = p + (prev_high - prev_low)
    s2 = p - (prev_high - prev_low)
    r3 = prev_high + 2*(p - prev_low)
    s3 = prev_low - 2*(prev_high - p)
    return p, r1, s1, r2, s2, r3, s3

def pivots_camarilla(prev_high, prev_low, prev_close):
    rng = prev_high - prev_low
    r1 = prev_close + rng * 1.1/12
    r2 = prev_close + rng * 1.1/6
    r3 = prev_close + rng * 1.1/4
    r4 = prev_close + rng * 1.1/2
    s1 = prev_close - rng * 1.1/12
    s2 = prev_close - rng * 1.1/6
    s3 = prev_close - rng * 1.1/4
    s4 = prev_close - rng * 1.1/2
    return r1, r2, r3, r4, s1, s2, s3, s4

def pivots_fibonacci(prev_high, prev_low, prev_close):
    p = (prev_high + prev_low + prev_close) / 3
    rng = prev_high - prev_low
    r1 = p + 0.382 * rng
    r2 = p + 0.618 * rng
    r3 = p + 1.000 * rng
    s1 = p - 0.382 * rng
    s2 = p - 0.618 * rng
    s3 = p - 1.000 * rng
    return p, r1, r2, r3, s1, s2, s3

# ======================================================================
# 8. SCORING 0–100
# ======================================================================

def compute_score(rsi, macd, ema20, ema50, price, atr):
    score = 50

    # RSI
    if rsi < 30:
        score += 15
    elif rsi > 70:
        score -= 15

    # MACD
    if macd > 0:
        score += 10
    else:
        score -= 10

    # EMA cross
    if ema20 > ema50:
        score += 10
    else:
        score -= 10

    # ATR (zmienność)
    if atr > price * 0.05:
        score -= 5
    else:
        score += 5

    return max(0, min(100, score))

# ======================================================================
# 9. GŁÓWNA FUNKCJA ANALITYCZNA DLA TICKERA
# ======================================================================

def analyze_symbol(symbol):
    try:
        t = yf.Ticker(symbol, session=session)
        df = t.history(period="1y", interval="1d", auto_adjust=False)

        if df.empty or len(df) < 50:
            return None

        df["Close"] = df["Close"].replace(0, np.nan).ffill()

        price = df["Close"].iloc[-1]
        prev = df.iloc[-2]

        # Techniczne
        rsi = compute_rsi(df["Close"]).iloc[-1]
        macd = compute_macd(df["Close"]).iloc[-1]
        ema20 = compute_ema(df["Close"], 20).iloc[-1]
        ema50 = compute_ema(df["Close"], 50).iloc[-1]
        atr = compute_atr(df).iloc[-1]

        # Pivoty
        p_classic = pivots_classic(prev["High"], prev["Low"], prev["Close"])
        p_camarilla = pivots_camarilla(prev["High"], prev["Low"], prev["Close"])
        p_fibo = pivots_fibonacci(prev["High"], prev["Low"], prev["Close"])

        # TP/SL dynamiczne
        sl = price - atr * 1.5
        tp = price + atr * 3.0

        # Scoring
        score = compute_score(rsi, macd, ema20, ema50, price, atr)

        return {
            "symbol": symbol,
            "price": float(price),
            "rsi": float(rsi),
            "macd": float(macd),
            "ema20": float(ema20),
            "ema50": float(ema50),
            "atr": float(atr),
            "sl": float(sl),
            "tp": float(tp),
            "score": int(score),
            "p_classic": p_classic,
            "p_camarilla": p_camarilla,
            "p_fibo": p_fibo,
            "df": df.tail(120)
        }

    except Exception:
        return None
# ======================================================================
# 10. PORTFEL PRO — WARTOŚĆ, P/L, TOP-10, WYKRES PORTFELA
# ======================================================================

def compute_portfolio_value(portfolio, prices):
    """Oblicza aktualną wartość portfela na podstawie cen rynkowych."""
    total = 0
    details = []

    for pos in portfolio["positions"]:
        sym = pos["symbol"]
        qty = pos["qty"]
        avg = pos["avg_price"]

        if qty == 0:
            continue

        price = prices.get(sym, None)
        if price is None:
            continue

        value = qty * price
        pl = (price - avg) * qty

        details.append({
            "symbol": sym,
            "qty": qty,
            "avg_price": avg,
            "price": price,
            "value": value,
            "pl": pl
        })

        total += value

    return total, details


def compute_daily_pl(portfolio, prices_today, prices_yesterday):
    """P/L dzienny."""
    total = 0
    for pos in portfolio["positions"]:
        sym = pos["symbol"]
        qty = pos["qty"]

        if qty == 0:
            continue

        p_today = prices_today.get(sym, None)
        p_yest = prices_yesterday.get(sym, None)

        if p_today is None or p_yest is None:
            continue

        total += (p_today - p_yest) * qty

    return total


def portfolio_chart(history):
    """Wykres wartości portfela w czasie."""
    if len(history) < 2:
        return None

    df = pd.DataFrame(history)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["value"],
        mode="lines",
        line=dict(color="#58a6ff", width=3),
        name="Wartość portfela"
    ))

    fig.update_layout(
        template="plotly_dark",
        height=350,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def update_portfolio_history(portfolio, total_value):
    """Zapisuje wartość portfela do historii."""
    if "value_history" not in portfolio:
        portfolio["value_history"] = []

    portfolio["value_history"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "value": total_value
    })

    save_portfolio(portfolio)


# ======================================================================
# 11. AI SUMMARY PORTFELA
# ======================================================================

def ai_summary_portfolio(details):
    if not client:
        return "Brak klucza API."

    if not details:
        return "Portfel jest pusty."

    text = "Podsumuj portfel inwestora. Dane:\n"
    for d in details:
        text += (
            f"- {d['symbol']}: qty={d['qty']}, avg={d['avg_price']:.4f}, "
            f"price={d['price']:.4f}, value={d['value']:.2f}, pl={d['pl']:.2f}\n"
        )

    prompt = (
        "Jesteś analitykiem finansowym. Oceń portfel inwestora, "
        "zwróć uwagę na ryzyko, dywersyfikację, ekspozycję, "
        "najsilniejsze i najsłabsze pozycje. "
        "Podaj rekomendacje i ocenę portfela w skali 0–100.\n\n"
        + text
    )

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content
    except:
        return "Błąd AI."
```python
# ======================================================================
# 12. UI GŁÓWNY – TICKERY, AUTO-REFRESH, PORTFEL, KAFELKI
# ======================================================================

st.sidebar.title("🚜 MONSTER v74 PRO")

# Auto-refresh 1–10 minut
refresh_minutes = st.sidebar.slider("Auto-refresh (minuty)", 1, 10, 3)
if st.sidebar.checkbox("Włącz auto-refresh", value=True):
    st_autorefresh(interval=refresh_minutes * 60 * 1000, key="auto_refresh_v74")

# Ryzyko
st.session_state.risk_cap = st.sidebar.number_input(
    "Kapitał PLN:", value=st.session_state.risk_cap
)
st.session_state.risk_pct = st.sidebar.slider(
    "Ryzyko % na pozycję:", 0.1, 5.0, st.session_state.risk_pct
)

# Tickery – bez żadnych firm na sztywno
tickers_text = st.sidebar.text_area(
    "Lista symboli (CSV):",
    load_tickers(),
    height=200,
    placeholder="ADTX, ACRS, ALZN, ..."
)

if st.sidebar.button("💾 Zapisz listę"):
    save_tickers(tickers_text)
    st.experimental_rerun()

# ======================================================================
# 13. GŁÓWNE OBLICZENIA
# ======================================================================

st.title("AI ALPHA MONSTER PRO v74")

symbols = [s.strip().upper() for s in tickers_text.split(",") if s.strip()]
results = []
prices_today = {}
prices_yesterday = {}

for sym in symbols:
    r = analyze_symbol(sym)
    if r:
        results.append(r)
        prices_today[sym] = r["price"]
        if len(r["df"]) > 1:
            prices_yesterday[sym] = float(r["df"]["Close"].iloc[-2])

portfolio = load_portfolio()
total_value, total_pl, daily_pl, port_details = compute_portfolio_value(
    portfolio, prices_today, prices_yesterday
)

if total_value > 0:
    update_portfolio_history(portfolio, total_value)

# ======================================================================
# 14. TOP 10 SYGNAŁÓW (SCORING)
# ======================================================================

if results:
    st.subheader("🔥 TOP 10 (scoring 0–100)")
    top_cols = st.columns(5)
    for i, r in enumerate(sorted(results, key=lambda x: x["score"], reverse=True)[:10]):
        if r["rsi"] < 33:
            tile_class = "tile-buy"
            sig = "KUP"
        elif r["rsi"] > 67:
            tile_class = "tile-sell"
            sig = "SPRZEDAJ"
        else:
            tile_class = "tile-neutral"
            sig = "CZEKAJ"
        with top_cols[i % 5]:
            st.markdown(
                f"""
                <div class="top-mini-tile {tile_class}">
                    <b>{r['symbol']}</b><br>
                    {r['price']:.4f}<br>
                    <small>{sig} | score: {r['score']}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.divider()

# ======================================================================
# 15. PORTFEL – KAFELKI + WYKRES
# ======================================================================

st.subheader("📊 Portfel (PLN)")
col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1:
    st.metric("Wartość portfela", format_pln(total_value))
with col_p2:
    st.metric("P/L całkowity", format_pln(total_pl))
with col_p3:
    st.metric("P/L dzienny", format_pln(daily_pl))
with col_p4:
    st.metric("Liczba pozycji", len([p for p in portfolio["positions"] if p["qty"] != 0]))

fig_port = portfolio_chart(portfolio)
if fig_port:
    st.plotly_chart(fig_port, use_container_width=True)

if port_details:
    df_port = pd.DataFrame(port_details)
    df_port_sorted = df_port.sort_values("pl", ascending=False)
    st.subheader("Top 10 pozycji wg zysku")
    st.dataframe(df_port_sorted.head(10)[["symbol", "qty", "avg_price", "price", "value", "pl"]])

    if st.checkbox("Pokaż pełny portfel"):
        st.dataframe(df_port_sorted)

# AI summary portfela
if st.checkbox("🤖 AI podsumowanie portfela"):
    with st.spinner("AI analizuje portfel..."):
        summary = ai_summary_portfolio(port_details)
    st.markdown(f"<div class='ai-strategy-box'>{summary}</div>", unsafe_allow_html=True)

st.divider()

# ======================================================================
# 16. KAFELKI DLA KAŻDEGO TICKERA
# ======================================================================

if results:
    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            st.markdown(
                f"""
                <div class="main-card">
                    <div>
                        <h2 style="margin:0;">{r['symbol']}</h2>
                        <h1 style="color:#58a6ff; margin:10px 0;">{r['price']:.6f}</h1>
                        <div class="sig-neutral">score: {r['score']}</div>
                    </div>

                    <div class="pos-calc-box">
                        <span class="pos-label">TP / SL (ATR)</span>
                        <span class="pos-val">TP: {r['tp']:.6f}</span>
                        <small>SL: {r['sl']:.6f}</small>
                    </div>

                    <div class="tech-grid">
                        <div class="tech-row">
                            <span class="t-lab">RSI (14)</span>
                            <span class="t-val">{r['rsi']:.1f}</span>
                        </div>
                        <div class="tech-row">
                            <span class="t-lab">MACD</span>
                            <span class="t-val">{r['macd']:.4f}</span>
                        </div>
                        <div class="tech-row">
                            <span class="t-lab">EMA 20</span>
                            <span class="t-val">{r['ema20']:.4f}</span>
                        </div>
                        <div class="tech-row">
                            <span class="t-lab">EMA 50</span>
                            <span class="t-val">{r['ema50']:.4f}</span>
                        </div>
                        <div class="tech-row">
                            <span class="t-lab">ATR (14)</span>
                            <span class="t-val">{r['atr']:.4f}</span>
                        </div>
                        <div class="tech-row">
                            <span class="t-lab">Pivot (classic)</span>
                            <span class="t-val">{r['p_classic'][0]:.4f}</span>
                        </div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=r["df"].index,
                        open=r["df"]["Open"],
                        high=r["df"]["High"],
                        low=r["df"]["Low"],
                        close=r["df"]["Close"],
                    )
                ]
            )
            fig.update_layout(
                template="plotly_dark",
                height=400,
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis_rangeslider_visible=False,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False},
            )

            st.markdown(
                "<div style='text-align:left; margin-top:20px;'>"
                "<span class='t-lab'>OSTATNIE NEWSY:</span></div>",
                unsafe_allow_html=True,
            )
            for n in r["news"]:
                if n.get("link"):
                    st.markdown(
                        f"<a class='news-link' href='{n['link']}' target='_blank'>● {n['title']}</a>",
                        unsafe_allow_html=True,
                    )
            st.markdown("</div>", unsafe_allow_html=True)

# ======================================================================
# 17. STOPKA
# ======================================================================

st.markdown(
    "<center><br><small style='color:#333;'>AI ALPHA MONSTER PRO v74 © 2026 | "
    "Auto-refresh: 1–10 min</small></center>",
    unsafe_allow_html=True,
)
