# ==========================================
#  TERMINAL TRADINGOWY 1:1 — analyzer_ultra.py
# ==========================================
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

client = OpenAI()

# Kolory
BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="Terminal Tradingowy", layout="wide")


# ==========================================
#  GLOBALNY NEON DARK MODE — CSS
# ==========================================
def inject_global_css():
    st.markdown(
        f"""
        <style>

        .stApp {{
            background-color: {BACKGROUND};
        }}

        html, body, [class*="css"]  {{
            color: {NEON_YELLOW} !important;
        }}

        .stButton>button {{
            background-color: #111;
            color: {NEON_BLUE};
            border: 1px solid {NEON_BLUE};
            padding: 0.6rem 1.2rem;
            border-radius: 6px;
        }}

        .stButton>button:hover {{
            background-color: {NEON_BLUE};
            color: black;
        }}

        input, select, textarea {{
            background-color: #111 !important;
            color: {NEON_GREEN} !important;
            border: 1px solid {NEON_GREEN} !important;
        }}

        ::-webkit-scrollbar {{
            width: 8px;
        }}

        ::-webkit-scrollbar-thumb {{
            background: {NEON_PINK};
            border-radius: 10px;
        }}

        /* Sidebar widoczny, neonowy */
        section[data-testid="stSidebar"] {{
            background-color: #0a0a0a !important;
            border-right: 2px solid {NEON_BLUE} !important;
        }}

        section[data-testid="stSidebar"] * {{
            color: {NEON_YELLOW} !important;
        }}

        </style>
        """,
        unsafe_allow_html=True
    )


# ==========================================
#  SIDEBAR — USTAWIENIA
# ==========================================
def sidebar():
    st.sidebar.title("⚙️ Ustawienia")

    st.sidebar.markdown("### Dane rynkowe")
    history_period = st.sidebar.selectbox(
        "Zakres danych:",
        ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
        index=2
    )

    interval = st.sidebar.selectbox(
        "Interwał:",
        ["1m", "5m", "15m", "30m", "1h", "1d"],
        index=5
    )

    live_data = st.sidebar.checkbox("Dane live", value=False)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Wskaźniki")

    show_sma = st.sidebar.checkbox("SMA", value=True)
    show_rsi = st.sidebar.checkbox("RSI", value=True)
    show_boll = st.sidebar.checkbox("Bollinger Bands", value=True)
    show_atr = st.sidebar.checkbox("ATR", value=True)
    show_fibo = st.sidebar.checkbox("Fibonacci", value=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### AI")

    ai_model = st.sidebar.selectbox(
        "Model AI:",
        ["gpt-4o-mini", "gpt-4o", "gpt-4.1"],
        index=0
    )

    return {
        "history_period": history_period,
        "interval": interval,
        "live_data": live_data,
        "ai_model": ai_model,
        "show_sma": show_sma,
        "show_rsi": show_rsi,
        "show_boll": show_boll,
        "show_atr": show_atr,
        "show_fibo": show_fibo
    }


# ==========================================
#  SEKCJA 2 — DANE, WSKAŹNIKI, BID/ASK, FX, RYZYKO
# ==========================================
def get_price_data(symbol, period, interval, live=False):
    df = yf.download(symbol, period=period, interval=interval)
    if df is None or df.empty:
        return pd.DataFrame()
    df.dropna(inplace=True)
    return df


def sma(series, length):
    return series.rolling(length).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger(series, length=20, num_std=2):
    ma = series.rolling(length).mean()
    std = series.rolling(length).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    return ma, upper, lower


def atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def fibonacci_levels(df):
    high = df["High"].max()
    low = df["Low"].min()
    diff = high - low
    return {
        "0%": high,
        "23.6%": high - diff * 0.236,
        "38.2%": high - diff * 0.382,
        "50%": high - diff * 0.5,
        "61.8%": high - diff * 0.618,
        "100%": low
    }


def detect_trend(series):
    """
    Stabilna wersja — działa dla każdej serii.
    Trend na podstawie zmiany ceny w ostatnich N świecach.
    """
    series = series.dropna()

    if len(series) < 3:
        return "NEUTRAL"

    step = min(10, len(series) - 1)
    close_now = float(series.iloc[-1])
    close_prev = float(series.iloc[-step])

    if close_now > close_prev:
        return "BULL"
    elif close_now < close_prev:
        return "BEAR"
    else:
        return "NEUTRAL"


def detect_multi_trend(df):
    close = df["Close"].dropna()

    if len(close) < 5:
        return {
            "short_term": "NEUTRAL",
            "medium_term": "NEUTRAL",
            "long_term": "NEUTRAL",
            "momentum": 0.0,
            "strength": 0.0,
        }

    short = detect_trend(close[-20:])
    medium = detect_trend(close[-50:])
    long = detect_trend(close[-200:])

    momentum = float(close.diff().iloc[-1])
    strength = abs(momentum)

    return {
        "short_term": short,
        "medium_term": medium,
        "long_term": long,
        "momentum": momentum,
        "strength": strength,
    }


def get_bid_ask(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        bid = info.get("bid")
        ask = info.get("ask")
        if bid is None or ask is None:
            return None, None, None
        return float(bid), float(ask), float(ask - bid)
    except Exception:
        return None, None, None


def get_usd_pln():
    try:
        df = yf.download("USDPLN=X", period="5d", interval="1d")
        if df is None or df.empty:
            return 4.00
        return float(df["Close"].iloc[-1])
    except Exception:
        return 4.00


def calculate_sl_tp(df, atr_value, trend):
    close = df["Close"].iloc[-1]

    if trend == "BULL":
        sl = close - atr_value * 2
        tp = close + atr_value * 3
    elif trend == "BEAR":
        sl = close + atr_value * 2
        tp = close - atr_value * 3
    else:
        sl = close - atr_value
        tp = close + atr_value

    neutral = (sl + tp) / 2

    if atr_value < close * 0.005:
        risk = "LOW"
    elif atr_value < close * 0.015:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    return {
        "close": close,
        "sl": sl,
        "tp": tp,
        "neutral": neutral,
        "risk": risk
    }


def position_risk(close, atr_value, spread, qty, sl):
    risk_per_share = abs(close - sl) + (spread or 0)
    total_risk = risk_per_share * qty
    position_value = close * qty
    if position_value == 0:
        risk_percent = 0
    else:
        risk_percent = (total_risk / position_value) * 100

    if risk_percent < 1:
        level = "LOW"
    elif risk_percent < 3:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "position_value": position_value,
        "risk_per_share": risk_per_share,
        "total_risk": total_risk,
        "risk_percent": risk_percent,
        "level": level
    }


# ==========================================
#  SEKCJA 3 — WYKRESY
# ==========================================
def show_price_chart(df, symbol):
    st.subheader(f"📈 Wykres ceny — {symbol}")

    fig = go.Figure()
    fig.add_candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"]
    )
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)


