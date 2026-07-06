import os
import requests
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import base64
from io import BytesIO

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ==========================
# 1. DATA LAYER
# ==========================
def normalize_ohlcv(df_raw: pd.DataFrame) -> pd.DataFrame:
    # MultiIndex → spłaszczamy
    if isinstance(df_raw.columns, pd.MultiIndex):
        df_raw.columns = [
            " ".join([str(c) for c in col if str(c) != ""])
            for col in df_raw.columns
        ]

    cols = [str(c) for c in df_raw.columns]

    # mapujemy po fragmencie nazwy, nie po całym stringu
    lower_cols = {c.lower(): c for c in cols}

    def find_col(*candidates):
        for lc, orig in lower_cols.items():
            for cand in candidates:
                if cand in lc:
                    return orig
        return None

    col_open = find_col("open")
    col_high = find_col("high")
    col_low = find_col("low")
    col_close = find_col("close", "adj close", "last", "close*")
    col_volume = find_col("volume", "vol", "total volume")

    needed = [col_open, col_high, col_low, col_close, col_volume]
    if any(c is None for c in needed):
        raise ValueError(f"Nie udało się znormalizować OHLCV: {df_raw.columns}")

    df = df_raw[[col_open, col_high, col_low, col_close, col_volume]].copy()
    df.columns = ["Open", "High", "Low", "Close", "Volume"]

    # wyrzucamy zerowy wolumen
    df = df[df["Volume"] > 0]
    # wygładzamy wolumen
    df["Volume"] = df["Volume"].rolling(3).mean().fillna(df["Volume"])

    return df


def fetch_price_data(ticker: str, period: str = "3mo") -> pd.DataFrame:
    df_raw = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        threads=False,
        progress=False
    )

    if df_raw.empty:
        raise ValueError(f"Brak danych dla {ticker}")

    df = normalize_ohlcv(df_raw)
    if df.empty:
        raise ValueError(f"Brak danych po normalizacji dla {ticker}")

    return df

