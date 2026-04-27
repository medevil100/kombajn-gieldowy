import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import requests

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.4", page_icon="🚜", layout="wide")

# Stabilna sesja
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"})

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                c = f.read().strip()
                return c if c else "BTC-USD, NVDA, TSLA"
        except: return "BTC-USD, NVDA, TSLA"
    return "BTC-USD, NVDA, TSLA"

if "capital" not in st.session_state: st.session_state.capital = 10000.0
if "risk_per_trade" not in st.session_state: st.session_state.risk_per_trade = 1.0

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .pos-box { background: rgba(88, 166, 255, 0.1); border: 1px solid #58a6ff; padding: 15px; border-radius: 8px; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieramy dane z auto_adjust dla stabilności
        df = yf.download(symbol, period="150d", interval="1d", progress=False, session=session, auto_adjust=True)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(df['Close'].iloc[-1])
        sma200 = df['Close'].rolling(min(len(df), 200)).mean().iloc[-1]
        atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        risk_amount = st.session_state.capital * (st.session_state.risk_per_trade / 100)
        sl_dist = atr * 1.5
        shares = int(risk_amount / sl_dist) if sl_dist > 0 else 0
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, 
            "trend": "Wzrostowy 🚀" if price > sma200 else "Spadkowy 📉",
            "trend_col": "#00ff88" if price > sma200 else "#ff4b4b",
            "shares": shares, "sl": price - sl_dist, "tp": price + (atr * 3.5), "df": df
        }
    except Exception as e:
        return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ KOMB_v12.4")
    st.session_state.capital = st.number_input("Kapitał ($)", value=st.session_state.capital)
    st.session_state.risk_per_trade = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_per_trade)
    
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole", value=load_tickers())
    
    if st.button("Zapisz i Odśwież"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
        st.rerun()
    
    # POPRAWIONE OPCJE
    refresh_val = st.select_slider("Odświeżanie (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh_val * 1000, key="global_refresh")

# --- 5. GŁÓWNA LOGIKA ---
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if not tickers:
    st.info("Wpisz symbole w sidebarze.")
else:
    with st.spinner("Pobieranie danych z rynku..."):
        data_list = []
        for t in tickers:
            res = get_analysis(t)
            if res: data_list.append(res)

    if not data_list:
        st.error("Błąd pobierania danych. Yahoo Finance może blokować zapytania. Spróbuj ponownie za chwilę.")
    else:
        for d in data_list:
            with st.container():
                st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.subheader(f"{d['symbol']}")
                    st.write(f"Cena: **{d['price']:.2f}** ({d['trend']})")
                    
                    st.markdown(f"""
                        <div class="pos-box">
                            Sugerowana pozycja: <b>{d['shares']} szt.</b><br>
                            <span style="color:#ff4b4b;">SL: {d['sl']:.2f}</span> | 
                            <span style="color:#00ff88;">TP: {d['tp']:.2f}</span>
                        </div>
                    """, unsafe_allow_html=True)

                    if api_key and st.button(f"Analiza AI {d['symbol']}", key=f"ai_{d['symbol']}"):
                        client = OpenAI(api_key=api_key)
                        prompt = f"Krótki werdykt dla {d['symbol']}, RSI {d['rsi']:.1f}, Trend {d['trend']}"
                        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                        st.info(resp.choices[0].message.content)
                
                with c2:
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:])])
                    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
