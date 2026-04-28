import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import re

# --- 1. KONFIGURACJA ---
DB_FILE = "moje_spolki.txt"
st.set_page_config(page_title="AI ALPHA GOLDEN v26 PRO", page_icon="🏆", layout="wide")

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "last_signals" not in st.session_state: st.session_state.last_signals = {}

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
        except: return "NVDA, TSLA, BTC-USD"
    return "NVDA, TSLA, BTC-USD"

# --- 2. STYLE I AUDIO ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0f111a, #1a1c2b); 
        padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px;
    }
    .sig-buy { color: #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 2px 8px; border-radius: 5px; background: rgba(0,255,136,0.1); }
    .sig-sell { color: #ff4b4b; font-weight: bold; border: 1px solid #ff4b4b; padding: 2px 8px; border-radius: 5px; background: rgba(255,75,75,0.1); }
    .metric-box { background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; text-align: center; font-size: 0.9rem; }
    .ai-brief { background: rgba(88, 166, 255, 0.05); padding: 12px; border-radius: 8px; border-left: 3px solid #58a6ff; margin-top: 15px; font-size: 0.85rem; line-height: 1.4; }
    </style>
    """, unsafe_allow_html=True)

# Funkcja do dźwięku (ukryta w HTML)
def play_sound():
    sound_html = """
    <audio autoplay><source src="https://soundjay.com" type="audio/mpeg"></audio>
    """
    st.markdown(sound_html, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def get_analysis(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        h1 = t.history(period="15d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty or d1.empty: return None
        h1, d1 = fix_col(h1), fix_col(d1)
        
        price = float(h1['Close'].iloc[-1])
        last_10_days = d1.tail(10)[['High', 'Low', 'Close']].to_string()
        
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = float(100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1])
        
        return {
            "symbol": symbol.strip().upper(), "price": price, "rsi": rsi, 
            "df": h1, "d1_history": last_10_days,
            "change": ((price - d1['Close'].iloc[-2]) / d1['Close'].iloc[-2] * 100)
        }
    except: return None

def get_ai_verdict(d, api_key):
    if d['symbol'] in st.session_state.ai_results:
        return st.session_state.ai_results[d['symbol']]
    
    try:
        client = OpenAI(api_key=api_key)
        prompt = (f"Jesteś analitykiem technicznym. Analizuj {d['symbol']} (Cena: {d['price']}). RSI: {d['rsi']:.1f}. "
                  f"Ostatnie 10 dni H/L/C:\n{d['d1_history']}\n"
                  f"Format odpowiedzi (BEZ LANIA WODY):\n"
                  f"WERDYKT: [KUP/SPRZEDAJ/TRZYMAJ]\n"
                  f"SL: [cena] | TP: [cena]\n"
                  f"ANALIZA: [max 2 konkretne zdania o trendzie z 10 świec]")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        res = resp.choices.message.content
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return "Błąd AI"

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🏆 GOLDEN v26 PRO")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli:", value=load_tickers(), height=120)
    if st.button("💾 ZAPISZ I SKANUJ"):
        st.session_state.ai_results = {}
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_input)
        st.rerun()
    refresh = st.select_slider("Auto-Refresh (s)", options=[30, 60, 300], value=60)
    st_autorefresh(interval=refresh * 1000, key="auto_ref_v26")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=5) as executor:
    all_data = [d for d in list(executor.map(get_analysis, tickers)) if d is not None]

if all_data:
    st.subheader(f"📊 MONITORING RYNKU - {datetime.now().strftime('%H:%M:%S')}")
    
    for d in all_data:
        # Pobieramy werdykt AI
        ai_info = get_ai_verdict(d, api_key) if api_key else "Brak klucza AI"
        
        # Ekstrakcja danych z tekstu AI
        verdict_match = re.search(r"WERDYKT:\s*(\w+)", ai_info)
        sl_match = re.search(r"SL:\s*([\d\.,]+)", ai_info)
        tp_match = re.search(r"TP:\s*([\d\.,]+)", ai_info)
        analiza_match = re.search(r"ANALIZA:\s*(.*)", ai_info, re.DOTALL)

        current_v = verdict_match.group(1) if verdict_match else "TRZYMAJ"
        sl_txt = sl_match.group(1) if sl_match else "---"
        tp_txt = tp_match.group(1) if tp_match else "---"
        brief = analiza_match.group(1) if analiza_match else "Brak analizy."

        # System powiadomień dźwiękowych
        if "KUP" in current_v.upper() and st.session_state.last_signals.get(d['symbol']) != "KUP":
            play_sound()
            st.session_state.last_signals[d['symbol']] = "KUP"

        v_class = "sig-buy" if "KUP" in current_v.upper() else "sig-sell" if "SPRZEDAJ" in current_v.upper() else ""

        with st.container():
            st.markdown(f"""
            <div class="ticker-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="margin:0;">{d['symbol']} <span class="{v_class}" style="font-size: 0.9rem;">{current_v}</span></h2>
                    <div style="text-align: right;">
                        <span style="font-size: 1.4rem; font-weight: bold;">{d['price']:.2f}</span>
                        <span style="color: {'#00ff88' if d['change'] > 0 else '#ff4b4b'}; font-size: 0.9rem;">({d['change']:.2f}%)</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-top: 15px;">
                    <div class="metric-box">RSI: <br><b>{d['rsi']:.1f}</b></div>
                    <div class="metric-box" style="border-bottom: 2px solid #ff4b4b;">STOP LOSS: <br><b style="color:#ff4b4b;">{sl_txt}</b></div>
                    <div class="metric-box" style="border-bottom: 2px solid #00ff88;">TAKE PROFIT: <br><b style="color:#00ff88;">{tp_txt}</b></div>
                    <div class="metric-box">ZMIANA 24H: <br><b>{d['change']:.2f}%</b></div>
                </div>
                <div class="ai-brief">
                    <b>💡 ANALIZA KONTEKSTOWA:</b><br>{brief}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🔍 Interaktywny Wykres 1H"):
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:])])
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")
else:
    st.info("👈 Wpisz symbole w panelu bocznym (np. AAPL, TSLA, BTC-USD).")
