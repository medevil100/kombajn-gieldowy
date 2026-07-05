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
    url = f"https://telegram.org{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": wiadomosc, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception:
        return False

# --- 4. ENGINE WYLICZEŃ TECHNICZNYCH (PRZETWARZANIE PACZKOWE) ---
def przetwórz_dane_historyczne(ticker, df_close, df_volume, df_high, df_low):
    """Szybkie wyliczanie wskaźników z pobranej wcześniej zbiorczej bazy danych"""
    try:
        if ticker not in df_close.columns or len(df_close[ticker].dropna()) < 20:
            return None
            
        cena = df_close[ticker].iloc[-1]
        vols = df_volume[ticker]
        highs = df_high[ticker]
        lows = df_low[ticker]
        closes = df_close[ticker]
        
        sma20 = closes.rolling(window=20).mean().iloc[-1]
        sma50 = closes.rolling(window=50).mean().iloc[-1]
        
        if cena > sma20 > sma50:
            ocena, sygnal = "Kupuj (Silny Up)", "LONG"
        elif cena < sma20 < sma50:
            ocena, sygnal = "Sprzedaj (Silny Down)", "SHORT"
        else:
            ocena, sygnal = "Trzymaj (Konsolidacja)", "NEUTRAL"
            
        ostatni_vol = vols.iloc[-1]
        sredni_vol = vols.rolling(window=20).mean().iloc[-1]
        skok_wolumenu = ostatni_vol / sredni_vol if (sredni_vol and sredni_vol > 0) else 1.0
        
        # Matematyka wskaźnika ATR
        high_low = highs - lows
        high_close = np.abs(highs - closes.shift())
        low_close = np.abs(lows - closes.shift())
        true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
        atr = true_range.rolling(14).mean().iloc[-1] if not pd.isna(true_range.rolling(14).mean().iloc[-1]) else (cena * 0.05)
        
        mnoznik_sl = 2.5 if cena < 5 else 2.0
        mnoznik_tp = 4.0 if cena < 5 else 3.0
        
        sl = cena - (mnoznik_sl * atr) if sygnal == "LONG" else cena + (mnoznik_sl * atr)
        tp = cena + (mnoznik_tp * atr) if sygnal == "LONG" else cena - (mnoznik_tp * atr)
        
        return {"cena": cena, "ocena": ocena, "sygnal": sygnal, "skok_wolumenu": round(skok_wolumenu, 2), "sl": round(sl, 2), "tp": round(tp, 2)}
    except Exception:
        return None

def głęboka_analiza_news_ai(ticker: str, tech: dict, rynek: str):
    try:
        search_query = f"{ticker} wiadomości giełda akcje" if rynek == "PL" else f"{ticker} penny stock clinical trial SEC filing catalyst"
        tavily_response = tavily_client.search(query=search_query, search_depth="advanced", max_results=3)
        context = ""
        for result in tavily_response['results']:
            context += f"- {result['title']}: {result['content']}\n"
            
        prompt = f"Jesteś analitykiem. Wyjaśnij zachowanie {ticker}. Cena: {tech['cena']}, Stan: {tech['ocena']}, Obrót: {tech['skok_wolumenu']}x. Teksty: {context}. Napisz po polsku w 2 zdaniach katalizator ruchu. Zwróć JSON: {{\n\"komentarz\": \"ANALIZA\"\n}}"
        completion = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}, temperature=0.1)
        return json.loads(completion.choices.message.content).get("komentarz", "Brak danych.")
    except Exception:
        return "Brak połączenia z silnikiem informacyjnym."

# --- 5. INTERFEJS UŻYTKOWNIKA STREAMLIT ---
st.title("📈 Profesjonalny Terminal Giełdowy AI Multi-Market")

# --- CZĘŚĆ 1: SZYBKI PODGLĄD POJEDYNCZEGO WALORU ---
st.subheader("🔍 Szybki podgląd i analiza wybranego waloru")
col_input1, col_input2 = st.columns(2)
with col_input1:
    szukany_ticker = st.text_input("Wpisz DOWOLNY ticker rynkowy (np. STX.WA, AAPL, PLRX):", "").upper().strip()
with col_input2:
    st.write("##")
    uruchom_szukanie = st.button("🔎 Analizuj Ticker")