def show_sma_chart(df):
    df["SMA20"] = sma(df["Close"], 20)
    st.line_chart(df["SMA20"])


def show_rsi_chart(df):
    df["RSI"] = rsi(df["Close"])
    st.line_chart(df["RSI"])


def show_bollinger_chart(df):
    ma, upper, lower = bollinger(df["Close"])
    st.line_chart({"MA": ma, "Upper": upper, "Lower": lower})


def show_atr_chart(df):
    df["ATR"] = atr(df)
    st.line_chart(df["ATR"])


def show_fibonacci_levels(df):
    levels = fibonacci_levels(df)
    for lvl, val in levels.items():
        st.write(f"{lvl}: {val:.2f}")


def charts_window(symbol, settings):
    df = get_price_data(symbol, settings["history_period"], settings["interval"], settings["live_data"])
    if df.empty:
        st.error("Brak danych dla tego symbolu.")
        return

    show_price_chart(df, symbol)

    if settings["show_sma"]:
        show_sma_chart(df)
    if settings["show_rsi"]:
        show_rsi_chart(df)
    if settings["show_boll"]:
        show_bollinger_chart(df)
    if settings["show_atr"]:
        show_atr_chart(df)
    if settings["show_fibo"]:
        show_fibonacci_levels(df)


# ==========================================
#  SEKCJA 4 — SKANER RYNKU
# ==========================================
def scanner_window(settings):
    st.subheader("📡 Skaner rynku")

    if "symbols_list" not in st.session_state:
        st.session_state.symbols_list = []

    new_symbols = st.text_input("Dodaj symbole (przecinki):")

    if st.button("➕ Dodaj"):
        if new_symbols.strip():
            parsed = [s.strip().upper() for s in new_symbols.split(",") if s.strip()]
            for sym in parsed:
                if sym not in st.session_state.symbols_list:
                    st.session_state.symbols_list.append(sym)

    st.markdown("### Lista spółek:")

    for sym in list(st.session_state.symbols_list):
        col1, col2 = st.columns([4, 1])
        col1.write(f"🔹 {sym}")
        if col2.button(f"❌", key=f"del_{sym}"):
            st.session_state.symbols_list.remove(sym)
            st.experimental_rerun()

    if st.button("🔎 Skanuj rynek"):
        for sym in st.session_state.symbols_list:
            st.markdown(f"### 🟦 {sym}")
            df = get_price_data(sym, settings["history_period"], settings["interval"], settings["live_data"])
            if df.empty:
                st.error("Brak danych.")
                continue

            trend = detect_trend(df["Close"])
            last_close = df["Close"].iloc[-1]
            volume = df["Volume"].iloc[-1]

            st.write(f"Cena: {last_close:.2f}")
            st.write(f"Wolumen: {volume}")
            st.write(f"Trend: {trend}")


