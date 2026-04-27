python
# ======================================================================
#  AI ALPHA MONSTER PRO v74 — FULL SINGLE-FILE BUILD (kombaj.py)
# ======================================================================

import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import requests
import json
import os
from datetime import datetime

# ======================================================================
# 1. KONFIGURACJA
# ======================================================================

st.set_page_config(
    page_title="AI ALPHA MONSTER PRO v74",
    page_icon="🚜",
    layout="wide",
)

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

TICKERS_FILE = "moje_spolki.txt"
PORTFOLIO_FILE = "portfolio.json"

if "risk_cap" not in st.session_state:
    st.session_state.risk_cap = 10000.0
if "risk_pct" not in st.session_state:
    st.session_state.risk_pct = 1.0

# ======================================================================
# 2. CSS
# ======================================================================

st.markdown(
    """
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
    .pos-calc-box {
        background: rgba(88, 166, 255, 0.08);
        border-radius: 15px;
        padding: 25px;
        margin: 25px 0;
        border: 1px solid #58a6ff;
        color: #58a6ff;
    }
    .pos-val {
        font-size: 2.2rem;
        display: block;
        margin-bottom: 5px;
        font-weight: 900;
        text-shadow: 0 0 10px #58a6ff;
    }
    .pos-label {
        font-size: 0.85rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .tech-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        background: rgba(255,255,255,0.02);
        padding: 20px;
        border-radius: 20px;
        text-align: left;
    }
    .tech-row {
        border-bottom: 1px solid #21262d;
        padding: 10px 0;
        font-size: 0.95rem;
        display: flex;
        justify-content: space-between;
    }
    .t-lab { color: #8b949e; }
    .t-val { color: #ffffff; font-weight: bold; }
    .ai-strategy-box {
        padding: 20px;
        border-radius: 15px;
        margin-top: 25px;
        font-size: 1rem;
        background: rgba(0, 255, 136, 0.05);
        border: 1px solid #00ff88;
        line-height: 1.6;
        text-align: left;
        color: #00ff88;
    }
    .news-link {
        color: #58a6ff;
        text-decoration: none;
        font-size: 0.85rem;
        display: block;
        margin-bottom: 12px;
        text-align: left;
    }
    .block-container {
        max-width: 98% !important;
        padding-top: 1.5rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ======================================================================
# 3. UTILS + PLIK TICKERÓW
# ======================================================================

def load_tickers():
    if os.path.exists(TICKERS_FILE):
        try:
            with open(TICKERS_FILE, "r") as f:
                c = f.read().strip()
                return c
        except Exception:
            pass
    return ""

def save_tickers(text):
    with open(TICKERS_FILE, "w") as f:
        f.write(text)

def format_pln(v):
    return f"{v:,.2f} zł".replace(",", " ").replace(".", ",")

# ======================================================================
# 4. PORTFEL
# ======================================================================

def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"positions": [], "history": [], "value_history": []}
    try:
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"positions": [], "history": [], "value_history": []}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f, indent=4)

def add_transaction(portfolio, symbol, qty, price):
    symbol = symbol.upper()
    qty = float(qty)
    price = float(price)
    portfolio["history"].append({
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "timestamp": datetime.utcnow().isoformat()
    })
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

def compute_portfolio_value(portfolio, prices, prices_yesterday=None):
    total = 0.0
    total_pl = 0.0
    daily_pl = 0.0
    details = []
    for pos in portfolio["positions"]:
        sym = pos["symbol"]
        qty = pos["qty"]
        avg = pos["avg_price"]
        if qty == 0:
            continue
        price = prices.get(sym)
        if price is None:
            continue
        value = qty * price
        pl = (price - avg) * qty
        total += value
        total_pl += pl
        if prices_yesterday is not None and sym in prices_yesterday:
            daily_pl += (price - prices_yesterday[sym]) * qty
        details.append({
            "symbol": sym,
            "qty": qty,
            "avg_price": avg,
            "price": price,
            "value": value,
            "pl": pl,
        })
    return total, total_pl, daily_pl, details

def update_portfolio_history(portfolio, total_value):
    portfolio["value_history"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "value": total_value
    })
    save_portfolio(portfolio)

def portfolio_chart(portfolio):
    if not portfolio["value_history"]:
        return None
    df = pd.DataFrame(portfolio["value_history"])
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
        height=300,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig

# ======================================================================
# 5. ANALITYKA TECHNICZNA
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

def pivots_classic(h, l, c):
    p = (h + l + c) / 3
    r1 = 2*p - l
    s1 = 2*p - h
    r2 = p + (h - l)
    s2 = p - (h - l)
    r3 = h + 2*(p - l)
    s3 = l - 2*(h - p)
    return p, r1, s1, r2, s2, r3, s3

def pivots_camarilla(h, l, c):
    r = h - l
    r1 = c + r * 1.1/12
    r2 = c + r * 1.1/6
    r3 = c + r * 1.1/4
    r4 = c + r * 1.1/2
    s1 = c - r * 1.1/12
    s2 = c - r * 1.1/6
    s3 = c - r * 1.1/4
    s4 = c - r * 1.1/2
    return r1, r2, r3, r4, s1, s2, s3, s4

def pivots_fibonacci(h, l, c):
    p = (h + l + c) / 3
    r = h - l
    r1 = p + 0.382 * r
    r2 = p + 0.618 * r
    r3 = p + 1.000 * r
    s1 = p - 0.382 * r
    s2 = p - 0.618 * r
    s3 = p - 1.000 * r
    return p, r1, r2, r3, s1, s2, s3

def compute_score(rsi, macd, ema20, ema50, price, atr):
    score = 50
    if rsi < 30:
        score += 15
    elif rsi > 70:
        score -= 15
    if macd > 0:
        score += 10
    else:
        score -= 10
    if ema20 > ema50:
        score += 10
    else:
        score -= 10
    if atr > price * 0.05:
        score -= 5
    else:
        score += 5
    return max(0, min(100, score))

def analyze_symbol(symbol):
    try:
        t = yf.Ticker(symbol, session=session)
        df = t.history(period="1y", interval="1d", auto_adjust=False)
        if df.empty or len(df) < 50:
            return None
        df["Close"] = df["Close"].replace(0, np.nan).ffill()
        price = df["Close"].iloc[-1]
        prev = df.iloc[-2]
        rsi = compute_rsi(df["Close"]).iloc[-1]
        macd = compute_macd(df["Close"]).iloc[-1]
        ema20 = compute_ema(df["Close"], 20).iloc[-1]
        ema50 = compute_ema(df["Close"], 50).iloc[-1]
        atr = compute_atr(df).iloc[-1]
        p_classic = pivots_classic(prev["High"], prev["Low"], prev["Close"])
        p_camarilla = pivots_camarilla(prev["High"], prev["Low"], prev["Close"])
        p_fibo = pivots_fibonacci(prev["High"], prev["Low"], prev["Close"])
        sl = price - atr * 1.5
        tp = price + atr * 3.0
        score = compute_score(rsi, macd, ema20, ema50, price, atr)
        news = []
        try:
            for n in t.news[:3]:
                news.append({
                    "title": str(n.get("title", ""))[:65],
                    "link": n.get("link", ""),
                })
        except Exception:
            pass
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
            "df": df.tail(80),
            "news": news,
        }
    except Exception:
        return None

# ======================================================================
# 6. AI SUMMARY PORTFELA
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
    except Exception:
        return "Błąd AI."

# ======================================================================
# 7. UI GŁÓWNY – TICKERY, AUTO-REFRESH, PORTFEL, KAFELKI
# ======================================================================

st.sidebar.title("🚜 MONSTER v74 PRO")

refresh_minutes = st.sidebar.slider("Auto-refresh (minuty)", 1, 10, 3)
if st.sidebar.checkbox("Włącz auto-refresh", value=True):
    st_autorefresh(interval=refresh_minutes * 60 * 1000, key="auto_refresh_v74")

st.session_state.risk_cap = st.sidebar.number_input(
    "Kapitał PLN:", value=st.session_state.risk_cap
)
st.session_state.risk_pct = st.sidebar.slider(
    "Ryzyko % na pozycję:", 0.1, 5.0, st.session_state.risk_pct
)

tickers_text = st.sidebar.text_area(
    "Lista symboli (CSV):",
    load_tickers(),
    height=200,
    placeholder="ADTX, ACRS, ALZN, ..."
)

if st.sidebar.button("💾 Zapisz listę"):
    save_tickers(tickers_text)
    st.experimental_rerun()

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
# 8. TOP 10 SYGNAŁÓW (SCORING)
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
# 9. PORTFEL – KAFELKI + WYKRES
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

if st.checkbox("🤖 AI podsumowanie portfela"):
    with st.spinner("AI analizuje portfel..."):
        summary = ai_summary_portfolio(port_details)
    st.markdown(f"<div class='ai-strategy-box'>{summary}</div>", unsafe_allow_html=True)

st.divider()

# ======================================================================
# 10. KAFELKI DLA KAŻDEGO TICKERA
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
# 11. STOPKA
# ======================================================================

st.markdown(
    "<center><br><small style='color:#333;'>AI ALPHA MONSTER PRO v74 © 2026 | "
    "Auto-refresh: 1–10 min</small></center>",
    unsafe_allow_html=True,
)