if uruchom_szukanie and szukany_ticker:
    with st.spinner(f"Skanowanie pojedyncze waloru {szukany_ticker}..."):
        obj = yf.Ticker(szukany_ticker)
        h = obj.history(period="1y")
        if h.empty:
            st.error(f"Brak danych dla symbolu: {szukany_ticker}")
        else:
            try:
                # Mapowanie struktur dla pojedynczego przetwarzania
                df_c = pd.DataFrame({szukany_ticker: h['Close']})
                df_v = pd.DataFrame({szukany_ticker: h['Volume']})
                df_h = pd.DataFrame({szukany_ticker: h['High']})
                df_l = pd.DataFrame({szukany_ticker: h['Low']})
                t_res = przetwórz_dane_historyczne(szukany_ticker, df_c, df_v, df_h, df_l)
                
                if t_res:
                    rynek_typ = "PL" if ".WA" in szukany_ticker else "USA"
                    uzasadnienie = głęboka_analiza_news_ai(szukany_ticker, t_res, rynek_typ)
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Aktualny Kurs", f"{t_res['cena']:.2f}")
                    c2.metric("Ocena Algorytmu", t_res['ocena'])
                    c3.metric("Skok Wolumenu Obrotu", f"{t_res['skok_wolumenu']}x")
                    
                    st.info(f"**Uzasadnienie AI:** {uzasadnienie}")
                    st.write(f"🎯 Take Profit: **{t_res['tp']:.2f}** | 🛑 Stop Loss: **{t_res['sl']:.2f}**")
                    
                    wyslij_telegram_alert(f"🔎 <b>SZYBKI SKAN: {szukany_ticker}</b>\nCena: {t_res['cena']:.2f}\nOcena: {t_res['ocena']}\n📝 {uzasadnienie}")
                    st.success("Wysłano raport na Telegram!")
            except Exception as e:
                st.error(f"Błąd przetwarzania: {e}")

st.write("---")

# --- CZĘŚĆ 2: GLOBALNA PĘTLA SKANOWANIA LISTY SPÓŁEK (BULK DOWNLOAD) ---
st.subheader("🔄 Globalny Automatyczny Skaner Portfela Spółek")

st.sidebar.header("⚙️ Zarządzanie Skanerem")
wybierz_pl = st.sidebar.checkbox("Skanuj listę GPW (43 spółki)", value=True)
wybierz_usa = st.sidebar.checkbox("Skanuj listę USA (19 spółek)", value=True)
cena_max_us = st.sidebar.slider("Maksymalny próg cenowy dla USA ($):", 0.5, 20.0, 5.0)

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    uruchom_globalny = st.button("🚀 Uruchom Skanowanie")
with col_btn2:
    if st.button("🔄 Wyczyszczenie pamięci i reset"):
        st.cache_data.clear()
        st.rerun()

if uruchom_globalny:
    lista_tickerów = []
    if wybierz_pl:
        lista_tickerów.extend(TICKERS_PL)
    if wybierz_usa:
        lista_tickerów.extend(TICKERS_USA)
        
    if not lista_tickerów:
        st.warning("Zaznacz przynajmniej jeden rynek w panelu bocznym!")
    else:
        with st.spinner("🚀 KROK 1: Pobieranie zbiorcze danych z Yahoo Finance dla wszystkich spółek naraz..."):
            # Pobieramy dane paczkowo (Wszystkie 62 spółki na raz w 2 sekundy)
            dane_bulk = yf.download(lista_tickerów, period="1y", group_by="ticker", progress=False)
            
            # Budujemy słowniki indeksowane dla ułatwienia odczytu wielopoziomowego
            df_close = pd.DataFrame()
            df_volume = pd.DataFrame()
            df_high = pd.DataFrame()
            df_low = pd.DataFrame()
            
            for t in lista_tickerów:
                if t in dane_bulk.columns.levels[0]:
                    df_close[t] = dane_bulk[t]['Close']
                    df_volume[t] = dane_bulk[t]['Volume']
                    df_high[t] = dane_bulk[t]['High']
                    df_low[t] = dane_bulk[t]['Low']

        st.write("⏳ KROK 2: Analiza techniczna formacji rynkowych i wysyłanie alertów...")
        pasek = st.progress(0)
        pelna_tabela_wynikow = []
        licznik_alertow = 0
        
        for index, ticker in enumerate(lista_tickerów):
            try:
                waluta = "PLN" if ".WA" in ticker else "USD"
                rynek = "PL" if ".WA" in ticker else "USA"
                
                tech = przetwórz_dane_historyczne(ticker, df_close, df_volume, df_high, df_low)
                if not tech:
                    continue
                    
                if rynek == "USA" and tech['cena'] > cena_max_us:
                    continue
                
                # Zapis do tabeli Live
                pelna_tabela_wynikow.append({
                                    # Zapis do tabeli Live
                pelna_tabela_wynikow.append({
                    "Ticker": ticker, 
                    "Rynek": rynek, 
                    "Aktualny Kurs": f"{tech['cena']:.2f} {waluta}",
                    "Ocena / Trend": tech['ocena'], 
                    "Skok Wolumenu": f"{tech['skok_wolumenu']}x",
                    "Stop Loss (SL)": f"{tech['sl']:.2f}", 
                    "Take Profit (TP)": f"{tech['tp']:.2f}"
                })
                
 # Uruchomienie wyszukiwarki Tavily wyłącznie dla spółek z wyraźną okazją (Skok wolumenu >= 1.5x lub sygnał)
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
                    time.sleep(0.3)
                    
            except Exception:
                pass
                
            pasek.progress((index + 1) / len(lista_tickerów))
            
        st.success("✅ Zbiorcza analiza giełdowa została pomyślnie sfinalizowana!")
        st.write(f"Wysłano ważnych alertów na Telegram: **{licznik_alertow}**")
        
        if pelna_tabela_wynikow:
            st.subheader("📊 Kompletny podgląd wszystkich przeskanowanych spółek")
            df_wynikowy = pd.DataFrame(pelna_tabela_wynikow)
            st.dataframe(df_wynikowy, use_container_width=True)
