
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
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Swing / Day / Long (3 modele GPT, realne dane)")

# ================== AI MODUŁY ==================

def ai_swing(ticker, text):
    prompt = f"""
Jesteś agresywnym traderem swingowym.
Patrzysz na momentum, RSI, wolumen i wybicia.

Analiza SWING dla {ticker}:
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

Analiza DAYTRADING dla {ticker}:
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

Analiza LONG-TERM dla {ticker}:
{text}

Zadanie:
- 2–3 zdania
- styl spokojny, analityczny
- zero kopiowania danych
"""
    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


# ================== DANE I WSKAŹNIKI ==================

def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    if tf == "D1":
        df = yf.download(
            ticker,
            period="1y",
            interval="1d",
            auto_adjust=False,
            group_by="column",
        )
    else:
        df = yf.download(
            ticker,
            period="30d",
            interval="60m",
            auto_adjust=False,
            group_by="column",
        )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    df = df.dropna()
    df = df.rename(columns=str.strip)
    return df


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


def trend_label_and_css(trend_code: str):
    if trend_code == "bull":
        return "Trend wzrostowy (🐂 byczy)", "trend-bull"
    if trend_code == "bear":
        return "Trend spadkowy (🐻 niedźwiedzi)", "trend-bear"
    return "Trend boczny / konsolidacja (➖)", "trend-side"


def detect_bollinger_signal(df: pd.DataFrame):
    last = df.iloc[-1]
    if last["Close"] > last["BB_upper"]:
        return ["Cena powyżej górnej wstęgi — silne momentum / możliwe wykupienie."]
    if last["Close"] < last["BB_lower"]:
        return ["Cena poniżej dolnej wstęgi — możliwe wyprzedanie / odbicie."]
    return ["Cena wewnątrz wstęg — brak skrajnych odchyleń."]


def detect_sma_signals(df: pd.DataFrame):
    last = df.iloc[-1]
    res = []
    for w in [20, 50, 100, 200]:
        col = f"SMA{w}"
        if col in df.columns and pd.notna(last[col]):
            if last["Close"] > last[col]:
                res.append(f"Cena powyżej SMA{w} — wsparcie trendu wzrostowego.")
            else:
                res.append(f"Cena poniżej SMA{w} — presja podażowa.")
    return res


def detect_rsi_signal(df: pd.DataFrame):
    rsi = df.iloc[-1]["RSI14"]
    if pd.isna(rsi):
        return ["RSI14: brak danych."]
    if rsi > 70:
        return [f"RSI14 ≈ {rsi:.1f} — wykupienie."]
    if rsi < 30:
        return [f"RSI14 ≈ {rsi:.1f} — wyprzedanie."]
    if rsi > 50:
        return [f"RSI14 ≈ {rsi:.1f} — przewaga byków."]
    return [f"RSI14 ≈ {rsi:.1f} — neutralnie."]


def compute_sl_tp(df: pd.DataFrame, trend_code: str):
    last = df.iloc[-1]
    close = last["Close"]
    atr = last["ATR14"]

    if pd.isna(atr) or atr == 0:
        return "SL/TP: brak danych ATR.", ""

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
        side = "RANGE"

    return f"{side}: SL ≈ {sl:.2f}", f"{side}: TP ≈ {tp:.2f}"


def build_summary_for_ai(df: pd.DataFrame, trend_code: str, tf: str) -> str:
    last = df.iloc[-1]
    boll = detect_bollinger_signal(df)
    sma_sig = detect_sma_signals(df)
    rsi_sig = detect_rsi_signal(df)
    sl_txt, tp_txt = compute_sl_tp(df, trend_code)
    trend_label, _ = trend_label_and_css(trend_code)

    lines = [
        f"Timeframe: {tf}",
        f"Ostatnie Close: {last['Close']:.2f}, High: {last['High']:.2f}, Low: {last['Low']:.2f}, Volume: {int(last['Volume'])}",
        f"Trend: {trend_label}",
        f"RSI14: {rsi_sig[0]}",
        f"Bollinger: {boll[0]}",
        "SMA sygnały: " + " | ".join(sma_sig[:3]),
        f"SL: {sl_txt}",
        f"TP: {tp_txt}",
    ]

    return "\n".join(lines)


def compute_trend_score(df: pd.DataFrame, trend_code: str) -> float:
    last = df.iloc[-1]
    score = 0.0

    if trend_code == "bull":
        score += 30

    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)
    close = last["Close"]
    rsi = last.get("RSI14", np.nan)

    if pd.notna(sma50) and close > sma50:
        score += 15
    if pd.notna(sma200) and close > sma200:
        score += 15
    if pd.notna(sma50) and pd.notna(sma200) and sma50 > sma200:
        score += 20
    if pd.notna(rsi):
        if 55 <= rsi <= 70:
            score += 10
        elif 50 <= rsi < 55:
            score += 5

    if close < 5:
        score += 10

    return score


