# ==========================================
#  IMPORTY I KONFIGURACJA APLIKACJI
# ==========================================
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from openai import OpenAI
import streamlit as st
from openai import OpenAI
## ==========================================
#  KLIENT AI — KLUCZ W STREAMLIT SECRETS
# ==========================================


# Klucz pobierany automatycznie z .streamlit/secrets.toml
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

client = OpenAI()

# ==========================================
#  KOLORY I STYL NEONOWY
# ==========================================
NEON_BLUE = "#00baff"
NEON_PINK = "#ff00ff"
NEON_GREEN = "#39ff14"
NEON_YELLOW = "#f5ff00"
BACKGROUND = "#0a0a0f"

# ==========================================
#  USTAWIENIA STRONY
# ==========================================
st.set_page_config(
    page_title="Terminal Tradingowy",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
#  FUNKCJE POMOCNICZE: MODELE AI
# ==========================================
def get_ai_model(name: str) -> str:
    if name == "AI‑1":
        return "gpt-4o-mini"
    if name == "AI‑2":
        return "gpt-4o"
    if name == "AI‑3":
        return "gpt-o3-mini"
    if name == "AI‑4":
        return "gpt-o1"
    return "gpt-4o-mini"

# ==========================================
#  PANEL BOCZNY (SIDEBAR)
# ==========================================
def sidebar():
    st.sidebar.title("⚙️ Ustawienia")

    # Auto-odświeżanie
    refresh = st.sidebar.number_input(
        "🔄 Auto-odświeżanie (minuty)",
        min_value=1,
        max_value=120,
        value=5
    )

    st.sidebar.markdown("---")

    # Skaner i dane
    st.sidebar.subheader("📡 Skaner i dane")

    history_period = st.sidebar.selectbox(
        "Okres historyczny",
        ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"]
    )

    live_data = st.sidebar.checkbox("Używaj danych bieżących (real-time)")

    interval = st.sidebar.selectbox(
        "Interwał",
        ["30m", "1h", "2h", "4h", "1d", "1wk"]
    )

    st.sidebar.markdown("---")

    # Wykresy i wskaźniki
    st.sidebar.subheader("📊 Wykresy i wskaźniki")

    show_sma = st.sidebar.checkbox("SMA")
    show_rsi = st.sidebar.checkbox("RSI")
    show_boll = st.sidebar.checkbox("Bollinger Bands")
    show_atr = st.sidebar.checkbox("ATR")
    show_fibo = st.sidebar.checkbox("Fibonacci")

    st.sidebar.markdown("---")

    # AI
    st.sidebar.subheader("🤖 AI analiza")

    ai_model = st.sidebar.selectbox(
        "Wybierz model AI",
        ["AI‑1", "AI‑2", "AI‑3", "AI‑4"]
    )

    st.sidebar.markdown("---")

    # Portfel (pusty, gotowy do zapisu)
    st.sidebar.subheader("💼 Portfel (PLN)")

    st.sidebar.text_input("Nazwa spółki (wyłączone)", disabled=True)
    st.sidebar.number_input("Kwota (wyłączone)", disabled=True)

    save_btn = st.sidebar.button("💾 Zapisz dane portfela")

    return {
        "refresh": refresh,
        "history_period": history_period,
        "live_data": live_data,
        "interval": interval,
        "show_sma": show_sma,
        "show_rsi": show_rsi,
        "show_boll": show_boll,
        "show_atr": show_atr,
        "show_fibo": show_fibo,
        "ai_model": ai_model,
        "save_btn": save_btn
    }
# ==========================================
#  DANE — POBIERANIE NOTOWAŃ
# ==========================================
def get_price_data(symbol, period, interval, live):
    if live:
        df = yf.download(symbol, period="1d", interval=interval)
    else:
        df = yf.download(symbol, period=period, interval=interval)

    df.dropna(inplace=True)
    return df


# ==========================================
#  BID / ASK / SPREAD
# ==========================================
def get_bid_ask(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info

    bid = info.get("bid")
    ask = info.get("ask")

    if bid is None or ask is None:
        return None, None, None

    spread = ask - bid
    return bid, ask, spread


# ==========================================
#  KURS USD/PLN
# ==========================================
def get_usd_pln():
    df = yf.download("USDPLN=X", period="1d", interval="1h")
    return df["Close"].iloc[-1]


# ==========================================
#  WSKAŹNIKI — SMA
# ==========================================
def sma(series, period=20):
    return series.rolling(window=period).mean()


# ==========================================
#  WSKAŹNIKI — RSI
# ==========================================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# ==========================================
#  WSKAŹNIKI — BOLLINGER BANDS
# ==========================================
def bollinger(series, period=20, std_mult=2):
    ma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = ma + std_mult * std
    lower = ma - std_mult * std
    return ma, upper, lower


# ==========================================
#  WSKAŹNIKI — ATR
# ==========================================
def atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ==========================================
#  WSKAŹNIKI — FIBONACCI
# ==========================================
def fibonacci_levels(df):
    high = df["High"].max()
    low = df["Low"].min()
    diff = high - low

    return {
        "0%": high,
        "23.6%": high - 0.236 * diff,
        "38.2%": high - 0.382 * diff,
        "50%": high - 0.5 * diff,
        "61.8%": high - 0.618 * diff,
        "100%": low
    }


# ==========================================
#  TREND — KRÓTKI / ŚREDNI / DŁUGI
# ==========================================
def detect_trend(close_series):
    if close_series.iloc[-1] > close_series.iloc[-20]:
        return "BULL"
    elif close_series.iloc[-1] < close_series.iloc[-20]:
        return "BEAR"
    return "NEUTRAL"


def detect_multi_trend(df):
    close = df["Close"]

    trends = {
        "short": detect_trend(close[-20:]),
        "medium": detect_trend(close[-50:]),
        "long": detect_trend(close[-200:])
    }

    momentum = close.iloc[-1] - close.iloc[-10]
    strength = abs(close.iloc[-1] - close.iloc[-50])

    return {
        "short_term": trends["short"],
        "medium_term": trends["medium"],
        "long_term": trends["long"],
        "momentum": momentum,
        "strength": strength
    }


# ==========================================
#  SL / TP — LOGIKA
# ==========================================
def calculate_sl_tp(df, atr_value, trend):
    close = df["Close"].iloc[-1]

    sl = close - (atr_value * 2)
    tp = close + (atr_value * 3)

    if trend == "BULL":
        tp = close + (atr_value * 4)
    elif trend == "BEAR":
        sl = close - (atr_value * 3)

    neutral = close

    risk = "LOW" if atr_value < close * 0.01 else "MEDIUM" if atr_value < close * 0.02 else "HIGH"

    return {
        "close": close,
        "sl": sl,
        "tp": tp,
        "neutral": neutral,
        "risk": risk
    }


# ==========================================
#  RYZYKO POZYCJI — ATR + SPREAD + ILOŚĆ AKCJI
# ==========================================
def position_risk(close, atr_value, spread, qty, sl):
    position_value = close * qty

    risk_per_share = (close - sl) + spread
    total_risk = risk_per_share * qty

    risk_percent = (total_risk / position_value) * 100 if position_value > 0 else 0

    if risk_percent < 1:
        level = "LOW"
    elif risk_percent < 3:
        level = "MEDIUM"
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
#  WYKRES CENY — OSOBNE OKNO
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
        name="Cena"
    )

    fig.update_layout(
        template="plotly_dark",
        height=500,
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font=dict(color=NEON_YELLOW)
    )

    st.plotly_chart(fig, use_container_width=True)


# ==========================================
#  WYKRES SMA — OSOBNE OKNO
# ==========================================
def show_sma_chart(df):
    st.subheader("📘 SMA (Simple Moving Average)")

    df["SMA20"] = sma(df["Close"], 20)

    st.line_chart(df["SMA20"])


# ==========================================
#  WYKRES RSI — OSOBNE OKNO
# ==========================================
def show_rsi_chart(df):
    st.subheader("📗 RSI (Relative Strength Index)")

    df["RSI"] = rsi(df["Close"])

    st.line_chart(df["RSI"])


# ==========================================
#  WYKRES BOLLINGER BANDS — OSOBNE OKNO
# ==========================================
def show_bollinger_chart(df):
    st.subheader("📕 Bollinger Bands")

    ma, upper, lower = bollinger(df["Close"])

    st.line_chart({
        "MA": ma,
        "Upper": upper,
        "Lower": lower
    })


# ==========================================
#  WYKRES ATR — OSOBNE OKNO
# ==========================================
def show_atr_chart(df):
    st.subheader("📙 ATR (Average True Range)")

    df["ATR"] = atr(df)

    st.line_chart(df["ATR"])


# ==========================================
#  WYKRES FIBONACCI — OSOBNE OKNO
# ==========================================
def show_fibonacci_levels(df):
    st.subheader("📐 Poziomy Fibonacciego")

    levels = fibonacci_levels(df)

    for lvl, val in levels.items():
        st.write(f"{lvl}: {val:.2f}")


# ==========================================
#  GŁÓWNA FUNKCJA WYKRESÓW
# ==========================================
def charts_window(symbol, settings):
    df = get_price_data(
        symbol=symbol,
        period=settings["history_period"],
        interval=settings["interval"],
        live=settings["live_data"]
    )

    # Wykres ceny
    show_price_chart(df, symbol)

    # SMA
    if settings["show_sma"]:
        show_sma_chart(df)

    # RSI
    if settings["show_rsi"]:
        show_rsi_chart(df)

    # Bollinger
    if settings["show_boll"]:
        show_bollinger_chart(df)

    # ATR
    if settings["show_atr"]:
        show_atr_chart(df)

    # Fibonacci
    if settings["show_fibo"]:
        show_fibonacci_levels(df)
# ==========================================
#  SKANER RYNKU — OKNO GŁÓWNE
# ==========================================
def scanner_window(settings):

    st.subheader("📡 Skaner rynku")

    # --------------------------------------
    #  INICJALIZACJA LISTY SPÓŁEK
    # --------------------------------------
    if "symbols_list" not in st.session_state:
        st.session_state.symbols_list = []

    # --------------------------------------
    #  DODAWANIE SPÓŁEK (jedna linia, przecinki)
    # --------------------------------------
    new_symbols = st.text_input(
        "Dodaj symbole (oddzielone przecinkami):",
        placeholder="np. AAPL, MSFT, TSLA"
    )

    if st.button("➕ Dodaj do listy"):
        if new_symbols.strip():
            parsed = [
                s.strip().upper()
                for s in new_symbols.split(",")
                if s.strip()
            ]
            for sym in parsed:
                if sym not in st.session_state.symbols_list:
                    st.session_state.symbols_list.append(sym)

    # --------------------------------------
    #  WYŚWIETLANIE LISTY SPÓŁEK
    # --------------------------------------
    st.markdown("### 📋 Lista obserwowanych spółek")

    if not st.session_state.symbols_list:
        st.info("Brak zapisanych spółek.")
    else:
        for sym in st.session_state.symbols_list:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"🔹 {sym}")
            with col2:
                if st.button(f"❌ Usuń {sym}", key=f"del_{sym}"):
                    st.session_state.symbols_list.remove(sym)
                    st.experimental_rerun()

    st.markdown("---")

    # --------------------------------------
    #  SKANOWANIE RYNKU
    # --------------------------------------
    if st.button("🔎 Skanuj rynek"):
        if not st.session_state.symbols_list:
            st.warning("Najpierw dodaj spółki do listy.")
            return

        data = {
            sym: get_price_data(
                symbol=sym,
                period=settings["history_period"],
                interval=settings["interval"],
                live=settings["live_data"]
            )
            for sym in st.session_state.symbols_list
        }

        st.markdown("---")

        # --------------------------------------
        #  WYNIKI SKANERA
        # --------------------------------------
        for symbol in st.session_state.symbols_list:
            st.markdown(f"### 🟦 {symbol}")

            df = data.get(symbol)

            if df is None or df.empty:
                st.error("Brak danych.")
                continue

            # Trend
            trend = detect_trend(df["Close"])

            # Cena i wolumen
            last_close = df["Close"].iloc[-1]
            volume = df["Volume"].iloc[-1]

            # Kolory neonowe
            color_map = {
                "BULL": NEON_GREEN,
                "BEAR": NEON_PINK,
                "NEUTRAL": NEON_YELLOW
            }

            st.markdown(
                f"""
                <div style='padding:12px;background:{BACKGROUND};
                border:1px solid {color_map[trend]};
                border-radius:8px;'>
                    <b>Cena zamknięcia:</b> {last_close:.2f}<br>
                    <b>Wolumen:</b> {volume:,}<br>
                    <b>Trend:</b>
                    <span style='color:{color_map[trend]};'>
                    {trend}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown("---")
# ==========================================
#  AI KOMENTARZ — ANALIZA DANYCH
# ==========================================
def ai_commentary(symbol, df, indicators, model_name):
    model = get_ai_model(model_name)

    last_close = df["Close"].iloc[-1]
    volume = df["Volume"].iloc[-1]

    trend = indicators.get("trend")
    rsi_val = indicators.get("rsi")
    atr_val = indicators.get("atr")
    momentum = indicators.get("momentum")
    strength = indicators.get("strength")

    bid, ask, spread = get_bid_ask(symbol)

    prompt = f"""
    Jesteś profesjonalnym analitykiem giełdowym. Przeanalizuj spółkę {symbol} na podstawie:

    • Cena bieżąca: {last_close}
    • Wolumen: {volume}
    • Trend: {trend}
    • RSI: {rsi_val}
    • ATR: {atr_val}
    • Momentum: {momentum}
    • Siła trendu: {strength}
    • BID: {bid}
    • ASK: {ask}
    • Spread: {spread}
    • Liczba świec historycznych: {len(df)}

    Podaj:
    1. Krótką analizę techniczną
    2. Momentum i zmienność
    3. Siłę trendu i kierunek
    4. Wpływ spreadu na decyzję
    5. Podsumowanie w 1 zdaniu
    """

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message["content"]


# ==========================================
#  OKNO AI KOMENTARZA
# ==========================================
def ai_commentary_window(symbol, settings):
    st.subheader("🤖 AI Komentarz")

    df = get_price_data(
        symbol=symbol,
        period=settings["history_period"],
        interval=settings["interval"],
        live=settings["live_data"]
    )

    # Wskaźniki
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

    st.markdown(
        f"""
        <div style='padding:15px;background:{BACKGROUND};
        border:1px solid {NEON_BLUE};border-radius:8px;'>
            {comment}
        </div>
        """,
        unsafe_allow_html=True
    )


# ==========================================
#  AI CZAT — NIEZALEŻNE OKNO
# ==========================================
def ai_chat_window(settings):
    st.subheader("💬 Czat AI (niezależny)")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    user_msg = st.text_input("Wpisz wiadomość:")

    if st.button("Wyślij"):
        if user_msg.strip():
            model = get_ai_model(settings["ai_model"])

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Jesteś pomocnym asystentem."},
                    *st.session_state.chat_history,
                    {"role": "user", "content": user_msg}
                ]
            )

            ai_msg = response.choices[0].message["content"]

            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            st.session_state.chat_history.append({"role": "assistant", "content": ai_msg})

    # Wyświetlanie historii
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"**Ty:** {msg['content']}")
        else:
            st.markdown(f"**AI:** {msg['content']}")
# ==========================================
#  OKNO TRENDÓW — KRÓTKI / ŚREDNI / DŁUGI
# ==========================================
def trends_window(symbol, settings):
    st.subheader(f"📊 Trendy — {symbol}")

    df = get_price_data(
        symbol=symbol,
        period=settings["history_period"],
        interval=settings["interval"],
        live=settings["live_data"]
    )

    trends = detect_multi_trend(df)

    color_map = {
        "BULL": NEON_GREEN,
        "BEAR": NEON_PINK,
        "NEUTRAL": NEON_YELLOW
    }

    st.markdown("---")

    # --------------------------------------
    #  TREND KRÓTKOTERMINOWY
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {color_map[trends["short_term"]]};
        border-radius:8px;'>
            <b>Trend krótkoterminowy:</b>
            <span style='color:{color_map[trends["short_term"]]};'>
            {trends["short_term"]}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  TREND ŚREDNIOTERMINOWY
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {color_map[trends["medium_term"]]};
        border-radius:8px;'>
            <b>Trend średnioterminowy:</b>
            <span style='color:{color_map[trends["medium_term"]]};'>
            {trends["medium_term"]}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  TREND DŁUGOTERMINOWY
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {color_map[trends["long_term"]]};
        border-radius:8px;'>
            <b>Trend długoterminowy:</b>
            <span style='color:{color_map[trends["long_term"]]};'>
            {trends["long_term"]}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    # --------------------------------------
    #  MOMENTUM
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_BLUE};
        border-radius:8px;'>
            <b>Momentum:</b> {trends["momentum"]:.2f}
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  SIŁA TRENDU
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_PINK};
        border-radius:8px;'>
            <b>Siła trendu:</b> {trends["strength"]:.2f}
        </div>
        """,
        unsafe_allow_html=True
    )
