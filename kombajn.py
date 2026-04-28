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

# --- 1. KONFIGURACJA I PAMIĘĆ SESJI ---
DB_FILE = "moje_spolki.txt"

st.set_page_config(page_title="AI ALPHA GOLDEN v26 PRO", page_icon="🏆", layout="wide")

# Inicjalizacja stanów sesji
if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "risk_cap" not in st.session_state: st.session_state.risk_cap = 10000.0
if "risk_pct" not in st.session_state: st.session_state.risk_pct = 1.0

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
        except: return "NVDA, TSLA, BTC-USD, PKO.WA"
    return "NVDA, TSLA, BTC-USD, PKO.WA"

# --- 2. STYLE WIZUALNE ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0f111a, #1a1c2b); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px;
    }
    .top-tile {
        background: #111420; padding: 12px; border-radius: 10px; border-bottom: 3px solid #00ff88; 
        text-align: center; min-height: 180px;
    }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    .calc-box { background: rgba(0, 255, 136, 0.1); border: 1px dashed #00ff88; padding: 10px; border-radius: 8px; margin-top: 10px; font-size: 0.85rem; }
    .stat-header { background: #0d1117; padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        
        if h1.empty or d1.empty: return None
        h1, d1 = fix_col(h1), fix_col(d1)
        
        price = float(h1['Close'].iloc[-1])
        cp = float(d1['Close'].iloc[-2]) 
        
        try:
            info = t.info
            bid = info.get('bid') or price * 0.9995
            ask = info.get('ask') or price * 1.0005
        except:
            bid, ask = price * 0.9995, price * 1.0005
        
        sma200 = float(d1['Close'].rolling(200).mean().iloc[-1])
        y_high = float(d1['High'].max())
        y_low = float(d1['Low'].min())
        
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = float(100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1])
        
        verd, vcl = "CZEKAJ 🟡", ""
        if rsi < 32: verd, vcl = "KUP 🟢", "sig-buy"
        elif rsi > 68: verd, vcl = "SPRZEDAJ 🔴", "sig-sell"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "sma200": sma200, "verdict": verd, "vcl": vcl, "y_high": y_high, "y_low": y_low,
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🏆 GOLDEN v26 PRO")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    st.subheader("⚙️ Zarządzanie Ryzykiem")
    st.session_state.risk_cap = st.number_input("Kapitał Portfela:", value=float(st.session_state.risk_cap))
    st.session_state.risk_pct = st.slider("Ryzyko na transakcję (%)", 0.1, 5.0, float(st.session_state.risk_pct))
    
    t_input = st.text_area("Lista Symboli (CSV):", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(t_input)
        st.success("Zapisano listę!")
    
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)
    if st.button("🧹 Wyczyść analizy AI"):
        st.session_state.ai_results = {}
        st.rerun()

st_autorefresh(interval=refresh * 1000, key="v26_refresh_main")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=8) as executor:
    all_data = [d for d in list(executor.map(get_analysis, tickers)) if d is not None]

if all_data:
    # --- PANEL STATYSTYK ---
    st.markdown('<div class="stat-header">', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
    s1.metric("Kapitał", f"{st.session_state.risk_cap:,.0f}")
    s2.metric("Ryzyko/Trade", f"{risk_val:,.2f}")
    s3.metric("Aktywne Symbole", len(all_data))
    s4.metric("Skaner", "Online 🟢")
    st.markdown('</div>', unsafe_allow_html=True)

    # --- RANKING TOP ---
    st.subheader("🔥 RANKING SYGNAŁÓW (RSI)")
    top_cols = st.columns(5)
    for i, d in enumerate(sorted(all_data, key=lambda x: x['rsi'])[:10]):
        with top_cols[i % 5]:
            st.markdown(f"""<div class="top-tile"><b>{d['symbol']}</b><br><span style="font-size:1.1rem; color:#00ff88;">{d['price']:.2f}</span><br><div class="bid-ask-mini">B: {d['bid']:.2f} | A: {d['ask']:.2f}</div><div class="{d['vcl']}">{d['verdict']}</div><small>RSI: {d['rsi']:.1f}</small></div>""", unsafe_allow_html=True)

    st.divider()

    # --- KARTY INSTRUMENTÓW ---
    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            
            with c1:
                st.markdown(f"<h3 class='{d['vcl']}'>{d['symbol']}</h3>", unsafe_allow_html=True)
                st.metric("CENA", f"{d['price']:.4f}", f"{d['change']:.2f}%")
                st.markdown(f"""
                    <div class="metric-row"><span>RSI (1h)</span><b>{d['rsi']:.1f}</b></div>
                    <div class="metric-row"><span>SMA 200</span><b>{d['sma200']:.2f}</b></div>
                    <div class="metric-row"><span style="color:#00ff88;">High 52t</span><b>{d['y_high']:.2f}</b></div>
                    <div class="metric-row"><span style="color:#ff4b4b;">Low 52t</span><b>{d['y_low']:.2f}</b></div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:])])
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{d['symbol']}")

            with c3:
                st.write(f"BID/ASK: `{d['bid']:.2f}` / `{d['ask']:.2f}`")
                if api_key:
                    if st.button(f"🧠 AI STRATEGIA", key=f"btn_{d['symbol']}"):
                        try:
                            client = OpenAI(api_key=api_key)
                            prompt = (f"Jesteś bezwzględnym traderem. Analiza {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, SMA200 {d['sma200']:.2f}. "
                                      f"Podaj konkretnie: 1. AKCJA, 2. WEJŚCIE, 3. SL, 4. TP, 5. POWÓD (max 10 słów). "
                                      f"Format SL musi być dokładnie taki: 'SL: [liczba]'. Nie lej wody.")
                            resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                            st.session_state.ai_results[d['symbol']] = resp.choices[0].message.content
                        except Exception as e:
                            st.error(f"Błąd AI: {e}")
                    
                    if d['symbol'] in st.session_state.ai_results:
                        res_text = st.session_state.ai_results[d['symbol']]
                        st.info(res_text)
                        
                        # KALKULATOR POZYCJI
                        sl_match = re.search(r"SL:\s*([\d\.,]+)", res_text)
                        if sl_match:
                            try:
                                sl_val = float(sl_match.group(1).replace(',', '.'))
                                diff = abs(d['price'] - sl_val)
                                if diff > 0:
                                    shares = risk_val / diff
                                    st.markdown(f"""<div class="calc-box">
                                        <b>Kalkulator Pozycji:</b><br>
                                        Ryzyko kwotowe: {risk_val:.2f}<br>
                                        Ilość: <b>{int(shares)} szt.</b><br>
                                        Wartość pozycji: {(int(shares) * d['price']):.2f}
                                    </div>""", unsafe_allow_html=True)
                            except: pass
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj symbole w panelu bocznym i upewnij się, że masz klucz OpenAI.")
