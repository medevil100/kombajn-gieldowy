import json
import traceback

import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


# ---------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------

st.set_page_config(
    page_title="AI",
    page_icon="📈",
    layout="wide"
)


# ---------------------------------------------------------
# POMOCNICZE FUNKCJE
# ---------------------------------------------------------

def clean_for_json(data):
    return json.loads(json.dumps(data, default=str))


def convert_keys_to_str(d):
    if isinstance(d, dict):
        return {str(k): convert_keys_to_str(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_keys_to_str(i) for i in d]
    else:
        return d


def normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().upper()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / (avg_loss.replace(0, pd.NA))
    rsi = 100 - (100 / (1 + rs))

    return rsi


@st.cache_data(ttl=300, show_spinner=False)
def fetch_prices(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    ticker = normalize_ticker(ticker)
    if not ticker:
        return pd.DataFrame()

    # Ograniczenia Yahoo dla intraday
    if interval == "1m" and period not in ["1d", "5d", "7d"]:
        period = "7d"
    if interval in ["2m", "5m", "15m", "30m", "60m", "90m", "1h"] and period in ["1y", "2y", "5y", "10y", "max"]:
        period = "60d"

    try:
        df = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if df is None or df.empty:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval, auto_adjust=False)

        if df is None or df.empty:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        df = df.dropna(how="all")
        return df

    except Exception:
        return pd.DataFrame()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["RSI14"] = calculate_rsi(df["Close"], 14)

    return df


def make_price_chart(df: pd.DataFrame, ticker: str):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=(f"Wykres ceny: {ticker}", "RSI")
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Cena"
        ),
        row=1,
        col=1
    )

    for col in ["SMA20", "SMA50", "SMA200"]:
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[col],
                    name=col,
                    line=dict(width=1)
                ),
                row=1,
                col=1
            )

    if "RSI14" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["RSI14"],
                name="RSI14",
                line=dict(width=1)
            ),
            row=2,
            col=1
        )
        fig.add_hline(y=70, line_dash="dash", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", row=2, col=1)

    fig.update_layout(
        height=750,
        xaxis_rangeslider_visible=False,
        template="plotly_dark"  # ciemne wykresy, jasny UI Streamlit
    )

    return fig


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yfinance_fundamentals(ticker: str) -> dict:
    ticker = normalize_ticker(ticker)

    results = {
        "profile": None,
        "metrics": None,
        "price_target": None,
        "income": None,
        "balance": None,
        "cash": None,
        "_errors": []
    }

    if not ticker:
        results["_errors"].append("Brak tickera.")
        return results

    try:
        stock = yf.Ticker(ticker)

        try:
            info = stock.info
            if not isinstance(info, dict):
                info = {}
        except Exception as e:
            info = {}
            results["_errors"].append(f"info: {e}")

        results["profile"] = {
            "symbol": ticker,
            "longName": info.get("longName"),
            "shortName": info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "website": info.get("website"),
            "longBusinessSummary": info.get("longBusinessSummary"),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "quoteType": info.get("quoteType"),
        }

        results["metrics"] = {
            "symbol": ticker,
            "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
            "marketCap": info.get("marketCap"),
            "enterpriseValue": info.get("enterpriseValue"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "priceToBook": info.get("priceToBook"),
            "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months"),
            "profitMargins": info.get("profitMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "grossMargins": info.get("grossMargins"),
            "returnOnAssets": info.get("returnOnAssets"),
            "returnOnEquity": info.get("returnOnEquity"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "totalRevenue": info.get("totalRevenue"),
            "totalDebt": info.get("totalDebt"),
            "totalCash": info.get("totalCash"),
            "freeCashflow": info.get("freeCashflow"),
            "operatingCashflow": info.get("operatingCashflow"),
            "dividendYield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        }

        results["price_target"] = {
            "symbol": ticker,
            "targetHighPrice": info.get("targetHighPrice"),
            "targetLowPrice": info.get("targetLowPrice"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "targetMedianPrice": info.get("targetMedianPrice"),
            "recommendationMean": info.get("recommendationMean"),
            "recommendationKey": info.get("recommendationKey"),
            "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
        }

        try:
            income = stock.financials
            if income is not None and not income.empty:
                results["income"] = convert_keys_to_str(income.to_dict())
        except Exception as e:
            results["_errors"].append(f"income: {e}")

        try:
            balance = stock.balance_sheet
            if balance is not None and not balance.empty:
                results["balance"] = convert_keys_to_str(balance.to_dict())
        except Exception as e:
            results["_errors"].append(f"balance: {e}")

        try:
            cash = stock.cashflow
            if cash is not None and not cash.empty:
                results["cash"] = convert_keys_to_str(cash.to_dict())
        except Exception as e:
            results["_errors"].append(f"cash: {e}")

    except Exception as e:
        results["_errors"].append(f"general yfinance error: {e}")

    return results


@st.cache_data(ttl=900, show_spinner=False)
def fetch_yfinance_news(ticker: str):
    ticker = normalize_ticker(ticker)
    if not ticker:
        return []

    try:
        stock = yf.Ticker(ticker)
        news = stock.news or []
        cleaned = []

        for item in news[:10]:
            cleaned.append({
                "title": item.get("title"),
                "publisher": item.get("publisher"),
                "link": item.get("link"),
                "providerPublishTime": item.get("providerPublishTime"),
                "type": item.get("type"),
            })

        return cleaned
    except Exception:
        return []


def simple_signal(df: pd.DataFrame) -> dict:
    result = {
        "signal": "BRAK DANYCH",
        "comment": "",
        "last_close": None,
        "rsi": None,
        "sma20": None,
        "sma50": None,
    }

    if df is None or df.empty or "Close" not in df.columns:
        result["comment"] = "Brak danych cenowych."
        return result

    df = add_indicators(df)
    last = df.dropna(subset=["Close"]).iloc[-1]

    close = float(last["Close"])
    rsi = float(last["RSI14"]) if "RSI14" in last and not pd.isna(last["RSI14"]) else None
    sma20 = float(last["SMA20"]) if "SMA20" in last and not pd.isna(last["SMA20"]) else None
    sma50 = float(last["SMA50"]) if "SMA50" in last and not pd.isna(last["SMA50"]) else None

    result["last_close"] = close
    result["rsi"] = rsi
    result["sma20"] = sma20
    result["sma50"] = sma50

    score = 0
    comments = []

    if sma20 and close > sma20:
        score += 1
        comments.append("Cena powyżej SMA20.")
    elif sma20:
        score -= 1
        comments.append("Cena poniżej SMA20.")

    if sma50 and close > sma50:
        score += 1
        comments.append("Cena powyżej SMA50.")
    elif sma50:
        score -= 1
        comments.append("Cena poniżej SMA50.")

    if rsi is not None:
        if rsi < 30:
            score += 1
            comments.append("RSI wskazuje możliwe wyprzedanie.")
        elif rsi > 70:
            score -= 1
            comments.append("RSI wskazuje możliwe wykupienie.")
        else:
            comments.append("RSI neutralne.")

    if score >= 2:
        result["signal"] = "POZYTYWNY"
    elif score <= -2:
        result["signal"] = "NEGATYWNY"
    else:
        result["signal"] = "NEUTRALNY"

    result["comment"] = " ".join(comments)
    return result


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

st.sidebar.title("📈 Kombajn Giełdowy")

app_mode = st.sidebar.selectbox(
    "Wybierz moduł aplikacji:",
    [
        "🏠 Strona główna",
        "📈 Analiza techniczna",
        "📊 Fundamenty spółki",
        "📰 Wiadomości rynkowe",
    ]
)


# ---------------------------------------------------------
# STRONA GŁÓWNA
# ---------------------------------------------------------

if app_mode == "🏠 Strona główna":
    st.title("📈 Kombajn Giełdowy")

    st.write(
        """
        To jest czysta, lekka wersja aplikacji bez OpenBB.

        Źródła danych:
        • ceny: Yahoo Finance (yfinance)
        • fundamenty: Yahoo Finance
        • wiadomości: Yahoo Finance

        Przykłady tickerów:
        • USA: AAPL, MSFT, NVDA, TSLA
        • GPW: CDR.WA, PKO.WA, KGH.WA
        • krypto: BTC-USD, ETH-USD
        """
    )

    st.success("Aplikacja działa w trybie czystym, gotowa do analizy.")


# ---------------------------------------------------------
# ANALIZA TECHNICZNA
# ---------------------------------------------------------

elif app_mode == "📈 Analiza techniczna":
    st.title("📈 Analiza techniczna")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        ticker = st.text_input("Wpisz ticker:", "AAPL").upper().strip()

    with col_b:
        period_label = st.selectbox(
            "Zakres danych:",
            ["1 dzień", "5 dni", "7 dni", "1 miesiąc", "3 miesiące", "6 miesięcy", "1 rok", "2 lata", "5 lat", "maksymalnie"],
            index=6
        )
        period_map = {
            "1 dzień": "1d",
            "5 dni": "5d",
            "7 dni": "7d",
            "1 miesiąc": "1mo",
            "3 miesiące": "3mo",
            "6 miesięcy": "6mo",
            "1 rok": "1y",
            "2 lata": "2y",
            "5 lat": "5y",
            "maksymalnie": "max",
        }
        period = period_map[period_label]

    with col_c:
        interval_label = st.selectbox(
            "Interwał świec:",
            ["1 minuta", "5 minut", "15 minut", "30 minut", "1 godzina", "1 dzień", "1 tydzień", "1 miesiąc"],
            index=5
        )
        interval_map = {
            "1 minuta": "1m",
            "5 minut": "5m",
            "15 minut": "15m",
            "30 minut": "30m",
            "1 godzina": "1h",
            "1 dzień": "1d",
            "1 tydzień": "1wk",
            "1 miesiąc": "1mo",
        }
        interval = interval_map[interval_label]

    if st.button("Analizuj"):
        try:
            with st.spinner("Pobieranie danych i analiza..."):
                df = fetch_prices(ticker, period, interval)

            if df.empty:
                st.error(
                    "Brak danych z Yahoo Finance. Sprawdź ticker albo interwał.\n"
                    "Dla GPW używaj np. CDR.WA, PKO.WA, KGH.WA."
                )
            else:
                df_ind = add_indicators(df)
                signal = simple_signal(df_ind)

                st.subheader(f"Wynik analizy: {ticker}")

                c1, c2, c3 = st.columns(3)
                c1.metric("Sygnał", signal["signal"])
                c2.metric("Cena", signal["last_close"])
                c3.metric("RSI", round(signal["rsi"], 2) if signal["rsi"] is not None else "brak")

                st.info(signal["comment"])

                fig = make_price_chart(df_ind, ticker)
                st.plotly_chart(fig, use_container_width=True)

                with st.expander("Dane tabelaryczne (ostatnie 100 wierszy)"):
                    st.dataframe(df_ind.tail(100))

        except Exception:
            st.error("Analiza przerwana błędem.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())


# ---------------------------------------------------------
# FUNDAMENTY
# ---------------------------------------------------------

elif app_mode == "📊 Fundamenty spółki":
    st.title("📊 Fundamenty spółki (Yahoo Finance)")
elif app_mode == "📊 Fundamenty spółki":

    st.caption("Dla GPW używaj sufiksu .WA, np. CDR.WA, PKO.WA, KGH.WA.")

    ticker_f = st.text_input("Ticker do fundamentów:", "AAPL").upper().strip()

    if st.button("Pobierz fundamenty"):
        try:
            with st.spinner("Pobieranie fundamentów..."):
                fund_data = fetch_yfinance_fundamentals(ticker_f)

            errors = fund_data.get("_errors", [])
            if errors:
                with st.expander("Ostrzeżenia / log"):
                    for err in errors:
                        st.warning(str(err))

            metrics = fund_data.get("metrics") or {}
            profile = fund_data.get("profile") or {}

            st.subheader(profile.get("longName") or profile.get("shortName") or ticker_f)

            c1, c2, c3 = st.columns(3)
            c1.metric("Cena", metrics.get("currentPrice") or "brak")
            c2.metric("Kapitalizacja (Market Cap)", metrics.get("marketCap") or "brak")
            c3.metric("P/E (trailing)", metrics.get("trailingPE") or "brak")

            st.write("### Profil spółki")
            st.json(clean_for_json(profile))

            st.write("### Wskaźniki finansowe")
            st.json(clean_for_json(metrics))

            st.write("### Cele cenowe (Price Target)")
            st.json(clean_for_json(fund_data.get("price_target")))

            with st.expander("Rachunek zysków i strat"):
                st.json(clean_for_json(fund_data.get("income")))

            with st.expander("Bilans"):
                st.json(clean_for_json(fund_data.get("balance")))

            with st.expander("Przepływy pieniężne"):
                st.json(clean_for_json(fund_data.get("cash")))

        except Exception:
            st.error("Nie udało się pobrać fundamentów.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())


# ---------------------------------------------------------
# WIADOMOŚCI
# ---------------------------------------------------------

elif app_mode == "📰 Wiadomości rynkowe":
    st.title("📰 Wiadomości rynkowe (Yahoo Finance)")

    ticker_n = st.text_input("Ticker do wyszukania wiadomości:", "AAPL").upper().strip()

    if st.button("Pobierz najnowsze wiadomości"):
        try:
            with st.spinner("Pobieranie newsów..."):
                news = fetch_yfinance_news(ticker_n)

            if not news:
                st.info("Brak newsów z Yahoo Finance dla tego tickera.")
            else:
                for item in news:
                    title = item.get("title") or "Bez tytułu"
                    publisher = item.get("publisher") or "Nieznane źródło"
                    link = item.get("link")

                    st.write(f"### {title}")
                    st.caption(f"Źródło: {publisher}")

                    if link:
                        st.write(link)

                    st.divider()

        except Exception:
            st.error("Nie udało się pobrać newsów.")
            with st.expander("Szczegóły błędu"):
                st.code(traceback.format_exc())
