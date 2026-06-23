import os
import json
import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from openai import OpenAI
from tavily import TavilyClient


# =========================================================
# 1. KONFIGURACJA STRONY
# =========================================================

st.set_page_config(
    page_title="AI Monte Carlo Advanced Predictor",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 Zaawansowany Predyktor Monte Carlo 52 tygodnie & Deep AI Analyst")


# =========================================================
# 2. KLUCZE API
# =========================================================

def get_key(name: str) -> str | None:
    """
    Bezpieczne pobieranie klucza:
    1. Streamlit Secrets
    2. Zmienne środowiskowe
    """
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass

    return os.getenv(name)


OPENAI_KEY = get_key("OPENAI_API_KEY")
TAVILY_KEY = get_key("TAVILY_API_KEY")

openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
tavily_client = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None


# =========================================================
# 3. PARAMETRY
# =========================================================

DNI_HANDLOWE_ROK = 252
MIN_LICZBA_DANYCH = 80


# =========================================================
# 4. FUNKCJE POMOCNICZE
# =========================================================

def fmt_money(value, currency: str = "USD") -> str:
    try:
        value = float(value)
        if np.isnan(value):
            return "brak"
        return f"{value:,.2f} {currency}".replace(",", " ")
    except Exception:
        return "brak"


def fmt_pct(value) -> str:
    try:
        value = float(value)
        if np.isnan(value):
            return "brak"
        return f"{value * 100:.2f}%"
    except Exception:
        return "brak"


def clean_text(text: str, limit: int = 1200) -> str:
    if text is None:
        return ""

    text = str(text)
    for ch in ["{", "}", "[", "]"]:
        text = text.replace(ch, "")

    return text[:limit]


# =========================================================
# 5. POBIERANIE DANYCH Z YAHOO FINANCE
# =========================================================

@st.cache_data(show_spinner=False, ttl=1800)
def load_price_history(ticker: str, years: int = 3) -> pd.DataFrame:
    """
    Pobiera historię cen z Yahoo Finance.
    Zwraca DataFrame z kolumnami m.in. Close, High, Low, Open, Volume.
    """

    end = dt.date.today() + dt.timedelta(days=1)
    start = dt.date.today() - dt.timedelta(days=365 * years + 10)

    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=False
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # Obsługa MultiIndex z yfinance
    if isinstance(df.columns, pd.MultiIndex):
        # Najczęściej level 0 = Open/High/Low/Close/Volume
        if "Close" in df.columns.get_level_values(0):
            df.columns = df.columns.get_level_values(0)
        else:
            df.columns = df.columns.get_level_values(-1)

    # Ujednolicenie nazw
    df.columns = [str(c).strip().capitalize() for c in df.columns]

    if "Close" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["Close"])

    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_fundamentals(ticker: str, last_price: float) -> dict:
    """
    Pobiera podstawowe dane fundamentalne.
    Część danych Yahoo Finance może być niestabilna, dlatego wszystko jest zabezpieczone.
    """

    result = {
        "currency": "USD",
        "shares_outstanding": None,
        "net_income_ttm": None,
        "eps_ttm": None,
        "pe_ttm": None,
        "target_mean_price": None,
        "target_text": "Brak danych",
        "eps_text": "Brak stabilnych danych",
        "pe_text": "Brak stabilnych danych",
    }

    ticker_obj = yf.Ticker(ticker)

    # Info
    info = {}
    try:
        info = ticker_obj.info or {}
    except Exception:
        info = {}

    try:
        currency = info.get("currency")
        if currency:
            result["currency"] = str(currency)
    except Exception:
        pass

    try:
        shares = info.get("sharesOutstanding")
        if shares and float(shares) > 0:
            result["shares_outstanding"] = float(shares)
    except Exception:
        pass

    try:
        target = info.get("targetMeanPrice")
        if target is not None and float(target) > 0:
            result["target_mean_price"] = float(target)
            result["target_text"] = f"{float(target):.2f} {result['currency']}"
    except Exception:
        pass

    # Net Income TTM z kwartalnego income statement
    try:
        income_stmt = ticker_obj.quarterly_income_stmt

        if income_stmt is not None and not income_stmt.empty:
            net_income_series = None

            if "Net Income" in income_stmt.index:
                net_income_series = income_stmt.loc["Net Income"]
            else:
                mask = income_stmt.index.astype(str).str.contains("Net Income", case=False, na=False)
                matches = income_stmt.loc[mask]
                if not matches.empty:
                    net_income_series = matches.iloc[0]

            if net_income_series is not None:
                vals = pd.to_numeric(net_income_series, errors="coerce").dropna()

                if len(vals) >= 4:
                    net_income_ttm = float(vals.iloc[:4].sum())
                    result["net_income_ttm"] = net_income_ttm

    except Exception:
        pass

    # Awaryjna próba znalezienia liczby akcji w bilansie
    if result["shares_outstanding"] is None:
        try:
            balance_sheet = ticker_obj.quarterly_balance_sheet

            if balance_sheet is not None and not balance_sheet.empty:
                if "Ordinary Shares Number" in balance_sheet.index:
                    shares_series = balance_sheet.loc["Ordinary Shares Number"]
                    vals = pd.to_numeric(shares_series, errors="coerce").dropna()

                    if not vals.empty and float(vals.iloc[0]) > 0:
                        result["shares_outstanding"] = float(vals.iloc[0])
        except Exception:
            pass

    # EPS i P/E
    try:
        net_income = result["net_income_ttm"]
        shares = result["shares_outstanding"]

        if net_income is not None and shares is not None and shares > 0:
            eps = net_income / shares
            result["eps_ttm"] = eps
            result["eps_text"] = f"{eps:.2f} {result['currency']}"

            if eps > 0:
                pe = last_price / eps
                result["pe_ttm"] = pe
                result["pe_text"] = f"{pe:.2f}"
            else:
                result["pe_text"] = "Ujemny EPS / P/E niemiarodajne"

    except Exception:
        pass

    return result


