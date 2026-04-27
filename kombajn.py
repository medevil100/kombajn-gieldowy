import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
import json
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA
# ==============================================================================
st.set_page_config(
    page_title="AI ALPHA MONSTER PRO v71",
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

DB_FILE = "moje_spolki.txt"
PORTFOLIO_FILE = "portfolio.json"

AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if "risk_cap" not in st.session_state:
    st.session_state.risk_cap = 10000.0
if "risk_pct" not in st.session_state:
    st.session_state.risk_pct = 1.0


def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                c = f.read().strip()
                return c if c else "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BDRX, BNOX, BOLT"
        except Exception:
            pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BDRX, BNOX, BOLT"


# ==============================================================================
# 2. PORTFEL REAL-PRO (portfolio.json)
# ==============================================================================
def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict) and "positions" in data:
                    return data
        except Exception:
            pass
    return {"positions": []}


def save_portfolio(portfolio):
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(portfolio, f, indent=2)
    except Exception:
        pass


def add_position(portfolio, symbol, qty, price, sl, tp):
    if qty <= 0:
        return portfolio
    pos = {
        "id": f"{symbol}_{datetime.utcnow().isoformat()}",
        "symbol": symbol,
        "qty": float(qty),
        "entry_price": float(price),
        "sl": float(sl),
        "tp": float(tp),
        "opened_at": datetime.utcnow().isoformat(),
        "closed_at": None,
        "status": "open",
    }
    portfolio["positions"].append(pos)
    save_portfolio(portfolio)
    return portfolio


def close_position_partial(portfolio, symbol, qty_to_sell, current_price):
    if qty_to_sell <= 0:
        return portfolio
    remaining = qty_to_sell
    for pos in portfolio["positions"]:
        if pos["status"] != "open":
            continue
        if pos["symbol"] != symbol:
            continue
        if remaining <= 0:
            break
        pos_qty = pos["qty"]
        if pos_qty <= remaining + 1e-9:
            remaining -= pos_qty
            pos["qty"] = 0.0
            pos["closed_at"] = datetime.utcnow().isoformat()
            pos["status"] = "closed"
        else:
            pos["qty"] = pos_qty - remaining
            remaining = 0.0
    save_portfolio(portfolio)
    return portfolio


def compute_portfolio_metrics(portfolio, price_map):
    rows = []
    total_invested = 0.0
    total_value = 0.0
    for pos in portfolio["positions"]:
        if pos["status"] != "open" or pos["qty"] <= 0:
            continue
        sym = pos["symbol"]
        qty = pos["qty"]
        entry = pos["entry_price"]
        price = price_map.get(sym, entry)
        invested = qty * entry
        value = qty * price
        pl = value - invested
        rows.append({
            "symbol": sym,
            "qty": qty,
            "entry_price": entry,
            "current_price": price,
            "invested": invested,
            "value": value,
            "pl": pl,
        })
        total_invested += invested
        total_value += value

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["symbol", "qty", "entry_price", "current_price", "invested", "value", "pl"]
    )
    agg = None
    if not df.empty:
        agg = (
            df.groupby("symbol")
            .agg({
                "qty": "sum",
                "entry_price": "mean",
                "current_price": "mean",
                "invested": "sum",
                "value": "sum",
                "pl": "sum",
            })
            .reset_index()
        )
    return df, agg, total_invested, total_value


