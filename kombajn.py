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

# Pobieranie klucza OpenAI bezpośrednio z bezpiecznej skrytki Streamlit Secrets
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")

def load_tickers():
    """Wczytywanie listy symboli z pliku tekstowego."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
        except Exception:
            return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"
    return "BBI, BNOX, EVOK, HILS, INFI, KTRA, RGLS, ALZN, ANIX, ATHE"

# Konfiguracja okna przeglądarki
st.set_page_config(
    page_title="AI ALPHA GOLDEN v71 MONSTER PRO",
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

# ==============================================================================
# SEKCJA 2: ROZBUDOWANA ARCHITEKTURA STYLÓW CSS (NEON DARK MODE)
# ==============================================================================
st.markdown("""
    <style>
    .stApp { background-color: #010101; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    
    .top-mini-tile {
        padding: 15px; border-radius: 12px; text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505); 
        border: 1px solid #30363d; margin-bottom: 15px; transition: 0.3s ease;
    }
    .tile-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.3); }
    .tile-sell { border: 2px solid #ff4b4b !important; box-shadow: 0 0 15px rgba(255,75,75,0.3); }
    
    .main-card { 
        background: linear-gradient(145deg, #0d1117, #020202); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        text-align: center; min-height: 880px; transition: 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        display: flex; flex-direction: column; justify-content: space-between; margin-bottom: 30px;
    }
    .main-card:hover { border-color: #58a6ff; transform: translateY(-10px); box-shadow: 0 20px 50px rgba(88, 166, 255, 0.15); }
    
    .sig-buy { color: #00ff88; font-weight: 900; font-size: 1.5rem; text-transform: uppercase; text-shadow: 0 0 12px #00ff88; }
    .sig-sell { color: #ff4b4b; font-weight: 900; font-size: 1.5rem; text-transform: uppercase; text-shadow: 0 0 12px #ff4b4b; }
    .sig-neutral { color: #8b949e; font-weight: 800; font-size: 1.3rem; }
    
    .pos-calc-box { background: rgba(88, 166, 255, 0.08); border-radius: 15px; padding: 20px; margin: 20px 0; border: 1px solid #58a6ff; color: #58a6ff; }
    .pos-val { font-size: 2rem; display: block; margin-bottom: 5px; font-weight: 900; text-shadow: 0 0 10px #58a6ff; }
    .pos-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 2px; }
    
    .tech-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: rgba(255,255,255,0.02); padding: 20px; border-radius: 15px; text-align: left; }
    .tech-row { border-bottom: 1px solid #21262d; padding: 8px 0; font-size: 0.95rem; display: flex; justify-content: space-between; }
    .t-lab { color: #8b949e; }
    .t-val { color: #ffffff; font-weight: bold; }
    
    .ai-strategy-box { padding: 20px; border-radius: 15px; margin-top: 25px; font-size: 1rem; background: rgba(0, 255, 136, 0.05); border: 1px solid #00ff88; line-height: 1.6; text-align: left; color: #00ff88; }
    .news-link { color: #58a6ff; text-decoration: none; font-size: 0.85rem; display: block; margin-bottom: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .news-link:hover { color: #ffffff; text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# SEKCJA 3: PANCERNY SILNIK ANALITYCZNY (Z FIXEM SMA I POZYCJI)
# ==============================================================================
def get_monster_analysis(symbol):
    try:
        time.sleep(0.65)
        s = symbol.strip().upper()
        ticker_obj = yf.Ticker(s)
        
        # FIX SMA: auto_adjust=True przelicza ceny po splitach
        df_raw = ticker_obj.history(period="250d", interval="1d", auto_adjust=True)
        
        if df_raw.empty or len(df_raw) < 150:
            return None
        
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = df_raw.columns.get_level_values(0)
            
        curr_price = float(df_raw['Close'].iloc[-1])
        
        # Średnie Kroczące
        sma50 = df_raw['Close'].rolling(window=50).mean().iloc[-1]
        sma100 = df_raw['Close'].rolling(window=100).mean().iloc[-1]
        sma200 = df_raw['Close'].rolling(window=200).mean().iloc[-1]
        
        # Zmienność
        ema20 = df_raw['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        std_20 = df_raw['Close'].rolling(window=20).std().iloc[-1]
        bb_upper = ema20 + (std_20 * 2)
        bb_lower = ema20 - (std_20 * 2)
        
        # MACD
        exp12 = df_raw['Close'].ewm(span=12, adjust=False).mean()
        exp26 = df_raw['Close'].ewm(span=26, adjust=False).mean()
        macd_line = exp12 - exp26
        macd_val = macd_line.iloc[-1]
        
        # RSI 14
        delta = df_raw['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(window=14).mean()
        rsi_val = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Pivot Points
        prev_day = df_raw.iloc[-2]
        pivot = (prev_day['High'] + prev_day['Low'] + prev_day['Close']) / 3
        
        # ATR i Position Sizing
        tr = pd.concat([df_raw['High']-df_raw['Low'], (df_raw['High']-df_raw['Close'].shift()).abs(), (df_raw['Low']-df_raw['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]
        
        risk_pln = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        # Fix SL: Przy Penny Stocks używamy 1.2 ATR dla lepszej płynności kapitału
        sl_margin = atr * 1.2 
        
        if sl_margin > 0:
            shares = int(risk_pln / sl_margin)
            max_shares = int(st.session_state.risk_cap / curr_price)
            if shares > max_shares: shares = max_shares
        else:
            shares = 0
            
        market_news = []
        try:
            raw_news = ticker_obj.news
            if raw_news:
                for n in raw_news[:3]: market_news.append({"title": n.get('title', '')[:65], "link": n.get('link', '#')})
        except Exception: pass

        # Werdykt
        v_type = "neutral"
        if rsi_val < 32 and curr_price < bb_lower: verdict_text, verdict_class, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 68 or curr_price > bb_upper: verdict_text, verdict_class, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verdict_text, verdict_class, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        return {
            "symbol": s, "price": curr_price, "rsi": rsi_val, "sma50": sma50, "sma100": sma100, "sma200": sma200,
            "pivot": pivot, "macd": macd_val, "verdict": verdict_text, "v_class": verdict_class, "v_type": v_type, 
            "shares": shares, "sl": curr_price - sl_margin, "tp": curr_price + (atr * 3.5), 
            "news": market_news, "df": df_raw.tail(70), "position_value": shares * curr_price,
            "atr_pct": (sl_margin / curr_price) * 100
        }
    except Exception: return None

# ==============================================================================
# SEKCJA 4: PANEL STEROWANIA (SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.title("🚜 GOLDEN v71 PRO")
    st.markdown("---")
    st.session_state.risk_cap = st.number_input("Twój Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na transakcję (%)", 0.1, 5.0, st.session_state.risk_pct)
    ticker_input = st.text_area("Symbole (BBI, BTC-USD...):", value=load_tickers(), height=250)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_input)
        st.cache_data.clear()
        st.rerun()
    
    refresh_rate = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_rate * 1000, key="monster_refresh_v71")

# ==============================================================================
# SEKCJA 5: GŁÓWNA LOGIKA WYŚWIETLANIA
# ==============================================================================
tickers = [x.strip().upper() for x in ticker_input.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=refresh_rate)
def fetch_data(s_list):
    res = []
    p = st.progress(0)
    for i, s in enumerate(s_list):
        d = get_monster_analysis(s)
        if d: res.append(d)
        p.progress((i + 1) / len(s_list))
    p.empty()
    return res

data_list = fetch_data(tickers)

if data_list:
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL")
    top_10 = sorted(data_list, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for idx, d in enumerate(top_10):
        with t_cols[idx % 5]:
            b_type = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""<div class="top-mini-tile {b_type}"><b>{d['symbol']}</b><br><small>RSI: {d['rsi']:.0f}</small><br><span class="{d['v_class']}">{d['verdict']}</span></div>""", unsafe_allow_html=True)

    st.divider()

    for i in range(0, len(data_list), 5):
        row = st.columns(5)
        for idx, d in enumerate(data_list[i:i+5]):
            with row[idx]:
                border = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {border};">
                    <div>
                        <div style="font-size:2.2rem; font-weight:bold; letter-spacing:-1px;">{d['symbol']}</div>
                        <div style="color:#58a6ff; font-size:1.5rem; margin-bottom:15px;">{d['price']:.2f} PLN</div>
                        <div style="margin: 20px 0;"><span class="{d['v_class']}">{d['verdict']}</span></div>
                    </div>
                    <div class="pos-calc-box">
                        <span class="pos-label">Ilość do kupna:</span><br>
                        <span class="pos-val">{d['shares']} szt.</span>
                        <small>Wartość: {d['position_value']:.0f} PLN</small>
                    </div>
                    <div class="tech-grid">
                        <div class="tech-row"><span class="t-lab">SMA 200:</span><span class="t-val" style="color:{'#00ff88' if d['price']>d['sma200'] else '#ff4b4b'};">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="t-lab">SMA 100/50:</span><span class="t-val">{d['sma100']:.1f}/{d['sma50']:.1f}</span></div>
                        <div class="tech-row"><span class="t-lab">Pęd MACD:</span><span class="t-val" style="color:{'#00ff88' if d['macd']>0 else '#ff4b4b'};">{d['macd']:.2f}</span></div>
                        <div class="tech-row"><span class="t-lab">PIVOT:</span><span class="t-val" style="color:#f1e05a;">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="t-lab">RSI (14):</span><span class="t-val" style="color:{'#00ff88' if d['rsi']<35 else '#ff4b4b' if d['rsi']>65 else '#8b949e'}; font-weight:900;">{d['rsi']:.0f}</span></div>
                        <div class="tech-row"><span class="t-lab">Dystans SL:</span><span class="t-val" style="color:#ff4b4b;">{d['atr_pct']:.1f}%</span></div>
                    </div>
                """, unsafe_allow_html=True)

                if st.button(f"🤖 ANALIZA AI: {d['symbol']}", key=f"btn_{d['symbol']}"):
                    if AI_KEY:
                        try:
                            with st.spinner("AI Analizuje..."):
                                client = OpenAI(api_key=AI_KEY)
                                resp = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[{"role": "user", "content": f"Analiza {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.0f}, MACD {d['macd']:.2f}. Strategia: SL {d['sl']:.2f}, TP {d['tp']:.2f}. Podaj konkretny plan w 3 punktach."}],
                                    max_tokens=300
                                )
                                st.session_state.ai_results[d['symbol']] = resp.choices[0].message.content
                        except Exception as e: st.error(f"Błąd AI: {str(e)}")
                    else: st.warning("Brak klucza w skrytce!")

                if d['symbol'] in st.session_state.ai_results:
                    st.markdown(f"""<div class="ai-strategy-box">{st.session_state.ai_results[d['symbol']]}</div>""", unsafe_allow_html=True)
                    if st.button("❌ Zamknij", key=f"cls_{d['symbol']}"):
                        del st.session_state.ai_results[d['symbol']]
                        st.rerun()

                st.markdown(f"""<div style="text-align:left; border-top:1px dashed #30363d; margin-top:20px; padding-top:15px;"><b>📢 NEWSY:</b>{"".join([f'<a class="news-link" href="{n["link"]}" target="_blank">• {n["title"]}</a>' for n in d['news']])}</div></div>""", unsafe_allow_html=True)
                
                with st.expander("📊 WYKRES ŚWIECOWY"):
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'], name="Cena")])
                    fig.add_trace(go.Scatter(x=d['df'].index, y=d['df']['Close'].rolling(200).mean(), line=dict(color='red', width=1.5), name="SMA200"))
                    fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

else: st.error("Błąd pobierania danych.")

st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:60px;'>v71.0 FINAL | {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
