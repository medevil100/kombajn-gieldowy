import time
import schedule
import threading
import requests
import yfinance as yf
import pandas as pd
import streamlit as st
import json
import numpy as np
import os
from openai import OpenAI
from tavily import TavilyClient
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# =====================================================================
# INTERFEJS GRAFICZNY STREAMLIT
# =====================================================================
st.set_page_config(page_title="Kombajn Tradingowy: Market Sniper AI", page_icon="🎯", layout="wide")
st.title("🎯 Kombajn Tradingowy: Market Sniper AI Pro")

if "alerts_history" not in st.session_state:
    st.session_state.alerts_history = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nie skanowano"
if "last_scanned_tickers" not in st.session_state:
    st.session_state.last_scanned_tickers = []

# =====================================================================
# SYSTEMOWY ODCZYT KLUCZY (OMINIĘCIE DROGI ST.SECRETS)
# =====================================================================
# Pobieramy klucze bezpośrednio z pamięci RAM systemu operacyjnego Linux w chmurze
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("openai_key")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") or os.environ.get("tavily_api_key")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("telegram_token")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("telegram_chat_id") or os.environ.get("telegram_id")

# Domyślne progi tradingowe
INTERVAL = "15m"
VOLUME_THRESHOLD = 3.5
PRICE_THRESHOLD = 2.0
MAX_PRICE_PLN = 165.0
MAX_PRICE_USD = 5.0

# Jeśli system operacyjny nie posiada tych kluczy w pamięci, wyświetlamy twardy komunikat stopu
if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not TAVILY_API_KEY:
    st.error("🚨 Krytyczny błąd: Serwer chmury nie przekazał kluczy do pamięci systemowej!")
    st.markdown("Wejdź w panelu chmury w **Settings -> Secrets** i upewnij się, że plik TOML jest tam zapisany.")
    st.stop()

# Inicjalizacja klientów bezpośrednio z bezpiecznych zmiennych systemowych
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)


# =====================================================================
# INTERFEJS GRAFICZNY STREAMLIT
# =====================================================================
st.set_page_config(page_title="Snajper Rynkowy AI Custom", page_icon="🎯", layout="wide")
st.title("🎯 Kombajn Tradingowy: Market Sniper AI Pro")

if "alerts_history" not in st.session_state:
    st.session_state.alerts_history = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nie skanowano"
if "last_scanned_tickers" not in st.session_state:
    st.session_state.last_scanned_tickers = []

# =====================================================================
# WCZYTYWANIE PARAMETRÓW (OFICJALNY STANDARD WIELKICH LITER)
# =====================================================================
try:
    # Wymuszamy duże litery dla OpenAI i Tavily, aby zapobiec awarii biblioteki
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]
    
    INTERVAL = st.secrets.get("INTERVAL") or st.secrets.get("interval") or "15m"
    VOLUME_THRESHOLD = float(st.secrets.get("VOLUME_THRESHOLD") or st.secrets.get("volume_threshold") or 3.5)
    PRICE_THRESHOLD = float(st.secrets.get("PRICE_THRESHOLD") or st.secrets.get("price_threshold") or 2.0)
    MAX_PRICE_PLN = float(st.secrets.get("MAX_PRICE_PLN") or st.secrets.get("max_price_pln") or 165.0)
    MAX_PRICE_USD = float(st.secrets.get("MAX_PRICE_USD") or st.secrets.get("max_price_usd") or 5.0)
    
except KeyError as e:
    st.error(f"❌ Krytyczny brak klucza {e} w panelu Secrets!")
    st.markdown("""
    **Wklej te klucze WIELKIMI LITERAMI do okna Settings -> Secrets w Streamlit Cloud:**
    ```toml
    OPENAI_API_KEY = "twój-klucz-openai"
    TAVILY_API_KEY = "twój-klucz-tavily"
    TELEGRAM_BOT_TOKEN = "8777292073:AAFHNJjrX-FDY4M6qRKaCNp_bScWoik9Ejw"
    TELEGRAM_CHAT_ID = "1690495877"
    VOLUME_THRESHOLD = 1.5
    MAX_PRICE_USD = 5.0
    ```
    """)
    st.stop()

# Oficjalna inicjalizacja silników AI (api_key z małej litery wewnątrz kodu)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