# =========================================================
# 6. TAVILY NEWS
# =========================================================

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_news_tavily(ticker: str, company_query: str = "") -> str:
    if tavily_client is None:
        return "Brak klucza Tavily — newsy nie zostały pobrane."

    current_year = dt.date.today().year

    query = (
        f"{ticker} stock financial catalysts earnings revenue margins AI products risks "
        f"supply chain competition outlook {current_year}"
    )

    if company_query:
        query += f" {company_query}"

    try:
        response = tavily_client.search(
            query=query,
            max_results=6,
            search_depth="advanced"
        )

        results = response.get("results", [])

        if not results:
            return "Brak istotnych newsów."

        lines = []

        for i, item in enumerate(results, start=1):
            title = clean_text(item.get("title", ""), 250)
            content = clean_text(item.get("content", ""), 700)
            url = clean_text(item.get("url", ""), 300)

            lines.append(
                f"Artykuł {i}: {title}\n"
                f"Treść: {content}\n"
                f"Źródło: {url}"
            )

        return "\n\n".join(lines)

    except Exception as e:
        return f"Brak możliwości pobrania newsów: {e}"


# =========================================================
# 7. MONTE CARLO
# =========================================================

def run_monte_carlo(
    close_prices: pd.Series,
    liczba_symulacji: int,
    dni_prognozy: int,
    target_mean_price: float | None = None
) -> dict:
    """
    Symulacja Monte Carlo oparta o logarytmiczne zwroty dzienne.
    Zwraca ścieżki percentylowe: 10%, 50%, 90%.
    """

    close_prices = close_prices.dropna()

    if len(close_prices) < MIN_LICZBA_DANYCH:
        raise ValueError("Za mało danych historycznych do wykonania Monte Carlo.")

    last_price = float(close_prices.iloc[-1])

    log_returns = np.log(close_prices / close_prices.shift(1)).dropna()

    if log_returns.empty or len(log_returns) < 30:
        raise ValueError("Za mało dziennych zwrotów do wykonania Monte Carlo.")

    mu_hist = float(log_returns.mean())
    sigma_hist = float(log_returns.std())

    if np.isnan(mu_hist):
        mu_hist = 0.0

    if np.isnan(sigma_hist) or sigma_hist <= 0:
        raise ValueError("Nieprawidłowa zmienność historyczna.")

    # Dryf z target price analityków
    analyst_daily_mu = None

    if target_mean_price is not None:
        try:
            target_mean_price = float(target_mean_price)

            if target_mean_price > 0 and last_price > 0:
                analyst_daily_mu = np.log(target_mean_price / last_price) / DNI_HANDLOWE_ROK
        except Exception:
            analyst_daily_mu = None

    if analyst_daily_mu is not None and not np.isnan(analyst_daily_mu):
        expected_mu = (mu_hist + analyst_daily_mu) / 2
    else:
        expected_mu = mu_hist

    rng = np.random.default_rng()

    # Dzienny log-return: N(expected_mu, sigma)
    random_log_returns = rng.normal(
        loc=expected_mu,
        scale=sigma_hist,
        size=(dni_prognozy, liczba_symulacji)
    )

    daily_growth = np.exp(random_log_returns)

    paths_without_initial = last_price * np.cumprod(daily_growth, axis=0)

    initial_row = np.full((1, liczba_symulacji), last_price)
    price_paths = np.vstack([initial_row, paths_without_initial])

    scenario_bear = np.percentile(price_paths, 10, axis=1)
    scenario_hold = np.percentile(price_paths, 50, axis=1)
    scenario_bull = np.percentile(price_paths, 90, axis=1)

    final_prices = price_paths[-1, :]

    probability_above_current = float(np.mean(final_prices > last_price))
    probability_above_target = None

    if target_mean_price is not None and target_mean_price > 0:
        probability_above_target = float(np.mean(final_prices > target_mean_price))

    return {
        "last_price": last_price,
        "mu_hist": mu_hist,
        "sigma_hist": sigma_hist,
        "expected_mu": expected_mu,
        "price_paths": price_paths,
        "bear": scenario_bear,
        "hold": scenario_hold,
        "bull": scenario_bull,
        "final_prices": final_prices,
        "probability_above_current": probability_above_current,
        "probability_above_target": probability_above_target,
    }


