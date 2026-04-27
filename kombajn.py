import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import os
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. ARCHITEKTURA SYSTEMU I LOGOWANIE
# ==============================================================================
DB_FILE = "moje_spolki.txt"
LOG_FILE = "monster_log.txt"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def setup_client():
    key = st.secrets.get("OPENAI_API_KEY", "")
    if key:
        return OpenAI(api_key=key)
    return None

client = setup_client()

# ==============================================================================
# 2. KONFIGURACJA STRONY I STYLE NEON
# ==============================================================================
st.set_page_config(
    page_title="AI ALPHA MONSTER v79 ULTRA PRO",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

def apply_custom_styles():
    st.markdown("""
        <style>
        @import url('https://googleapis.com');
        
        .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
        
        /* Kontener Karty Spółki */
        .neon-card { 
            background: linear-gradient(145deg, #0d1117, #020202); 
            padding: 40px; 
            border-radius: 30px; 
            border: 1px solid #30363d; 
            margin-bottom: 50px; 
            min-height: 1200px; 
            width: 100%;
            transition: all 0.4s ease-in-out;
            position: relative;
            overflow: hidden;
        }
        
        .neon-card:hover {
            border-color: #58a6ff;
            box-shadow: 0 0 40px rgba(88, 166, 255, 0.15);
            transform: translateY(-5px);
        }

        /* Statusy Neonowe */
        .buy { border: 2px solid #00ff88 !important; box-shadow: inset 0 0 20px rgba(0,255,136,0.1); }
        .sell { border: 2px solid #ff4b4b !important; box-shadow: inset 0 0 20px rgba(255,75,75,0.1); }
        .hold { border: 1px solid #30363d !important; }
        
        /* Etykiety i Wartości */
        .neon-label { 
            font-size: 0.85rem; 
            color: #8b949e; 
            text-transform: uppercase; 
            letter-spacing: 2px; 
            display: block; 
            margin-top: 15px;
        }
        
        .neon-value { 
            font-size: 1.4rem; 
            font-weight: 900; 
            color: #ffffff; 
            display: block; 
            margin-bottom: 5px;
            text-shadow: 0 0 5px rgba(255,255,255,0.2);
        }
        
        .sig-text-buy { color: #00ff88; font-weight: 900; font-size: 2rem; text-transform: uppercase; }
        .sig-text-sell { color: #ff4b4b; font-weight: 900; font-size: 2rem; text-transform: uppercase; }
        
        /* Siatki */
        .metric-grid { 
            display: grid; 
            grid-template-columns: 1fr 1fr; 
            gap: 20px; 
            margin: 25px 0; 
            background: rgba(255,255,255,0.02);
            padding: 20px;
            border-radius: 20px;
        }
        
        .pos-box {
            background: rgba(88, 166, 255, 0.08); 
            padding: 25px; 
            border-radius: 20px; 
            border: 1px solid #58a6ff;
            margin: 25px 0;
            text-align: center;
        }

        .news-link {
            color: #58a6ff;
            text-decoration: none;
            font-size: 0.9rem;
            display: block;
            margin-bottom: 12px;
            padding: 10px;
            background: rgba(88, 166, 255, 0.05);
            border-radius: 10px;
        }
        
        .news-link:hover {
            background: rgba(88, 166, 255, 0.1);
            color: #ffffff;
        }

        .block-container { max-width: 98% !important; padding-top: 1.5rem !important; }
        </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. SILNIK FINANSOWY I ANALIZA ŚWIEC
# ==============================================================================
def detect_candle_pattern(df):
    """Prosty skaner formacji świecowych dla ostatniej świecy."""
    try:
        last = df.iloc[-1]
        body = abs(last['Open'] - last['Close'])
        range_tot = last['High'] - last['Low']
        if range_tot == 0: return "Brak ruchu"
        
        upper_wick = last['High'] - max(last['Open'], last['Close'])
        lower_wick = min(last['Open'], last['Close']) - last['Low']
        
        if lower_wick > body * 2 and upper_wick < body: return "HAMMER (Odbicie?) 🔨"
        if upper_wick > body * 2 and lower_wick < body: return "SHOOTING STAR (Opór?) ☄️"
        if body < (range_tot * 0.1): return "DOJI (Niezdecydowanie) ⚖️"
        return "Brak wyraźnej formacji"
    except:
        return "Błąd skanera"

def fetch_ticker_pro_data(symbol):
    """Główny silnik pobierania danych z Yahoo Finance."""
    try:
        time.sleep(0.2) # Ochrona przed banem
        s_clean = symbol.strip().upper()
        ticker = yf.Ticker(s_clean)
        
        # Pobieramy 2 lata by SMA 200 było stabilne
        df = ticker.history(period="2y", interval="1d", auto_adjust=True)
        
        if df.empty or len(df) < 200:
            logging.warning(f"Brak wystarczających danych dla {s_clean}")
            return None
        
        # Oczyszczanie NaN
        df['Close'] = df['Close'].replace(0, np.nan).ffill()
        c = df['Close']
        curr = c.iloc[-1]
        
        # Średnie Kroczące (SMA)
        s20 = c.rolling(20).mean().iloc[-1]
        s50 = c.rolling(50).mean().iloc[-1]
        s100 = c.rolling(100).mean().iloc[-1]
        s200 = c.rolling(200).mean().iloc[-1]
        
        # Wskaźnik RSI (14)
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Wskaźnik MACD
        e12 = c.ewm(span=12, adjust=False).mean()
        e26 = c.ewm(span=26, adjust=False).mean()
        macd_val = (e12 - e26).iloc[-1]
        
        # Ekstrema 52-tygodniowe
        df_52 = df.tail(252)
        h52 = df_52['High'].max()
        l52 = df_52['Low'].min()
        
        # Pivot Points
        prev_day = df.iloc[-2]
        pp = (prev_day['High'] + prev_day['Low'] + prev_day['Close']) / 3
        r1 = (2 * pp) - prev_day['Low']
        s1 = (2 * pp) - prev_day['High']
        
        # Risk Management (ATR)
        tr = pd.concat([df['High']-df['Low'], (df['High']-c.shift()).abs(), (df['Low']-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        risk_pln = st.session_state.get('risk_cap', 10000) * (st.session_state.get('risk_pct', 1.0) / 100)
        # Przyjmujemy SL na poziomie 1.5x ATR
        stop_loss_dist = atr * 1.5
        shares = int(risk_pln / stop_loss_dist) if stop_loss_dist > 0 else 0
        
        # Werdykt
        if rsi < 33:
            v_text, v_class = "KUP 🔥", "buy"
        elif rsi > 67:
            v_text, v_class = "SPRZEDAJ ⚠️", "sell"
        else:
            v_text, v_class = "CZEKAJ ⏳", "hold"

        # Pobieranie Newsów
        processed_news = []
        try:
            raw_news = ticker.news
            for n in raw_news[:3]:
                title = n.get('title')
                if title:
                    processed_news.append({"t": str(title)[:60], "l": n.get('link', '#')})
        except:
            pass

        return {
            "symbol": s_clean,
            "price": curr,
            "rsi": rsi,
            "macd": macd_val,
            "pp": pp,
            "r1": r1,
            "s1": s1,
            "h52": h52,
            "l52": l52,
            "sma20": s20,
            "sma50": s50,
            "sma100": s100,
            "sma200": s200,
            "atr": atr,
            "shares": shares,
            "sl": curr - stop_loss_dist,
            "tp": curr + (atr * 3.5),
            "verdict": v_text,
            "class": v_class,
            "news": processed_news,
            "df_plot": df.tail(100),
            "pattern": detect_candle_pattern(df)
        }
    except Exception as e:
        logging.error(f"Błąd krytyczny dla {symbol}: {e}")
        return None

# ==============================================================================
# 4. MODUŁ AI STRATEGY
# ==============================================================================
def get_ai_pro_strategy(data):
    """Zaawansowany prompt wysyłający pełną matrycę danych do AI."""
    if not client:
        return "Brak klucza OpenAI w Secrets. Skonfiguruj 'OPENAI_API_KEY'."
    
    prompt = f"""
    DZIAŁAJ JAKO EKSPERT QUANT: Przeanalizuj spółkę {data['symbol']}.
    DANE TECHNICZNE:
    - Cena: {data['price']:.2f}
    - RSI: {data['rsi']:.1f}
    - MACD: {data['macd']:.4f}
    - Formacja świecowa: {data['pattern']}
    - SMA20: {data['sma20']:.2f}, SMA50: {data['sma50']:.2f}, SMA200: {data['sma200']:.2f}
    - Ekstrema 52T: {data['l52']:.2f} (min) / {data['h52']:.2f} (max)
    - Pivot Point: {data['pp']:.2f}
    
    ZADANIE:
    1. Podaj precyzyjny Stop Loss i Take Profit na podstawie tych danych.
    2. Określ krótkoterminowy trend.
    3. Podaj strategię wejścia w 3 konkretnych punktach.
    BEZ LANIA WODY. MAKSYMALNIE KONKRETNIE. JĘZYK POLSKI.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Jesteś analitykiem giełdowym HFT."},
                      {"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Błąd AI: {str(e)}"

# ==============================================================================
# 5. INTERFEJS UŻYTKOWNIKA I PĘTLA GŁÓWNA
# ==============================================================================
def main():
    apply_custom_styles()
    
    # --- PANEL BOCZNY ---
    with st.sidebar:
        st.title("🚜 MONSTER v79")
        st.subheader("Ustawienia Systemu")
        
        refresh_min = st.slider("Odświeżanie danych (min)", 1, 30, 5)
        st_autorefresh(interval=refresh_min * 60000, key="data_refresh_token")
        
        st.divider()
        
        if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0
        st.session_state.risk_cap = st.number_input("Twój Kapitał (PLN):", value=st.session_state.risk_cap, step=1000.0)
        
        if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0
        st.session_state.risk_pct = st.slider("Ryzyko na transakcję (%)", 0.1, 10.0, st.session_state.risk_pct)
        
        st.divider()
        
        def load_raw_tickers():
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "r") as f: return f.read()
            return "NVDA, TSLA, AAPL, PKO.WA, BTC-USD"

        t_area = st.text_area("Lista Symboli (oddziel przecinkiem):", value=load_raw_tickers(), height=250)
        
        if st.button("💾 ZAPISZ I ANALIZUJ"):
            with open(DB_FILE, "w") as f: f.write(t_area)
            st.toast("Zapisano listę!", icon="✅")
            time.sleep(1)
            st.rerun()

        st.info(f"Ostatni przebieg: {datetime.now().strftime('%H:%M:%S')}")

    # --- PRZETWARZANIE DANYCH ---
    symbols = [s.strip().upper() for s in t_area.split(",") if s.strip()]
    
    st.markdown(f"### 🚜 Monitorowanie {len(symbols)} spółek")
    
    # Podział na zakładki dla stabilności (Paczki po 6)
    num_groups = (len(symbols) // 6) + (1 if len(symbols) % 6 > 0 else 0)
    ticker_groups = [symbols[i*6:(i+1)*6] for i in range(num_groups)]
    
    tab_titles = [f"Grupa {i+1}" for i in range(num_groups)]
    if not tab_titles: tab_titles = ["Brak danych"]
    
    tabs = st.tabs(tab_titles)

    for i, tab in enumerate(tabs):
        with tab:
            batch = ticker_groups[i]
            
            # Wielowątkowość dla szybkości
            with ThreadPoolExecutor(max_workers=6) as executor:
                results = list(executor.map(fetch_ticker_pro_data, batch))
            
            results = [r for r in results if r is not None]
            
            # Grid 3 kolumny
            cols = st.columns(3)
            
            for idx, r in enumerate(results):
                col_idx = idx % 3
                with cols[col_idx]:
                    # Dynamiczna klasa neonowa
                    st.markdown(f"""
                        <div class="neon-card {r['class']}">
                            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                                <div>
                                    <h3 style="margin:0; opacity:0.6;">{r['symbol']}</h3>
                                    <h1 style="color:#58a6ff; margin:10px 0; font-size:3rem;">{r['price']:.2f}</h1>
                                </div>
                                <div class="sig-text-{r['class']}">{r['verdict']}</div>
                            </div>
                            
                            <div class="pos-box">
                                <span class="neon-label">Formacja Świecowa</span>
                                <span style="font-weight:bold; color:#ffcc00;">{r['pattern']}</span>
                                <hr style="border:0; border-top:1px solid rgba(88,166,255,0.2); margin:15px 0;">
                                <span class="neon-label">Sugerowana Pozycja</span>
                                <span class="neon-value" style="font-size:2rem; color:#58a6ff;">{r['shares']} SZT.</span>
                                <div style="display:flex; justify-content:space-around; margin-top:10px;">
                                    <span style="color:#ff4b4b;">SL: {r['sl']:.2f}</span>
                                    <span style="color:#00ff88;">TP: {r['tp']:.2f}</span>
                                </div>
                            </div>

                            <div class="metric-grid">
                                <div>
                                    <span class="neon-label">RSI (14)</span>
                                    <span class="neon-value">{r['rsi']:.1f}</span>
                                </div>
                                <div>
                                    <span class="neon-label">MACD</span>
                                    <span class="neon-value">{r['macd']:.4f}</span>
                                </div>
                                <div>
                                    <span class="neon-label">SMA 50</span>
                                    <span class="neon-value">{r['sma50']:.2f}</span>
                                </div>
                                <div>
                                    <span class="neon-label">SMA 200</span>
                                    <span class="neon-value">{r['sma200']:.2f}</span>
                                </div>
                                <div>
                                    <span class="neon-label">Pivot Point</span>
                                    <span class="neon-value">{r['pp']:.2f}</span>
                                </div>
                                <div>
                                    <span class="neon-label">Max 52T</span>
                                    <span class="neon-value">{r['h52']:.2f}</span>
                                </div>
                            </div>
                    """, unsafe_allow_html=True)
                    
                    # Interaktywny Wykres Plotly
                    fig = go.Figure()
                    # Świece
                    fig.add_trace(go.Candlestick(
                        x=r['df_plot'].index,
                        open=r['df_plot']['Open'],
                        high=r['df_plot']['High'],
                        low=r['df_plot']['Low'],
                        close=r['df_plot']['Close'],
                        name="Cena"
                    ))
                    # Średnie
                    fig.add_trace(go.Scatter(x=r['df_plot'].index, y=r['df_plot']['Close'].rolling(20).mean(), line=dict(color='yellow', width=1), name="SMA20"))
                    fig.add_trace(go.Scatter(x=r['df_plot'].index, y=r['df_plot']['Close'].rolling(50).mean(), line=dict(color='orange', width=1.5), name="SMA50"))
                    
                    fig.update_layout(
                        template="plotly_dark",
                        height=350,
                        margin=dict(l=0, r=0, t=0, b=0),
                        xaxis_rangeslider_visible=False,
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{r['symbol']}_{i}")
                    
                    # Przycisk AI i Newsy
                    if st.button(f"🤖 ANALIZA EKSPERCKA {r['symbol']}", key=f"btn_ai_{r['symbol']}"):
                        with st.spinner("AI analizuje rynek..."):
                            opinion = get_ai_pro_strategy(r)
                            st.markdown(f'<div class="ai-box">{opinion}</div>', unsafe_allow_html=True)
                    
                    st.markdown("<span class='neon-label'>Ostatnie Newsy</span>", unsafe_allow_html=True)
                    if r['news']:
                        for n in r['news']:
                            st.markdown(f"<a class='news-link' href='{n['l']}' target='_blank'>● {n['t']}</a>", unsafe_allow_html=True)
                    else:
                        st.write("Brak nowych wiadomości.")
                        
                    st.markdown("</div>", unsafe_allow_html=True)

    # Footer
    st.divider()
    st.caption(f"AI ALPHA MONSTER PRO v79 ULTRA © 2026 | Logi systemowe: {LOG_FILE}")

if __name__ == "__main__":
    main()
