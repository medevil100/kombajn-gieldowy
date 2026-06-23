import datetime
import os
import matplotlib.pyplot as plt
import numpy as np
import openai
import streamlit as st
import yfinance as yf
from langchain_community.utilities import TavilySearchAPIWrapper

# ==========================================
# 1. KONFIGURACJA STRONY I AUTOMATYCZNYCH KLUCZY
# ==========================================
st.set_page_config(page_title="AI Monte Carlo Predictor", layout="wide")
st.title("📈 AI Monte Carlo 52-Week Predictor & News Analyst")

# Samoczynne pobieranie kluczy (najpierw szuka w Streamlit Cloud Secrets, potem w systemie)
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))
TAVILY_KEY = st.secrets.get("TAVILY_API_KEY", os.environ.get("TAVILY_API_KEY"))

# Przypisanie kluczy do bibliotek
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY
if TAVILY_KEY:
    os.environ["TAVILY_API_KEY"] = TAVILY_KEY

# Panel boczny sterowania (bez pól na klucze)
ticker = st.sidebar.text_input(
    "Wpisz Ticker Spółki (np. AAPL, TSLA)", "AAPL"
).upper()
liczba_symulacji = st.sidebar.slider(
    "Liczba symulacji Monte Carlo", 1000, 10000, 5000, step=1000
)
generuj = st.sidebar.button("Uruchom analizę")


# Funkcja do przeszukiwania sieci przez Tavily
def pobierz_newsy_tavily(query):
    try:
        search = TavilySearchAPIWrapper()
        wyniki = search.results(query, max_results=4)
        tekst_newsow = ""
        for i, res in enumerate(wyniki):
            tekst_newsow += f"\n[{i+1}] {res['title']}: {res['snippet']}\nURL: {res['url']}\n"
        return tekst_newsow
    except Exception as e:
        return f"Brak możliwości pobrania newsów. Sprawdź klucz Tavily. Błąd: {e}"


