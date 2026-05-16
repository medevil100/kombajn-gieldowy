import os
import time
import re
import asyncio
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import AsyncOpenAI  # Zmiana na klienta asynchronicznego

# --- KONFIGURACJA STRONY ---
st.set_page_config(
    page_title="Skaner Groszówek AI Master Pro", page_icon="📱", layout="centered"
)

# --- MATRYCA WIZUALNA (CSS) ---
st.markdown(
    """
    <style>
    .stApp { background-color: #0E1117; }
    div[data-testid="stDataFrame"] { background-color: #161B22; border: 1px solid #30363D; border-radius: 8px; }
    div.stButton > button:first-child {
        background-color: #00ff66 !important; color: #000000 !important; font-weight: bold !important;
        border-radius: 6px !important; border: none !important; box-shadow: 0 0 12px rgba(0, 255, 102, 0.5);
    }
    .consensus-box {
        padding: 15px; border-radius: 8px; border: 1px solid #30363D; text-align: center; margin-bottom: 20px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# --- SECRETS & AUTORYZACJA ---
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    st.error("Błąd: Skonfiguruj 'OPENAI_API_KEY' oraz 'APP_PASSWORD' w Streamlit Secrets.")
    st.stop()

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


# --- TRWAŁY ZAPIS DO PLIKÓW ---
def wczytaj_liste_z_pliku(rynek):
    nazwa_pliku = "spolki_pl.txt" if rynek == "PL (GPW)" else "spolki_usa.txt"
    if os.path.exists(nazwa_pliku):
        with open(nazwa_pliku, "r") as f:
            zawartosc = f.read()
            return [t.strip().upper() for t in zawartosc.split(",") if t.strip()]
    return (
        ["ATT.WA", "COG.WA", "PCO.WA", "SNS.WA"]
        if rynek == "PL (GPW)"
        else ["SNDL", "NIO", "AAL", "F"]
    )


def zapisz_liste_do_pliku(rynek, lista_tickerow):
    nazwa_pliku = "spolki_pl.txt" if rynek == "PL (GPW)" else "spolki_usa.txt"
    with open(nazwa_pliku, "w") as f:
        f.write(", ".join(lista_tickerow))


# --- DETEKCJA FORMACJI ŚWIECOWYCH ---
def wykryj_formacje_swiecowe(df):
    if len(df) < 2:
        return "Brak danych"

    o = df["Open"].iloc[-1]
    h = df["High"].iloc[-1]
    l = df["Low"].iloc[-1]
    c = df["Close"].iloc[-1]

    o_prev = df["Open"].iloc[-2]
    c_prev = df["Close"].iloc[-2]

    korpus = abs(c - o)
    cien_dolny = min(o, c) - l
    cien_gorny = h - max(o, c)
    zakres = h - l if (h - l) > 0 else 0.001

    if cien_dolny > (2 * korpus) and cien_gorny < (0.2 * zakres):
        return "🔨 Młot"
    if c_prev < o_prev and c > o and o <= c_prev and c >= o_prev:
        return "🔥 Objęcie Hossy"

    return "Neutralna"


# --- MATEMATYKA GIEŁDOWA ---
def oblicz_wskazniki(df):
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    exp1 = df["Close"].ewm(span=12, adjust=False).mean()
    exp2 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = exp1 - exp2
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    df["MA20"] = df["Close"].rolling(window=20).mean()
    df["STD20"] = df["Close"].rolling(window=20).std()
    df["Upper_Band"] = df["MA20"] + (df["STD20"] * 2)
    df["Lower_Band"] = df["MA20"] - (df["STD20"] * 2)

    high_low = df["High"] - df["Low"]
    high_cp = np.abs(df["High"] - df["Close"].shift())
    low_cp = np.abs(df["Low"] - df["Close"].shift())
    df["ATR"] = (
        pd.concat([high_low, high_cp, low_cp], axis=1)
        .max(axis=1)
        .rolling(14)
        .mean()
    )

    return df


def skanuj_wybrane_spolki(lista_tickerow):
    dane_spolek = []
    slownik_df = {}
    if not lista_tickerow:
        return pd.DataFrame(), {}

    for ticker in lista_tickerow:
        try:
            t = yf.Ticker(ticker.strip().upper())
            df = t.history(period="260d")
            if df.empty or len(df) < 50:
                continue

            okres_52w = df.iloc[-252:] if len(df) >= 252 else df
            high_52w = okres_52w["High"].max()
            low_52w = okres_52w["Low"].min()
            roznica_52w = high_52w - low_52w if (high_52w - low_52w) > 0 else 0.001

            df = oblicz_wskazniki(df)
            ostatni = df.iloc[-1]
            cena = ostatni["Close"]
            wolumen_teraz = ostatni["Volume"]
            wolumen_srednia = df["Volume"].rolling(10).mean().iloc[-1]

            if wolumen_teraz > 0:
                sma_10 = df["Close"].rolling(10).mean().iloc[-1]
                skok_vol = (
                    wolumen_teraz / wolumen_srednia
                    if wolumen_srednia > 0
                    else 1.0
                )
                trend = "🟢 Wzrostowy" if cena > sma_10 else "🔴 Spadkowy"

                u_band = ostatni["Upper_Band"]
                l_band = ostatni["Lower_Band"]
                m_band = ostatni["MA20"]
                
                pozycja_bb = "Środek"
                if cena >= u_band:
                    pozycja_bb = "🔥 Wybicie Górą"
                elif cena <= l_band:
                    pozycja_bb = "⚠️ Wybicie Dołem"
                elif cena > m_band:
                    pozycja_bb = "📈 Powyżej MA20"
                elif cena < m_band:
                    pozycja_bb = "📉 Poniżej MA20"

                f38 = high_52w - (0.382 * roznica_52w)
                f50 = high_52w - (0.500 * roznica_52w)
                f61 = high_52w - (0.618 * roznica_52w)

                odleglosc_od_dna = ((cena - low_52w) / low_52w) * 100
                
                if cena >= f38:
                    strefa_fibo = "👑 HIGH"
                elif cena < f38 and cena >= f61:
                    strefa_fibo = "⚖️ ŚRODEK"
                else:
                    strefa_fibo = "🛒 LOW"

                formacja = wykryj_formacje_swiecowe(df)

                dane_spolek.append(
                    {
                        "Ticker": ticker.strip().upper(),
                        "Cena": round(cena, 2),
                        "Skok Vol": round(skok_vol, 2),
                        "Trend": trend,
                        "RSI (14)": (
                            round(ostatni["RSI"], 1)
                            if not pd.isna(ostatni["RSI"])
                            else 50.0
                        ),
                        "MACD Hist": (
                            round(ostatni["MACD"] - ostatni["Signal"], 4)
                            if not pd.isna(ostatni["Signal"])
                            else 0.0
                        ),
                        "Zmienność (ATR)": (
                            round(ostatni["ATR"], 3)
                            if not pd.isna(ostatni["ATR"])
                            else 0.0
                        ),
                        "Wstęgi BB": pozycja_bb,
                        "Strefa Fibo": strefa_fibo,
                        "Fibo 50%": round(f50, 2),
                        "52W Low": round(low_52w, 2),
                        "52W High": round(high_52w, 2),
                        "Od Dna (%)": round(odleglosc_od_dna, 1),
                        "Formacja": formacja,
                    }
                )
                slownik_df[ticker.strip().upper()] = df
        except Exception:
            continue

    return pd.DataFrame(dane_spolek), slownik_df


# --- NOWOŚĆ: ASYNCHRONICZNE ODPYTYWANIE OPENAI ---
async def async_generuj_odpowiedz_modelu(client, model, prompt):
    params = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if model == "o3-mini":
        params["reasoning_effort"] = "high"

    try:
        response = await client.chat.completions.create(**params)
        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        return "❌ Błąd: Odpowiedź modelu jest pusta."
    except Exception as e:
        return f"❌ Błąd OpenAI dla {model}: {str(e)}"


# Koordynator asynchroniczny uruchamiający 3 modele na raz
async def pobierz_wszystkie_raporty(api_key, prompt):
    client = AsyncOpenAI(api_key=api_key)
    zadania = [
        async_generuj_odpowiedz_modelu(client, "o3-mini", prompt),
        async_generuj_odpowiedz_modelu(client, "gpt-4o", prompt),
        async_generuj_odpowiedz_modelu(client, "gpt-4o-mini", prompt)
    ]
    return await asyncio.gather(*zadania)


# --- PARSER PUNKTACJI CONSENSUS SCORE ---
def wyciagnij_score(tekst_raportu):
    match = re.search(r"\[SCORE:\s*([1-5])\]", tekst_raportu)
    if match:
        return int(match.group(1))
    return None


# --- WIZUALIZACJA WYKRESU INTERAKTYWNEGO Z BB I FIBO ---
def rysuj_wykres(df, ticker):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Cena"))
    fig.add_trace(go.Scatter(x=df.index, y=df["Upper_Band"], line=dict(color="rgba(255, 0, 100, 0.6)", width=1.5, dash="dash"), name="BB Górna"))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA20"], line=dict(color="rgba(255, 255, 255, 0.4)", width=1), name="BB Środek (MA20)"))
    fig.add_trace(go.Scatter(x=df.index, y=df["Lower_Band"], line=dict(color="rgba(0, 150, 255, 0.6)", width=1.5, dash="dash"), name="BB Dolna"))
    
    okres_52w = df.iloc[-252:] if len(df) >= 252 else df
    h_52w = okres_52w["High"].max()
    l_52w = okres_52w["Low"].min()
    diff = h_52w - l_52w

    poziomy_fibo = {
        "Fibo 100%": h_52w, "Fibo 61.8%": h_52w - (0.382 * diff), "Fibo 50.0%": h_52w - (0.500 * diff),
        "Fibo 38.2%": h_52w - (0.618 * diff), "Fibo 23.6%": h_52w - (0.764 * diff), "Fibo 0%": l_52w
    }
    colors = ["#ff4d4d", "#ffaa00", "#ffff00", "#00ffaa", "#00aaff", "#aa00ff"]
    for (nazwa, poziom), kolor in zip(poziomy_fibo.items(), colors):
        fig.add_trace(go.Scatter(x=[df.index[0], df.index[-1]], y=[poziom, poziom], mode="lines", line=dict(color=kolor, width=1, dash="dot"), name=nazwa))

    fig.update_layout(title=f"Wykres techniczny {ticker}", template="plotly_dark", xaxis_rangeslider_visible=False, height=450)
    st.plotly_chart(fig, use_container_width=True)


# --- INTERFEJS UŻYTKOWNIKA ---
st.title("📱 Skaner AI Pro Master v2")

with st.sidebar:
    st.header("⚙️ Panel Sterowania")
    rynek = st.radio("Wybierz rynek:", ["PL (GPW)", "USA (NYSE/NASDAQ)"])
    
    # --- NOWOŚĆ: Bezpiecznik portfela API (Inteligentne Sito) ---
    aktywuj_sito = st.checkbox("🛡️ Aktywuj Inteligentne Sito AI", value=True, help="Blokuje odpytywanie AI dla spółek o niskim wolumenie i bez wyraźnego układu technicznego. Oszczędza tokeny.")
    
    lista_tickerow = wczytaj_liste_z_pliku(rynek)

    st.subheader("📝 Edycja Listy Spółek")
    nowa_lista_str = st.text_area("Wpisz tickery po przecinku:", value=", ".join(lista_tickerow))

    if st.button("Zapisz listę spółek", use_container_width=True):
        zaktualizowana_lista = [t.strip().upper() for t in nowa_lista_str.split(",") if t.strip()]
        zapisz_liste_do_pliku(rynek, zaktualizowana_lista)
        st.success("Lista została zapisana!")
        st.rerun()

if st.button("🚀 URUCHOM SKANOWANIE RYNKU", use_container_width=True):
    with st.spinner("Pobieranie danych i obliczanie wskaźników..."):
        df_wyniki, slownik_df = skanuj_wybrane_spolki(lista_tickerow)
        if df_wyniki.empty:
            st.warning("Brak danych.")
        else:
            st.session_state["df_wyniki"] = df_wyniki
            st.session_state["slownik_df"] = slownik_df
            st.success(f"Przeskanowano {len(df_wyniki)} spółek!")

if "df_wyniki" in st.session_state and not st.session_state["df_wyniki"].empty:
    df_wyniki = st.session_state["df_wyniki"]
    slownik_df = st.session_state["slownik_df"]

    st.subheader("📊 Wyniki Analizy Technicznej + Fibo + BB")
    st.dataframe(df_wyniki, use_container_width=True)

    st.divider()
    st.subheader("🤖 Błyskawiczna Multi-Analiza Asynchroniczna AI")

    wybrany_ticker = st.selectbox("Wybierz spółkę do analizy:", df_wyniki["Ticker"].tolist())
    wiersz = df_wyniki[df_wyniki["Ticker"] == wybrany_ticker].iloc[0]

    # Bezpiecznik sita rynkowego przed AI
    sito_zaliczone = True
    powod_blokady = ""
    if aktywuj_sito:
        if wiersz["Skok Vol"] < 1.5 and wiersz["Formacja"] == "Neutralna" and wiersz["Wstęgi BB"] == "Środek":
            sito_zaliczone = False
            powod_blokady = "Niski wolumen (Skok Vol < 1.5) oraz brak jasnych sygnałów technicznych (Formacja Neutralna, Wstęgi BB: Środek)."

    st.write(f"### 🎯 Konfiguracja pozycji dla {wybrany_ticker}")
    col1, col2, col3, col4 = st.columns(4)
    with col1: tp1 = st.number_input("TP1", value=float(wiersz["Cena"] * 1.05), step=0.01)
    with col2: tp2 = st.number_input("TP2", value=float(wiersz["Cena"] * 1.10), step=0.01)
    with col3: tp3 = st.number_input("TP3", value=float(wiersz["Cena"] * 1.20), step=0.01)
    with col4: sl = st.number_input("Stop Loss", value=float(wiersz["Cena"] * 0.95), step=0.01)

    tp_tekst = f"Cele: TP1={tp1}, TP2={tp2}, TP3={tp3}, SL={sl}."

    # Blokada przycisku, jeśli aktywowane jest sito i warunki nie zostały spełnione
    if not sito_zaliczone:
        st.warning(f"🚫 **Sito AI zablokowało tę spółkę**: {powod_blokady}")
        generuj_klik = st.button("Uruchom mimo blokady sita (Wymuś)", use_container_width=True)
    else:
        generuj_klik = st.button("⚡ GENERUJ ASYNCHRONICZNE PORÓWNANIE (3 MODELE)", use_container_width=True)

    if generuj_klik:
        dane_tekst = wiersz.to_string()
        
        # Wymuszenie formatu rygorystycznego punktowania za pomocą tagu [SCORE: X]
        prompt = f"""
        Jesteś elitarnym traderem. Wykonaj natychmiastową analizę techniczną.
        
        NAJWAŻNIEJSZA REGUŁA: Twoja odpowiedź MUSI zaczynać się od sztywnego formatu oceny pozycji w pierwszej linijce, np: '[SCORE: 4]' (gdzie 1 to mocne sprzedaj, 5 to mocne kup). Nie używaj żadnego tekstu przed tym tagiem!
        
        [DANE TECH-MATH]:
        {dane_tekst}
        
        [STRATEGIA TRADERA]:
        {tp_tekst}
        
        Zinterpretuj krytycznie w punktach:
        1. Położenie na siatce Fibonacciego ({wiersz['Strefa Fibo']}) i wstęgach Bollingera ({wiersz['Wstęgi BB']}).
        2. Realność matematyczną celów TP1, TP2, TP3 w oparciu o zmienność ATR i Skok Wolumenu.
        3. Ostateczną decyzję (KUP / SPRZEDAJ / CZEKAJ).
        
        Surowo, technicznie, krótko. Używaj emoji.
        """
        
        with st.spinner("Asynchroniczny silnik pobiera odpowiedzi równolegle ze wszystkich 3 modeli..."):
            # Wywołanie pętli asynchronicznej wewnątrz synchronicznego Streamlita
            raport_o3, raport_4o, raport_mini = asyncio.run(pobierz_wszystkie_raporty(OPENAI_API_KEY, prompt))
            
        # Obliczanie Consensus Score
        score_o3 = wyciagnij_score(raport_o3)
        score_4o = wyciagnij_score(raport_4o)
        score_mini = wyciagnij_score(raport_mini)
        
        wyniki_score = [s for s in [score_o3, score_4o, score_mini] if s is not None]
        
        # Sekcja wizualna Consensus Score
        if wyniki_score:
            srednia_consensus = round(np.mean(wyniki_score), 2)
            if srednia_consensus >= 4.0:
                kolor_box, tekst_box = "#004d1a", "🟢 SILNY KONSENSUS KUPNA"
            elif srednia_consensus <= 2.2:
                kolor_box, tekst_box = "#4d0000", "🔴 SILNY KONSENSUS SPRZEDAŻY"
            else:
                kolor_box, tekst_box = "#332200", "🟡 BRAK JEDNOMYŚLNOŚCI / CZEKAJ"
                
            st.markdown(
                f"""
                <div class="consensus-box" style="background-color: {kolor_box};">
                    <h2 style="color: white; margin: 0;">📊 Średni AI Consensus Score: {srednia_consensus} / 5.0</h2>
                    <strong style="color: #00ff66;">{tekst_box}</strong><br>
                    <small style="color: #cccccc;">(o3-mini: {score_o3 if score_o3 else 'N/A'} | gpt-4o: {score_4o if score_4o else 'N/A'} | gpt-4o-mini: {score_mini if score_mini else 'N/A'})</small>
                </div>
                """,
                unsafe_allow_html=True
            )
            
        # Wyświetlanie wyników w zakładkach
        tab1, tab2, tab3 = st.tabs(["🧠 o3-mini (Rozumowanie)", "⚡ gpt-4o (Główny Analityk)", "💨 gpt-4o-mini (Weryfikator)"])
        with tab1: st.info(raport_o3)
        with tab2: st.success(raport_4o)
        with tab3: st.warning(raport_mini)

    if wybrany_ticker in slownik_df:
        rysuj_wykres(slownik_df[wybrany_ticker], wybrany_ticker)