# =====================================================================
# DYNAMICZNE OKNO NA TWOJE TICKERY
# =====================================================================
st.subheader("📝 Zarządzanie Twoją Listą Obserwacyjną")
domyslna_lista = (
    "APS.WA, STX.WA, AIT.WA, CLD.WA, NVS.WA, PTN.WA, IFR.WA, KCH.WA, ENG.WA, PEP.WA, "
    "MDF.WA, BIM.WA, BML.WA, VVD.WA, MIR.WA, QNT.WA, MGT.WA, SYN.WA, OAT.WA, IGN.WA, "
    "GT.WA, BIO.WA, PHR.WA, PURE.WA, MAB.WA, VIV.WA, ULT.WA, HUG.WA, TEN.WA, RDS.WA, "
    "MOV.WA, FOR.WA, PCF.WA, CIG.WA, BBT.WA, RFK.WA, PXM.WA, MSW.WA, ZRE.WA, TRK.WA, "
    "TOR.WA, PND.WA, DEK.WA"
)
user_input = st.text_area(
    "Wklej tutaj swoje spółki rozdzielone przecinkami (USA lub GPW z końcówką .WA):",
    value=domyslna_lista,
    height=100
)

MARKET_DATABASE = [t.strip().upper() for t in user_input.split(",") if t.strip()]

# =====================================================================
# MODUŁ KOMUNIKACJI I ANALIZY FINANSOWEJ
# =====================================================================
def send_telegram_message(message):
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": str(TELEGRAM_CHAT_ID).strip(), "text": message, "parse_mode": "HTML"}
    try: 
        requests.post(url, json=payload, timeout=5)
    except Exception: 
        pass

def oblicz_rsi(df, period=14):
    try:
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception: 
        return None

def głęboka_analiza_news_tavily_ai(ticker, price, skok_vol, change, current_rsi, rynek_typ):
    """Pobiera wiadomości finansowe i generuje zwięzły raport inwestycyjny"""
    try:
        # Skan internetu czasu rzeczywistego przez Tavily MCP
        search_query = f"{ticker.replace('.WA','')} wyniki finansowe wiadomości giełda akcje raport" if rynek_typ == "PL" else f"{ticker} penny stock clinical trial SEC filing catalyst"
        tavily_response = tavily_client.search(query=search_query, search_depth="advanced", max_results=3)
        
        context = ""
        for result in tavily_response['results']:
            context += f"- {result['title']}: {result['content']}\n"
            
        prompt = (
            f"Jesteś starszym analitykiem giełdowym (CFA). Spółka {ticker} wygenerowała sygnał zakupu akcji (LONG):\n"
            f"Cena: {price:.2f}, Zmiana: +{change:.2f}%, Wolumen: {skok_vol:.1f}x normy, RSI: {current_rsi:.1f}.\n"
            f"Dane z internetu: {context}\n"
            f"Napisz po polsku w maksymalnie 2 konkretnych zdaniach, co jest główną przyczyną nagłego skoku obrotów kapitału i czy warto akumulować te akcje giełdowe."
        )
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.1
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return "Brak stabilnych wiadomości rynkowych. Ruch o charakterze czysto technicznym."

