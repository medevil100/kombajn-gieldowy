import os
import re
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ---------------- CONFIG ----------------

st.set_page_config(page_title="CYBER DESK PRO", page_icon="💠", layout="wide")

# NEON THEME (global CSS)
st.markdown(
    """
    <style>
    body, .stApp {
        background-color: #050816;
        color: #E5E7EB;
    }
    .stSidebar, section[data-testid="stSidebar"] {
        background: radial-gradient(circle at top, #111827 0, #020617 55%, #000 100%);
        border-right: 1px solid #1F2937;
    }
    .stButton>button {
        background: linear-gradient(90deg, #06b6d4, #22c55e);
        color: #0b1120;
        border-radius: 999px;
        border: none;
        font-weight: 600;
    }
    .stButton>button:hover {
        box-shadow: 0 0 20px rgba(34,197,94,0.6);
        transform: translateY(-1px);
    }
    .neon-box {
        border-radius: 12px;
        padding: 12px 16px;
        border: 1px solid rgba(56,189,248,0.4);
        background: radial-gradient(circle at top left, rgba(56,189,248,0.12), rgba(15,23,42,0.95));
    }
    .neon-box-yellow {
        border-radius: 12px;
        padding: 12px 16px;
        border: 1px solid rgba(250,204,21,0.6);
        background: radial-gradient(circle at top left, rgba(250,204,21,0.12), rgba(15,23,42,0.95));
    }
    .neon-title {
        color: #e5e7eb;
        font-weight: 700;
    }
    .neon-sub {
        color: #9ca3af;
        font-size: 0.9rem;
    }
    .signal-buy {
        color: #22c55e;
        font-weight: 700;
    }
    .signal-sell {
        color: #f97316;
        font-weight: 700;
    }
    .signal-hold {
        color: #e5e7eb;
        font-weight: 700;
    }
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
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 💠 CYBER DESK PRO")
    st.caption("1 plik · Czat + Trading · GPT-4.1 + Tavily + yfinance")
    mode = st.radio("Tryb pracy:", ["🤖 Czat AI (internet + trading)", "📈 Kombajn tradingowy"])


# ---------------- POMOCNICZE ----------------

def detect_ticker_from_text(text: str):
    pattern = r"\b[A-Z0-9]{2,5}\.[A-Z]{2,3}\b"
    m = re.search(pattern, text)
    if m:
        return m.group(0)
    return None


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


# ---------------- MODUŁ 2: KOMBAJN TRADINGOWY ----------------

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

    # MA
    ma_fast_series = close.rolling(10).mean().dropna()
    ma_slow_series = close.rolling(30).mean().dropna()
    last_ma_fast = to_scalar(ma_fast_series.iloc[-1]) if not ma_fast_series.empty else np.nan
    last_ma_slow = to_scalar(ma_slow_series.iloc[-1]) if not ma_slow_series.empty else np.nan

    # Bollinger
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
    last_macd = to_scalar(macd_series.iloc[-1])
    last_macd_signal = to_scalar(macd_signal_series.iloc[-1])
    last_macd_hist = to_scalar(macd_hist_series.iloc[-1])

    # Volatility
    vol_series = close.pct_change().rolling(20).std().dropna()
    last_vol = to_scalar(vol_series.iloc[-1]) if not vol_series.empty else np.nan

    # Volume
    last_volume = to_scalar(volume.iloc[-1]) if not volume.empty else np.nan

    # SL/TP na bazie Bollinger (prosty model)
    sl_level = last_lower_bb
    tp_level = last_upper_bb

    # Trend (MA10 vs MA30)
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
        "last_macd": last_macd,
        "last_macd_signal": last_macd_signal,
        "last_macd_hist": last_macd_hist,
        "vol": last_vol,
        "volume": last_volume,
        "sl": sl_level,
        "tp": tp_level,
        "trend": trend,
    }


def compute_score(price, ind):
    """
    Prosty scoring 0–100:
    - RSI: preferujemy 35–65
    - Trend: uptrend +10, sideways +5, downtrend -10
    - Volatility: umiarkowana lepsza niż ekstremalna
    - Pozycja vs Bollinger: bliżej środka = lepiej
    """
    score = 50
    details = []

    rsi = ind["rsi"]
    trend = ind["trend"]
    vol = ind["vol"]
    sl = ind["sl"]
    tp = ind["tp"]

    # RSI
    if not np.isnan(rsi):
        if 35 <= rsi <= 65:
            score += 10
            details.append("RSI w strefie równowagi (35–65) → +10.")
        elif rsi < 30 or rsi > 70:
            score -= 10
            details.append("RSI w strefie skrajnej (<30 lub >70) → -10.")
        else:
            details.append("RSI neutralne → 0.")

    # Trend
    if trend == "Uptrend":
        score += 10
        details.append("Trend wzrostowy (MA10 > MA30) → +10.")
    elif trend == "Sideways":
        score += 5
        details.append("Trend boczny → +5.")
    elif trend == "Downtrend":
        score -= 10
        details.append("Trend spadkowy (MA10 < MA30) → -10.")
    else:
        details.append("Trend nieznany → 0.")

    # Volatility
    if not np.isnan(vol):
        if vol < 0.01:
            score -= 5
            details.append("Bardzo niska zmienność → -5 (mało ruchu).")
        elif vol > 0.05:
            score -= 5
            details.append("Bardzo wysoka zmienność → -5 (ryzyko).")
        else:
            score += 5
            details.append("Umiarkowana zmienność → +5.")

    # Pozycja vs Bollinger
    if not np.isnan(price) and not np.isnan(sl) and not np.isnan(tp) and tp != sl:
        rel = (price - sl) / (tp - sl)
        if 0.3 <= rel <= 0.7:
            score += 5
            details.append("Cena w środku kanału Bollingera → +5.")
        elif rel < 0.1 or rel > 0.9:
            score -= 5
            details.append("Cena przy skrajach kanału Bollingera → -5.")

    score = max(0, min(100, score))

    if score >= 70:
        label = "Silny setup"
    elif score >= 55:
        label = "Dobry setup"
    elif score >= 45:
        label = "Neutralny"
    elif score >= 30:
        label = "Słaby setup"
    else:
        label = "Ryzykowny setup"

    return score, label, details


def generate_signal(price, ind):
    rsi = ind["rsi"]
    ma_fast = ind["ma_fast"]
    ma_slow = ind["ma_slow"]
    vol = ind["vol"]
    sl = ind["sl"]
    tp = ind["tp"]
    trend = ind["trend"]

    if any(np.isnan(x) for x in [rsi, ma_fast, ma_slow]):
        return "HOLD", "Za mało danych do wygenerowania sygnału."

    reasons = []
    signal = "HOLD"

    # Trend
    if trend == "Uptrend":
        reasons.append("Trend wzrostowy (MA10 > MA30).")
    elif trend == "Downtrend":
        reasons.append("Trend spadkowy (MA10 < MA30).")
    else:
        reasons.append("Trend boczny / niejednoznaczny.")

    # RSI
    if rsi < 30:
        reasons.append("RSI < 30 → wyprzedanie.")
    elif rsi > 70:
        reasons.append("RSI > 70 → wykupienie.")
    else:
        reasons.append("RSI w strefie neutralnej.")

    # Prosty model sygnału
    if trend == "Uptrend" and rsi < 40:
        signal = "BUY"
        reasons.append("Trend wzrostowy + RSI < 40 → potencjalna akumulacja.")
    elif trend == "Downtrend" and rsi > 60:
        signal = "SELL"
        reasons.append("Trend spadkowy + RSI > 60 → potencjalna dystrybucja.")
    else:
        signal = "HOLD"
        reasons.append("Brak jednoznacznego sygnału – obserwacja.")

    # SL/TP info
    if not np.isnan(sl):
        reasons.append(f"Proponowany SL (Bollinger dolna): {sl:.2f}")
    if not np.isnan(tp):
        reasons.append(f"Proponowany TP (Bollinger górna): {tp:.2f}")
    if not np.isnan(vol):
        reasons.append(f"Zmienność (20): {vol:.4f}")

    return signal, "\n".join(f"- {r}" for r in reasons)


def fetch_news_sentiment(ticker):
    try:
        t = yf.Ticker(ticker)
        news = t.news if hasattr(t, "news") else []
    except Exception:
        news = []

    titles = [n.get("title", "") for n in news if isinstance(n.get("title", ""), str)]
    titles = [t for t in titles if t.strip()][:5]

    if not titles:
        return "Mixed", [], "Brak newsów."

    score = 0
    for title in titles:
        tl = title.lower()
        if any(w in tl for w in ["beat", "strong", "growth", "upgrade", "profit", "record"]):
            score += 1
        if any(w in tl for w in ["miss", "weak", "downgrade", "fall", "loss", "cut"]):
            score -= 1

    sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"
    return sentiment, titles, ""


def fetch_macro_and_sectors():
    """
    Prosty moduł makro + heatmapa sektorowa:
    - SPY, QQQ, IWM, ^VIX, ^TNX
    - ETF-y sektorowe: XLF, XLK, XLE, XLY, XLP, XLV
    """
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


def render_trading():
    st.title("📈 Kombajn tradingowy – pełny panel")
    st.caption("Świece, wskaźniki, sygnały, scoring, makro, heatmapa sektorowa.")

    ticker = st.text_input("Ticker (np. AAPL, MSFT, STX.WA):", "AAPL")

    col1, col2 = st.columns(2)
    period = col1.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
    interval = col2.selectbox("Interwał:", ["15m", "30m", "1h", "1d"], index=3)

    if st.button("Pobierz dane i policz sygnały", use_container_width=True):
        try:
            data = yf.download(ticker, period=period, interval=interval)
            if data.empty:
                st.error("Brak danych dla tego tickera lub interwału.")
                return

            # Obsługa ewentualnego MultiIndex w kolumnach
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

            # --- LAYOUT: 3 główne sekcje w zakładkach ---
            tab_main, tab_mini, tab_macro = st.tabs(
                ["📊 Główny wykres + sygnał", "📉 Mini‑wykresy + scoring", "🌍 Makro + heatmapa sektorowa"]
            )

            # --- TAB 1: GŁÓWNY WYKRES + SYGNAŁ ---
            with tab_main:
                fig = go.Figure()
                fig.add_trace(
                    go.Candlestick(
                        x=data.index,
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        name="Świece",
                        increasing_line_color="#22c55e",
                        decreasing_line_color="#f97316",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=data.index,
                        y=ind["upper_bb"],
                        line=dict(color="rgba(34,197,94,0.6)", width=1),
                        name="Bollinger górna",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=data.index,
                        y=ind["lower_bb"],
                        line=dict(color="rgba(239,68,68,0.6)", width=1),
                        name="Bollinger dolna",
                    )
                )
                fig.update_layout(
                    height=500,
                    title=f"Wykres {ticker}",
                    plot_bgcolor="#020617",
                    paper_bgcolor="#020617",
                    font=dict(color="#e5e7eb"),
                    xaxis=dict(gridcolor="#1f2937"),
                    yaxis=dict(gridcolor="#1f2937"),
                )
                st.plotly_chart(fig, use_container_width=True)

                signal, explanation = generate_signal(price, ind)
                score, score_label, score_details = compute_score(price, ind)

                # Ikonki strzałek + sygnał
                if signal == "BUY":
                    sig_icon = "🟢⬆️"
                    sig_class = "signal-buy"
                elif signal == "SELL":
                    sig_icon = "🟠⬇️"
                    sig_class = "signal-sell"
                else:
                    sig_icon = "⚪⏸️"
                    sig_class = "signal-hold"

                st.markdown("### 🤖 AI Sygnał automatyczny (engine)")
                st.markdown(
                    f"""
                    <div class="neon-box">
                        <div class="neon-title">
                            {sig_icon} <span class="{sig_class}">Sygnał: {signal}</span>
                        </div>
                        <div class="neon-sub">
                            Ticker: <b>{ticker}</b><br/>
                            Cena: <b>{price:.2f}</b> (jeśli dostępna)
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col_sig1, col_sig2 = st.columns(2)
                with col_sig1:
                    if not np.isnan(ind["rsi"]):
                        st.write(f"**RSI (14):** {ind['rsi']:.1f}")
                    if not np.isnan(ind["ma_fast"]) and not np.isnan(ind["ma_slow"]):
                        st.write(f"**MA10:** {ind['ma_fast']:.2f} | **MA30:** {ind['ma_slow']:.2f}")
                    st.write(f"**Trend:** {ind['trend']}")
                    if not np.isnan(ind["vol"]):
                        st.write(f"**Volatility (20):** {ind['vol']:.4f}")
                    if not np.isnan(ind["volume"]):
                        st.write(f"**Wolumen (ostatnia świeca):** {ind['volume']:.0f}")
                with col_sig2:
                    if not np.isnan(ind["sl"]):
                        st.write(f"**SL (Bollinger dolna):** {ind['sl']:.2f}")
                    if not np.isnan(ind["tp"]):
                        st.write(f"**TP (Bollinger górna):** {ind['tp']:.2f}")
                    st.markdown(
                        f'<span class="score-badge">Scoring: {score}/100 – {score_label}</span>',
                        unsafe_allow_html=True,
                    )

                st.markdown("**Uzasadnienie sygnału:**")
                st.markdown(explanation)

                st.markdown("**Detale scoringu:**")
                for d in score_details:
                    st.markdown(f"- {d}")

                # News sentiment
                st.markdown("---")
                st.subheader("📰 News sentiment (Yahoo Finance)")
                sentiment, titles, comment = fetch_news_sentiment(ticker)
                st.write(f"**Sentyment:** {sentiment}")
                if comment:
                    st.write(comment)
                if titles:
                    for t in titles:
                        st.markdown(f"- {t}")

            # --- TAB 2: MINI‑WYKRESY + SCORING ---
            with tab_mini:
                st.markdown("#### 📉 Mini‑wykresy (sparkline + MACD + RSI)")

                # Sparkline ceny
                mini_close = close.tail(60)
                fig_spark = go.Figure()
                fig_spark.add_trace(
                    go.Scatter(
                        x=mini_close.index,
                        y=mini_close.values,
                        mode="lines",
                        line=dict(color="#22c55e", width=2),
                        name="Cena",
                    )
                )
                fig_spark.update_layout(
                    height=180,
                    margin=dict(l=10, r=10, t=30, b=10),
                    plot_bgcolor="#020617",
                    paper_bgcolor="#020617",
                    font=dict(color="#e5e7eb"),
                    xaxis=dict(showgrid=False, showticklabels=False),
                    yaxis=dict(showgrid=False),
                    title="Sparkline ceny (ostatnie 60 świec)",
                )
                st.plotly_chart(fig_spark, use_container_width=True)

                # Mini MACD
                macd = ind["macd"].tail(60)
                macd_sig = ind["macd_signal"].tail(60)
                fig_macd = go.Figure()
                fig_macd.add_trace(
                    go.Scatter(
                        x=macd.index,
                        y=macd.values,
                        mode="lines",
                        line=dict(color="#38bdf8", width=2),
                        name="MACD",
                    )
                )
                fig_macd.add_trace(
                    go.Scatter(
                        x=macd_sig.index,
                        y=macd_sig.values,
                        mode="lines",
                        line=dict(color="#facc15", width=1),
                        name="Signal",
                    )
                )
                fig_macd.update_layout(
                    height=180,
                    margin=dict(l=10, r=10, t=30, b=10),
                    plot_bgcolor="#020617",
                    paper_bgcolor="#020617",
                    font=dict(color="#e5e7eb"),
                    xaxis=dict(showgrid=False, showticklabels=False),
                    yaxis=dict(showgrid=True, gridcolor="#1f2937"),
                    title="Mini‑MACD (ostatnie 60 świec)",
                )
                st.plotly_chart(fig_macd, use_container_width=True)

                # Mini RSI
                rsi_series = close.pct_change().rolling(14).apply(
                    lambda x: 100 - (100 / (1 + (x[x > 0].mean() / (abs(x[x < 0]).mean() + 1e-9)))),
                    raw=False,
                )
                rsi_series = rsi_series.dropna().tail(60)
                fig_rsi = go.Figure()
                fig_rsi.add_trace(
                    go.Scatter(
                        x=rsi_series.index,
                        y=rsi_series.values,
                        mode="lines",
                        line=dict(color="#f97316", width=2),
                        name="RSI",
                    )
                )
                fig_rsi.add_hrect(y0=30, y1=70, fillcolor="rgba(148,163,184,0.15)", line_width=0)
                fig_rsi.update_layout(
                    height=180,
                    margin=dict(l=10, r=10, t=30, b=10),
                    plot_bgcolor="#020617",
                    paper_bgcolor="#020617",
                    font=dict(color="#e5e7eb"),
                    xaxis=dict(showgrid=False, showticklabels=False),
                    yaxis=dict(range=[0, 100], gridcolor="#1f2937"),
                    title="Mini‑RSI (ostatnie 60 świec)",
                )
                st.plotly_chart(fig_rsi, use_container_width=True)

                st.markdown("#### 📊 Scoring 0–100")
                score, score_label, score_details = compute_score(price, ind)
                st.markdown(
                    f'<span class="score-badge">Scoring: {score}/100 – {score_label}</span>',
                    unsafe_allow_html=True,
                )
                for d in score_details:
                    st.markdown(f"- {d}")

            # --- TAB 3: MAKRO + HEATMAPA SEKTOROWA ---
            with tab_macro:
                st.markdown("#### 🌍 Makro – indeksy i rynek długu / zmienności")
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
                    st.write("Brak danych makro (SPY/QQQ/IWM/VIX/TNX).")

                st.markdown("---")
                st.markdown("#### 🧊 Heatmapa sektorowa (ETF‑y sektorowe)")

                if sector_data:
                    sectors = list(sector_data.keys())
                    changes = list(sector_data.values())
                    df_heat = pd.DataFrame({"Sektor": sectors, "Zmiana": changes})
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
                    st.write("Brak danych sektorowych (XLF/XLK/XLE/XLY/XLP/XLV).")

            # Zapis analizy do czatu
            st.session_state["last_analysis"] = {
                "ticker": ticker,
                "price": price,
                "indicators": ind,
                "signal": signal,
                "explanation": explanation,
                "sentiment": sentiment,
                "news_titles": titles,
                "period": period,
                "interval": interval,
                "score": score,
                "score_label": score_label,
            }

            st.success("Analiza zapisana – czat AI będzie korzystał z tych danych (zero zgadywania).")

        except Exception as e:
            st.error(f"Błąd: {e}")


# ---------------- MODUŁ 1: CZAT AI (GPT-4.1 + TAVILY + TRADING ENGINE) ----------------

def render_ai_chat():
    st.title("🤖 Czat AI – Analityk finansowy (GPT-4.1 + Tavily + Trading Engine)")
    st.caption("Zero zgadywania: tylko dane z trading engine + Tavily (finance/news).")

    if "OPENAI_API_KEY" not in st.secrets:
        st.error("Brak OPENAI_API_KEY w .streamlit/secrets.toml")
        return
    if "TAVILY_API_KEY" not in st.secrets:
        st.error("Brak TAVILY_API_KEY w .streamlit/secrets.toml")
        return

    openai_key = st.secrets["OPENAI_API_KEY"]
    tavily_key = st.secrets["TAVILY_API_KEY"]

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.markdown("### Historia rozmowy")
    for sender, msg in st.session_state.chat_history:
        st.markdown(f"**{sender}:** {msg}")

    user_input = st.text_input("Twoja wiadomość:")

    col_send, col_clear = st.columns([3, 1])
    send = col_send.button("Wyślij")
    clear = col_clear.button("Wyczyść czat")

    if clear:
        st.session_state.chat_history = []
        st.rerun()

    if not send or not user_input.strip():
        return

    question = user_input.strip()
    st.session_state.chat_history.append(("Ty", question))

    # Auto-wykrywanie tickera z pytania lub z ostatniej analizy
    ticker = detect_ticker_from_text(question)
    if not ticker and "last_analysis" in st.session_state:
        ticker = st.session_state["last_analysis"].get("ticker")

    # Dane z trading engine (jeśli są)
    trading_data = st.session_state.get("last_analysis", None)

    trading_summary = "Brak danych z Trading Engine."
    if trading_data:
        ind = trading_data["indicators"]
        lines = [
            f"Ticker: {trading_data['ticker']}",
        ]
        if not np.isnan(trading_data["price"]):
            lines.append(f"Cena: {trading_data['price']:.2f}")
        lines.append(f"Sygnał engine: {trading_data['signal']}")
        if not np.isnan(ind["rsi"]):
            lines.append(f"RSI(14): {ind['rsi']:.1f}")
        if not np.isnan(ind["ma_fast"]) and not np.isnan(ind["ma_slow"]):
            lines.append(f"MA10: {ind['ma_fast']:.2f}, MA30: {ind['ma_slow']:.2f}")
        lines.append(f"Trend: {ind['trend']}")
        if not np.isnan(ind["vol"]):
            lines.append(f"Volatility(20): {ind['vol']:.4f}")
        if not np.isnan(ind["volume"]):
            lines.append(f"Wolumen (ostatnia świeca): {ind['volume']:.0f}")
        if not np.isnan(ind["sl"]):
            lines.append(f"SL (Bollinger dolna): {ind['sl']:.2f}")
        if not np.isnan(ind["tp"]):
            lines.append(f"TP (Bollinger górna): {ind['tp']:.2f}")
        lines.append(f"Sentyment newsów (Yahoo): {trading_data['sentiment']}")
        if "score" in trading_data:
            lines.append(f"Scoring: {trading_data['score']}/100 – {trading_data['score_label']}")
        trading_summary = "\n".join(lines)

    # --- 1) Research Tavily (fundamenty + newsy) ---
    try:
        tavily_query = question
        if ticker:
            tavily_query = f"{ticker} stock fundamentals, dividend, outlook, 2026"

        tavily_resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {tavily_key}"},
            json={
                "query": tavily_query,
                "topic": "finance",
                "max_results": 8,
                "include_answer": True,
                "include_raw_content": False,
            },
            timeout=20,
        )
        tavily_resp.raise_for_status()
        tavily_json = tavily_resp.json()

        answer = tavily_json.get("answer", "")
        results = tavily_json.get("results", [])

        bullets = []
        for item in results:
            title = item.get("title", "")
            url = item.get("url", "")
            if title or url:
                bullets.append(f"- {title} ({url})")

        research_text = ""
        if answer:
            research_text += f"Podsumowanie Tavily:\n{answer}\n\n"
        if bullets:
            research_text += "Źródła Tavily:\n" + "\n".join(bullets)
        if not research_text:
            research_text = "Brak istotnych wyników finansowych z Tavily."
    except Exception as e:
        research_text = f"[Błąd Tavily] {e}"

    # --- 2) Odpowiedź GPT-4.1 z trybem „zero halucynacji” ---
    try:
        system_prompt = (
            "Jesteś profesjonalnym analitykiem finansowym w terminalu tradingowym.\n"
            "Masz dwa źródła danych:\n"
            "1) Trading Engine (yfinance) – twarde dane: cena, RSI, MA, Bollinger, MACD, wolumen, SL/TP, trend, sentyment newsów, scoring.\n"
            "2) Tavily (topic=finance/news) – kontekst rynkowy, newsy, raporty, fundamenty.\n\n"
            "Zasady ZERO HALUCYNACJI:\n"
            "- Jeśli nie masz danych → NIE ZGADUJ.\n"
            "- Jeśli ticker nieznany → NIE ZGADUJ.\n"
            "- Jeśli branża nieznana → NIE ZGADUJ.\n"
            "- Jeśli Tavily nie zwróciło wyników → powiedz to wprost.\n"
            "- Jeśli Trading Engine nie zwrócił danych → powiedz to wprost.\n"
            "- Odpowiadasz TYLKO na podstawie danych z trading engine i Tavily.\n"
            "- NIE wolno Ci wymyślać wyników finansowych, branży, danych historycznych ani prognoz.\n"
            "- Jeśli dane są niepełne → podaj scenariusze warunkowe.\n"
            "- Jeśli Tavily zwróciło newsy → uwzględnij je w analizie.\n"
            "- Jeśli Trading Engine zwrócił wskaźniki → uwzględnij je w analizie technicznej.\n"
            "- Jeśli nie możesz odpowiedzieć bez zgadywania → powiedz wprost, że brak danych.\n"
            "Odpowiadasz po polsku, konkretnie, jak analityk biura maklerskiego."
        )

        gpt_resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_key}"},
            json={
                "model": "gpt-4.1",
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "system",
                        "content": f"Dane z Trading Engine:\n{trading_summary}",
                    },
                    {
                        "role": "system",
                        "content": f"Research z Tavily (topic=finance/news):\n{research_text}",
                    },
                    *[
                        {
                            "role": "user" if s == "Ty" else "assistant",
                            "content": c,
                        }
                        for s, c in st.session_state.chat_history
                    ],
                ],
                "temperature": 0.1,
            },
            timeout=20,
        )
        gpt_resp.raise_for_status()
        gpt_json = gpt_resp.json()
        ai_msg = gpt_json["choices"][0]["message"]["content"]
    except Exception as e:
        ai_msg = f"[Błąd GPT] {e}"

    st.session_state.chat_history.append(("AI", ai_msg))
    st.rerun()


# ---------------- ROUTING ----------------

if mode == "🤖 Czat AI (internet + trading)":
    render_ai_chat()
else:
    render_trading()
