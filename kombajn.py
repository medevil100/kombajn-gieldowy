import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime

# --- KONFIGURACJA ŚRODOWISKA ---
st.set_page_config(page_title="AI ALPHA MONSTER v72 PRO", layout="wide")
DB_FILE = "moje_spolki.txt"

# Pobranie klucza OpenAI z Secrets
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

# Autorefresh co 5 minut (300 000 ms)
st_autorefresh(interval=300000, key="data_refresh")

# --- SYSTEM STYLÓW NEON ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .neon-card { 
        background: rgba(13, 17, 23, 0.9); 
        padding: 20px; border-radius: 15px; border: 1px solid #30363d; 
        margin-bottom: 20px; transition: 0.3s;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); color: #00ff88; }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); color: #ff4b4b; }
    .hold { border: 2px solid #8b949e !important; color: #8b949e; }
    .neon-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .neon-value { font-size: 1.1rem; font-weight: bold; color: #ffffff; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE SILNIKA ---
def fetch_analysis_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d") # 1 rok dla szczytów/dołków 52-tyg
        if df.empty: return None
        
        # Dane bieżące
        info = t.info
        curr = df['Close'].iloc[-1]
        
        # 1. Analiza 52-tygodniowa
        high_52 = info.get("fiftyTwoWeekHigh", df['High'].max())
        low_52 = info.get("fiftyTwoWeekLow", df['Low'].min())
        
        # 2. Pivot Points (Klasyczne)
        prev = df.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        r1, s1 = (2 * pivot) - prev['Low'], (2 * pivot) - prev['High']
        
        # 3. RSI (14 dni)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # 4. Werdykt kafelka
        if rsi < 35: v_text, v_class = "KUP 🔥", "buy"
        elif rsi > 65: v_text, v_class = "SPRZEDAJ ⚠️", "sell"
        else: v_text, v_class = "TRZYMAJ ⏳", "hold"

        return {
            "s": symbol.upper(), "p": curr, "rsi": rsi, "pivot": pivot, "r1": r1, "s1": s1,
            "h52": high_52, "l52": low_52, "v": v_text, "vc": v_class, "news": t.news[:2], "df": df
        }
    except: return None

def get_ai_pro_analysis(data):
    if not client: return "Brak klucza OpenAI w skrytce."
    prompt = f"""
    Analiza ekspercka dla {data['s']}:
    Cena: {data['p']:.2f}, RSI: {data['rsi']:.1f}, Pivot: {data['pivot']:.2f}.
    Szczyt 52-tyg: {data['h52']:.2f}, Dołek 52-tyg: {data['l52']:.2f}.
    Podaj: Konkretny Stop Loss (SL) i Take Profit (TP), analizę świec z 1 dnia i strategię.
    Bez lania wody, same fakty.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        return response.choices[0].message.content
    except: return "Błąd połączenia z AI."

# --- INTERFEJS UŻYTKOWNIKA ---
with st.sidebar:
    st.title("🚜 MONSTER v72")
    new_ticker = st.text_input("Dodaj spółkę (np. NVDA, PKO.WA):")
    if st.button("DODAJ I ZAPISZ"):
        with open(DB_FILE, "a") as f: f.write(f"{new_ticker},")
        st.success("Zapisano!")
        st.rerun()
    
    st.divider()
    kapital = st.number_input("Twój kapitał (PLN):", value=10000.0, step=1000.0)
    st.info(f"Monitorowanie portfela: {kapital:,.2f} PLN")

# Wczytywanie tickerów
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        symbols = [s.strip() for s in f.read().split(",") if s.strip()]
else: symbols = ["AAPL", "TSLA"]

# Pobieranie danych
results = []
for sym in symbols:
    res = fetch_analysis_data(sym)
    if res: results.append(res)

# --- RANKING TOP 10 ---
st.subheader("🔥 TOP 10 SPÓŁEK (Ranking RSI)")
top_10 = sorted(results, key=lambda x: x['rsi'])[:10]
t_cols = st.columns(5)
for i, r in enumerate(top_10):
    with t_cols[i % 5]:
        st.markdown(f"""
        <div class="neon-card {r['vc']}" style="text-align:center;">
            <b>{r['s']}</b><br><small>{r['p']:.2f}</small><br>
            <div style="font-size:0.8rem; margin-top:5px;">{r['v']}</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# --- LISTA SZCZEGÓŁOWA ---
for r in results:
    with st.container():
        st.markdown(f'<div class="neon-card {r["vc"]}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.5, 1])
        
        with c1:
            st.markdown(f"### {r['s']} | {r['v']}")
            st.metric("Cena Bieżąca", f"{r['p']:.2f} USD")
            st.markdown(f"""
                <div class="metric-grid">
                    <div><span class="neon-label">Szczyt 52T</span><br><span class="neon-value">{r['h52']:.2f}</span></div>
                    <div><span class="neon-label">Dołek 52T</span><br><span class="neon-value">{r['l52']:.2f}</span></div>
                    <div><span class="neon-label">RSI (14)</span><br><span class="neon-value">{r['rsi']:.1f}</span></div>
                    <div><span class="neon-label">Pivot</span><br><span class="neon-value">{r['pivot']:.2f}</span></div>
                </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown("<span class="neon-label">AI STRATEGIA (SL/TP & ŚWIECE)</span>", unsafe_allow_html=True)
            if st.button(f"GENERUJ ANALIZĘ AI", key=f"ai_{r['s']}"):
                st.info(get_ai_pro_analysis(r))
            
            st.markdown("<span class="neon-label">OSTATNIE WIADOMOŚCI</span>", unsafe_allow_html=True)
            for n in r['news']:
                st.markdown(f"• [{n['title'][:60]}...]({n['link']})")

        with c3:
            fig = go.Figure(data=[go.Candlestick(x=r['df'].index[-30:], open=r['df']['Open'][-30:],
                            high=r['df']['High'][-30:], low=r['df']['Low'][-30:], close=r['df']['Close'][-30:])])
            fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}")

        st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<center><small>AI ALPHA MONSTER PRO v72 © 2026 | Odświeżanie automatyczne co 5 min</small></center>", unsafe_allow_html=True)
