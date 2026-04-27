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

# --- 1. KONFIGURACJA PLIKÓW I SKRYTKA ---
DB_FILE = "moje_spolki.txt"
# Pobieranie klucza OpenAI bezpośrednio ze skrytki Secrets
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")

def load_tickers():
    """Wczytuje listę symboli z pliku lokalnego."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
        except:
            return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"

# Konfiguracja strony Streamlit
st.set_page_config(
    page_title="AI ALPHA GOLDEN v60 ULTIMATE",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicjalizacja stanów sesji (pamięć portfela i analiz AI)
if 'risk_cap' not in st.session_state:
    st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state:
    st.session_state.risk_pct = 1.0
if 'ai_results' not in st.session_state:
    st.session_state.ai_results = {}

# --- 2. ROZBUDOWANA BIBLIOTEKA STYLÓW CSS (PONAD 70 LINII) ---
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    /* Sekcja TOP 10 Terminal */
    .top-mini-tile {
        padding: 15px; border-radius: 12px; text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505); 
        border: 1px solid #30363d; margin-bottom: 10px; transition: 0.3s;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.3); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.3); }
    
    /* Główne Karty Spółek - Format Maxi */
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        text-align: center; min-height: 750px; transition: 0.4s ease;
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .main-card:hover { 
        border-color: #58a6ff; transform: translateY(-8px); 
        box-shadow: 0 15px 45px rgba(88, 166, 255, 0.1); 
    }
    
    /* Sygnalizacja Wizualna */
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.3rem; text-transform: uppercase; text-shadow: 0 0 10px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.3rem; text-transform: uppercase; text-shadow: 0 0 10px #ff4b4b; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.1rem; }
    
    /* Kalkulator PLN i Pozycji */
    .pos-calc { 
        background: rgba(88, 166, 255, 0.1); border-radius: 15px; padding: 18px; 
        margin: 20px 0; border: 1px solid #58a6ff; color: #58a6ff; font-weight: bold;
    }
    .pos-val { font-size: 1.8rem; display: block; margin-bottom: 5px; text-shadow: 0 0 5px #58a6ff; }
    
    /* Tabela Wskaźników Technicznych */
    .tech-grid { 
        display: grid; grid-template-columns: 1fr 1fr; gap: 10px; 
        background: rgba(255,255,255,0.02); padding: 15px; border-radius: 15px; text-align: left;
    }
    .tech-row { border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; display: flex; justify-content: space-between; }
    .t-label { color: #8b949e; }
    .t-value { color: #ffffff; font-weight: bold; }
    
    /* Pole Analizy AI */
    .ai-display { 
        padding: 18px; border-radius: 15px; margin-top: 20px; font-size: 0.95rem; 
        background: rgba(0, 255, 136, 0.05); border: 1px solid #00ff88;
        min-height: 120px; display: flex; flex-direction: column; align-items: center; line-height: 1.5; font-style: italic;
    }
    
    /* Sekcja Informacji rynkowych */
    .news-box { margin-top: 20px; text-align: left; border-top: 1px dashed #30363d; padding-top: 15px; }
    .news-link { 
        color: #58a6ff; text-decoration: none; font-size: 0.8rem; 
        display: block; margin-bottom: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; 
    }
    .news-link:hover { color: #ffffff; text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALITYCZNY (WSZYSTKIE WSKAŹNIKI) ---
def perform_deep_analysis(symbol):
    """Pobiera dane i wylicza komplet wskaźników technicznych."""
    try:
        # Prewencyjne opóźnienie dla stabilności API Yahoo
        time.sleep(0.5)
        s = symbol.strip().upper()
        ticker = yf.Ticker(s)
        
        # Pobieranie szerokiego zakresu danych dla SMA 200 i MACD
        df = ticker.history(period="250d", interval="1d")
        if df.empty or len(df) < 150:
            return None
        
        # Aktualna cena
        price = float(df['Close'].iloc[-1])
        
        # Średnie kroczące (SMA)
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma100 = df['Close'].rolling(100).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # EMA i Wstęgi Bollingera
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        std_dev = df['Close'].rolling(20).std().iloc[-1]
        bb_up, bb_low = ema20 + (std_dev * 2), ema20 - (std_dev * 2)
        
        # MACD (Moving Average Convergence Divergence)
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_val = (ema12 - ema26).iloc[-1]
        
        # Pivot Point (Standardowy)
        prev_candle = df.iloc[-2]
        pivot = (prev_candle['High'] + prev_candle['Low'] + prev_candle['Close']) / 3
        
        # Wskaźnik RSI (14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(window=14).mean()
        rsi_val = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR i Zarządzanie Wielkością Pozycji
               # --- POPRAWIONY KALKULATOR POZYCJI (FIXED POSITION SIZING) ---
        risk_per_trade = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        
        # Stop Loss oparty na 1.6x ATR
        sl_distance = atr * 1.6
        
        if sl_distance > 0:
            # Ile akcji kupić, aby w razie straty stracić TYLKO kwotę ryzyka?
            num_shares = int(risk_per_trade / sl_distance)
            
            # Zabezpieczenie: Wartość pozycji nie może przekroczyć Twojego całego kapitału
            max_shares_by_cap = int(st.session_state.risk_cap / price)
            if num_shares > max_shares_by_cap:
                num_shares = max_shares_by_cap
                
            position_val = num_shares * price
        else:
            num_shares, position_val = 0, 0

        
        # Kalkulator ryzyka
        risk_per_pos = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        # Stop Loss oparty na 1.6x ATR
        sl_distance = atr * 1.6
        num_shares = int(risk_per_pos / sl_distance) if sl_distance > 0 else 0
        
        # Pobieranie Newsów
        news_headlines = []
        try:
            raw_news = ticker.news
            if raw_news:
                for n in raw_news[:2]:
                    news_headlines.append({"title": n.get('title', '')[:65], "link": n.get('link', '#')})
        except:
            pass
        if not news_headlines:
            news_headlines = [{"title": "Brak komunikatów rynkowych", "link": "#"}]

        # Logika Werdyktu Technicznego
        v_type = "neutral"
        if rsi_val < 32 and price < bb_low: 
            verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 68 and price > bb_up: 
            verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: 
            verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        return {
            "symbol": s, "price": price, "rsi": rsi_val, "sma50": sma50, "sma100": sma100, 
            "sma200": sma200, "ema20": ema20, "pivot": pivot, "macd": macd_val, 
            "verd": verd, "vcl": vcl, "v_type": v_type, "shares": num_shares, 
            "sl": price - sl_distance, "tp": price + (atr * 3.5), 
            "news": news_headlines, "df": df.tail(60), "position_val": num_shares * price
        }
    except:
        return None

# --- 4. PANEL BOCZNY (SIDEBAR) ---
with st.sidebar:
    st.title("🚜 ALPHA ULTIMATE v60")
    st.markdown("---")
    st.session_state.risk_cap = st.number_input("Twój Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    ticker_area_input = st.text_area("Lista symboli (przecinek):", value=load_tickers(), height=200)
    
    if st.button("💾 ZAPISZ I URUCHOM ANALIZĘ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_area_input)
        st.cache_data.clear()
        st.success("Lista zaktualizowana!")
        st.rerun()
    
    # Wybór częstotliwości odświeżania
    refresh_rate_sec = st.select_slider("Automatyczne odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_rate_sec * 1000, key="v60_refresh_global")

# --- 5. GŁÓWNA LOGIKA WYŚWIETLANIA ---
symbols_list = [x.strip().upper() for x in ticker_area_input.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=refresh_rate_sec)
def fetch_and_process_all(s_list):
    """Pobiera dane dla wszystkich spółek sekwencyjnie dla stabilności."""
    results = []
    pbar_placeholder = st.progress(0)
    for i, sym in enumerate(s_list):
        res = perform_deep_analysis(sym)
        if res:
            results.append(res)
        pbar_placeholder.progress((i + 1) / len(s_list))
    pbar_placeholder.empty()
    return results

data_collection = fetch_and_process_all(symbols_list)

if data_collection:
    # --- TERMINAL TOP 10 (Ranking RSI) ---
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL")
    top_10_rsi = sorted(data_collection, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for idx, d in enumerate(top_10_rsi):
        with top_cols[idx % 5]:
            tile_border = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""
                <div class="top-mini-tile {tile_border}">
                    <b style="font-size:1.1rem;">{d['symbol']}</b> | {d['price']:.2f}<br>
                    <small>RSI: {d['rsi']:.0f}</small><br>
                    <span class="{d['vcl']}">{d['verd']}</span>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA KART ---
    for i in range(0, len(data_collection), 5):
        row_cols = st.columns(5)
        for idx, d in enumerate(data_collection[i:i+5]):
            with row_cols[idx]:
                border_color = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {border_color};">
                    <div>
                        <div style="font-size:1.8rem; font-weight:bold; letter-spacing:-1px;">{d['symbol']}</div>
                        <div style="color:#58a6ff; font-size:1.3rem;">{d['price']:.2f} PLN</div>
                        <div style="margin: 20px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    </div>
                    
                    <div class="pos-calc">
                        <span class="pos-label">Ile kupić:</span><br>
                        <span class="pos-val">{d['shares']} szt.</span>
                        <small>Wartość: {d['position_val']:.0f} PLN</small>
                    </div>
                    
                    <div class="tech-grid">
                        <div class="tech-row"><span class="t-label">SMA 200:</span><span class="t-value">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">SMA 100:</span><span class="t-value">{d['sma100']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">SMA 50:</span><span class="t-value">{d['sma50']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">MACD:</span><span class="t-value">{d['macd']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">PIVOT:</span><span class="t-value">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">RSI:</span><span class="t-value">{d['rsi']:.0f}</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # SEKCJA AI - ZAPAMIĘTYWANIE W SESJI
                if st.button(f"🤖 ANALIZA AI: {d['symbol']}", key=f"ai_btn_{d['symbol']}"):
                    if AI_KEY:
                        try:
                            with st.spinner(f"AI Analizuje {d['symbol']}..."):
                                client = OpenAI(api_key=AI_KEY)
                                prompt_content = (
                                    f"Jesteś ekspertem giełdowym. Przeanalizuj {d['symbol']}: Cena {d['price']}, "
                                    f"RSI {d['rsi']:.0f}, MACD {d['macd']:.2f}, SMA200 {d['sma200']:.2f}. "
                                    f"Moje techniczne wyliczenia: SL {d['sl']:.2f}, TP {d['tp']:.2f}. "
                                    f"Podaj konkretną strategię w 3 punktach, uwzględniając SL i TP."
                                )
                                response_ai = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[{"role": "user", "content": prompt_content}]
                                )
                                st.session_state.ai_results[d['symbol']] = response_ai.choices[0].message.content
                        except Exception as e:
                            st.error(f"AI Error: {str(e)}")
                    else:
                        st.warning("Brak klucza w skrytce Streamlit!")

                if d['symbol'] in st.session_state.ai_results:
                    st.markdown(f"""<div class="ai-display"><b>STRATEGIA AI:</b><br>{st.session_state.ai_results[d['symbol']]}</div>""", unsafe_allow_html=True)
                    if st.button("❌ Zamknij", key=f"close_ai_{d['symbol']}"):
                        del st.session_state.ai_results[d['symbol']]
                        st.rerun()

                st.markdown(f"""
                    <div class="news-box">
                        <b>INFO RYNKOWE:</b>
                        {"".join([f'<a class="news-link" href="{n["link"]}" target="_blank">• {n["title"]}</a>' for n in d['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("🔍 WYKRES ŚWIECOWY"):
                    st.write(f"Techniczny Stop Loss: `{d['sl']:.2f}` | Take Profit: `{d['tp']:.2f}`")
                    fig_candlestick = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'], name="Cena")])
                    fig_candlestick.add_trace(go.Scatter(x=d['df'].index, y=d['df']['Close'].rolling(200).mean(), line=dict(color='red', width=2), name="SMA200"))
                    fig_candlestick.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig_candlestick, use_container_width=True)

else:
    st.error("❌ Błąd: Nie udało się pobrać danych. Sprawdź symbole lub połączenie z internetem.")

# --- 6. STOPKA SYSTEMOWA ---
st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:50px;'>v60.0 ULTIMATE | Ostatnie odświeżenie: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
