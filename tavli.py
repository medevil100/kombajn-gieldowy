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

# --- 1. KONFIGURACJA I INICJALIZACJA ---
st.set_page_config(page_title="Multi-Market Trading Scanner AI", layout="wide", page_icon="🚀")

try:
    TAVILY_KEY = st.secrets["TAVILY_API_KEY"]
    OPENAI_KEY = st.secrets["OPENAI_API_KEY"]
    TG_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    TG_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except KeyError as e:
    st.error(f"Błąd: Brak klucza {e} w pliku secrets.toml!")
    st.stop()

openai_client = OpenAI(api_key=OPENAI_KEY)
tavily_client = TavilyClient(api_key=TAVILY_KEY)

# --- 2. STAŁE LISTY TICKERÓW (POLSKA + USA) ---
TICKERS_PL = [
    "APS.WA", "STX.WA", "AIT.WA", "CLD.WA", "NVS.WA", "PTN.WA", "IFR.WA", "KCH.WA", "ENG.WA", "PEP.WA",
    "MDF.WA", "BIM.WA", "BML.WA", "VVD.WA", "MIR.WA", "QNT.WA", "MGT.WA", "SYN.WA", "OAT.WA", "IGN.WA",
    "GT.WA", "BIO.WA", "PHR.WA", "PURE.WA", "MAB.WA", "VIV.WA", "ULT.WA", "HUG.WA", "TEN.WA", "RDS.WA",
    "MOV.WA", "FOR.WA", "PCF.WA", "CIG.WA", "BBT.WA", "RFK.WA", "PXM.WA", "MSW.WA", "ZRE.WA", "TRK.WA",
    "TOR.WA", "PND.WA", "DEK.WA"
]

TICKERS_USA_STATIC = [
    "PLRX", "HUMA", "FATE", "TCRX", "IOVA", "MREO", "GOSS", "SNTI", "VINC", "ACRS", 
    "SLS", "TTWOQ", "ATNXQ", "MNTS", "BBIG", "NBY", "AEMD", "XELA", "COMS"
]

# --- 3. MODUŁ POWIADOMIEŃ TELEGRAM ---
def wyslij_telegram_alert(wiadomosc: str):
    url = f"https://telegram.org{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": wiadomosc,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception:
        return False

# --- 4. ENGINE ANALIZY TECHNICZNEJ I MATEMATYKI ATR ---
def oblicz_wskazniki_techniczne(df):
    if df is None or len(df) < 30:
        return None
        
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    
    ostatnia_cena = df['Close'].iloc[-1]
    sma20_ost = df['SMA20'].iloc[-1]
    sma50_ost = df['SMA50'].iloc[-1]
    
    # Detekcja Trendu przy użyciu średnich kroczących
    if ostatnia_cena > sma20_ost > sma50_ost:
        trend = "Silny Trend Wzrostowy (Bullish)"
        sygnal = "LONG"
    elif ostatnia_cena < sma20_ost < sma50_ost:
        trend = "Silny Trend Spadkowy (Bearish)"
        sygnal = "SHORT"
    else:
        trend = "Konsolidacja / Trend Boczny"
        sygnal = "NEUTRAL"
        
    # Analiza wolumenu (Dzisiejszy vs Średni z 20 dni)
    ostatni_wolumen = df['Volume'].iloc[-1]
    sredni_wolumen = df['Volume'].rolling(window=20).mean().iloc[-1]
    skok_wolumenu = ostatni_wolumen / sredni_wolumen if sredni_wolumen > 0 else 1
    
    # Wyliczanie poziomów obronnych (SL/TP) na podstawie zmienności ATR(14)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(14).mean().iloc[-1]
    
    # Mnożnik ATR dopasowany do zmienności groszówek (wyższy rozstaw chroni przed szumem)
    mnoznik_sl = 2.5 if ostatnia_cena < 5 else 2.0
    mnoznik_tp = 4.0 if ostatnia_cena < 5 else 3.0
    
    sl = ostatnia_cena - (mnoznik_sl * atr) if sygnal == "LONG" else ostatnia_cena + (mnoznik_sl * atr)
    tp = ostatnia_cena + (mnoznik_tp * atr) if sygnal == "LONG" else ostatnia_cena - (mnoznik_tp * atr)
    
    return {
        "cena": ostatnia_cena, "trend": trend, "sygnal": sygnal,
        "skok_wolumenu": round(skok_wolumenu, 2), "atr": round(atr, 3),
        "sl": round(sl, 2), "tp": round(tp, 2)
    }

