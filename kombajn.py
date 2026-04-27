import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime

# --- 1. KONFIGURACJA ŚRODOWISKA ---
st.set_page_config(page_title="AI ALPHA MONSTER v72 PRO", layout="wide")
DB_FILE = "moje_spolki.txt"

# Pobranie klucza OpenAI z Secrets
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

# --- 2. STYLE WIZUALNE (Powiększone okna i Neon) ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .neon-card { 
        background: rgba(13, 17, 23, 0.98); 
        padding: 35px; border-radius: 20px; border: 1px solid #30363d; 
        margin-bottom: 30px; transition: 0.3s;
        width: 100%; min-height: 600px;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 25px rgba(0,255,136,0.35); color: #00ff88; }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 25px rgba(255,75,75,0.35); color: #ff4b4b; }
    .hold { border: 2px solid #8b949e !important; color: #8b949e; }
    .neon-label { font-size: 0.9rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1.5px; display: block; margin-bottom: 10px; }
    .neon-value { font-size: 1.3rem; font-weight: bold; color: #ffffff; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 25px 0; }
    .stMetric { background: #161b22; padding: 15px; border-radius: 12px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALITYCZNY ---
def fetch_analysis_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        
        curr = df['Close'].iloc[-1]
        high_52 = df['High'].max()
        low_52 = df['Low'].min()
        
        prev = df.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        if rsi < 35: v_text, v_class = "KUP 🔥", "buy"
        elif rsi > 65: v_text, v_class = "SPRZEDAJ ⚠️", "sell"
        else: v_text, v_class = "TRZYMAJ ⏳", "hold"

        # News - Naprawione pobieranie
        raw_news = t.news if hasattr(t, 'news') else []
        news = []
        for n in raw_news[:3]:
            news.append({"title": n.get('title', 'Brak tytułu'), "link": n.get('link', '#')})

        return {
            "s": symbol.upper(), "p": curr, "rsi": rsi, "pivot": pivot,
            "h52": high_52, "l52": low_52, "v": v_text, "vc": v_class, "news": news, "df": df
        }
    except: return None

def get_ai_pro_analysis(data):
    if not client: return "Brak klucza OpenAI."
    prompt = f"Giełda: {data['s']}. Cena {data['p']:.2f}, RSI {data['rsi']:.1f}, Pivot {data['pivot']:.2f}. Podaj SL, TP i 3-punktową strategię. Nie ucinaj wypowiedzi."
    try:
        # Zwiększono max_tokens, aby zapobiec ucinaniu tekstu
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content
    except: return "Błąd generowania AI."

# --- 4. PANEL STEROWANIA ---
with st.sidebar:
    st.title("🚜 KONTROLA MONSTERA")
    st.write(f"Aktualizacja: **{datetime.now().strftime('%H:%M:%S')}**")
    
    # Regulacja odświeżania
    refresh_min = st.slider("Częstotliwość odświeżania (min)", 1, 15, 5)
    st_autorefresh(interval=refresh_min * 60000, key="data_refresh")
    
    new_ticker = st.text_input("Dodaj spółkę:")
    if st.button("DODAJ I ZAPISZ"):
        if new_ticker:
            with open(DB_FILE, "a") as f: f.write(f"{new_ticker.strip().upper()},")
            st.rerun()
    if st.button("WYCZYŚĆ LISTĘ"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()
    
    st.divider()
    kapital = st.number_input("Twój kapitał (PLN):", value=10000.0)

# --- 5. LOGIKA WYŚWIETLANIA ---
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        symbols = list(set([s.strip() for s in f.read().split(",") if s.strip()]))
else: symbols = ["AAPL", "TSLA", "NVDA"]

results = [res for sym in symbols if (res := fetch_analysis_data(sym))]

if results:
    st.subheader("🔥 TOP SYGNAŁY")
    top_10 = sorted(results, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(min(len(top_10), 5))
    for i, r in enumerate(top_10):
        with t_cols[i % 5]:
            st.markdown(f'<div class="neon-card {r["vc"]}" style="min-height:120px; padding:15px; text-align:center;"><b>{r["s"]}</b><br>{r["p"]:.2f}<br>{r["v"]}</div>', unsafe_allow_html=True)

    st.divider()

    for r in results:
        with st.container():
            st.markdown(f"<div class='neon-card {r['vc']}'>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 1.4, 1.4])
            
            with c1:
                st.markdown(f"### {r['s']} | {r['v']}")
                st.metric("AKTUALNA CENA", f"{r['p']:.2f}")
                st.markdown(f"""<div class="metric-grid">
                    <div><span class='neon-label'>Szczyt 52T</span><span class='neon-value'>{r['h52']:.2f}</span></div>
                    <div><span class='neon-label'>Dołek 52T</span><span class='neon-value'>{r['l52']:.2f}</span></div>
                    <div><span class='neon-label'>Wskaźnik RSI</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                    <div><span class='neon-label'>Punkt Pivot</span><span class='neon-value'>{r['pivot']:.2f}</span></div>
                </div>""", unsafe_allow_html=True)

            with c2:
                st.markdown("<span class='neon-label'>ANALIZA AI I STRATEGIA</span>", unsafe_allow_html=True)
                if st.button(f"GENERUJ RAPORT AI", key=f"ai_{r['s']}"):
                    st.info(get_ai_pro_analysis(r))
                st.markdown("<br><span class='neon-label'>WIADOMOŚCI RYNKOWE</span>", unsafe_allow_html=True)
                if r['news']:
                    for n in r['news']:
                        st.markdown(f"• [{n['title'][:65]}...]({n['link']})")
                else: st.write("Brak nowych newsów.")

            with c3:
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index[-40:], open=r['df']['Open'][-40:], high=r['df']['High'][-40:], low=r['df']['Low'][-40:], close=r['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}")

            st.markdown('</div>', unsafe_allow_html=True)
