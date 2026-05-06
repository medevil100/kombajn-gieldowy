import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np

# ============================================================
# ULTRA ENGINE v7.1 — ROBUST TERMINAL (GPW READY)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v7.1", page_icon="📈")

st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
    .status-kup { color: #00ff88; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def get_safe_data(symbol):
    try:
        t = yf.Ticker(symbol)
        # Pobieramy historię
        df = t.history(period="150d")
        if df.empty: return None

        # Próba pobrania info (często zawodzi na GPW, więc dajemy try/except)
        try:
            info = t.info
        except:
            info = {}

        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # --- TECHNIKA ---
        delta = df['close'].diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean()
        rsi_val = 100 - (100 / (1 + (up/down))).iloc[-1]
        
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        vol_ratio = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1] if df['volume'].rolling(20).mean().iloc[-1] != 0 else 1

        # --- MIKRO (zabezpieczone) ---
        pe = info.get('forwardPE', info.get('trailingPE', 'N/A'))
        quick = info.get('quickRatio', 'N/A')
        mcap = info.get('marketCap', 0) / 1e6
        sector = info.get('sector', 'N/A')

        # Sygnał
        score = 0
        if rsi_val < 35: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 1.8: score += 2
        
        sig = "KUP" if score >= 3 else "SPRZEDAJ" if rsi_val > 70 else "CZEKAJ"
        
        return {
            "Symbol": symbol,
            "Sektor": sector,
            "Cena": round(last_close, 3),
            "RSI": round(rsi_val, 2) if not np.isnan(rsi_val) else 50,
            "Trend": "↑ Wzrost" if last_close > sma50 else "↓ Spadek",
            "Vol x": round(vol_ratio, 2),
            "C/Z (PE)": pe,
            "Płynność (QR)": quick,
            "Cap(M)": f"{int(mcap)}M" if mcap > 0 else "N/A",
            "Sygnał": sig
        }
    except Exception as e:
        return None

# --- UI ---
st.title("⚔️ MARKET TERMINAL v7.1")

# Domyślna lista z Twoimi symbolami
default_list = "HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, IOVA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
watchlist_input = st.sidebar.text_area("Symbole do analizy", default_list)
symbols = [s.strip() for s in watchlist_input.split(",")]

if st.button("URUCHOM SKANER"):
    results = []
    progress_bar = st.progress(0)
    
    for i, s in enumerate(symbols):
        data = get_safe_data(s)
        if data:
            results.append(data)
        progress_bar.progress((i + 1) / len(symbols))
    
    if results:
        df_res = pd.DataFrame(results)
        
        # Wyświetlanie tabeli
        st.dataframe(df_res.style.applymap(
            lambda x: 'color: #00ff88' if x == 'KUP' else ('color: #ff4444' if x == 'SPRZEDAJ' else ''),
            subset=['Sygnał']
        ), use_container_width=True)

        # Analiza AI
        if client:
            st.divider()
            st.subheader("🤖 GENESIS AI: Raport Strategiczny")
            
            summary = df_res.to_string()
            prompt = f"Oto dane rynkowe: {summary}. Wybierz 3 najsilniejsze fundamentalnie i technicznie spółki. Jeśli Płynność (QR) jest N/A lub < 1, zachowaj ostrożność. Podaj krótkie uzasadnienie."
            
            with st.spinner("AI myśli..."):
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "Jesteś ekspertem od GPW i NASDAQ."}, {"role": "user", "content": prompt}]
                )
                st.info(response.choices[0].message.content)
    else:
        st.error("Nie udało się pobrać danych. Upewnij się, że symbole są poprawne (np. AAPL dla USA, PKN.WA dla Polski).")
