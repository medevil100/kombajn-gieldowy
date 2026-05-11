import time
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# Inicjalizacja OpenAI
client = OpenAI()

# Kolory
BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="ULTRA ENGINE v2", layout="wide")


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


# --- Dane rynkowe ---
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
    series = pd.Series(series).astype(float)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean().abs()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def ema(series, period=20):
    series = pd.Series(series).astype(float)
    return series.ewm(span=period, adjust=False).mean()


def macd(series):
    series = pd.Series(series).astype(float)
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return macd_line, signal, hist


def smi(df, k_period=14, d_period=3, smoothing=3):
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

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
    high = df["High"].astype(float).tail(100).max()
    low = df["Low"].astype(float).tail(100).min()
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
    close = df["Close"].astype(float)
    last = float(close.iloc[-1])
    r = float(rsi(close).iloc[-1])
    a = float(atr(df).iloc[-1])

    ema20_val = float(ema(close, 20).iloc[-1])
    ema50_val = float(ema(close, 50).iloc[-1])

    if ema20_val > ema50_val and last > ema20_val:
        trend = "UP"
    elif ema20_val < ema50_val and last < ema20_val:
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
    if bid is not None and ask is not None:
        spread = ask - bid

    return {
        "last": last,
        "rsi": r,
        "atr": a,
        "ema20": ema20_val,
        "ema50": ema50_val,
        "trend": trend,
        "sl_long": sl_long,
        "tp_long": tp_long,
        "sl_short": sl_short,
        "tp_short": tp_short,
        "bid": bid,
        "ask": ask,
        "spread": spread,
    }


def build_market_context_single(df, symbol):
    close = df["Close"].astype(float)
    last = float(close.iloc[-1])
    if len(close) > 1:
        prev = float(close.iloc[-2])
    else:
        prev = last
    if prev == 0:
        ch_pct = 0.0
    else:
        ch_pct = (last - prev) / prev * 100

    r = float(rsi(close).iloc[-1])
    a = float(atr(df).iloc[-1])
    ema20_val = float(ema(close, 20).iloc[-1])
    ema50_val = float(ema(close, 50).iloc[-1])

    ctx = f"""
SYMBOL: {symbol}
LAST PRICE: {last:.2f} ({ch_pct:+.2f}% vs poprzednia świeca)

RSI(14): {r:.2f}
ATR(14): {a:.4f}
EMA20: {ema20_val:.2f}
EMA50: {ema50_val:.2f}

RELACJA CENY DO EMA:
- Cena {'POWYŻEJ' if last > ema20_val else 'PONIŻEJ'} EMA20
- Cena {'POWYŻEJ' if last > ema50_val else 'PONIŻEJ'} EMA50
"""
    return ctx


def get_news_summary(symbol, max_items=5):
    t = yf.Ticker(symbol)
    news = getattr(t, "news", []) or []
    items = news[:max_items]
    lines = []
    for n in items:
        title = n.get("title", "")
        publisher = n.get("publisher", "")
        lines.append(f"- [{publisher}] {title}")
    if not lines:
        return "Brak świeżych newsów."
    return "\n".join(lines)


def build_multi_context(symbols, period, interval):
    blocks = []
    for sym in symbols:
        df = get_price_data(sym, period, interval)
        if df.empty:
            blocks.append(f"SYMBOL: {sym}\nBrak danych.\n")
            continue

        close = df["Close"].astype(float)
        last = float(close.iloc[-1])
        if len(close) > 1:
            prev = float(close.iloc[-2])
        else:
            prev = last
        if prev == 0:
            ch_pct = 0.0
        else:
            ch_pct = (last - prev) / prev * 100

        r = float(rsi(close).iloc[-1])
        a = float(atr(df).iloc[-1])
        ema20_val = float(ema(close, 20).iloc[-1])
        ema50_val = float(ema(close, 50).iloc[-1])

        if ema20_val > ema50_val and last > ema20_val:
            trend = "UP"
        elif ema20_val < ema50_val and last < ema20_val:
            trend = "DOWN"
        else:
            trend = "SIDE"

        news_txt = get_news_summary(sym, max_items=5)

        block = f"""
========================
SYMBOL: {sym}
LAST PRICE: {last:.2f} ({ch_pct:+.2f}% vs poprzednia świeca)
RSI(14): {r:.2f}
ATR(14): {a:.4f}
EMA20: {ema20_val:.2f}
EMA50: {ema50_val:.2f}
TREND: {trend}

NEWS (ostatnie nagłówki, bez linków):
{news_txt}
"""
        blocks.append(block)

    return "\n".join(blocks)