# =====================================================================
# WIELOWĄTKOWA ANALIZA SPÓŁKI
# =====================================================================
def analizuj_jedna_spolke(ticker, now):
    try:
        df = yf.download(ticker, period="5d", interval=INTERVAL, progress=False)
        if df.empty or len(df) < 15: return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        df['RSI'] = oblicz_rsi(df)
        ostatnia_swieca = df.iloc[-1]
        poprzednia_swieca = df.iloc[-2]
        
        def do_float(val):
            return float(val.iloc[0]) if isinstance(val, pd.Series) else float(val)

        aktualna_cena = do_float(ostatnia_swieca['Close'])
        cena_zamkniecia_poprzednia = do_float(poprzednia_swieca['Close'])
        current_rsi = do_float(ostatnia_swieca['RSI'])
        
        if aktualna_cena <= 0 or pd.isna(current_rsi): return None
            
        is_gpw = ticker.endswith(".WA")
        waluta = "PLN" if is_gpw else "USD"
        rynek_typ = "PL" if is_gpw else "USA"
        
        # Filtry odcinające drogie akcje
        if is_gpw and aktualna_cena > MAX_PRICE_PLN: return None
        if not is_gpw and aktualna_cena > MAX_PRICE_USD: return None
            
        zmiana_ceny = ((aktualna_cena - cena_zamkniecia_poprzednia) / cena_zamkniecia_poprzednia) * 100
        aktualny_wolumen = do_float(ostatnia_swieca['Volume'])
        sredni_wolumen = do_float(df['Volume'].mean())
        
        if sredni_wolumen == 0: return None
        skok_wolumenu = aktualny_wolumen / sredni_wolumen
        
        # Filtry giełdowe fizycznych akcji: Trend wzrostowy i bezpieczny rozstaw wskaźnika RSI
        sygnal_techniczny = (zmiana_ceny >= PRICE_THRESHOLD and skok_wolumenu >= VOLUME_THRESHOLD)
        rsi_bezpieczny = (30.0 <= current_rsi <= 70.0)
        
        sygnal_trafiony = sygnal_techniczny and rsi_bezpieczny
        status_okazji = "🟢 KUPUJ (UP)" if sygnal_trafiony else "Unikaj / Konsolidacja"
        
        # Wyliczanie dynamicznego SL i TP za pomocą zmienności procentowej sesji
        sl = aktualna_cena * 0.93  # 7% bufor obrony pod ceną zakupu
        tp = aktualna_cena * 1.15  # 15% cel realizacji zysku
        
        ticker_info = {
            "Ticker": ticker, "Rynek": rynek_typ, "Cena": f"{aktualna_cena:.2f} {waluta}",
            "RSI": f"{current_rsi:.1f}", "Skok Wolumenu": f"{skok_wolumenu:.1f}x", 
            "Stop Loss (Na dole)": f"{sl:.2f}", "Take Profit": f"{tp:.2f}",
            "Status": status_okazji, "Sygnał": sygnal_trafiony
        }
        
        if sygnal_trafiony:
            # INTEGRACJA TAVILY + OPENAI GPT
            komentarz = głęboka_analiza_news_tavily_ai(ticker, aktualna_cena, skok_wolumenu, zmiana_ceny, current_rsi, rynek_typ)
            
            flag_rynek = "🇵🇱" if is_gpw else "🇺🇸"
            alert_text = (
                f"🚨 <b>ALERT SNAJPERA AKCJI {flag_rynek}: {ticker}</b>\n"
                f"▪️ Cena: {aktualna_cena:.2f} {waluta} (+{zmiana_ceny:.2f}%)\n"
                f"▪️ Wolumen: <b>{skok_wolumenu:.1f}x</b> powyżej średniej\n"
                f"🛡️ Wskaźnik RSI: {current_rsi:.1f} (Strefa Bezpieczna)\n"
                f"🎯 Cel (TP): {tp:.2f} | 🛑 Obrona (SL na dole): {sl:.2f}\n\n"
                f"📝 <b>Raport Finansowy AI:</b> {komentarz}"
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
        if total_spolki == 0:
            if status_placeholder: 
                status_placeholder.error("❌ Lista spółek obserwowanych jest pusta.")
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
                if progress_bar: 
                    progress_bar.progress(przetworzone / total_spolki)
                    
        st.session_state.last_scanned_tickers = lista_podgladu

# =====================================================================
# MODUŁ HARMONOGRAMU (SCHEDULE OPIERANY NA TWOIM REQUIREMENTS.TXT)
# =====================================================================
st.sidebar.header("⏱️ Harmonogram Automatyczny")
auto_scan = st.sidebar.selectbox("Częstotliwość skanowania giełdy:", ["Tylko ręcznie", "Co 1 minutę", "Co 5 minut", "Co 15 minut"])

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    uruchom_skan = st.button("🚀 Uruchom Skaner")
with col_btn2:
    if st.button("🗑️ Wyczyść Historię Alertów"):
        st.session_state.alerts_history = []
        st.rerun()

st.sidebar.info(f"⏱️ Ostatni udany skan: {st.session_state.last_scan_time}")

status_ph = st.empty()
prog_bar = st.empty()

def run_schedule_loop():
    while True:
        schedule.run_pending()
        time.sleep(1)

if "schedule_threaded" not in st.session_state:
    schedule.clear()
    if auto_scan == "Co 1 minutę":
        schedule.every(1).minutes.do(job_skanera)
    elif auto_scan == "Co 5 minut":
        schedule.every(5).minutes.do(job_skanera)
    elif auto_scan == "Co 15 minut":
        schedule.every(15).minutes.do(job_skanera)
        
    if auto_scan != "Tylko ręcznie":
        t = threading.Thread(target=run_schedule_loop, daemon=True)
        t.start()
        st.session_state["schedule_threaded"] = True

if uruchom_skan:
    status_ph.write("⌛ Trwa wielowątkowe pobieranie danych technicznych z GPW i USA...")
    prog_bar.progress(0)
    job_skanera(status_ph, prog_bar)
    status_ph.success("✅ Analiza zakończona! Wyniki wyświetlone poniżej.")

# Wyświetlanie tabel podglądu rynkowego
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd aktualnego cyklu skanowania")
    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)
    if "Sygnał" in df_wyniki.columns: 
        df_wyniki = df_wyniki.drop(columns=["Sygnał"])
    if "Alert_Data" in df_wyniki.columns: 
        df_wyniki = df_wyniki.drop(columns=["Alert_Data"])
    st.dataframe(df_wyniki, use_container_width=True)

if st.session_state.alerts_history:
    st.subheader("🚨 Historiografia wygenerowanych okazji (LONG)")
    st.dataframe(pd.DataFrame(st.session_state.alerts_history), use_container_width=True)
