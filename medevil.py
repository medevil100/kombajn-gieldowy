import time
import threading
import requests
import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
from openai import OpenAI
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# =====================================================================
# INTERFEJS GRAFICZNY STREAMLIT
# =====================================================================
st.set_page_config(page_title="Snajper Rynkowy Custom", page_icon="🎯", layout="wide")
st.title("🎯 Twój Autorski Skaner Groszówek: Market Sniper")

if "alerts_history" not in st.session_state:
    st.session_state.alerts_history = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nie skanowano"
if "last_scanned_tickers" not in st.session_state:
    st.session_state.last_scanned_tickers = []

# =====================================================================
# WCZYTYWANIE PARAMETRÓW Z TWOJEGO DZIAŁAJĄCEGO SECRETS.TOML
# =====================================================================
try:
    TELEGRAM_TOKEN = st.secrets.get("telegram_token") or st.secrets.get("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = st.secrets.get("telegram_id") or st.secrets.get("TELEGRAM_CHAT_ID") or st.secrets.get("telegram_chat_id")
    OPENAI_API_KEY = st.secrets.get("openai_key") or st.secrets.get("OPENAI_API_KEY")
    
    INTERVAL = st.secrets.get("interval") or "15m"
    VOLUME_THRESHOLD = float(st.secrets.get("volume_threshold") or 3.5)
    PRICE_THRESHOLD = float(st.secrets.get("price_threshold") or 2.0)
    MAX_PRICE_PLN = float(st.secrets.get("max_price_pln") or 165.0)
    MAX_PRICE_USD = float(st.secrets.get("max_price_usd") or 5.0)
    
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        raise KeyError("Brak kluczowych zmiennych autoryzacyjnych w secrets.toml")
except Exception as e:
    st.error(f"❌ Błąd kluczy w secrets.toml: {e}")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# DYNAMICZNE OKNO NA TWOJE TICKERY
# =====================================================================
st.subheader("📝 Zarządzanie Twoją Listą Obserwacyjną")
domyslna_lista = "APS.WA, STX.WA"
user_input = st.text_area(
    "Wklej tutaj swoje spółki rozdzielone przecinkami (USA lub GPW z końcówką .WA):",
    value=domyslna_lista,
    height=100
)

MARKET_DATABASE = [t.strip().upper() for t in user_input.split(",") if t.strip()]

# SUWAKI DO KONTROLI PARAMETRÓW W LOCIE (Zintegrowane z Twoim szkieletem)
col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    ui_interval = st.selectbox("Interwał świecy:", ["1m", "5m", "15m", "30m", "1h"], index=3)
with col_p2:
    ui_vol_threshold = st.slider("Próg skoku obrotu (x średniej):", 1.0, 10.0, VOLUME_THRESHOLD, step=0.5)
with col_p3:
    ui_price_threshold = st.slider("Próg wzrostu ceny (%):", 0.1, 5.0, PRICE_THRESHOLD, step=0.1)

# =====================================================================
# MODUŁ KOMUNIKACJI I MATEMATYKI RSI
# =====================================================================
def send_telegram_message(message):
    czysty_token = str(TELEGRAM_TOKEN).strip()
    url = f"https://telegram.org{czysty_token}/sendMessage"
    payload = {"chat_id": str(TELEGRAM_CHAT_ID).strip(), "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=5)
    except Exception: pass

def oblicz_rsi(df, period=14):
    try:
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception: return None

def generuj_komentarz_ai(ticker, price, volume, change, rsi, waluta):
    try:
        prompt = (
            f"Jesteś profesjonalnym traderem akcji (Long). Spółka {ticker} wygenerowała sygnał wzrostowy: "
            f"cena {float(price):.2f} {waluta}, wzrost o +{float(change):.2f}%, wolumen {float(volume):.1f}x ponad średnią, RSI {float(rsi):.1f}. "
            f"Napisz jedno bardzo krótkie zdanie techniczne (max 10 słów) podsumowania okazji i uzasadnienia wejścia pod trend."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=35, temperature=0.7
        )
        return response.choices.message.content.strip()
    except Exception: return "Wykryto nagły skok momentum rynkowego."

# =====================================================================
# ROZBUDOWANA ANALIZA AKCJI (ŚCIŚLE LONG - SL NA DOLE)
# =====================================================================
def analizuj_jedna_spolke(ticker, now):
    try:
        df = yf.download(ticker, period="5d", interval=ui_interval, progress=False)
        if df.empty or len(df) < 15: return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        df['RSI'] = oblicz_rsi(df)
        ostatnia_swieca = df.iloc[-1]
        poprzednia_swieca = df.iloc[-2]
        
        def do_float(val):
            return float(val.iloc) if isinstance(val, pd.Series) else float(val)

        aktualna_cena = do_float(ostatnia_swieca['Close'])
        cena_zamkniecia_poprzednia = do_float(poprzednia_swieca['Close'])
        current_rsi = do_float(ostatnia_swieca['RSI'])
        
        if aktualna_cena <= 0 or pd.isna(current_rsi): return None
            
        is_gpw = ticker.endswith(".WA")
        waluta = "PLN" if is_gpw else "USD"
        
        # Filtry odcinające drogie akcje
        if is_gpw and aktualna_cena > MAX_PRICE_PLN: return None
        if not is_gpw and aktualna_cena > MAX_PRICE_USD: return None
            
        zmiana_ceny = ((aktualna_cena - cena_zamkniecia_poprzednia) / cena_zamkniecia_poprzednia) * 100
        aktualny_wolumen = do_float(ostatnia_swieca['Volume'])
        sredni_wolumen = do_float(df['Volume'].mean())
        
        if sredni_wolumen == 0: return None
        skok_wolumenu = aktualny_wolumen / sredni_wolumen
        
        # Ocena trendu i generowanie statusu
        sygnal_techniczny = (zmiana_ceny >= ui_price_threshold and skok_wolumenu >= ui_vol_threshold)
        rsi_bezpieczny = (30.0 <= current_rsi <= 70.0)
        
        sygnal_trafiony = sygnal_techniczny and rsi_bezpieczny
        
        if sygnal_trafiony:
            ocena_trendu = "🟢 Kupuj (Up)"
            sort_score = 3  # Najwyższy priorytet do sortowania
        elif zmiana_ceny > 0:
            ocena_trendu = "🟡 Trzymaj"
            sort_score = 2
        else:
            ocena_trendu = "🔴 Unikaj"
            sort_score = 1
            
        # POZYCJA LONG: Zabezpieczenie Stop Loss (SL) ZAWSZE NA DOLE (pod ceną zakupu)
        # Obliczamy dynamiczny bufor 5% na podstawie ceny akcji
        sl_na_dole = aktualna_cena * 0.95
        tp_na_gorze = aktualna_cena * 1.15
        
        ticker_info = {
            "Ticker": ticker, 
            "Cena": f"{aktualna_cena:.2f} {waluta}",
            "Zmiana %": round(zmiana_ceny, 2),
            "Wolumen (Multiplier)": f"{skok_wolumenu:.2f}x",
            "RSI": f"{current_rsi:.1f}", 
            "Stop Loss (SL na dole)": f"{sl_na_dole:.2f} {waluta}",
            "Take Profit (TP)": f"{tp_na_gorze:.2f} {waluta}",
            "Status / Ocena": ocena_trendu, 
            "Sygnał": sygnal_trafiony,
            "score": sort_score
        }
        
        if sygnal_trafiony:
            komentarz = generuj_komentarz_ai(ticker, aktualna_cena, skok_wolumenu, zmiana_ceny, current_rsi, waluta)
            alert_text = (
                f"🟢 *REALNA OKAZJA RYNKOWA:* `{ticker}`\n"
                f"💰 Cena: {aktualna_cena:.2f} {waluta}\n"
                f"📈 Zmiana: +{zmiana_ceny:.2f}%\n"
                f"📊 Wolumen: {skok_wolumenu:.1f}x ponad średnią\n"
                f"🛡️ Wskaźnik RSI: `{current_rsi:.1f}` (Strefa Bezpieczna)\n"
                f"🛑 Obrona (SL na dole): {sl_na_dole:.2f} {waluta}\n"
                f"🤖 *AI:* {komentarz}"
            )
            send_telegram_message(alert_text)
            
            ticker_info["Alert_Data"] = {
                "Czas": now, "Ticker": ticker, "Cena": f"{aktualna_cena:.2f} {waluta}",
                "Zmiana": f"+{zmiana_ceny:.2f}%", "Wolumen": f"{skok_wolumenu:.1f}x", "RSI": f"{current_rsi:.1f}", "Komentarz AI": komentarz
            }
        return ticker_info
    except Exception: 
        pass
    return None

def job_skanera(status_placeholder=None, progress_bar=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_scan_time = now
    
    total_spolki = len(MARKET_DATABASE)
    lista_podgladu = []
    przetworzone = 0

    if total_spolki == 0:
        if status_placeholder: status_placeholder.error("❌ Lista spółek obserwowanych jest pusta.")
        return

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(analizuj_jedna_spolke, ticker, now): ticker for ticker in MARKET_DATABASE}
        for future in as_completed(futures):
            res = future.result()
            if res:
                lista_podgladu.append(res)
                if res.get("Sygnał") and "Alert_Data" in res:
                    st.session_state.alerts_history.append(res["Alert_Data"])
            przetworzone += 1
            if progress_bar: progress_bar.progress(przetworzone / total_spolki)
                
    st.session_state.last_scanned_tickers = lista_podgladu

# =====================================================================
# STEROWANIE RADAREM
# =====================================================================
st.sidebar.header("⏱️ Sterowanie Radarem")
auto_scan = st.sidebar.selectbox("Automatyczne odświeżanie:", ["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"])

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    uruchom_skan = st.button("🚀 Uruchom Skaner")
with col_btn2:
    if st.button("🗑️ Wyczyść Historię"):
        st.session_state.alerts_history = []
        st.rerun()

st.sidebar.info(f"⏱️ Ostatni udany skan: {st.session_state.last_scan_time}")

status_ph = st.empty()
prog_bar = st.empty()

if uruchom_skan:
    status_ph.write("⌛ Trwa pobieranie i analiza danych giełdowych...")
    prog_bar.progress(0)
    job_skanera(status_ph, prog_bar)
    status_ph.success(f"⚙️ Status: Wielowątkowy radar aktywny | Ostatni skan: {st.session_state.last_scan_time}")

# Wyświetlanie rozbudowanej i posortowanej tabeli Live
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd aktualnego cyklu skanowania (Posortowany)")
    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)
    
    # SORTOWANIE: Układamy tabelę od "Kupuj" do "Unikaj" przy użyciu wewnętrznego 'score'
    if "score" in df_wyniki.columns:
        df_wyniki = df_wyniki.sort_values(by="score", ascending=False)
        df_wyniki = df_wyniki.drop(columns=["score"])
        
    if "Sygnał" in df_wyniki.columns: 
        df_wyniki = df_wyniki.drop(columns=["Sygnał"])
    if "Alert_Data" in df_wyniki.columns: 
        df_wyniki = df_wyniki.drop(columns=["Alert_Data"])
        
    st.dataframe(df_wyniki, use_container_width=True)

if st.session_state.alerts_history:
    st.subheader("📋 Zapamiętane Okazje Snajperskie (Zielone Alerty 🟢)")
    st.dataframe(pd.DataFrame(st.session_state.alerts_history), use_container_width=True)

# Natywny i bezpieczny re-run lokalny w PowerShellu
if auto_scan == "Co 1 minutę":
    time.sleep(60)
    st.rerun()
elif auto_scan == "Co 5 minut":
    time.sleep(300)
    st.rerun()
elif auto_scan == "Co 15 minut":
    time.sleep(900)
    st.rerun()