# ==========================================
#  SEKCJA 5 — AI KOMENTARZ + AI CZAT
# ==========================================
def ai_commentary(symbol, df, indicators, model_name):
    prompt = f"""
    Przeanalizuj spółkę {symbol} na podstawie:
    Cena: {df['Close'].iloc[-1]}
    Trend: {indicators['trend']}
    RSI: {indicators['rsi']}
    ATR: {indicators['atr']}
    Momentum: {indicators['momentum']}
    Siła trendu: {indicators['strength']}
    Napisz krótki, konkretny komentarz tradingowy.
    """

    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message["content"]


def ai_commentary_window(symbol, settings):
    st.subheader("🤖 AI Komentarz")

    df = get_price_data(symbol, settings["history_period"], settings["interval"], settings["live_data"])
    if df.empty:
        st.error("Brak danych.")
        return

    df["RSI"] = rsi(df["Close"])
    df["ATR"] = atr(df)
    trends = detect_multi_trend(df)

    indicators = {
        "trend": trends["short_term"],
        "rsi": df["RSI"].iloc[-1],
        "atr": df["ATR"].iloc[-1],
        "momentum": trends["momentum"],
        "strength": trends["strength"]
    }

    comment = ai_commentary(symbol, df, indicators, settings["ai_model"])
    st.write(comment)


def ai_chat_window(settings):
    st.subheader("💬 Czat AI")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    user_msg = st.text_input("Wpisz wiadomość:")

    if st.button("Wyślij"):
        if user_msg.strip():
            response = client.chat.completions.create(
                model=settings["ai_model"],
                messages=[
                    {"role": "system", "content": "Jesteś pomocnym asystentem tradingowym."},
                    *st.session_state.chat_history,
                    {"role": "user", "content": user_msg}
                ]
            )
            ai_msg = response.choices[0].message["content"]
            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            st.session_state.chat_history.append({"role": "assistant", "content": ai_msg})

    for msg in st.session_state.chat_history:
        role = "Ty" if msg["role"] == "user" else "AI"
        st.write(f"**{role}:** {msg['content']}")


# ==========================================
#  SEKCJA 6 — TRENDY
# ==========================================
def trends_window(symbol, settings):
    st.subheader(f"📊 Trendy — {symbol}")

    df = get_price_data(symbol, settings["history_period"], settings["interval"], settings["live_data"])
    if df.empty:
        st.error("Brak danych.")
        return

    trends = detect_multi_trend(df)

    st.write(f"Krótki: {trends['short_term']}")
    st.write(f"Średni: {trends['medium_term']}")
    st.write(f"Długi: {trends['long_term']}")
    st.write(f"Momentum: {trends['momentum']:.2f}")
    st.write(f"Siła trendu: {trends['strength']:.2f}")


# ==========================================
#  SEKCJA 7 — SL / TP
# ==========================================
def sl_tp_window(symbol, settings):
    st.subheader(f"🎯 SL / TP — {symbol}")

    df = get_price_data(symbol, settings["history_period"], settings["interval"], settings["live_data"])
    if df.empty:
        st.error("Brak danych.")
        return

    df["ATR"] = atr(df)
    atr_value = df["ATR"].iloc[-1]
    trend = detect_trend(df["Close"])

    results = calculate_sl_tp(df, atr_value, trend)

    st.write(f"Cena: {results['close']:.2f}")
    st.write(f"SL: {results['sl']:.2f}")
    st.write(f"TP: {results['tp']:.2f}")
    st.write(f"Neutral: {results['neutral']:.2f}")
    st.write(f"Ryzyko systemowe: {results['risk']}")

    qty = st.number_input("Ilość akcji:", min_value=1, value=1)

    bid, ask, spread = get_bid_ask(symbol)
    if bid is None:
        st.error("Brak danych BID/ASK.")
        return

    risk = position_risk(results["close"], atr_value, spread, qty, results["sl"])

    st.write(f"Wartość pozycji: {risk['position_value']:.2f}")
    st.write(f"Ryzyko na akcję: {risk['risk_per_share']:.2f}")
    st.write(f"Ryzyko całkowite: {risk['total_risk']:.2f}")
    st.write(f"Ryzyko %: {risk['risk_percent']:.2f}%")
    st.write(f"Poziom ryzyka: {risk['level']}")