def skanuj_i_analizuj_spolke(ticker: str, język_raportu: str):
    try:
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(period="1y")
        if hist.empty: return None, None
        
        tech = oblicz_wskazniki_techniczne(hist)
        if not tech: return None, None
        
        # Filtrowanie szumu: Pomijamy nudne spółki bez skoku wolumenu lub trendu
        if tech['sygnal'] == "NEUTRAL" and tech['skok_wolumenu'] < 1.5:
            return tech, None
            
        # Dopasowanie zapytania językowego Tavily do rynku docelowego
        if język_raportu == "PL":
            search_query = f"{ticker.replace('.WA','')} wiadomości giełda akcje raport wolumen fuzje"
        else:
            search_query = f"{ticker} penny stock clinical trial SEC filing delisting volume spike catalyst"
            
        tavily_response = tavily_client.search(query=search_query, search_depth="advanced", max_results=3)
        
        context = ""
        for result in tavily_response['results']:
            context += f"- {result['title']}: {result['content']}\n"
            
        prompt = f"""
        Jesteś hedge fund traderem specjalizującym się w sytuacjach specjalnych (anomalie wolumenu, penny stocks, spółki biotechnologiczne, bankructwa OTC).
        Przeanalizuj krótki setup dla waloru {ticker}.
        Cena: {tech['cena']}, Kierunek techniczny: {tech['sygnal']}, Skok Wolumenu: {tech['skok_wolumenu']}x.
        
        Doniesienia i katalizatory rynkowe:
        {context}
        
        Napisz raport w języku POLSKIM. Wskaż w 2-3 konkretnych zdaniach, czy skok wolumenu jest wywołany realnym katalizatorem (np. wyniki badań klinicznych, raport SEC, plotki o przejęciu, ryzyko wycofania z giełdy/delisting), czy to czysta spekulacja.
        Zwróć format JSON: {{"analiza_tekst": "TUTAJ_RAPORT", "potwierdzenie_ai": "TAK/NIE"}}
        """
        
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        ai_res = json.loads(completion.choices.message.content)
        return tech, ai_res
    except Exception:
        return None, None

# --- 5. INTERFEJS UŻYTKOWNIKA STREAMLIT ---
st.title("🤖 Zaawansowany Skaner Multimarket AI Pro")
st.write("Równoległy skaner GPW (Polska) oraz US Penny Stocks & Biotech (USA) z filtrem wolumenu i powiadomieniami Telegram.")

st.sidebar.header("⚙️ Parametry Skanera")
rynek_pl = st.sidebar.checkbox("Skanuj rynek polski (43 spółki GPW)", value=True)
rynek_usa = st.sidebar.checkbox("Skanuj rynek USA (19 stałych spółek + groszówki)", value=True)
filtr_penny = st.sidebar.slider("Maksymalna cena dla spółek z USA (Penny Stocks limit $):", 0.5, 20.0, 5.0)

if st.button("🚀 Uruchom Globalną Pętlę Skanującą"):
    wybrane_tickery = []
    if rynek_pl:
        for t in TICKERS_PL: wybrane_tickery.append((t, "PL", "PLN"))
    if rynek_usa:
        for t in TICKERS_USA_STATIC: wybrane_tickery.append((t, "USA", "USD"))
        
    if not wybrane_tickery:
        st.warning("Wybierz przynajmniej jeden rynek w panelu bocznym!")
        st.stop()
        
    st.subheader(f"⌛ Skanowanie {len(wybrane_tickery)} instrumentów w czasie rzeczywistym...")
    postep = st.progress(0)
    wyszukane_okazje = []
    
    for idx, (ticker, rynek, waluta) in enumerate(wybrane_tickery):
        tech, ai = skanuj_i_analizuj_spolke(ticker, rynek)
        
        if tech:
            if rynek == "USA" and tech['cena'] > filtr_penny:
                postep.progress((idx + 1) / len(wybrane_tickery))
                continue
                
            if tech['skok_wolumenu'] >= 1.5 or tech['sygnal'] in ["LONG", "SHORT"]:
                komentarz_ai = ai["analiza_tekst"] if ai else "Brak kluczowych doniesień prasowych. Ruch o charakterze czysto technicznym."
                potwierdzone = ai["potwierdzenie_ai"] if ai else "NIE"
                
                wpis = {
                    "Ticker": ticker, "Rynek": rynek, "Cena": f"{tech['cena']:.2f} {waluta}",
                    "Sygnał": tech['sygnal'], "Skok Wolumenu": f"{tech['skok_wolumenu']}x",
                    "Stop Loss (SL)": f"{tech['sl']:.2f}", "Take Profit (TP)": f"{tech['tp']:.2f}",
                    "Analiza Katalizatora (AI)": komentarz_ai
                }
                wyszukane_okazje.append(wpis)
                
                if tech['skok_wolumenu'] >= 1.5 or potwierdzone == "TAK":
                    emoji_rynek = "🇵🇱" if rynek == "PL" else "🇺🇸"
                    alert_msg = (
                        f"🚨 *ALERT MULTI-MARKET AI {emoji_rynek}: {ticker}*\n"
                        f"▪️ Cena: `{tech['cena']:.2f} {waluta}`\n"
                        f"▪️ Sygnał techniczny: *{tech['sygnal']}*\n"
                        f"▪️ Skok obrotu: `{tech['skok_wolumenu']}x` powyżej średniej!\n"
                        f"🎯 Cel (TP): `{tech['tp']:.2f}` | 🛑 Obrona (SL): `{tech['sl']:.2f}`\n\n"
                        f"📝 *Katalizator biznesowy:* {komentarz_ai}"
                    )
                    wyslij_telegram_alert(alert_msg)
                    
        postep.progress((idx + 1) / len(wybrane_tickery))
        time.sleep(0.2)
        
    st.success("✅ Skanowanie bazy rynków zakończone pomyślnie!")
    
    if wyszukane_okazje:
        st.subheader("🎯 Wykryte Anomalie i Setupu Inwestycyjne")
        df_wyniki = pd.DataFrame(wyszukane_okazje)
        st.dataframe(df_wyniki, use_container_width=True)
    else:
        st.info("Brak istotnych anomalii wolumenowych spełniających kryteria na skanowanych giełdach.")




