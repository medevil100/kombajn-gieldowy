import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import numpy as np
import json
# =========================================================
# CZYTELNOŚĆ V3 – KOMPONENTY UI
# =========================================================

def badge(text, color):
    return f"<span style='background-color:{color}; padding:4px 8px; border-radius:6px; color:white; font-size:0.85rem;'>{text}</span>"

def score_bar(score):
    pct = max(0, min(100, score))
    color = "#10b981" if pct >= 70 else "#f59e0b" if pct >= 50 else "#ef4444"
    return f"""
    <div style='width:100%; background:#1f2937; border-radius:6px; height:12px; margin:6px 0;'>
        <div style='width:{pct}%; background:{color}; height:12px; border-radius:6px;'></div>
    </div>
    """

def trend_icon(trend):
    if trend == "UP":
        return "📈"
    elif trend == "DOWN":
        return "📉"
    return "➖"

def highlight_value(label, value, good_range=None, bad_range=None):
    try:
        v = float(value)
    except:
        return f"{label}: {value}"

    color = "white"
    if good_range and good_range[0] <= v <= good_range[1]:
        color = "#10b981"
    if bad_range and (v < bad_range[0] or v > bad_range[1]):
        color = "#ef4444"

    return f"<span style='color:{color}; font-weight:600;'>{label}: {value}</span>"

def section_title(text):
    return f"<h3 style='margin-top:25px; color:#e5e7eb;'>{text}</h3>"

def mini_metric(label, value):
    return f"""
    <div style='padding:10px; background:#111827; border-radius:8px; margin-bottom:6px;'>
        <div style='color:#9ca3af; font-size:0.8rem;'>{label}</div>
        <div style='color:white; font-size:1.1rem; font-weight:600;'>{value}</div>
    </div>
    """

def opportunity_badge(opportunity):
    if opportunity == "OKAZJA":
        return badge("OKAZJA", "#10b981")
    elif opportunity == "ŚREDNIE":
        return badge("ŚREDNIE", "#f59e0b")
    return badge("UNIKAJ", "#ef4444")

def entry_box(levels):
    return f"""
    <div style='padding:12px; background:#1f2937; border-radius:10px; margin-top:10px;'>
        <div style='color:#9ca3af; font-size:0.8rem;'>Poziomy wejścia</div>
        <div style='color:white; font-size:1rem; font-weight:600;'>
            Entry: {fmt_num(levels['entry'],2)}<br>
            SL: {fmt_num(levels['sl'],2)}<br>
            TP1: {fmt_num(levels['tp1'],2)}<br>
            TP2: {fmt_num(levels['tp2'],2)}
        </div>
    </div>
    """

def fundamentals_box(metrics, dcf):
    pe = fmt_num(metrics.get("trailingPE"),2)
    price = fmt_num(metrics.get("currentPrice"),2)
    mc = fmt_num(metrics.get("marketCap"),0)

    if "error" in dcf:
        dcf_text = f"<span style='color:#ef4444;'>DCF: {dcf['error']}</span>"
    else:
        dcf_text = f"""
        Wartość wewnętrzna: {fmt_num(dcf['intrinsic_value'],2)}<br>
        Upside: {fmt_num(dcf['upside'],2)}%<br>
        FCF: {dcf['latest_fcf']:,.0f} USD
        """

    return f"""
    <div style='padding:12px; background:#1f2937; border-radius:10px; margin-top:10px;'>
        <div style='color:#9ca3af; font-size:0.8rem;'>Fundamenty</div>
        <div style='color:white; font-size:1rem; font-weight:600;'>
            Cena: {price}<br>
            Market Cap: {mc}<br>
            P/E: {pe}<br><br>
            {dcf_text}
        </div>
    </div>
    """

def tech_box(ind):
    return f"""
    <div style='padding:12px; background:#1f2937; border-radius:10px; margin-top:10px;'>
        <div style='color:#9ca3af; font-size:0.8rem;'>Technika</div>
        <div style='color:white; font-size:1rem; font-weight:600;'>
            Trend: {trend_icon(ind['trend'])} {ind['trend']}<br>
            RSI: {fmt_num(ind['rsi'],2)}<br>
            MACD: {fmt_num(ind['macd'],4)}<br>
            RVOL: {fmt_num(ind['rvol_last'],2)}<br>
            ATR: {fmt_num(ind['atr'],2)}
        </div>
    </div>
    """

# =========================================================
# UTILS
# =========================================================