# ==========================================
#  OKNO SL / TP — PEŁNA ANALIZA
# ==========================================
def sl_tp_window(symbol, settings):

    st.subheader(f"🎯 SL / TP — {symbol}")

    # Pobranie danych
    df = get_price_data(
        symbol=symbol,
        period=settings["history_period"],
        interval=settings["interval"],
        live=settings["live_data"]
    )

    # ATR
    df["ATR"] = atr(df)
    atr_value = df["ATR"].iloc[-1]

    # Trend
    trend = detect_trend(df["Close"])

    # SL/TP
    results = calculate_sl_tp(df, atr_value, trend)

    # BID/ASK/SPREAD
    bid, ask, spread = get_bid_ask(symbol)

    color_map = {
        "LOW": NEON_GREEN,
        "MEDIUM": NEON_YELLOW,
        "HIGH": NEON_PINK
    }

    st.markdown("---")

    # --------------------------------------
    #  CENA BIEŻĄCA
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_BLUE};border-radius:8px;'>
            <b>Cena bieżąca:</b> {results["close"]:.2f}
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  STOP LOSS
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_PINK};border-radius:8px;'>
            <b>Stop‑Loss:</b> {results["sl"]:.2f}
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  TAKE PROFIT
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_GREEN};border-radius:8px;'>
            <b>Take‑Profit:</b> {results["tp"]:.2f}
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  POZIOM NEUTRALNY
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_YELLOW};border-radius:8px;'>
            <b>Poziom neutralny:</b> {results["neutral"]:.2f}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    # --------------------------------------
    #  RYZYKO SYSTEMOWE (LOW / MEDIUM / HIGH)
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {color_map[results["risk"]]};border-radius:8px;'>
            <b>Ryzyko systemowe:</b>
            <span style='color:{color_map[results["risk"]]};'>
            {results["risk"]}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    # --------------------------------------
    #  RYZYKO POZYCJI (ilość akcji)
    # --------------------------------------
    st.subheader("⚠️ Ryzyko pozycji")

    qty = st.number_input("Ilość akcji:", min_value=1, value=1)

    if bid is None:
        st.error("Brak danych BID/ASK — nie można policzyć ryzyka pozycji.")
        return

    risk = position_risk(
        close=results["close"],
        atr_value=atr_value,
        spread=spread,
        qty=qty,
        sl=results["sl"]
    )

    st.markdown(
        f"""
        <div style='padding:15px;background:{BACKGROUND};
        border:1px solid {color_map[risk["level"]]};border-radius:8px;'>
            <b>Wartość pozycji:</b> {risk["position_value"]:.2f} PLN<br>
            <b>Ryzyko na 1 akcję:</b> {risk["risk_per_share"]:.2f} PLN<br>
            <b>Ryzyko całkowite:</b> {risk["total_risk"]:.2f} PLN<br>
            <b>Ryzyko procentowe:</b> {risk["risk_percent"]:.2f}%<br>
            <b>Poziom ryzyka:</b>
            <span style='color:{color_map[risk["level"]]};'>
            {risk["level"]}</span>
        </div>
        """,
        unsafe_allow_html=True
    )
