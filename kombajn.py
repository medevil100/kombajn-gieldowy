import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# SEKCJA 1: KONFIGURACJA ŚRODOWISKA I STANU
# ==============================================================================
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

st.set_page_config(
    page_title="AI ALPHA MONSTER PRO v71",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicjalizacja stanów sesji
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0
if 'ai_cache' not in st.session_state: st.session_state.ai_cache = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            c = f.read().strip()
            return c if c else "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS"

# ==============================================================================
# SEKCJA 2: ARCHITEKTURA STYLÓW CSS (NEON DARK)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    
    .stApp { background-color: #050505; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 25px; border-radius: 20px; border: 1px solid #30363d; 
        text-align: center; margin-bottom: 25px; min-height: 1100px;
        transition: 0.3s ease-in-out;
    }
    .main-card:hover { border-color: #58a6ff; box-shadow: 0 0 20px rgba(88, 166, 255, 0.1); }
    
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.8rem; text-shadow: 0 0 15px #00ff88; text-transform: uppercase; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.8rem; text-shadow: 0 0 15px #ff4b4b; text-transform: uppercase; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.5rem; }
    
    .pos-box { background: rgba(88, 166, 255, 0.08); border-radius: 15px; padding: 15px; margin: 15px 0; border: 1px solid #58a6ff; }
    .pos-val { font-size: 2.2rem; font-weight: 900; color: #ffffff; display: block; }
    
    .tech-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }
    .tech-item { background: rgba(255,255,255,0.03); padding: 10px; border-radius: 10px; border: 1px solid #21262d; text-align: left; }
    .tech-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .tech-value { font-size: 1rem; font-weight: bold; color: #ffffff; display: block; }
    
    .ai-box { 
        background: rgba(0, 255, 136, 0.03); border: 1px solid rgba(0, 255, 136, 0.2); 
        padding: 15px; border-radius: 12px; margin-top: 15px; text-align: left; font-size: 0.9rem; line-height: 1.5;
    }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.8rem; display: block; margin: 5px 0; text-align: left; }
    
    hr { border: 0; border-top: 1px solid #21262d; margin: 20px 0; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# SEKCJA 3: SILNIK ANALITYCZNY I AI
# ==============================================================================
def get_ai_opinion(symbol, data_summary):
    """Generuje analizę strategii za pomocą GPT-4o."""
    if not client: return "Brak klucza OpenAI. Skonfiguruj Secrets."
    
    cache_key = f"{symbol}_{datetime.now().strftime('%H')}"
    if cache_key in st.session_state.ai_cache:
        return st.session_state.ai_cache[cache_key]
    
    try:
        prompt = f"Analizuj spółkę {symbol}. Dane: {data_summary}. Napisz w 3 krótkich punktach: dlaczego warto/nie warto, poziom ryzyka i główny cel techniczny. Max 50 słów. Język polski."
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        opinion = response.choices[0].message.content
        st.session_state.ai_cache[cache_key] = opinion
        return opinion
    except:
        return "Błąd połączenia z AI."

def fetch_data(symbol):
    """Pobiera i przetwarza dane giełdowe."""
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        df = t.history(period="200d", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 50: return None
        
        # Wskaźniki Techniczne
        c = df['Close']
        sma50 = c.rolling(50).mean().iloc[-1]
        sma200 = c.rolling(200).mean().iloc[-1]
        
        # RSI
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR i Pozycja
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        curr = float(c.iloc[-1])
        risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.5
        shares = int(risk_val / sl_dist) if sl_dist > 0 else 0
        if shares * curr > st.session_state.risk_cap: shares = int(st.session_state.risk_cap / curr)

        # Werdykt
        if rsi < 35: verdict, v_class = "KUP 🔥", "sig-buy"
        elif rsi > 65: verdict, v_class = "SPRZEDAJ ⚠️", "sig-sell"
        else: verdict, v_class = "CZEKAJ ⏳", "sig-neutral"

        # News
        news = []
        try:
            for n in t.news[:2]: news.append({"t": n['title'][:55], "l": n['link']})
        except: pass

        return {
            "s": s, "p": curr, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "v": verdict, "vc": v_class, "sh": shares, "atr": atr,
            "sl": curr - sl_dist, "tp": curr + (atr * 3.5), "news": news, "df": df
        }
    except: return None

# ==============================================================================
# SEKCJA 4: WIZUALIZACJA (WYKRESY PLOTLY)
# ==============================================================================
def create_chart(df, symbol):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'], name="Cena"
    ))
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'].rolling(50).mean(), line=dict(color='#00ff88', width=1), name="SMA50"))
    fig.update_layout(
        template="plotly_dark", height=300, margin=dict(l=0, r=0, t=0, b=0),
        xaxis_rangeslider_visible=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False
    )
    return fig

# ==============================================================================
# SEKCJA 5: INTERFEJS UŻYTKOWNIKA
# ==============================================================================
def main():
    st.sidebar.image("https://flaticon.com", width=80)
    st.sidebar.title("ALPHA MONSTER v71")
    
    t_input = st.sidebar.text_area("Lista Tickerów (CSV):", load_tickers(), height=150)
    st.session_state.risk_cap = st.sidebar.number_input("Kapitał Portfela (PLN):", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.sidebar.slider("Ryzyko na transakcję (%):", 0.1, 5.0, st.session_state.risk_pct)
    
    if st.sidebar.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.session_state.ai_cache = {} # Reset cache AI przy zmianie listy
        st.rerun()

    st_autorefresh(interval=600000, key="monster_refresh")
    
    symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]
    
    # Nagłówek statystyk
    st.markdown(f"### 🚜 Monitorowanie {len(symbols)} spółek | Ryzyko: {st.session_state.risk_pct}% ({st.session_state.risk_cap * st.session_state.risk_pct / 100:.0f} PLN)")
    
    # Wielowątkowe pobieranie danych
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_data, symbols))
    
    # Renderowanie kart
    cols = st.columns(3)
    for idx, res in enumerate([r for r in results if r]):
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"""
                <div class="main-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:1.5rem; font-weight:900;">{res['s']}</span>
                        <span style="color:#8b949e;">{datetime.now().strftime('%H:%M')}</span>
                    </div>
                    <h1 style="color:#58a6ff; font-size:3.5rem; margin:10px 0;">{res['p']:.2f}<small style="font-size:1rem;"> USD</small></h1>
                    <div class="{res['vc']}">{res['v']}</div>
                    
                    <div class="pos-box">
                        <span class="tech-label">Sugerowana Pozycja</span>
                        <span class="pos-val">{res['sh']} <small style="font-size:1rem;">szt.</small></span>
                        <div style="display:flex; justify-content:space-between; margin-top:10px;">
                            <span style="color:#ff4b4b;">SL: {res['sl']:.2f}</span>
                            <span style="color:#00ff88;">TP: {res['tp']:.2f}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Wykres interaktywny
                st.plotly_chart(create_chart(res['df'], res['s']), use_container_width=True, config={'displayModeBar': False})
                
                # Grid Techniczny
                st.markdown(f"""
                    <div class="tech-grid">
                        <div class="tech-item"><span class="tech-label">RSI (14)</span><span class="tech-value">{res['rsi']:.1f}</span></div>
                        <div class="tech-item"><span class="tech-label">ATR (14)</span><span class="tech-value">{res['atr']:.2f}</span></div>
                        <div class="tech-item"><span class="tech-label">SMA 50</span><span class="tech-value">{res['sma50']:.2f}</span></div>
                        <div class="tech-item"><span class="tech-label">SMA 200</span><span class="tech-value">{res['sma200']:.2f}</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Analiza AI
                data_summary = f"Cena: {res['p']}, RSI: {res['rsi']}, SMA50: {res['sma50']}, ATR: {res['atr']}"
                opinion = get_ai_opinion(res['s'], data_summary)
                st.markdown(f"""
                    <div class="ai-box">
                        <b style="color:#00ff88;">🤖 ANALIZA AI:</b><br>{opinion}
                    </div>
                    <div style="margin-top:15px; border-top: 1px solid #21262d; padding-top:10px;">
                        {''.join([f'<a class="news-link" href="{n["l"]}" target="_blank">● {n["t"]}...</a>' for n in res['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # Footer
    st.markdown("<br><hr><center><small style='color:#30363d;'>AI ALPHA MONSTER PRO v71 © 2024 | Powered by GPT-4o & yFinance</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

# ==============================================================================
# KONIEC KODU - DOKUMENTACJA FUNKCJI:
# 1. Automatyczne odświeżanie (co 10 min) zapobiega timeoutom.
# 2. Wykresy Plotly są responsywne i dark-mode.
# 3. OpenAI GPT-4o analizuje dane techniczne w czasie rzeczywistym.
# 4. ThreadPoolExecutor pozwala na błyskawiczną analizę wielu spółek naraz.
# 5. Position Sizing bierze pod uwagę zmienność ATR dla bezpieczeństwa kapitału.
# ==============================================================================