# ==============================================================================
# 3. CSS NEON
# ==============================================================================
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

    .sig-buy {
        color: #00ff88;
        font-weight: 900;
        font-size: 1.8rem;
        text-transform: uppercase;
        text-shadow: 0 0 12px #00ff88;
    }
    .sig-sell {
        color: #ff4b4b;
        font-weight: 900;
        font-size: 1.8rem;
        text-transform: uppercase;
        text-shadow: 0 0 12px #ff4b4b;
    }
    .sig-neutral {
        color: #8b949e;
        font-weight: 800;
        font-size: 1.5rem;
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

# ==============================================================================
# 4. SILNIK ANALITYCZNY
# ==============================================================================
def get_monster_analysis(symbol: str):
    try:
        time.sleep(np.random.uniform(0.1, 0.4))
        s = symbol.strip().upper()
        t = yf.Ticker(s, session=session)

        df_raw = t.history(period="2y", interval="1d", auto_adjust=False)
        if df_raw.empty or len(df_raw) < 200:
            return None

        df_raw["Close"] = df_raw["Close"].replace(0, np.nan).ffill()
        c = df_raw["Close"]
        curr_price = float(c.iloc[-1])

        s20 = c.rolling(20).mean().iloc[-1]
        s50 = c.rolling(50).mean().iloc[-1]
        s100 = c.rolling(100).mean().iloc[-1]
        s200 = c.rolling(200).mean().iloc[-1]

        delta = c.diff()
        g = delta.where(delta > 0, 0).rolling(14).mean()
        l = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi_val = 100 - (100 / (1 + (g / (l + 1e-12)))).iloc[-1]

        e12 = c.ewm(span=12).mean()
        e26 = c.ewm(span=26).mean()
        macd_val = (e12 - e26).iloc[-1]

        prev = df_raw.iloc[-2]
        pivot = (prev["High"] + prev["Low"] + prev["Close"]) / 3
        h52 = df_raw["High"].tail(252).max()
        l52 = df_raw["Low"].tail(252).min()

        high = df_raw["High"]
        low = df_raw["Low"]
        close = df_raw["Close"]
        tr = pd.concat(
            [
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100.0)
        sh = int(risk_cash / (atr * 1.5)) if atr > 0 else 0
        sl = curr_price - (atr * 1.5)
        tp = curr_price + (atr * 3.5)

        if rsi_val < 33:
            v_text, v_class, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 67:
            v_text, v_class, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else:
            v_text, v_class, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        news = []
        try:
            for n in t.news[:3]:
                news.append(
                    {
                        "title": str(n.get("title", ""))[:65],
                        "link": n.get("link", ""),
                    }
                )
        except Exception:
            pass

        return {
            "symbol": s,
            "price": curr_price,
            "rsi": float(rsi_val),
            "macd": float(macd_val),
            "pivot": float(pivot),
            "s20": float(s20),
            "s50": float(s50),
            "s100": float(s100),
            "s200": float(s200),
            "h52": float(h52),
            "l52": float(l52),
            "atr": float(atr),
            "sh": int(sh),
            "sl": float(sl),
            "tp": float(tp),
            "v_text": v_text,
            "v_class": v_class,
            "v_type": v_type,
            "news": news,
            "df": df_raw.tail(80),
        }
    except Exception:
        return None


# ==============================================================================
# 5. UI: SIDEBAR, AUTO-REFRESH, TICKERY
# ==============================================================================
st.sidebar.title("🚜 MONSTER v71 PRO")

refresh_minutes = st.sidebar.slider("Auto-refresh (minuty):", 1, 10, 1)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="global_monster_refresh")

t_area = st.sidebar.text_area("Lista Symboli (CSV):", load_tickers(), height=250)
st.session_state.risk_cap = st.sidebar.number_input(
    "Kapitał PLN:", value=st.session_state.risk_cap
)
st.session_state.risk_pct = st.sidebar.slider(
    "Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct
)

if st.sidebar.button("💾 ZAPISZ I START"):
    with open(DB_FILE, "w") as f:
        f.write(t_area)
    st.rerun()

symbols = [s.strip().upper() for s in t_area.split(",") if s.strip()]

# ==============================================================================
# 6. ANALIZA WIELOWĄTKOWA
# ==============================================================================
with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in executor.map(get_monster_analysis, symbols) if r]

portfolio = load_portfolio()

