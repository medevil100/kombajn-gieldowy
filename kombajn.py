import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# SEKCJA 1: KONFIGURACJA ŚRODOWISKA I BAZY DANYCH
# ==============================================================================
DB_FILE = "moje_spolki.txt"

# Klucz OpenAI pobierany z Secrets (Skrytka Streamlit)
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")

def load_tickers():
    """Wczytywanie listy symboli z pliku tekstowego lub ładowanie domyślnych Penny Stocks."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                if content:
                    return content
                else:
                    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
        except Exception:
            return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"

# Konfiguracja okna przeglądarki
st.set_page_config(
    page_title="AI ALPHA GOLDEN v70 MONSTER",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicjalizacja stanów sesji (pamięć podręczna aplikacji)
if 'risk_cap' not in st.session_state:
    st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state:
    st.session_state.risk_pct = 1.0
if 'ai_results' not in st.session_state:
    st.session_state.ai_results = {}
if 'ticker_cache' not in st.session_state:
    st.session_state.ticker_cache = {}

# ==============================================================================
# SEKCJA 2: ZAAWANSOWANA ARCHITEKTURA STYLÓW CSS (NEON DARK MODE)
# ==============================================================================
st.markdown("""
    <style>
    /* Globalny Dark Mode */
    .stApp { 
        background-color: #010101; 
        color: #e0e0e0; 
        font-family: 'Inter', -apple-system, sans-serif; 
    }
    
    /* Sekcja TOP 10 - Mini kafelki sygnałów */
    .top-mini-tile {
        padding: 15px; 
        border-radius: 12px; 
        text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505); 
        border: 1px solid #30363d; 
        margin-bottom: 15px; 
        transition: 0.3s ease;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.2); }
    
    /* Główna karta spółki (Format MAXI) */
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; 
        border-radius: 20px; 
        border: 1px solid #30363d; 
        text-align: center; 
        min-height: 850px; 
        transition: 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        display: flex; 
        flex-direction: column; 
        justify-content: space-between;
        margin-bottom: 30px;
    }
    .main-card:hover { 
        border-color: #58a6ff; 
        transform: translateY(-10px); 
        box-shadow: 0 20px 50px rgba(88, 166, 255, 0.15); 
    }
    
    /* Stylizacja sygnałów technicznych */
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.5rem; text-transform: uppercase; text-shadow: 0 0 12px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.5rem; text-transform: uppercase; text-shadow: 0 0 12px #ff4b4b; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.3rem; }
    
    /* Kalkulator Ryzyka i Pozycji */
    .pos-calc-box { 
        background: rgba(88, 166, 255, 0.08); 
        border-radius: 15px; 
        padding: 20px; 
        margin: 20px 0; 
        border: 1px solid #58a6ff; 
        color: #58a6ff; 
    }
    .pos-val { font-size: 2rem; display: block; margin-bottom: 5px; font-weight: 900; text-shadow: 0 0 10px #58a6ff; }
    .pos-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 2px; }
    
    /* Grid danych technicznych (SMA/MACD/RSI) */
    .tech-grid { 
        display: grid; 
        grid-template-columns: 1fr 1fr; 
        gap: 12px; 
        background: rgba(255,255,255,0.02); 
        padding: 20px; 
        border-radius: 15px; 
        text-align: left;
    }
    .tech-row { 
        border-bottom: 1px solid #21262d; 
        padding: 8px 0; 
        font-size: 0.95rem; 
        display: flex; 
        justify-content: space-between; 
    }
    .t-lab { color: #8b949e; }
    .t-val { color: #ffffff; font-weight: bold; }
    
    /* Okno Analizy AI (Deep Learning Look) */
    .ai-strategy-box { 
        padding: 20px; 
        border-radius: 15px; 
        margin-top: 25px; 
        font-size: 0.95rem; 
        background: rgba(0, 255, 136, 0.03); 
        border-left: 5px solid #00ff88;
        min-height: 150px; 
        line-height: 1.6; 
        text-align: left;
        color: #d1d1d1;
    }
    
    /* Nagłówki i Newsy */
    .news-section { 
        margin-top: 30px; 
        text-align: left; 
        border-top: 1px dashed #30363d; 
        padding-top: 20px; 
    }
    .news-link { 
        color: #58a6ff; 
        text-decoration: none; 
        font-size: 0.85rem; 
        display: block; 
        margin-bottom: 10px; 
        overflow: hidden; 
        text-overflow: ellipsis; 
        white-space: nowrap;
    }
    .news-link:hover { color: #ffffff; text-decoration: underline; }
    
    /* Scrollbar Styling */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #010101; }
    ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# SEKCJA 3: SILNIK ANALITYCZNY (WSZYSTKIE WSKAŹNIKI TECHNICZNE)
# ==============================================================================
def get_monster_analysis(symbol):
    """Pobiera dane rynkowe i wykonuje kompleksową analizę techniczną."""
    try:
        # Prewencyjna pauza dla stabilności Yahoo Finance
        time.sleep(0.65)
        s = symbol.strip().upper()
        ticker_obj = yf.Ticker(s)
        
        # Pobieranie danych historycznych (250 dni dla pełnej SMA200 i stabilności)
        df_raw = ticker_obj.history(period="250d", interval="1d")
        
        if df_raw.empty or len(df_raw) < 150:
            return None
        
        # Rozwiązanie problemu MultiIndex w nowych wersjach yfinance
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = df_raw.columns.get_level_values(0)
            
        # Aktualna cena rynkowa
        curr_price = float(df_raw['Close'].iloc[-1])
        
        # 1. Obliczanie Średnich Kroczących (Trend)
        sma50 = df_raw['Close'].rolling(window=50).mean().iloc[-1]
        sma100 = df_raw['Close'].rolling(window=100).mean().iloc[-1]
        sma200 = df_raw['Close'].rolling(window=200).mean().iloc[-1]
        
        # 2. Wstęgi Bollingera (Zmienność i Przegrzanie)
        ema20 = df_raw['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        std_20 = df_raw['Close'].rolling(window=20).std().iloc[-1]
        bb_upper = ema20 + (std_20 * 2)
        bb_lower = ema20 - (std_20 * 2)
        
        # 3. MACD (Pęd trendu)
        exp12 = df_raw['Close'].ewm(span=12, adjust=False).mean()
        exp26 = df_raw['Close'].ewm(span=26, adjust=False).mean()
        macd_line = exp12 - exp26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_val = macd_line.iloc[-1]
        
        # 4. RSI 14 (Siła relatywna)
        delta = df_raw['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(window=14).mean()
        rsi_val = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # 5. Pivot Points (Klasyczne poziomy wsparcia i oporu)
        prev_day = df_raw.iloc[-2]
        pivot = (prev_day['High'] + prev_day['Low'] + prev_day['Close']) / 3
        r1_level = (2 * pivot) - prev_day['Low']
        s1_level = (2 * pivot) - prev_day['High']
        
        # 6. ATR i Kalkulator Position Sizing (Zarządzanie ryzykiem)
        tr1 = df_raw['High'] - df_raw['Low']
        tr2 = (df_raw['High'] - df_raw['Close'].shift()).abs()
        tr3 = (df_raw['Low'] - df_raw['Close'].shift()).abs()
        atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(window=14).mean().iloc[-1]
        
        # Wyliczanie ilości akcji na podstawie ryzyka PLN
        risk_pln = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_margin = atr * 1.6  # Bezpieczny bufor 1.6 ATR
        
        if sl_margin > 0:
            shares_to_buy = int(risk_pln / sl_margin)
            # Limit kapitałowy: Nie kupuj za więcej niż masz w portfelu
            max_shares_allowed = int(st.session_state.risk_cap / curr_price)
            if shares_to_buy > max_shares_allowed:
                shares_to_buy = max_shares_allowed
        else:
            shares_to_buy = 0
            
        # 7. Pobieranie informacji rynkowych (Newsy)
        market_news = []
        try:
            raw_news_data = ticker_obj.news
            if raw_news_data:
                for n in raw_news_data[:3]:
                    market_news.append({
                        "title": n.get('title', '')[:65] + "...", 
                        "link": n.get('link', '#')
                    })
        except Exception:
            pass
        if not market_news:
            market_news = [{"title": "Brak komunikatów rynkowych dla tego symbolu", "link": "#"}]

        # 8. Logika Automatycznego Werdyktu
        v_type = "neutral"
        if rsi_val < 32 and curr_price < bb_lower: 
            verdict_text, verdict_class, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 68 or curr_price > bb_upper: 
            verdict_text, verdict_class, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: 
            verdict_text, verdict_class, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        # 9. Kolorystyka trendu i RSI dla UI
        trend_color = "#00ff88" if curr_price > sma200 else "#ff4b4b"
        rsi_color = "#ff4b4b" if rsi_val > 70 else "#00ff88" if rsi_val < 30 else "#8b949e"
        macd_color = "#00ff88" if macd_val > 0 else "#ff4b4b"

        return {
            "symbol": s, "price": curr_price, "rsi": rsi_val, "rsi_color": rsi_color,
            "sma50": sma50, "sma100": sma100, "sma200": sma200, "trend_color": trend_color,
            "pivot": pivot, "r1": r1_level, "s1": s1_level, "macd": macd_val, "macd_color": macd_color,
            "verdict": verdict_text, "v_class": verdict_class, "v_type": v_type, 
            "shares": shares_to_buy, "sl": curr_price - sl_margin, "tp": curr_price + (atr * 3.8), 
            "news": market_news, "df": df_raw.tail(70), "position_value": shares_to_buy * curr_price,
            "atr_pct": (sl_margin / curr_price) * 100
        }
    except Exception as e:
        return None

# ==============================================================================
# SEKCJA 4: PANEL STEROWANIA (SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.title("🚜 GOLDEN MONSTER v70")
    st.markdown("---")
    
    st.subheader("💰 USTAWIENIA PORTFELA")
    st.session_state.risk_cap = st.number_input("Całkowity Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na transakcję (%)", 0.1, 5.0, st.session_state.risk_pct, help="Ile % kapitału stracisz przy trafieniu SL")
    
    st.subheader("📝 LISTA MONITOROWANA")
    ticker_input_area = st.text_area("Symbole (BBI, EVOK, BTC-USD...):", value=load_tickers(), height=250)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_input_area)
        st.cache_data.clear()
        st.success("Baza symboli zaktualizowana!")
        st.rerun()
    
    st.markdown("---")
    # Wybór częstotliwości odświeżania (Poprawione opcje)
    refresh_rate_sec = st.select_slider("Częstotliwość odświeżania (s)", options=[30, 60, 120, 300, 600], value=60)

# Uruchomienie automatycznego odświeżania
st_autorefresh(interval=refresh_rate_sec * 1000, key="monster_refresh_engine")

# ==============================================================================
# SEKCJA 5: GŁÓWNA LOGIKA RENDEROWANIA I ANALIZA AI
# ==============================================================================
symbols_to_process = [x.strip().upper() for x in ticker_input_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=refresh_rate_sec)
def fetch_monster_data(symbols):
    """Pobiera dane sekwencyjnie z graficznym paskiem postępu."""
    processed_results = []
    pbar = st.progress(0)
    for i, sym in enumerate(symbols):
        result = get_monster_analysis(sym)
        if result:
            processed_results.append(result)
        pbar.progress((i + 1) / len(symbols))
    pbar.empty()
    return processed_results

data_ready_list = fetch_monster_data(symbols_to_process)

if data_ready_list:
    # --- RANKING TOP 10 SIGNAL TERMINAL ---
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL (RANKING OKAZJI)")
    # Sortujemy od najbardziej wyprzedanych (najniższe RSI)
    top_10_occassions = sorted(data_ready_list, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for idx, d in enumerate(top_10_occassions):
        with top_cols[idx % 5]:
            border_type = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""
                <div class="top-mini-tile {border_type}">
                    <b style="font-size:1.2rem; color:white;">{d['symbol']}</b><br>
                    <span style="color:#58a6ff; font-weight:bold;">{d['price']:.2f} PLN</span><br>
                    <small style="color:{d['rsi_color']};">RSI: {d['rsi']:.0f}</small><br>
                    <span class="{d['v_class']}">{d['verdict']}</span>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- KARTY SZCZEGÓŁOWE GŁÓWNE ---
    for i in range(0, len(data_ready_list), 5):
        row_columns = st.columns(5)
        for idx, d in enumerate(data_ready_list[i:i+5]):
            with row_columns[idx]:
                accent = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {accent};">
                    <div>
                        <div style="font-size:2.2rem; font-weight:bold; letter-spacing:-1px; color:white;">{d['symbol']}</div>
                        <div style="color:#58a6ff; font-size:1.5rem; margin-bottom:15px;">{d['price']:.2f} PLN</div>
                        <div style="margin: 20px 0;"><span class="{d['v_class']}">{d['verdict']}</span></div>
                    </div>
                    
                    <div class="pos-calc-box">
                        <span class="pos-label">Ilość do kupna:</span><br>
                        <span class="pos-val">{d['shares']} szt.</span>
                        <small>Wartość: {d['position_value']:.0f} PLN</small>
                    </div>
                    
                    <div class="tech-grid">
                        <div class="tech-row"><span class="t-lab">SMA 200 (Trend):</span><span class="t-val" style="color:{d['trend_color']};">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="t-lab">SMA 100 / 50:</span><span class="t-val">{d['sma100']:.1f} / {d['sma50']:.1f}</span></div>
                        <div class="tech-row"><span class="t-lab">Pęd (MACD):</span><span class="t-val" style="color:{d['macd_color']};">{d['macd']:.2f}</span></div>
                        <div class="tech-row"><span class="t-lab">Pivot Point:</span><span class="t-val" style="color:#f1e05a;">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="t-lab">RSI (Siła):</span><span class="t-val" style="color:{d['rsi_color']};">{d['rsi']:.0f}</span></div>
                        <div class="tech-row"><span class="t-lab">Dystans SL:</span><span class="t-val" style="color:#ff4b4b;">{d['atr_pct']:.1f}%</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # --- LOGIKA ANALIZY AI (GŁĘBOKA STRATEGIA) ---
                if st.button(f"🤖 ANALIZA AI: {d['symbol']}", key=f"ai_monster_{d['symbol']}"):
                    if AI_KEY:
                        try:
                            with st.spinner(f"AI Generuje strategię dla {d['symbol']}..."):
                                ai_client = OpenAI(api_key=AI_KEY)
                                monster_prompt = (
                                    f"Jesteś starszym analitykiem giełdowym Goldman Sachs. Przeanalizuj {d['symbol']}. "
                                    f"DANE TECHNICZNE: Cena {d['price']}, RSI {d['rsi']:.0f}, MACD {d['macd']:.2f}, SMA200 {d['sma200']:.2f}. "
                                    f"MOJE CELE: Stop Loss na {d['sl']:.2f}, Take Profit na {d['tp']:.2f}. "
                                    f"ZADANIE: Podaj konkretną strategię: "
                                    f"1. Czy to dobry moment na wejście? "
                                    f"2. Jakie są szanse na odbicie od Pivot Point {d['pivot']:.2f}? "
                                    f"3. Potwierdź poziomy TP i SL. Pisz konkretnie, w punktach."
                                )
                                monster_response = ai_client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[{"role": "user", "content": monster_prompt}],
                                    max_tokens=300
                                )
                                st.session_state.ai_results[d['symbol']] = monster_response.choices.message.content
                        except Exception as e:
                            st.error("Usługa AI czasowo niedostępna")
                    else:
                        st.warning("Dodaj klucz OpenAI w Sidebar/Secrets!")

                # Wyświetlanie wyników AI, które zostają po odświeżeniu
                if d['symbol'] in st.session_state.ai_results:
                    st.markdown(f"""<div class="ai-strategy-box"><b>PROFESJONALNA STRATEGIA AI:</b><br>{st.session_state.ai_results[d['symbol']]}</div>""", unsafe_allow_html=True)
                    if st.button("❌ Zamknij raport", key=f"close_monster_{d['symbol']}"):
                        del st.session_state.ai_results[d['symbol']]
                        st.rerun()

                # Sekcja Newsów rynkowych
                st.markdown(f"""
                    <div class="news-section">
                        <b style="color:white; font-size:0.8rem;">📢 INFO RYNKOWE:</b>
                        {"".join([f'<a class="news-link" href="{n["link"]}" target="_blank">• {n["title"]}</a>' for n in d['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Interaktywny Wykres w Expanderze
                with st.expander("📊 INTERAKTYWNY WYKRES ŚWIECOWY"):
                    st.write(f"Sugerowany SL: `{d['sl']:.2f}` | Sugerowany TP: `{d['tp']:.2f}`")
                    fig_candlestick = go.Figure(data=[go.Candlestick(
                        x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], 
                        low=d['df']['Low'], close=d['df']['Close'], name="Cena"
                    )])
                    # Dodanie SMA 200 na wykres
                    fig_candlestick.add_trace(go.Scatter(x=d['df'].index, y=d['df']['Close'].rolling(200).mean(), line=dict(color='red', width=1.5), name="SMA200"))
                    fig_candlestick.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig_candlestick, use_container_width=True)

else:
    st.error("❌ Błąd: System nie mógł pobrać danych z Yahoo Finance. Sprawdź symbole lub spróbuj za chwilę.")

# ==============================================================================
# SEKCJA 6: STOPKA SYSTEMOWA I CZAS OSTATNIEJ AKTUALIZACJI
# ==============================================================================
st.markdown(f"""
    <div style='text-align:center; color:#8b949e; margin-top:60px; padding:20px; border-top:1px solid #30363d;'>
        <b>AI ALPHA GOLDEN v70.0 MONSTER FULL MAXI</b><br>
        Ostatnia aktualizacja rynkowa: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
        Twoje ryzyko portfela: {st.session_state.risk_pct}% | Kapitał: {st.session_state.risk_cap:.0f} PLN
    </div>
""", unsafe_allow_html=True)