# ================== WYKRES MULTICHART ==================

def plot_multichart(df: pd.DataFrame):
    df = df.dropna().tail(120).copy()
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


# ================== UI — SKANER RYNKU ==================

st.subheader("🧪 Skaner groszówek PL + USA — ranking trendów")

tickers_text = st.text_area(
    "Lista tickerów (oddzielone przecinkami lub nową linią):",
    "AAPL, TSLA, NVDA",
    height=100,
)

only_pennies = st.checkbox("Filtruj tylko groszówki (Close < 5 w walucie notowania)", value=True)
tf_scan = st.selectbox("Interwał dla skanera:", ["D1 (świece dzienne)", "H1 (świece godzinowe)"])
tf_scan_code = "D1" if tf_scan.startswith("D1") else "H1"

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
            rsi = float(last.get("RSI14", np.nan)) if not pd.isna(last.get("RSI14", np.nan)) else np.nan
            sma50 = float(last.get("SMA50", np.nan)) if not pd.isna(last.get("SMA50", np.nan)) else np.nan
            sma200 = float(last.get("SMA200", np.nan)) if not pd.isna(last.get("SMA200", np.nan)) else np.nan
            score = compute_trend_score(df_t, trend_code)

            if only_pennies and close >= 5:
                continue

            rows.append({
                "Ticker": t,
                "Trend": trend_code,
                "Close": round(close, 4),
                "RSI14": round(rsi, 2) if not np.isnan(rsi) else np.nan,
                "SMA50": round(sma50, 4) if not np.isnan(sma50) else np.nan,
                "SMA200": round(sma200, 4) if not np.isnan(sma200) else np.nan,
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
            st.warning("Brak spółek w wyraźnym trendzie wzrostowym dla podanych tickerów.")
        else:
            st.markdown("### 🏆 Ranking spółek w trendzie wzrostowym")
            st.dataframe(ranking_df, use_container_width=True)
    else:
        st.warning("Nie udało się pobrać danych dla żadnego z podanych tickerów.")

# ================== UI — ANALIZA PO WYBRANIU Z RANKINGU ==================

st.subheader("🤖 Analiza AI wybranej spółki")

selected_ticker = None
if ranking_df is not None and not ranking_df.empty:
    selected_ticker = st.selectbox(
        "Wybierz ticker z rankingu do analizy AI:",
        ranking_df["Ticker"].tolist(),
    )
else:
    selected_ticker = st.text_input("Ticker (fallback, gdy brak rankingu):", "AAPL")

tf_detail = st.selectbox(
    "Interwał danych do analizy szczegółowej:",
    ["D1 (świece dzienne)", "H1 (świece godzinowe)"],
)
tf_detail_code = "D1" if tf_detail.startswith("D1") else "H1"

ai_choice = st.selectbox(
    "Wybierz AI:",
    ["AI Swing — gpt‑4o‑mini", "AI Day — gpt‑4o", "AI Long — o3‑mini"]
)

user_notes = st.text_area(
    "Twoje notatki / kontekst (opcjonalne):",
    "",
    placeholder="Np. ważne poziomy, newsy, własne obserwacje..."
)

if st.button("Analizuj wybraną spółkę (realne dane + AI)"):
    try:
        if ranking_df is not None and selected_ticker in scan_results:
            df = scan_results[selected_ticker]
        else:
            df = get_ohlc(selected_ticker, tf_detail_code)
            if df.empty:
                st.error("Brak danych dla tego tickera / interwału.")
                st.stop()
            df = add_indicators(df)
    except Exception as e:
        st.error(f"Problem z pobraniem danych dla {selected_ticker}: {e}")
        st.stop()

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

    summary = build_summary_for_ai(df, trend_code, tf_detail_code)
    if user_notes.strip():
        summary += "\n\nNotatki użytkownika:\n" + user_notes.strip()

    if "Swing" in ai_choice:
        wynik = ai_swing(selected_ticker, summary)
        css = "swing"
    elif "Day" in ai_choice:
        wynik = ai_day(selected_ticker, summary)
        css = "day"
    else:
        wynik = ai_long(selected_ticker, summary)
        css = "long"

    st.markdown(
        f"""
        <div class="box {css}">
            <b>Wynik AI ({ai_choice}):</b><br>{wynik}
        </div>
        """,
        unsafe_allow_html=True,
    )

