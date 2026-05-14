
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from openai import OpenAI
from sklearn.ensemble import RandomForestClassifier

# =========================================================
# KONFIGURACJA / UI
# =========================================================
st.set_page_config(page_title="AI ALPHA KOMBAJN ULTRA v2", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #0d1117; color: #c9d1d9; }
.block-container { padding-top: 1rem; }
.ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
.top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
.stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

DB_FILE = "tickers_db.txt"

def load_tickers_default():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, BTC-USD, NVDA, TSLA"
        except:
            return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# =========================================================
# FUNKCJE WSPÓLNE
# =========================================================
def calculate_rsi(series, window=14):
    if len(series) < window:
        return pd.Series([50] * len(series), index=series.index)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_yf_ohlc(symbol, period="1y", interval="1d"):
    df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df["time"] = df.index
    return df.reset_index(drop=True)

# =========================================================
# SILNIK: MONITORING (v12.1)
# =========================================================
def get_analysis(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)

        if d15.empty or d1d.empty:
            return None

        if isinstance(d15.columns, pd.MultiIndex):
            d15.columns = d15.columns.get_level_values(0)
        if isinstance(d1d.columns, pd.MultiIndex):
            d1d.columns = d1d.columns.get_level_values(0)

        price = float(d15["Close"].iloc[-1])
        prev_close = float(d1d["Close"].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100

        sma200 = d1d["Close"].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#00ff88" if price > sma200 else "#ff4b4b"

        atr = (d1d["High"] - d1d["Low"]).rolling(14).mean().iloc[-1]
        pivot = (d1d["High"].iloc[-2] + d1d["Low"].iloc[-2] + d1d["Close"].iloc[-2]) / 3

        delta = d15["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        if rsi < 32:
            rec, rec_col = "KUPUJ", "#238636"
        elif rsi > 68:
            rec, rec_col = "SPRZEDAJ", "#da3633"
        else:
            rec, rec_col = "CZEKAJ", "#8b949e"

        return {
            "symbol": symbol,
            "price": price,
            "change": change_pct,
            "rsi": rsi,
            "rec": rec,
            "rec_col": rec_col,
            "trend": trend_label,
            "trend_col": trend_color,
            "pivot": pivot,
            "tp": price + (atr * 1.5),
            "sl": price - (atr * 1.2),
            "df": d15,
        }
    except:
        return None

# =========================================================
# SILNIK: PORTFEL (z konsoli)
# =========================================================
MOJE_AKCJE = {
    "BCS.WA": [5.610, 200],
    "STX.WA": [2.753, 2050],
    "RVU.WA": [25.10, 100],
    "GOSS": [0.45, 2000],
}

def pobierz_kurs_usd():
    try:
        usd = yf.download("USDPLN=X", period="1d", interval="1m", progress=False)
        if isinstance(usd.columns, pd.MultiIndex):
            usd.columns = usd.columns.get_level_values(0)
        return float(usd["Close"].iloc[-1])
    except:
        return 4.0

def analiza_portfela():
    kurs_usd = pobierz_kurs_usd()
    rows = []
    total_pln = 0.0
    total_invested_pln = 0.0

    for ticker, dane in MOJE_AKCJE.items():
        try:
            cena_wejscia, ilosc = dane
            df = yf.download(ticker, period="60d", interval="1d", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty:
                continue

            cena_teraz = float(df["Close"].iloc[-1])
            zysk_proc = ((cena_teraz - cena_wejscia) / cena_wejscia) * 100

            mnoznik = kurs_usd if ".WA" not in ticker else 1
            wartosc_pln = (cena_teraz * ilosc) * mnoznik
            invested_pln = (cena_wejscia * ilosc) * mnoznik

            total_pln += wartosc_pln
            total_invested_pln += invested_pln

            sma20 = float(df["Close"].rolling(window=20).mean().iloc[-1])
            status = "OK" if cena_teraz > sma20 else "SŁABNIE"

            rows.append(
                {
                    "Ticker": ticker,
                    "Cena wejścia": cena_wejscia,
                    "Ilość": ilosc,
                    "Cena teraz": cena_teraz,
                    "Zysk %": zysk_proc,
                    "Wartość PLN": wartosc_pln,
                    "Status": status,
                }
            )
        except:
            continue

    summary = None
    if total_invested_pln > 0:
        calkowity_zysk = total_pln - total_invested_pln
        summary = {
            "Łączna wartość": total_pln,
            "Zysk/Strata": calkowity_zysk,
            "Zysk %": (calkowity_zysk / total_invested_pln) * 100,
            "Kurs USD": kurs_usd,
        }

    return pd.DataFrame(rows), summary

# =========================================================
# SILNIK: ML – POJEDYNCZA SPÓŁKA
# =========================================================
def ml_prognoza_ticker(symbol, period="2y"):
    df = yf.download(symbol, period=period, interval="1d", progress=False)
    if df.empty:
        return None, None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))

    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["SMA_50"] = df["Close"].rolling(window=50).mean()
    df["Trend_Up"] = np.where(df["SMA_20"] > df["SMA_50"], 1, 0)
    df["Vol_Change"] = df["Volume"].pct_change()

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)

    if df.empty:
        return None, None

    features = ["Close", "Volume", "RSI", "Trend_Up", "Vol_Change"]
    X = df[features]
    y = (df["Close"].shift(-1) > df["Close"]).astype(int)
    y = y.loc[X.index]
    X = X.iloc[:-1]
    y = y.iloc[:-1]

    if len(X) < 30:
        return None, None

    train_size = int(len(X) * 0.8)
    X_train = X[:train_size]
    y_train = y[:train_size]

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    ostatnie_dane = X.tail(1)
    prognoza = model.predict(ostatnie_dane)[0]
    szansa = model.predict_proba(ostatnie_dane)[0][1]

    return prognoza, szansa

# =========================================================
# SILNIK: BIOTECH RADAR (ML)
# =========================================================
USA_BIOTECH = [
    "GOSS",
    "TCRX",
    "HUMA",
    "FATE",
    "PLRX",
    "TTOO",
    "IMUX",
    "IOVA",
    "SLS",
    "ATHE",
    "BDRX",
    "MREO",
    "XLO",
    "ACRS",
    "AURA",
    "DRMA",
    "BOLT",
    "VINC",
    "NRSN",
]

POLSKA_BIOTECH = [
    "BCX.WA",
    "SCP.WA",
    "CLN.WA",
    "RVU.WA",
    "SLV.WA",
    "MAB.WA",
    "BMX.WA",
    "SNT.WA",
    "PHN.WA",
]

WSZYSTKIE_SPOLKI_BIOTECH = USA_BIOTECH + POLSKA_BIOTECH

def przygotuj_dane_biotech(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df["RSI"] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    df["RVOL"] = df["Volume"] / df["Volume"].rolling(window=20).mean()
    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["Trend"] = np.where(df["Close"] > df["SMA_20"], 1, 0)
    df["Target"] = (df["Close"].shift(-3) > df["Close"]).astype(int)

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)
    return df

def biotech_radar():
    ranking = []
    for ticker in WSZYSTKIE_SPOLKI_BIOTECH:
        try:
            df = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
            if df.empty or len(df) < 30:
                continue

            df = przygotuj_dane_biotech(df)
            if df.empty:
                continue

            features = ["Close", "RSI", "Trend", "RVOL"]
            X = df[features]
            y = df["Target"]

            if len(X) < 30:
                continue

            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model.fit(X[:-3], y[:-3])

            ostatnie = X.tail(1)
            szansa = model.predict_proba(ostatnie)[0][1] * 100
            rvol = float(df["RVOL"].iloc[-1])
            cena = float(df["Close"].iloc[-1])

            ranking.append(
                {
                    "Ticker": ticker,
                    "Szansa %": round(szansa, 1),
                    "RVOL": round(rvol, 2),
                    "Cena": round(cena, 4 if (".WA" not in ticker and cena < 1) else 2),
                }
            )
        except:
            continue

    if not ranking:
        return pd.DataFrame()
    return pd.DataFrame(ranking).sort_values(by="Szansa %", ascending=False)

# =========================================================
# AI HELPER
# =========================================================
def get_openai_client(api_key: str | None):
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except:
        return None

def call_gpt(client: OpenAI | None, system_prompt: str, user_prompt: str) -> str:
    if client is None:
        return "(AI OFF – brak poprawnego klucza OpenAI)"
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"(AI ERROR: {e})"

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.title("⚙️ KOMBAJN ULTRA v2")

    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("✅ OpenAI Key z Secrets")
    else:
        api_key = st.text_input("OpenAI Key", type="password")
        if not api_key:
            st.warning("Dodaj klucz w Secrets lub wpisz go tutaj.")

    client = get_openai_client(api_key)

    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers_default())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f:
            f.write(tickers_input)
        st.rerun()

    mode = st.selectbox(
        "Tryb",
        [
            "Monitoring rynku",
            "Szczegóły + wykres",
            "Portfel",
            "ML: prognoza spółki",
            "Biotech Radar (ML)",
            "AI alerty z listy",
        ],
    )

