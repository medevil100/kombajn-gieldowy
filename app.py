
import streamlit as st
import pandas as pd
import numpy as np
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
import time
import plotly.graph_objects as go
import plotly.express as px

# =========================
# KONFIG: TICKERY / ID / TV
# =========================

INVESTING_URLS = {
    "ATT.WA": "https://www.investing.com/equities/grupa-azoty-sa",
    # dopisz swoje:
    # "HRT.WA": "https://www.investing.com/equities/hrt-wa",
}

INVESTING_IDS = {
    "ATT.WA": 945,
    # "HRT.WA": 1126841,
}

TRADINGVIEW_SYMBOLS = {
    "ATT.WA": "GPW:ATT",
    # "HRT.WA": "GPW:HRT",
}

# =========================
# SCRAPER: DANE BIEŻĄCE
# =========================

def get_investing_live(url: str):
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )
    r = scraper.get(url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    price_el = soup.select_one("div.instrument-price_instrument-price__3uw25 span.text-2xl")
    price = float(price_el.text.replace("\xa0", "").replace(",", ".")) if price_el else None

    change_el = soup.select_one("div.instrument-price_change-percent__19cas span")
    change_pct = None
    if change_el:
        txt = change_el.text.replace("%", "").replace("\xa0", "").replace(",", ".")
        try:
            change_pct = float(txt)
        except ValueError:
            change_pct = None

    stats = {}
    rows = soup.select("div.instrument-stats_instrument-stats__1x0eu div.flex.flex-col")
    for row in rows:
        label_el = row.select_one("span.text-xs")
        value_el = row.select_one("span.text-sm")
        if not label_el or not value_el:
            continue
        label = label_el.text.strip()
        value = value_el.text.strip().replace("\xa0", "").replace(",", ".")
        try:
            if value.endswith("K"):
                value = float(value[:-1]) * 1_000
            elif value.endswith("M"):
                value = float(value[:-1]) * 1_000_000
            else:
                value = float(value)
        except ValueError:
            pass
        stats[label] = value

    return {"price": price, "change_pct": change_pct, "stats": stats}

# =========================
# SCRAPER: HISTORIA OHLC
# =========================

def get_investing_history(instrument_id: int, start="2020-01-01", end=None):
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    url = (
        f"https://api.investing.com/api/financialdata/historical/"
        f"{instrument_id}?interval=P1D&start-date={start}&end-date={end}"
    )

    scraper = cloudscraper.create_scraper()
    r = scraper.get(url)
    r.raise_for_status()
    data = r.json()
    rows = data.get("data", [])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], unit="ms")
    df = df.rename(columns={
        "date": "Date",
        "last_close": "Close",
        "last_open": "Open",
        "last_max": "High",
        "last_min": "Low",
        "volume": "Volume"
    })
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df = df.sort_values("Date").set_index("Date")
    return df

# =========================
# WSKAŹNIKI TECHNICZNE
# =========================

def compute_indicators(df: pd.DataFrame):
    out = {}

    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    out["ATR"] = tr.rolling(14).mean().iloc[-1]

    out["EMA20"] = df["Close"].ewm(span=20).mean().iloc[-1]
    out["EMA50"] = df["Close"].ewm(span=50).mean().iloc[-1]

    ema12 = df["Close"].ewm(span=12).mean()
    ema26 = df["Close"].ewm(span=26).mean()
    out["MACD"] = ema12.iloc[-1] - ema26.iloc[-1]

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    out["RSI"] = 100 - (100 / (1 + rs.iloc[-1]))

    return out

# =========================
# AI TURBO — OPIS
# =========================

def ai_turbo(row):
    txt = []
    txt.append(f"{row['Symbol']}: trend {row['Trend']}, sygnał {row['Signal']}, setup {row['SetupScore']:.1f}/100.")

    if row["RSI"] < 30:
        txt.append("RSI wyprzedany — możliwy bounce.")
    elif row["RSI"] > 70:
        txt.append("RSI wykupiony — możliwa korekta.")
    else:
        txt.append("RSI neutralny.")

    if row["EMA20"] > row["EMA50"]:
        txt.append("EMA20 > EMA50 — krótkoterminowy trend wzrostowy.")
    else:
        txt.append("EMA20 < EMA50 — trend spadkowy.")

    if row["ATR"] / row["Price"] > 0.05:
        txt.append("Wysoka zmienność — ostrożnie z pozycją.")
    else:
        txt.append("Zmienność umiarkowana.")

    return " ".join(txt)

# =========================
# ANALIZA SYMBOLU
# =========================

