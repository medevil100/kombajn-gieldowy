import streamlit as st
from openai import OpenAI
from tavily import TavilyClient
import json
import yfinance as yf
import datetime
import pandas as pd
import numpy as np
import requests
import time

# --- 1. INICJALIZACJA I KONFIGURACJA KLUCZY ---
st.set_page_config(page_title="Terminal Tradingowy AI Pro", layout="wide", page_icon="📈")

TG_TOKEN = "8777292073:AAFHNJjrX-FDY4M6qRKaCNp_bScWoik9Ejw"
TG_CHAT_ID = "1690495877"

try:
    TAVILY_KEY = st.secrets["TAVILY_API_KEY"]
    OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
except KeyError as e:
    st.error(f"🚨 Brak klucza {e} w panelu Secrets aplikacji Streamlit Cloud!")
    st.stop()

openai_client = OpenAI(api_key=OPENAI_KEY)
tavily_client = TavilyClient(api_key=TAVILY_KEY)

# --- 2. BAZA TICKERÓW ---
TICKERS_PL = [
    "APS.WA", "STX.WA", "AIT.WA", "CLD.WA", "NVS.WA", "PTN.WA", "IFR.WA", "KCH.WA", "ENG.WA", "PEP.WA",
    "MDF.WA", "BIM.WA", "BML.WA", "VVD.WA", "MIR.WA", "QNT.WA", "MGT.WA", "SYN.WA", "OAT.WA", "IGN.WA",
    "GT.WA", "BIO.WA", "PHR.WA", "PURE.WA", "MAB.WA", "VIV.WA", "ULT.WA", "HUG.WA", "TEN.WA", "RDS.WA",
    "MOV.WA", "FOR.WA", "PCF.WA", "CIG.WA", "BBT.WA", "RFK.WA", "PXM.WA", "MSW.WA", "ZRE.WA", "TRK.WA",
    "TOR.WA", "PND.WA", "DEK.WA"
]

TICKERS_USA = [
    "PLRX", "HUMA", "FATE", "TCRX", "IOVA", "MREO", "GOSS", "SNTI", "VINC", "ACRS", 
    "SLS", "TTWOQ", "ATNXQ", "MNTS", "BBIG", "NBY", "AEMD", "XELA", "COMS"
]

# --- 3. BEZPIECZNA WYSYŁKA NA TELEGRAM ---
def wyslij_telegram_alert(wiadomosc: str):
    """Wysyła czysty tekst na Telegram (użycie HTML zapobiega błędom parsowania Markdown)"""
    url = f"https://telegram.org{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": wiadomosc,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception:
        return False

# --- 4. SILNIK ANALIZY TECHNICZNEJ ---
def oblicz_wskaźniki(df):
    if df is None or len(df) < 20:
        return None
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    
    ostatnia_cena = df['Close'].iloc[-1]
    sma20_ost = df['SMA20'].iloc[-1] if not pd.isna(df['SMA20'].iloc[-1]) else ostatnia_cena
    sma50_ost = df['SMA50'].iloc[-1] if not pd.isna(df['SMA50'].iloc[-1]) else ostatnia_cena
    
    # Przypisywanie oceny rynkowej na podstawie układu średnich kroczących
    if ostatnia_cena > sma20_ost > sma50_ost:
        ocena = "Kupuj (Silny Up)"
        sygnal = "LONG"
    elif ostatnia_cena < sma20_ost < sma50_ost:
        ocena = "Sprzedaj (Silny Down)"
        sygnal = "SHORT"
    else:
        ocena = "Trzymaj (Konsolidacja)"
        sygnal = "NEUTRAL"
        
    ostatni_wolumen = df['Volume'].iloc[-1]
    sredni_wolumen = df['Volume'].rolling(window=20).mean().iloc[-1]
    skok_wolumenu = ostatni_wolumen / sredni_wolumen if (sredni_wolumen and sredni_wolumen > 0) else 1.0
    
    # Wyliczanie poziomów obronnych ATR
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(14).mean().iloc[-1] if not pd.isna(true_range.rolling(14).mean().iloc[-1]) else (ostatnia_cena * 0.05)
    
    mnoznik_sl = 2.5 if ostatnia_cena < 5 else 2.0
    mnoznik_tp = 4.0 if ostatnia_cena < 5 else 3.0
    
    sl = ostatnia_cena - (mnoznik_sl * atr) if sygnal == "LONG" else ostatnia_cena + (mnoznik_sl * atr)
    tp = ostatnia_cena + (mnoznik_tp * atr) if sygnal == "LONG" else ostatnia_cena - (mnoznik_tp * atr)
    
    return {
        "cena": ostatnia_cena, "ocena": ocena, "sygnal": sygnal,
        "skok_wolumenu": round(skok_wolumenu, 2), "sl": round(sl, 2), "tp": round(tp, 2)
    }

