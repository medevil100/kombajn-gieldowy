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
#   CACHE – DANE I WSKAŹNIKI
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def load_data(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period="2y", interval="1d", auto_adjust=True)

    if df.empty:
        return df

    # Spłaszcz MultiIndex, jeśli występuje
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    return df


@st.cache_data(show_spinner=False, ttl=3600)
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "Close" not in df.columns or "High" not in df.columns or "Low" not in df.columns:
        return pd.DataFrame()

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
    except Exception:
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


@st.cache_data(show_spinner=False, ttl=3600)
def scenarios_numeric(price: float, df: pd.DataFrame, horizon_days: int = 30) -> pd.DataFrame:
    returns = np.log(df["Close"] / df["Close"].shift(1)).dropna()
    if returns.empty:
        days = np.arange(1, horizon_days + 1)
        return pd.DataFrame(
            {"Bull": price, "Hold": price, "Bear": price},
            index=days
        )

    mu = returns.mean()
    sigma = returns.std()

    days = np.arange(1, horizon_days + 1)

    bull = np.exp(np.log(price) + (mu + sigma) * days)
    base = np.exp(np.log(price) + mu * days)
    bear = np.exp(np.log(price) + (mu - sigma) * days)

    return pd.DataFrame({"Bull": bull, "Hold": base, "Bear": bear}, index=days)


# ============================
#   NEWSY TAVILY (cache)
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
    except Exception:
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
#   AI – KOMENTARZ / SCENARIUSZE / SENTYMENT (cache)
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def ai_analysis_pl(
    ticker: str,
    trend: str,
    price: float,
    atr: float,
    sl: float,
    tp: float,
    scen_df: pd.DataFrame,
    news_summary: str,
    horizon_days: int
) -> str:
    if client is None:
        return "Brak klucza OpenAI."

    scen_last = scen_df.iloc[-1]
    bull_target = scen_last["Bull"]
    base_target = scen_last["Hold"]
    bear_target = scen_last["Bear"]

    prompt = f"""
Jesteś analitykiem rynkowym piszącym po polsku.

Dane:
- Ticker: {ticker}
- Cena: {price:.2f}
- Trend: {trend}
- ATR({ATR_WINDOW}): {atr:.2f}
- SL: {sl:.2f}
- TP: {tp:.2f}
- Horyzont: {horizon_days} dni

Scenariusze liczbowe:
- Bull: {bull_target:.2f}
- Bazowy: {base_target:.2f}
- Bear: {bear_target:.2f}

News summary:
{news_summary}

Zadania:
1. Podaj SENTYMENT (jedno słowo: byczy / neutralny / niedźwiedzi).
2. Napisz krótki komentarz rynkowy (2–3 akapity).
3. Opisz 3 scenariusze na najbliższy miesiąc:
   - Bull case
   - Base case
   - Bear case
   Każdy z orientacyjną ceną, ryzykami i narracją.

Pisz po polsku, konkretnie.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Jesteś analitykiem rynkowym."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=900
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Błąd generowania odpowiedzi AI."


# ============================
#   AI – ALERTY (zmiana trendu, SMA, zmienność) – D
# ============================

@st.cache_data(show_spinner=False, ttl=3600)
def ai_alerts_pl(
    ticker: str,
    last_row: pd.Series,
    prev_row: pd.Series | None,
    trend: str,
    horizon_days: int
) -> str:
    if client is None:
        return "Brak klucza OpenAI."

    try:
        price = float(last_row.get("Close", np.nan))
        sma_fast = float(last_row.get(f"SMA{SMA_FAST}", np.nan))
        sma_slow = float(last_row.get(f"SMA{SMA_SLOW}", np.nan))
        atr = float(last_row.get(f"ATR{ATR_WINDOW}", np.nan))
    except Exception:
        price = np.nan
        sma_fast = np.nan
        sma_slow = np.nan
        atr = np.nan

    prev_trend = "Unknown"
    prev_price = np.nan
    prev_sma_fast = np.nan
    prev_sma_slow = np.nan

    if prev_row is not None:
        try:
            prev_price = float(prev_row.get("Close", np.nan))
            prev_sma_fast = float(prev_row.get(f"SMA{SMA_FAST}", np.nan))
            prev_sma_slow = float(prev_row.get(f"SMA{SMA_SLOW}", np.nan))
            prev_trend = detect_trend(prev_row)
        except Exception:
            prev_trend = "Unknown"

    prompt = f"""
Jesteś systemem alertów rynkowych piszącym po polsku.

Dane bieżące:
- Ticker: {ticker}
- Cena: {price:.2f}
- SMA{SMA_FAST}: {sma_fast:.2f}
- SMA{SMA_SLOW}: {sma_slow:.2f}
- ATR({ATR_WINDOW}): {atr:.2f}
- Trend bieżący: {trend}

