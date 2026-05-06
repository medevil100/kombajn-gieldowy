import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np

# ============================================================
# ULTRA ENGINE v7.2 — STABLE & READY
# ============================================================

st.set_page_config(layout="wide", page_title="MARKET TERMINAL v7.2", page_icon="📈")

# --- STYLIZACJA ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
</style>
""", unsafe_allow_html=True)

# --- SECRETS ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def get_market_data(symbol):
    """Pobiera dane techniczne i fundamentalne bez wywalania błędu"""
    try:
        t = yf.Ticker(symbol)
        # Pobieramy historię (period=1mo wystarczy dla RSI, ale 1y daje lepszy trend)
        df = t.history(period="1y")
        if df.empty: return None

        # Bezpieczne pobieranie info (często zawodzi na GPW)
        try:
            info = t.info
        except:
            info = {}

        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # --- OBLICZENIA TECHNICZNE ---
        # RSI 14
        delta = df['close'].diff()
        up = delta.clip(lower=0).rolling(window=14).mean()
        down = -delta.clip(upper=0).rolling(window=14).mean()
        rs = up / down
        rsi_series = 100 - (100 / (1 + rs))
        last_rsi = rsi_series.iloc[-1]
        
        # SMA50 (Trend krótki)
        sma50 = df['close'].rolling(window=50).mean().iloc[-1]
        
        # Wolumen (czy jest pompa?)
        avg_vol = df['volume'].tail(20).mean()
        last_vol = df['volume'].iloc[-1]
        vol_ratio = last_vol / avg_vol if avg_vol != 0 else 1

        # --- DANE MIKRO / FUNDAMENTY ---
        pe = info.get('forwardPE', info.get('trailingPE', 'N/A'))
        quick_ratio = info.get('quickRatio', 'N/A')
        mcap = info.get('marketCap', 0) / 1e6 # Miliony
        sector = info.get('sector', 'N/A')

        # --- LOGIKA SYGNAŁÓW ---
        score = 0
        # 1. RSI (wyprzedanie)
        if last_rsi < 35: score += 2
        # 2. Trend (cena nad średnią)
        if last_close > sma50: score += 1
        # 3. Wolumen (ponadprzeciętny obrót)
        if vol_ratio > 1.8: score += 2
        
        # Interpretacja
        if score >= 3:
            sig = "KUP"
        elif last_rsi > 70:
            sig = "SPRZEDAJ"
        else:
            sig = "CZEKAJ"
        
        return {
            "Symbol": symbol,
            "Sektor": sector,
            "Cena": round(last_close, 3),
            "RSI": round(last_rsi, 2) if not np.isnan(last_rsi) else 50.0,
            "Trend": "↑ Wzrost" if last_close > sma50 else "↓ Spadek",
            "Vol x": round(vol_ratio, 2),
            "C/Z (PE)": pe,
            "Płynność (QR)": quick_ratio,
            "Cap(M)": f"{int(mcap)}M" if mcap > 0 else "N/A",
            "Sygnał": sig
        }
    except Exception:
        return None

# --- INTERFEJS UŻYTKOWNIKA ---
st.title("⚔️ MARKET TERMINAL v7.2 — MONITOR")

# Twoja lista spółek
default_list = "HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, IOVA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
watchlist = st.sidebar.text_area("Symbole (oddziel przecinkiem)", default_list)
symbols = [s.strip() for s in watchlist.split(",")]

if st.button("URUCHOM ANALIZĘ"):
    results = []
    progress_text = "Skanowanie rynku..."
    progress_bar = st.progress(0)
    
    for i, s in enumerate(symbols):
        data = get_market_data(s)
        if data:
            results.append(data)
        progress_bar.progress((i + 1) / len(symbols))
    
    if results:
        df_res = pd.DataFrame(results)
        
        # STYLIZACJA TABELI (Naprawiony błąd applymap)
        def color_signals(val):
            if val == 'KUP': return 'color: #00ff88; font-weight: bold;'
            if val == 'SPRZEDAJ': return 'color: #ff4444; font-weight: bold;'
            return ''

        # Wyświetlamy tabelę
        st.subheader("📊 Wyniki skanowania")
        st.dataframe(df_res.style.map(color_signals, subset=['Sygnał']), use_container_width=True)

        # ANALIZA AI
        if client:
            st.divider()
            st.subheader("🤖 GENESIS AI: Wyrok")
            
            summary_text = df_res.to_string()
            prompt = f"""
            Przeanalizuj listę spółek:
            {summary_text}
            
            Wybierz 2-3 najlepsze okazje. Weź pod uwagę RSI (szukaj niskiego) oraz Vol x (szukaj wysokiego).
            Jeśli Quick Ratio (Płynność QR) jest N/A lub poniżej 1.0, ostrzeż o ryzyku finansowym.
            Odpowiadaj krótko i konkretnie.
            """
            
            try:
                with st.spinner("AI przetwarza dane..."):
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Jesteś ekspertem od spekulacji giełdowej."}, {"role": "user", "content": prompt}]
                    )
                    st.info(response.choices[0].message.content)
            except Exception as e:
                st.warning(f"AI nie odpowiedziało: {e}")
    else:
        st.error("Brak danych. Sprawdź, czy symbole są wpisane poprawnie.")
