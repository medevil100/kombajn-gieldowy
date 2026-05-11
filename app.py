import streamlit as st
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
import time

# ============================================
# KONFIGURACJA: TICKERY → URL + ID
# ============================================

INVESTING_URLS = {
    "ATT.WA": "https://www.investing.com/equities/grupa-azoty-sa",
}

INVESTING_IDS = {
    "ATT.WA": 945,
}

# ============================================
# SCRAPER: DANE BIEŻĄCE
# ============================================

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
        except:
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
        except:
            pass
        stats[label] = value

    return {"price": price, "change_pct": change_pct, "stats": stats}

# ============================================
# SCRAPER: HISTORIA OHLC
# ============================================

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

# ============================================
# WSKAŹNIKI TECHNICZNE
# ============================================

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

# ============================================
# AI TURBO — OPIS TECHNICZNY
# ============================================

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

# ============================================
# ANALIZA SYMBOLU
# ============================================

def analyze_symbol(symbol):
    url = INVESTING_URLS.get(symbol)
    inst_id = INVESTING_IDS.get(symbol)

    live = get_investing_live(url)
    df = get_investing_history(inst_id)

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
    }

    row["AI"] = ai_turbo(row)
    return row

# ============================================
# STREAMLIT UI
# ============================================

st.set_page_config(page_title="KOMBAJN 3.0", layout="wide")

st.title("⚡ KOMBAJN 3.0 — Investing.com + AI Turbo")

symbols = st.text_input("Podaj tickery (oddzielone przecinkami):", "ATT.WA")
symbols = [s.strip() for s in symbols.split(",")]

if st.button("Skanuj"):
    results = []
    for s in symbols:
        with st.spinner(f"Analizuję {s}..."):
            res = analyze_symbol(s)
            results.append(res)
            time.sleep(1)

    df = pd.DataFrame(results).sort_values("SetupScore", ascending=False)

    st.subheader("📊 Ranking setupów")
    st.dataframe(df)

    st.subheader("🤖 AI Turbo — komentarze")
    for _, row in df.iterrows():
        st.write(f"### {row['Symbol']}")
        st.write(row["AI"])
        st.write("---")
