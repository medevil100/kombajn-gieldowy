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

# Autorefresh co 5 minut
st_autorefresh(interval=300000, key="data_refresh")

# --- SYSTEM STYLÓW NEON (Poprawiony rozmiar i stabilność) ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .neon-card { 
        background: rgba(13, 17, 23, 0.95); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        margin-bottom: 25px; transition: 0.3s;
        min-height: 500px; /* Zwiększona minimalna wysokość */
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 20px rgba(0,255,136,0.3); color: #00ff88; }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 20px rgba(255,75,75,0.3); color: #ff4b4b; }
    .hold { border: 2px solid #8b949e !important; color: #8b949e; }
    .neon-label { font-size: 0.85rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 8px; }
    .neon-value { font-size: 1.2rem; font-weight: bold; color: #ffffff; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }
    
    /* Naprawa szerokości kontenerów Streamlit */
    [data-testid="stVerticalBlock"] > div:has(div.neon-card) {
        width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE SILNIKA ---
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

        # News - BEZPIECZNE POBIERANIE (Naprawa KeyError)
        raw_news = t.news if hasattr(t, 'news') else []
        news = []
        for n in raw_news[:3]:
            title = n.get('title', 'Brak tytułu') # Użycie .get() zapobiega KeyError
            link = n.get('link', '#')
            news.append({"title": title, "link": link})

        return {
            "s": symbol.upper(), "p": curr, "rsi": rsi, "pivot": pivot,
            "h52": high_52, "l52": low_52, "v": v_text, "vc": v_class, "news": news, "df": df
        }
    except: return None

def get_ai_pro_analysis(data):
    if not client: return "Brak klucza OpenAI w skrytce."
    prompt = f"Analiza {data['s']}: Cena {data['p']:.2f}, RSI {data['rsi']:.1f}, Pivot {data['pivot']:.2f}. Podaj SL, TP i strategię (3 punkty, konkret)."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        return response.choices[0].message.content
    except: return "Błąd AI."

# --- INTERFEJS ---
with st.sidebar:
    st.title("🚜 MONSTER v72")
    st.write(f"Ostatnia aktualizacja: {datetime.now().strftime('%H:%M:%S')}")
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

# Wczytywanie i pobieranie
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        symbols = list(set([s.strip() for s in f.read().split(",") if s.strip()]))
else: symbols = ["AAPL", "TSLA", "NVDA"]

results = [res for sym in symbols if (res := fetch_analysis_data(sym))]

# --- RENDEROWANIE ---
if results:
    st.subheader("🔥 TOP SYGNAŁY")
    top_10 = sorted(results, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(min(len(top_10), 5))
    for i, r in enumerate(top_10):
        with t_cols[i % 5]:
            st.markdown(f'<div class="neon-card {r["vc"]}" style="text-align:center; min-height:150px; padding:15px;"><b>{r["s"]}</b><br>{r["p"]:.2f}<br><small>{r["v"]}</small></div>', unsafe_allow_html=True)

    st.divider()

    for r in results:
        with st.container():
            st.markdown(f"<div class='neon-card {r['vc']}'>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 1.2, 1.2]) # Zmienione proporcje dla większego okna
            
            with c1:
                st.markdown(f"### {r['s']} | {r['v']}")
                st.metric("CENA", f"{r['p']:.2f}")
                st.markdown(f"""<div class="metric-grid">
                    <div><span class='neon-label'>Max 52T</span><span class='neon-value'>{r['h52']:.2f}</span></div>
                    <div><span class='neon-label'>Min 52T</span><span class='neon-value'>{r['l52']:.2f}</span></div>
                    <div><span class='neon-label'>RSI</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                    <div><span class='neon-label'>Pivot</span><span class='neon-value'>{r['pivot']:.2f}</span></div>
                </div>""", unsafe_allow_html=True)

            with c2:
                st.markdown("<span class='neon-label'>STRATEGIA AI</span>", unsafe_allow_html=True)
                if st.button(f"GENERUJ AI", key=f"ai_{r['s']}"):
                    st.info(get_ai_pro_analysis(r))
                st.markdown("<br><span class='neon-label'>NEWS</span>", unsafe_allow_html=True)
                for n in r['news']:
                    st.markdown(f"• [{n['title'][:55]}...]({n['link']})")

            with c3:
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index[-30:], open=r['df']['Open'][-30:], high=r['df']['High'][-30:], low=r['df']['Low'][-30:], close=r['df']['Close'][-30:])])
                fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}")

            st.markdown('</div>', unsafe_allow_html=True)