# =========================================================
# 8. WYKRES
# =========================================================

def build_chart(
    ticker: str,
    close_prices: pd.Series,
    bear: np.ndarray,
    hold: np.ndarray,
    bull: np.ndarray,
    currency: str
) -> go.Figure:

    hist = close_prices.dropna().tail(120).values
    x_hist = np.arange(-len(hist) + 1, 1)
    x_future = np.arange(0, len(bear))

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=x_hist,
            y=hist,
            mode="lines",
            name="Historia — ostatnie 120 sesji",
            line=dict(color="black", width=2)
        )
    )

    # Wypełnienie zakresu Bear-Bull
    fig.add_trace(
        go.Scatter(
            x=x_future,
            y=bull,
            mode="lines",
            name="BULL 90%",
            line=dict(color="green", width=2.5)
        )
    )

    fig.add_trace(
        go.Scatter(
            x=x_future,
            y=bear,
            mode="lines",
            name="BEAR 10%",
            line=dict(color="red", width=2.5),
            fill="tonexty",
            fillcolor="rgba(0, 180, 0, 0.08)"
        )
    )

    fig.add_trace(
        go.Scatter(
            x=x_future,
            y=hold,
            mode="lines",
            name="HOLD 50% / mediana",
            line=dict(color="blue", width=2.2, dash="dash")
        )
    )

    fig.add_vline(
        x=0,
        line_width=1.5,
        line_dash="dot",
        line_color="purple"
    )

    fig.update_layout(
        title=f"Monte Carlo — prognoza 52 tygodnie dla {ticker}",
        xaxis_title="Dni giełdowe, 0 = dzisiaj",
        yaxis_title=f"Cena akcji ({currency})",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )

    return fig


# =========================================================
# 9. RAPORT AI
# =========================================================

