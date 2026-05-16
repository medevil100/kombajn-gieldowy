import os
import time
import re
import asyncio
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import AsyncOpenAI

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
        padding: 20px; border-radius: 8px; border: 1px solid #30363D; 
        background-color: #161B22; color: #E6EDF2; text-align: left; 
        margin-top: 20px; margin-bottom: 20px; line-height: 1.6;
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


# --- FUNKCJA ALARMOWA PC ---
def wyzwól_alarm_dzwiekowy_pc():
    """Odtwarza dźwięk ostrzegawczy bezpośrednio w przeglądarce PC."""
    audio_html = """
        <audio autoplay style="display:none;">
            <source src="https://google.com" type="audio/ogg">
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)


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
    rs = gain / (loss + 1e-10)
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

    df["MA50"] = df["Close"].rolling(window=50).mean()
    df["MA10"] = df["Close"].rolling(window=10).mean()

    low_14 = df["Low"].rolling(window=14).min()
    high_14 = df["High"].rolling(window=14).max()
    df["Stoch_K"] = 100 * ((df["Close"] - low_14) / ((high_14 - low_14) + 1e-10))
    df["Stoch_D"] = df["Stoch_K"].rolling(window=3).mean()

    return df


def skanuj_wybrane_spolki(lista_tickerow):
    dane_spolek = []
    slownik_df = {}
    if not lista_tickerow:
        return pd.DataFrame(), {}

    for ticker in lista_tickerow:
        try:
            ticker_clean = ticker.strip().upper()
            t = yf.Ticker(ticker_clean)
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
                skok_vol = (
                    wolumen_teraz / wolumen_srednia
                    if wolumen_srednia > 0
                    else 1.0
                )
                
                ma10_teraz = ostatni["MA10"]
                ma50_teraz = ostatni["MA50"]
                if pd.isna(ma50_teraz):
                    trend = "⚪ Brak danych MA50"
                else:
                    trend = "🟢 Byczy (MA10 > MA50)" if ma10_teraz > ma50_teraz else "🔴 Niedźwiedzi"

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

                stoch_k_val = ostatni["Stoch_K"] if not pd.isna(ostatni["Stoch_K"]) else 50.0
                
                if stoch_k_val > 80:
                    kondycja_stoch = "⚠️ Wykupiony"
                elif stoch_k_val < 20:
                    kondycja_stoch = "🛒 Wyprzedany"
                else:
                    kondycja_stoch = "Neutralny"

                dane_spolek.append(
                    {
                        "Ticker": ticker_clean,
                        "Cena": round(cena, 2),
                        "Skok Vol": round(skok_vol, 2),
                        "Trend (MA10/50)": trend,
                        "RSI (14)": (
                            round(ostatni["RSI"], 1)
                            if not pd.isna(ostatni["RSI"])
                            else 50.0
                        ),
                        "Stochastic %K": round(stoch_k_val, 1),
                        "Stoch Stan": kondycja_stoch,
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
                slownik_df[ticker_clean] = df
        except Exception:
            continue

    df_wynikowy = pd.DataFrame(dane_spolek)
    
    if not df_wynikowy.empty and "Ticker" in df_wynikowy.columns:
        kolejnosc_kolumn = ["Ticker"] + [c for c in df_wynikowy.columns if c != "Ticker"]
        df_wynikowy = df_wynikowy[kolejnosc_kolumn]
        
    return df_wynikowy, slownik_df


# --- NAPRAWIONE ASYNCHRONICZNE ODPYTYWANIE OPENAI ---
async def async_generuj_odpowiedz_modelu(client, model, prompt):
    params = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if model == "o3-mini":
        params["reasoning_effort"] = "high"

    try:
        response = await client.chat.completions.create(**params)
        # NAPRAWA BŁĘDU MAPOWANIA STRUKTURY ODPOWIEDZI DLA NOWEGO API OPENAI
        return response.choices[0].message.content
    except Exception as e:
        return f"Błąd LLM ({model}): {str(e)}"


# --- INTERFEJS UŻYTKOWNIKA STREAMLIT ---
def main():
    st.title("📱 Skaner Groszówek AI Master Pro")
    
    rynek = st.selectbox("Wybierz rynek:", ["PL (GPW)", "USA"])
    
    lista_tickerow = wczytaj_liste_z_pliku(rynek)
    nowa_lista_str = st.text_area(
        "Edytuj listę spółek (rozdzielone przecinkami):", 
        value=", ".join(lista_tickerow)
    )
    
    if st.button("Zapisz listę spółek"):
        zaktualizowana_lista = [t.strip().upper() for t in nowa_lista_str.split(",") if t.strip()]
        zapisz_liste_do_pliku(rynek, zaktualizowana_lista)
        st.success("Lista została zaktualizowana!")
        st.rerun()

    model_ai = st.selectbox("Wybierz model AI wspierający analizę:", ["gpt-4o", "o3-mini"])

    if st.button("URUCHOM SKANOWANIE RYNKU", use_container_width=True):
        zaktualizowana_lista = [t.strip().upper() for t in nowa_lista_str.split(",") if t.strip()]
        
        with st.spinner("Pobieranie danych rynkowych i analiza wskaźników..."):
            df_wyniki, slownik_charts = skanuj_wybrane_spolki(zaktualizowana_lista)
            
        if df_wyniki.empty:
            st.warning("Brak danych do wyświetlenia. Sprawdź poprawność tickerów.")
            return

        st.subheader("📊 Wyniki Analizy Technicznej + Fibo + BB")
        st.dataframe(df_wyniki, use_container_width=True)

        # --- DETEKTOR ALARMÓW (LOGIKA WYŁĄCZNIE NA PC) ---
        okazje = df_wyniki[
            (df_wyniki["Stoch Stan"] == "🛒 Wyprzedany") | 
            (df_wyniki["Wstęgi BB"] == "⚠️ Wybicie Dołem") |
            (df_wyniki["Formacja"].isin(["🔨 Młot", "🔥 Objęcie Hossy"]))
        ]
        
        if not okazje.empty:
            wyzwól_alarm_dzwiekowy_pc()
            st.error(f"🚨 ALARM SYSTEMOWY PC: Wykryto okazje zakupowe dla spółek: {', '.join(okazje['Ticker'].tolist())}!")

        # Analiza Konsensusu AI (Panel z ulepszonym stylem wyświetlania)
        st.subheader("🤖 Analiza Konsensusu Sztucznej Inteligencji")
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        
        prompt_ai = f"""
        Jesteś profesjonalnym analitykiem giełdowym. Przeanalizuj poniższe rozbudowane dane rynkowe z systemu skanera:
        {df_wyniki.to_string(index=False)}
        
        Wskaż 2 najlepsze okazje inwestycyjne oparte o sygnały Wstęg Bollingera (BB), poziomów Fibonacciego (Fibo) oraz nowego oscylatora Stochastic i trendu MA10/MA50.
        Podaj jasne i precyzyjne uzasadnienie w punktach.
        """
        
        with st.spinner("AI generuje konsensus analityczny..."):
            analiza_tekst = asyncio.run(async_generuj_odpowiedz_modelu(client, model_ai, prompt_ai))
            
        # Wyświetlenie komentarza AI w sformatowanym panelu consensus-box
        st.markdown(f'<div class="consensus-box">{analiza_tekst}</div>', unsafe_allow_html=True)

        st.subheader("📈 Interaktywny podgląd wykresów technicznych")
        for tick, df_tick in slownik_charts.items():
            with st.expander(f"Wykres dla: {tick}"):
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df_tick.index[-60:], open=df_tick['Open'].iloc[-60:],
                    high=df_tick['High'].iloc[-60:], low=df_tick['Low'].iloc[-60:],
                    close=df_tick['Close'].iloc[-60:], name="Cena"
                ))
                fig.add_trace(go.Scatter(
                    x=df_tick.index[-60:], y=df_tick['Upper_Band'].iloc[-60:],
                    line=dict(color='rgba(255, 0, 0, 0.5)', width=1), name="BB Górna"
                ))
                fig.add_trace(go.Scatter(
                    x=df_tick.index[-60:], y=df_tick['Lower_Band'].iloc[-60:],
                    line=dict(color='rgba(0, 255, 0, 0.5)', width=1), name="BB Dolna"
                ))
                if 'MA50' in df_tick.columns:
                    fig.add_trace(go.Scatter(
                        x=df_tick.index[-60:], y=df_tick['MA50'].iloc[-60:],
                        line=dict(color='rgba(255, 255, 0, 0.6)', width=1.5, dash='dash'), name="MA50 (Trend)"
                    ))
                fig.update_layout(title=f"Ostatnie 60 sesji dla {tick}", template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
