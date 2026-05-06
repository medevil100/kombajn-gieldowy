import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.express as px
import feedparser
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# ============================================================
# ULTRA ENGINE v9.0 — TOTAL ORACLE (FINAL CONSOLIDATED)
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v9.0 ORACLE", page_icon="⚔️")

# --- AUTO REFRESH (Co 5 minut domyślnie) ---
refresh_minutes = st.sidebar.slider("Interwał odświeżania (minuty)", 1, 15, 5)
st_autorefresh(interval=refresh_minutes * 60 * 1000, key="datarefresh")

# --- STYLIZACJA TERMINALA ---
st.markdown("""
<style>
    .stApp { background-color: #030305; color: #e0e0e0; }
    thead tr th { background-color: #111 !important; color: #00ff88 !important; }
    .status-kup { color: #00ff88; font-weight: bold; }
    .stDataFrame { border: 1px solid #222; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# --- SECRETS & AI CLIENT ---
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

def play_sound():
    """Alert dźwiękowy dla sygnałów KUP"""
    st.components.v1.html("""<audio autoplay><source src="https://soundjay.com"></audio>""", height=0)

def get_beast_news(symbol):
    """Najmocniejszy silnik newsów: Yahoo + Google News RSS"""
    news_text = []
    try:
        t = yf.Ticker(symbol)
        # 1. Yahoo Finance News
        news_text.extend([n.get('title', '') for n in t.news[:3]])

        # 2. Agresywne Google News (szukanie po nazwie lub tickerze)
        clean_sym = symbol.split('.')[0]
        google_url = f"https://google.com{clean_sym}+stock+news&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(google_url)
        news_text.extend([e.title for e in feed.entries[:5]])
        
        news_text = list(set([n for n in news_text if n])) # Usuń duplikaty
        
        if not news_text: return "NEUTRALNY: System szuka wieści..."
        
        if client:
            prompt = f"Analizuj newsy dla {symbol}: {news_text[:5]}. Wydaj wyrok: BYCZY/NIEDŹWIEDZI/NEUTRALNY + krótki powód (max 10 słów)."
            res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=60)
            return res.choices[0].message.content
        return "AI Offline"
    except: return "NEUTRALNY: News lag"

def get_earnings_turbo(symbol):
    """Turbo-monitoring wyników i dywidend z priorytetem dla 'Gorących Zdarzeń'"""
    # --- RĘCZNE MONITOROWANIE KLUCZOWYCH ZDARZEŃ (Wiedza Specjalistyczna) ---
    special_events = {
        "IOVA": "🔥 WYNIKI: 7 Maja (Przed sesją)",
        "STX.WA": "💰 DYWIDENDA: 0.73 PLN (Rekomendacja)",
        "PGV.WA": "📈 Akumulacja (Vol Shock)",
        "HUMA": "⚠️ Ryzyko (Wysokie RSI)"
    }
    
    # 1. Sprawdź, czy mamy to w bazie wydarzeń specjalnych
    clean_sym = symbol.upper()
    if clean_sym in special_events:
        return special_events[clean_sym]

    # 2. Jeśli nie, szukaj standardowo w API
    try:
        t = yf.Ticker(symbol)
        cal = t.calendar
        if cal is not None and not cal.empty:
            # Próba wyciągnięcia daty z różnych formatów yfinance
            if 'Earnings Date' in cal.index:
                date_val = cal.loc['Earnings Date'].iloc[0]
                return date_val.strftime('%Y-%m-%d')
            # Fallback dla starszych wersji
            return str(cal.iloc[0, 0]).split(' ')[0]
        return "N/A"
    except:
        return "N/A"


def get_full_analysis(symbol):
    """Główny silnik analityczny"""
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty or len(df) < 30: return None
        df.columns = [c.lower() for c in df.columns]
        last_close = df['close'].iloc[-1]
        
        # Wskaźniki techniczne
        delta = df['close'].diff()
        rsi = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / -delta.clip(upper=0).rolling(14).mean()))).iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        
        # Vol Shock & Momentum
        avg_vol = df['volume'].tail(20).mean()
        vol_ratio = df['volume'].iloc[-1] / avg_vol if avg_vol != 0 else 1
        momentum_10d = ((last_close - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100

        # Logika sygnału (Turbo Score)
        score = 0
        if rsi < 38: score += 2
        if last_close > sma50: score += 1
        if vol_ratio > 2.5: score += 3 
        if momentum_10d > 10: score += 1
        
        sig = "🔥 MOCNE KUP" if score >= 5 else "KUP" if score >= 3 else "SPRZEDAJ" if rsi > 72 else "CZEKAJ"

        return {
            "Symbol": symbol, "Cena": round(last_close, 3), "Sygnał": sig,
            "RSI": round(rsi, 1), "Vol Shock": f"{round(vol_ratio,1)}x",
            "Mom% (10d)": round(momentum_10d, 2), "Earnings": get_earnings_turbo(symbol),
            "AI Verdict": get_beast_news(symbol)
        }
    except: return None

# --- UI INTERFACE ---
st.title("⚡ TERMINAL v9.0 — TOTAL ORACLE")

default_list = "IOVA, HRT.WA, CFS.WA, PRT.WA, ATT.WA, STX.WA, PUR.WA, BCS.WA, KCH.WA, PGV.WA, HPE.WA, VVD.WA, HIVE, MER.WA, APS.WA, NVG.WA, PLRX, HUMA, TCRX, GOSS, MREO, ADTX"
symbols_input = st.sidebar.text_area("Lista Symboli", default_list)
symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]

if st.button("WYMUŚ SKANOWANIE"): st.rerun()

results = []
with st.spinner("Skanowanie rynków i analizowanie newsów przez AI..."):
    for s in symbols:
        data = get_full_analysis(s)
        if data: results.append(data)

if results:
    df_res = pd.DataFrame(results)
    
    # Stylizacja kolorystyczna tabeli
    def style_table(row):
        color = ''
        sent = str(row['AI Verdict']).upper()
        if "MOCNE" in str(row['Sygnał']) or "BYCZY" in sent: color = 'color: #00ff88; font-weight: bold'
        elif "SPRZEDAJ" in str(row['Sygnał']) or "NIEDŹWIEDZI" in sent: color = 'color: #ff4444'
        elif "NEUTRALNY" in sent: color = 'color: #ffa500'
        return [color] * len(row)

    if any("KUP" in str(s) for s in df_res['Sygnał']): play_sound()

    st.dataframe(df_res.style.apply(style_table, axis=1), use_container_width=True)

    # --- RANKING SIŁY ---
    st.divider()
    st.subheader("🏆 Ranking Momentum (Ostatnie 10 sesji)")
    df_sorted = df_res.sort_values(by="Mom% (10d)", ascending=True)
    fig = px.bar(df_sorted, x="Mom% (10d)", y="Symbol", orientation='h',
                 color="Mom% (10d)", color_continuous_scale='RdYlGn', text="Sygnał")
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # --- GENESIS AI: RAPORT SPEKULACYJNY ---
    if client:
        st.subheader("🤖 GENESIS AI: Wyrok Terminala")
        summary = df_res.to_string()
        prompt = f"""
        Jesteś bezlitosnym analitykiem portfela. Przeanalizuj: {summary}
        
        1. Wskaż lidera sesji i oceń czy Vol Shock potwierdza rajd.
        2. Czy data Earnings dla spółek (szczególnie IOVA) sugeruje akumulację pod wyniki?
        3. Wydaj 2 konkretne rekomendacje KUP/SPRZEDAJ z uzasadnieniem technicznym.
        Pisz krótko, agresywnie, po tradersku.
        """
        try:
            res_ai = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
            st.info(res_ai.choices[0].message.content)
        except Exception as e: st.error(f"AI Error: {e}")
else:
    st.warning("Oczekiwanie na dane z serwerów giełdowych...")