def generate_ai_report(dane_rynkowe: dict) -> str:
    if openai_client is None:
        return "Brak klucza OpenAI — raport AI nie został wygenerowany."

    system_prompt = (
        "Jesteś profesjonalnym analitykiem rynku akcji. "
        "Piszesz po polsku, konkretnie i bez lania wody. "
        "Twoim zadaniem jest przygotować raport inwestycyjny na podstawie dostarczonych danych. "
        "Nie udawaj pewności, jeśli dane są niepełne. "
        "Wyraźnie rozdziel fakty, model statystyczny i interpretację. "
        "Nie dawaj gwarancji zysków. "
        "Dodaj krótkie zastrzeżenie, że to nie jest rekomendacja inwestycyjna."
    )

    user_prompt = f"""
Otrzymujesz dane rynkowe w formacie JSON:

{json.dumps(dane_rynkowe, ensure_ascii=False, indent=2)}

Przygotuj profesjonalny raport po polsku.

Struktura raportu:

1. WERDYKT
- Jeden z wariantów: byczy / neutralny / niedźwiedzi.
- Krótkie uzasadnienie w 3–5 zdaniach.

2. OBRAZ TECHNICZNO-STATYSTYCZNY
- Omów wyniki Monte Carlo.
- Odnieś się do scenariuszy BEAR, HOLD i BULL.
- Oceń prawdopodobieństwo zamknięcia roku powyżej obecnej ceny.

3. FUNDAMENTY
- Oceń EPS TTM i P/E, jeśli dane są dostępne.
- Jeżeli P/E jest niedostępne albo EPS jest ujemny, jasno to wyjaśnij.
- Odnieś się do ceny docelowej analityków, jeśli jest dostępna.

4. SENTYMENT I NEWSY
- Wypunktuj najważniejsze czynniki z newsów.
- Oddziel katalizatory pozytywne od ryzyk.

5. SCENARIUSZ BEAR
- Podaj orientacyjny poziom cenowy z modelu.
- Wskaż konkretne ryzyka biznesowe, rynkowe lub wynikowe.

6. SCENARIUSZ BASE / HOLD
- Podaj orientacyjny poziom cenowy z modelu.
- Opisz realistyczną narrację bazową.

7. SCENARIUSZ BULL
- Podaj orientacyjny poziom cenowy z modelu.
- Wskaż konkretne katalizatory wzrostowe.

8. PODSUMOWANIE
- Krótka konkluzja.
- Najważniejsze poziomy do obserwacji.
- Zastrzeżenie: to nie jest rekomendacja inwestycyjna.

Pisz konkretnie. Unikaj pustych zdań typu „spółka stoi przed wyzwaniami”.
"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.35,
            max_tokens=1800
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Błąd generowania raportu AI: {e}"


# =========================================================
# 10. SIDEBAR
# =========================================================

st.sidebar.header("⚙️ Parametry analizy")

ticker = st.sidebar.text_input(
    "Ticker spółki",
    value="AAPL",
    help="Przykłady: AAPL, MSFT, TSLA, NVDA, AMZN"
).upper().strip()

liczba_symulacji = st.sidebar.slider(
    "Liczba symulacji Monte Carlo",
    min_value=1000,
    max_value=10000,
    value=5000,
    step=1000
)

dni_prognozy = st.sidebar.slider(
    "Horyzont prognozy — dni giełdowe",
    min_value=60,
    max_value=252,
    value=252,
    step=21
)

company_query = st.sidebar.text_input(
    "Dodatkowe hasła do newsów, opcjonalnie",
    value=""
)

generuj = st.sidebar.button("🚀 Uruchom głęboką analizę")


# =========================================================
# 11. GŁÓWNA LOGIKA APLIKACJI
# =========================================================

if not OPENAI_KEY:
    st.warning("⚠️ Brak OPENAI_API_KEY — część AI nie będzie działać.")

if not TAVILY_KEY:
    st.warning("⚠️ Brak TAVILY_API_KEY — newsy Tavily nie będą pobierane.")

st.info(
    "Aplikacja wykonuje symulację Monte Carlo na podstawie historycznej zmienności "
    "oraz generuje raport AI na bazie danych rynkowych, fundamentalnych i newsów."
)

if generuj:
    if not ticker:
        st.error("Podaj ticker.")
        st.stop()

    # -----------------------------------------------------
    # Pobieranie danych cenowych
    # -----------------------------------------------------
    with st.spinner("Pobieranie danych cenowych z Yahoo Finance..."):
        dane = load_price_history(ticker, years=3)

    if dane.empty:
        st.error(f"❌ Nie udało się pobrać poprawnych danych cenowych dla tickera: {ticker}")
        st.stop()

    if "Close" not in dane.columns:
        st.error("❌ Brak kolumny Close w danych z Yahoo Finance.")
        st.write("Dostępne kolumny:", dane.columns.tolist())
        st.stop()

    ceny_zamkniecia = dane["Close"].dropna()

    if len(ceny_zamkniecia) < MIN_LICZBA_DANYCH:
        st.error("❌ Za mało danych historycznych do wykonania analizy.")
        st.stop()

    ostatnia_cena = float(ceny_zamkniecia.iloc[-1])

    # -----------------------------------------------------
    # Dane fundamentalne
    # -----------------------------------------------------
    with st.spinner("Pobieranie danych fundamentalnych..."):
        fundamentals = load_fundamentals(ticker, ostatnia_cena)

    currency = fundamentals.get("currency", "USD")
    target_mean_price = fundamentals.get("target_mean_price")

    # -----------------------------------------------------
    # Monte Carlo
    # -----------------------------------------------------
    with st.spinner("Uruchamianie symulacji Monte Carlo..."):
        try:
            mc = run_monte_carlo(
                close_prices=ceny_zamkniecia,
                liczba_symulacji=liczba_symulacji,
                dni_prognozy=dni_prognozy,
                target_mean_price=target_mean_price
            )
        except Exception as e:
            st.error(f"❌ Błąd Monte Carlo: {e}")
            st.stop()

    bear = mc["bear"]
    hold = mc["hold"]
    bull = mc["bull"]

    final_bear = float(bear[-1])
    final_hold = float(hold[-1])
    final_bull = float(bull[-1])

    prob_above_current = mc["probability_above_current"]
    prob_above_target = mc["probability_above_target"]

    # -----------------------------------------------------
    # Metryki
    # -----------------------------------------------------
    st.subheader("📌 Podsumowanie liczbowe")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Aktualna cena",
        fmt_money(ostatnia_cena, currency)
    )

    col2.metric(
        "BEAR 10%",
        fmt_money(final_bear, currency),
        delta=f"{((final_bear / ostatnia_cena) - 1) * 100:.1f}%"
    )

    col3.metric(
        "HOLD 50%",
        fmt_money(final_hold, currency),
        delta=f"{((final_hold / ostatnia_cena) - 1) * 100:.1f}%"
    )

    col4.metric(
        "BULL 90%",
        fmt_money(final_bull, currency),
        delta=f"{((final_bull / ostatnia_cena) - 1) * 100:.1f}%"
    )

    col5, col6, col7, col8 = st.columns(4)

    col5.metric(
        "Prawdopodobieństwo > obecna cena",
        fmt_pct(prob_above_current)
    )

    col6.metric(
        "Zmienność dzienna",
        fmt_pct(mc["sigma_hist"])
    )

    col7.metric(
        "Target analityków",
        fundamentals.get("target_text", "Brak danych")
    )

    if prob_above_target is not None:
        col8.metric(
            "Prawdopodobieństwo > target",
            fmt_pct(prob_above_target)
        )
    else:
        col8.metric(
            "Prawdopodobieństwo > target",
            "brak"
        )

    # -----------------------------------------------------
    # Dane fundamentalne
    # -----------------------------------------------------
    st.subheader("🏦 Dane fundamentalne")

    fundamental_table = pd.DataFrame(
        {
            "Wskaźnik": [
                "Ticker",
                "Waluta",
                "Cena bieżąca",
                "EPS TTM",
                "P/E TTM",
                "Target mean price",
                "Liczba akcji",
                "Net Income TTM"
            ],
            "Wartość": [
                ticker,
                currency,
                fmt_money(ostatnia_cena, currency),
                fundamentals.get("eps_text", "Brak danych"),
                fundamentals.get("pe_text", "Brak danych"),
                fundamentals.get("target_text", "Brak danych"),
                f"{fundamentals['shares_outstanding']:,.0f}".replace(",", " ") if fundamentals.get("shares_outstanding") else "Brak danych",
                fmt_money(fundamentals["net_income_ttm"], currency) if fundamentals.get("net_income_ttm") else "Brak danych"
            ]
        }
    )

    st.dataframe(fundamental_table, use_container_width=True, hide_index=True)

    # -----------------------------------------------------
    # Tabela scenariuszy
    # -----------------------------------------------------
    st.subheader("📊 Scenariusze Monte Carlo")

    scenario_table = pd.DataFrame(
        {
            "Scenariusz": ["BEAR 10%", "HOLD 50%", "BULL 90%"],
            "Cena końcowa": [
                fmt_money(final_bear, currency),
                fmt_money(final_hold, currency),
                fmt_money(final_bull, currency)
            ],
            "Zmiana vs obecna cena": [
                f"{((final_bear / ostatnia_cena) - 1) * 100:.2f}%",
                f"{((final_hold / ostatnia_cena) - 1) * 100:.2f}%",
                f"{((final_bull / ostatnia_cena) - 1) * 100:.2f}%"
            ]
        }
    )

    st.dataframe(scenario_table, use_container_width=True, hide_index=True)

    # -----------------------------------------------------
    # Wykres
    # -----------------------------------------------------
    st.subheader("📈 Wykres prognozy")

    fig = build_chart(
        ticker=ticker,
        close_prices=ceny_zamkniecia,
        bear=bear,
        hold=hold,
        bull=bull,
        currency=currency
    )

    st.plotly_chart(fig, use_container_width=True)

    # -----------------------------------------------------
    # Newsy
    # -----------------------------------------------------
    st.subheader("📰 News summary — Tavily")

    with st.spinner("Pobieranie newsów i katalizatorów z Tavily..."):
        newsy = fetch_news_tavily(ticker, company_query)

    with st.expander("Pokaż pobrane newsy"):
        st.text(newsy)

    # -----------------------------------------------------
    # Dane dla AI
    # -----------------------------------------------------
    dane_rynkowe = {
        "ticker": ticker,
        "waluta": currency,
        "aktualna_cena": fmt_money(ostatnia_cena, currency),
        "horyzont_prognozy_dni_gieldowe": dni_prognozy,
        "liczba_symulacji_monte_carlo": liczba_symulacji,
        "monte_carlo": {
            "bear_10_percent": fmt_money(final_bear, currency),
            "hold_50_percent_mediana": fmt_money(final_hold, currency),
            "bull_90_percent": fmt_money(final_bull, currency),
            "probability_final_price_above_current": fmt_pct(prob_above_current),
            "probability_final_price_above_target": fmt_pct(prob_above_target) if prob_above_target is not None else "brak",
            "historyczna_srednia_dzienna_log_return": fmt_pct(mc["mu_hist"]),
            "oczekiwany_dzienny_log_return_modelu": fmt_pct(mc["expected_mu"]),
            "historyczna_zmiennosc_dzienna": fmt_pct(mc["sigma_hist"]),
        },
        "fundamenty": {
            "eps_ttm": fundamentals.get("eps_text"),
            "pe_ttm": fundamentals.get("pe_text"),
            "target_mean_price": fundamentals.get("target_text"),
            "shares_outstanding": fundamentals.get("shares_outstanding"),
            "net_income_ttm": fundamentals.get("net_income_ttm"),
        },
        "newsy_tavily": newsy,
    }

    # -----------------------------------------------------
    # Raport AI
    # -----------------------------------------------------
    st.subheader("🔬 Profesjonalna analiza fundamentalno-sentymentowa AI")

    with st.spinner("Generowanie raportu AI..."):
        raport = generate_ai_report(dane_rynkowe)

    st.markdown(raport)

    st.caption(
        "Uwaga: model Monte Carlo jest modelem statystycznym opartym na danych historycznych. "
        "Nie przewiduje przyszłości i nie stanowi rekomendacji inwestycyjnej."
    )
