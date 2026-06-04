import time
from typing import Dict, Any, List, Optional

import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from openai import OpenAI

# =========================================================
# KONFIGURACJA STRONY
# =========================================================
st.set_page_config(layout="wide", page_title="Terminal Finansowy AI MAX")
st.title("⚡ Terminal AI MAX – Fundamenty, Momentum, Skanery, Raport ULTRA, Asystent AI")

# =========================================================
# AUTOMATYCZNE POBIERANIE KLUCZA OPENAI (ST.SECRETS)
# =========================================================
# Sprawdzenie czy klucz istnieje w sekretach Streamlit
if "OPENAI_API_KEY" not in st.secrets:
    st.error("❌ Brak klucza API! Skonfiguruj plik .streamlit/secrets.toml lub ustawienia chmury.")
    st.stop()

# Pobranie klucza w tle
openai_key = st.secrets["OPENAI_API_KEY"]

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=openai_key)

# =========================================================
# RESZTA TWOJEGO KODU TERMINALA
# =========================================================
st.success("✅ Klucz API został wczytany automatycznie. Terminal jest gotowy do pracy!")


# =========================================================
# GLOBALNY SYSTEM PROMPT – OSOBOWOŚĆ ASYSTENTA
# =========================================================
AI_SYSTEM = """
Jesteś profesjonalnym analitykiem finansowym i asystentem inwestora.
Masz dostęp do danych, które dostarcza aplikacja (ceny, wskaźniki, fundamenty).
NIGDY nie pisz, że nie masz dostępu do danych rynkowych, internetu ani notowań.
Analizujesz TYLKO na podstawie danych przekazanych przez użytkownika lub aplikację.
Nie odsyłaj do Yahoo, Google, GPW, Bloomberg ani żadnych stron.
Pisz konkretnie, technicznie, po polsku, bez lania wody.
Zachowuj się jak ekspert, nie jak chatbot.
"""

# =========================================================
# SESJA – PAMIĘĆ I KONTEKST
# =========================================================
if "ai_memory" not in st.session_state:
    st.session_state["ai_memory"] = []

if "ostatnia_spolka" not in st.session_state:
    st.session_state["ostatnia_spolka"] = None

if "historia_czatu" not in st.session_state:
    st.session_state["historia_czatu"] = []

# =========================================================
# AUTO-WYKRYWANIE TRYBU GŁOSOWEGO
# =========================================================
try:
    import speech_recognition as sr
    GLOS_OK = True
except Exception:
    GLOS_OK = False

# =========================================================
# PANEL BOCZNY
# =========================================================
st.sidebar.header("⚙️ Ustawienia AI i rynku")

wybrany_model = st.sidebar.selectbox(
    "Model OpenAI:",
    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    index=0
)

