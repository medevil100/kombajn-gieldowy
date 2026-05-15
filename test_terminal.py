import time
import pandas as pd
import streamlit as st
import yfinance as yf
from openai import OpenAI

# Ustawienia pod telefony komórkowe
st.set_page_config(
    page_title="Skaner Groszówek AI Pro", 
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
    if st.button("Zaloguj się", use_container_width=True):
        if haslo == APP_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Błędne hasło!")
    st.stop()

# --- ZARZĄDZANIE ZAPISANYMI LISTAMI SPÓŁEK ---
if "spolki_pl" not in st.session_state:
    # Początkowa lista startowa (możesz ją wyczyścić w aplikacji)
    st.session_state.spolki_pl = ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA", "RFK.WA"]

if "spolki_usa" not in st.session_state:
    st.session_state.spolki_usa = ["SNDL", "NIO", "AAL", "F", "LCID", "RIG"]

# --- FUNKCJE ANALITYCZNE ---
def skanuj_wybrane_spolki(lista_tickerow):
    """Pobiera dane w czasie rzeczywistym dla zdefiniowanej listy spółek."""
    dane_spolek = []
    if not lista_tickerow:
        return pd.DataFrame()
        
    for ticker in lista_tickerow:
        try:
            t = yf.Ticker(ticker.strip().upper())
            df = t.history(period="15d")
            if df.empty or len(df) < 10:
                continue
                
            cena = df["Close"].iloc[-1]
            wolumen_teraz = df["Volume"].iloc[-1]
            wolumen_srednia = df["Volume"].rolling(10).mean().iloc[-1]
            
            if wolumen_teraz > 0:
                sma_10 = df["Close"].rolling(10).mean().iloc[-1]
                skok_vol = wolumen_teraz / wolumen_srednia if wolumen_srednia > 0 else 1.0
                trend = "Wzrostowy" if cena > sma_10 else "Spadkowy"
                
                dane_spolek.append({
                    "Ticker": ticker.strip().upper(),
                    "Cena": round(cena, 2),
                    "Skok Vol": round(skok_vol, 2),
                    "Trend": trend
                })
        except Exception:
            continue
            
    return pd.DataFrame(dane_spolek)

def generuj_raport_mocne_llm(model, dane_tabeli):
    """Wysyła dane do najsilniejszych modeli OpenAI zoptymalizowanych pod kątem głębokiego rozumowania."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    tekst_tabeli = dane_tabeli.to_string(index=False)
    
    prompt = f"""
    Jesteś elitarnym analitykiem ilościowym (Quant) specjalizującym się w spółkach groszowych.
    Dokonaj rygorystycznej oceny ryzyka i potencjału dla poniższych pozycji giełdowych:

    {tekst_tabeli}

    Wskaż:
    1. Najsilniejsze anomalie wolumenowe potwierdzające napływ kapitału (Skok Vol >> 1.0 + Trend Wzrostowy).
    2. Spółki z Twojego portfela, które drastycznie tracą siłę (Trend Spadkowy) - wygeneruj dla nich wyraźne ALERT-y.
    
    Sformatuj odpowiedź krótko i czytelnie, idealnie pod ekran smartfona. Używaj punktów i emoji.
    """
    
    # Modele z serii o1/o3 nie zawsze wspierają parametr system prompt lub temperature w tradycyjny sposób,
    # dlatego przekazujemy pełną instrukcję bezpośrednio w treści wiadomości użytkownika.
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices.message.content


# --- INTERFEJS MOBILNY (STREAMLIT) ---
st.title("📱 Skaner AI Pro")

# Panel boczny (Sidebar)
with st.sidebar:
    st.header("⚙️ Parametry")
    rynek_wybor = st.radio("Wybierz okno rynkowe:", ["PL (GPW)", "USA"])
    
    # Wybór najmocniejszych modeli AI na rynku
    gpt_wybor = st.selectbox(
        "Mocny Silnik AI:", 
        ["o3-mini", "o1", "gpt-4o"]
    )
    
    interwal = st.slider(
        "Interwał odświeżania (min):", 
        min_value=1, 
        max_value=60, 
        value=5
    )
    st.caption(f"Aktualizacja automatyczna co {interwal} min.")

# --- SEKCJA RĘCZNEGO DODAWANIA SPÓŁEK ---
st.subheader("📝 Zarządzaj swoją listą")
aktualna_lista = st.session_state.spolki_pl if rynek_wybor == "PL (GPW)" else st.session_state.spolki_usa

# Wyświetlanie obecnych tickerów w formie czytelnego ciągu tekstowego
lista_tekst = ", ".join(aktualna_lista)
nowa_lista_tekst = st.text_area(
    f"Edytuj spółki dla {rynek_wybor} (rozdzielaj przecinkami):", 
    value=lista_tekst,
    help="Dla GPW pamiętaj o dopisku .WA, np. COG.WA, PCO.WA"
)

# Zapisywanie zmian wprowadzonych przez użytkownika
if st.button("💾 Zapisz listę spółek", use_container_width=True):
    czysta_lista = [t.strip().upper() for t in nowa_lista_tekst.split(",") if t.strip()]
    if rynek_wybor == "PL (GPW)":
        st.session_state.spolki_pl = czysta_lista
    else:
        st.session_state.spolki_usa = czysta_lista
    st.success("Lista została pomyślnie zaktualizowana i zapisana!")
    st.rerun()


# --- WYŚWIETLANIE DANYCH I ANALIZA ---
st.subheader(f"📊 Monitorowane Groszówki: {rynek_wybor}")
df_aktywne = skanuj_wybrane_spolki(st.session_state.spolki_pl if rynek_wybor == "PL (GPW)" else st.session_state.spolki_usa)

if not df_aktywne.empty:
    # Sortowanie po anomalii obrotu (najwyższy skok wolumenu na górze)
    df_aktywne = df_aktywne.sort_values(by="Skok Vol", ascending=False)
    
    # Tabela dopasowana pod telefon
    st.dataframe(df_aktywne, use_container_width=True, hide_index=True)
    
    # Przycisk uruchomienia zaawansowanego rozumowania AI
    if st.button(f"🧠 Analizuj przez {gpt_wybor}", type="primary", use_container_width=True):
        with st.spinner(f"Potężny model {gpt_wybor} przetwarza i wnioskuje..."):
            wynik_ai = generuj_raport_llm = analizuj_przez_gpt = raport = analizuj_sentyment_wiadomosci = generuj_raport_mocne_llm(gpt_wybor, df_aktywne)
            st.markdown("### 📝 Zaawansowany Raport i Alerty AI:")
            st.info(wynik_ai)
else:
    st.warning("Twoja lista jest pusta lub dodane spółki nie handlowały na dzisiejszej sesji.")

# Stopka mobilna z odliczaniem czasu
st.caption(f"Aktualne dane z godziny: {time.strftime('%H:%M:%S')} | Auto-odświeżanie za {interwal} min.")
time.sleep(interwal * 60)
st.rerun()
