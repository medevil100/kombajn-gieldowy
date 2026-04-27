import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime

# --- 1. KONFIGURACJA PLIKÓW I PAMIĘCI ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
        except: return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
    return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"

# Konfiguracja strony
st.set_page_config(page_title="AI ALPHA GOLDEN v38.5 PLN", page_icon="🚜", layout="wide")

# Inicjalizacja stanów sesji
if 'risk_cap' not in st.session_state:
    st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state:
    st.session_state.risk_pct = 1.0

# --- 2. BIBLIOTEKA STYLÓW CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0d1117, #050505); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; 
        margin-bottom: 20px;
    }
    .top-tile-buy { 
        border: 2px solid #00ff88; box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.2); 
        text-align: center; padding: 15px; border-radius: 15px; min-height: 200px; background: #0d1117;
    }
    .top-tile-sell { 
        border: 2px solid #ff4b4b; box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.2); 
        text-align: center; padding: 15px; border-radius: 15px; min-height: 200px; background: #0d1117;
    }
    .top-tile-neutral { 
        border: 1px solid #30363d; text-align: center; padding: 15px; border-radius: 15px; 
        min-height: 200px; background: #0d1117;
    }
    .sig-buy { color: #00ff88; font-weight: bold; text-shadow: 0 0 10px rgba(0,255,136,0.5); }
    .sig-sell { color: #ff4b4b; font-weight: bold; text-shadow: 0 0 10px rgba(255,75,75,0.5); }
    .pos-calc { 
        background: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; 
        padding: 10px; margin-top: 10px; border-radius: 5px; font-size: 0.9rem;
    }
    .stat-label { color: #8b949e; font-size: 0.85rem; }
    .stat-value { color: #ffffff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. PANCERNY SILNIK ANALIZY (FIX DLA BRAKU DANYCH) ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        if not symbol: return None
        
        # yf.download jest stabilniejszy niż Ticker().history
        df = yf.download(symbol, period="250d", interval="1d", progress=False, group_by='ticker')
        
        # Naprawa formatu danych (MultiIndex fix)
        if isinstance(df.columns, pd.MultiIndex):
            if symbol in df.columns.levels[0]:
                df = df[symbol]
            else:
                return None
            
        if df.empty or len(df) < 30: return None
        
        price = float(df['Close'].iloc[-1])
        
        # RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi_val = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR (zmienność)
        tr = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['Close'].shift()).abs(),
            (df['Low'] - df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Średnia i ekstrema
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        y_high = df['High'].max()
        y_low = df['Low'].min()
        
        # Ryzyko w PLN
        risk_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.5
        
        if sl_dist > 0:
            shares = int(risk_money / sl_dist)
            pos_value = shares * price
        else:
            shares, pos_value = 0, 0

        # Werdykt
        v_type = "neutral"
        if rsi_val < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "rsi": rsi_val, "atr": atr,
            "verd": verd, "vcl": vcl, "v_type": v_type, "sma200": sma200,
            "sl": price - sl_dist, "tp": price + (atr * 3), "shares": shares,
            "pos_value": pos_value, "y_high": y_high, "y_low": y_low, "df": df.tail(40)
        }
    except Exception as e:
        return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v38.5 PLN")
    st.markdown("---")
    
    st.subheader("💰 PORTFEL (PLN)")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    st.subheader("📝 LISTA SYMBOLI")
    ticker_area = st.text_area("Symbole (PKO.WA, BTC-USD...):", value=load_tickers(), height=200)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_area)
        st.cache_data.clear() # Czyścimy cache przy zapisie
        st.rerun()
        
    refresh_rate = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_rate * 1000, key="v38_pln_refresh")

# --- 5. LOGIKA GŁÓWNA ---
tickers_list = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=60)
def get_all_results(t_list):
    results = []
    for t in t_list:
        data = get_analysis(t)
        if data:
            results.append(data)
    return results

data_ready = get_all_results(tickers_list)

if data_ready:
    st.subheader("🏆 TERMINAL SYGNAŁÓW PLN")
    
    # Kafelki Top 10
    for i in range(0, len(data_ready[:10]), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                st.markdown(f"""
                    <div class="top-tile-{d['v_type']}">
                        <div style="font-size:1.3rem; font-weight:bold;">{d['symbol']}</div>
                        <div style="color:#58a6ff; font-size:1.1rem;">{d['price']:.2f} PLN</div>
                        <div class="{d['vcl']}" style="margin:10px 0;">{d['verd']}</div>
                        <div class="pos-calc">
                            <b>Kup: {d['shares']} szt.</b><br>
                            <small>Wartość: {d['pos_value']:.0f} PLN</small>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

    st.divider()

    # Szczegóły i wykresy
    for d in data_ready:
        with st.expander(f"📊 {d['symbol']} - Szczęgóły (Cena: {d['price']:.2f} PLN)"):
            c1, c2 = st.columns([2, 1])
            with c1:
                fig = go.Figure(data=[go.Candlestick(
                    x=d['df'].index, open=d['df']['Open'], high=d['df']['High'],
                    low=d['df']['Low'], close=d['df']['Close'], name="Cena"
                )])
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.markdown(f"**RSI:** {d['rsi']:.1f}")
                st.markdown(f"**Stop Loss:** :red[{d['sl']:.2f} PLN]")
                st.markdown(f"**Take Profit:** :green[{d['tp']:.2f} PLN]")
                st.markdown(f"**SMA 200:** {d['sma200']:.2f} PLN")
else:
    st.error("Brak danych do wyświetlenia. Upewnij się, że symbole są poprawne (np. PKO.WA) i masz połączenie z internetem.")

st.markdown(f"<p style='text-align:center; color:gray;'>Aktualizacja: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)
