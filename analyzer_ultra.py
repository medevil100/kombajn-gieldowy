import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="Heatmap Engine", layout="wide")

# --- Pobieranie danych ---
def get_price_data(symbol, period="1d", interval="1h"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

# --- Heatmapa ---
def build_heatmap(symbols):
    heat_data = []

    for s in symbols:
        df = get_price_data(s, "1d", "1h")

        if df.empty:
            heat_data.append({"Symbol": s, "Change": 0})
            continue

        close = df["Close"].astype(float)
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else last

        change = ((last - prev) / prev * 100) if prev != 0 else 0
        heat_data.append({"Symbol": s, "Change": change})

    return pd.DataFrame(heat_data)

# --- Kolorowanie ---
def color_map(val):
    if val > 0:
        return f"background-color: rgba(0,255,0,{min(abs(val)/10,1)})"
    elif val < 0:
        return f"background-color: rgba(255,0,0,{min(abs(val)/10,1)})"
    return "background-color: rgba(128,128,128,0.3)"

# --- Główna aplikacja ---
def main():
    st.title("🔥 Heatmapa Rynku — Minimalna Stabilna Wersja")

    # Lista spółek
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

    # Wybór aktywnej spółki
    sym = st.sidebar.selectbox("Aktywna spółka:", st.session_state.symbols)

    # Pobranie danych do wykresu
    df = get_price_data(sym, "1mo", "1d")
    if df.empty:
        st.error("Brak danych dla tej spółki.")
        return

    # --- TABS ---
    tab_chart, tab_heatmap = st.tabs(["📈 Wykres", "🔥 Heatmapa"])

    # --- Wykres ---
    with tab_chart:
        st.subheader(f"Wykres {sym}")
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
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

    # --- Heatmapa ---
    with tab_heatmap:
        st.subheader("Heatmapa zmian %")

        heat_df = build_heatmap(st.session_state.symbols)

        st.dataframe(
            heat_df.style
                .applymap(color_map, subset=["Change"])
                .format({"Change": "{:+.2f}%"})
        )

if __name__ == "__main__":
    main()
