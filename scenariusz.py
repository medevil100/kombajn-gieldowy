import datetime
import os
import numpy as np
import openai
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import cloudscraper
from tavily import TavilyClient

# ==========================================
# 0. ROZWIĄZANIE PROBLEMU Z BLOKADĄ IP (Yahoo Rate Limit)
# ==========================================
scraper_session = cloudscraper.create_scraper()
scraper_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3'
})

# ==========================================
# 1. KONFIGURACJA STRONY I AUTOMATYCZNYCH KLUCZY
# ==========================================
st.set_page_config(
    page_title="AI Monte Carlo Predictor", layout="wide", initial_sidebar_state="expanded"
)
st.title("📈 AI Monte Carlo 52-Week Predictor & News Analyst")

# Samoczynne pobieranie kluczy ze środowiska Streamlit Cloud
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))
TAVILY_KEY = st.secrets.get("TAVILY_API_KEY", os.environ.get("TAVILY_API_KEY"))

# Przypisanie klucza OpenAI
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

# Panel boczny
ticker = st.sidebar.text_input(
    "Wpisz Ticker Spółki (np. AAPL, TSLA, MSFT)", "AAPL"
).upper()
liczba_symulacji = st.sidebar.slider(
    "Liczba symulacji Monte Carlo", 1000, 10000, 5000, step=1000
)
generuj = st.sidebar.button("Uruchom analizę")


# Funkcja do przeszukiwania sieci przez bezpośredniego klienta Tavily
def pobierz_newsy_tavily(query):
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        wyniki = tavily.search(query=query, max_results=4)
        
        tekst_newsow = ""
        for i, res in enumerate(wyniki.get('results', [])):
            tekst_newsow += f"\n[{i+1}] {res['title']}: {res['content']}\nURL: {res['url']}\n"
        return tekst_newsow
    except Exception as e:
        return f"Brak możliwości pobrania newsów. Sprawdź klucz Tavily. Błąd: {e}"


