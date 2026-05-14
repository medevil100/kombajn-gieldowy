import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from openai import OpenAI
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="AI Trading Terminal PRO", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #02030a; color: #e5e7eb; }
.sidebar .sidebar-content { background: radial-gradient(circle at top left, #020617, #000000); border-right: 1px solid #1f2937; }
h1, h2, h3 { color: #f9fafb; text-shadow: 0 0 12px rgba(56,189,248,0.35); }
.stButton>button { background: linear-gradient(135deg, #0f172a, #0369a1); color: #e5e7eb; border-radius: 999px; border: 1px solid #38bdf8; padding: 0.35rem 0.9rem; font-weight: 600; box-shadow: 0 0 14px rgba(56,189,248,0.35); }
.stButton>button:hover { border-color: #22c55e; box-shadow: 0 0 18px rgba(34,197,94,0.55); }
.metric-green { color: #22c55e; text-shadow: 0 0 8px rgba(34,197,94,0.7); }
.metric-yellow { color: #eab308; text-shadow: 0 0 8px rgba(234,179,8,0.7); }
.metric-red { color: #ef4444; text-shadow: 0 0 8px rgba(239,68,68,0.7); }
</style>
""", unsafe_allow_html=True)

def get_openai_client():
    key = st.secrets.get("OPENAI_API_KEY", None)
    if not key:
        return None
    try:
        return OpenAI(api_key=key)
    except:
        return None

def rsi(series, window=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    m = ema_fast - ema_slow
    s = m.ewm(span=signal, adjust=False).mean()
    h = m - s
    return m, s, h

def bollinger(series, window=20, mult=2):
    mid = series.rolling(window).mean()
    std = series.rolling(window).std()
    upper = mid + mult * std
    lower = mid - mult * std
    return mid, upper, lower

def trend_signal(close):
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    if sma20.iloc[-1] > sma50.iloc[-1] > sma200.iloc[-1]:
        return "KUP", "metric-green"
    if sma20.iloc[-1] < sma50.iloc[-1] < sma200.iloc[-1]:
        return "SPRZEDAJ", "metric-red"
    return "TRZYMAJ", "metric-yellow"

def load(symbol, interval, period):
    df = yf.download(symbol, interval=interval, period=period, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

def build_prompt(style):
    return (
        "Jesteś profesjonalnym traderem technicznym. Analizujesz jeden instrument i podajesz konkretny plan.\n\n"
        "#1 DECYZJA: KUP / SPRZEDAJ / TRZYMAJ\n"
        "#2 UZASADNIENIE: RSI, SMA20/50/200, MACD, Bollinger Bands, trend, momentum, poziomy\n"
        "#3 PLAN: ENTRY, SL, TP1, TP2, TP3\n"
        "#4 RYZYKO: 1–10\n"
        "#5 AUTO-PATTERN DETECTION: opisz wykryte patterny (np. double top, triangle, flag, range) tylko jeśli są istotne\n\n"
        f"Styl: {style}."
    )

def call_ai(client, model, system_prompt, user_prompt):
    if client is None:
        return "AI OFF – brak klucza w secrets."
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            temperature=0.25,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"AI ERROR: {e}"

st.sidebar.header("⚙️ Ustawienia")
symbol = st.sidebar.text_input("Ticker", "")
tf = st.sidebar.selectbox("Interwał", ["1m", "5m", "15m", "30m", "1h"], index=2)
model = st.sidebar.selectbox("Model GPT", ["gpt-4o-mini", "gpt-4o", "gpt-4.1"], index=0)
style = st.sidebar.selectbox("Styl AI", ["Technicznie", "Swing", "Daytrading"], index=0)

if tf == "1m":
    interval, period = "1m", "5d"
elif tf == "5m":
    interval, period = "5m", "10d"
elif tf == "15m":
    interval, period = "15m", "30d"
elif tf == "30m":
    interval, period = "30m", "60d"
else:
    interval, period = "60m", "1y"

st.title("AI Trading Terminal PRO")

if not symbol:
    st.info("Wpisz ticker, aby rozpocząć.")
else:
    df = load(symbol, interval, period)
    if df.empty:
        st.warning("Brak danych.")
    else:
        df["RSI"] = rsi(df["Close"])
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        df["ATR"] = atr(df)
        df["MACD"], df["MACD_SIGNAL"], df["MACD_HIST"] = macd(df["Close"])
        df["BB_MID"], df["BB_UPPER"], df["BB_LOWER"] = bollinger(df["Close"])

        last = df.iloc[-1]
        last_close = float(last["Close"])
        atr_val = float(last["ATR"])

        sl = last_close - 1.5 * atr_val
        tp1 = last_close + 1.0 * atr_val
        tp2 = last_close + 2.0 * atr_val
        tp3 = last_close + 3.0 * atr_val

        sig, cls = trend_signal(df["Close"])

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"<div class='{cls}'>Trend: {sig}</div>", unsafe_allow_html=True)
        with c2:
            r_val = float(last["RSI"])
            rc = "metric-green" if r_val < 30 else "metric-red" if r_val > 70 else "metric-yellow"
            st.markdown(f"<div class='{rc}'>RSI: {r_val:.1f}</div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='metric-yellow'>ATR: {atr_val:.4f}</div>", unsafe_allow_html=True)

        n_trend = min(80, len(df))
        x_idx = np.arange(n_trend)
        y_close = df["Close"].iloc[-n_trend:].values
        if len(y_close) > 1:
            coef = np.polyfit(x_idx, y_close, 1)
            trend_line = coef[0] * x_idx + coef[1]
            trend_x = df.index[-n_trend:]
        else:
            trend_line = None
            trend_x = None

        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.45, 0.15, 0.2, 0.2]
        )

        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
            name="Cena"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], line=dict(color="#22c55e", width=1.2), name="SMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], line=dict(color="#eab308", width=1.2), name="SMA50"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], line=dict(color="#ef4444", width=1.2), name="SMA200"), row=1, col=1)

        fig.add_trace(go.Scatter(x=df.index, y=df["BB_UPPER"], line=dict(color="#eab308", width=0.8, dash="dot"), name="BB Upper"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_MID"], line=dict(color="#eab308", width=0.8), name="BB Mid"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_LOWER"], line=dict(color="#eab308", width=0.8, dash="dot"), name="BB Lower"), row=1, col=1)

        if trend_line is not None:
            fig.add_trace(go.Scatter(x=trend_x, y=trend_line, line=dict(color="#22c55e", width=1.4, dash="dash"), name="Auto Trendline"), row=1, col=1)

        vol = df["Volume"]
        v_q1, v_q2, v_q3 = vol.quantile([0.33, 0.66, 0.9])
        colors = []
        for v, o, c in zip(vol, df["Open"], df["Close"]):
            if v >= v_q3:
                colors.append("#ef4444" if c < o else "#22c55e")
            elif v >= v_q2:
                colors.append("#eab308")
            else:
                colors.append("#22c55e" if c >= o else "#ef4444")

        fig.add_trace(go.Bar(
            x=df.index,
            y=df["Volume"],
            marker_color=colors,
            name="Volume Heatmap"
        ), row=2, col=1)

        fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], line=dict(color="#eab308", width=1.2), name="RSI"), row=3, col=1)
        fig.add_hrect(y0=30, y1=70, fillcolor="rgba(148,163,184,0.15)", line_width=0, row=3, col=1)

        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], line=dict(color="#22c55e", width=1.2), name="MACD"), row=4, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD_SIGNAL"], line=dict(color="#ef4444", width=1.0), name="MACD Signal"), row=4, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df["MACD_HIST"],
                             marker_color=np.where(df["MACD_HIST"] >= 0, "#22c55e", "#ef4444"),
                             name="MACD Hist"), row=4, col=1)

        fig.update_layout(
            template="plotly_dark",
            height=900,
            xaxis_rangeslider_visible=False,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Plan transakcji")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"<div class='metric-red'>SL: {sl:.4f}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='metric-green'>TP1: {tp1:.4f}</div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='metric-green'>TP2: {tp2:.4f}</div>", unsafe_allow_html=True)
        with c4:
            st.markdown(f"<div class='metric-green'>TP3: {tp3:.4f}</div>", unsafe_allow_html=True)

        st.subheader("AI analiza instrumentu")

        if st.button("🔮 Wygeneruj analizę AI"):
            client = get_openai_client()
            last_rows = df.tail(20)[["Open", "High", "Low", "Close"]]
            pattern_snippet = last_rows.to_string()
            system_prompt = build_prompt(style)
            user_prompt = (
                f"Analizuj {symbol} na interwale {tf}. Cena: {last_close:.4f}, RSI {last['RSI']:.1f}, "
                f"SMA20 {df['SMA20'].iloc[-1]:.4f}, SMA50 {df['SMA50'].iloc[-1]:.4f}, "
                f"SMA200 {df['SMA200'].iloc[-1]:.4f}, ATR {atr_val:.4f}. "
                f"MACD {df['MACD'].iloc[-1]:.4f}, MACD_SIGNAL {df['MACD_SIGNAL'].iloc[-1]:.4f}. "
                f"Bollinger: górne {df['BB_UPPER'].iloc[-1]:.4f}, dolne {df['BB_LOWER'].iloc[-1]:.4f}. "
                f"Trend: {sig}. SL {sl:.4f}, TP1 {tp1:.4f}, TP2 {tp2:.4f}, TP3 {tp3:.4f}. "
                f"Oto ostatnie świece (Open, High, Low, Close) do auto-pattern detection:\n{pattern_snippet}"
            )
            out = call_ai(client, model, system_prompt, user_prompt)
            st.markdown(out)

st.markdown("""
<hr style='border: 1px solid #1f2937; margin-top: 40px;'>
<div style='text-align: center; color: #6b7280; font-size: 0.8rem;'>
AI Trading Terminal PRO • Neon Dark • SMA / RSI / MACD / BB / ATR / Trend • 2026
</div>
""", unsafe_allow_html=True)
