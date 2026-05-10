
# ==========================================
#  TERMINAL TRADINGOWY — analyzer_ultra.py
#  Wersja: spójna, bez modułów, z normalizacją danych
# ==========================================
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

client = OpenAI()

BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="Terminal Tradingowy", layout="wide")


# ==========================================
#  GLOBALNY STYL
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
        section[data-testid="stSidebar"] {{
            background-color: #0a0a0a !important;
            border-right: 2px solid {NEON_BLUE} !important;
        }}
        section[data-testid="stSidebar"] * {{
            color: {NEON_YELLOW} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==========================================
#  SIDEBAR
# ==========================================
def sidebar():
    st.sidebar.title("⚙️ Ustawienia")

    st.sidebar.markdown("### Symbol")
    symbol = st.sidebar.text_input("Podaj symbol spółki:", placeholder="np. AAPL").upper()

    st.sidebar.markdown("### Dane rynkowe")
    history_period = st.sidebar.selectbox(
        "Zakres danych:",
        ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
        index=2,
    )

    interval = st.sidebar.selectbox(
        "Interwał:",
        ["1m", "5m", "15m", "30m", "1h", "1d"],
        index=5,
    )

    live_data = st.sidebar.checkbox("Dane live", value=False)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Wskaźniki na wykresie")

    show_sma = st.sidebar.checkbox("SMA", value=True)
    show_rsi = st.sidebar.checkbox("RSI", value=True)
    show_boll = st.sidebar.checkbox("Bollinger Bands", value=True)
    show_atr = st.sidebar.checkbox("ATR", value=True)
    show_fibo = st.sidebar.checkbox("Fibonacci", value=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Sekcje widoczne")

    show_scanner = st.sidebar.checkbox("📡 Skaner rynku", value=True)
    show_ai_comment = st.sidebar.checkbox("🤖 AI komentarz", value=True)
    show_ai_chat = st.sidebar.checkbox("💬 AI czat", value=True)
    show_trends = st.sidebar.checkbox("📊 Trendy", value=True)
    show_sl_tp = st.sidebar.checkbox("🎯 SL / TP", value=True)
    show_portfolio = st.sidebar.checkbox("💼 Portfel", value=True)
    show_bidask = st.sidebar.checkbox("💹 BID / ASK / Spread", value=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### AI")

    ai_model = st.sidebar.selectbox(
        "Model AI:",
        ["gpt-4o-mini", "gpt-4o", "gpt-4.1"],
        index=0,
    )

    return {
        "symbol": symbol,
        "history_period": history_period,
        "interval": interval,
        "live_data": live_data,
        "ai_model": ai_model,
        "show_sma": show_sma,
        "show_rsi": show_rsi,
        "show_boll": show_boll,
        "show_atr": show_atr,
        "show_fibo": show_fibo,
        "show_scanner": show_scanner,
        "show_ai_comment": show_ai_comment,
        "show_ai_chat": show_ai_chat,
        "show_trends": show_trends,
        "show_sl_tp": show_sl_tp,
        "show_portfolio": show_portfolio,
        "show_bidask": show_bidask,
    }


# ==========================================
#  DANE I WSKAŹNIKI
# ==========================================
def _to_scalar(x):
    if isinstance(x, (list, tuple)):
        return x[0]
    if hasattr(x, "item"):
        try:
            return x.item()
        except Exception:
            return x
    return x


def get_price_data(symbol, period, interval, live=False):
    if not symbol:
        return pd.DataFrame()

    df = yf.download(symbol, period=period, interval=interval)
    if df is None or df.empty:
        return pd.DataFrame()

    # normalizacja wszystkich kolumn do 1D float
    for col in df.columns:
        df[col] = df[col].apply(_to_scalar)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna()
    return df


def sma(series, length):
    return series.rolling(length).mean()


def rsi(series, period=14):
    s = pd.to_numeric(pd.Series(series), errors="coerce")
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger(series, length=20, num_std=2):
    s = pd.to_numeric(pd.Series(series), errors="coerce")
    ma = s.rolling(length).mean()
    std = s.rolling(length).std()
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
    high = df["High"]
    low = df["Low"]

    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")

    high_val = high.max()
    low_val = low.min()

    if pd.isna(high_val) or pd.isna(low_val):
        return {lvl: None for lvl in ["0%", "23.6%", "38.2%", "50%", "61.8%", "100%"]}

    diff = high_val - low_val

    return {
        "0%": high_val,
        "23.6%": high_val - diff * 0.236,
        "38.2%": high_val - diff * 0.382,
        "50%": high_val - diff * 0.5,
        "61.8%": high_val - diff * 0.618,
        "100%": low_val,
    }


def detect_trend(series):
    if series is None:
        return "NEUTRAL"

    s = pd.to_numeric(pd.Series(series), errors="coerce").dropna()

    if len(s) < 3:
        return "NEUTRAL"

    step = min(10, len(s) - 1)
    close_now = float(s.iloc[-1])
    close_prev = float(s.iloc[-step])

    if close_now > close_prev:
        return "BULL"
    elif close_now < close_prev:
        return "BEAR"
    else:
        return "NEUTRAL"


def detect_multi_trend(df):
    if df is None or df.empty or "Close" not in df.columns:
        return {
            "short_term": "NEUTRAL",
            "medium_term": "NEUTRAL",
            "long_term": "NEUTRAL",
            "momentum": 0.0,
            "strength": 0.0,
        }

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()

    if len(close) < 5:
        return {
            "short_term": "NEUTRAL",
            "medium_term": "NEUTRAL",
            "long_term": "NEUTRAL",
            "momentum": 0.0,
            "strength": 0.0,
        }

    momentum = float(close.diff().iloc[-1])
    strength = abs(momentum)

    return {
        "short_term": detect_trend(close[-20:]),
        "medium_term": detect_trend(close[-50:]),
        "long_term": detect_trend(close[-200:]),
        "momentum": momentum,
        "strength": strength,
    }


def get_bid_ask(symbol):
    if not symbol:
        return None, None, None
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
    close = float(df["Close"].iloc[-1])

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
        "risk": risk,
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
        "level": level,
    }


# ==========================================
#  WYKRESY
# ==========================================
def show_price_chart(df, symbol):
    st.subheader(f"📈 Wykres ceny — {symbol}")

    fig = go.Figure()
    fig.add_candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
    )
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)


def show_sma_chart(df):
    df = df.copy()
    df["SMA20"] = sma(df["Close"], 20)
    st.line_chart(df["SMA20"])


def show_rsi_chart(df):
    df = df.copy()
    df["RSI"] = rsi(df["Close"])
    st.line_chart(df["RSI"])


def show_bollinger_chart(df):
    close = df["Close"]
    ma, upper, lower = bollinger(close)

    bb_df = pd.DataFrame(
        {
            "MA": ma.values,
            "Upper": upper.values,
            "Lower": lower.values,
        },
        index=df.index,
    ).dropna()

    if bb_df.empty:
        st.info("Za mało danych, żeby policzyć Bollinger Bands.")
        return

    st.line_chart(bb_df)


def show_atr_chart(df):
    df = df.copy()
    df["ATR"] = atr(df)
    st.line_chart(df["ATR"])


def show_fibonacci_levels(df):
    st.subheader("🔢 Poziomy Fibonacciego")

    levels = fibonacci_levels(df)

    for lvl, val in levels.items():
        if val is None or pd.isna(val):
            st.write(f"{lvl}: brak danych")
        else:
            st.write(f"{lvl}: {float(val):.2f}")


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
#  SKANER
# ==========================================
def scanner_window(settings):
    st.subheader("📡 Skaner rynku")

    if "symbols_list" not in st.session_state:
        st.session_state.symbols_list = []

    new_symbols = st.text_input("Dodaj symbole (przecinki):", key="scanner_input")

    if st.button("➕ Dodaj", key="scanner_add"):
        if new_symbols.strip():
            parsed = [s.strip().upper() for s in new_symbols.split(",") if s.strip()]
            for sym in parsed:
                if sym not in st.session_state.symbols_list:
                    st.session_state.symbols_list.append(sym)

    st.markdown("### Lista spółek:")

    for sym in list(st.session_state.symbols_list):
        col1, col2 = st.columns([4, 1])
        col1.write(f"🔹 {sym}")
        if col2.button("❌", key=f"del_{sym}"):
            st.session_state.symbols_list.remove(sym)
            st.experimental_rerun()

    if st.button("🔎 Skanuj rynek", key="scanner_run"):
        for sym in st.session_state.symbols_list:
            st.markdown(f"### 🟦 {sym}")
            df = get_price_data(sym, settings["history_period"], settings["interval"], settings["live_data"])
            if df.empty:
                st.error("Brak danych.")
                continue

            trend = detect_trend(df["Close"])

            last_close = float(df["Close"].iloc[-1])
            volume = float(df["Volume"].iloc[-1])

            st.write(f"Cena: {last_close:.2f}")
            st.write(f"Wolumen: {int(volume)}")
            st.write(f"Trend: {trend}")


# ==========================================
#  AI KOMENTARZ + CZAT
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
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content


def ai_commentary_window(symbol, settings):
    st.subheader("🤖 AI Komentarz")

    df = get_price_data(symbol, settings["history_period"], settings["interval"], settings["live_data"])
    if df.empty:
        st.error("Brak danych.")
        return

    df = df.copy()
    df["RSI"] = rsi(df["Close"])
    df["ATR"] = atr(df)
    trends = detect_multi_trend(df)

    indicators = {
        "trend": trends["short_term"],
        "rsi": df["RSI"].iloc[-1],
        "atr": df["ATR"].iloc[-1],
        "momentum": trends["momentum"],
        "strength": trends["strength"],
    }

    comment = ai_commentary(symbol, df, indicators, settings["ai_model"])
    st.write(comment)


def ai_chat_window(settings):
    st.subheader("💬 Czat AI")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    user_msg = st.text_input("Wpisz wiadomość:", key="chat_input")

    if st.button("Wyślij", key="chat_send"):
        if user_msg.strip():
            response = client.chat.completions.create(
                model=settings["ai_model"],
                messages=[
                    {"role": "system", "content": "Jesteś pomocnym asystentem tradingowym."},
                    *st.session_state.chat_history,
                    {"role": "user", "content": user_msg},
                ],
            )
            ai_msg = response.choices[0].message.content
            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            st.session_state.chat_history.append({"role": "assistant", "content": ai_msg})

    for msg in st.session_state.chat_history:
        role = "Ty" if msg["role"] == "user" else "AI"
        st.write(f"**{role}:** {msg['content']}")


# ==========================================
#  TRENDY
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
#  SL / TP
# ==========================================
def sl_tp_window(symbol, settings):
    st.subheader(f"🎯 SL / TP — {symbol}")

    df = get_price_data(symbol, settings["history_period"], settings["interval"], settings["live_data"])
    if df.empty:
        st.error("Brak danych.")
        return

    df = df.copy()
    df["ATR"] = atr(df)
    atr_value = float(df["ATR"].iloc[-1])
    trend = detect_trend(df["Close"])

    results = calculate_sl_tp(df, atr_value, trend)

    st.write(f"Cena: {results['close']:.2f}")
    st.write(f"SL: {results['sl']:.2f}")
    st.write(f"TP: {results['tp']:.2f}")
    st.write(f"Neutral: {results['neutral']:.2f}")
    st.write(f"Ryzyko systemowe: {results['risk']}")

    qty = st.number_input("Ilość akcji:", min_value=1, value=1, key="sl_qty")

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
#  PORTFEL
# ==========================================
def portfolio_window():
    st.subheader("💼 Portfel")

    if "portfolio" not in st.session_state:
        st.session_state.portfolio = []

    usd_pln = float(get_usd_pln())
    st.write(f"Kurs USD/PLN: {usd_pln:.2f}")

    symbol = st.text_input("Symbol:", key="pf_symbol")
    qty = st.number_input("Ilość:", min_value=0.0, key="pf_qty")
    price_usd = st.number_input("Cena USD:", min_value=0.0, key="pf_price")

    if st.button("➕ Dodaj", key="pf_add"):
        if symbol and qty > 0 and price_usd > 0:
            st.session_state.portfolio.append(
                {
                    "symbol": symbol.upper(),
                    "qty": qty,
                    "price_pln": price_usd * usd_pln,
                }
            )

    total_value = 0.0
    for pos in list(st.session_state.portfolio):
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(f"{pos['symbol']} — {pos['qty']} szt.")
        col2.write(f"{pos['price_pln']:.2f} PLN")
        total_value += pos["price_pln"]
        if col3.button("❌", key=f"pf_del_{pos['symbol']}"):
            st.session_state.portfolio.remove(pos)
            st.experimental_rerun()

    st.markdown("---")
    st.write(f"Łączna wartość portfela (na podstawie cen wejścia): {total_value:.2f} PLN")


# ==========================================
#  BID / ASK
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
#  MAIN
# ==========================================
def main_app():
    inject_global_css()
    settings = sidebar()

    st.title("💹 Terminal Tradingowy — 1:1 (bez modułów)")
    st.markdown("---")

    symbol = settings["symbol"]

    if symbol:
        charts_window(symbol, settings)
    else:
        st.info("Podaj symbol w panelu bocznym, aby zobaczyć wykres i analizy.")

    st.markdown("---")

    if settings["show_scanner"]:
        scanner_window(settings)
        st.markdown("---")

    if settings["show_trends"] and symbol:
        trends_window(symbol, settings)
        st.markdown("---")

    if settings["show_sl_tp"] and symbol:
        sl_tp_window(symbol, settings)
        st.markdown("---")

    if settings["show_ai_comment"] and symbol:
        ai_commentary_window(symbol, settings)
        st.markdown("---")

    if settings["show_ai_chat"]:
        ai_chat_window(settings)
        st.markdown("---")

    if settings["show_portfolio"]:
        portfolio_window()
        st.markdown("---")

    if settings["show_bidask"] and symbol:
        bidask_window(symbol)


if __name__ == "__main__":
    main_app()
