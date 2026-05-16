import streamlit as st
from openai import OpenAI
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
st.set_page_config(page_title="3× AI — Swing / Day / Long", layout="centered")
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ================== STYLE ==================
st.markdown("""
<style>
.box {
    padding: 15px;
    border-radius: 10px;
    font-size: 18px;
    margin-top: 15px;
    color: white;
}
.swing  { background-color: #0f5132; }
.day    { background-color: #0d6efd; }
.long   { background-color: #6f42c1; }

.trend-box {
    padding: 10px;
    border-radius: 8px;
    margin-top: 10px;
    color: white;
    font-size: 16px;
}
.trend-bear   { background-color: #d9534f; border: 2px solid #b52b27; }
.trend-bull   { background-color: #5cb85c; border: 2px solid #3d8b3d; }
.trend-side   { background-color: #f0ad4e; border: 2px solid #c77c11; }

.info-box {
    padding: 10px;
    border-radius: 8px;
    margin-top: 10px;
    background-color: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
    font-size: 15px;
}

.plot-border {
    border: 3px solid #6f42c1;
    border-radius: 12px;
    padding: 8px;
    margin-top: 10px;
}
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Swing / Day / Long (3 modele GPT, realne dane)")

# ================== AI ==================

def ai_swing(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[{"role": "user", "content": f"""
Jesteś agresywnym traderem swingowym.
Analiza SWING dla {ticker}:
{text}
Zadanie: 2–3 zdania, dynamicznie, zero kopiowania danych.
"""}],
    )
    return r.choices[0].message.content.strip()

def ai_day(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{"role": "user", "content": f"""
Jesteś precyzyjnym daytraderem.
Analiza DAYTRADING dla {ticker}:
{text}
Zadanie: 2–3 zdania, szybko i konkretnie.
"""}],
    )
    return r.choices[0].message.content.strip()

def ai_long(ticker, text):
    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": f"""
Jesteś spokojnym analitykiem długoterminowym.
Analiza LONG-TERM dla {ticker}:
{text}
Zadanie: 2–3 zdania, spokojnie i analitycznie.
"""}],
    )
    return r.choices[0].message.content.strip()

# ================== DANE ==================

def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    if tf == "D1":
        df = yf.download(ticker, period="1y", interval="1d", auto_adjust=False)
    else:
        df = yf.download(ticker, period="30d", interval="60m", auto_adjust=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(0)

    df.columns = [c.strip() for c in df.columns]

    if "Close" not in df.columns:
        return pd.DataFrame()

    return df.dropna()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    for w in [20, 50, 100, 200]:
        df[f"SMA{w}"] = close.rolling(w).mean()

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["BB_upper"] = ma20 + 2 * std20
    df["BB_lower"] = ma20 - 2 * std20

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    roll_up = gain.rolling(14).mean()
    roll_down = loss.rolling(14).mean()
    rs = roll_up / (roll_down + 1e-9)
    df["RSI14"] = 100 - (100 / (1 + rs))

    high = df["High"]
    low = df["Low"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()

    return df

# ================== TREND ==================

def detect_trend_from_df(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    sma200 = last.get("SMA200", np.nan)
    sma50 = last.get("SMA50", np.nan)

    if pd.notna(sma200):
        if last["Close"] > sma200 * 1.01:
            return "bull"
        if last["Close"] < sma200 * 0.99:
            return "bear"

    if pd.notna(sma50):
        if last["Close"] > sma50:
            return "bull"
        if last["Close"] < sma50:
            return "bear"

    return "side"

def trend_label_and_css(code: str):
    if code == "bull": return "Trend wzrostowy (🐂)", "trend-bull"
    if code == "bear": return "Trend spadkowy (🐻)", "trend-bear"
    return "Trend boczny (➖)", "trend-side"

def compute_trend_score(df: pd.DataFrame, trend_code: str) -> float:
    last = df.iloc[-1]
    score = 0

    if trend_code == "bull": score += 30
    if last["Close"] < 5: score += 10

    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)
    rsi = last.get("RSI14", np.nan)

    if pd.notna(sma50) and last["Close"] > sma50: score += 15
    if pd.notna(sma200) and last["Close"] > sma200: score += 15
    if pd.notna(sma50) and pd.notna(sma200) and sma50 > sma200: score += 20

    if pd.notna(rsi):
        if 55 <= rsi <= 70: score += 10
        elif 50 <= rsi < 55: score += 5

    return score

# ================== WYKRES ==================

def plot_multichart(df: pd.DataFrame):
    df = df.tail(120)
    x = df.index

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.05, row_heights=[0.55, 0.25, 0.20]
    )

    fig.add_trace(go.Candlestick(
        x=x, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        increasing_line_color="#00ff88",
        decreasing_line_color="#ff0055",
        name="Świece"
    ), row=1, col=1)

    for w, color in [(20, "#ffaa00"), (50, "#00e5ff"), (100, "#cc66ff"), (200, "#888888")]:
        fig.add_trace(go.Scatter(
            x=x, y=df[f"SMA{w}"],
            line=dict(color=color, width=1.8),
            name=f"SMA{w}"
        ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=df["BB_upper"],
        line=dict(color="#60a5fa", dash="dash", width=1.5),
        name="BB Upper"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=df["BB_lower"],
        line=dict(color="#60a5fa", dash="dash", width=1.5),
        name="BB Lower"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=df["RSI14"],
        line=dict(color="#ffff00", width=2),
        name="RSI14"
    ), row=2, col=1)

    fig.add_hline(y=70, line=dict(color="#ff4444", dash="dot"), row=2, col=1)
    fig.add_hline(y=30, line=dict(color="#44ff44", dash="dot"), row=2, col=1)

    fig.add_trace(go.Bar(
        x=x, y=df["Volume"],
        marker_color="#aa44ff",
        name="Volume"
    ), row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=800,
        margin=dict(l=20, r=20, t=30, b=20),
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        title="📊 MULTICHART — neonowa analiza techniczna"
    )

    st.markdown('<div class="plot-border">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ================== SKANER RYNKU ==================

st.subheader("🧪 Skaner groszówek PL + USA — ranking trendów")

tickers_text = st.text_area(
    "Lista tickerów (oddzielone przecinkami lub nową linią):",
    "AAPL, TSLA, NVDA, CDR, AMC, MULN",
    height=100,
)

only_pennies = st.checkbox("Filtruj tylko groszówki (Close < 5)", value=True)
tf_scan = st.selectbox("Interwał skanera:", ["D1", "H1"])
tf_scan_code = "D1" if tf_scan == "D1" else "H1"

ranking_df = None
scan_results = {}

if st.button("Skanuj rynek i zbuduj ranking trendów"):
    raw = tickers_text.replace("\n", ",")
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    tickers = list(dict.fromkeys(tickers))

    rows = []
    for t in tickers:
        try:
            df_t = get_ohlc(t, tf_scan_code)
            if df_t.empty:
                continue
            df_t = add_indicators(df_t)
            trend_code = detect_trend_from_df(df_t)
            last = df_t.iloc[-1]
            close = float(last["Close"])
            score = compute_trend_score(df_t, trend_code)

            if only_pennies and close >= 5:
                continue

            rows.append({
                "Ticker": t,
                "Trend": trend_code,
                "Close": round(close, 4),
                "TrendScore": round(score, 2),
            })
            scan_results[t] = df_t
        except Exception:
            continue

    if rows:
        ranking_df = pd.DataFrame(rows)
        ranking_df = ranking_df[ranking_df["Trend"] == "bull"]
        ranking_df = ranking_df.sort_values("TrendScore", ascending=False).reset_index(drop=True)

        if ranking_df.empty:
            st.warning("Brak spółek w trendzie wzrostowym.")
        else:
            st.markdown("### 🏆 Ranking spółek w trendzie wzrostowym")
            st.dataframe(ranking_df, use_container_width=True)
    else:
        st.warning("Brak danych dla podanych tickerów.")

# ================== ANALIZA AI ==================

st.subheader("🤖 Analiza AI wybranej spółki")

if ranking_df is not None and not ranking_df.empty:
    selected_ticker = st.selectbox("Wybierz ticker:", ranking_df["Ticker"].tolist())
else:
    selected_ticker = st.text_input("Ticker:", "AAPL")

tf_detail = st.selectbox("Interwał analizy:", ["D1", "H1"])
tf_detail_code = "D1" if tf_detail == "D1" else "H1"

ai_choice = st.selectbox(
    "Wybierz AI:",
    ["AI Swing — gpt‑4o‑mini", "AI Day — gpt‑4o", "AI Long — o3‑mini"]
)

user_notes = st.text_area("Twoje notatki:", "")

if st.button("Analizuj wybraną spółkę"):
    try:
        if ranking_df is not None and selected_ticker in scan_results:
            df = scan_results[selected_ticker]
        else:
            df = get_ohlc(selected_ticker, tf_detail_code)
            df = add_indicators(df)
    except:
        st.error("Błąd pobierania danych.")
        st.stop()

    trend_code = detect_trend_from_df(df)
    trend_label, trend_css = trend_label_and_css(trend_code)

    st.markdown(
        f'<div class="trend-box {trend_css}"><b>Trend:</b> {trend_label}</div>',
        unsafe_allow_html=True,
    )

    summary = f"""
Ticker: {selected_ticker}
Trend: {trend_label}
Close: {df.iloc[-1]['Close']:.2f}
RSI14: {df.iloc[-1]['RSI14']:.2f}
Notatki: {user_notes}
"""

    if "Swing" in ai_choice:
        wynik = ai_swing(selected_ticker, summary)
        css = "swing"
    elif "Day" in ai_choice:
        wynik = ai_day(selected_ticker, summary)
        css = "day"
    else:
        wynik = ai_long(selected_ticker, summary)
        css = "long"

    st.markdown(f'<div class="box {css}"><b>Wynik AI:</b><br>{wynik}</div>', unsafe_allow_html=True)

    with st.expander("📈 MULTICHART"):
        plot_multichart(df)
