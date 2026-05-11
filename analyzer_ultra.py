
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# Inicjalizacja OpenAI
client = OpenAI()

# Kolory Terminala
BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="Terminal Tradingowy", layout="wide")

# Odświeżanie co 5 minut
st_autorefresh(interval=5 * 60 * 1000, key="datarefresh")


def inject_global_css():
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {BACKGROUND}; }}
        html, body, [class*="css"]  {{ color: {NEON_YELLOW} !important; }}
        .stButton>button {{ background-color: #111; color: {NEON_BLUE}; border: 1px solid {NEON_BLUE}; border-radius: 6px; }}
        input, select, textarea {{ background-color: #111 !important; color: {NEON_GREEN} !important; border: 1px solid {NEON_GREEN} !important; }}
        section[data-testid="stSidebar"] {{ background-color: #0a0a0a !important; border-right: 2px solid {NEON_BLUE} !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- Logika Danych ---
def get_price_data(symbol, period, interval):
    if not symbol:
        return pd.DataFrame()
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()


# --- Wskaźniki ---
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean().abs()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    tr = pd.concat(
        [
            (df["High"] - df["Low"]),
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"] - df["Close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def ema(series, period=20):
    return series.ewm(span=period, adjust=False).mean()


def macd(series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return macd_line, signal, hist


def smi(df, k_period=14, d_period=3, smoothing=3):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    ll = low.rolling(k_period).min()
    hh = high.rolling(k_period).max()
    mid = (hh + ll) / 2
    diff = close - mid

    diff_sm = diff.ewm(span=smoothing, adjust=False).mean()
    range_sm = (hh - ll).ewm(span=smoothing, adjust=False).mean()

    smi_val = 100 * (diff_sm / (range_sm / 2))
    signal = smi_val.ewm(span=d_period, adjust=False).mean()
    return smi_val, signal


def fib_levels(df):
    high = df["High"].tail(100).max()
    low = df["Low"].tail(100).min()
    diff = high - low
    levels = {
        "0.0%": high,
        "23.6%": high - 0.236 * diff,
        "38.2%": high - 0.382 * diff,
        "50.0%": high - 0.5 * diff,
        "61.8%": high - 0.618 * diff,
        "78.6%": high - 0.786 * diff,
        "100%": low,
    }
    return levels


def trend_and_levels(df, symbol):
    close = df["Close"]
    last = close.iloc[-1]
    r = rsi(close).iloc[-1]
    a = atr(df).iloc[-1]

    ema20 = ema(close, 20).iloc[-1]
    ema50 = ema(close, 50).iloc[-1]

    if ema20 > ema50 and last > ema20:
        trend = "UP"
    elif ema20 < ema50 and last < ema20:
        trend = "DOWN"
    else:
        trend = "SIDE"

    sl_long = last - 1.5 * a
    tp_long = last + 3 * a
    sl_short = last + 1.5 * a
    tp_short = last - 3 * a

    t = yf.Ticker(symbol)
    fi = getattr(t, "fast_info", {})
    bid = fi.get("bid", None)
    ask = fi.get("ask", None)
    spread = None
    if bid and ask:
        spread = ask - bid

    return {
        "last": last,
        "rsi": r,
        "atr": a,
        "ema20": ema20,
        "ema50": ema50,
        "trend": trend,
        "sl_long": sl_long,
        "tp_long": tp_long,
        "sl_short": sl_short,
        "tp_short": tp_short,
        "bid": bid,
        "ask": ask,
        "spread": spread,
    }


def build_market_context(df, symbol):
    close = df["Close"]
    last = close.iloc[-1]
    prev = close.iloc[-2] if len(close) > 1 else last
    ch_pct = (last - prev) / prev * 100 if prev != 0 else 0

    r = rsi(close).iloc[-1]
    a = atr(df).iloc[-1]

    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

    ctx = f"""
SYMBOL: {symbol}
LAST PRICE: {last:.2f} ({ch_pct:+.2f}% vs poprzednia świeca)

RSI(14): {r:.2f}
ATR(14): {a:.4f}
EMA20: {ema20:.2f}
EMA50: {ema50:.2f}

RELACJA CENY DO EMA:
- Cena {'POWYŻEJ' if last > ema20 else 'PONIŻEJ'} EMA20
- Cena {'POWYŻEJ' if last > ema50 else 'PONIŻEJ'} EMA50
"""
    return ctx


def company_snapshot(symbol):
    t = yf.Ticker(symbol)
    info = getattr(t, "info", {})
    name = info.get("longName", "brak nazwy")
    sector = info.get("sector", "brak sektora")
    website = info.get("website", "brak strony")
    return name, sector, website


# --- UI GŁÓWNE ---
def main():
    inject_global_css()

    st.sidebar.title("⚙️ Terminal")

    # Portfel – czysty na starcie, użytkownik dopisuje spółki
    if "symbols" not in st.session_state:
        st.session_state.symbols = []

    new_sym = st.sidebar.text_input("Dodaj spółkę (ticker):", "").upper()
    if st.sidebar.button("➕ Dodaj", use_container_width=True) and new_sym:
        if new_sym not in st.session_state.symbols:
            st.session_state.symbols.append(new_sym)

    if st.session_state.symbols:
        sym = st.sidebar.selectbox("Wybierz spółkę:", st.session_state.symbols)
    else:
        sym = None
        st.sidebar.info("Brak spółek. Dodaj ticker powyżej.")

    # Zakres danych: 1 miesiąc – 2 lata
    range_p = st.sidebar.selectbox(
        "Zakres danych:",
        ["1mo", "3mo", "6mo", "1y", "2y"],
        index=0,
    )

    # Interwał
    tf = st.sidebar.selectbox("Interwał:", ["1d", "1h", "15m"], index=0)

    # Model AI – zawsze Prop-Trader Mode
    ai_mod = st.sidebar.selectbox(
        "Model AI:",
        ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview"],
    )

    if st.session_state.symbols:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Spółki w portfelu")
        for s in st.session_state.symbols:
            st.sidebar.write(f"- {s}")

    if not sym:
        st.warning("Dodaj spółkę i wybierz ją z listy, aby zobaczyć dane.")
        return

    df = get_price_data(sym, range_p, tf)
    if df.empty:
        st.info("Brak danych dla tego symbolu w wybranym zakresie.")
        return

    tab_price, tab_rsi, tab_fibo, tab_smi, tab_macd, tab_trend, tab_ai, tab_info = st.tabs(
        ["Wykres", "RSI", "Fibo", "SMI", "MACD", "Trend / SL/TP", "AI Prop", "Info o spółkach"]
    )

    # --- Wykres główny ---
    with tab_price:
        st.subheader(f"📈 Wykres {sym}")
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df.index,
                    open=df["Open"],
                    high=df["High"],
                    low=df["Low"],
                    close=df["Close"],
                )
            ]
        )
        fig.update_layout(
            template="plotly_dark",
            height=500,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- RSI ---
    with tab_rsi:
        st.subheader("RSI (14)")
        r = rsi(df["Close"]).dropna()
        st.line_chart(r)
        st.write(f"Ostatnia wartość RSI: **{r.iloc[-1]:.2f}**")

    # --- Fibo ---
    with tab_fibo:
        st.subheader("Poziomy Fibonacciego (ostatnie ~100 świec)")
        levels = fib_levels(df)
        for name, val in levels.items():
            st.write(f"**{name}**: {val:.2f}")
        st.info(
            "Poziomy Fibo pokazują potencjalne strefy wsparcia/oporu na bazie ostatniego większego ruchu."
        )

    # --- SMI ---
    with tab_smi:
        st.subheader("SMI (Stochastic Momentum Index)")
        smi_val, smi_sig = smi(df)
        s = pd.DataFrame({"SMI": smi_val, "Signal": smi_sig}).dropna()
        st.line_chart(s)
        st.write(
            f"Ostatni SMI: **{s['SMI'].iloc[-1]:.2f}**, Signal: **{s['Signal'].iloc[-1]:.2f}**"
        )

    # --- MACD ---
    with tab_macd:
        st.subheader("MACD")
        macd_line, signal, hist = macd(df["Close"])
        m = pd.DataFrame({"MACD": macd_line, "Signal": signal, "Hist": hist}).dropna()
        st.line_chart(m[["MACD", "Signal"]])
        st.bar_chart(m["Hist"])

    # --- Trend / SL / TP / bid / ask / spread ---
    with tab_trend:
        st.subheader("Trend, poziomy SL/TP, bid/ask, spread")
        info = trend_and_levels(df, sym)

        col_a, col_b = st.columns(2)

        with col_a:
            st.write(f"**Cena ostatnia:** {info['last']:.2f}")
            st.write(f"**Trend:** {info['trend']}")
            st.write(f"**RSI(14):** {info['rsi']:.2f}")
            st.write(f"**ATR(14):** {info['atr']:.4f}")
            st.write(f"**EMA20:** {info['ema20']:.2f}")
            st.write(f"**EMA50:** {info['ema50']:.2f}")

        with col_b:
            st.write("**Scenariusz LONG:**")
            st.write(f"SL: {info['sl_long']:.2f}")
            st.write(f"TP: {info['tp_long']:.2f}")
            st.write("**Scenariusz SHORT:**")
            st.write(f"SL: {info['sl_short']:.2f}")
            st.write(f"TP: {info['tp_short']:.2f}")

            st.markdown("---")
            st.write(f"**Bid:** {info['bid'] if info['bid'] else 'brak'}")
            st.write(f"**Ask:** {info['ask'] if info['ask'] else 'brak'}")
            if info["spread"] is not None:
                st.write(f"**Spread:** {info['spread']:.4f}")

    # --- AI Prop-Trader: BUY / SELL / HOLD ---
    with tab_ai:
        st.subheader("💬 AI – Prop-Trader (BUY / SELL / HOLD)")

        if "chat" not in st.session_state:
            st.session_state.chat = []

        for m in st.session_state.chat:
            with st.chat_message(m["role"]):
                st.write(m["content"])

        if p := st.chat_input("Pytaj AI..."):
            st.session_state.chat.append({"role": "user", "content": p})

            market_ctx = build_market_context(df, sym)

            system_prompt = """
Jesteś zawodowym prop-traderem. 
Twoim zadaniem jest na podstawie danych rynkowych wyrazić opinię: BUY / SELL / HOLD.

Zasady:
- pierwsza linijka odpowiedzi: tylko jedno słowo: BUY / SELL / HOLD
- potem krótko uzasadnienie (max 5–7 zdań)
- opierasz się na RSI(14), ATR(14), EMA20, EMA50, trendzie oraz ostatnim ruchu ceny
- możesz odwołać się do poziomów SL/TP, jeśli setup jest sensowny
- jeśli setup jest słaby – możesz dać HOLD i napisać, czego brakuje

To nie jest porada inwestycyjna, tylko analiza scenariuszy.
"""

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "system",
                    "content": "Aktualny kontekst rynku na podstawie danych:\n"
                    + market_ctx,
                },
            ] + st.session_state.chat

            res = client.chat.completions.create(
                model=ai_mod,
                messages=messages,
            )

            reply = res.choices[0].message.content
            st.session_state.chat.append({"role": "assistant", "content": reply})
            st.rerun()

    # --- Info o spółkach (szukanie w sieci przez yfinance) ---
    with tab_info:
        st.subheader("Informacje o wszystkich dodanych spółkach")
        if not st.session_state.symbols:
            st.info("Brak spółek w portfelu.")
        else:
            for s in st.session_state.symbols:
                name, sector, website = company_snapshot(s)
                st.markdown(f"### {s}")
                st.write(f"**Nazwa:** {name}")
                st.write(f"**Sektor:** {sector}")
                st.write(f"**Strona www:** {website}")
                st.markdown("---")


if __name__ == "__main__":
    main()