if results:
    price_map = {r["symbol"]: r["price"] for r in results}

    # TOP 10
    st.subheader("🔥 TOP 10 SYGNAŁÓW (Najniższe RSI)")
    top_cols = st.columns(5)
    for i, r in enumerate(sorted(results, key=lambda x: x["rsi"])[:10]):
        tile_class = (
            "tile-buy" if r["v_type"] == "buy"
            else "tile-sell" if r["v_type"] == "sell"
            else "tile-neutral"
        )
        with top_cols[i % 5]:
            st.markdown(
                f"""
                <div class="top-mini-tile {tile_class}">
                    <b>{r['symbol']}</b><br>
                    {r['price']:.4f}<br>
                    <small>{r['v_text']}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    # GŁÓWNA SIATKA
    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            with st.container():
                st.markdown(
                    f"""
                    <div class="main-card">
                        <div>
                            <h2 style="margin:0;">{r['symbol']}</h2>
                            <h1 style="color:#58a6ff; margin:10px 0;">{r['price']:.6f}</h1>
                            <div class="{r['v_class']}">{r['v_text']}</div>
                        </div>

                        <div class="pos-calc-box">
                            <span class="pos-label">WIELKOŚĆ POZYCJI (RYZYKO)</span>
                            <span class="pos-val">{r['sh']} SZT.</span>
                            <small>SL: {r['sl']:.6f} | TP: {r['tp']:.6f}</small>
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
                                <span class="t-lab">SMA 20</span>
                                <span class="t-val">{r['s20']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">SMA 50</span>
                                <span class="t-val">{r['s50']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">SMA 100</span>
                                <span class="t-val">{r['s100']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">SMA 200</span>
                                <span class="t-val">{r['s200']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">Pivot</span>
                                <span class="t-val">{r['pivot']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">Max 52T</span>
                                <span class="t-val">{r['h52']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">Min 52T</span>
                                <span class="t-val">{r['l52']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">ATR (14)</span>
                                <span class="t-val">{r['atr']:.4f}</span>
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
                    key=f"chart_{r['symbol']}_{idx}",
                    config={"displayModeBar": False},
                )

                qty_key = f"qty_{r['symbol']}_{idx}"
                if qty_key not in st.session_state:
                    st.session_state[qty_key] = r["sh"]
                qty = st.number_input(
                    f"Ilość ({r['symbol']})",
                    min_value=0,
                    value=int(st.session_state[qty_key]),
                    key=qty_key,
                )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        f"🟢 KUP do portfela {r['symbol']}",
                        key=f"buy_{r['symbol']}_{idx}",
                    ):
                        portfolio = add_position(
                            portfolio,
                            r["symbol"],
                            qty,
                            r["price"],
                            r["sl"],
                            r["tp"],
                        )
                        st.experimental_rerun()
                with c2:
                    if st.button(
                        f"🔴 SPRZEDAJ z portfela {r['symbol']}",
                        key=f"sell_{r['symbol']}_{idx}",
                    ):
                        portfolio = close_position_partial(
                            portfolio,
                            r["symbol"],
                            qty,
                            r["price"],
                        )
                        st.experimental_rerun()

                if client and st.button(
                    f"🤖 STRATEGIA AI {r['symbol']}",
                    key=f"ai_{r['symbol']}_{idx}",
                ):
                    prompt = (
                        f"Analiza {r['symbol']}: "
                        f"cena {r['price']:.6f}, RSI {r['rsi']:.1f}, "
                        f"MACD {r['macd']:.4f}, Pivot {r['pivot']:.4f}, "
                        f"ATR {r['atr']:.4f}, SL {r['sl']:.6f}, TP {r['tp']:.6f}. "
                        "Podaj konkretny plan wejścia, wyjścia, zarządzania pozycją i ryzykiem "
                        "dla krótkoterminowego trade'u."
                    )
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                    )
                    st.markdown(
                        f"<div class='ai-strategy-box'>{res.choices[0].message.content}</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    "<div style='text-align:left; margin-top:20px;'>"
                    "<span class='t-lab'>OSTATNIE NEWSY:</span></div>",
                    unsafe_allow_html=True,
                )
                for n in r["news"]:
                    if n["link"]:
                        st.markdown(
                            f"<a class='news-link' href='{n['link']}' target='_blank'>● {n['title']}</a>",
                            unsafe_allow_html=True,
                        )

                st.markdown("</div>", unsafe_allow_html=True)

    # ==============================================================================
    # 7. PORTFEL – PODSUMOWANIE
    # ==============================================================================
    st.divider()
    st.subheader("💼 PORTFEL REAL (PLN)")

    df_pos, df_agg, total_invested, total_value = compute_portfolio_metrics(
        portfolio, price_map
    )
    total_pl = total_value - total_invested

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Zainwestowane", f"{total_invested:,.2f} PLN")
    with c2:
        st.metric("Wartość bieżąca", f"{total_value:,.2f} PLN")
    with c3:
        st.metric(
            "P/L łączny",
            f"{total_pl:,.2f} PLN",
            delta=f"{total_pl:,.2f} PLN",
        )

    st.markdown("### Otwarte pozycje (zagregowane)")
    if df_agg is not None and not df_agg.empty:
        st.dataframe(
            df_agg.style.format(
                {
                    "qty": "{:,.2f}",
                    "entry_price": "{:,.4f}",
                    "current_price": "{:,.4f}",
                    "invested": "{:,.2f}",
                    "value": "{:,.2f}",
                    "pl": "{:,.2f}",
                }
            ),
            use_container_width=True,
        )
    else:
        st.info("Brak otwartych pozycji.")

    st.markdown("### Wszystkie pozycje (historia)")
    if not df_pos.empty:
        st.dataframe(
            df_pos.style.format(
                {
                    "qty": "{:,.2f}",
                    "entry_price": "{:,.4f}",
                    "current_price": "{:,.4f}",
                    "invested": "{:,.2f}",
                    "value": "{:,.2f}",
                    "pl": "{:,.2f}",
                }
            ),
            use_container_width=True,
        )
    else:
        st.info("Brak pozycji w portfelu.")

st.markdown(
    "<center><small style='color:#333;'>AI ALPHA MONSTER PRO v71 ULTRA © 2026 | "
    "Auto-refresh: 1–10 min</small></center>",
    unsafe_allow_html=True,
)

