import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor
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
st.set_page_config(page_title="AI ALPHA GOLDEN v38 PLN PRO", page_icon="🚜", layout="wide")

# Inicjalizacja stanów sesji
if 'risk_cap' not in st.session_state:
    st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state:
    st.session_state.risk_pct = 1.0

# --- 2. PEŁNA BIBLIOTEKA STYLÓW CSS ---
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
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: 'Courier New', monospace; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: 'Courier New', monospace; }
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

# --- 3. ZOPTYMALIZOWANY SILNIK ANALIZY ---
def get_analysis(symbol):
    """Pobiera dane bez użycia t.info, co zapobiega zawieszaniu skryptu."""
    try:
        symbol = symbol.strip().upper()
        if not symbol: return None
        t = yf.Ticker(symbol)
        
        # Pobieramy historię (szybkie i stabilne)
        df = t.history(period="250d", interval="1d")
        if df.empty: return None
        
        price = df['Close'].iloc[-1]
        
        # Obliczenia techniczne
        # RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi_val = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR (do Stop Loss)
        df['TR'] = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['Close'].shift()).abs(),
            (df['Low'] - df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr = df['TR'].rolling(14).mean().iloc[-1]
        
        # Poziomy techniczne
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        y_high = df['High'].max()
        y_low = df['Low'].min()
        
        # Zarządzanie ryzykiem (Position Sizing)
        risk_amount = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.5
        stop_loss = price - sl_dist
        take_profit = price + (atr * 3)
        
        # Ile akcji kupić? (Risk / Distance to SL)
        if sl_dist > 0:
            shares_to_buy = int(risk_amount / sl_dist)
            pos_value = shares_to_buy * price
        else:
            shares_to_buy, pos_value = 0, 0

        # Werdykt techniczny
        v_type = "neutral"
        if rsi_val < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "rsi": rsi_val, "atr": atr,
            "verd": verd, "vcl": vcl, "v_type": v_type, "sma200": sma200,
            "sl": stop_loss, "tp": take_profit, "shares": shares_to_buy,
            "pos_value": pos_value, "y_high": y_high, "y_low": y_low,
            "df": df.tail(40)
        }
    except:
        return None

# --- 4. PANEL BOCZNY (USTAWIENIA PLN) ---
with st.sidebar:
    st.title("🚜 GOLDEN v38 PLN")
    st.markdown("---")
    
    st.subheader("💰 PORTFEL I RYZYKO")
    st.session_state.risk_cap = st.number_input("Kapitał całkowity (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na transakcję (%)", 0.1, 5.0, st.session_state.risk_pct, help="Ile % kapitału stracisz, jeśli trafi SL")
    
    st.subheader("📝 LISTA OBSERWOWANYCH")
    ticker_area = st.text_area("Symbole (np. PKO.WA, ALE.WA, BTC-USD):", value=load_tickers(), height=250)
    
    if st.button("💾 ZAPISZ I ODŚWIEŻ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_area)
        st.success("Baza zaktualizowana!")
        st.rerun()
        
    refresh_rate = st.select_slider("Auto-odświeżanie (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh_rate * 1000, key="v38_pln_fsh")

# --- 5. LOGIKA GŁÓWNA I RENDEROWANIE ---
tickers_list = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=30)
def fetch_data(t_list):
    # Limitujemy workers do 5, aby Yahoo nie blokowało połączenia
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(get_analysis, t_list))
    return [r for r in results if r is not None]

data_ready = fetch_data(tickers_list)

if data_ready:
    # --- TOP 10 KAFELKI ---
    st.subheader("🏆 SYGNAŁY I KALKULACJA POZYCJI")
    
    # Wyświetlamy w rzędach po 5
    for i in range(0, len(data_ready[:10]), 5):
        row_data = data_ready[i:i+5]
        cols = st.columns(5)
        for idx, d in enumerate(row_data):
            with cols[idx]:
                st.markdown(f"""
                    <div class="top-tile-{d['v_type']}">
                        <div style="font-size:1.4rem; font-weight:bold;">{d['symbol']}</div>
                        <div style="color:#58a6ff; font-size:1.2rem; margin-bottom:5px;">{d['price']:.2f} PLN</div>
                        <div class="{d['vcl']}">{d['verd']}</div>
                        <hr style="border:0.5px solid #30363d; margin:10px 0;">
                        <small class="stat-label">RSI:</small> <small class="stat-value">{d['rsi']:.1f}</small><br>
                        <div class="pos-calc">
                            <b>Wielkość: {d['shares']} szt.</b><br>
                            <small>Wartość: {d['pos_value']:.0f} PLN</small>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

    st.divider()

    # --- SZCZEGÓŁOWA LISTA ANALITYCZNA ---
    st.subheader("📊 SZCZEGÓŁOWA ANALIZA TECHNICZNA")
    
    for d in data_ready:
        with st.expander(f"🔍 ANALIZA: {d['symbol']} | Cena: {d['price']:.2f} PLN | Sygnał: {d['verd']}"):
            c1, c2, c3 = st.columns([2, 1, 1])
            
            with c1:
                # Wykres świecowy
                fig = go.Figure(data=[go.Candlestick(
                    x=d['df'].index,
                    open=d['df']['Open'], high=d['df']['High'],
                    low=d['df']['Low'], close=d['df']['Close'],
                    name="Cena"
                )])
                fig.add_hline(y=d['sl'], line_dash="dash", line_color="#ff4b4b", annotation_text="STOP LOSS")
                fig.add_hline(y=d['tp'], line_dash="dash", line_color="#00ff88", annotation_text="TAKE PROFIT")
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,b=0,t=0))
                st.plotly_chart(fig, use_container_width=True)
            
            with c2:
                st.markdown("### 🛠 Parametry")
                st.write(f"**Cena:** {d['price']:.2f} PLN")
                st.write(f"**SMA 200:** {d['sma200']:.2f} PLN")
                st.write(f"**Trend:** {'HOSSA 📈' if d['price'] > d['sma200'] else 'BESSA 📉'}")
                st.write(f"**Roczny Max:** {d['y_high']:.2f}")
                st.write(f"**Roczny Min:** {d['y_low']:.2f}")
            
            with c3:
                st.markdown("### 🛡 Zarządzanie Ryzykiem")
                st.info(f"Ryzykujesz: {(st.session_state.risk_cap * st.session_state.risk_pct / 100):.2f} PLN")
                st.error(f"Stop Loss: {d['sl']:.2f} PLN")
                st.success(f"Take Profit: {d['tp']:.2f} PLN")
                st.warning(f"Kup: {d['shares']} jednostek")

else:
    st.warning("⚠️ Brak danych. Sprawdź czy symbole są poprawne (np. PKO.WA dla GPW) lub czy Yahoo Finance nie blokuje połączenia.")

# --- STOPKA ---
st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:50px;'>Ostatnia aktualizacja: {datetime.now().strftime('%H:%M:%S')} | AI ALPHA GOLDEN v38.4 PLN</div>", unsafe_allow_html=True)