# ==========================================
#  PORTFEL — OKNO GŁÓWNE
# ==========================================
def portfolio_window():

    st.subheader("💼 Portfel (PLN)")

    # --------------------------------------
    #  INICJALIZACJA PORTFELA
    # --------------------------------------
    if "portfolio" not in st.session_state:
        st.session_state.portfolio = []

    # --------------------------------------
    #  KURS USD/PLN
    # --------------------------------------
    usd_pln = get_usd_pln()

    st.markdown(
        f"""
        <div style='padding:10px;background:{BACKGROUND};
        border:1px solid {NEON_BLUE};border-radius:8px;'>
            <b>Kurs USD/PLN:</b> {usd_pln:.2f} PLN
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    # --------------------------------------
    #  DODAWANIE POZYCJI
    # --------------------------------------
    col1, col2, col3 = st.columns(3)

    with col1:
        symbol = st.text_input("Symbol spółki:")

    with col2:
        qty = st.number_input("Ilość akcji:", min_value=0.0, step=0.1)

    with col3:
        price_usd = st.number_input("Cena zakupu (USD):", min_value=0.0, step=0.01)

    if st.button("➕ Dodaj do portfela"):
        if symbol and qty > 0 and price_usd > 0:
            st.session_state.portfolio.append({
                "symbol": symbol.upper(),
                "qty": qty,
                "price_usd": price_usd,
                "price_pln": price_usd * usd_pln
            })

    st.markdown("---")

    # --------------------------------------
    #  WYŚWIETLANIE PORTFELA
    # --------------------------------------
    if not st.session_state.portfolio:
        st.info("Portfel jest pusty.")
        return

    st.markdown("### 📋 Twoje pozycje:")

    for pos in st.session_state.portfolio:

        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

        with col1:
            st.write(f"🔹 {pos['symbol']}")

        with col2:
            st.write(f"Ilość: {pos['qty']}")

        with col3:
            st.write(f"Wartość PLN: {pos['price_pln']:.2f}")

        with col4:
            if st.button(f"❌ Usuń {pos['symbol']}", key=f"del_{pos['symbol']}"):
                st.session_state.portfolio.remove(pos)
                st.experimental_rerun()
# ==========================================
#  OKNO BID / ASK / SPREAD
# ==========================================
def bidask_window(symbol):

    st.subheader(f"💹 BID / ASK — {symbol}")

    bid, ask, spread = get_bid_ask(symbol)

    if bid is None or ask is None:
        st.error("Brak danych BID/ASK dla tej spółki.")
        return

    st.markdown("---")

    # --------------------------------------
    #  BID
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_GREEN};border-radius:8px;'>
            <b>BID:</b> {bid}
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  ASK
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_PINK};border-radius:8px;'>
            <b>ASK:</b> {ask}
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------
    #  SPREAD
    # --------------------------------------
    st.markdown(
        f"""
        <div style='padding:12px;background:{BACKGROUND};
        border:1px solid {NEON_YELLOW};border-radius:8px;'>
            <b>Spread:</b> {spread}
        </div>
        """,
        unsafe_allow_html=True
    )
# ==========================================
#  GŁÓWNY INTERFEJS — ROUTING I LAYOUT
# ==========================================
def main_app():

    st.title("💹 Terminal Tradingowy — 1:1")

    st.markdown("---")

    # --------------------------------------
    #  WYBÓR MODUŁU
    # --------------------------------------
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

    # --------------------------------------
    #  SYMBOL (dla modułów które go potrzebują)
    # --------------------------------------
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

    # --------------------------------------
    #  ROUTING DO MODUŁÓW
    # --------------------------------------
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
# ==========================================
#  GLOBALNY NEON DARK MODE — CSS
# ==========================================
def inject_global_css():
    st.markdown(
        f"""
        <style>

        /* Tło całej aplikacji */
        .stApp {{
            background-color: {BACKGROUND};
        }}

        /* Tekst */
        html, body, [class*="css"]  {{
            color: {NEON_YELLOW} !important;
        }}

        /* Przyciski */
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

        /* Inputy */
        .stTextInput>div>div>input {{
            background-color: #111 !important;
            color: {NEON_GREEN} !important;
            border: 1px solid {NEON_GREEN};
        }}

        .stNumberInput>div>div>input {{
            background-color: #111 !important;
            color: {NEON_GREEN} !important;
            border: 1px solid {NEON_GREEN};
        }}

        /* Selectbox */
        .stSelectbox>div>div>select {{
            background-color: #111 !important;
            color: {NEON_YELLOW} !important;
            border: 1px solid {NEON_YELLOW};
        }}

        /* Scrollbar */
        ::-webkit-scrollbar {{
            width: 8px;
        }}

        ::-webkit-scrollbar-track {{
            background: #111;
        }}

        ::-webkit-scrollbar-thumb {{
            background: {NEON_PINK};
            border-radius: 10px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: {NEON_BLUE};
        }}

        </style>
        """,
        unsafe_allow_html=True
    )


# ==========================================
#  GŁÓWNY INTERFEJS
# ==========================================
def main_app():
    inject_global_css()   # <-- poprawne miejsce i wcięcie

    st.title("💹 Terminal Tradingowy — 1:1")
    st.markdown("---")

    # ...reszta Twojego kodu main_app()...
