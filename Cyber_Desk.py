import re
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ============================================================
#   CYBER‑DESK PRO ULTRA v3
# ============================================================

st.set_page_config(
    page_title="CYBER‑DESK PRO ULTRA v3",
    page_icon="💠",
    layout="wide",
)

# ============================================================
#   GLOBAL NEON THEME
# ============================================================

st.markdown("""
<style>
body, .stApp {
    background-color: #050816;
    color: #E5E7EB;
    font-family: 'Inter', sans-serif;
}

/* NAV TITLE */
.nav-title {
    font-size: 1.4rem;
    font-weight: 700;
    color: #38bdf8;
}

/* NEON BOXES */
.neon-box {
    border-radius: 12px;
    padding: 14px 18px;
    border: 1px solid rgba(56,189,248,0.4);
    background: radial-gradient(circle at top left, rgba(56,189,248,0.12), rgba(15,23,42,0.95));
}
.neon-box-yellow {
    border-radius: 12px;
    padding: 14px 18px;
    border: 1px solid rgba(250,204,21,0.6);
    background: radial-gradient(circle at top left, rgba(250,204,21,0.12), rgba(15,23,42,0.95));
}
.neon-title {
    font-weight: 700;
    color: #e5e7eb;
}
.neon-sub {
    font-size: 0.9rem;
    color: #9ca3af;
}

/* SIGNAL COLORS */
.signal-buy { color: #22c55e; font-weight: 700; }
.signal-sell { color: #f97316; font-weight: 700; }
.signal-hold { color: #e5e7eb; font-weight: 700; }

/* BADGES */
.score-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.85rem;
    background: rgba(56,189,248,0.12);
    border: 1px solid rgba(56,189,248,0.6);
    color: #e5e7eb;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
#   SESSION STATE
# ============================================================

if "mode" not in st.session_state:
    st.session_state.mode = "AI"

# ============================================================
#   NAVBAR
# ============================================================

col_nav1, col_nav2 = st.columns([3, 2])
with col_nav1:
    st.markdown('<div class="nav-title">💠 CYBER‑DESK PRO ULTRA v3</div>', unsafe_allow_html=True)
with col_nav2:
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🤖 Czat AI", key="nav_ai", use_container_width=True):
            st.session_state.mode = "AI"
    with c2:
        if st.button("📈 Kombajn Tradingowy", key="nav_trading", use_container_width=True):
            st.session_state.mode = "TRADING"

# ============================================================
#   HELPERS
# ============================================================

def to_scalar(x):
    if isinstance(x, (pd.Series, np.ndarray, list)):
        if len(x) == 0:
            return np.nan
        try:
            return float(np.asarray(x).ravel()[-1])
        except Exception:
            return np.nan
    try:
        return float(x)
    except Exception:
        return np.nan

# ============================================================
#   AI ENGINE — TAVILY + TICKER ANALYSIS
# ============================================================

TAVILY_KEY = st.secrets.get("TAVILY_API_KEY", "")

def tavily_search(query: str, n=5):
    if not TAVILY_KEY:
        return []
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": query, "n_tokens": 2048, "num_results": n},
            timeout=10,
        )
        data = r.json()
        return data.get("results", [])
    except Exception:
        return []

def detect_ticker(text: str):
    pattern = r"\b[A-Z0-9]{2,6}(?:\.[A-Z]{2,3}|-[A-Z]{2,4}|USD)?\b"
    m = re.findall(pattern, text.upper())
    return m[0] if m else None

def ai_analyze_ticker(ticker: str):
    try:
        df = yf.download(ticker, period="6mo", interval="1d")
        if df.empty:
            return None, "Brak danych dla tego tickera."

        close = df["Close"]

        price_raw = close.iloc[-1]
        price = float(price_raw.values[0]) if hasattr(price_raw, "values") else float(price_raw)

        rsi_raw = close.pct_change().rolling(14).std().iloc[-1] * 100
        rsi = float(rsi_raw.values[0]) if hasattr(rsi_raw, "values") else float(rsi_raw)

        ma20_raw = close.rolling(20).mean().iloc[-1]
        ma20 = float(ma20_raw.values[0]) if hasattr(ma20_raw, "values") else float(ma20_raw)

        trend = "Uptrend" if price > ma20 else "Downtrend"

        return {
            "price": price,
            "rsi": rsi,
            "ma20": ma20,
            "trend": trend,
        }, None
    except Exception as e:
        return None, str(e)

def ai_generate_response(user_msg: str):
    ticker = detect_ticker(user_msg)

    ticker_block = ""
    if ticker:
        data, err = ai_analyze_ticker(ticker)
        if data:
            ticker_block = (
                f"**Ticker wykryty:** {ticker}\n"
                f"- Cena: {data['price']:.2f}\n"
                f"- RSI‑proxy: {data['rsi']:.2f}\n"
                f"- MA20: {data['ma20']:.2f}\n"
                f"- Trend: {data['trend']}\n"
            )
        else:
            ticker_block = f"Nie udało się pobrać danych dla {ticker}: {err}\n"

    news_block = ""
    if ticker:
        t = yf.Ticker(ticker)
        news = t.news if hasattr(t, "news") else []
        titles = [n.get("title", "") for n in news][:5]
        if titles:
            news_block = "**Ostatnie newsy:**\n" + "\n".join(f"- {t}" for t in titles)

    tav = tavily_search(user_msg, n=4)
    tav_block = ""
    if tav:
        tav_block = "**Wyniki z internetu:**\n" + "\n".join(
            f"- {item.get('title', '')}" for item in tav
        )

    final = "### 🤖 Odpowiedź AI\n"
    if ticker_block:
        final += "\n#### 📈 Analiza wykrytego tickera\n" + ticker_block + "\n"
    if news_block:
        final += "\n#### 📰 Newsy rynkowe\n" + news_block + "\n"
    if tav_block:
        final += "\n#### 🌐 Internet (Tavily)\n" + tav_block + "\n"

    final += "\n---\n### 💬 Komentarz AI\n"
    final += (
        "Twoja wiadomość została przeanalizowana. "
        "Jeśli chcesz głębszą analizę techniczną, napisz: *analiza techniczna TICKER*."
    )
    return final

def render_ai_chat():
    st.markdown("## 🤖 Czat AI — Internet + Trading Engine")
    user_msg = st.text_area("Wpisz wiadomość:", "", height=120)
    if st.button("Wyślij", use_container_width=True):
        if not user_msg.strip():
            st.warning("Wpisz wiadomość.")
            return
        with st.spinner("AI analizuje..."):
            time.sleep(0.3)
            out = ai_generate_response(user_msg)
        st.markdown(out)

# ============================================================
#   TRADING ENGINE — INDICATORS / SCORE / SIGNAL / RISK
# ============================================================
def compute_indicators(close, volume):
    close = close.copy()

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.dropna()
    last_rsi = to_scalar(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

    # MA10 / MA30
    ma_fast_series = close.rolling(10).mean().dropna()
    ma_slow_series = close.rolling(30).mean().dropna()
    last_ma_fast = to_scalar(ma_fast_series.iloc[-1]) if not ma_fast_series.empty else np.nan
    last_ma_slow = to_scalar(ma_slow_series.iloc[-1]) if not ma_slow_series.empty else np.nan

    # Bollinger Bands
    ma_bb = close.rolling(20).mean()
    std_bb = close.rolling(20).std()
    upper_bb = ma_bb + 2 * std_bb
    lower_bb = ma_bb - 2 * std_bb
    last_upper_bb = to_scalar(upper_bb.iloc[-1]) if not upper_bb.dropna().empty else np.nan
    last_lower_bb = to_scalar(lower_bb.iloc[-1]) if not lower_bb.dropna().empty else np.nan

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_series = ema12 - ema26
    macd_signal_series = macd_series.ewm(span=9, adjust=False).mean()
    macd_hist_series = macd_series - macd_signal_series

    # Volatility
    vol_series = close.pct_change().rolling(20).std().dropna()
    last_vol = to_scalar(vol_series.iloc[-1]) if not vol_series.empty else np.nan

    # Volume
    last_volume = to_scalar(volume.iloc[-1]) if not volume.empty else np.nan

    # SL / TP
    sl_level = last_lower_bb
    tp_level = last_upper_bb

    # Trend
    if not np.isnan(last_ma_fast) and not np.isnan(last_ma_slow):
        if last_ma_fast > last_ma_slow:
            trend = "Uptrend"
        elif last_ma_fast < last_ma_slow:
            trend = "Downtrend"
        else:
            trend = "Sideways"
    else:
        trend = "Unknown"

    return {
        "rsi": last_rsi,
        "ma_fast": last_ma_fast,
        "ma_slow": last_ma_slow,
        "upper_bb": upper_bb,
        "lower_bb": lower_bb,
        "last_upper_bb": last_upper_bb,
        "last_lower_bb": last_lower_bb,
        "macd": macd_series,
        "macd_signal": macd_signal_series,
        "macd_hist": macd_hist_series,
        "vol": last_vol,
        "volume": last_volume,
        "sl": sl_level,
        "tp": tp_level,
        "trend": trend,
    }


def compute_score(price, ind):
    score = 50
    details = []

    rsi = ind["rsi"]
    trend = ind["trend"]
    vol = ind["vol"]
    sl = ind["sl"]
    tp = ind["tp"]

    # --- RSI ---
    if not np.isnan(rsi):
        if rsi < 25:
            score += 25
            details.append("RSI < 25 → silne wyprzedanie → +25.")
        elif rsi > 75:
            score -= 25
            details.append("RSI > 75 → silne wykupienie → -25.")
        elif 35 <= rsi <= 65:
            score += 10
            details.append("RSI w strefie równowagi → +10.")
        else:
            details.append("RSI neutralne → 0.")

    # --- TREND ---
    if trend == "Uptrend":
        score += 15
        details.append("MA10 > MA30 → trend wzrostowy → +15.")
    elif trend == "Downtrend":
        score -= 15
        details.append("MA10 < MA30 → trend spadkowy → -15.")
    else:
        details.append("Trend nieznany → 0.")

    # --- ZMIENNOŚĆ ---
    if not np.isnan(vol):
        if vol < 0.01:
            score -= 5
            details.append("Bardzo niska zmienność → -5.")
        elif vol > 0.06:
            score -= 5
            details.append("Bardzo wysoka zmienność → -5.")
        else:
            score += 5
            details.append("Umiarkowana zmienność → +5.")

    # --- BOLLINGER ---
    if not np.isnan(price) and not np.isnan(sl) and not np.isnan(tp) and tp != sl:
        rel = (price - sl) / (tp - sl)
        if rel < 0.1:
            score += 10
            details.append("Cena przy dolnym BB → +10.")
        elif rel > 0.9:
            score -= 10
            details.append("Cena przy górnym BB → -10.")
        elif 0.3 <= rel <= 0.7:
            score += 15
            details.append("Cena w środku kanału → +15.")

    score = max(0, min(100, score))

    if score >= 80:
        label = "Silny setup"
    elif score >= 65:
        label = "Dobry setup"
    elif score >= 45:
        label = "Neutralny"
    elif score >= 30:
        label = "Słaby setup"
    else:
        label = "Ryzykowny setup"

    return score, label, details

def compute_risk_summary(price, sl, tp):
    if any(np.isnan(x) for x in [price, sl, tp]) or price == 0:
        return None
    risk_pct = (price - sl) / price * 100
    reward_pct = (tp - price) / price * 100
    rr = reward_pct / abs(risk_pct) if risk_pct > 0 else np.nan
    return {
        "risk_pct": risk_pct,
        "reward_pct": reward_pct,
        "rr": rr,
    }

def generate_signal(price, ind):
    rsi = ind["rsi"]
    trend = ind["trend"]
    sl = ind["sl"]
    tp = ind["tp"]
    vol = ind["vol"]

    if np.isnan(rsi):
        return "STOP", "Za mało danych (brak RSI)."

    reasons = []

    # --- BUY ---
    if rsi < 25:
        reasons.append("RSI < 25 → silne wyprzedanie.")
        if trend in ["Uptrend", "Unknown"]:
            return "BUY", "\n".join(["- " + r for r in reasons])

    # --- SELL ---
    if rsi > 75:
        reasons.append("RSI > 75 → silne wykupienie.")
        if trend in ["Downtrend", "Unknown"]:
            return "SELL", "\n".join(["- " + r for r in reasons])

    # --- HOLD ---
    reasons.append("Brak jednoznacznego edge → HOLD.")
    return "HOLD", "\n".join(["- " + r for r in reasons])

# ============================================================
#   CHARTS — MAIN + MINI (ULTRA‑COMPACT)
# ============================================================

def render_main_chart(ticker, data, ind, price):
    close = data["Close"]
    open_ = data["Open"]
    high = data["High"]
    low = data["Low"]

    height = 300
    margin = dict(l=8, r=8, t=28, b=8)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=open_,
        high=high,
        low=low,
        close=close,
        name="Świece",
        increasing_line_color="#22c55e",
        decreasing_line_color="#f97316",
    ))
    fig.add_trace(go.Scatter(
        x=data.index, y=ind["upper_bb"],
        line=dict(color="rgba(34,197,94,0.6)", width=1),
        name="Bollinger górna",
    ))
    fig.add_trace(go.Scatter(
        x=data.index, y=ind["lower_bb"],
        line=dict(color="rgba(239,68,68,0.6)", width=1),
        name="Bollinger dolna",
    ))

    fig.update_layout(
        height=height,
        margin=margin,
        plot_bgcolor="#020617",
        paper_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        xaxis=dict(
            gridcolor="#1f2937",
            rangebreaks=[dict(bounds=["sat", "mon"])],
            showticklabels=False,
        ),
        yaxis=dict(
            gridcolor="#1f2937",
            fixedrange=False,
            showticklabels=False,
        ),
        title=f"{ticker} — świece",
    )
    st.plotly_chart(fig, use_container_width=True)

def render_mini_charts(close, ind):
    height = 110
    margin = dict(l=5, r=5, t=20, b=5)

    st.markdown("### 📉 Mini‑wykresy")

    mini_close = close.tail(60)
    fig_spark = go.Figure()
    fig_spark.add_trace(go.Scatter(
        x=mini_close.index, y=mini_close.values,
        mode="lines", line=dict(color="#22c55e", width=2),
    ))
    fig_spark.update_layout(
        height=height,
        margin=margin,
        plot_bgcolor="#020617",
        paper_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=False),
        title="Sparkline",
    )
    st.plotly_chart(fig_spark, use_container_width=True)

    macd = ind["macd"].tail(60)
    macd_sig = ind["macd_signal"].tail(60)
    fig_macd = go.Figure()
    fig_macd.add_trace(go.Scatter(
        x=macd.index, y=macd.values,
        mode="lines", line=dict(color="#38bdf8", width=2),
    ))
    fig_macd.add_trace(go.Scatter(
        x=macd_sig.index, y=macd_sig.values,
        mode="lines", line=dict(color="#facc15", width=1),
    ))
    fig_macd.update_layout(
        height=height,
        margin=margin,
        plot_bgcolor="#020617",
        paper_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=False),
        title="Mini‑MACD",
    )
    st.plotly_chart(fig_macd, use_container_width=True)

    rsi_proxy = close.pct_change().rolling(14).std().dropna().tail(60) * 100
    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(
        x=rsi_proxy.index, y=rsi_proxy.values,
        mode="lines", line=dict(color="#f97316", width=2),
    ))
    fig_rsi.update_layout(
        height=height,
        margin=margin,
        plot_bgcolor="#020617",
        paper_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=False),
        title="Mini‑RSI",
    )
    st.plotly_chart(fig_rsi, use_container_width=True)

# ============================================================
#   MAKRO / HEATMAPA / MULTI‑TICKER / MONITOR
# ============================================================

def fetch_macro_and_sectors():
    tickers_macro = ["SPY", "QQQ", "IWM", "^VIX", "^TNX"]
    tickers_sectors = ["XLF", "XLK", "XLE", "XLY", "XLP", "XLV"]

    macro_data = {}
    sector_data = {}

    try:
        df_macro = yf.download(tickers_macro, period="5d", interval="1d", group_by="ticker", auto_adjust=True)
        for t in tickers_macro:
            try:
                close = df_macro[t]["Close"].dropna()
                if len(close) >= 2:
                    chg = (close.iloc[-1] / close.iloc[-2] - 1) * 100
                    macro_data[t] = chg
            except Exception:
                continue
    except Exception:
        pass

    try:
        df_sec = yf.download(tickers_sectors, period="5d", interval="1d", group_by="ticker", auto_adjust=True)
        for t in tickers_sectors:
            try:
                close = df_sec[t]["Close"].dropna()
                if len(close) >= 2:
                    chg = (close.iloc[-1] / close.iloc[-2] - 1) * 100
                    sector_data[t] = chg
            except Exception:
                continue
    except Exception:
        pass

    return macro_data, sector_data

def render_multi_ticker(multi_tickers):
    st.markdown("### 📚 Szybki przegląd wielu tickerów")
    tick_list = [t.strip() for t in multi_tickers.split(",") if t.strip()]
    if not tick_list:
        st.info("Wpisz tickery oddzielone przecinkami.")
        return
    cols = st.columns(min(4, len(tick_list)))
    for i, tck in enumerate(tick_list):
        col = cols[i % len(cols)]
        try:
            d = yf.download(tck, period="5d", interval="1d")
            if d.empty:
                col.write(f"**{tck}:** brak danych")
                continue
            close_mt = d["Close"]
            vol_mt = d["Volume"]
            price_mt = to_scalar(close_mt.iloc[-1])
            ind_mt = compute_indicators(close_mt, vol_mt)
            score_mt, label_mt, _ = compute_score(price_mt, ind_mt)
            color = "#22c55e" if score_mt >= 60 else "#f97316" if score_mt < 40 else "#e5e7eb"
            col.markdown(
                f"""
                <div class="neon-box">
                    <div class="neon-title">{tck}</div>
                    <div class="neon-sub">
                        Cena: {price_mt:.2f}<br/>
                        Scoring: <span style="color:{color};">{score_mt} – {label_mt}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception:
            col.write(f"**{tck}:** błąd danych")

def render_monitor(monitor_tickers, refresh_choice):
    st.markdown("### 🖥️ Monitor 5 spółek (auto‑odświeżanie)")
    if refresh_choice != "Brak":
        minutes = {
            "10 min": 10,
            "15 min": 15,
            "30 min": 30,
            "1 h": 60,
            "2 h": 120,
        }[refresh_choice]
        st.query_params.update({"refresh": str(minutes)})

    tick_list = [t.strip() for t in monitor_tickers.split(",") if t.strip()]
    tick_list = tick_list[:5]
    if not tick_list:
        st.info("Wpisz tickery do monitorowania.")
        return

    cols = st.columns(len(tick_list))
    for i, tck in enumerate(tick_list):
        col = cols[i]
        try:
            d = yf.download(tck, period="5d", interval="1d")
            if d.empty:
                col.write(f"**{tck}:** brak danych")
                continue
            close_mt = d["Close"]
            vol_mt = d["Volume"]
            price_mt = to_scalar(close_mt.iloc[-1])
            ind_mt = compute_indicators(close_mt, vol_mt)
            score_mt, label_mt, _ = compute_score(price_mt, ind_mt)
            color = "#22c55e" if score_mt >= 60 else "#f97316" if score_mt < 40 else "#e5e7eb"
            col.markdown(
                f"""
                <div class="neon-box-yellow">
                    <div class="neon-title">{tck}</div>
                    <div class="neon-sub">
                        Cena: {price_mt:.2f}<br/>
                        Scoring: <span style="color:{color};">{score_mt} – {label_mt}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception:
            col.write(f"**{tck}:** błąd danych")

def render_macro_and_heatmap():
    st.markdown("### 🌍 Makro — indeksy i rynek długu / zmienności")
    macro_data, sector_data = fetch_macro_and_sectors()
    if macro_data:
        col_m1, col_m2, col_m3 = st.columns(3)
        items = list(macro_data.items())
        for i, (t, chg) in enumerate(items):
            col = [col_m1, col_m2, col_m3][i % 3]
            color = "#22c55e" if chg >= 0 else "#f97316"
            col.markdown(
                f"""
                <div class="neon-box-yellow">
                    <div class="neon-title">{t}</div>
                    <div class="neon-sub">Zmiana d/d: <span style="color:{color};">{chg:+.2f}%</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.write("Brak danych makro.")

    st.markdown("---")
    st.markdown("### 🧊 Heatmapa sektorowa (ETF‑y sektorowe)")
    if sector_data:
        sectors = list(sector_data.keys())
        changes = list(sector_data.values())
        fig_h = px.imshow(
            [changes],
            labels=dict(x="Sektor", color="Zmiana %"),
            x=sectors,
            y=[""],
            color_continuous_scale="RdYlGn",
            aspect="auto",
        )
        fig_h.update_layout(
            height=220,
            plot_bgcolor="#020617",
            paper_bgcolor="#020617",
            font=dict(color="#e5e7eb"),
            coloraxis_colorbar=dict(title="%", tickformat="+.1f"),
        )
        st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.write("Brak danych sektorowych.")

# ============================================================
#   TRADING PANEL
# ============================================================

def render_trading():
    st.markdown("## 📈 Kombajn Tradingowy — ULTRA Panel")
    st.caption("Świece · Wskaźniki · Sygnały · Scoring · Ryzyko · Makro · Heatmapa · Multi‑Ticker · Monitor")

    ticker = st.text_input("Ticker (np. AAPL, MSFT, STX.WA):", "AAPL")

    col1, col2, col3 = st.columns(3)
    period = col1.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
    interval = col2.selectbox("Interwał:", ["1m", "5m", "15m", "30m", "1h", "1d"], index=5)
    multi_tickers = col3.text_input("Lista tickerów (oddzielone przecinkami):", "")

    st.markdown("---")
    mon_col1, mon_col2 = st.columns([2, 1])
    monitor_tickers = mon_col1.text_input("Tickery do monitorowania (max 5):", "", key="monitor_tickers")
    refresh_choice = mon_col2.selectbox(
        "Auto‑odświeżanie:",
        ["Brak", "10 min", "15 min", "30 min", "1 h", "2 h"],
        index=0,
    )

    if st.button("Pobierz dane i policz sygnały", use_container_width=True):
        try:
            data = yf.download(ticker, period=period, interval=interval)
            if data.empty:
                st.error("Brak danych dla tego tickera.")
                return

            if isinstance(data.columns, pd.MultiIndex):
                close = data["Close"].iloc[:, 0]
                open_ = data["Open"].iloc[:, 0]
                high = data["High"].iloc[:, 0]
                low = data["Low"].iloc[:, 0]
                volume = data["Volume"].iloc[:, 0]
            else:
                close = data["Close"]
                open_ = data["Open"]
                high = data["High"]
                low = data["Low"]
                volume = data["Volume"]

            ind = compute_indicators(close, volume)
            price = to_scalar(close.iloc[-1])

            tab_main, tab_mini, tab_macro = st.tabs(
                ["📊 Główny wykres + sygnał", "📉 Mini‑wykresy + scoring", "🌍 Makro + heatmapa"]
            )

            with tab_main:
                render_main_chart(ticker, data, ind, price)
                signal, explanation = generate_signal(price, ind)
                score, score_label, score_details = compute_score(price, ind)
                risk_summary = compute_risk_summary(price, ind["sl"], ind["tp"])

                if signal == "BUY":
                    sig_icon = "🟢⬆️"
                    sig_class = "signal-buy"
                elif signal == "SELL":
                    sig_icon = "🟠⬇️"
                    sig_class = "signal-sell"
                elif signal == "STOP":
                    sig_icon = "🔴⛔"
                    sig_class = "signal-sell"
                else:
                    sig_icon = "⚪⏸️"
                    sig_class = "signal-hold"

                st.markdown("### 🤖 AI Sygnał automatyczny")
                st.markdown(
                    f"""
                    <div class="neon-box">
                        <div class="neon-title">
                            {sig_icon} <span class="{sig_class}">Sygnał: {signal}</span>
                        </div>
                        <div class="neon-sub">
                            Ticker: <b>{ticker}</b><br/>
                            Cena: <b>{price:.2f}</b>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col_sig1, col_sig2 = st.columns(2)
                with col_sig1:
                    if not np.isnan(ind["rsi"]):
                        st.write(f"**RSI (14):** {ind['rsi']:.1f}")
                    st.write(f"**MA10:** {ind['ma_fast']:.2f}")
                    st.write(f"**MA30:** {ind['ma_slow']:.2f}")
                    st.write(f"**Trend:** {ind['trend']}")
                    st.write(f"**Zmienność (20):** {ind['vol']:.4f}")
                    st.write(f"**Wolumen:** {ind['volume']:.0f}")
                with col_sig2:
                    st.write(f"**SL:** {ind['sl']:.2f}")
                    st.write(f"**TP:** {ind['tp']:.2f}")
                    st.markdown(
                        f'<span class="score-badge">Scoring: {score}/100 – {score_label}</span>',
                        unsafe_allow_html=True,
                    )
                    if risk_summary:
                        st.write(
                            f"**Ryzyko:** {risk_summary['risk_pct']:+.1f}% | "
                            f"**Potencjał:** {risk_summary['reward_pct']:+.1f}%"
                        )
                        if not np.isnan(risk_summary["rr"]):
                            st.write(f"**R/R:** {risk_summary['rr']:.2f}")

                st.markdown("### Uzasadnienie sygnału")
                st.markdown(explanation)
                st.markdown("### Detale scoringu")
                for d in score_details:
                    st.markdown(f"- {d}")

            with tab_mini:
                render_mini_charts(close, ind)
                st.markdown("### 📊 Scoring 0–100")
                score, score_label, score_details = compute_score(price, ind)
                st.markdown(
                    f'<span class="score-badge">Scoring: {score}/100 – {score_label}</span>',
                    unsafe_allow_html=True,
                )
                for d in score_details:
                    st.markdown(f"- {d}")

            with tab_macro:
                render_macro_and_heatmap()

            if multi_tickers.strip():
                st.markdown("---")
                render_multi_ticker(multi_tickers)

        except Exception as e:
            st.error(f"Błąd: {e}")

    st.markdown("---")
    render_monitor(monitor_tickers, refresh_choice)

# ============================================================
#   ROUTING
# ============================================================

if st.session_state.mode == "AI":
    render_ai_chat()
else:
    render_trading()
