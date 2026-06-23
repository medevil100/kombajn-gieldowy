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
# 0. BEZPIECZNA SESJA ODPORNA NA LIMITOWANIE
# ==========================================
scraper_session = cloudscraper.create_scraper()
scraper_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3'
})

# ==========================================
# 1. KONFIGURACJA STRONY
# ==========================================
st.set_page_config(
    page_title="AI Monte Carlo Advanced Predictor", layout="wide", initial_sidebar_state="expanded"
)
st.title("📈 Zaawansowany Predyktor Monte Carlo 52-Tygodnie & Deep AI Analyst")

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))
TAVILY_KEY = st.secrets.get("TAVILY_API_KEY", os.environ.get("TAVILY_API_KEY"))

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

ticker = st.sidebar.text_input("Wpisz Ticker Spółki (np. AAPL, TSLA, MSFT)", "AAPL").upper()
liczba_symulacji = st.sidebar.slider("Liczba symulacji Monte Carlo", 1000, 10000, 5000, step=1000)
generuj = st.sidebar.button("Uruchom głęboką analizę")

def pobierz_newsy_tavily(query):
    try:
        tavily = TavilyClient(api_key=TAVILY_KEY)
        wyniki = tavily.search(query=query, max_results=5, search_depth="advanced")
        tekst_newsow = ""
        for i, res in enumerate(wyniki.get('results', [])):
            tekst_newsow += f"\n[{i+1}] {res['title']}\nTreść: {res['content']}\nŹródło: {res['url']}\n"
        return tekst_newsow
    except Exception as e:
        return f"Błąd Tavily: {e}"

