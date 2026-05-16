import streamlit as st
from openai import OpenAI
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
st.set_page_config(page_title="3× AI — Swing / Day / Long", layout="centered")

# Bezpieczne pobieranie klucza API
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("Brak klucza OPENAI_API_KEY w st.secrets!")
    st.stop()

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
        df = yf.download(ticker, period="1y", interval="1d", auto_adjust=False)
    else:
        df = yf.download(ticker, period="30d", interval="60m", auto_adjust=False)

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
    
    # POPRAWKA: Konwersja na czysty float, aby uniknąć błędów z typem Series
    close_val = float(last["Close"])
    sma200 = float(last["SMA200"]) if pd.notna(last.get("SMA200")) else np.nan
    sma50 = float(last["SMA50"]) if pd.notna(last.get("SMA50")) else np.nan

    if pd.notna(sma200):
        if close_val > sma200 * 1.01:
            return "bull"
        if close_val < sma200 * 0.99:
            return "bear"

    if pd.notna(sma50):
        if close_val > sma50:
            return "bull"
        if close_val < sma50:
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
    close_val = float(last["Close"])
    upper_val = float(last["BB_upper"])
    lower_val = float(last["BB_lower"])
    
    if close_val > upper_val:
        return ["Cena powyżej górnej wstęgi — silne momentum / możliwe wykupienie."]
    if close_val < lower_val:
        return ["Cena poniżej dolnej wstęgi — możliwe wyprzedanie / odbicie."]
    return ["Cena wewnątrz wstęg — brak skrajnych odchyleń."]


def detect_sma_signals(df: pd.DataFrame):
    last = df.iloc[-1]
    close_val = float(last["Close"])
    res = []
    for w in [20, 50, 100, 200]:
        col = f"SMA{w}"
        if col in df.columns and pd.notna(last[col]):
            sma_val = float(last[col])
            if close_val > sma_val:
                res.append(f"Cena powyżej SMA{w} — wsparcie trendu wzrostowego.")
            else:
                res.append(f"Cena poniżej SMA{w} — presja podażowa.")
    return res


def detect_rsi_signal(df: pd.DataFrame):
    rsi = float(df.iloc[-1]["RSI14"])
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
    close = float(last["Close"])
    atr = float(last["ATR14"])

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
        f"Ostatnie Close: {float(last['Close']):.2f}, High: {float(last['High']):.2f}, Low: {float(last['Low']):.2f}, Volume: {int(last['Volume'])}",
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

    close = float(last["Close"])
    sma50 = float(last["SMA50"]) if pd.notna(last.get("SMA50")) else np.nan
    sma200 = float(last["SMA200"]) if pd.notna(last.get("SMA200")) else np.nan
    rsi = float(last["RSI14"]) if pd.notna(last.get("RSI14")) else np.nan

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


# ================== INTERFEJS UŻYTKOWNIKA (DOKOŃCZENIE) ==================

st.sidebar.header("Ustawienia analizy")
ticker = st.sidebar.text_input("Ticker giełdowy (np. AAPL, TSLA, BTC-USD)", value="AAPL")
timeframe = st.sidebar.selectbox("Interwał", options=["D1", "1H"])

if st.sidebar.button("Uruchom analizę 🚀"):
    with st.spinner("Pobieranie danych giełdowych..."):
        try:
            df_raw = get_ohlc(ticker, timeframe)
            if df_raw.empty:
                st.error("Nie znaleziono danych dla podanego tickera.")
                st.stop()
                
            df_features = add_indicators(df_raw)
            trend_code = detect_trend_from_df(df_features)
            trend_label, trend_css = trend_label_and_css(trend_code)
            summary_text = build_summary_for_ai(df_features, trend_code, timeframe)
            score = compute_trend_score(df_features, trend_code)
            
            # Prezentacja wyników technicznych
            st.subheader(f"Wyniki analizy technicznej dla: {ticker}")
            st.markdown(f'<div class="trend-box {trend_css}">{trend_label} (Score: {score:.0f}/100)</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="info-box"><pre style="color:inherit; background:transparent; margin:0;">{summary_text}</pre></div>', unsafe_allow_html=True)
            
            # Generowanie opinii AI
            st.subheader("🤖 Rekomendacje Modeli AI")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown('<div class="box swing">🎯 SWING TRADER (gpt-4o-mini)</div>', unsafe_allow_html=True)
                with st.spinner("Generowanie..."):
                    st.write(ai_swing(ticker, summary_text))
                    
            with col2:
                st.markdown('<div class="box day">⚡ DAYTRADER (gpt-4o)</div>', unsafe_allow_html=True)
                with st.spinner("Generowanie..."):
                    st.write(ai_day(ticker, summary_text))
                    
            with col3:
                st.markdown('<div class="box long">⏳ LONG-TERM (o3-mini)</div>', unsafe_allow_html=True)
                with st.spinner("Generowanie..."):
                    st.write(ai_long(ticker, summary_text))
                    
        except Exception as e:
            st.error(f"Wystąpił nieoczekiwany błąd: {e}")