domyslny_rynek = st.sidebar.selectbox(
    "Domyślny rynek:",
    ["USA", "GPW", "MIX"],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.info(
    "Format tickerów:\n"
    "- GPW: STX, PKO, CDR (skrypt sam doda .WA)\n"
    "- USA: AAPL, TSLA, NVDA\n"
    "- Groszówki USA: np. ZOM, SNDL"
)

# =========================================================
# FUNKCJE POMOCNICZE
# =========================================================
def normalizuj_ticker(ticker: str, rynek_domyslny: str = "USA") -> str:
    t = ticker.upper().strip()
    if "." in t:
        return t
    if rynek_domyslny == "GPW":
        return f"{t}.WA"
    if rynek_domyslny == "USA":
        return t
    if len(t) <= 4:
        return f"{t}.WA"
    return t


def bezpieczna_wartosc(val, fallback=None):
    return fallback if val is None else val


def wyciagnij_ticker_z_tekstu(tekst: str) -> Optional[str]:
    """
    Bardzo prosta heurystyka:
    - szukamy tokenów z kropką (np. HRT.WA, STX.WA)
    - jeśli brak, bierzemy ostatni "słowo" złożone z liter/cyfr o długości 2–6
    """
    raw = tekst.replace(",", " ").replace(":", " ").replace(";", " ")
    tokens = [t.strip().upper() for t in raw.split() if t.strip()]
    # najpierw coś z kropką
    for tok in tokens:
        if "." in tok and len(tok) >= 3:
            return tok
    # potem czyste tickery
    kandydaci = [t for t in tokens if t.isalnum() and 2 <= len(t) <= 6]
    if kandydaci:
        return kandydaci[-1]
    return None

# =========================================================
# WSKAŹNIKI TECHNICZNE + TREND + SL/TP
# =========================================================
def oblicz_wskazniki(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["RSI14"] = 100 - (100 / (1 + rs))

    exp1 = df["Close"].ewm(span=12).mean()
    exp2 = df["Close"].ewm(span=26).mean()
    df["MACD"] = exp1 - exp2
    df["Signal_Line"] = df["MACD"].ewm(span=9).mean()

    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()

    cena = df["Close"].iloc[-1]
    ema20 = df["EMA20"].iloc[-1]
    ema50 = df["EMA50"].iloc[-1]

    if cena > ema20 > ema50:
        trend = "Silny Trend Wzrostowy"
    elif cena < ema20 < ema50:
        trend = "Silny Trend Spadkowy"
        # else:
    else:
        trend = "Konsolidacja / brak wyraźnego trendu"

    atr = df["ATR14"].iloc[-1]
    if pd.isna(atr):
        atr = cena * 0.02

    if trend == "Silny Trend Wzrostowy":
        sl = cena - 2 * atr
        tp = cena + 4 * atr
    elif trend == "Silny Trend Spadkowy":
        sl = cena + 2 * atr
        tp = cena - 4 * atr
    else:
        sl = cena * 0.95
        tp = cena * 1.10

    df.attrs["trend"] = trend
    df.attrs["sl"] = float(sl)
    df.attrs["tp"] = float(tp)

    return df

# =========================================================
# ANALIZA POJEDYNCZEJ SPÓŁKI
# =========================================================
def analizuj_spolke(ticker: str, rynek_domyslny: str = "USA") -> Dict[str, Any] | None:
    norm = normalizuj_ticker(ticker, rynek_domyslny)
    t_obj = yf.Ticker(norm)

    try:
        df = t_obj.history(period="1y")
    except Exception:
        return None

    if df.empty:
        if not norm.endswith(".WA"):
            t_obj = yf.Ticker(f"{ticker.upper().strip()}.WA")
            df = t_obj.history(period="1y")
            if df.empty:
                return None
        else:
            return None

    df = df.reset_index()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df["Date_str"] = df["Date"].dt.strftime("%Y-%m-%d")
    else:
        df["Date_str"] = range(len(df))

    df = oblicz_wskazniki(df)

    info = {}
    try:
        info = t_obj.info
    except Exception:
        info = {}

    cena = bezpieczna_wartosc(info.get("regularMarketPrice"), df["Close"].iloc[-1])
    wolumen = bezpieczna_wartosc(info.get("regularMarketVolume"), df["Volume"].iloc[-1])
    otwarcie = bezpieczna_wartosc(info.get("regularMarketOpen"), df["Open"].iloc[-1])
    max_dzis = bezpieczna_wartosc(info.get("regularMarketDayHigh"), df["High"].iloc[-1])
    min_dzis = bezpieczna_wartosc(info.get("regularMarketDayLow"), df["Low"].iloc[-1])

    fundamenty = {
        "ticker": norm,
        "cena": float(cena),
        "wolumen": int(wolumen) if wolumen and not pd.isna(wolumen) else None,
        "otwarcie": float(otwarcie),
        "max_dzis": float(max_dzis),
        "min_dzis": float(min_dzis),
        "kapitalizacja": info.get("marketCap"),
        "przychody": info.get("totalRevenue"),
        "zysk_netto": info.get("netIncomeToCommon"),
        "dlug_do_kapitalu": info.get("debtToEquity"),
        "dywidenda": (info.get("dividendYield") or 0) * 100,
        "pe": info.get("trailingPE"),
        "pb": info.get("priceToBook"),
        "trend": df.attrs["trend"],
        "sl": df.attrs["sl"],
        "tp": df.attrs["tp"],
        "rsi": float(df["RSI14"].iloc[-1]),
        "macd": float(df["MACD"].iloc[-1]),
        "signal": float(df["Signal_Line"].iloc[-1]),
        "ema20": float(df["EMA20"].iloc[-1]),
        "ema50": float(df["EMA50"].iloc[-1]),
    }

    return {"df": df, "fundamenty": fundamenty}

# =========================================================
# SKANER MOMENTUM
# =========================================================
def skaner_momentum(lista_tickerow: List[str], rynek_domyslny: str = "USA") -> pd.DataFrame:
    wyniki = []
    for t in lista_tickerow:
        norm = normalizuj_ticker(t, rynek_domyslny)
        try:
            df = yf.Ticker(norm).history(period="3mo")
        except Exception:
            continue
        if df.empty:
            continue
        df = df.reset_index()
        df = oblicz_wskazniki(df)
        close_now = df["Close"].iloc[-1]
        close_prev = df["Close"].iloc[0]
        zmiana = (close_now / close_prev - 1) * 100
        rsi = df["RSI14"].iloc[-1]
        trend = df.attrs["trend"]
        wyniki.append(
            {
                "Ticker": norm,
                "Zmiana_%": round(zmiana, 2),
                "RSI14": round(rsi, 2),
                "Trend": trend,
            }
        )
        time.sleep(0.1)
    if not wyniki:
        return pd.DataFrame()
    return pd.DataFrame(wyniki).sort_values("Zmiana_%", ascending=False)

# =========================================================
# SKANER WOLUMENOWY
# =========================================================
def skaner_wolumenowy(lista_tickerow: List[str], rynek_domyslny: str = "USA") -> pd.DataFrame:
    wyniki = []
    for t in lista_tickerow:
        norm = normalizuj_ticker(t, rynek_domyslny)
        try:
            df = yf.Ticker(norm).history(period="1mo")
        except Exception:
            continue
        if df.empty:
            continue
        sr_vol = df["Volume"].rolling(10).mean().iloc[-1]
        vol_now = df["Volume"].iloc[-1]
        if sr_vol == 0 or pd.isna(sr_vol):
            continue
        rel = vol_now / sr_vol
        wyniki.append(
            {
                "Ticker": norm,
                "Wolumen_aktualny": int(vol_now),
                "Śr_wolumen_10": int(sr_vol),
                "Relacja": round(rel, 2),
            }
        )
        time.sleep(0.1)
    if not wyniki:
        return pd.DataFrame()
    return pd.DataFrame(wyniki).sort_values("Relacja", ascending=False)

# =========================================================
# HEATMAPA RYNKU
# =========================================================
def heatmapa_rynku(lista_tickerow: List[str], rynek_domyslny: str = "USA") -> pd.DataFrame:
    wyniki = []
    for t in lista_tickerow:
        norm = normalizuj_ticker(t, rynek_domyslny)
        try:
            df = yf.Ticker(norm).history(period="5d")
        except Exception:
            continue
        if df.empty:
            continue
        close_now = df["Close"].iloc[-1]
        close_prev = df["Close"].iloc[0]
        zmiana = (close_now / close_prev - 1) * 100
        wyniki.append(
            {
                "Ticker": norm,
                "Zmiana_5d_%": round(zmiana, 2),
            }
        )
        time.sleep(0.05)
    if not wyniki:
        return pd.DataFrame()
    return pd.DataFrame(wyniki).sort_values("Zmiana_5d_%", ascending=False)

# =========================================================
# AI RAPORT ULTRA
# =========================================================
def ai_raport_ultra(f: Dict[str, Any]) -> str:
    prompt = f"""
DANE WEJŚCIOWE SPÓŁKI:
Ticker: {f['ticker']}
Cena: {f['cena']}
Trend: {f['trend']}
RSI(14): {f['rsi']}
MACD: {f['macd']}
Signal: {f['signal']}
Wolumen: {f['wolumen']}
SL: {f['sl']}
TP: {f['tp']}
P/E: {f['pe']}
P/B: {f['pb']}
Dywidenda: {f['dywidenda']}
Kapitalizacja: {f['kapitalizacja']}
Przychody: {f['przychody']}
Zysk netto: {f['zysk_netto']}
Dług/kapitał: {f['dlug_do_kapitalu']}

Na podstawie powyższych danych wygeneruj pełny, techniczny RAPORT ULTRA według struktury:

1. TREND I STRUKTURA RUCHU CENY
2. MOMENTUM I OSCYLATORY (RSI, MACD)
3. FUNDAMENTY I JAKOŚĆ SPÓŁKI
4. RYZYKO, ZMIENNOŚĆ I ZACHOWANIE CENY
5. FORMACJE I STRUKTURA TECHNICZNA (KONCEPTUALNIE)
6. KONTEKST RYNKU SZEROKIEGO (HIPOTEZA)
7. SCORING 0–100 I PEWNOŚĆ WERDYKTU
8. WNIOSEK INWESTYCYJNY – 3 PROFILE INWESTORA

Wymagania:
- Pisz po polsku.
- Styl: profesjonalny, konkretny, techniczny.
- Zero lania wody, zero ogólników.
- Nie powtarzaj tych samych zdań innymi słowami.
"""
    odp = client.chat.completions.create(
        model=wybrany_model,
        messages=[
            {"role": "system", "content": AI_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.12,
    )
    return odp.choices[0].message.content

# =========================================================
# STREAMING ODPOWIEDZI
# =========================================================
def ai_stream(model, messages, temperature=0.4):
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=True
    )
    full = ""
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            full += chunk.choices[0].delta.content
            yield chunk.choices[0].delta.content
    return full

# =========================================================
# UI – ZAKŁADKI
# =========================================================
zakladki = st.tabs([
    "📈 Pojedyncza spółka",
    "🔥 Raport ULTRA",
    "📊 Skanery",
    "🗺️ Heatmapa rynku",
    "💬 Asystent AI"
])

# ---------------------------------------------------------------------
# ZAKŁADKA 1 – POJEDYNCZA SPÓŁKA
# ---------------------------------------------------------------------
with zakladki[0]:
    st.subheader("📈 Analiza pojedynczej spółki")

    col1, col2 = st.columns([2, 1])
    with col1:
        ticker_input = st.text_input("Ticker spółki:", "AAPL")
    with col2:
        rynek_input = st.selectbox("Rynek dla tego tickera:", ["USA", "GPW", "MIX"], index=0)

    if st.button("Analizuj spółkę", type="primary"):
        wyniki = analizuj_spolke(ticker_input, rynek_input)

        if not wyniki:
            st.error("Nie udało się pobrać danych dla podanego tickera.")
        else:
            df = wyniki["df"]
            f = wyniki["fundamenty"]

            st.session_state["ostatnia_spolka"] = f

            st.markdown(f"### {f['ticker']} – dane rynkowe i wskaźniki")

            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Cena", f"{f['cena']:.2f}")
            col_b.metric("Trend", f["trend"])
            col_c.metric("RSI(14)", f"{f['rsi']:.2f}")
            col_d.metric("MACD vs Signal", f"{f['macd']:.4f} / {f['signal']:.4f}")

            fig = go.Figure()
            fig.add_trace(
                go.Candlestick(
                    x=df["Date_str"],
                    open=df["Open"],
                    high=df["High"],
                    low=df["Low"],
                    close=df["Close"],
                    name="Cena",
                )
            )
            fig.add_trace(go.Scatter(x=df["Date_str"], y=df["EMA20"], name="EMA20", line=dict(color="orange")))
            fig.add_trace(go.Scatter(x=df["Date_str"], y=df["EMA50"], name="EMA50", line=dict(color="blue")))
            fig.update_layout(height=500, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### Podstawowe fundamenty")
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            col_f1.metric("P/E", f"{f['pe']}" if f["pe"] is not None else "brak")
            col_f2.metric("P/B", f"{f['pb']}" if f["pb"] is not None else "brak")
            col_f3.metric("Dywidenda %", f"{f['dywidenda']:.2f}")
            col_f4.metric("Wolumen", f"{f['wolumen']}")

            st.markdown("#### Poziomy systemowe SL / TP")
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("SL", f"{f['sl']:.3f}")
            col_s2.metric("TP", f"{f['tp']:.3f}")
            rr = (f["tp"] - f["cena"]) / (f["cena"] - f["sl"]) if f["cena"] != f["sl"] else None
            col_s3.metric("R/R (TP:SL)", f"{rr:.2f}" if rr is not None else "n/d")

# ---------------------------------------------------------------------
# ZAKŁADKA 2 – RAPORT ULTRA
# ---------------------------------------------------------------------
with zakladki[1]:
    st.subheader("🔥 Raport inwestycyjny AI – tryb ULTRA")

    ticker_ultra = st.text_input("Ticker do raportu ULTRA:", "AAPL", key="ticker_ultra")
    rynek_ultra = st.selectbox("Rynek:", ["USA", "GPW", "MIX"], index=0, key="rynek_ultra")

    if st.button("Generuj Raport ULTRA", type="primary"):
        wyniki = analizuj_spolke(ticker_ultra, rynek_ultra)
        if not wyniki:
            st.error("Nie udało się pobrać danych dla podanego tickera.")
        else:
            f = wyniki["fundamenty"]
            with st.spinner("Generuję raport ULTRA..."):
                raport = ai_raport_ultra(f)
            st.markdown("### Raport ULTRA")
            st.write(raport)

# ---------------------------------------------------------------------
# ZAKŁADKA 3 – SKANERY
# ---------------------------------------------------------------------
with zakladki[2]:
    st.subheader("📊 Skanery rynku")

    st.markdown("#### Lista tickerów do skanowania (oddzielone przecinkami)")
    tickery_skan = st.text_area(
        "Tickery:",
        "AAPL, MSFT, NVDA, TSLA, META, AMZN",
        height=80,
    )
    rynek_skan = st.selectbox("Rynek dla skanerów:", ["USA", "GPW", "MIX"], index=0, key="rynek_skan")

    lista = [t.strip() for t in tickery_skan.split(",") if t.strip()]

    col_skan1, col_skan2 = st.columns(2)

    with col_skan1:
        if st.button("Skaner Momentum"):
            if not lista:
                st.warning("Podaj przynajmniej jeden ticker.")
            else:
                with st.spinner("Skanuję momentum..."):
                    df_mom = skaner_momentum(lista, rynek_skan)
                if df_mom.empty:
                    st.info("Brak wyników.")
                else:
                    st.dataframe(df_mom, use_container_width=True)

    with col_skan2:
        if st.button("Skaner Wolumenowy"):
            if not lista:
                st.warning("Podaj przynajmniej jeden ticker.")
            else:
                with st.spinner("Skanuję wolumen..."):
                    df_vol = skaner_wolumenowy(lista, rynek_skan)
                if df_vol.empty:
                    st.info("Brak wyników.")
                else:
                    st.dataframe(df_vol, use_container_width=True)

# ---------------------------------------------------------------------
# ZAKŁADKA 4 – HEATMAPA RYNKU
# ---------------------------------------------------------------------
with zakladki[3]:
    st.subheader("🗺️ Heatmapa rynku (prosta zmiana % 5d)")

    tickery_heat = st.text_area(
        "Tickery do heatmapy:",
        "AAPL, MSFT, NVDA, TSLA, META, AMZN",
        height=80,
        key="tickery_heat",
    )
    rynek_heat = st.selectbox("Rynek:", ["USA", "GPW", "MIX"], index=0, key="rynek_heat")

    lista_heat = [t.strip() for t in tickery_heat.split(",") if t.strip()]

    if st.button("Generuj heatmapę"):
        if not lista_heat:
            st.warning("Podaj przynajmniej jeden ticker.")
        else:
            with st.spinner("Pobieram dane do heatmapy..."):
                df_heat = heatmapa_rynku(lista_heat, rynek_heat)
            if df_heat.empty:
                st.info("Brak wyników.")
            else:
                st.dataframe(df_heat, use_container_width=True)

# ---------------------------------------------------------------------
# ZAKŁADKA 5 – ASYSTENT AI
# ---------------------------------------------------------------------
with zakladki[4]:
    st.subheader("💬 Asystent AI – rozmowa jak z analitykiem")

    for msg in st.session_state["historia_czatu"]:
        if msg["role"] == "user":
            st.markdown(f"**Ty:** {msg['content']}")
        elif msg["role"] == "assistant":
            st.markdown(f"**AI:** {msg['content']}")

    st.markdown("---")

    use_memory = st.checkbox("Użyj pamięci AI (zapamiętane preferencje)")

    user_msg = st.text_input("Napisz wiadomość:", "", key="czat_input")

    if GLOS_OK:
        if st.button("🎤 Nagraj głos"):
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                st.info("Mów…")
                audio = recognizer.listen(source)
            try:
                user_msg = recognizer.recognize_google(audio, language="pl-PL")
                st.success(f"Rozpoznano: {user_msg}")
            except Exception:
                st.error("Nie udało się rozpoznać głosu.")
                user_msg = ""
    else:
        st.info("🎤 Tryb głosowy niedostępny (brak modułu SpeechRecognition).")

    if user_msg.lower().startswith("zapamiętaj:"):
        st.session_state["ai_memory"].append(user_msg[11:].strip())
        st.success("Preferencja zapamiętana.")
        st.stop()

    if st.button("Wyślij", type="primary"):
        if user_msg.strip():
            # AUTO-ANALIZA TICKERA Z WIADOMOŚCI
            tick = wyciagnij_ticker_z_tekstu(user_msg)
            if tick:
                wyniki_auto = analizuj_spolke(tick, domyslny_rynek)
                if wyniki_auto:
                    st.session_state["ostatnia_spolka"] = wyniki_auto["fundamenty"]

            messages = [{"role": "system", "content": AI_SYSTEM}]

            if use_memory and st.session_state.get("ai_memory"):
                messages.append({
                    "role": "system",
                    "content": "Zapamiętane preferencje użytkownika: " + str(st.session_state["ai_memory"])
                })

            if st.session_state.get("ostatnia_spolka"):
                f = st.session_state["ostatnia_spolka"]
                kontekst = f"""
ANALIZA SPÓŁKI — PEŁNY KONTEKST:

Ticker: {f['ticker']}
Cena: {f['cena']}
Trend: {f['trend']}
RSI(14): {f['rsi']}
MACD: {f['macd']}
Signal: {f['signal']}
Wolumen: {f['wolumen']}

Poziomy systemowe:
SL: {f['sl']}
TP: {f['tp']}

Fundamenty:
P/E: {f['pe']}
P/B: {f['pb']}
Dywidenda: {f['dywidenda']}

ZASADY:
- NIE pisz, że nie masz dostępu do danych.
- NIE opisuj spółki encyklopedycznie.
- NIE odsyłaj do Yahoo, Google, Bloomberg itd.
- Analizuj TYLKO na podstawie powyższych danych.
- Zachowuj się jak profesjonalny analityk techniczny i fundamentalny.
- Podawaj sygnały, scenariusze, poziomy, ryzyka i rekomendacje.
"""
                messages.append({"role": "system", "content": kontekst})

            messages += st.session_state["historia_czatu"]
            messages.append({"role": "user", "content": user_msg})
            st.session_state["historia_czatu"].append({"role": "user", "content": user_msg})

            st.markdown("**AI pisze…**")
            placeholder = st.empty()
            full_answer = ""

            for fragment in ai_stream(wybrany_model, messages):
                full_answer += fragment
                placeholder.markdown(f"**AI:** {full_answer}")

            st.session_state["historia_czatu"].append({
                "role": "assistant",
                "content": full_answer
            })

            st.rerun()

    if st.button("Wyczyść czat"):
        st.session_state["historia_czatu"] = []
        st.rerun()