# ==========================================
# 2. LOGIKA MATEMATYCZNA I OBLICZANIE WSKAŹNIKÓW
# ==========================================
if generuj:
    if not OPENAI_KEY or not TAVILY_KEY:
        st.error("❌ Brak kluczy API w konfiguracji Streamlit Secrets.")
        st.stop()

    with st.spinner("Pobieranie danych rynkowych i finansowych spółki..."):
        koniec = datetime.date.today()
        start = koniec - datetime.timedelta(days=3 * 365)
        
        spolka = yf.Ticker(ticker, session=scraper_session)
        
        try:
            dane = spolka.history(start=start, end=koniec)
        except Exception as e:
            st.error("❌ Problem z pobraniem historii cen z Yahoo Finance.")
            st.stop()

        if dane.empty:
            st.error(f"Brak danych dla {ticker}.")
            st.stop()

        if isinstance(dane.columns, pd.MultiIndex):
            dane.columns = dane.columns.get_level_values(0)

        ceny_zamkniecia = dane["Close"].dropna()
        ostatnia_cena = float(ceny_zamkniecia.iloc[-1])
        dni_handlowe = 252 # Dokładnie rok giełdowy

        # --- REWOLUCJA: SAMODZIELNE OBLICZANIE P/E ZAMIAST ZAUFANIA .INFO ---
        pe_obliczone = "Brak danych (Błąd raportu)"
        eps_ttm = "Brak danych"
        try:
            # Pobieramy kwartalne sprawozdanie zysków i strat
            kwartaly = spolka.quarterly_income_stmt
            if not kwartaly.empty:
                # Szukamy wiersza Net Income (Zysk netto) - bierzemy sumę z ostatnich 4 kwartałów (TTM)
                zysk_netto_ttm = kwartaly.loc['Net Income'].iloc[0:4].sum()
                
                # Pobieramy liczbę akcji w obiegu z bilansu
                bilans = spolka.quarterly_balance_sheet
                shares = None
                if 'Share Capital' in bilans.index:
                    shares = bilans.loc['Share Capital'].iloc[0]
                elif 'Ordinary Shares Number' in bilans.index:
                    shares = bilans.loc['Ordinary Shares Number'].iloc[0]
                
                if zysk_netto_ttm and shares and shares > 0:
                    eps_ttm = zysk_netto_ttm / shares
                    pe_calc_val = ostatnia_cena / eps_ttm
                    pe_obliczone = f"{pe_calc_val:.2f}"
                    eps_ttm = f"{eps_ttm:.2f} USD"
        except Exception as e:
            pass

        # Pobieranie ceny docelowej analityków (zostaje jako uzupełnienie)
        try:
            target_mean = spolka.info.get("targetMeanPrice")
        except:
            target_mean = None

        if target_mean and target_mean > 0:
            dzienny_zwrot_analitykow = ((target_mean - ostatnia_cena) / ostatnia_cena) / 252
        else:
            dzienny_zwrot_analitykow = None

        # Obliczenia Monte Carlo
        zwroty_hist = ceny_zamkniecia.pct_change().dropna()
        sredni_zwrot_hist = zwroty_hist.mean()
        zmiennosc_hist = zwroty_hist.std()

        oczekiwany_dryf = (sredni_zwrot_hist + dzienny_zwrot_analitykow) / 2 if dzienny_zwrot_analitykow else sredni_zwrot_hist
        v = oczekiwany_dryf - (0.5 * zmiennosc_hist**2)

        losowe_szoki = np.random.normal(0, zmiennosc_hist, (dni_handlowe, liczba_symulacji))
        codzienne_zwroty = np.exp(v + losowe_szoki)

        macierz_cen = np.zeros((dni_handlowe + 1, liczba_symulacji))
        macierz_cen[0, :] = ostatnia_cena
        for t in range(1, dni_handlowe + 1):
            macierz_cen[t, :] = macierz_cen[t - 1, :] * codzienne_zwroty[t - 1, :]

        scenariusz_bear = np.percentile(macierz_cen, 10, axis=1)
        scenariusz_hold = np.percentile(macierz_cen, 50, axis=1)
        scenariusz_bull = np.percentile(macierz_cen, 90, axis=1)

    # ==========================================
    # 3. INTERFEJS I INTERAKTYWNY WYKRES PLOTLY
    # ==========================================
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Aktualna Cena", f"{ostatnia_cena:.2f} USD")
    col2.metric("BEAR (10% pr.)", f"{scenariusz_bear[-1]:.2f} USD")
    col3.metric("HOLD (Mediana)", f"{scenariusz_hold[-1]:.2f} USD")
    col4.metric("BULL (90% pr.)", f"{scenariusz_bull[-1]:.2f} USD")

    ceny_hist = ceny_zamkniecia.tail(120).values
    os_historii = np.arange(-len(ceny_hist) + 1, 1)
    os_prognozy = np.arange(0, dni_handlowe + 1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=os_historii, y=ceny_hist, mode="lines", name="Historia (Ostatnie pół roku)", line=dict(color="black", width=2)))
    fig.add_trace(go.Scatter(x=os_prognozy, y=scenariusz_bull, mode="lines", name=f"BULL (90%): {scenariusz_bull[-1]:.2f} USD", line=dict(color="green", width=2.5)))
    fig.add_trace(go.Scatter(x=os_prognozy, y=scenariusz_hold, mode="lines", name=f"HOLD (50%): {scenariusz_hold[-1]:.2f} USD", line=dict(color="blue", width=2, dash="dash")))
    fig.add_trace(go.Scatter(x=os_prognozy, y=scenariusz_bear, mode="lines", name=f"BEAR (10%): {scenariusz_bear[-1]:.2f} USD", line=dict(color="red", width=2.5)))

    fig.update_layout(
        title=f"Zaawansowana prognoza 52 tygodnie dla {ticker}",
        xaxis_title="Dni giełdowe (0 = Dzisiaj)", yaxis_title="Cena akcji (USD)",
        template="plotly_white", hovermode="x unified"
    )
    fig.add_vline(x=0, line_width=1.5, line_dash="dot", line_color="purple")
    st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # 4. GŁĘBOKI RAPORT INWESTYCYJNY AI (OPENAI + TAVILY ADVANCED)
    # ==========================================
    st.subheader("🔬 Profesjonalna Analiza Fundamentalno-Sentymentowa AI")
    with st.spinner("Przeszukiwanie bazy Tavily (Deep Search) i generowanie zaawansowanego raportu..."):
        
        # Agresywnie ukierunkowane wyszukiwanie na najnowsze, konkretne wydarzenia
        newsy = pobierz_newsy_tavily(
            f"{ticker} stock financial catalysts earnings supply chain growth risks {datetime.date.today().year}"
        )

        prompt_ai = f"""
        Jesteś dyrektorem ds. analiz w funduszu hedgingowym na Wall Street. Napisz mięsisty, głęboki, profesjonalny i pozbawiony lania wody raport inwestycyjny dla spółki {ticker}.

        DANE FUNDAMENTALNE I RYNKOWE (OSTATNIE RAPORTY KWARTALNE):
        - Aktualna cena rynkowa: {ostatnia_cena:.2f} USD
        - Wyliczony wskaźnik P/E TTM: {pe_obliczone}
        - Wyliczony zysk na akcję EPS TTM: {eps_ttm}
        - Konsensus analityków (Target Price): {target_mean if target_mean else 'Brak stabilnych danych internetowych'} USD

        PROGNOZA STATYSTYCZNA MONTE CARLO (HORYZONT 52 TYGODNIE):
        - Scenariusz BULL (90. percentyl): {scenariusz_bull[-1]:.2f} USD
        - Scenariusz HOLD (50. percentyl): {scenariusz_hold[-1]:.2f} USD
        - Scenariusz BEAR (10. percentyl): {scenariusz_bear[-1]:.2f} USD

        NAJNOWSZE FAKTY, NEWSY I WYDARZENIA RYNKOWE Z BAZY TAVILY:
        {newsy}

        WYMAGANIA DOTYCZĄCE RAPORTU (BĄDŹ BEZWZGLĘDNIE RESTRYKCYJNY):
        1. Kategorycznie unikaj ogólnych zdań typu 'Spółka staje przed poważnymi wyzwaniami' lub 'Innowacje mogą napędzać wzrost'. Każde stwierdzenie MUSI opierać się na konkretnym fakcie (np. konkretny model produktu, konkretna fabryka, rezygnacja z projektu, precyzyjne koszty chipów, dane o marżach, konkretny konkurent).
        2. Oceń wyliczony wskaźnik P/E. Czy przy obecnej cenie spółka jest przewartościowana, czy niedowartościowana w stosunku do swojej historii i sektora? Co to oznacza dla scenariusza HOLD?
        3. W sekcji SCENARIUSZ BEAR rozbij na czynniki pierwsze twarde ryzyka biznesowe (np. cła, zerwane łańcuchy dostaw, spadek marż, konkretne słabości raportowane w mediach). Jak te wydarzenia doprowadzą cenę do poziomu {scenariusz_bear[-1]:.2f} USD.
        4. W sekcji SCENARIUSZ BULL podaj konkretne, namacalne katalizatory (nowe linie przychodów, AI, konkretne produkty, ekspansja na nowe rynki). Jak te czynniki wystrzelą kurs do poziomu {scenariusz_bull[-1]:.2f} USD.