# --- UI ---
def label_to_seconds(label: str) -> int:
    if label.endswith("s"):
        return int(label[:-1])
    if label.endswith("m"):
        return int(label[:-1]) * 60
    return 60


def main():
    inject_global_css()

    if "symbols" not in st.session_state:
        st.session_state.symbols = []
    if "chat" not in st.session_state:
        st.session_state.chat = []
    if "ai_multi_result" not in st.session_state:
        st.session_state.ai_multi_result = ""
    if "last_ai_run" not in st.session_state:
        st.session_state.last_ai_run = 0.0

    st.sidebar.title("⚙️ ULTRA ENGINE v2")

    # Dodawanie spółek – tickery oddzielone przecinkami, np. PKN.WA, PKO.WA, AAPL, TSLA
    symbols_input = st.sidebar.text_input(
        "Dodaj spółki (tickery, oddzielone przecinkami):", ""
    )
    add_col1, add_col2 = st.sidebar.columns([2, 1])
    with add_col1:
        if st.button("➕ Dodaj spółki", use_container_width=True) and symbols_input:
            raw_list = symbols_input.split(",")
            for raw in raw_list:
                sym = raw.strip().upper()
                if sym and sym not in st.session_state.symbols:
                    st.session_state.symbols.append(sym)
    with add_col2:
        if st.button("🗑 Wyczyść listę", use_container_width=True):
            st.session_state.symbols = []

    if st.session_state.symbols:
        sym = st.sidebar.selectbox("Aktywna spółka (do wykresów):", st.session_state.symbols)
    else:
        sym = None
        st.sidebar.info("Brak spółek. Dodaj tickery powyżej (np. PKN.WA, AAPL).")

    # Zakres danych
    range_p = st.sidebar.selectbox(
        "Zakres danych:",
        ["1mo", "3mo", "6mo", "1y", "2y"],
        index=0,
    )

    # Interwał
    tf = st.sidebar.selectbox("Interwał:", ["1d", "1h", "15m"], index=0)

    # Suwaki odświeżania
    st.sidebar.markdown("---")
    st.sidebar.subheader("⏱ Odświeżanie")

    data_interval_label = st.sidebar.selectbox(
        "Odświeżanie danych:",
        ["5s", "10s", "30s", "1m", "5m", "15m"],
        index=3,
    )
    ai_interval_label = st.sidebar.selectbox(
        "Odświeżanie AI (multi-analiza):",
        ["30s", "1m", "5m", "15m", "30m"],
        index=2,
    )

    data_interval_sec = label_to_seconds(data_interval_label)
    ai_interval_sec = label_to_seconds(ai_interval_label)

    st_autorefresh(interval=data_interval_sec * 1000, key="auto_refresh")

    if st.session_state.symbols:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Spółki w portfelu")
        for s in st.session_state.symbols:
            st.sidebar.write(f"- {s}")

    if not sym:
        st.warning("Dodaj spółki i wybierz jedną jako aktywną, aby zobaczyć dane.")
        return

    df = get_price_data(sym, range_p, tf)
    if df.empty:
        st.info("Brak danych dla tego symbolu w wybranym zakresie.")
        return

    # --- TABS ---
    tab_price, tab_rsi, tab_fibo, tab_smi, tab_macd, tab_trend, tab_ai_chat, tab_ai_multi, tab_heatmap = st.tabs(
        [
            "Wykres",
            "RSI",
            "Fibo",
            "SMI",
            "MACD",
            "Trend / SL/TP",
            "AI Chat (1 spółka)",
            "AI Multi Verdict (wiele spółek)",
            "Heatmapa Rynku",
        ]
    )

    # --- Wykres główny + Fibo ---
    with tab_price:
        st.subheader(f"📈 Wykres {sym} z poziomami Fibo")
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df.index,
                    open=df["Open"],
                    high=df["High"],
                    low=df["Low"],
                    close=df["Close"],
                    name="Cena",
                )
            ]
        )
        levels = fib_levels(df)
        for name, val in levels.items():
            fig.add_hline(
                y=val,
                line_dash="dot",
                line_color=NEON_BLUE,
                annotation_text=name,
                annotation_position="right",
            )
        fig.update_layout(
            template="plotly_dark",
            height=550,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Świece + poziomy Fibonacciego (ostatnie ~100 świec).")

    # --- RSI ---
    with tab_rsi:
        st.subheader("RSI (Relative Strength Index)")
        r = rsi(df["Close"]).dropna()
        st.line_chart(r)
        st.write(f"Ostatnia wartość RSI(14): **{r.iloc[-1]:.2f}**")
        st.caption("RSI > 70 – wykupienie, < 30 – wyprzedanie (w kontekście trendu).")

    # --- Fibo – tabela + osobny wykres ---
    with tab_fibo:
        st.subheader("Poziomy Fibonacciego – tabela")
        levels = fib_levels(df)
        fib_df = pd.DataFrame(
            {"Poziom": list(levels.keys()), "Cena": [round(v, 4) for v in levels.values()]}
        )
        st.table(fib_df)

        st.subheader("Wykres Fibo (Close + poziomy)")
        fig_f = go.Figure()
        fig_f.add_trace(
            go.Scatter(
                x=df.index,
                y=df["Close"],
                mode="lines",
                name="Close",
                line=dict(color=NEON_YELLOW),
            )
        )
        for name, val in levels.items():
            fig_f.add_hline(
                y=val,
                line_dash="dot",
                line_color=NEON_BLUE,
                annotation_text=name,
                annotation_position="right",
            )
        fig_f.update_layout(
            template="plotly_dark",
            height=400,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_f, use_container_width=True)

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
        macd_line, signal_line, hist = macd(df["Close"])
        m = pd.DataFrame({"MACD": macd_line, "Signal": signal_line, "Hist": hist}).dropna()
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
            st.write("**Scenariusz LONG (na bazie ATR):**")
            st.write(f"SL: {info['sl_long']:.2f}")
            st.write(f"TP: {info['tp_long']:.2f}")
            st.write("**Scenariusz SHORT (na bazie ATR):**")
            st.write(f"SL: {info['sl_short']:.2f}")
            st.write(f"TP: {info['tp_short']:.2f}")
            st.markdown("---")
            st.write(f"**Bid:** {info['bid'] if info['bid'] is not None else 'brak'}")
            st.write(f"**Ask:** {info['ask'] if info['ask'] is not None else 'brak'}")
            if info["spread"] is not None:
                st.write(f"**Spread:** {info['spread']:.4f}")

    # --- AI Chat – jedna spółka ---
    with tab_ai_chat:
        st.subheader(f"💬 AI – Prop-Trader Chat (tylko {sym})")

        for m in st.session_state.chat:
            with st.chat_message(m["role"]):
                st.write(m["content"])

        user_msg = st.chat_input("Pytaj AI o tę spółkę...")
        if user_msg:
            st.session_state.chat.append({"role": "user", "content": user_msg})

            market_ctx = build_market_context_single(df, sym)

            system_prompt = """
Jesteś zawodowym prop-traderem. 
Analizujesz TYLKO jedną spółkę na raz (symbol podany w kontekście rynku).
Mówisz krótko, konkretnie, bez lania wody.

Zasady:
- możesz sugerować kierunek (LONG / SHORT / NEUTRAL), ale nie jako poradę inwestycyjną
- opierasz się na RSI(14), ATR(14), EMA20, EMA50, trendzie oraz ostatnim ruchu ceny
- możesz odwołać się do poziomów SL/TP, jeśli setup jest sensowny
- unikasz ogólników typu „rynek jest niepewny” – zawsze formułujesz scenariusz A/B

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

    # --- AI Multi Verdict – wiele spółek ---
    with tab_ai_multi:
        st.subheader("🧠 AI Multi Verdict – analiza wielu spółek naraz")

        if not st.session_state.symbols:
            st.info("Brak spółek do analizy.")
        else:
            st.write(
                f"Spółki do analizy: {', '.join(st.session_state.symbols)} (realnie sensownie do ~20)."
            )

            now = time.time()
            auto_run = st.checkbox(
                "Automatyczna analiza AI zgodnie z suwakiem odświeżania AI",
                value=False,
            )
            run_ai_now = st.button("🔍 Uruchom analizę AI teraz")

            should_run_ai = False
            if run_ai_now:
                should_run_ai = True
            elif auto_run and (now - st.session_state.last_ai_run > ai_interval_sec):
                should_run_ai = True

            if should_run_ai and st.session_state.symbols:
                multi_ctx = build_multi_context(
                    st.session_state.symbols, range_p, tf
                )

                system_prompt_multi = """
Jesteś zawodowym prop-traderem i risk managerem w desk'u prop-tradingowym.
Dostajesz dane rynkowe i nagłówki newsów dla wielu spółek naraz.

Twoje zadanie:
1) Dla każdej spółki wystaw werdykt: BUY / SELL / HOLD.
2) Zrób tabelę w formie tekstowej (kolumny: Symbol | Werdykt | Confidence(0-100) | Krótki komentarz).
3) Na końcu daj ZBIORCZY WERDYKT:
   - TOP 5 najlepszych setupów (krótko dlaczego),
   - spółki do unikania (krótko dlaczego),
   - ogólny sentyment (byczy / niedźwiedzi / neutralny).

