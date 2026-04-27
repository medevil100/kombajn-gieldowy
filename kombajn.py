import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA ŚRODOWISKA I BAZY DANYCH
# ==============================================================================
DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

st.set_page_config(
    page_title="AI ALPHA MONSTER v75 ULTRA",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicjalizacja stanów sesji (pamięć podręczna aplikacji)
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0
if 'ai_results' not in st.session_state: st.session_state.ai_results = {}

def load_tickers():
    """Wczytywanie listy symboli z pliku tekstowego."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "NVDA, TSLA, BTC-USD, PKO.WA, CDR.WA"
        except: pass
    return "NVDA, TSLA, BTC-USD, PKO.WA, CDR.WA"

# ==============================================================================
# 2. ARCHITEKTURA STYLÓW CSS (NEON DARK MODE)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://googleapis.com');
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    .neon-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 40px; border-radius: 30px; border: 1px solid #30363d; 
        margin-bottom: 50px; transition: 0.4s ease;
        display: flex; flex-direction: column; justify-content: space-between;
        min-height: 900px;
    }
    .buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 30px rgba(0,255,136,0.25); }
    .sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 30px rgba(255,75,75,0.25); }
    .hold { border: 1px solid #30363d !important; }
    
    .metric-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }
    .neon-label { font-size: 0.9rem; color: #8b949e; text-transform: uppercase; letter-spacing: 2px; }
    .neon-value { font-size: 1.4rem; font-weight: 900; color: #ffffff; display: block; margin-top: 5px; }
    
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.8rem; text-shadow: 0 0 10px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.8rem; text-shadow: 0 0 10px #ff4b4b; }
    
    .ai-box { 
        background: rgba(0, 255, 136, 0.05); border: 1px solid rgba(0, 255, 136, 0.3); 
        padding: 20px; border-radius: 15px; margin-top: 20px; text-align: left; font-size: 0.95rem;
    }
    .news-item { border-bottom: 1px solid #21262d; padding: 10px 0; font-size: 0.85rem; color: #58a6ff; text-decoration: none; display: block; }
    .block-container { max-width: 98% !important; padding-top: 1rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. PANCERNY SILNIK ANALITYCZNY (WSKAŹNIKI I DANE)
# ==============================================================================
def get_monster_analysis(symbol):
    try:
        s = symbol.strip().upper()
        t = yf.Ticker(s)
        # Pobranie 2 lat danych dla SMA200
        df_raw = t.history(period="2y", interval="1d", auto_adjust=True)
        
        if df_raw.empty or len(df_raw) < 200: return None
        
        # Średnie Kroczące
        df_raw['SMA20'] = df_raw['Close'].rolling(window=20).mean()
        df_raw['SMA50'] = df_raw['Close'].rolling(window=50).mean()
        df_raw['SMA100'] = df_raw['Close'].rolling(window=100).mean()
        df_raw['SMA200'] = df_raw['Close'].rolling(window=200).mean()
        
        curr = df_raw['Close'].iloc[-1]
        
        # Ekstrema 52-tygodniowe
        df_52 = df_raw.tail(252)
        h52, l52 = df_52['High'].max(), df_52['Low'].min()
        
        # MACD
        exp1 = df_raw['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df_raw['Close'].ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        
        # RSI 14
        delta = df_raw['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Pivot Points
        prev = df_raw.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        r1, s1 = (2 * pp) - prev['Low'], (2 * pp) - prev['High']
        
        # ATR i Position Sizing
        tr = pd.concat([df_raw['High']-df_raw['Low'], (df_raw['High']-df_raw['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        shares = int(risk_cash / (atr * 1.5)) if atr > 0 else 0
        
        # News (Fix)
        m_news = []
        try:
            raw_news = t.get_news()
            for n in raw_news[:3]:
                m_news.append({"title": n.get('title', 'Market Update'), "link": n.get('link', '#')})
        except: m_news = [{"title": "Brak bieżących newsów", "link": "#"}]

        # Werdykt
        if rsi < 32: verd, vcl = "KUP 🔥", "buy"
        elif rsi > 68: verd, vcl = "SPRZEDAJ ⚠️", "sell"
        else: verd, vcl = "TRZYMAJ ⏳", "hold"

        return {
            "s": s, "p": curr, "rsi": rsi, "macd": macd_line.iloc[-1], "pp": pp,
            "h52": h52, "l52": l52, "shares": shares, "sl": curr - (atr * 1.5),
            "tp": curr + (atr * 3), "sma20": df_raw['SMA20'].iloc[-1],
            "sma50": df_raw['SMA50'].iloc[-1], "sma100": df_raw['SMA100'].iloc[-1],
            "sma200": df_raw['SMA200'].iloc[-1], "news": m_news, "df": df_raw.tail(100), "v": verd, "vc": vcl
        }
    except Exception as e: return None

# ==============================================================================
# 4. MODUŁ AI (GPT-4o EXPERT ANALYZER)
# ==============================================================================
def get_ai_strategy(data):
    if not client: return "Brak klucza OpenAI. Dodaj go w Secrets."
    prompt = f"""
    Ekspert Giełdowy. Analiza {data['s']}:
    Aktualna Cena: {data['p']:.2f}, RSI: {data['rsi']:.1f}, MACD: {data['macd']:.4f}, Pivot: {data['pp']:.2f}.
    Średnie: SMA20: {data['sma20']:.2f}, SMA50: {data['sma50']:.2f}, SMA200: {data['sma200']:.2f}.
    Szczyt 52T: {data['h52']:.2f}, Dołek 52T: {data['l52']:.2f}.
    Zasady: Podaj konkretny SL i TP. Analiza świec z 1 dnia. Strategia wejścia/wyjścia (3 pkt). 
    Maksymalnie konkretnie, bez lania wody. Język polski.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=600
        )
        return response.choices[0].message.content
    except: return "AI jest obecnie przeciążone. Spróbuj za chwilę."