# ==========================================
# 2. LOGIKA MATEMATYCZNA (MONTE CARLO)
# ==========================================
if generuj:
    if not OPENAI_KEY or not TAVILY_KEY:
        st.error(
            "❌ Błąd: Nie wykryto kluczy OPENAI_API_KEY lub TAVILY_API_KEY w panelu Streamlit Secrets."
        )
        st.stop()

    with st.spinner("Pobieranie danych rynkowych i obliczanie Monte Carlo..."):
        koniec = datetime.date.today()
        start = koniec - datetime.timedelta(days=3 * 365)
        
        spolka = yf.Ticker(ticker, session=scraper_session)
        
        try:
            dane = spolka.history(start=start, end=koniec)
        except Exception as e:
            st.error("❌ Yahoo Finance odrzuciło zapytanie z powodu limitu serwera Streamlit. Spróbuj kliknąć ponownie za chwilę.")
            st.stop()

        if dane.empty:
            st.error(f"Nie znaleziono danych dla tickera lub Yahoo zablokowało ruch: {ticker}. Spróbuj ponownie.")
            st.stop()

        # BEZPIECZNE PROSTOWANIE KOLUMN (Na wypadek struktur MultiIndex w nowych wersjach yfinance)
        if isinstance(dane.columns, pd.MultiIndex):
            dane.columns = dane.columns.get_level_values(0)

        # Wyciągnięcie cen zamknięcia
        ceny_zamkniecia = dane["Close"].dropna()
        ostatnia_cena = float(ceny_zamkniecia.iloc[-1])
        dni_handlowe = 52 * 5  # 52 tygodnie prognozy

        try:
            target_mean = spolka.info.get("targetMeanPrice")
        except:
            target_mean = None

        if target_mean and target_mean > 0:
            dzienny_zwrot_analitykow = ((target_mean - ostatnia_cena) / ostatnia_cena) / 252
        else:
            dzienny_zwrot_analitykow = None

        # Statystyka historyczna
        zwroty_hist = ceny_zamkniecia.pct_change().dropna()
        sredni_zwrot_hist = zwroty_hist.mean()
        zmiennosc_hist = zwroty_hist.std()

        oczekiwany_dryf = (
            (sredni_zwrot_hist + dzienny_zwrot_analitykow) / 2
            if dzienny_zwrot_analitykow
            else sredni_zwrot_hist
        )
        v = oczekiwany_dryf - (0.5 * zmiennosc_hist**2)

        # Generowanie losowych ścieżek cenowych
        losowe_szoki = np.random.normal(0, zmiennosc_hist, (dni_handlowe, liczba_symulacji))
        codzienne_zwroty = np.exp(v + losowe_szoki)

        # POPRAWNA INICJALIZACJA MACIERZY (Naprawa błędu IndexError)
        macierz_cen = np.zeros((dni_handlowe + 1, liczba_symulacji))
        macierz_cen[0, :] = ostatnia_cena  # Wypełnienie wyłącznie pierwszego wiersza wartością początkową
        
        for t in range(1, dni_handlowe + 1):
            macierz_cen[t, :] = macierz_cen[t - 1, :] * codzienne_zwroty[t - 1, :]

        # Wyciąganie percentyli
        scenariusz_bear = np.percentile(macierz_cen, 10, axis=1)
        scenariusz_hold = np.percentile(macierz_cen, 50, axis=1)
        scenariusz_bull = np.percentile(macierz_cen, 90, axis=1)

    # ==========================================
    # 3. INTERFEJS I INTERAKTYWNY WYKRES PLOTLY
    # ==========================================
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Aktualna Cena", f"{ostatnia_cena:.2f} USD")
    col2.metric("BEAR (10. pct)", f"{scenariusz_bear[-1]:.2f} USD")
    col3.metric("HOLD (50. pct)", f"{scenariusz_hold[-1]:.2f} USD")
    col4.metric("BULL (90. pct)", f"{scenariusz_bull[-1]:.2f} USD")

    # Przygotowanie osi czasu dla wykresu
    ceny_hist = ceny_zamkniecia.tail(100).values
    os_historii = np.arange(-len(ceny_hist) + 1, 1)
    os_prognozy = np.arange(0, dni_handlowe + 1)

    # Tworzenie wykresu Plotly
    fig = go.Figure()

    # Linia historii
    fig.add_trace(
        go.Scatter(
            x=os_historii,
            y=ceny_hist,
            mode="lines",
            name="Historia (100 dni)",
            line=dict(color="black", width=2),
        )
    )

    # Linia BULL
    fig.add_trace(
        go.Scatter(
            x=os_prognozy,
            y=scenariusz_bull,
            mode="lines",
            name=f"BULL (90%): {scenariusz_bull[-1]:.2f} USD",
            line=dict(color="green", width=2),
        )
    )

    # Linia HOLD
    fig.add_trace(
        go.Scatter(
            x=os_prognozy,
            y=scenariusz_hold,
            mode="lines",
            name=f"HOLD (50%): {scenariusz_hold[-1]:.2f} USD",
            line=dict(color="blue", width=2, dash="dash"),
        )
    )

    # Linia BEAR
    fig.add_trace(
        go.Scatter(
            x=os_prognozy,
            y=scenariusz_bear,
            mode="lines",
            name=f"BEAR (10%): {scenariusz_bear[-1]:.2f} USD",
            line=dict(color="red", width=2),
        )
    )

    # Stylizacja wykresu Plotly
    fig.update_layout(
        title=f"Interaktywna prognoza 52 tygodnie dla {ticker}",
        xaxis_title="Dni giełdowe (0 = Dzisiaj)",
        yaxis_title="Cena akcji (USD)",
        template="plotly_white",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        hovermode="x unified",
    )

    fig.add_vline(x=0, line_width=1.5, line_dash="dot", line_color="purple")
    st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # 4. GENEROWANIE RAPORTU PRZEZ AI
    # ==========================================
    st.subheader("🤖 Analiza Fundamentalna i Sentymentu przez AI")
    with st.spinner("Przeszukiwanie internetu za pomocą Tavily i analiza GPT-4o..."):
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