# =========================================================
# LOGIKA GŁÓWNA
# =========================================================
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

st.title("📈 AI ALPHA KOMBAJN ULTRA v2 (bez XTB)")

# ---------------- MONITORING ----------------
if mode == "Monitoring rynku":
    data_list = []
    for t in tickers:
        res = get_analysis(t)
        if res:
            data_list.append(res)

    if not data_list:
        st.warning("Brak danych dla podanych tickerów.")
    else:
        st.subheader("📊 Monitoring rynku")
        top_cols = st.columns(min(len(data_list), 5))

        for i, d in enumerate(data_list[:10]):
            with top_cols[i % 5]:
                c_col = "#00ff88" if d["change"] >= 0 else "#ff4b4b"
                st.markdown(
                    f"""
                    <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                        <b>{d['symbol']}</b><br>
                        <span style="color:{c_col}; font-weight:bold;">{d['price']:.2f}</span><br>
                        <span style="font-size:0.8rem; color:{d['trend_col']};">{d['trend']}</span><br>
                        <div style="background:{d['rec_col']}; font-size:0.7rem; border-radius:3px; margin:5px 0; color:white;">{d['rec']}</div>
                        <span class="stat-label">RSI: {d['rsi']:.1f} | P: {d['pivot']:.1f}</span>
                    </div>
                """,
                    unsafe_allow_html=True,
                )

        for d in data_list:
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f"### {d['symbol']} ({d['trend']})")
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**Pivot:** {d['pivot']:.2f} | **RSI:** {d['rsi']:.1f}")
                st.write(f"**TP:** {d['tp']:.2f} | **SL:** {d['sl']:.2f}")

                if st.button(f"🧠 ANALIZA AI {d['symbol']}", key=f"btn_{d['symbol']}"):
                    prompt = (
                        f"Jako agresywny trader oceń: {d['symbol']}, Cena: {d['price']}, "
                        f"Trend: {d['trend']}, RSI: {d['rsi']:.1f}. Pivot: {d['pivot']:.2f}. "
                        f"Podaj konkretny werdykt i ryzyko 1-10."
                    )
                    ans = call_gpt(client, "Jesteś systemem tradingowym.", prompt)
                    st.session_state[f"ai_{d['symbol']}"] = ans

                if f"ai_{d['symbol']}" in st.session_state:
                    st.info(st.session_state[f"ai_{d['symbol']}"])

            with c2:
                df = d["df"]
                fig = go.Figure(
                    data=[
                        go.Candlestick(
                            x=df.index[-50:],
                            open=df["Open"][-50:],
                            high=df["High"][-50:],
                            low=df["Low"][-50:],
                            close=df["Close"][-50:],
                        )
                    ]
                )
                fig.add_hline(y=d["pivot"], line_dash="dot", line_color="white")
                fig.update_layout(
                    template="plotly_dark",
                    height=300,
                    margin=dict(l=0, r=0, t=0, b=0),
                    xaxis_rangeslider_visible=False,
                )
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