# ==============================================================================
# 5. UI I RENDEROWANIE INTERFEJSU
# ==============================================================================
def main():
    # Sidebar
    st.sidebar.title("🚜 KONTROLA MONSTERA")
    st.sidebar.write(f"Zegar: {datetime.now().strftime('%H:%M:%S')}")
    
    t_input = st.sidebar.text_area("Lista Symboli (CSV):", load_tickers(), height=150)
    st.session_state.risk_cap = st.sidebar.number_input("Kapitał Portfela (PLN):", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.sidebar.slider("Ryzyko na transakcję (%):", 0.1, 5.0, st.session_state.risk_pct)
    
    refresh_val = st.sidebar.slider("Odświeżanie (min):", 1, 15, 5)
    st_autorefresh(interval=refresh_val * 60000, key="global_refresh")
    
    if st.sidebar.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.rerun()

    symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]
    
    # Wielowątkowe pobieranie danych (Speed)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_monster_analysis, symbols))
    results = [r for r in results if r]

    # --- TOP 10 RANKING ---
    st.subheader("🔥 TOP SYGNAŁY (Ranking okazji RSI)")
    top_10 = sorted(results, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, r in enumerate(top_10):
        with top_cols[i % 5]:
            st.markdown(f"""
            <div class="neon-card {r['vc']}" style="min-height:150px; padding:20px; text-align:center;">
                <b style="font-size:1.2rem;">{r['s']}</b><br>
                <span style="font-size:1.1rem; color:#58a6ff;">{r['p']:.2f} USD</span><br>
                <small>{r['v']}</small>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA (KARTY ULTRA) ---
    for r in results:
        with st.container():
            st.markdown(f"<div class='neon-card {r['vc']}'>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 1.2, 1.8])
            
            with c1:
                st.markdown(f"### {r['s']} | <span class='sig-{'buy' if r['vc']=='buy' else 'sell' if r['vc']=='sell' else ''}'>{r['v']}</span>", unsafe_allow_html=True)
                st.metric("AKTUALNA CENA", f"{r['p']:.2f}")
                st.markdown(f"""
                    <div class="metric-row">
                        <div><span class='neon-label'>Max 52T</span><span class='neon-value'>{r['h52']:.2f}</span></div>
                        <div><span class='neon-label'>Min 52T</span><span class='neon-value'>{r['l52']:.2f}</span></div>
                        <div><span class='neon-label'>RSI (14)</span><span class='neon-value'>{r['rsi']:.1f}</span></div>
                        <div><span class='neon-label'>Pivot</span><span class='neon-value'>{r['pp']:.2f}</span></div>
                        <div><span class='neon-label'>SMA 50</span><span class='neon-value'>{r['sma50']:.2f}</span></div>
                        <div><span class='neon-label'>SMA 200</span><span class='neon-value'>{r['sma200']:.2f}</span></div>
                    </div>
                """, unsafe_allow_html=True)

            with c2:
                st.markdown("<span class='neon-label'>EKSPERT AI & STRATEGIA</span>", unsafe_allow_html=True)
                if st.button(f"GENERUJ RAPORT AI", key=f"ai_{r['s']}"):
                    with st.spinner("AI analizuje wykres..."):
                        st.info(get_ai_strategy(r))
                
                st.markdown("<br><span class='neon-label'>POZYCJA I RYZYKO</span>", unsafe_allow_html=True)
                st.write(f"Sugerowana ilość: **{r['shares']} szt.**")
                st.write(f"Stop Loss: **{r['sl']:.2f}** | Take Profit: **{r['tp']:.2f}**")
                
                st.markdown("<br><span class='neon-label'>NEWSY</span>", unsafe_allow_html=True)
                for n in r['news']:
                    st.markdown(f"<a class='news-item' href='{n['link']}' target='_blank'>● {n['title']}</a>", unsafe_allow_html=True)

            with c3:
                # Rozbudowany Wykres Plotly
                fig = go.Figure(data=[go.Candlestick(x=r['df'].index, open=r['df']['Open'], high=r['df']['High'], low=r['df']['Low'], close=r['df']['Close'], name="Cena")])
                
                # Dodanie Średnich Kroczących
                colors = {'SMA20': 'yellow', 'SMA50': 'orange', 'SMA100': 'cyan', 'SMA200': 'red'}
                for sma in ['SMA20', 'SMA50', 'SMA100', 'SMA200']:
                    fig.add_trace(go.Scatter(x=r['df'].index, y=r['df'][sma], line=dict(width=1.5, color=colors[sma]), name=sma))
                
                fig.update_layout(
                    template="plotly_dark", height=550, margin=dict(l=0,r=0,t=0,b=0),
                    xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{r['s']}")

            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<center><small style='color:#333;'>AI ALPHA MONSTER PRO v75 ULTRA © 2026 | Odświeżanie: 5 min</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