def głęboka_analiza_news_ai(ticker: str, tech: dict, rynek: str):
    """Pobiera wiadomości z Tavily i generuje uzasadnienie decyzji przez OpenAI"""
    try:
        search_query = f"{ticker} wiadomości giełda akcje raport" if rynek == "PL" else f"{ticker} penny stock clinical trial SEC filing catalyst"
        tavily_response = tavily_client.search(query=search_query, search_depth="advanced", max_results=3)
        
        context = ""
        for result in tavily_response['results']:
            context += f"- {result['title']}: {result['content']}\n"
            
        prompt = f"""
        Jesteś analitykiem giełdowym. Wyjaśnij zachowanie waloru {ticker}.
        Cena: {tech['cena']}, Stan techniczny: {tech['ocena']}, Obrót: {tech['skok_wolumenu']}x średniej.
        Doniesienia prasowe: {context}
        Napisz w 2 zwięzłych zdaniach po polsku, co jest głównym powodem ruchu i czy jest to potwierdzone fundamentalnie.
        Zwróć wyłącznie surowy format JSON: {{"komentarz": "TUTAJ WPISZ ANALIZĘ"}}
        """
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(completion.choices.message.content).get("komentarz", "Brak istotnych danych.")
    except Exception:
        return "Brak połączenia z silnikiem informacyjnym."

# --- 5. INTERFEJS UŻYTKOWNIKA STREAMLIT ---
st.title("📈 Profesjonalny Terminal Giełdowy AI Multi-Market")

# --- MODUŁ A: SZYBKIE OKNO SPRAWDZANIA TICKERA ---
st.subheader("🔍 Szybki podgląd i analiza wybranego waloru")
col_input1, col_input2 = st.columns([3, 1])
with col_input1:
    szukany_ticker = st.text_input("Wpisz DOWOLNY ticker rynkowy, aby sprawdzić go natychmiast (np. STX.WA, AAPL, NVDA, PLRX):", "").upper().strip()
with col_input2:
    st.write("##")
    uruchom_szukanie = st.button("🔎 Analizuj Ticker")

if uruchom_szukanie and szukany_ticker:
    with st.spinner(f"Trwa natychmiastowe skanowanie waloru {szukany_ticker}..."):
        obj = yf.Ticker(szukany_ticker)
        h = obj.history(period="1y")
        if h.empty:
            st.error(f"Nie znaleziono danych giełdowych dla symbolu: {szukany_ticker}")
        else:
            t_res = oblicz_wskaźniki(h)
            rynek_typ = "PL" if ".WA" in szukany_ticker else "USA"
            uzasadnienie = głęboka_analiza_news_ai(szukany_ticker, t_res, rynek_typ)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Aktualny Kurs", f"{t_res['cena']:.2f}")
            c2.metric("Ocena Algorytmu", t_res['ocena'])
            c3.metric("Skok Wolumenu Obrotu", f"{t_res['skok_wolumenu']}x")
            
            st.info(f"**Uzasadnienie AI (Tavily + OpenAI):** {uzasadnienie}")
            st.write(f"🎯 Docelowy Take Profit (TP): **{t_res['tp']:.2f}** | 🛑 Poziom Stop Loss (SL): **{t_res['sl']:.2f}**")
            
            # Wymuszenie powiadomienia na Telegram z szybkiego okna
            wiadomosc_tg = (
                f"🔎 <b>SZYBKI SKAN TICKERA: {szukany_ticker}</b>\n"
                f"▪️ Cena: {t_res['cena']:.2f}\n"
                f"▪️ Ocena: <b>{t_res['ocena']}</b>\n"
                f"▪️ Wolumen: {t_res['skok_wolumenu']}x\n"
                f"🎯 TP: {t_res['tp']:.2f} | 🛑 SL: {t_res['sl']:.2f}\n"
                f"📝 <b>Raport:</b> {uzasadnienie}"
            )
            wyslij_telegram_alert(wiadomosc_tg)
            st.success("Wysłano raport z szybkiego podglądu na Twój Telegram!")