# ==========================
# 2. TECHNICAL ENGINE
# ==========================
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["MA10"] = out["Close"].rolling(10).mean()
    out["MA30"] = out["Close"].rolling(30).mean()

    delta = out["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    out["RSI"] = 100 - (100 / (1 + rs))

    ema12 = out["Close"].ewm(span=12).mean()
    ema26 = out["Close"].ewm(span=26).mean()
    out["MACD"] = ema12 - ema26
    out["MACD_signal"] = out["MACD"].ewm(span=9).mean()

    out["ATR"] = (out["High"] - out["Low"]).rolling(14).mean()
    out["TREND"] = np.where(out["MA10"] > out["MA30"], "UP", "DOWN")

    return out

# ==========================
# 3. FUNDAMENTAL & NEWS LAYER (SZKIELET)
# ==========================
def get_fundamentals_and_news(ticker: str) -> dict:
    return {
        "price": None,
        "market_cap": None,
        "pe": None,
        "sector": None,
        "industry": None,
        "events": []
    }

# ==========================
# 4. SCORING & AI ENGINE
# ==========================
def score_technical(df: pd.DataFrame) -> float:
    last = df.iloc[-1]
    rsi = last["RSI"]
    macd = last["MACD"]
    atr = last["ATR"]
    close = last["Close"]
    trend = last["TREND"]

    score = 0
    if rsi < 30:
        score += 25
    if macd > 0:
        score += 25
    if atr < close * 0.03:
        score += 25
    if trend == "UP":
        score += 25

    return float(score)


def score_fundamental(facts: dict) -> float:
    return 50.0


def fused_score(tech: float, fund: float) -> float:
    return round(tech * 0.6 + fund * 0.4, 1)


def classify(score: float) -> str:
    if score < 40:
        return "UNIKAJ"
    if score < 70:
        return "NEUTRAL"
    return "OKAZJA"


def build_report(ticker: str, tech: float, fund: float, fused: float,
                 df: pd.DataFrame, facts: dict) -> str:
    last = df.iloc[-1]
    rsi = last["RSI"]
    macd = last["MACD"]
    macd_sig = last["MACD_signal"]
    ma10 = last["MA10"]
    ma30 = last["MA30"]
    atr = last["ATR"]
    rv = last["Volume"] / df["Volume"].rolling(20).mean().iloc[-1]
    trend = last["TREND"]
    cls = classify(fused)

    return f"""
2.py – Okazje + Wejścia dla {ticker}
Technical Score (60%): {tech:.1f}/100
Fundamental Score (40%): {fund:.1f}/100
Fused Score: {fused:.1f}/100
Klasyfikacja okazji: {cls}

Technika:
Trend: {trend} | RSI: {rsi:.2f} | MACD: {macd:.4f} vs sygnał {macd_sig:.4f}
MA10: {ma10:.2f} | MA30: {ma30:.2f} | RVOL: {rv:.2f} | ATR: {atr:.2f}

Fundamenty:
Cena: {facts['price'] if facts['price'] is not None else 'brak'} |
Market Cap: {facts['market_cap'] if facts['market_cap'] is not None else 'brak'} |
P/E: {facts['pe'] if facts['pe'] is not None else 'brak'}
Spółka: {ticker} | Sektor: {facts['sector'] or 'brak'} | Branża: {facts['industry'] or 'brak'}

Wejście (modelowe):
Entry: {last['Close']:.2f} | SL: {last['Close']*0.92:.2f} |
TP1: {last['Close']*1.08:.2f} | TP2: {last['Close']*1.16:.2f}

To nie jest rekomendacja inwestycyjna. Model ma charakter edukacyjny.
"""

# ==========================
# 5. TELEGRAM
# ==========================
def send_telegram_message(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception:
        pass

# ==========================
# 6. UI LAYER
# ==========================
def init_session_state():
    defaults = {
        "last_ticker": None,
        "last_df": None,
        "last_tech": None,
        "last_fund": None,
        "last_fused": None,
        "last_facts": None,
        "last_report": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def mini_candles(df: pd.DataFrame) -> str:
    df = df.tail(20)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(1.6, 1.0),
        gridspec_kw={"height_ratios": [3, 1]},
        dpi=75
    )

    for i, row in enumerate(df.itertuples()):
        o, h, l, c = row.Open, row.High, row.Low, row.Close
        color = "#00ff00" if c >= o else "#ff0000"
        ax1.vlines(i, l, h, color=color, linewidth=0.8)
        ax1.vlines(i, o, c, color=color, linewidth=2)

    ax1.set_xticks([]); ax1.set_yticks([]); ax1.set_facecolor("#000000")
    ax2.bar(range(len(df)), df["Volume"], color="#666666", width=0.6)
    ax2.set_xticks([]); ax2.set_yticks([]); ax2.set_facecolor("#000000")

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    fig.clf(); plt.close(fig)

    return base64.b64encode(buf.getvalue()).decode("utf-8")

# ==========================
# MAIN
# ==========================
st.set_page_config(page_title="2.py", page_icon="📈", layout="wide")
st.title("2.py – Okazje + Wejścia")

init_session_state()

col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("Ticker (GPW/USA):", "STX.WA")
with col2:
    period = st.selectbox("Okres danych cenowych:", ["1mo", "3mo", "6mo", "1y"], index=1)

if st.button("Analizuj"):
    try:
        df = fetch_price_data(ticker, period)
        df = compute_indicators(df)
        facts = get_fundamentals_and_news(ticker)

        tech = score_technical(df)
        fund = score_fundamental(facts)
        fused = fused_score(tech, fund)
        report = build_report(ticker, tech, fund, fused, df, facts)

        st.session_state.last_ticker = ticker
        st.session_state.last_df = df
        st.session_state.last_tech = tech
        st.session_state.last_fund = fund
        st.session_state.last_fused = fused
        st.session_state.last_facts = facts
        st.session_state.last_report = report

        if classify(fused) == "OKAZJA":
            send_telegram_message(f"[2.py] OKAZJA na {ticker}\n\n{report}")

    except Exception as e:
        st.error(f"Błąd: {e}")

st.write("---")
st.write(f"Ostatni ticker: {st.session_state.last_ticker or 'brak'}")

if st.session_state.last_df is not None:
    df = st.session_state.last_df
    tech = st.session_state.last_tech
    fund = st.session_state.last_fund
    fused = st.session_state.last_fused
    report = st.session_state.last_report

    st.subheader("📈 Wykres cenowy + MA")
    st.line_chart(df[["Close", "MA10", "MA30"]])

    st.subheader("📊 Technika")
    last = df.iloc[-1]
    rv = last["Volume"] / df["Volume"].rolling(20).mean().iloc[-1]
    st.write(f"Trend (MA10 vs MA30): {last['TREND']}")
    st.write(f"RSI (14): {last['RSI']:.2f}")
    st.write(f"MACD: {last['MACD']:.4f}")
    st.write(f"MACD sygnał: {last['MACD_signal']:.4f}")
    st.write(f"RVOL (20): {rv:.2f}")
    st.write(f"ATR (14): {last['ATR']:.2f}")

    st.subheader("🎯 Okazja + Wejście")
    st.write(f"Technical Score: {tech:.1f}/100")
    st.write(f"Fundamental Score: {fund:.1f}/100")
    st.write(f"Fused Score: {fused:.1f}/100")
    st.write(f"Klasyfikacja okazji: {classify(fused)}")

    entry = last["Close"]
    sl = entry * 0.92
    tp1 = entry * 1.08
    tp2 = entry * 1.16

    st.write(f"Entry: {entry:.2f}")
    st.write(f"Stop Loss: {sl:.2f}")
    st.write(f"TP1: {tp1:.2f}")
    st.write(f"TP2: {tp2:.2f}")

    st.subheader("📄 Raport")
    st.text(report)