def fmt_num(val, digits=2):
    try:
        return f"{float(val):.{digits}f}"
    except:
        return "brak"

def clean_for_json(data):
    if data is None:
        return {}
    cleaned = {}
    for key, val in data.items():
        key_str = str(key)
        if isinstance(val, dict):
            inner = {}
            for k2, v2 in val.items():
                inner[str(k2)] = v2
            cleaned[key_str] = inner
        else:
            cleaned[key_str] = val
    return cleaned

# =========================================================
# DATA LOADERS
# =========================================================

def load_price_data(ticker: str, period: str = "6mo", interval: str = "1d"):
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)

    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Close"])

    return df

def fetch_fundamentals(ticker: str):
    out = {
        "_errors": [],
        "metrics": {},
        "profile": {},
        "income": {},
        "balance": {},
        "cash": {},
    }

    try:
        t = yf.Ticker(ticker)
        info = t.info
    except Exception as e:
        out["_errors"].append(f"Błąd pobierania info: {e}")
        return out

    out["metrics"]["currentPrice"] = info.get("currentPrice")
    out["metrics"]["marketCap"] = info.get("marketCap")
    out["metrics"]["trailingPE"] = info.get("trailingPE")

    out["profile"]["longName"] = info.get("longName")
    out["profile"]["sector"] = info.get("sector")
    out["profile"]["industry"] = info.get("industry")
    out["profile"]["longBusinessSummary"] = info.get("longBusinessSummary")

    try:
        out["income"] = t.financials.to_dict()
    except:
        out["_errors"].append("Brak income statement")

    try:
        out["balance"] = t.balance_sheet.to_dict()
    except:
        out["_errors"].append("Brak balance sheet")

    try:
        out["cash"] = t.cashflow.to_dict()
    except:
        out["_errors"].append("Brak cashflow")

    return out

# =========================================================
# TECHNICAL INDICATORS
# =========================================================

def compute_rsi(close, period=14):
    close = pd.Series(close).astype(float)
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    return rsi.fillna(50)

def compute_macd(close, fast=12, slow=26, signal=9):
    close = pd.Series(close).astype(float)

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()

    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()

    return macd, macd_signal

def compute_obv(close, volume):
    close = pd.Series(close).astype(float)
    volume = pd.Series(volume).astype(float)

    obv = [0]

    for i in range(1, len(close)):
        c_now = close.iloc[i]
        c_prev = close.iloc[i - 1]
        v_now = volume.iloc[i]

        if np.isnan(c_now) or np.isnan(c_prev) or np.isnan(v_now):
            obv.append(obv[-1])
            continue

        if c_now > c_prev:
            obv.append(obv[-1] + v_now)
        elif c_now < c_prev:
            obv.append(obv[-1] - v_now)
        else:
            obv.append(obv[-1])

    return pd.Series(obv, index=close.index)

def compute_rvol(volume, window=20):
    volume = pd.Series(volume).astype(float)
    avg_vol = volume.rolling(window=window).mean()
    rvol = volume / avg_vol
    return rvol.fillna(1)

def compute_indicators(df: pd.DataFrame):
    close = df["Close"]
    volume = df["Volume"]

    rsi = compute_rsi(close)
    macd, macd_signal = compute_macd(close)

    ma_fast = close.rolling(10).mean()
    ma_slow = close.rolling(30).mean()

    obv = compute_obv(close, volume)
    rvol = compute_rvol(volume)

    trend = "UP" if ma_fast.iloc[-1] > ma_slow.iloc[-1] else "DOWN"

    high = df["High"]
    low = df["Low"]
    prev_close = close.shift(1)

    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(14).mean().iloc[-1]

    ind = {
        "rsi": rsi.iloc[-1],
        "macd": macd.iloc[-1],
        "macd_signal": macd_signal.iloc[-1],
        "ma_fast": ma_fast.iloc[-1],
        "ma_slow": ma_slow.iloc[-1],
        "trend": trend,
        "obv_last": obv.iloc[-1],
        "rvol_last": rvol.iloc[-1],
        "atr": atr,
    }

    return ind, rsi, macd, macd_signal, ma_fast, ma_slow, obv, rvol

# =========================================================
# DCF MODEL
# =========================================================

def extract_latest_fcf(fund_data: dict):
    cash = fund_data.get("cash", {})
    if not cash:
        return None

    for col, series in cash.items():
        if not isinstance(series, dict):
            continue
        for row_name, val in series.items():
            if isinstance(row_name, str) and "free" in row_name.lower() and "cash" in row_name.lower():
                try:
                    return float(val)
                except:
                    continue

    return None

