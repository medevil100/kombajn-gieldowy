import time
import requests
import pandas as pd
import streamlit as st
import yfinance as yf
from openai import OpenAI

# Ustawienia pod telefony komórkowe
st.set_page_config(
    page_title="Skaner Groszówek AI", 
    page_icon="📱", 
    layout="centered"
)

# Bezpieczne pobieranie kluczy ze Streamlit Secrets
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    st.error("Błąd: Skonfiguruj 'OPENAI_API_KEY' oraz 'APP_PASSWORD' w Streamlit Secrets.")
    st.stop()

# Blokada dostępowa dla urządzeń mobilnych
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔒 Autoryzacja")
    haslo = st.text_input("Wpisz hasło mobilne:", type="password")
    if st.button("Zaloguj się"):
        if haslo == APP_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Błędne hasło!")
    st.stop()

# --- FUNKCJE DYNAMICZNEGO POBIERANIA SPÓŁEK ---
@st.cache_data(ttl=3600)  # Cache na godzinę, aby nie przeciążać sieci przy odświeżaniu minutowym
def pobierz_wszystkie_tickery(rynek):
    """Pobiera aktualną listę wszystkich dostępnych tickerów z zewnątrz."""
    try:
        if rynek == "PL (GPW)":
            # Pobieranie aktualnej listy spółek z GPW z serwerów Stooq
            url = "https://stooq.pl"
            df = pd.read_csv(url, sep='\t', header=None)
            # Filtrujemy tylko akcje polskie (kończące się na .pl -> zamiana na .WA dla yfinance)
            tickery = df[0].dropna().tolist()
            gpw_tickers = [f"{t.upper()}.WA" for t in tickery if t.isalpha()]
            return gpw_tickers
        else:
            # Pobieranie pełnej listy aktywnych spółek z rynku USA
            url = "https://githubusercontent.com"
            res = requests.get(url)
            if res.status_code == 200:
                return [t.strip() for t in res.text.split('\n') if t.strip().isalpha()]
            return ["SNDL", "NIO", "AAL", "F", "LCID", "RIG", "SOFI", "BITF", "HUT"]
    except Exception:
        # Rezerwowa lista awaryjna
        if rynek == "PL (GPW)":
            return ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA", "RFK.WA", "MSW.WA", "BOW.WA"]
        return ["SNDL", "NIO", "AAL", "F", "LCID", "RIG", "SOFI", "BITF", "HUT"]

def skanuj_rynek_realtime(rynek):
    """Skanuje rynek i wyciąga max 100 najtańszych aktywnych spółek spełniających kryteria."""
    pula_tickerow = pobierz_wszystkie_tickery(rynek)
    dane_spolek = []
    licznik = 0
    
    # Pasek postępu widoczny na smartfonie
    progress_bar = st.progress(0, text="Skanowanie rynku w poszukiwaniu groszówek...")
    Calkowita_pula = min(len(pula_tickerow), 150) # Ograniczenie wielkości próby dla szybkości mobilnej
    
    for idx, ticker in enumerate(pula_tickerow[:calkowita_pula]):
        if licznik >= 100:
            break
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="15d")
            if df.empty or len(df) < 10:
                continue
                
            cena = df["Close"].iloc[-1]
            # Kryterium groszówki / centówki (od 0.10 do 5.00 PLN/USD)
            if 0.10 <= cena <= 5.00:
                wolumen_teraz = df["Volume"].iloc[-1]
                wolumen_srednia = df["Volume"].rolling(10).mean().iloc[-1]
                
                if wolumen_teraz > 0:
                    sma_10 = df["Close"].rolling(10).mean().iloc[-1]
                    skok_vol = wolumen_teraz / wolumen_srednia if wolumen_srednia > 0 else 1.0
                    trend = "Wzrostowy" if cena > sma_10 else "Spadkowy"
                    
                    dane_spolek.append({
                        "Ticker": ticker,
                        "Cena": round(cena, 2),
                        "Skok Vol": round(skok_vol, 2),
                        "Trend": trend
                    })
                    licznik += 1
        except Exception:
            continue
        progress_bar.progress((idx + 1) / calkowita_pula, text=f"Sprawdzono {idx+1} spółek...")
        
    progress_bar.empty()
    return pd.DataFrame(dane_spolek)

def generuj_raport_llm(model, dane_tabeli):
    """Wysyła pobrane dane dynamiczne bezpośrednio do wybranego modelu GPT."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    tekst_tabeli = dane_tabeli.to_string(index=False)
    
    prompt = f"""
    Przeanalizuj poniższą listę najtańszych spółek rynkowych w czasie rzeczywistym.
    Wskaż maks. 3 najlepsze okazje (wysoki Skok Vol, cena stabilna lub rosnąca, Trend Wzrostowy).
    Ostrzeż przed spółkami, które drastycznie tracą siłę (Trend Spadkowy przy dużym obrocie).
    Napisz bardzo zwięzłą analizę rynkową przygotowaną pod ekran smartfona:

    {tekst_tabeli}
    """
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Jesteś analitykiem giełdowym. Pisz bardzo krótko, używaj wypunktowań, pogrubień kluczowych tickerów i emoji."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    return response.choices.message.content


# --- INTERFEJS MOBILNY (STREAMLIT) ---
st.title("📱 Mobilny Skaner AI")

# Panel kontrolny ukryty w sidebarze (bocznym menu na telefonie)
with st.sidebar:
    st.header("⚙️ Parametry")
    rynek_wybor = st.radio("Wybierz okno rynkowe:", ["PL (GPW)", "USA"])
    
    # 3 Modele GPT do wyboru zgodnie z życzeniem
    gpt_wybor = st.selectbox(
        "Silnik LLM:", 
        ["gpt-4o-mini", "gpt-4o", "o1-mini"]
    )
    
    # Regulacja odświeżania od 1 do 60 minut
    interwal = st.slider(
        "Interwał odświeżania (min):", 
        min_value=1, 
        max_value=60, 
        value=5
    )
    st.caption(f"Aktualizacja nastąpi automatycznie co {interwal} min.")

# Pobieranie i prezentacja danych bez zapisanych na stałe spółek
st.subheader(f"📊 TOP Groszówki: {rynek_wybor}")
df_aktywne = skanuj_rynek_realtime(rynek_wybor)

if not df_aktywne.empty:
    # Sortowanie domyślne po największym skoku obrotów (potencjał wybicia)
    df_aktywne = df_aktywne.sort_values(by="Skok Vol", ascending=False).head(100)
    
    # Wyświetlanie tabeli na całą szerokość ekranu telefonu
    st.dataframe(df_aktywne, use_container_width=True, hide_index=True)
    
    # Przycisk uruchamiania wybranego GPT
    if st.button(f"🤖 Analizuj przez {gpt_wybor}", type="primary", use_container_width=True):
        with st.spinner("Model GPT przetwarza dane rynkowe..."):
            wynik_ai = generuj_raport_llm(gpt_wybor, df_aktywne)
            st.markdown("### 📝 Wnioski i Alerty AI:")
            st.success(wynik_ai)
else:
    st.warning("W tym momencie brak spółek spełniających kryteria cenowe.")

# Stopka informacyjna o czasie odświeżenia i pętla czasowa
st.caption(f"Zaktualizowano: {time.strftime('%H:%M:%S')} | Następne skanowanie za {interwal} min.")
time.sleep(interwal * 60)
st.rerun()
