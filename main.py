import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from openai import OpenAI

# ============================================================
# ULTRA ENGINE v6.5 — MULTI-STOCK + AGGRESSIVE AI
# ============================================================

st.set_page_config(layout="wide", page_title="ULTRA ENGINE v6.5", page_icon="⚔️")

# --- STYLE ---
st.markdown("""
<style>
    .stApp { background-color: #030308; color: #d0d0ff; }
    .signal-BUY { color: #00ff88; font-weight: bold; font-size: 1.2rem; }
    .signal-SELL { color: #ff4444; font-weight: bold; font-size: 1.2rem; }
    .signal-WATCH { color: #00ccff; }
    .card { border: 1px solid #222; padding: 15px; border-radius: 10px; background: #050a0f; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# --- ENGINE ---
def get_stock_analysis(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="100d")
        if df.empty or len(df) < 50: return None
        
        df.columns = [c.lower() for c in df.columns]
        close = df['close']
        
        # Wskaźniki
        rsi = (100 - (100 / (1 + (close.diff().clip(lower=0).rolling(14).mean() / -close.diff().clip(upper=0).rolling(14).mean())))).iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1] if len(df) >= 200 else ma50
        vol_rel = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1]
        
        # Prosta logika punktowa
        score = 0
        if close.iloc[-1] > ma50: score += 2
        if rsi < 30: score += 3
        if rsi > 70: score -= 3
        if vol_rel > 1.5: score += 1
        
        signal = "BUY" if score >= 3 else "SELL" if score <= -2 else "WATCH"
        
        return {
            "symbol": symbol,
            "price": round(close.iloc[-1], 2),
            "rsi": round(rsi, 2),
            "signal": signal,
            "score": score,
            "history": df['close'].tail(5).tolist() # Ostatnie 5 dni dla AI
        }
    except: return None

def genesis_brutal_analysis(data_list):
    if not client: return "Brak klucza OpenAI."
    
    # Budujemy konkretny raport dla AI
    context = ""
    for d in data_list:
        context += f"Spółka {d['symbol']}: Cena ${d['price']}, RSI: {d['rsi']}, Ostatnie ceny: {d['history']}. Sygnał techniczny: {d['signal']}\n"

    prompt = f"""
    Jesteś agresywnym traderem. Przeanalizuj listę spółek:
    {context}
    
    Zasady:
    1. Nie lej wody. Nie używaj słów 'może', 'warto rozważyć', 'neutralna sytuacja'.
    2. Wskaż JEDNEGO lidera do kupna (BUY) i JEDNEGO do wywalenia (SELL).
    3. Podaj konkretny powód techniczny (np. 'RSI szoruje po dnie przy wysokim wolumenie').
    4. Jeśli dane są słabe, powiedz to wprost.
    """
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Jesteś brutalnym analitykiem giełdowym."}, {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return resp.choices[0].message.content
    except Exception as e: return f"AI Error: {e}"

# --- UI ---
st.title("⚔️ ULTRA ENGINE v6.5 — RAPORT")

# Lista spółek do monitorowania
watchlist = st.sidebar.text_area("Lista spółek (rozdzielone przecinkiem)", "NVDA, AAPL, TSLA, AMD, MSFT, BTC-USD")
symbols = [s.strip() for s in watchlist.split(",")]

if st.button("URUCHOM MONITORING"):
    all_results = []
    
    # 1. Zbieranie danych
    cols = st.columns(len(symbols))
    for i, sym in enumerate(symbols):
        res = get_stock_analysis(sym)
        if res:
            all_results.append(res)
            with cols[i]:
                st.markdown(f"""
                <div class="card">
                    <b>{res['symbol']}</b><br>
                    <span class="price-tag">${res['price']}</span><br>
                    <span class="signal-{res['signal']}">{res['signal']}</span>
                </div>
                """, unsafe_allow_html=True)

    # 2. Analiza zbiorcza AI
    if all_results:
        st.divider()
        st.subheader("🤖 WYROK GENESIS AI (Globalny Przegląd)")
        with st.status("Analizowanie portfela przez AI...", expanded=True):
            verdict = genesis_brutal_analysis(all_results)
            st.write(verdict)
    else:
        st.error("Nie udało się pobrać danych dla żadnej spółki.")