# ---------------- SZCZEGÓŁY + WYKRES ----------------
elif mode == "Szczegóły + wykres":
    st.subheader("Szczegóły spółki – wykres świecowy")
    if not tickers:
        st.warning("Dodaj przynajmniej jeden ticker.")
    else:
        symbol = st.selectbox("Wybierz spółkę", tickers)
        df = get_yf_ohlc(symbol, period="1y", interval="1d")
        if df.empty:
            st.error("Brak danych.")
        else:
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=df["time"],
                        open=df["Open"],
                        high=df["High"],
                        low=df["Low"],
                        close=df["Close"],
                    )
                ]
            )
            fig.update_layout(title=f"Wykres świecowy – {symbol}", height=600, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df.tail(50), use_container_width=True)

# ---------------- PORTFEL ----------------
elif mode == "Portfel":
    st.subheader("Portfel (na bazie yfinance)")
    df_port, summary = analiza_portfela()
    if df_port.empty:
        st.warning("Brak danych portfela.")
    else:
        st.dataframe(df_port, use_container_width=True)
        if summary:
            st.markdown("### Podsumowanie")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Łączna wartość", f"{summary['Łączna wartość']:.2f} PLN")
            col2.metric("Zysk/Strata", f"{summary['Zysk/Strata']:.2f} PLN")
            col3.metric("Zysk %", f"{summary['Zysk %']:.2f}%")
            col4.metric("Kurs USD", f"{summary['Kurs USD']:.2f} PLN")

