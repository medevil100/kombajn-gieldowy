import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
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
#   FUNKCJE TECHNICZNE
# ============================

def load_data(ticker):
    return yf.download(ticker, period="2y", interval="1d", auto_adjust=True)


def indicators(df):
    df = df.copy()
    df[f"SMA{SMA_FAST}"] = df["Close"].rolling(SMA_FAST).mean()
    df[f"SMA{SMA_SLOW}"] = df["Close"].rolling(SMA_SLOW).mean()

    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift(1)).abs()
    lc = (df["Low"] - df["Close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df[f"ATR{ATR_WINDOW}"] = tr.rolling(ATR_WINDOW).mean()

    return df


def detect_trend(row):
    sma_fast = row[f"SMA{SMA_FAST}"]
    sma_slow = row[f"SMA{SMA_SLOW}"]
    price = row["Close"]

    if sma_fast > sma_slow and price > sma_fast:
        return "Bull"
    elif sma_fast < sma_slow and price < sma_fast:
        return "Bear"
    return "Neutral"


def sl_tp(price, atr, side="long"):
    if side == "long":
        return price - K_SL * atr, price + K_TP * atr
    else:
        return price + K_SL * atr, price - K_TP * atr


def scenarios_numeric(price, df, horizon_days=30):
    returns = np.log(df["Close"] / df["Close"].shift(1)).dropna()
    mu = returns.mean()
    sigma = returns.std()

    days = np.arange(1, horizon_days + 1)

    bull = np.exp(np.log(price) + (mu + sigma) * days)
    base = np.exp(np.log(price) + mu * days)
    bear = np.exp(np.log(price) + (mu - sigma) * days)

    return pd.DataFrame({"Bull": bull, "Hold": base, "Bear": bear}, index=days)


# ============================
#   NEWSY TAVILY
# ============================

def fetch_news_summary(ticker, horizon_days=30):
    if tavily_client is None:
        return "Brak klucza Tavily."

    query = f"Najważniejsze wiadomości dotyczące spółki {ticker} z ostatnich {horizon_days} dni."
    res = tavily_client.search(query=query, max_results=5)

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
#   AI – KOMENTARZ / SCENARIUSZE / SENTYMENT
# ============================

def ai_analysis_pl(ticker, trend, price, atr, sl, tp, scen_df, news_summary, horizon_days):
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


# ============================
#   WYKRES PLOTLY
# ============================

def plot_scenarios_plotly(scen, price, sl, tp):
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

st.title("📈 AI Scenariusze Rynkowe – 1 Ticker (PL)")

ticker = st.text_input("Ticker:", "AAPL").upper()
side = st.selectbox("Strona pozycji:", ["long", "short"])
horizon = st.slider("Horyzont (dni):", 20, 60, 30)

if st.button("Analizuj"):
    df = load_data(ticker)
    if df.empty:
        st.error("Brak danych.")
        st.stop()

    df = indicators(df)
    last = df.iloc[-1]

    price = last["Close"]
    atr = last[f"ATR{ATR_WINDOW}"]
    tr = detect_trend(last)
    sl, tp = sl_tp(price, atr, side)
    scen = scenarios_numeric(price, df, horizon)

    st.subheader("📌 Dane techniczne")
    st.write(f"**Trend:** {tr}")
    st.write(f"**Cena:** {round(price, 2)}")
    st.write(f"**ATR:** {round(atr, 2)}")
    st.write(f"**SL:** {round(sl, 2)}")
    st.write(f"**TP:** {round(tp, 2)}")

    st.subheader("📊 Scenariusze liczbowe")
    fig = plot_scenarios_plotly(scen, price, sl, tp)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📰 News summary (Tavily)")
    news_summary = fetch_news_summary(ticker, horizon)
    st.text(news_summary)

    st.subheader("🤖 AI-komentarz i scenariusze")
    ai_text = ai_analysis_pl(
        ticker, tr, price, atr, sl, tp, scen, news_summary, horizon
    )
    st.markdown(ai_text)
