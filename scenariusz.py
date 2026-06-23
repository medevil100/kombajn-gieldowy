import os
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go

from openai import OpenAI
from tavily import TavilyClient


# ============================
#   KLUCZE API
# ============================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


# ============================
#   PARAMETRY ANALIZY
# ============================

ATR_WINDOW = 20
SMA_FAST = 50
SMA_SLOW = 200
K_SL = 1.8
K_TP = 3.5


# ============================
#   POPRAWIONE POBIERANIE DANYCH Z YAHOO
# ============================

def safe_load_yahoo(ticker: str) -> pd.DataFrame | None:
    df = yf.download(
        ticker,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False
    )

    if df is None or df.empty:
        return None

    # Obsługa MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        # Jeśli poziom 1 zawiera ticker → wybierz go
        if ticker.upper() in df.columns.get_level_values(-1):
            df = df.xs(ticker.upper(), axis=1, level=-1)
        else:
            # W przeciwnym razie użyj poziomu 0 (Open, High, Low, Close)
            df.columns = df.columns.get_level_values(0)

    # Normalizacja nazw kolumn
    df.columns = [str(c).strip().capitalize() for c in df.columns]

    required_cols = {"Close", "High", "Low"}
    if not required_cols.issubset(df.columns):
        return None

    df = df.dropna(subset=["Close", "High", "Low"])

    if df.empty:
        return None

    return df


# ============================
#   WSKAŹNIKI
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df[f"SMA{SMA_FAST}"] = df["Close"].rolling(SMA_FAST).mean()
    df[f"SMA{SMA_SLOW}"] = df["Close"].rolling(SMA_SLOW).mean()

    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift(1)).abs()
    lc = (df["Low"] - df["Close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df[f"ATR{ATR_WINDOW}"] = tr.rolling(ATR_WINDOW).mean()

    return df


def detect_trend(row: pd.Series) -> str:
    try:
        sma_fast = float(row.get(f"SMA{SMA_FAST}", np.nan))
        sma_slow = float(row.get(f"SMA{SMA_SLOW}", np.nan))
        price = float(row.get("Close", np.nan))
    except:
        return "Unknown"

    if np.isnan(sma_fast) or np.isnan(sma_slow) or np.isnan(price):
        return "Unknown"

    if sma_fast > sma_slow and price > sma_fast:
        return "Bull"
    elif sma_fast < sma_slow and price < sma_fast:
        return "Bear"
    return "Neutral"


def sl_tp(price: float, atr: float, side: str = "long"):
    if np.isnan(atr):
        return np.nan, np.nan

    if side == "long":
        return price - K_SL * atr, price + K_TP * atr
    else:
        return price + K_SL * atr, price - K_TP * atr


# ============================
#   POPRAWIONE SCENARIUSZE LICZBOWE
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def scenarios_numeric(price: float, df: pd.DataFrame, horizon_days: int = 30) -> pd.DataFrame:
    returns = np.log(df["Close"] / df["Close"].shift(1)).dropna()

    days = np.arange(1, horizon_days + 1)

    if returns.empty:
        return pd.DataFrame(
            {"Bull": price, "Hold": price, "Bear": price},
            index=days
        )

    mu = returns.mean()
    sigma = returns.std()

    if np.isnan(mu):
        mu = 0.0
    if np.isnan(sigma):
        sigma = 0.0

    bull = np.exp(np.log(price) + (mu + sigma) * days)
    base = np.exp(np.log(price) + mu * days)
    bear = np.exp(np.log(price) + (mu - sigma) * days)

    return pd.DataFrame(
        {"Bull": bull, "Hold": base, "Bear": bear},
        index=days
    )


# ============================
#   NEWSY TAVILY
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_news_summary(ticker: str, horizon_days: int = 30) -> str:
    if tavily_client is None:
        return "Brak klucza Tavily."

    try:
        res = tavily_client.search(
            query=f"Najważniejsze wiadomości o spółce {ticker} z ostatnich {horizon_days} dni.",
            max_results=5
        )
    except:
        return "Błąd pobierania newsów."

    items = res.get("results", [])
    if not items:
        return "Brak istotnych newsów."

    lines = []
    for item in items:
        title = item.get("title", "")
        snippet = item.get("content", "")[:300]
        lines.append(f"- {title}: {snippet}")

    return "\n".join(lines)


# ============================
#   AI – KOMENTARZ / SCENARIUSZE
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def ai_analysis_pl(
    ticker, trend, price, atr, sl, tp, scen_df, news_summary, horizon_days
):
    if client is None:
        return "Brak klucza OpenAI."

    scen_last = scen_df.iloc[-1]

    prompt = f"""
Jesteś analitykiem rynkowym piszącym po polsku.

Dane:
- Ticker: {ticker}
- Cena: {price:.2f}
- Trend: {trend}
- ATR: {atr:.2f}
- SL: {sl:.2f}
- TP: {tp:.2f}

Scenariusze liczbowe:
- Bull: {scen_last['Bull']:.2f}
- Bazowy: {scen_last['Hold']:.2f}
- Bear: {scen_last['Bear']:.2f}

News summary:
{news_summary}

Zadania:
1. Podaj sentyment (byczy / neutralny / niedźwiedzi).
2. Napisz komentarz rynkowy.
3. Opisz 3 scenariusze (Bull, Base, Bear).
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=900
        )
        return r.choices[0].message.content.strip()
    except:
        return "Błąd generowania odpowiedzi AI."


# ============================
#   AI – ALERTY TECHNICZNE
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def ai_alerts_pl(ticker, last, prev, trend, horizon_days):
    if client is None:
        return "Brak klucza OpenAI."

    prompt = f"""
Jesteś systemem alertów technicznych.

Dane:
Cena: {last['Close']:.2f}
SMA50: {last.get(f"SMA{SMA_FAST}", np.nan):.2f}
SMA200: {last.get(f"SMA{SMA_SLOW}", np.nan):.2f}
Trend: {trend}

Poprzednia sesja:
Cena: {prev['Close']:.2f if prev is not None else 'brak'}

Zadanie:
Wypisz maksymalnie 5 alertów technicznych (zmiana trendu, wybicia SMA, zmienność).
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        return r.choices[0].message.content.strip()
    except:
        return "- Błąd generowania alertów AI."


# ============================
#   POPRAWIONY WYKRES PLOTLY
# ============================

def plot_scenarios_plotly(scen, price, sl, tp):
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=scen.index, y=scen["Bull"], mode="lines",
                             name="Bull", line=dict(color="green")))
    fig.add_trace(go.Scatter(x=scen.index, y=scen["Hold"], mode="lines",
                             name="Bazowy", line=dict(color="blue")))
    fig.add_trace(go.Scatter(x=scen.index, y=scen["Bear"], mode="lines",
                             name="Bear", line=dict(color="red")))

    if not np.isnan(price):
        fig.add_hline(y=price, line_dash="dash", line_color="gray", annotation_text="Cena")

    if not np.isnan(sl):
        fig.add_hline(y=sl, line_dash="dash", line_color="orange", annotation_text="SL")

    if not np.isnan(tp):
        fig.add_hline(y=tp, line_dash="dash", line_color="purple", annotation_text="TP")

    fig.update_layout(
        title="Scenariusze Bull / Bazowy / Bear",
        xaxis_title="Dni",
        yaxis_title="Cena",
        template="plotly_dark"
    )

    return fig