def analyze_symbol(symbol: str):
    url = INVESTING_URLS.get(symbol)
    inst_id = INVESTING_IDS.get(symbol)

    if not url or not inst_id:
        return {"Symbol": symbol, "Error": "Brak URL/ID w konfiguracji"}

    live = get_investing_live(url)
    df = get_investing_history(inst_id)

    if df.empty:
        return {"Symbol": symbol, "Error": "Brak danych historycznych"}

    ind = compute_indicators(df)

    last = df["Close"].iloc[-1]
    prev = df["Close"].iloc[-2]
    change = (last - prev) / prev * 100

    trend = "UP" if ind["EMA20"] > ind["EMA50"] else "DOWN"
    signal = "BUY" if trend == "UP" else "SELL"

    momentum = max(0, min(100, 50 + change))
    setup = max(0, min(100, momentum * 0.3 + (20 if signal == "BUY" else 10)))

    row = {
        "Symbol": symbol,
        "Price": last,
        "Change%": change,
        "ATR": ind["ATR"],
        "EMA20": ind["EMA20"],
        "EMA50": ind["EMA50"],
        "MACD": ind["MACD"],
        "RSI": ind["RSI"],
        "Trend": trend,
        "Signal": signal,
        "Momentum": momentum,
        "SetupScore": setup,
        "DF": df,
    }
    row["AI"] = ai_turbo(row)
    return row

# =========================
# WYKRES ŚWIECOWY (Plotly)
# =========================

def plot_candles(df: pd.DataFrame, symbol: str):
    fig = go.Figure(data=[
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=symbol
        )
    ])
    fig.update_layout(
        title=f"Wykres świecowy — {symbol}",
        xaxis_title="Data",
        yaxis_title="Cena",
        height=500,
    )
    return fig

# =========================
# HEATMAPA SETUPÓW
# =========================

def plot_heatmap(df: pd.DataFrame):
    if df.empty:
        return go.Figure()
    heat_df = df.set_index("Symbol")[["SetupScore", "RSI", "Momentum"]]
    fig = px.imshow(
        heat_df.T,
        color_continuous_scale="RdYlGn",
        aspect="auto",
        labels=dict(x="Symbol", y="Metryka", color="Wartość"),
        title="Heatmapa setupów"
    )
    return fig

# =========================
# TRADINGVIEW WIDGET (embed)
# =========================

def tradingview_widget(symbol: str):
    tv_symbol = TRADINGVIEW_SYMBOLS.get(symbol)
    if not tv_symbol:
        st.info("Brak symbolu TradingView w konfiguracji.")
        return
    code = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_chart"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
          "width": "100%",
          "height": 500,
          "symbol": "{tv_symbol}",
          "interval": "D",
          "timezone": "Etc/UTC",
          "theme": "dark",
          "style": "1",
          "locale": "en",
          "toolbar_bg": "#f1f3f6",
          "enable_publishing": false,
          "hide_top_toolbar": false,
          "hide_legend": false,
          "save_image": false,
          "container_id": "tradingview_chart"
      }});
      </script>
    </div>
    """
    st.components.v1.html(code, height=520)

# =========================
# STREAMLIT UI
# =========================

st.set_page_config(page_title="KOMBAJN 4.0", layout="wide")
st.title("⚡ KOMBAJN 4.0 — Investing.com + Świeczki + Heatmapa + AI Turbo")

default_syms = ",".join(INVESTING_URLS.keys())
symbols_input = st.text_input("Tickery (po przecinku):", default_syms)
symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]

if st.button("Skanuj rynek"):
    results = []
    for s in symbols:
        with st.spinner(f"Analizuję {s}..."):
            res = analyze_symbol(s)
            results.append(res)
            time.sleep(0.8)

    df = pd.DataFrame(results)
    if "Error" in df.columns:
        df_ok = df[df["Error"].isna()] if df["Error"].notna().any() else df
    else:
        df_ok = df

    df_ok = df_ok.sort_values("SetupScore", ascending=False)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📊 Ranking setupów")
        st.dataframe(df_ok[["Symbol", "Price", "Change%", "ATR", "EMA20", "EMA50", "RSI", "Trend", "Signal", "Momentum", "SetupScore"]])

        st.subheader("🔥 Heatmapa")
        st.plotly_chart(plot_heatmap(df_ok), use_container_width=True)

    with col2:
        st.subheader("🤖 AI Turbo — komentarze")
        for _, row in df_ok.iterrows():
            st.markdown(f"**{row['Symbol']}**")
            st.write(row["AI"])
            st.write("---")

    st.subheader("📈 Wykres świecowy (Plotly)")
    selected = st.selectbox("Wybierz symbol do wykresu:", df_ok["Symbol"].tolist())
    sel_row = next(r for r in results if r["Symbol"] == selected)
    st.plotly_chart(plot_candles(sel_row["DF"], selected), use_container_width=True)

    st.subheader("📊 TradingView widget")
    tradingview_widget(selected)