Dane poprzednie (poprzednia sesja):
- Cena poprzednia: {prev_price:.2f}
- SMA{SMA_FAST} poprzednie: {prev_sma_fast:.2f}
- SMA{SMA_SLOW} poprzednie: {prev_sma_slow:.2f}
- Trend poprzedni: {prev_trend}

Zadanie:
1. Wykryj potencjalne ALERTY techniczne na najbliższy okres (ok. {horizon_days} dni), np.:
   - zmiana trendu (Bull/Neutral/Bear),
   - wybicie powyżej/poniżej SMA50/SMA200,
   - wzrost/spadek zmienności (ATR),
   - nietypowy ruch ceny.
2. Zwróć listę krótkich alertów w formie wypunktowanej (max 5 punktów).
3. Każdy alert ma być konkretny, po polsku, bez żargonu algorytmicznego.

Jeśli nie ma istotnych alertów, napisz: "- Brak istotnych alertów technicznych."
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Jesteś systemem alertów rynkowych."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "- Błąd generowania alertów AI."


# ============================
#   WYKRES PLOTLY
# ============================

def plot_scenarios_plotly(scen: pd.DataFrame, price: float, sl: float, tp: float):
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=scen.index, y=scen["Bull"], mode="lines",
                             name="Bull", line=dict(color="green")))
    fig.add_trace(go.Scatter(x=scen.index, y=scen["Hold"], mode="lines",
                             name="Bazowy", line=dict(color="blue")))
    fig.add_trace(go.Scatter(x=scen.index, y=scen["Bear"], mode="lines",
                             name="Bear", line=dict(color="red")))

    fig.add_hline(y=price, line_dash="dash", line_color="gray", annotation_text="Cena")
    fig.add_hline(y=sl, line_dash="dash", line_color="orange", annotation_text="SL")
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

st.title("📈 AI Scenariusze Rynkowe – Wersja PRO + AI Alerty (PL)")

ticker = st.text_input("Ticker:", "AAPL").upper()
side = st.selectbox("Strona pozycji:", ["long", "short"])
horizon = st.slider("Horyzont (dni):", 20, 60, 30)

if st.button("Analizuj"):
    df = load_data(ticker)

    if df.empty:
        st.error("Brak danych dla tego tickera.")
        st.stop()

    if "Close" not in df.columns:
        st.error("Brak kolumny 'Close' w danych z Yahoo Finance.")
        st.stop()

    if len(df) < SMA_SLOW + 5:
        st.error("Za mało danych, aby policzyć SMA200 i scenariusze.")
        st.stop()

    df = compute_indicators(df)
    if df.empty:
        st.error("Błąd wyliczania wskaźników.")
        st.stop()

    # Bezpieczne pobranie ostatniego i poprzedniego wiersza
    try:
        last_two = df.tail(2).reset_index(drop=True)
        last = last_two.iloc[-1]
        prev = last_two.iloc[-2] if len(last_two) == 2 else None
    except Exception:
        st.error("Błąd pobierania ostatnich danych.")
        st.stop()

    try:
        price = float(last["Close"])
    except Exception:
        st.error("Błąd: wartość Close nie jest liczbą.")
        st.stop()

    try:
        atr = float(last.get(f"ATR{ATR_WINDOW}", np.nan))
    except Exception:
        atr = np.nan

    tr = detect_trend(last)
    sl, tp = sl_tp(price, atr, side)
    scen = scenarios_numeric(price, df, horizon)

    st.subheader("📌 Dane techniczne")
    st.write(f"**Trend:** {tr}")
    st.write(f"**Cena:** {round(price, 2)}")
    st.write(f"**ATR({ATR_WINDOW}):** {round(atr, 2) if not np.isnan(atr) else 'brak'}")
    st.write(f"**SL:** {round(sl, 2) if not np.isnan(sl) else 'brak'}")
    st.write(f"**TP:** {round(tp, 2) if not np.isnan(tp) else 'brak'}")

    st.subheader("📊 Scenariusze liczbowe")
    fig = plot_scenarios_plotly(scen, price, sl, tp)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🚨 AI-alerty techniczne")
    alerts_text = ai_alerts_pl(ticker, last, prev, tr, horizon)
    st.markdown(alerts_text)

    st.subheader("📰 News summary (Tavily)")
    news_summary = fetch_news_summary(ticker, horizon)
    st.text(news_summary)

    st.subheader("🤖 AI-komentarz i scenariusze")
    ai_text = ai_analysis_pl(
        ticker, tr, price, atr, sl, tp, scen, news_summary, horizon
    )
    st.markdown(ai_text)