# ============================
#   STREAMLIT UI
# ============================

st.title("📈 AI Scenariusze Rynkowe – Wersja PRO + AI Alerty (FINAL)")

ticker = st.text_input("Ticker:", "AAPL").upper()
side = st.selectbox("Strona pozycji:", ["long", "short"])
horizon = st.slider("Horyzont (dni):", 20, 60, 30)

if st.button("Analizuj"):
    df = safe_load_yahoo(ticker)

    if df is None:
        st.error("Yahoo Finance nie zwrócił poprawnych danych dla tego tickera.")
        st.stop()

    df = compute_indicators(df)

    last_two = df.tail(2).reset_index(drop=True)
    last = last_two.iloc[-1]
    prev = last_two.iloc[-2] if len(last_two) == 2 else None

    price = float(last["Close"])
    atr = float(last.get(f"ATR{ATR_WINDOW}", np.nan))

    tr = detect_trend(last)
    sl, tp = sl_tp(price, atr, side)
    scen = scenarios_numeric(price, df, horizon)

    st.subheader("📌 Dane techniczne")
    st.write(f"**Trend:** {tr}")
    st.write(f"**Cena:** {round(price, 2)}")
    st.write(f"**ATR:** {round(atr, 2) if not np.isnan(atr) else 'brak'}")
    st.write(f"**SL:** {round(sl, 2) if not np.isnan(sl) else 'brak'}")
    st.write(f"**TP:** {round(tp, 2) if not np.isnan(tp) else 'brak'}")

    st.subheader("📊 Scenariusze liczbowe")
    st.plotly_chart(plot_scenarios_plotly(scen, price, sl, tp), use_container_width=True)

    st.subheader("🚨 AI-alerty techniczne")
    st.markdown(ai_alerts_pl(ticker, last, prev, tr, horizon))

    st.subheader("📰 News summary (Tavily)")
    news_summary = fetch_news_summary(ticker, horizon)
    st.text(news_summary)

    st.subheader("🤖 AI-komentarz i scenariusze")
    st.markdown(ai_analysis_pl(ticker, tr, price, atr, sl, tp, scen, news_summary, horizon))