# ==========================================
#  SEKCJA 8 — PORTFEL
# ==========================================
def portfolio_window():
    st.subheader("💼 Portfel")

    if "portfolio" not in st.session_state:
        st.session_state.portfolio = []

    usd_pln = float(get_usd_pln())
    st.write(f"Kurs USD/PLN: {usd_pln:.2f}")

    symbol = st.text_input("Symbol:")
    qty = st.number_input("Ilość:", min_value=0.0)
    price_usd = st.number_input("Cena USD:", min_value=0.0)

    if st.button("➕ Dodaj"):
        if symbol and qty > 0 and price_usd > 0:
            st.session_state.portfolio.append({
                "symbol": symbol.upper(),
                "qty": qty,
                "price_pln": price_usd * usd_pln
            })

    total_value = 0.0
    for pos in list(st.session_state.portfolio):
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(f"{pos['symbol']} — {pos['qty']} szt.")
        col2.write(f"{pos['price_pln']:.2f} PLN")
        total_value += pos["price_pln"]
        if col3.button("❌", key=f"del_{pos['symbol']}"):
            st.session_state.portfolio.remove(pos)
            st.experimental_rerun()

    st.markdown("---")
    st.write(f"Łączna wartość portfela (na podstawie cen wejścia): {total_value:.2f} PLN")


# ==========================================
#  SEKCJA 9 — BID / ASK / SPREAD
# ==========================================
def bidask_window(symbol):
    st.subheader(f"💹 BID / ASK — {symbol}")

    bid, ask, spread = get_bid_ask(symbol)

    if bid is None:
        st.error("Brak danych BID/ASK.")
        return

    st.markdown("---")
    st.write(f"**BID:** {bid}")
    st.write(f"**ASK:** {ask}")
    st.write(f"**Spread:** {spread}")


# ==========================================
#  SEKCJA 10 — GŁÓWNY INTERFEJS (ROUTING)
# ==========================================
def main_app():
    inject_global_css()
    settings = sidebar()

    st.title("💹 Terminal Tradingowy — 1:1")
    st.markdown("---")

    module = st.selectbox(
        "Wybierz moduł:",
        [
            "📈 Wykresy i wskaźniki",
            "📡 Skaner rynku",
            "🤖 AI komentarz",
            "💬 AI czat",
            "📊 Trendy",
            "🎯 SL / TP",
            "💼 Portfel",
            "💹 BID / ASK / Spread"
        ]
    )

    st.markdown("---")

    symbol_required = module in [
        "📈 Wykresy i wskaźniki",
        "🤖 AI komentarz",
        "📊 Trendy",
        "🎯 SL / TP",
        "💹 BID / ASK / Spread"
    ]

    symbol = None
    if symbol_required:
        symbol = st.text_input("Podaj symbol spółki:", placeholder="np. AAPL")
        if not symbol:
            st.info("Wpisz symbol, aby kontynuować.")
            return
        symbol = symbol.upper()

    if module == "📈 Wykresy i wskaźniki":
        charts_window(symbol, settings)
    elif module == "📡 Skaner rynku":
        scanner_window(settings)
    elif module == "🤖 AI komentarz":
        ai_commentary_window(symbol, settings)
    elif module == "💬 AI czat":
        ai_chat_window(settings)
    elif module == "📊 Trendy":
        trends_window(symbol, settings)
    elif module == "🎯 SL / TP":
        sl_tp_window(symbol, settings)
    elif module == "💼 Portfel":
        portfolio_window()
    elif module == "💹 BID / ASK / Spread":
        bidask_window(symbol)


# ==========================================
#  START APLIKACJI
# ==========================================
if __name__ == "__main__":
    main_app()