# ==========================================
# 2. LOGIKA MATEMATYCZNA (MONTE CARLO)
# ==========================================
if generuj:
    # Weryfikacja obecności kluczy w tle
    if not OPENAI_KEY or not TAVILY_KEY:
        st.error(
            "❌ Błąd: Nie wykryto kluczy OpenAI lub Tavily w systemie. Aplikacja nie może ruszyć."
        )
        st.stop()

    with st.spinner("Pobieranie danych rynkowych i obliczanie Monte Carlo..."):
        koniec = datetime.date.today()
        start = koniec - datetime.timedelta(days=3 * 365)
        spolka = yf.Ticker(ticker)
        dane = spolka.history(start=start, end=koniec)

        if dane.empty:
            st.error(f"Nie znaleziono danych dla tickera: {ticker}")
            st.stop()

        ostatnia_cena = dane["Close"].iloc[-1]
        dni_handlowe = 52 * 5  # 52 tygodnie prognozy

        try:
            target_mean = spolka.info.get("targetMeanPrice")
        except:
            target_mean = None

        if target_mean and target_mean > 0:
            dzienny_zwrot_analitykow = (
                (target_mean - ostatnia_cena) / ostatnia_cena
            ) / 252
        else:
            dzienny_zwrot_analitykow = None

        # Statystyka i dryf geometrycznego ruchu Browna
        zwroty_hist = dane["Close"].pct_change().dropna()
        sredni_zwrot_hist = zwroty_hist.mean()
        zmiennosc_hist = zwroty_hist.std()

        oczekiwany_dryf = (
            (sredni_zwrot_hist + dzienny_zwrot_analitykow) / 2
            if dzienny_zwrot_analitykow
            else sredni_zwrot_hist
        )
        v = oczekiwany_dryf - (0.5 * zmiennosc_hist**2)

        # Generowanie losowych ścieżek cenowych
        losowe_szoki = np.random.normal(
            0, zmiennosc_hist, (dni_handlowe, liczba_symulacji)
        )
        codzienne_zwroty = np.exp(v + losowe_szoki)

        macierz_cen = np.zeros((dni_handlowe + 1, liczba_symulacji))
        macierz_cen = ostatnia_cena
        for t in range(1, dni_handlowe + 1):
            macierz_cen[t] = macierz_cen[t - 1] * codzienne_zwroty[t - 1]

        # Wyciąganie percentyli (Scenariusze 90%, 50%, 10%)
        scenariusz_bear = np.percentile(macierz_cen, 10, axis=1)
        scenariusz_hold = np.percentile(macierz_cen, 50, axis=1)
        scenariusz_bull = np.percentile(macierz_cen, 90, axis=1)

    # ==========================================
    # 3. INTERFEJS I WYKRES
    # ==========================================
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Aktualna Cena", f"{ostatnia_cena:.2f} USD")
    col2.metric("BEAR (10%)", f"{scenariusz_bear[-1]:.2f} USD")
    col3.metric("HOLD (50%)", f"{scenariusz_hold[-1]:.2f} USD")
    col4.metric("BULL (90%)", f"{scenariusz_bull[-1]:.2f} USD")

    fig, ax = plt.subplots(figsize=(12, 5))
    ceny_hist = dane["Close"].tail(100).values
    os_historii = np.arange(-len(ceny_hist) + 1, 1)

    ax.plot(os_historii, ceny_hist, label="Historia (100 dni)", color="black")
    os_prognozy = np.arange(0, dni_handlowe + 1)
    ax.plot(
        os_prognozy,
        scenariusz_bull,
        label=f"BULL: {scenariusz_bull[-1]:.2f} USD",
        color="green",
    )
    ax.plot(
        os_prognozy,
        scenariusz_hold,
        label=f"HOLD: {scenariusz_hold[-1]:.2f} USD",
        color="blue",
        linestyle="--",
    )
    ax.plot(
        os_prognozy,
        scenariusz_bear,
        label=f"BEAR: {scenariusz_bear[-1]:.2f} USD",
        color="red",
    )
    ax.fill_between(
        os_prognozy,
        scenariusz_bear,
        scenariusz_bull,
        color="gray",
        alpha=0.15,
        label="Obszar 80% prawdopodobieństwa",
    )
    ax.set_title(f"Prognoza 52 tygodnie dla {ticker}")
    ax.set_xlabel("Dni giełdowe")
    ax.set_ylabel("Cena (USD)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    st.pyplot(fig)

    # ==========================================
    # 4. GENEROWANIE RAPORTU PRZEZ AI
    # ==========================================
    st.subheader("🤖 Analiza Fundamentalna i Sentymentu przez AI")
    with st.spinner("Przeszukiwanie internetu i generowanie analizy..."):
        newsy = pobierz_newsy_tavily(
            f"latest stock market news financial health catalysts {ticker}"
        )

        prompt_ai = f"""
        Jesteś starszym analitykiem finansowym z Wall Street. 
        Przeanalizuj spółkę o tickerze: {ticker}.
        Aktualna cena na rynku: {ostatnia_cena:.2f} USD.
        Model statystyczny Monte Carlo na 52 tygodnie wygenerował poziomy:
        - Scenariusz optymistyczny Bull (90%): {scenariusz_bull[-1]:.2f} USD
        - Scenariusz neutralny Hold (50%): {scenariusz_hold[-1]:.2f} USD
        - Scenariusz pesymistyczny Bear (10%): {scenariusz_bear[-1]:.2f} USD
        
        Oto najnowsze wiadomości z internetu pobrane dla tej spółki:
        {newsy}
        
        Napisz krótki, konkretny komentarz giełdowy (w języku polskim). 
        Uzasadnij na podstawie newsów, co może zepchnąć kurs do poziomu BEAR, a co da paliwo do poziomu BULL. 
        Odpowiedź sformatuj w krótkie, czytelne punkty.
        """

        client = openai.OpenAI(api_key=OPENAI_KEY)
        odpowiedz = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Jesteś ekspertem giełdowym."},
                {"role": "user", "content": prompt_ai},
            ],
            temperature=0.7,
        )

        st.write(odpowiedz.choices.message.content)
