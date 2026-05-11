import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Heatmap PRO", layout="wide")

# --- Pobieranie danych ---
def get_price_data(symbol, period="1d", interval="1h"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

# --- Obliczenia PRO ---
def compute_metrics(symbol):
    df = get_price_data(symbol, "5d", "1h")
    if df.empty:
        return {"Symbol": symbol, "Change": 0, "Volume": 0, "ATR": 0, "Trend": "NONE", "Signal": "NEUTRAL"}

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else last
    change = ((last - prev) / prev * 100) if prev != 0 else 0

    # ATR
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    # Trend
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

    if last > ema20 > ema50:
        trend = "UP"
    elif last < ema20 < ema50:
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

    return {
        "Symbol": symbol,
        "Change": change,
        "Volume": volume.iloc[-1],
        "ATR": atr,
        "Trend": trend,
        "Signal": signal,
    }

# --- Stylowanie PRO ---
def style_heatmap(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)

    for i, row in df.iterrows():

        # Zmiana %
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

        # Sygnał
        if row["Signal"] == "BUY":
            styles.loc[i, "Signal"] = "background-color: rgba(0,255,0,0.6)"
        elif row["Signal"] == "SELL":
            styles.loc[i, "Signal"] = "background-color: rgba(255,0,0,0.6)"
        else:
            styles.loc[i, "Signal"] = "background-color: rgba(128,128,128,0.3)"

    return df.style.apply(lambda _: styles, axis=None).format({
        "Change": "{:+.2f}%",
        "Volume": "{:,.0f}",
        "ATR": "{:.4f}",
    })

# --- Aplikacja ---
def main():
    st.title("🔥 HEATMAPA PRO — Stabilna Baza")

    if "symbols" not in st.session_state:
        st.session_state.symbols = []

    symbols_input = st.sidebar.text_input("Dodaj spółki:", "")

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

    st.subheader("🔥 Heatmapa PRO — zmiana %, wolumen, ATR, trend, sygnał")

    rows = []
    for s in st.session_state.symbols:
        rows.append(compute_metrics(s))

    df = pd.DataFrame(rows)

    st.dataframe(style_heatmap(df), use_container_width=True)

if __name__ == "__main__":
    main()
