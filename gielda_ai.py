import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from openai import OpenAI
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== 1. KONFIGURACJA STREAMLIT (MUSI BYĆ PIERWSZA!) ==================
st.set_page_config(page_title="3× AI — Swing / Day / Long", layout="centered")

# Teraz bezpiecznie możemy inicjalizować klienta OpenAI i pobierać sekrety
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ================== STYLE CSS ==================
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
    # Dla o3-mini usuwamy temperature=0.1, aby uniknąć błędów walidacji API
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

    df = df.dropna()
    
    # Zabezpieczenie przed MultiIndex w nowym yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
        
    df.columns = df.columns.str.strip()
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    # Konwersja na typ float, gdyby yfinance zwrócił obiekty
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = df[col].astype(float)
        
    close = df["Close"]

    # SMA
    for w in [20, 50, 100, 200]:
        df[f"SMA{w}"] = close.rolling(w).mean()

    # Bollinger
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["BB_upper"] = ma20 + 2 * std20
    df["BB_lower"] = ma20 - 2 * std20

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


# ================== FUNKCJE POMOCNICZE I TRENDY ==================

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
        if col in last and pd.notna(last[col]):
            if last["Close"] > last[col]:
                res.append(f"Cena powyżej SMA{w} — wsparcie trendu.")
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


# ================== WYKRES MULTICHART (DOKOŃCZONY) ==================

def plot_multichart(df: pd.DataFrame):
    df = df.dropna().tail(120).copy()
    x = df.index

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.55, 0.20, 0.25]
    )

    # 1. Świece (Row 1)
    fig.add_trace(go.Candlestick(
        x=x,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        increasing_line_color="lime",
        decreasing_line_color="red",
        name="Cena"
    ), row=1, col=1)

    # Wstęgi Bollingera (Row 1)
    fig.add_trace(go.Scatter(x=x, y=df["BB_upper"], line=dict(color="rgba(173,216,230,0.5)", dash="dash"), name="BB Upper"), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["BB_lower"], line=dict(color="rgba(173,216,230,0.5)", dash="dash"), name="BB Lower"), row=1, col=1)

    # Średnie kroczące SMA (Row 1)
    for w, color in [(20, "orange"), (50, "cyan"), (100, "violet"), (200, "gray")]:
        col = f"SMA{w}"
        if df[col].notna().any():
            fig.add_trace(go.Scatter(
                x=x, y=df[col],
                line=dict(color=color, width=1.3),
                name=f"SMA {w}"
            ), row=1, col=1)

    # 2. Wolumen (Row 2)
    fig.add_trace(go.Bar(
        x=x, y=df["Volume"],
        marker_color="dodgerblue",
        name="Wolumen"
    ), row=2, col=1)

    # 3. RSI (Row 3)
    fig.add_trace(go.Scatter(
        x=x, y=df["RSI14"],
        line=dict(color="purple", width=1.5),
        name="RSI14"
    ), row=3, col=1)
    
    # Linie poziomów RSI (30, 50, 70)
    fig.add_shape(type="line", x0=x[0], y0=70, x1=x[-1], y1=70, line=dict(color="red", dash="dash"), row=3, col=1)
    fig.add_shape(type="line", x0=x[0], y0=30, x1=x[-1], y1=30, line=dict(color="green", dash="dash"), row=3, col=1)

    fig.update_layout(
        height=700,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        margin=dict(l=10, r=10, t=30, b=10)
    )
    return fig


# ================== INTERFEJS UŻYTKOWNIKA STREAMLIT ==================

ticker_input = st.text_input("Wpisz ticker giełdowy (np. AAPL, TSLA, BTC-USD):", value="AAPL").upper()
timeframe = st.selectbox("Wybierz interwał (Timeframe):", ["D1", "1H"])

if st.button("Uruchom analizę"):
    with st.spinner("Pobieranie danych i generowanie analizy przez AI..."):
        try:
            # 1. Pobieranie danych
            raw_data = get_ohlc(ticker_input, timeframe)
            
            if raw_data.empty:
                st.error("Nie znaleziono danych dla podanego tickera. Sprawdź symbol.")
            else:
                # 2. Obliczanie wskaźników
                df_with_indicators = add_indicators(raw_data)
                trend = detect_trend_from_df(df_with_indicators)
                label, css_class = trend_label_and_css(trend)
                
                # 3. Wyświetlanie trendu
                st.markdown(f'<div class="trend-box {css_class}">Obecny stan techniczny: <b>{label}</b></div>', unsafe_allow_html=True)
                
                # 4. Budowanie podsumowania tekstowego dla modeli LLM
                ai_summary = build_summary_for_ai(df_with_indicators, trend, timeframe)
                
                # Wyświetlenie wyciągu danych w sekcji info
                with st.expander("Zobacz surowe dane wysyłane do AI"):
                    st.text(ai_summary)
                
                # 5. Generowanie odpowiedzi z 3 modeli AI równolegle/kolejno
                st.subheader("🤖 Rekomendacje Modeli AI")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown('<div class="box swing">⚡ SWING TRADING (gpt-4o-mini)</div>', unsafe_allow_html=True)
                    res_swing = ai_swing(ticker_input, ai_summary)
                    st.markdown(f'<div class="info-box">{res_swing}</div>', unsafe_allow_html=True)
                    
                with col2:
                    st.markdown('<div class="box day">🔥 DAYTRADING (gpt-4o)</div>', unsafe_allow_html=True)
                    res_day = ai_day(ticker_input, ai_summary)
                    st.markdown(f'<div class="info-box">{res_day}</div>', unsafe_allow_html=True)
                    
                with col3:
                    st.markdown('<div class="box long">🏛️ LONG-TERM (o3-mini)</div>', unsafe_allow_html=True)
                    res_long = ai_long(ticker_input, ai_summary)
                    st.markdown(f'<div class="info-box">{res_long}</div>', unsafe_allow_html=True)
                
                # 6. Rysowanie wykresu
                st.subheader("📊 Wykres techniczny (Ostatnie 120 świec)")
                chart_fig = plot_multichart(df_with_indicators)
                st.plotly_chart(chart_fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"Wystąpił nieoczekiwany błąd: {e}")