def calculate_dcf(fund_data: dict, wacc: float, growth_1_5: float, terminal_growth: float):
    metrics = fund_data.get("metrics", {})
    current_price = metrics.get("currentPrice")

    if not current_price:
        return {"error": "Brak ceny rynkowej"}

    fcf = extract_latest_fcf(fund_data)
    if not fcf or fcf <= 0:
        return {"error": "Brak dodatniego FCF"}

    try:
        fcf_list = [fcf * ((1 + growth_1_5) ** i) for i in range(1, 6)]
        disc_fcf = [fcf_list[i] / ((1 + wacc) ** (i + 1)) for i in range(5)]

        if terminal_growth >= wacc:
            return {"error": "Terminal growth >= WACC"}

        tv = fcf_list[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
        disc_tv = tv / ((1 + wacc) ** 5)

        equity_value = sum(disc_fcf) + disc_tv

        market_cap = metrics.get("marketCap")
        if market_cap and market_cap > 0:
            shares = market_cap / current_price
            intrinsic = equity_value / shares
        else:
            intrinsic = current_price

        upside = (intrinsic / current_price - 1) * 100

        return {
            "intrinsic_value": intrinsic,
            "current_price": current_price,
            "upside": upside,
            "latest_fcf": fcf,
        }

    except Exception as e:
        return {"error": f"Błąd DCF: {e}"}

# =========================================================
# SCORING: TECHNIKA 60 / FUNDAMENTY 40
# =========================================================

def compute_technical_score(ind: dict) -> float:
    score = 50.0

    if ind.get("trend") == "UP":
        score += 15
    elif ind.get("trend") == "DOWN":
        score -= 15

    rsi = ind.get("rsi", 50)
    if 40 <= rsi <= 60:
        score += 10
    elif rsi < 30 or rsi > 70:
        score -= 10

    macd = ind.get("macd", 0)
    macd_signal = ind.get("macd_signal", 0)
    if macd > macd_signal and ind.get("trend") == "UP":
        score += 10
    elif macd < macd_signal and ind.get("trend") == "DOWN":
        score += 10
    else:
        score -= 5

    rvol = ind.get("rvol_last", 1)
    if rvol > 1.2:
        score += 10
    elif rvol < 0.8:
        score -= 5

    atr = ind.get("atr", 0)
    if atr > 0:
        score -= 5

    return max(0.0, min(100.0, score))

def compute_fundamental_score(fund: dict, dcf: dict) -> float:
    score = 50.0
    metrics = fund.get("metrics", {})
    profile = fund.get("profile", {})

    pe = metrics.get("trailingPE")
    if pe is not None:
        try:
            pe = float(pe)
            if 8 <= pe <= 18:
                score += 10
            elif pe < 5 or pe > 30:
                score -= 10
        except:
            pass

    if "error" not in dcf:
        upside = dcf.get("upside", 0)
        if upside > 20:
            score += 15
        elif upside < -10:
            score -= 15

    if profile.get("longBusinessSummary"):
        score += 5

    return max(0.0, min(100.0, score))

def classify_opportunity(fused_score: float) -> str:
    if fused_score >= 70:
        return "OKAZJA"
    elif fused_score >= 50:
        return "ŚREDNIE"
    else:
        return "UNIKAJ"

# =========================================================
# ENTRY / SL / TP
# =========================================================

def suggest_levels(df: pd.DataFrame, ind: dict):
    last_price = df["Close"].iloc[-1]
    atr = ind.get("atr", None)

    if last_price is None or atr is None or atr <= 0:
        return None

    entry = last_price
    sl = last_price - 2 * atr
    tp1 = last_price + 2 * atr
    tp2 = last_price + 4 * atr

    return {
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
    }

# =========================================================
# RAPORT V3
# =========================================================

def generate_v3_report(ticker: str, ind: dict, fund: dict, dcf: dict, tech_score: float, fund_score: float, fused_score: float, opportunity: str, levels: dict | None):
    metrics = fund.get("metrics", {})
    profile = fund.get("profile", {})

    lines = []
    lines.append(f"### Adam Terminal V3 – Okazje + Wejścia dla {ticker}")
    lines.append("")
    lines.append(f"**Technical Score (60%):** {tech_score:.1f}/100")
    lines.append(f"**Fundamental Score (40%):** {fund_score:.1f}/100")
    lines.append(f"**Fused Score:** {fused_score:.1f}/100")
    lines.append(f"**Klasyfikacja okazji:** {opportunity}")
    lines.append("")
    lines.append("**Technika:**")
    lines.append(
        f"- Trend: {ind.get('trend', 'brak')} | RSI: {fmt_num(ind.get('rsi'), 2)} | "
        f"MACD: {fmt_num(ind.get('macd'), 4)} vs sygnał {fmt_num(ind.get('macd_signal'), 4)}"
    )
    lines.append(
        f"- MA10: {fmt_num(ind.get('ma_fast'), 2)} | MA30: {fmt_num(ind.get('ma_slow'), 2)} | "
        f"RVOL: {fmt_num(ind.get('rvol_last'), 2)} | ATR: {fmt_num(ind.get('atr'), 2)}"
    )
    lines.append("")
    lines.append("**Fundamenty:**")
    lines.append(
        f"- Cena: {fmt_num(metrics.get('currentPrice'), 2)} | "
        f"Market Cap: {fmt_num(metrics.get('marketCap'), 0)} | "
        f"P/E: {fmt_num(metrics.get('trailingPE'), 2)}"
    )
    if "error" in dcf:
        lines.append(f"- DCF: {dcf['error']}")
    else:
        lines.append(
            f"- DCF wartość wewnętrzna: {fmt_num(dcf.get('intrinsic_value'), 2)} vs cena "
            f"{fmt_num(dcf.get('current_price'), 2)} | Upside: {fmt_num(dcf.get('upside'), 2)}%"
        )
        lines.append(f"- FCF użyty: {dcf.get('latest_fcf', 0):,.0f} USD")
    lines.append(f"- Spółka: {profile.get('longName', ticker)} | Sektor: {profile.get('sector', 'brak')} | Branża: {profile.get('industry', 'brak')}")
    lines.append("")
    lines.append("**Wejście (modelowe):**")
    if levels:
        lines.append(
            f"- Entry: {fmt_num(levels['entry'], 2)} | SL: {fmt_num(levels['sl'], 2)} | "
            f"TP1: {fmt_num(levels['tp1'], 2)} | TP2: {fmt_num(levels['tp2'], 2)}"
        )
    else:
        lines.append("- Brak danych do wyznaczenia poziomów (ATR / cena).")
    lines.append("")
    lines.append("_To nie jest rekomendacja inwestycyjna. Model ma charakter edukacyjny._")

    return "\n".join(lines)

# =========================================================
# STREAMLIT APP
# =========================================================

st.set_page_config(page_title="Adam Terminal V3 – Okazje + Wejścia", layout="wide")

st.title("Adam Terminal V3 – Okazje + Wejścia (Technika 60 / Fundamenty 40)")

col_top1, col_top2 = st.columns(2)
with col_top1:
    ticker = st.text_input("Ticker (GPW: CDR.WA, STX.WA / USA: AAPL, MSFT):", "AAPL").upper().strip()
with col_top2:
    period = st.selectbox("Okres danych cenowych:", ["3mo", "6mo", "1y"], index=1)

if st.button("Skanuj okazję i wyznacz wejście"):
    df = load_price_data(ticker, period=period, interval="1d")
    if df.empty:
        st.error("Brak danych cenowych dla tego tickera.")
    else:
        ind, rsi_series, macd_series, macd_signal_series, ma_fast_series, ma_slow_series, obv_series, rvol_series = compute_indicators(df)

        st.subheader("📈 Wykres cenowy + MA")
        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Cena"
        ))

        fig.add_trace(go.Scatter(
            x=df.index,
            y=ma_fast_series,
            mode="lines",
            name="MA10",
            line=dict(color="orange")
        ))

        fig.add_trace(go.Scatter(
            x=df.index,
            y=ma_slow_series,
            mode="lines",
            name="MA30",
            line=dict(color="blue")
        ))

        fig.update_layout(
            height=600,
            template="plotly_dark",
            xaxis_rangeslider_visible=False
        )

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📊 Technika")

        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        col_t1.metric("Trend (MA10 vs MA30)", ind["trend"])
        col_t2.metric("RSI (14)", fmt_num(ind["rsi"], 2))
        col_t3.metric("MACD", fmt_num(ind["macd"], 4))
        col_t4.metric("MACD sygnał", fmt_num(ind["macd_signal"], 4))

        col_v1, col_v2 = st.columns(2)
        col_v1.metric("RVOL (20)", fmt_num(ind["rvol_last"], 2))
        col_v2.metric("OBV (ostatni)", fmt_num(ind["obv_last"], 0))

        st.caption(f"ATR (14): {fmt_num(ind['atr'], 2)}")

        st.subheader("📊 Fundamenty + DCF")

        fund = fetch_fundamentals(ticker)
        if fund.get("_errors"):
            with st.expander("Ostrzeżenia fundamentals"):
                for e in fund["_errors"]:
                    st.warning(e)

        metrics = fund["metrics"]
        profile = fund["profile"]

        col_f1, col_f2, col_f3 = st.columns(3)
        col_f1.metric("Cena rynkowa", fmt_num(metrics.get("currentPrice"), 2))
        col_f2.metric("Market Cap", fmt_num(metrics.get("marketCap"), 0))
        col_f3.metric("P/E", fmt_num(metrics.get("trailingPE"), 2))

        st.write(f"**Spółka:** {profile.get('longName', ticker)}")
        st.write(f"**Sektor:** {profile.get('sector', 'brak')} | **Branża:** {profile.get('industry', 'brak')}")

        with st.expander("Opis biznesu"):
            st.write(profile.get("longBusinessSummary", "Brak opisu."))

        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            wacc_i = st.slider("WACC", 0.04, 0.20, 0.09, 0.01)
        with col_d2:
            growth_i = st.slider("Wzrost FCF (1-5)", -0.10, 0.40, 0.08, 0.01)
        with col_d3:
            term_i = st.slider("Terminal growth", 0.00, 0.05, 0.02, 0.005)

        dcf = calculate_dcf(fund, wacc_i, growth_i, term_i)

        if "error" in dcf:
            st.error(dcf["error"])
        else:
            col_dcf1, col_dcf2, col_dcf3 = st.columns(3)
            col_dcf1.metric("Wartość DCF (na akcję)", fmt_num(dcf["intrinsic_value"], 2))
            col_dcf2.metric("Cena rynkowa", fmt_num(dcf["current_price"], 2))
            col_dcf3.metric("Upside", f"{dcf['upside']:.2f}%")

            st.caption(f"FCF użyty: {dcf['latest_fcf']:,.0f} USD")

        st.subheader("🎯 Okazja + Wejście")

        tech_score = compute_technical_score(ind)
        fund_score = compute_fundamental_score(fund, dcf)
        fused_score = tech_score * 0.6 + fund_score * 0.4
        fused_score = max(0.0, min(100.0, fused_score))
        opportunity = classify_opportunity(fused_score)

        levels = suggest_levels(df, ind)

        col_o1, col_o2, col_o3 = st.columns(3)
        col_o1.metric("Technical Score", f"{tech_score:.1f}/100")
        col_o2.metric("Fundamental Score", f"{fund_score:.1f}/100")
        col_o3.metric("Fused Score", f"{fused_score:.1f}/100")

        st.write(f"**Klasyfikacja okazji:** {opportunity}")

        if levels:
            col_l1, col_l2, col_l3, col_l4 = st.columns(4)
            col_l1.metric("Entry", fmt_num(levels["entry"], 2))
            col_l2.metric("Stop Loss", fmt_num(levels["sl"], 2))
            col_l3.metric("TP1", fmt_num(levels["tp1"], 2))
            col_l4.metric("TP2", fmt_num(levels["tp2"], 2))
        else:
            st.warning("Brak danych do wyliczenia poziomów SL/TP.")

        st.subheader("📄 Raport V3 – Okazje + Wejścia")
        report_text = generate_v3_report(ticker, ind, fund, dcf, tech_score, fund_score, fused_score, opportunity, levels)
        st.markdown(report_text)

        st.subheader("📄 Sprawozdania finansowe")
        with st.expander("Income Statement"):
            st.json(clean_for_json(fund["income"]))
        with st.expander("Balance Sheet"):
            st.json(clean_for_json(fund["balance"]))
        with st.expander("Cash Flow"):
            st.json(clean_for_json(fund["cash"]))

st.markdown(
    """
    <hr style='border: 1px solid #1f2937; margin-top: 40px;'>
    <div style='text-align: center; color: #6b7280; font-size: 0.8rem;'>
    Adam Terminal V3 • Okazje + Wejścia • Technika 60 / Fundamenty 40
    <br>
    Narzędzie edukacyjne i analityczne. Nie stanowi rekomendacji inwestycyjnej.
    </div>
    """,
    unsafe_allow_html=True
)
