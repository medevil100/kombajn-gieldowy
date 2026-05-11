import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

st.set_page_config(page_title="Heatmap PRO", layout="wide")

# --- OpenAI config ---
AI_MODEL = "gpt-4o-mini"
client = OpenAI()  # API key z sekreta

# --- Pobieranie danych ---
def get_price_data(symbol, period="5d", interval="1h"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

# --- Obliczenia PRO ---
def compute_metrics(symbol):
    df = get_price_data(symbol, "5d", "1h")
    if df.empty or len(df) < 3:
        return {
            "Symbol": symbol,
            "Change": 0.0,
            "Volume": 0.0,
            "ATR": 0.0,
            "Trend": "NONE",
            "Signal": "NEUTRAL",
            "MomentumScore": 0.0,
            "VolatilityScore": 0.0,
            "TrendStrength": 0.0,
            "RiskScore": 50.0,
            "SetupScore": 0.0,
        }

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = ((last - prev) / prev * 100) if prev != 0 else 0.0

    # ATR
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_series = tr.rolling(14).mean()
    atr = float(atr_series.iloc[-1]) if not atr_series.dropna().empty else 0.0

    # Trend (EMA)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema20_last = float(ema20.iloc[-1])
    ema50_last = float(ema50.iloc[-1])

    if last > ema20_last > ema50_last:
        trend = "UP"
    elif last < ema20_last < ema50_last:
        trend = "DOWN"
    else:
        trend = "SIDE"

    # Sygnał techniczny
    if trend == "UP" and change > 0:
        signal = "BUY"
    elif trend == "DOWN" and change < 0:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    # MomentumScore
    vol_last = float(volume.iloc[-1])
    vol_prev = float(volume.iloc[-2]) if len(volume) > 1 else vol_last
    vol_change = ((vol_last - vol_prev) / vol_prev * 100) if vol_prev != 0 else 0.0

    raw_momentum = change * 0.7 + vol_change * 0.3
    momentum_score = max(0.0, min(100.0, 50.0 + raw_momentum))

    # VolatilityScore (ATR / cena)
    vol_ratio = (atr / last * 100) if last != 0 else 0.0
    volatility_score = max(0.0, min(100.0, vol_ratio * 2))

    # TrendStrength
    trend_diff = abs(ema20_last - ema50_last) / last * 100 if last != 0 else 0.0
    trend_strength = max(0.0, min(100.0, trend_diff * 5))

    # RiskScore
    risk_raw = volatility_score
    risk_score = max(0.0, min(100.0, risk_raw))

    # SetupScore
    setup = 0.0
    if signal == "BUY":
        setup += 30
    elif signal == "SELL":
        setup += 20

    setup += momentum_score * 0.3
    setup += trend_strength * 0.3
    setup -= risk_score * 0.2

    setup_score = max(0.0, min(100.0, setup))

    return {
        "Symbol": symbol,
        "Change": change,
        "Volume": vol_last,
        "ATR": atr,
        "Trend": trend,
        "Signal": signal,
        "MomentumScore": momentum_score,
        "VolatilityScore": volatility_score,
        "TrendStrength": trend_strength,
        "RiskScore": risk_score,
        "SetupScore": setup_score,
    }

# --- Stylowanie tabeli ---
def style_heatmap(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)

    for i, row in df.iterrows():
        ss = row["SetupScore"]
        intensity = min(max(ss / 100.0, 0.0), 1.0)
        base_color = "0,255,0" if ss >= 50 else "255,0,0"
        row_bg = f"background-color: rgba({base_color},{0.15 + 0.35*intensity})"

        for col in df.columns:
            styles.loc[i, col] = row_bg

        c = row["Change"]
        if c > 0:
            styles.loc[i, "Change"] = f"background-color: rgba(0,255,0,{min(abs(c)/10,1)})"
        elif c < 0:
            styles.loc[i, "Change"] = f"background-color: rgba(255,0,0,{min(abs(c)/10,1)})"
        else:
            styles.loc[i, "Change"] = "background-color: rgba(128,128,128,0.3)"

        if row["Trend"] == "UP":
            styles.loc[i, "Trend"] = "background-color: rgba(0,255,0,0.4)"
        elif row["Trend"] == "DOWN":
            styles.loc[i, "Trend"] = "background-color: rgba(255,0,0,0.4)"
        else:
            styles.loc[i, "Trend"] = "background-color: rgba(128,128,128,0.3)"

        if row["Signal"] == "BUY":
            styles.loc[i, "Signal"] = "background-color: rgba(0,255,0,0.6)"
        elif row["Signal"] == "SELL":
            styles.loc[i, "Signal"] = "background-color: rgba(255,0,0,0.6)"
        else:
            styles.loc[i, "Signal"] = "background-color: rgba(128,128,128,0.3)"

    return df.style.apply(lambda _: styles, axis=None).format(
        {
            "Change": "{:+.2f}%",
            "Volume": "{:,.0f}",
            "ATR": "{:.4f}",
            "MomentumScore": "{:.1f}",
            "VolatilityScore": "{:.1f}",
            "TrendStrength": "{:.1f}",
            "RiskScore": "{:.1f}",
            "SetupScore": "{:.1f}",
        }
    )

# --- AI Verdict dla TOP 5 ---
def ai_verdict_for_top5(top_df: pd.DataFrame) -> str:
    if top_df.empty:
        return "Brak spółek do analizy."

    lines = []
    for _, row in top_df.iterrows():
        lines.append(
            f"{row['Symbol']}: "
            f"SetupScore={row['SetupScore']:.1f}, "
            f"Change={row['Change']:+.2f}%, "
            f"Trend={row['Trend']}, "
            f"Signal={row['Signal']}, "
            f"Momentum={row['MomentumScore']:.1f}, "
            f"Volatility={row['VolatilityScore']:.1f}, "
            f"Risk={row['RiskScore']:.1f}"
        )
    context = "\n".join(lines)

    system_prompt = """
Jesteś zawodowym prop-traderem i risk managerem.
Dostajesz listę maksymalnie 5 spółek z metrykami:
- SetupScore (0-100)
- Change %
- Trend (UP/DOWN/SIDE)
- Signal (BUY/SELL/NEUTRAL)
- MomentumScore
- VolatilityScore
- RiskScore

Twoje zadanie:
1) Dla każdej spółki daj krótki werdykt (1-3 zdania): co jest mocne, co słabe, co trzeba obserwować.
2) Na końcu daj zbiorczy komentarz:
   - która spółka wygląda NAJCIEKAWEJ jako setup,
   - gdzie ryzyko jest najwyższe,
   - co musi się stać, żeby setup był „A+”.

Pisz krótko, konkretnie, bez lania wody.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Oto dane spółek:\n{context}"},
    ]

    res = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
    )
    return res.choices[0].message.content

# --- Wykres PRO ---
def plot_pro_chart(symbol: str):
    df = get_price_data(symbol, "3mo", "1d")
    if df.empty:
        st.warning("Brak danych do wykresu.")
        return

    close = df["Close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    fig = go.Figure()
    fig.add_candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Cena",
    )
    fig.add_trace(go.Scatter(x=df.index, y=ema20, mode="lines", name="EMA20", line=dict(color="cyan")))
    fig.add_trace(go.Scatter(x=df.index, y=ema50, mode="lines", name="EMA50", line=dict(color="magenta")))
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean().abs()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.dropna()

    st.subheader("RSI(14)")
    st.line_chart(rsi)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_df = pd.DataFrame({"MACD": macd_line, "Signal": signal_line}).dropna()

    st.subheader("MACD")
    st.line_chart(macd_df)

    # ATR
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_series = tr.rolling(14).mean().dropna()

    st.subheader("ATR(14)")
    st.line_chart(atr_series)

# --- Aplikacja ---
def main():
    st.title("🔥 HEATMAPA PRO — Setup Scanner + AI + Wykres PRO + Skaner Sygnałów")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []
    if "ai_top5_comment" not in st.session_state:
        st.session_state.ai_top5_comment = ""

    symbols_input = st.sidebar.text_input("Dodaj spółki (oddzielone przecinkami):", "")

    if st.sidebar.button("Dodaj"):
        for raw in symbols_input.split(","):
            sym = raw.strip().upper()
            if sym and sym not in st.session_state.symbols:
                st.session_state.symbols.append(sym)

    if st.sidebar.button("Wyczyść"):
        st.session_state.symbols = []
        st.session_state.ai_top5_comment = ""

    if not st.session_state.symbols:
        st.warning("Dodaj spółki, aby kontynuować.")
        return

    # --- TABS ---
    tab_heatmap, tab_chart, tab_scanner = st.tabs([
        "📊 Heatmap PRO + AI",
        "📈 Wykres PRO",
        "📡 Skaner Sygnałów"
    ])

    # --- HEATMAP + AI ---
    with tab_heatmap:
        rows = [compute_metrics(s) for s in st.session_state.symbols]
        df = pd.DataFrame(rows)
        df = df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        st.subheader("🏆 TOP 5 setupów (kafelki)")

        top_n = min(5, len(df))
        if top_n > 0:
            top_df = df.head(top_n)
            cols = st.columns(top_n)
            for idx, (_, row) in enumerate(top_df.iterrows()):
                with cols[idx]:
                    ss = row["SetupScore"]
                    color = "🟢" if ss >= 60 else ("🟡" if ss >= 40 else "🔴")
                    st.markdown(f"### {color} {row['Symbol']}")
                    st.write(f"**SetupScore:** {ss:.1f} / 100")
                    st.write(f"**Change:** {row['Change']:+.2f}%")
                    st.write(f"**Trend:** {row['Trend']}")
                    st.write(f"**Signal:** {row['Signal']}")
                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}")
                    st.write(f"**Volatility:** {row['VolatilityScore']:.1f}")
                    st.write(f"**Risk:** {row['RiskScore']:.1f}")

            st.markdown("---")
            if st.button("🧠 Generuj komentarz AI dla TOP 5"):
                with st.spinner("AI analizuje TOP 5 setupów..."):
                    st.session_state.ai_top5_comment = ai_verdict_for_top5(top_df)

            if st.session_state.ai_top5_comment:
                st.subheader("🧠 Komentarz AI (prop-trader view)")
                st.markdown(st.session_state.ai_top5_comment)

        st.markdown("---")
        st.subheader("📊 Pełna tabela — Heatmapa PRO")
        st.dataframe(style_heatmap(df), use_container_width=True)

    # --- WYKRES PRO ---
    with tab_chart:
        st.subheader("📈 Wykres PRO dla wybranej spółki")
        symbol_for_chart = st.selectbox(
            "Wybierz spółkę do wykresu:", st.session_state.symbols
        )
        plot_pro_chart(symbol_for_chart)

    # --- SKANER SYGNAŁÓW ---
    with tab_scanner:
        st.subheader("📡 BUY / SELL Radar — Skaner Sygnałów")

        rows = [compute_metrics(s) for s in st.session_state.symbols]
        scan_df = pd.DataFrame(rows)
        scan_df = scan_df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

        buy_df = scan_df[
            (scan_df["Signal"] == "BUY") &
            (scan_df["Trend"] == "UP") &
            (scan_df["SetupScore"] >= 50) &
            (scan_df["MomentumScore"] >= 40)
        ]

        sell_df = scan_df[
            (scan_df["Signal"] == "SELL") &
            (scan_df["Trend"] == "DOWN") &
            (scan_df["SetupScore"] >= 40)
        ]

        neutral_df = scan_df[
            ~scan_df.index.isin(buy_df.index) &
            ~scan_df.index.isin(sell_df.index)
        ]

        st.markdown("## 🟢 BUY Radar")
        if buy_df.empty:
            st.info("Brak mocnych sygnałów BUY.")
        else:
            cols = st.columns(min(5, len(buy_df)))
            for idx, (_, row) in enumerate(buy_df.iterrows()):
                with cols[idx % len(cols)]:
                    st.markdown(f"### 🟢 {row['Symbol']}")
                    st.write(f"**SetupScore:** {row['SetupScore']:.1f}")
                    st.write(f"**Momentum:** {row['MomentumScore']:.1f}")
                    st.write(f"**Trend:** {row['Trend']}")
                    st.write(f"**Change:** {row['Change']:+.2f}%")

        st.markdown("---")

        st.markdown("## 🔴 SELL Radar")
        if sell_df.empty:
            st.info("Brak mocnych sygnałów SELL.")
        else:
            cols = st.columns(min(5, len(sell_df)))
            for idx, (_, row) in enumerate(sell_df.iterrows()):
                with cols[idx % len(cols)]:
                    st.markdown(f"### 🔴 {row['Symbol']}")
                    st.write(f"**SetupScore:** {row['SetupScore']:.1f}")
                    st.write(f"**Volatility:** {row['VolatilityScore']:.1f}")
                    st.write(f"**Trend:** {row['Trend']}")
                    st.write(f"**Change:** {row['Change']:+.2f}%")

        st.markdown("---")

        st.markdown("## 🟡 Neutral Radar")
        if neutral_df.empty:
            st.info("Brak neutralnych setupów.")
        else:
            st.dataframe(
                neutral_df[[
                    "Symbol", "SetupScore", "Trend", "Signal",
                    "MomentumScore", "VolatilityScore", "RiskScore"
                ]],
                use_container_width=True
            )

if __name__ == "__main__":
    main()