Nie podajesz linków, nie odsyłasz do stron.
Nie udzielasz porad inwestycyjnych – to tylko analiza scenariuszy.
"""

                messages_multi = [
                    {"role": "system", "content": system_prompt_multi},
                    {
                        "role": "system",
                        "content": "Dane rynkowe i newsy dla wielu spółek:\n"
                        + multi_ctx,
                    },
                ]

                res_multi = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_multi,
                )
                st.session_state.ai_multi_result = res_multi.choices[0].message.content
                st.session_state.last_ai_run = now

            if st.session_state.ai_multi_result:
                st.markdown("### Werdykt AI:")
                st.text(st.session_state.ai_multi_result)
            else:
                st.info(
                    "Brak jeszcze analizy AI. Użyj przycisku powyżej lub włącz automatyczną analizę."
                )

  # --- HEATMAPA RYNKU ---
with tab_heatmap:
    st.subheader("🔥 Heatmapa Rynku – zmiana % dla wszystkich spółek")

    if not st.session_state.symbols:
        st.info("Brak spółek do wyświetlenia heatmapy.")
    else:
        heat_data = []

        for s in st.session_state.symbols:
            df_h = get_price_data(s, "1d", "1h")

            if df_h.empty:
                heat_data.append({"Symbol": s, "Change": 0})
                continue

            close_h = df_h["Close"].astype(float)
            last_h = float(close_h.iloc[-1])
            prev_h = float(close_h.iloc[-2]) if len(close_h) > 1 else last_h

            change = ((last_h - prev_h) / prev_h * 100) if prev_h != 0 else 0
            heat_data.append({"Symbol": s, "Change": change})

        heat_df = pd.DataFrame(heat_data)

        def color_map(val):
            if val > 0:
                return f"background-color: rgba(0, 255, 0, {min(abs(val)/10, 1)})"
            elif val < 0:
                return f"background-color: rgba(255, 0, 0, {min(abs(val)/10, 1)})"
            else:
                return "background-color: rgba(128,128,128,0.3)"

        st.dataframe(
            heat_df.style
                .apply(lambda col: col.map(color_map) if col.name == "Change" else col)
                .format({"Change": "{:+.2f}%"})
        )

        st.caption("Kolor = kierunek ruchu, intensywność = siła zmiany procentowej.")



if __name__ == "__main__":
    main()
