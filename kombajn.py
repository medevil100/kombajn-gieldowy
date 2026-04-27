    import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- SEKCJA 1: INICJALIZACJA SYSTEMU I BAZY DANYCH ---
# Plik przechowujący listę Twoich ulubionych spółek
DB_FILE = "moje_spolki.txt"

# Pobieranie klucza OpenAI bezpośrednio z bezpiecznej skrytki Streamlit Secrets
# Pamiętaj, aby dodać OPENAI_API_KEY w ustawieniach Streamlit Cloud!
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")

def load_tickers():
    """Funkcja ładująca symbole. Jeśli plik nie istnieje, ładuje Penny Stocks."""
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

# Konfiguracja głównego okna aplikacji
st.set_page_config(
    page_title="AI ALPHA GOLDEN v62 ULTIMATE PRO",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicjalizacja stanów sesji (pamięć podręczna dla stabilności danych)
if 'risk_cap' not in st.session_state:
    st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state:
    st.session_state.risk_pct = 1.0
if 'ai_results' not in st.session_state:
    st.session_state.ai_results = {}
if 'last_data' not in st.session_state:
    st.session_state.last_data = []

# --- SEKCJA 2: ROZBUDOWANA ARCHITEKTURA STYLÓW CSS (NEON DARK) ---
st.markdown("""
    <style>
    /* Globalne ustawienia tła i czcionki */
    .stApp { 
        background-color: #010101; 
        color: #e0e0e0; 
        font-family: 'Inter', sans-serif; 
    }
    
    /* Neonowe miniatury TOP 10 */
    .top-mini-tile {
        padding: 15px; 
        border-radius: 12px; 
        text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505); 
        border: 1px solid #30363d; 
        margin-bottom: 10px; 
        transition: 0.3s;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.3); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.3); }
    
    /* Główne karty spółek - Maksymalna czytelność */
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; 
        border-radius: 20px; 
        border: 1px solid #30363d; 
        text-align: center; 
        min-height: 800px; 
        transition: 0.4s ease;
        display: flex; 
        flex-direction: column; 
        justify-content: space-between;
        margin-bottom: 25px;
    }
    .main-card:hover { 
        border-color: #58a6ff; 
        transform: translateY(-8px); 
        box-shadow: 0 15px 45px rgba(88, 166, 255, 0.15); 
    }
    
    /* Sygnalizacja kolorystyczna werdyktów */
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.4rem; text-transform: uppercase; text-shadow: 0 0 10px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.4rem; text-transform: uppercase; text-shadow: 0 0 10px #ff4b4b; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.2rem; }
    
    /* Panel Kalkulatora Ryzyka i Pozycji */
    .pos-calc { 
        background: rgba(88, 166, 255, 0.1); 
        border-radius: 15px; 
        padding: 20px; 
        margin: 20px 0; 
        border: 1px solid #58a6ff; 
        color: #58a6ff; 
        font-weight: bold;
    }
    .pos-val { font-size: 1.9rem; display: block; margin-bottom: 5px; text-shadow: 0 0 8px #58a6ff; }
    .pos-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    
    /* Siatka danych technicznych */
    .tech-grid { 
        display: grid; 
        grid-template-columns: 1fr 1fr; 
        gap: 12px; 
        background: rgba(255,255,255,0.03); 
        padding: 15px; 
        border-radius: 15px; 
        text-align: left;
    }
    .tech-row { 
        border-bottom: 1px solid #21262d; 
        padding: 6px 0; 
        font-size: 0.95rem; 
        display: flex; 
        justify-content: space-between; 
    }
    .t-label { color: #8b949e; }
    .t-value { color: #ffffff; font-weight: bold; }
    
    /* Wyświetlacz Analizy AI */
    .ai-display { 
        padding: 20px; 
        border-radius: 15px; 
        margin-top: 20px; 
        font-size: 1rem; 
        background: rgba(0, 255, 136, 0.05); 
        border: 1px solid #00ff88;
        min-height: 140px; 
        display: flex; 
        flex-direction: column; 
        line-height: 1.6; 
        font-style: italic;
        color: #00ff88;
    }
    
    /* Sekcja Newsów */
    .news-box { 
        margin-top: 25px; 
        text-align: left; 
        border-top: 1px dashed #30363d; 
        padding-top: 15px; 
    }
    .news-link { 
        color: #58a6ff; 
        text-decoration: none; 
        font-size: 0.85rem; 
        display: block; 
        margin-bottom: 12px; 
        white-space: nowrap; 
        overflow: hidden; 
        text-overflow: ellipsis; 
    }
    .news-link:hover { color: #ffffff; text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)

# --- SEKCJA 3: PANCERNY SILNIK ANALITYCZNY (360 STOPNI) ---
def get_analysis(symbol):
    """Pobiera dane historyczne i oblicza kompletny zestaw wskaźników."""
    try:
        # Pauza dla stabilności (Yahoo blokuje seryjne zapytania)
        time.sleep(0.6)
        s = symbol.strip().upper()
        ticker = yf.Ticker(s)
        
        # Pobieranie danych historycznych (250 dni, aby SMA200 było stabilne)
        df = ticker.history(period="250d", interval="1d")
        
        # Obsługa błędów braku danych
        if df.empty or len(df) < 150:
            return None
        
        # Naprawa formatu kolumn MultiIndex w nowym yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Aktualne parametry rynkowe
        price = float(df['Close'].iloc[-1])
        
        # 1. Średnie Kroczące (Trend)
        sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        sma100 = df['Close'].rolling(window=100).mean().iloc[-1]
        sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
        
        # 2. Wstęgi Bollingera (Zmienność)
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        std_dev = df['Close'].rolling(window=20).std().iloc[-1]
        bb_up = ema20 + (std_dev * 2)
        bb_low = ema20 - (std_dev * 2)
        
        # 3. MACD (Pęd rynkowy)
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        curr_macd = macd_line.iloc[-1]
        
        # 4. Pivot Point (Punkty zwrotne rynkowe)
        prev_candle = df.iloc[-2]
        pivot = (prev_candle['High'] + prev_candle['Low'] + prev_candle['Close']) / 3
        r1 = (2 * pivot) - prev_candle['Low']
        s1 = (2 * pivot) - prev_candle['High']
        
        # 5. Wskaźnik RSI (Siła trendu)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(window=14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # 6. ATR i Kalkulator Zarządzania Ryzykiem
        tr = pd.concat([
            df['High']-df['Low'], 
            (df['High']-df['Close'].shift()).abs(), 
            (df['Low']-df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]
        
        # Logika wielkości pozycji (Position Sizing)
        risk_amount = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.6
        if sl_dist > 0:
            shares = int(risk_amount / sl_dist)
            # Zabezpieczenie: nie kupuj za więcej niż masz
            max_shares = int(st.session_state.risk_cap / price)
            if shares > max_shares:
                shares = max_shares
        else:
            shares = 0
            
        # 7. Pobieranie Newsów rynkowych
        market_news = []
        try:
            raw_news = ticker.news
            if raw_news:
                for n in raw_news[:2]:
                    market_news.append({
                        "t": n.get('title', '')[:65] + "...", 
                        "l": n.get('link', '#')
                    })
        except Exception:
            pass
        if not market_news:
            market_news = [{"t": "Info rynkowe czasowo niedostępne", "l": "#"}]

        # 8. Logika Decyzyjna (System Expert)
        v_type = "neutral"
        if rsi < 32 and price < bb_low: 
            verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68 and price > bb_up: 
            verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: 
            verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        return {
            "s": s, "p": price, "rsi": rsi, "sma50": sma50, "sma100": sma100, 
            "sma200": sma200, "ema20": ema20, "pivot": pivot, "r1": r1, "s1": s1,
            "macd": curr_macd, "verd": verd, "vcl": vcl, "v_type": v_type, 
            "shares": shares, "sl": price - sl_dist, "tp": price + (atr * 3.8), 
            "news": market_news, "df": df.tail(65), "val": shares * price
        }
    except Exception:
        return None

# --- SEKCJA 4: INTERFEJS UŻYTKOWNIKA (SIDEBAR) ---
with st.sidebar:
    st.title("🚜 GOLDEN v62 ULTIMATE")
    st.markdown("---")
    
    st.subheader("💰 KONFIGURACJA KAPITAŁU")
    st.session_state.risk_cap = st.number_input("Twój Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    st.subheader("📝 LISTA OBSERWOWANYCH")
    ticker_area = st.text_area("Wpisz symbole (rozdzielone przecinkiem):", value=load_tickers(), height=250)
    
    if st.button("💾 ZAPISZ I URUCHOM ANALIZĘ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_area)
        st.cache_data.clear()
        st.success("Lista zaktualizowana!")
        st.rerun()
    
    st.markdown("---")
    # Wybór częstotliwości odświeżania (naprawiony suwak)
    refresh_rate = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

# Automatyczne odświeżanie strony w tle
st_autorefresh(interval=refresh_rate * 1000, key="v62_fsh_global")

# --- SEKCJA 5: LOGIKA WYŚWIETLANIA I ANALIZA AI ---
tickers_list = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=refresh_rate)
def fetch_all_data(s_list):
    """Pobiera dane sekwencyjnie z paskiem postępu."""
    results = []
    progress_placeholder = st.progress(0)
    for i, symbol in enumerate(s_list):
        data = get_analysis(symbol)
        if data:
            results.append(data)
        progress_placeholder.progress((i + 1) / len(s_list))
    progress_placeholder.empty()
    return results

data_ready = fetch_all_data(tickers_list)

if data_ready:
    # --- TERMINAL TOP 10 (Ranking okazji) ---
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL (RANKING RSI)")
    top_10 = sorted(data_ready, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for idx, d in enumerate(top_10):
        with t_cols[idx % 5]:
            t_cls = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""
                <div class="top-mini-tile {t_cls}">
                    <b style="font-size:1.2rem;">{d['s']}</b> | {d['p']:.2f}<br>
                    <small>RSI: {d['rsi']:.0f}</small><br>
                    <span class="{d['vcl']}">{d['verd']}</span>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- GENEROWANIE KAFELKÓW GŁÓWNYCH ---
    for i in range(0, len(data_ready), 5):
        row_cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with row_cols[idx]:
                border = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {border};">
                    <div>
                        <div style="font-size:2rem; font-weight:bold; letter-spacing:-1px;">{d['s']}</div>
                        <div style="color:#58a6ff; font-size:1.4rem; margin-bottom:10px;">{d['p']:.2f} PLN</div>
                        <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    </div>
                    
                    <div class="pos-calc">
                        <span class="pos-label">Ilość do kupna:</span><br>
                        <span class="pos-val">{d['shares']} szt.</span>
                        <small>Wartość: {d['val']:.0f} PLN</small>
                    </div>
                    
                    <div class="tech-grid">
                        <div class="tech-row"><span class="t-label">SMA 200:</span><span class="t-value">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">SMA 100:</span><span class="t-value">{d['sma100']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">SMA 50:</span><span class="t-value">{d['sma50']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">MACD:</span><span class="t-value">{d['macd']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">PIVOT:</span><span class="t-value">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">RSI (14):</span><span class="t-value">{d['rsi']:.0f}</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # SEKCJA TRWAŁEJ ANALIZY AI
                if st.button(f"🤖 GŁĘBOKA ANALIZA AI: {d['s']}", key=f"btn_{d['s']}"):
                    if AI_KEY:
                        try:
                            with st.spinner(f"AI Analizuje {d['s']}..."):
                                client = OpenAI(api_key=AI_KEY)
                                prompt = (
                                    f"Jesteś analitykiem giełdowym. Przeanalizuj {d['s']}. "
                                    f"Cena: {d['p']}, RSI: {d['rsi']:.0f}, MACD: {d['macd']:.2f}, SMA200: {d['sma200']:.2f}. "
                                    f"MOJE CELE: SL {d['sl']:.2f}, TP {d['tp']:.2f}. "
                                    f"Zadanie: Podaj konkretny plan w 3-4 punktach, oceń ryzyko i potwierdź poziomy TP/SL. Konkretnie!"
                                )
                                response = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[{"role": "user", "content": prompt}],
                                    max_tokens=250
                                )
                                st.session_state.ai_results[d['s']] = response.choices[0].message.content
                        except Exception as e:
                            st.error(f"Błąd AI: {str(e)}")
                    else:
                        st.warning("Dodaj klucz OpenAI do skrytki (Secrets)!")

                # Wyświetlanie wyników AI, które nie znikają przy odświeżaniu
                if d['s'] in st.session_state.ai_results:
                    st.markdown(f"""<div class="ai-display"><b>STRATEGIA AI:</b><br>{st.session_state.ai_results[d['s']]}</div>""", unsafe_allow_html=True)
                    if st.button("❌ Zamknij", key=f"close_{d['s']}"):
                        del st.session_state.ai_results[d['s']]
                        st.rerun()

                st.markdown(f"""
                    <div class="news-box">
                        <b>📢 NEWSY:</b>
                        {"".join([f'<a class="news-link" href="{n["l"]}" target="_blank">• {n["t"]}</a>' for n in d['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("🔍 WYKRES I PROGI"):
                    st.write(f"Sugerowany SL: `{d['sl']:.2f}` | Sugerowany TP: `{d['tp']:.2f}`")
                    fig = go.Figure(data=[go.Candlestick(
                        x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], 
                        low=d['df']['Low'], close=d['df']['Close'], name="Cena"
                    )])
                    fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("❌ Błąd pobierania danych. Sprawdź symbole lub połączenie z internetem.")

# --- SEKCJA 6: STOPKA SYSTEMOWA ---
st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:50px;'>v62.0 ULTIMATE MAXI | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>", unsafe_allow_html=True)
