
import streamlit as st
from openai import OpenAI
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
st.set_page_config(page_title="3× AI — Swing / Day / Long", layout="centered")

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
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Swing / Day / Long (3 modele GPT, realne dane)")

# ================== AI MODUŁY ==================

def ai_swing(ticker, text):
    prompt = f"""
Jesteś agresywnym traderem swingowym.
Patrzysz na momentum, RSI, wolumen i wybicia.

Analiza SWING dla {ticker} (realne dane):
{text}

Zadanie:
- 2–3 zdania
- dynamiczny styl
- zero kopiowania danych
"""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


def ai_day(ticker, text):
    prompt = f"""
Jesteś precyzyjnym daytraderem.
Analizujesz mikro‑ruchy, momentum 3, RSI7, wolumen intraday.

Analiza DAYTRADING dla {ticker} (realne dane):
{text}

Zadanie:
- 2–3 zdania
- styl szybki, konkretny
- zero kopiowania danych
"""
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


def ai_long(ticker, text):
    prompt = f"""
Jesteś spokojnym analitykiem długoterminowym.
Patrzysz na trend EMA50/100/200, stabilność i wolumen.

Analiza LONG-TERM dla {ticker} (realne dane):
{text}

Zadanie:
- 2–3 zdania
- styl spokojny, analityczny
- zero kopiowania danych
"""
    r = client.chat.completions.create(
        model="o3-mini",
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


# ================== DANE I WSKAŹNIKI ==================

def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    if tf == "D1":
        df = yf.download(ticker, period="1y", interval="1d", auto_adjust=False)
    else:  # H1
        df = yf.download(ticker, period="30d", interval="60m", auto_adjust=False)

    df = df.dropna()
    df = df.rename(columns=str.strip)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    # SMA
    for w in [20, 50, 100, 200]:
        df[f"SMA{w}"] = close.rolling(w).mean()

    # Bollinger (klasyczny: MA20 + 2*STD20 na CLOSE)
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()

    bb_upper = (ma20 + 2 * std20)
    bb_lower = (ma20 - 2 * std20)

    df["BB_upper"] = bb_upper.reindex(df.index).astype(float)
    df["BB_lower"] = bb_lower.reindex(df.index).astype(float)

    # RSI14
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    roll_up = gain.rolling(14).mean()
    roll_down = loss.rolling(14).mean()
    rs = roll_up / (roll_down + 1e-9)
    df["RSI14"] = 100 - (100 / (1 + rs))

    # ATR14
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


def detect_trend_from_df(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    if pd.notna(last.get("SMA200")):
        if last["Close"] > last["SMA200"] * 1.01:
            return "bull"
        if last["Close"] < last["SMA200"] * 0.99:
            return "bear"
    if pd.notna(last.get("SMA50")):
        if last["Close"] > last["SMA50"]:
            return "bull"
        if last["Close"] < last["SMA50"]:
            return "bear"
    return "side"


def trend_label_and_css(trend_code: str):
    if trend_code == "bull":
        return "Trend wzrostowy (🐂 byczy)", "trend-bull"
    if trend_code == "bear":
        return "Trend spadkowy (🐻 niedźwiedzi)", "trend-bear"
    return "Trend boczny / konsolidacja (➖)", "trend-side"


def detect_bollinger_signal(df: pd.DataFrame):
    last = df.iloc[-1]
    sig = []
    if pd.notna(last["BB_upper"]) and last["Close"] > last["BB_upper"]:
        sig.append("Cena powyżej górnej wstęgi — silne momentum / możliwe wykupienie.")
    elif pd.notna(last["BB_lower"]) and last["Close"] < last["BB_lower"]:
        sig.append("Cena poniżej dolnej wstęgi — możliwe wyprzedanie / odbicie.")
    else:
        sig.append("Cena wewnątrz wstęg — brak skrajnych odchyleń.")
    return sig


def detect_sma_signals(df: pd.DataFrame):
    last = df.iloc[-1]
    res = []
    for w in [20, 50, 100, 200]:
        col = f"SMA{w}"
        if col in df.columns and pd.notna(last[col]):
            if last["Close"] > last[col]:
                res.append(f"Cena powyżej SMA{w} — wsparcie trendu wzrostowego.")
            elif last["Close"] < last[col]:
                res.append(f"Cena poniżej SMA{w} — presja podażowa względem SMA{w}.")
    if df["SMA50"].notna().sum() > 5 and df["SMA200"].notna().sum() > 5:
        s50 = df["SMA50"].tail(5)
        s200 = df["SMA200"].tail(5)
        if (s50.iloc[-2] < s200.iloc[-2]) and (s50.iloc[-1] > s200.iloc[-1]):
            res.append("Golden cross (SMA50 przecięła SMA200 w górę) — silny sygnał byczy.")
        if (s50.iloc[-2] > s200.iloc[-2]) and (s50.iloc[-1] < s200.iloc[-1]):
            res.append("Death cross (SMA50 przecięła SMA200 w dół) — sygnał niedźwiedzi.")
    return res


def detect_rsi_signal(df: pd.DataFrame):
    last = df.iloc[-1]
    rsi = last["RSI14"]
    if pd.isna(rsi):
        return ["RSI14: brak wystarczającej liczby danych."]
    if rsi > 70:
        return [f"RSI14 ≈ {rsi:.1f} — strefa wykupienia."]
    if rsi < 30:
        return [f"RSI14 ≈ {rsi:.1f} — strefa wyprzedania."]
    if rsi > 50:
        return [f"RSI14 ≈ {rsi:.1f} — przewaga byków."]
    return [f"RSI14 ≈ {rsi:.1f} — neutralnie / lekka przewaga podaży."]


def compute_sl_tp(df: pd.DataFrame, trend_code: str):
    last = df.iloc[-1]
    close = last["Close"]
    atr = last["ATR14"]
    if pd.isna(atr) or atr == 0:
        return "SL/TP: za mało danych ATR.", ""

    if trend_code == "bull":
        sl = close - 1.5 * atr
        tp = close + 2.5 * atr
        side = "LONG"
    elif trend_code == "bear":
        sl = close + 1.5 * atr
        tp = close - 2.5 * atr
        side = "SHORT"
    else:
        sl = close - 1.0 * atr
        tp = close + 1.5 * atr
        side = "RANGE / MEAN REVERSION"

    sl_txt = f"{side}: SL ≈ {sl:.2f}"
    tp_txt = f"{side}: TP ≈ {tp:.2f}"
    return sl_txt, tp_txt


def build_summary_for_ai(df: pd.DataFrame, trend_code: str, tf: str) -> str:
    last = df.iloc[-1]
    boll = detect_bollinger_signal(df)
    sma_sig = detect_sma_signals(df)
    rsi_sig = detect_rsi_signal(df)
    sl_txt, tp_txt = compute_sl_tp(df, trend_code)
    trend_label, _ = trend_label_and_css(trend_code)

    lines = []
    lines.append(f"Timeframe: {tf}")
    lines.append(f"Ostatnie Close: {last['Close']:.2f}, High: {last['High']:.2f}, Low: {last['Low']:.2f}, Volume: {int(last['Volume'])}")
    lines.append(f"Trend: {trend_label}")
    lines.append(f"RSI14: {rsi_sig[0]}")
    lines.append(f"Bollinger: {boll[0]}")
    if sma_sig:
        lines.append("SMA sygnały: " + " | ".join(sma_sig[:3]))
    lines.append(f"SL: {sl_txt}")
    lines.append(f"TP: {tp_txt}")

    return "\n".join(lines)


# ================== WYKRES MULTICHART ==================

def plot_multichart(df: pd.DataFrame):
    df = df.dropna().copy()
    df = df.tail(120)

    x = df.index

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.55, 0.25, 0.20]
    )

    fig.add_trace(go.Candlestick(
        x=x,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        increasing_line_color="lime",
        decreasing_line_color="red",
        name="Świece"
    ), row=1, col=1)

    for w, color in [(20, "orange"), (50, "cyan"), (100, "violet"), (200, "gray")]:
        col = f"SMA{w}"
        if col in df.columns and df[col].notna().any():
            fig.add_trace(go.Scatter(
                x=x, y=df[col],
                line=dict(color=color, width=1.3),
                name=f"SMA{w}"
            ), row=1, col=1)

    if "BB_upper" in df.columns and "BB_lower" in df.columns:
        fig.add_trace(go.Scatter(
            x=x, y=df["BB_upper"],
            line=dict(color="#60a5fa", dash="dash", width=1),
            name="BB Upper"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=x, y=df["BB_lower"],
            line=dict(color="#60a5fa", dash="dash", width=1),
            name="BB Lower"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=list(x) + list(x[::-1]),
            y=list(df["BB_upper"]) + list(df["BB_lower"][::-1]),
            fill="toself",
            fillcolor="rgba(76, 29, 149, 0.18)",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            showlegend=False
        ), row=1, col=1)

    if "RSI14" in df.columns:
        fig.add_trace(go.Scatter(
            x=x, y=df["RSI14"],
            line=dict(color="yellow", width=2),
            name="RSI14"
        ), row=2, col=1)
        fig.add_hline(y=70, line=dict(color="red", dash="dot"), row=2, col=1)
        fig.add_hline(y=30, line=dict(color="lime", dash="dot"), row=2, col=1)

    fig.add_trace(go.Bar(
        x=x, y=df["Volume"],
        marker_color="purple",
        name="Volume"
    ), row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=800,
        margin=dict(l=20, r=20, t=30, b=20),
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        title="📊 MULTICHART: realne dane (świece + SMA + BB + RSI + Volume)"
    )

    st.plotly_chart(fig, use_container_width=True)


