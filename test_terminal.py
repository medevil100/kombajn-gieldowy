import time
import pandas as pd
import streamlit as str
import yfinance as yf
from openai import OpenAI

# Ustawienia strony zoptymalizowane pod urządzenia mobilne
str.set_page_config(
    page_title="Groszówki AI", page_icon="📈", layout="centered"
)

# Ładowanie kluczy z Streamlit Secrets
try:
    OPENAI_API_KEY = str.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = str.secrets["APP_PASSWORD"]
except Exception:
    str.error(
        "Błąd: Brak kluczy w Streamlit Secrets (OPENAI_API_KEY lub APP_PASSWORD)."
    )
    str.stop()

# Prosty ekran logowania na telefonie
if "logged_in" not in str.session_state:
    str.session_state.logged_in = False

if not str.session_state.logged_in:
    str.title("🔒 Dostęp zablokowany")
    haslo = str.text_input("Podaj hasło dostępowe:", type="password")
    if str.button("Zaloguj się"):
        if haslo == APP_PASSWORD:
            str.session_state.logged_in = True
            str.rerun()
        else:
            str.error("Niepoprawne hasło.")
    str.stop()


# --- FUNKCJE ANALITYCZNE ---
def pobierz_aktywne_groszowki(rynek):
    """Pobiera i dynamicznie filtruje groszówki ze stałej bazy płynnych tickerów."""
    # Lista bazowa dla zachowania szybkości na telefonie (można rozszerzyć do 100+)
    baza = (
        ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA", "RFK.WA", "MSW.WA", "BOW.WA"]
        if rynek == "PL (GPW)"
        else ["SNDL", "NIO", "AAL", "F", "LCID", "RIG", "SOFI", "BITF", "HUT"]
    )

    dane_spolek = []
    for ticker in baza:
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="30d")
            if len(df) < 15:
                continue

            cena = df["Close"].iloc[-1]
            wolumen_teraz = df["Volume"].iloc[-1]
            wolumen_srednia = df["Volume"].rolling(10).mean().iloc[-1]

            # Kryterium groszówki (< 5 PLN/USD) oraz minimalna płynność
            if 0.10 <= cena <= 5.00 and wolumen_teraz > 0:
                # Wyliczanie wskaźników pędu i trendu
                sma_15 = df["Close"].rolling(15).mean().iloc[-1]
                skok_wolumenu = (
                    wolumen_teraz / wolumen_srednia if wolumen_srednia > 0 else 1.0
                )
                trend = "Wzrostowy" if cena > sma_15 else "Spadkowy"

                dane_spolek.append(
                    {
                        "Spółka": ticker,
                        "Cena": round(cena, 2),
                        "Skok Vol": round(skok_wolumenu, 2),
                        "Trend": trend,
                    }
                )
        except Exception:
            continue

    return pd.DataFrame(dane_spolek)


def analizuj_przez_gpt(model, dane_tabeli):
    """Przesyła przefiltrowane dane giełdowe do wybranego modelu GPT."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    tekst_danych = dane_tabeli.to_string(index=False)

    Prompt = (
        f"Przeanalizuj poniższe spółki groszowe. Wskaż 1-2 najlepsze okazje "
        f"(wysoki Skok Vol + Trend Wzrostowy) oraz ostrzeż przed spółkami tracącymi siłę. "
        f"Napisz krótki, konkretny raport zwięźle, idealny do przeczytania na ekranie telefonu:\n\n{tekst_danych}"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Jesteś ekspertem giełdowym od penny stocks. Odpowiadasz krótko, używając wypunktowań i emoji.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


# --- INTERFEJS MOBILNY (STREAMLIT) ---
str.title("📱 Skaner Groszówek AI")

# Menu boczne zoptymalizowane pod smartfony (z możliwością zwinięcia)
with str.sidebar:
    str.header("⚙️ Ustawienia")
    rynek_wybor = str.radio("Wybierz rynek:", ["PL (GPW)", "USA"])

    # 3 Modele GPT do wyboru
    gpt_wybor = str.selectbox(
        "Model AI (OpenAI):", ["gpt-4o-mini", "gpt-4o", "o1-mini"]
    )

    # Regulacja odświeżania w czasie rzeczywistym
    interwal = str.slider(
        "Czas odświeżania (minuty):",
        min_value=1,
        max_value=60,
        value=5,
        step=1,
    )
    str.caption(f"Aplikacja przeładuje dane automatycznie co {interwal} min.")

# Główny kontener danych rynkowych
str.subheader(f"📊 Dane Real-Time: {rynek_wybor}")
tabela_danych = pobierz_aktywne_groszowki(rynek_wybor)

if not tabela_danych.empty:
    # Wyświetlanie danych w tabeli dopasowanej do smartfona
    str.dataframe(tabela_danych, use_container_width=True, hide_index=True)

    # Sekcja uruchamiania dedykowanej analizy LLM
    if str.button(f"🤖 Generuj analizę przez {gpt_wybor}", type="primary"):
        with str.spinner("Sztuczna inteligencja przetwarza macierz danych..."):
            raport = analizuj_przez_gpt(gpt_wybor, tabela_danych)
            str.markdown("### 📝 Raport i Alerty AI:")
            str.info(raport)
else:
    str.warning("Brak spółek spełniających kryteria groszówki w tej minucie.")

# Licznik czasu i pętla automatycznego odświeżania ekranu mobilnego
str.caption(f"Ostatnia aktualizacja: {time.strftime('%H:%M:%S')}")
time.sleep(interwal * 60)
str.rerun()
