import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np

# ============================================================
# ULTRA ENGINE v7.0 — PROFESSIONAL DASHBOARD
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v7.0", page_icon="📈")

# --- CUSTOM CSS FOR DARK TERMINAL LOOK ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .reportview-container .main { background: #050505; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
    .status-buy { color: #00ff88; font-weight: bold; }
    .status-sell { color: #ff4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def get_advanced_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="150d")
        info = t.info # Dane mikroekonomiczne
        
        if df.empty or len(df) < 50: return None
        
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # --- OBLICZENIA TECHNICZNE ---
        # RSI
        delta = df['close'].diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (up/down)))
        
        # Trend (SMA 50 vs 200)
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else sma50
        
        # Wolumen (Mikro-skok)
        vol_ratio = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1]

        # --- DANE MIKRO / FUNDAMENTALNE ---
        pe_ratio = info.get('forwardPE', 'N/A')
        quick_ratio = info.get('quickRatio', 'N/A')
        market_cap = info.get('marketCap', 0) / 1e6 # w milionach
        
        # Sygnał
        score = 0
        if rsi.iloc[-1] < 30: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 1.5: score += 2
        
        sig = "KUP" if score >= 3 else "SPRZEDAJ" if rsi.iloc[-1] > 70 else "CZEKAJ"
        
        return {
            "Symbol": symbol,
            "Cena": round(last_close, 3),
            "RSI": round(rsi.iloc[-1], 2),
            "Trend": "↑ Wzrostowy" if last_close > sma50 else "↓ Spadkowy",
            "Vol Score": f"{round(vol_ratio, 2)}x",
            "P/E (C/Z)": pe_ratio,
            "Quick Ratio": quick_ratio,
            "Cap (M)": f"{int(market_cap)}M",
            "Sygnał": sig
        }
    except: return None

# --- UI INTERFACE ---
st.title("⚔️ MARKET TERMINAL v7.0")

watchlist_input = st.sidebar.text_area("Lista Symboli", "NVDA, TSLA, PUR.WA, PGV.WA, MER.WA, BTC-USD")
symbols = [s.strip() for s in watchlist_input.split(",")]

if st.button("ANALIZUJ RYNEK"):
    results = []
    with st.spinner("Pobieranie danych rynkowych i mikro..."):
        for s in symbols:
            data = get_advanced_analysis(s)
            if data: results.append(data)
    
    if results:
        df_res = pd.DataFrame(results)
        
        # Kolorowanie tabeli
        def color_signal(val):
            color = '#00ff88' if val == "KUP" else '#ff4444' if val == "SPRZEDAJ" else '#888'
            return f'color: {color}'

        st.table(df_res.style.applymap(color_signal, subset=['Sygnał']))

        # --- SEKCJA MAKRO AI ---
        st.divider()
        st.subheader("🤖 WYROK STRATEGICZNY (Fundamenty + Technika)")
        
        # Przygotowanie promptu z danymi mikro
        context = df_res.to_string()
        prompt = f"""
        Przeanalizuj poniższą tabelę spółek. 
        Zwróć uwagę na P/E (C/Z) oraz Quick Ratio (płynność finansowa).
        Jeśli Quick Ratio jest poniżej 1.0, ostrzeż przed bankructwem.
        Jeśli Vol Score jest wysoki (>2x), szukaj anomalii.
        Oto dane:
        {context}
        
        Podsumuj krótko: Najlepsza okazja fundamentalna vs techniczna.
        """
        
        if client:
            res_ai = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            st.info(res_ai.choices[0].message.content)
    else:
        st.error("Brak danych. Sprawdź symbole.")
