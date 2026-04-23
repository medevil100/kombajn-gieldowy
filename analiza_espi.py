import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I STYLE ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA GOLDEN v16.4", page_icon="🍯", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    /* Styl kafli TOP 10 */
    .top-tile { background: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .verdict-badge { padding: 5px 15px; border-radius: 20px; font-weight: bold; text-transform: uppercase; font-size: 0.8rem; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    .analysis-box { background: #070a0e; padding: 15px; border-left: 5px solid #f1c40f; border-radius: 5px; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"
    return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"

# --- 2. SILNIK DANYCH ---
def get_data(symbol):
    try:
        d1d = yf.download(symbol, period="2y", interval="1d", progress=False, auto_adjust=True)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False, auto_adjust=True)
        if d15.empty or d1d.empty: return None
        if isinstance(d15.columns, pd.MultiIndex): d15.columns = d15.columns.get_level_values(0)
        if isinstance(d1d.columns, pd.MultiIndex): d1d.columns = d1d.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        sma200 = float(d1d['Close'].rolling(200).mean().iloc[-1])
        h_p, l_p, c_p = float(d1d['High'].iloc[-2]), float(d1d['Low'].iloc[-2]), float(d1d['Close'].iloc[-2])
        pivot = (h_p + l_p + c_p) / 3
        
        delta = d1d['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        atr = float((d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1])
        change = ((price - c_p) / c_p * 100)

        if rsi < 32: verdict, v_class = "KUP", "v-buy"
        elif rsi > 68: verdict, v_class = "SPRZEDAJ", "v-sell"
        else: verdict, v_class = "CZEKAJ", "v-wait"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma200": sma200, "pivot": pivot,
            "verdict": verdict, "v_class": v_class, "change": change,
            "peak": float(d1d['High'].max()), "bottom": float(d1d['Low'].min()),
            "tp": price + (atr * 2), "sl": price - (atr * 1.5), "df": d15
        }
    except: return None

# --- 3. SIDEBAR (Z PRZYCISKIEM ZAPISZ) ---
with st.sidebar:
    st.title("🍯 v16.4 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f:
            f.write(t_input)
        st.success("Lista zapisana!")
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 4. LOGIKA GŁÓWNA ---
t_list = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    # --- SEKCOJA TOP 10 (KAFELKI) ---
    st.subheader("🔥 TOP SYGNAŁY")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with cols[i % 5]:
            st.markdown(f"""
                <div class="top-tile">
                    <small>{d['symbol']}</small><br>
                    <b style="font-size:1.2rem;">{d['price']:.2f}</b><br>
                    <span class="verdict-badge {d['v_class']}">{d['verdict']}</span>
                </div><br>
            """, unsafe_allow_html=True)

    # --- SZCZEGÓŁOWE KARTY ---
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown(f"## {d['symbol']} <span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            # Tabela parametrów
            st.markdown(f"""
                <div class="metric-row"><span>RSI (14d)</span><b>{d['rsi']:.1f}</b></div>
                <div class="metric-row"><span>Pivot Point</span><b style="color:orange;">{d['pivot']:.2f}</b></div>
                <div class="metric-row"><span>SMA 200</span><b style="color:#ff4b4b;">{d['sma200']:.2f}</b></div>
                <div class="metric-row"><span>Szczyt 52t</span><b>{d['peak']:.2f}</b></div>
                <div class="metric-row"><span>Dołek 52t</span><b>{d['bottom']:.2f}</b></div>
                <div class="metric-row"><b style="color:#00ff88;">TARGET (TP)</b><b>{d['tp']:.2f}</b></div>
                <div class="metric-row"><b style="color:#ff4b4b;">STOP LOSS (SL)</b><b>{d['sl']:.2f}</b></div>
            """, unsafe_allow_html=True)

            if api_key and st.button(f"🧠 ANALIZA AI", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = (f"Działaj jako Senior Trader. Symbol: {d['symbol']}, Cena: {d['price']}, "
                          f"SMA200: {d['sma200']}, RSI: {d['rsi']}, Szczyt: {d['peak']}. "
                          f"PODAJ: 1. WERDYKT (KUP/SPRZEDAJ/CZEKAJ), 2. CENA WEJŚCIA, 3. RYZYKO 1-10.")
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"res_{d['symbol']}"] = resp.choices[0].message.content
            
            if f"res_{d['symbol']}" in st.session_state:
                st.markdown(f'<div class="analysis-box"><b>AI STRATEGIA:</b><br>{st.session_state[f"res_{d['symbol']}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-80:], open=d['df']['Open'][-80:], high=d['df']['High'][-80:], low=d['df']['Low'][-80:], close=d['df']['Close'][-80:])])
            fig.add_hline(y=d['pivot'], line_color="orange", line_dash="dot")
            fig.add_hline(y=d['sma200'], line_color="red")
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Dodaj poprawne symbole i zapisz listę w panelu bocznym.")