st.write("---")

# --- MODUŁ B: GLOBALNA PĘTLA SKANOWANIA LISTY SPÓŁEK ---
st.subheader("🔄 Globalny Automatyczny Skaner Portfela Spółek")

st.sidebar.header("⚙️ Zarządzanie Skanerem")
wybierz_pl = st.sidebar.checkbox("Skanuj listę GPW (43 spółki)", value=True)
wybierz_usa = st.sidebar.checkbox("Skanuj listę USA (19 spółek)", value=True)
cena_max_us = st.sidebar.slider("Maksymalny próg cenowy dla USA ($):", 0.5, 20.0, 5.0)

col_btn1, col_btn2 = st.columns([1, 5])
with col_btn1:
    uruchom_globalny = st.button("🚀 Uruchom Skanowanie")
with col_btn2:
    if st.button("🔄 Wyczyszczenie pamięci i powtórny skan"):
        st.cache_data.clear()
        st.rerun()

if uruchom_globalny:
    lista_do_przejrzenia = []
    if wybierz_pl:
        for tick in TICKERS_PL: lista_do_przejrzenia.append((tick, "PL", "PLN"))
    if wybierz_usa:
        for tick in TICKERS_USA: lista_do_przejrzenia.append((tick, "USA", "USD"))
        
    if not lista_do_przejrzenia:
        st.warning("Zaznacz giełdy w panelu bocznym do wykonania operacji!")
    else:
        st.write(f"⏳ Analiza portfela giełdowego (Spółek do zbadania: {len(lista_do_przejrzenia)})...")
        pasek = st.progress(0)
        
        pelna_tabela_wynikow = []
        licznik_alertow = 0
        
        for index, (ticker, rynek, waluta) in enumerate(lista_do_przejrzenia):
            try:
                t_obj = yf.Ticker(ticker)
                historia = t_obj.history(period="1y")
                
                if historia.empty:
                    pasek.progress((index + 1) / len(lista_do_przejrzenia))
                    continue
                    
                tech = oblicz_wskaźniki(historia)
                if not tech:
                    pasek.progress((index + 1) / len(wybrane_tickery if 'wybrane_tickery' in locals() else lista_do_przejrzenia))
                    continue
                    
                # Filtracja progu cenowego dla groszówek z USA
                if rynek == "USA" and tech['cena'] > cena_max_us:
                    pasek.progress((index + 1) / len(lista_do_przejrzenia))
                    continue
                
                              # Zbieramy dane do pełnego podglądu przeskanowanych spółek
                dane_wiersza = {
                    "Ticker": ticker,
                    "Rynek": rynek,
                    "Aktualny Kurs": f"{tech['cena']:.2f} {waluta}",
                    "Ocena / Trend": tech['ocena'],
                    "Skok Wolumenu": f"{tech['skok_wolumenu']}x",
                    "Stop Loss (SL)": f"{tech['sl']:.2f}",
                    "Take Profit (TP)": f"{tech['tp']:.2f}"
                }
                pelna_tabela_wynikow.append(dane_wiersza)
                
                # Kryterium wysłania alertu na Telegram: silny sygnał giełdowy L/S LUB nagły wysoki obrót (Skok wolumenu >= 1.5x)
                if tech['sygnal'] in ["LONG", "SHORT"] or tech['skok_wolumenu'] >= 1.5:
                    licznik_alertow += 1
                    komentarz_rynkowy = głęboka_analiza_news_ai(ticker, tech, rynek)
                    
                    flag_rynek = "🇵🇱" if rynek == "PL" else "🇺🇸"
                    raport_tg = (
                        f"🚨 <b>ALERT RYNKOWY {flag_rynek}: {ticker}</b>\n"
                        f"▪️ Cena: {tech['cena']:.2f} {waluta}\n"
                        f"▪️ Ocena: <b>{tech['ocena']}</b>\n"
                        f"▪️ Wolumen obrotu: {tech['skok_wolumenu']}x\n"
                        f"🎯 Cel (TP): {tech['tp']:.2f} | 🛑 Obrona (SL): {tech['sl']:.2f}\n\n"
                        f"📝 <b>Analiza:</b> {komentarz_rynkowy}"
                    )
                    wyslij_telegram_alert(raport_tg)
                    time.sleep(0.5) # Zapobiega przekroczeniu limitów wysyłki w API Telegrama
