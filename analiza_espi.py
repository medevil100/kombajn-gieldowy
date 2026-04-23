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
st.set_page_config(page_title="AI ALPHA GOLDEN v16.2", page_icon="🍯", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 25px; }
    .sl-alert { border: 2px solid #ff4b4b !important; background: #2d1616 !important; }
    .verdict-badge { padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; text-transform: uppercase; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .analysis-box { background: #070a0e; padding: 15px; border-left: 5px solid #f1c40f; border-radius: 5px; margin-top: 15px; }
    .metric-table { width: 100%; margin-top: 10px; }
    .metric-table td { padding: 8px; border-bottom: 1px solid #21262d; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, ALE.WA, NVDA, TSLA, BTC-USD"
    return "PKO.WA, ALE.WA, NVDA, TSLA, BTC-USD"

# --- 2. SILNIK POBIERANIA DANYCH ---
def get_data(symbol):
    try:
        # Pobieranie danych dziennych i 15-minutowych
        d1d = yf.download(symbol, period="2y", interval="1d", progress=False, auto_adjust=True)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False, auto_adjust=True)
        
        if d15.empty or d1d.empty: return None
        
        # Naprawa MultiIndex (częsty błąd yfinance)
        if isinstance(d15.columns, pd.MultiIndex): d15.columns = d15.columns.get_level_values(0)
        if isinstance(d1d.columns, pd.MultiIndex): d1d.columns = d1d.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        sma200 = float(d1d['Close'].rolling(200).mean().iloc[-1])
        
        # Pivot Point na podstawie wczorajszej sesji
        h_p, l_p, c_p = float(d1d['High'].iloc[-2]), float(d1d['Low'].iloc[-2]), float(d1d['Close'].iloc[-2])
        pivot = (h_p + l_p + c_p) / 3
        
        # RSI (14)
        delta = d1d['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        peak_52w = float(d1d['High'].max())
        bottom_52w = float(d1d['Low'].min())
        atr = float((d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1])

        # Logika werdyktu
        if rsi < 32: verdict, v_class = "KUP", "v-buy"
        elif rsi > 68: verdict, v_class = "SPRZEDAJ", "v-sell"
        else: verdict, v_class = "CZEKAJ", "v-wait"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma200": sma200, "pivot": pivot,
            "verdict": verdict, "v_class": v_class, "peak": peak_52w, "bottom": bottom_52w,
            "tp": price + (atr * 2), "sl": price - (atr * 1.5),
            "df": d15, "change": ((price - c_p) / c_p * 100)
        }
    except: return None

# --- 3. SIDEBAR I ODŚWIEŻANIE ---
with st.sidebar:
    st.title("🍯 v16.2 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole (np. PKO.WA, NVDA)", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 4. WYŚWIETLANIE DANYCH ---
tickers_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, tickers_list)) if r]

if data_list:
    # Sekcja TOP 10 (Sygnały ekstremalne)
    st.subheader("🔥 TOP SYGNAŁY (RSI)")
    top_cols = st.columns(min(len(data_list), 5))
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:5]
    for i, d in enumerate(sorted_top):
        with top_cols[i]:
            st.markdown(f'''<div style="background:#161b22; padding:10px; border-radius:10px; border:1px solid #30363d; text-align:center;">
                <small>{d['symbol']}</small><br>
                <span class="verdict-badge {d['v_class']}">{d['verdict']}</span><br>
                <b>{d['price']:.2f}</b></div>''', unsafe_allow_html=True)

    # Lista główna
    for d in data_list:
        is_alert = "sl-alert" if d['price'] <= d['sl'] else ""
        st.markdown(f'<div class="ticker-card {is_alert}">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown(f'## {d["symbol"]} <span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span>', unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"""
                <table class="metric-table">
                    <tr><td>RSI (14d)</td><td style="text-align:right;">{d['rsi']:.1f}</td></tr>
                    <tr><td>PIVOT (Pomarańcz)</td><td style="text-align:right; color:orange;">{d['pivot']:.2f}</td></tr>
                    <tr><td>SMA200 (Czerwony)</td><td style="text-align:right; color:#ff4b4b;">{d['sma200']:.2f}</td></tr>
                    <tr style="color:#00ff88;"><td><b>TARGET (TP)</b></td><td style="text-align:right;"><b>{d['tp']:.2f}</b></td></tr>
                    <tr style="color:#ff4b4b;"><td><b>STOP LOSS (SL)</b></td><td style="text-align:right;"><b>{d['sl']:.2f}</b></td></tr>
                </table>""", unsafe_allow_html=True)

            if api_key and st.button(f"🧠 ANALIZA AI: {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = f"Analiza techniczna {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, SMA200 {d['sma200']:.2f}. Podaj werdykt i cel."
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"res_{d['symbol']}"] = resp.choices[0].message.content
            
            if f"res_{d['symbol']}" in st.session_state:
                st.markdown(f'<div class="analysis-box"><b>WERDYKT AI:</b><br>{st.session_state[f"res_{d['symbol']}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:])])
            fig.add_hline(y=d['pivot'], line_color="orange", line_dash="dot")
            fig.add_hline(y=d['sma200'], line_color="red")
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj symbole w panelu bocznym (np. PKO.WA, NVDA), aby rozpocząć analizę.")