# ================== UI ==================

col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("Ticker:", "AAPL")
with col2:
    tf = st.selectbox(
        "Interwał danych:",
        ["D1 (świece dzienne)", "H1 (świece godzinowe)"]
    )

tf_code = "D1" if tf.startswith("D1") else "H1"

ai_choice = st.selectbox(
    "Wybierz AI:",
    [
        "AI Swing — gpt‑4o‑mini",
        "AI Day — gpt‑4o",
        "AI Long — o3‑mini"
    ]
)

user_notes = st.text_area(
    "Twoje notatki / kontekst (opcjonalne):",
    "",
    placeholder="Np. ważne poziomy, newsy, własne obserwacje..."
)

if st.button("Analizuj (realne dane + AI)"):
    try:
        df = get_ohlc(ticker, tf_code)
    except Exception as e:
        st.error(f"Problem z pobraniem danych dla {ticker}: {e}")
        st.stop()

    if df.empty:
        st.error("Brak danych dla tego tickera / interwału.")
        st.stop()

    df = add_indicators(df)
    trend_code = detect_trend_from_df(df)
    trend_label, trend_css = trend_label_and_css(trend_code)

    st.subheader("🔍 Analiza techniczna (realne dane)")

    st.markdown(
        f"""
        <div class="trend-box {trend_css}">
            <b>Trend główny:</b> {trend_label}
        </div>
        """,
        unsafe_allow_html=True,
    )

    boll = detect_bollinger_signal(df)
    sma_sig = detect_sma_signals(df)
    rsi_sig = detect_rsi_signal(df)
    sl_txt, tp_txt = compute_sl_tp(df, trend_code)

    st.markdown("**Wstęgi Bollingera:**")
    for b in boll:
        st.markdown(f"- {b}")

    st.markdown("**SMA / średnie kroczące:**")
    for s in sma_sig:
        st.markdown(f"- {s}")

    st.markdown("**RSI14:**")
    for r in rsi_sig:
        st.markdown(f"- {r}")

    st.markdown("**SL / TP (na bazie ATR14):**")
    st.markdown(f"- {sl_txt}")
    st.markdown(f"- {tp_txt}")

    with st.expander("📈 MULTICHART — pełna analiza techniczna (realne dane)"):
        plot_multichart(df)

    st.markdown(
        """
        <div class="info-box">
            Analiza oparta na realnych danych z Yahoo Finance (yfinance).
            Zawsze łącz to z własnym planem, risk managementem i kontekstem rynkowym.
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary = build_summary_for_ai(df, trend_code, tf_code)
    if user_notes.strip():
        summary = summary + "\n\nNotatki użytkownika:\n" + user_notes.strip()

    if "Swing" in ai_choice:
        wynik = ai_swing(ticker, summary)
        css = "swing"
    elif "Day" in ai_choice:
        wynik = ai_day(ticker, summary)
        css = "day"
    else:
        wynik = ai_long(ticker, summary)
        css = "long"

    st.markdown(f"""
    <div class="box {css}">
        <b>Wynik AI ({ai_choice}):</b><br>{wynik}
    </div>
    """, unsafe_allow_html=True)
