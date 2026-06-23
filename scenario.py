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
#   POMOCNICZE FORMATOWANIE
# ============================

def fmt_num(x, digits=2):
    try:
        x = float(x)
        if np.isnan(x):
            return "brak"
        return f"{x:.{digits}f}"
    except Exception:
        return "brak"


# ============================
#   POBIERANIE DANYCH Z YAHOO
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
        if ticker.upper() in df.columns.get_level_values(-1):
            df = df.xs(ticker.upper(), axis=1, level=-1)
        else:
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


# ============================
#   SCENARIUSZE LICZBOWE
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
#   AI – KOMENTARZ / SCENARIUSZE
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
- Bull: {scen_last['Bull']:.2f}
- Bazowy: {scen_last['Hold']:.2f}
- Bear: {scen_last['Bear']:.2f}

News summary:
{news_summary}

Zadania:
1. Podaj sentyment (byczy / neutralny / niedźwiedzi).
2. Napisz krótki komentarz rynkowy (2–3 akapity).
3. Opisz 3 scenariusze (Bull, Base, Bear) z orientacyjnymi poziomami cen i ryzykami.
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Jesteś analitykiem rynkowym."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=900
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd generowania odpowiedzi AI: {e}"


# ============================
#   AI – ALERTY TECHNICZNE
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

    price = fmt_num(last_row.get("Close", np.nan))
    sma_fast = fmt_num(last_row.get(f"SMA{SMA_FAST}", np.nan))
    sma_slow = fmt_num(last_row.get(f"SMA{SMA_SLOW}", np.nan))
    atr = fmt_num(last_row.get(f"ATR{ATR_WINDOW}", np.nan))

    if prev_row is not None:
        prev_price = fmt_num(prev_row.get("Close", np.nan))
        prev_sma_fast = fmt_num(prev_row.get(f"SMA{SMA_FAST}", np.nan))
        prev_sma_slow = fmt_num(prev_row.get(f"SMA{SMA_SLOW}", np.nan))
        prev_trend = detect_trend(prev_row)
    else:
        prev_price = "brak"
        prev_sma_fast = "brak"
        prev_sma_slow = "brak"
        prev_trend = "Unknown"

    prompt = f"""
Jesteś systemem alertów rynkowych piszącym po polsku.

Dane bieżące:
- Ticker: {ticker}
- Cena: {price}
- SMA{SMA_FAST}: {sma_fast}
- SMA{SMA_SLOW}: {sma_slow}
- ATR({ATR_WINDOW}): {atr}
- Trend bieżący: {trend}

Dane poprzednie, poprzednia sesja:
- Cena poprzednia: {prev_price}
- SMA{SMA_FAST} poprzednie: {prev_sma_fast}
- SMA{SMA_SLOW} poprzednie: {prev_sma_slow}
- Trend poprzedni: {prev_trend}

Zadanie:
1. Wykryj potencjalne ALERTY techniczne na najbliższy okres, około {horizon_days} dni:
   - zmiana trendu,
   - wybicia powyżej/poniżej SMA50/SMA200,
   - wzrost/spadek zmienności ATR,
   - nietypowy ruch ceny.
2. Zwróć listę krótkich alertów (max 5 punktów), po polsku.
3. Jeśli nie ma alertów, napisz:
- Brak istotnych alertów technicznych.
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
    except Exception as e:
        return f"- Błąd generowania alertów AI: {e}"


# ============================
#   WYKRES PLOTLY
# ============================

def plot_scenarios_plotly(scen: pd.DataFrame, price: float, sl: float, tp: float):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=scen.index,
        y=scen["Bull"],
        mode="lines",
        name="Bull",
        line=dict(color="green")
    ))

    fig.add_trace(go.Scatter(
        x=scen.index,
        y=scen["Hold"],
        mode="lines",
        name="Bazowy",
        line=dict(color="blue")
    ))

    fig.add_trace(go.Scatter(
        x=scen.index,
        y=scen["Bear"],
        mode="lines",
        name="Bear",
        line=dict(color="red")
    ))

    if not np.isnan(price):
        fig.add_hline(
            y=price,
            line_dash="dash",
            line_color="gray",
            annotation_text="Cena"
        )

    if not np.isnan(sl):
        fig.add_hline(
            y=sl,
            line_dash="dash",
            line_color="orange",
            annotation_text="SL"
        )

    if not np.isnan(tp):
        fig.add_hline(
            y=tp,
            line_dash="dash",
            line_color="purple",
            annotation_text="TP"
        )

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

st.title("📈 AI Scenariusze Rynkowe – Wersja PRO + AI Alerty")

ticker = st.text_input("Ticker:", "AAPL").upper()
side = st.selectbox("Strona pozycji:", ["long", "short"])
horizon = st.slider("Horyzont (dni):", 20, 60, 30)

if st.button("Analizuj"):
    df = safe_load_yahoo(ticker)

    if df is None:
        st.error("Yahoo Finance nie zwrócił poprawnych danych dla tego tickera.")
        st.stop()

    if len(df) < SMA_SLOW + 5:
        st.error("Za mało danych, aby policzyć SMA200 i scenariusze.")
        st.stop()

    df = compute_indicators(df)

    last_two = df.tail(2).reset_index(drop=True)
    last = last_two.iloc[-1]
    prev = last_two.iloc[-2] if len(last_two) == 2 else None

    price = float(last["Close"])
    atr_val = float(last.get(f"ATR{ATR_WINDOW}", np.nan))

    tr = detect_trend(last)
    sl, tp = sl_tp(price, atr_val, side)
    scen = scenarios_numeric(price, df, horizon)

    st.subheader("📌 Dane techniczne")
    st.write(f"**Trend:** {tr}")
    st.write(f"**Cena:** {fmt_num(price)}")
    st.write(f"**ATR({ATR_WINDOW}):** {fmt_num(atr_val)}")
    st.write(f"**SL:** {fmt_num(sl)}")
    st.write(f"**TP:** {fmt_num(tp)}")

    st.subheader("📊 Scenariusze liczbowe")
    st.plotly_chart(plot_scenarios_plotly(scen, price, sl, tp), use_container_width=True)

    st.subheader("🚨 AI-alerty techniczne")
    st.markdown(ai_alerts_pl(ticker, last, prev, tr, horizon))

    st.subheader("📰 News summary (Tavily)")
    news_summary = fetch_news_summary(ticker, horizon)
    st.text(news_summary)

    st.subheader("🤖 AI-komentarz i scenariusze")
    st.markdown(ai_analysis_pl(ticker, tr, price, atr_val, sl, tp, scen, news_summary, horizon))
