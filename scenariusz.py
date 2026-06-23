import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from openai import OpenAI
from tavily import TavilyClient  # upewnij się, że nazwa paczki się zgadza

# --- KLUCZE ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None

# --- PARAMETRY SWING/LONG ---
ATR_WINDOW = 20
SMA_FAST = 50
SMA_SLOW = 200
K_SL = 1.8
K_TP = 3.5


# ================== DANE I WSKAŹNIKI ==================

def load_data(ticker):
    df = yf.download(ticker, period="2y", interval="1d", auto_adjust=True)
    return df


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

    scen = pd.DataFrame({"Bull": bull, "Hold": base, "Bear": bear}, index=days)
    return scen


# ================== NEWSY (TAVILY) ==================

def fetch_news_summary(ticker: str, horizon_days: int = 30) -> str:
    if tavily_client is None:
        return "Brak klucza Tavily – nie mogę pobrać newsów."

    query = f"Najważniejsze wiadomości i wydarzenia dotyczące spółki {ticker} z ostatnich {horizon_days} dni."
    res = tavily_client.search(query=query, max_results=5)

    # Proste sklejenie tytułów + opisów
    items = res.get("results", []) if isinstance(res, dict) else res
    if not items:
        return "Brak istotnych newsów w wynikach Tavily."

    lines = []
    for item in items:
        title = item.get("title", "")
        snippet = item.get("content", "")[:300]
        lines.append(f"- {title}: {snippet}")

    return "\n".join(lines)


# ================== AI – KOMENTARZ, SCENARIUSZE, SENTYMENT ==================

def ai_analysis_pl(ticker: str,
                   trend: str,
                   price: float,
                   atr: float,
                   sl: float,
                   tp: float,
                   scen_df: pd.DataFrame,
                   news_summary: str,
                   horizon_days: int = 30) -> str:
    if client is None:
        return "Brak klucza OpenAI – nie mogę wygenerować komentarza AI."

    # Zbuduj krótki kontekst liczbowy
    scen_last = scen_df.iloc[-1]
    bull_target = scen_last["Bull"]
    base_target = scen_last["Hold"]
    bear_target = scen_last["Bear"]

    prompt = f"""
Jesteś analitykiem rynkowym piszącym po polsku, zwięźle i konkretnie.

Dane wejściowe:
- Ticker: {ticker}
- Aktualna cena: {price:.2f}
- Trend techniczny (na bazie SMA50/200): {trend}
- ATR({ATR_WINDOW}): {atr:.2f}
- Poziom SL: {sl:.2f}
- Poziom TP: {tp:.2f}
- Horyzont analizy: {horizon_days} dni (około 1 miesiąc)

Scenariusze liczbowo (na koniec horyzontu):
- Bull (optymistyczny): {bull_target:.2f}
- Bazowy (neutralny): {base_target:.2f}
- Bear (pesymistyczny): {bear_target:.2f}

News summary (ostatnie wydarzenia, streszczenie):
{news_summary}

Zadania:
1. Oceń ogólny SENTYMENT dla tego tickera na najbliższy miesiąc (pojedyncze słowo: "byczy", "neutralny" lub "niedźwiedzi").
2. Napisz krótki AI-komentarz rynkowy (2–3 akapity, max ~300 słów).
3. Opisz 3 scenariusze na najbliższy miesiąc:
   - Scenariusz byczy (Bull case)
   - Scenariusz bazowy (Base case)
   - Scenariusz niedźwiedzi (Bear case)
   W każdym scenariuszu uwzględnij:
   - orientacyjny poziom ceny (na bazie podanych wartości),
   - główne czynniki ryzyka / szanse,
   - ogólną narrację (co musiałoby się wydarzyć).

Forma odpowiedzi:
- Najpierw linia: "Sentyment: ...".
- Potem sekcja "Komentarz AI:".
- Potem sekcja "Scenariusze na najbliższy miesiąc:" z trzema podpunktami.
- Pisz po polsku, bez żargonu algorytmicznego, ale konkretnie.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Jesteś doświadczonym analitykiem rynkowym piszącym po polsku."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4,
        max_tokens=900,
    )

    return response.choices[0].message.content.strip()


# ================== STREAMLIT UI ==================

st.title("📈 Swing & Long-Term AI Scenario Tool (PL)")

ticker = st.text_input("Ticker:", "AAPL").upper()
side = st.selectbox("Strona pozycji:", ["long", "short"])
horizon = st.slider("Horyzont scenariuszy (dni):", 20, 60, 30)

if st.button("Analizuj"):
    if not ticker:
        st.warning("Podaj ticker.")
    else:
        with st.spinner("Pobieram dane i liczę wskaźniki..."):
            df = load_data(ticker)
            if df.empty:
                st.error("Brak danych dla tego tickera.")
            else:
                df = indicators(df)
                last = df.iloc[-1]

                price = last["Close"]
                atr = last[f"ATR{ATR_WINDOW}"]
                tr = detect_trend(last)
                sl, tp = sl_tp(price, atr, side)
                scen = scenarios_numeric(price, df, horizon_days=horizon)

        st.subheader("📌 Wyniki liczbowe")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Trend:** {tr}")
            st.write(f"**Cena:** {round(price, 2)}")
            st.write(f"**ATR({ATR_WINDOW}):** {round(atr, 2)}")
        with col2:
            st.write(f"**Strona:** {side}")
            st.write(f"**SL:** {round(sl, 2)}")
            st.write(f"**TP:** {round(tp, 2)}")

        st.subheader("📊 Scenariusze Bull / Hold / Bear (liczbowe)")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(scen.index, scen["Bull"], label="Bull", color="green")
        ax.plot(scen.index, scen["Hold"], label="Hold", color="blue")
        ax.plot(scen.index, scen["Bear"], label="Bear", color="red")
        ax.axhline(price, color="gray", linestyle="--", label="Aktualna cena")
        ax.axhline(sl, color="orange", linestyle="--", label="SL")
        ax.axhline(tp, color="purple", linestyle="--", label="TP")
        ax.set_xlabel("Dni")
        ax.set_ylabel("Cena")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

        # --- NEWSY + AI ---
        st.subheader("📰 AI-analiza newsów + komentarz rynkowy")

        with st.spinner("Pobieram newsy (Tavily) i generuję komentarz AI..."):
            news_summary = fetch_news_summary(ticker, horizon_days=horizon)
            st.markdown("**Streszczenie newsów (Tavily):**")
            st.text(news_summary)

            ai_text = ai_analysis_pl(
                ticker=ticker,
                trend=tr,
                price=price,
                atr=atr,
                sl=sl,
                tp=tp,
                scen_df=scen,
                news_summary=news_summary,
                horizon_days=horizon
            )

        st.markdown("---")
        st.markdown("### 🤖 AI-komentarz i scenariusze (PL)")
        st.markdown(ai_text)
