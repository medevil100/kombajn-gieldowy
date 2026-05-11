import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Heatmap PRO", layout="wide")

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

    # MomentumScore (prosto: ostatnia zmiana + zmiana wolumenu)
    vol_last = float(volume.iloc[-1])
    vol_prev = float(volume.iloc[-2]) if len(volume) > 1 else vol_last
    vol_change = ((vol_last - vol_prev) / vol_prev * 100) if vol_prev != 0 else 0.0

    raw_momentum = change * 0.7 + vol_change * 0.3
    momentum_score = max(0.0, min(100.0, 50.0 + raw_momentum))  # 0–100

    # VolatilityScore (ATR / cena)
    vol_ratio = (atr / last * 100) if last != 0 else 0.0
    volatility_score = max(0.0, min(100.0, vol_ratio * 2))  # skalowanie

    # TrendStrength (różnica EMA20–EMA50)
    trend_diff = abs(ema20_last - ema50_last) / last * 100 if last != 0 else 0.0
    trend_strength = max(0.0, min(100.0, trend_diff * 5))

    # RiskScore (im większa zmienność, tym większe ryzyko)
    risk_raw = volatility_score
    risk_score = max(0.0, min(100.0, risk_raw))

    # SetupScore – główny wynik
    setup = 0.0
    if signal == "BUY":
        setup += 30
    elif signal == "SELL":
        setup += 20  # też może być okazja, ale innego typu

    setup += momentum_score * 0.3
    setup += trend_strength * 0.3
    setup -= risk_score * 0.2  # im większe ryzyko, tym niższy wynik

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
        # SetupScore – kolor całego wiersza tła
        ss = row["SetupScore"]
        # 0–100 → 0–1
        intensity = min(max(ss / 100.0, 0.0), 1.0)
        base_color = "0,255,0" if ss >= 50 else "255,0,0"  # zielony powyżej 50, czerwony poniżej
        row_bg = f"background-color: rgba({base_color},{0.15 + 0.35*intensity})"

        for col in df.columns:
            styles.loc[i, col] = row_bg

        # Change – nadpisanie kolumny
        c = row["Change"]
        if c > 0:
            styles.loc[i, "Change"] = f"background-color: rgba(0,255,0,{min(abs(c)/10,1)})"
        elif c < 0:
            styles.loc[i, "Change"] = f"background-color: rgba(255,0,0,{min(abs(c)/10,1)})"
        else:
            styles.loc[i, "Change"] = "background-color: rgba(128,128,128,0.3)"

        # Trend
        if row["Trend"] == "UP":
            styles.loc[i, "Trend"] = "background-color: rgba(0,255,0,0.4)"
        elif row["Trend"] == "DOWN":
            styles.loc[i, "Trend"] = "background-color: rgba(255,0,0,0.4)"
        else:
            styles.loc[i, "Trend"] = "background-color: rgba(128,128,128,0.3)"

        # Signal
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

# --- Aplikacja ---
def main():
    st.title("🔥 HEATMAPA PRO — Setup Scanner (Hybrid)")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []

    symbols_input = st.sidebar.text_input("Dodaj spółki (oddzielone przecinkami):", "")

    if st.sidebar.button("Dodaj"):
        for raw in symbols_input.split(","):
            sym = raw.strip().upper()
            if sym and sym not in st.session_state.symbols:
                st.session_state.symbols.append(sym)

    if st.sidebar.button("Wyczyść"):
        st.session_state.symbols = []

    if not st.session_state.symbols:
        st.warning("Dodaj spółki, aby kontynuować.")
        return

    rows = [compute_metrics(s) for s in st.session_state.symbols]
    df = pd.DataFrame(rows)

    # Sortowanie po SetupScore malejąco
    df = df.sort_values("SetupScore", ascending=False).reset_index(drop=True)

    st.subheader("🏆 TOP 5 setupów (kafelki)")

    top_n = min(5, len(df))
    if top_n > 0:
        top_df = df.head(top_n)
        cols = st.columns(top_n)
        for idx, (i, row) in enumerate(top_df.iterrows()):
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
    st.subheader("📊 Pełna tabela — Heatmapa PRO")

    st.dataframe(style_heatmap(df), use_container_width=True)

if __name__ == "__main__":
    main()