# ---------------- ML: PROGNOZA SPÓŁKI ----------------
elif mode == "ML: prognoza spółki":
    st.subheader("ML – prognoza wzrostu na jutro")
    if not tickers:
        st.warning("Dodaj przynajmniej jeden ticker.")
    else:
        symbol = st.selectbox("Spółka do analizy ML", tickers)
        if st.button("Uruchom model ML"):
            with st.spinner("Trenuję model i liczę prognozę..."):
                wynik, szansa = ml_prognoza_ticker(symbol)
            if wynik is None:
                st.error("Nie udało się policzyć prognozy (za mało danych?).")
            else:
                st.write(f"**Prognoza wzrostu na jutro:** {'TAK' if wynik == 1 else 'NIE'}")
                st.write(f"**Prawdopodobieństwo wzrostu:** {szansa:.2%}")

# ---------------- BIOTECH RADAR ----------------
elif mode == "Biotech Radar (ML)":
    st.subheader("Biotech Radar – ML skaner okazji (USA + PL)")
    if st.button("Skanuj biotechy"):
        with st.spinner("Skanuję i trenuję modele..."):
            df_bio = biotech_radar()
        if df_bio.empty:
            st.error("Brak wyników.")
        else:
            st.dataframe(df_bio.head(30), use_container_width=True)

# ---------------- AI ALERTY Z LISTY ----------------
elif mode == "AI alerty z listy":
    st.subheader("AI alerty – analiza listy spółek")
    rows = []
    for t in tickers:
        try:
            df = get_yf_ohlc(t, period="200d", interval="1d")
            if df.empty:
                continue
            close = df["Close"]
            rsi = float(calculate_rsi(close).iloc[-1])
            price = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            mom = (price - prev) / prev
            rows.append({"symbol": t, "price": price, "rsi": rsi, "mom20": mom})
        except:
            continue

    if not rows:
        st.warning("Brak danych do analizy.")
    else:
        text = "Wygeneruj alerty tradingowe dla spółek:\n\n"
        for r in rows:
            text += f"- {r['symbol']}: cena {r['price']:.2f}, RSI {r['rsi']:.1f}, momentum {r['mom20']:.2%}\n"

        ans = call_gpt(client, "Jesteś systemem alertów tradingowych.", text)
        st.write(ans)

