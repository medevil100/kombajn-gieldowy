import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA GOLDEN v16.2", page_icon="🍯", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "STX.WA, PKO.WA, NVDA, TSLA, BTC-USD"
    return "STX.WA, PKO.WA, NVDA, TSLA, BTC-USD"

# --- 2. STYLE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 25px; }
    .sl-alert { border: 2px solid #ff4b4b !important; background: #2d1616 !important; }
    .verdict-badge { padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; text-transform: uppercase; margin-left: 10px; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .analysis-box { background: #070a0e; padding: 15px; border-left: 5px solid #f1c40f; border-radius: 5px; margin: 10px 0; }
    .metric-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    .metric-table td { padding: 8px; border-bottom: 1px solid #21262d; font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_data(symbol):
    try:
        t_obj = yf.Ticker(symbol)
        # Pobieranie danych z obsługą MultiIndex
        d1d = yf.download(symbol, period="2y", interval="1d", progress=False)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        
        if d15.empty or d1d.empty: return None
        
        # Spłaszczanie kolumn (naprawa błędu pobierania)
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        sma200 = float(d1d['Close'].rolling(200).mean().iloc[-1])
        
        high_p = float(d1d['High'].iloc[-2])
        low_p = float(d1d['Low'].iloc[-2])
        close_p = float(d1d['Close'].iloc[-2])
        pivot = (high_p + low_p + close_p) / 3
        
        delta = d15['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        
        peak_52w = float(d1d['High'].max())
        bottom_52w = float(d1d['Low'].min())

        if rsi < 32: verdict, v_class = "KUP", "v-buy"
        elif rsi > 68: verdict, v_class = "SPRZEDAJ", "v-sell"
        else: verdict, v_class = "CZEKAJ", "v-wait"

        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma200": sma200, "pivot": pivot,
            "verdict": verdict, "v_class": v_class,
            "peak": peak_52w, "bottom": bottom_52w,
            "tp": price + (atr * 2), "sl": price - (atr * 1.5),
            "df": d15, "change": ((price - close_p) / close_p * 100)
        }
    except Exception as e:
        return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.2 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers())
    if st.button("Zapisz Listę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[60, 300, 600], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, tickers_list)) if r]

if data_list:
    st.subheader("🔥 TOP 10 - SYGNAŁY (RSI)")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    t_cols = st.columns(min(len(sorted_top), 5))
    for i, d in enumerate(sorted_top):
        with t_cols[i % 5]:
            st.markdown(f'''<div style="background:#161b22; padding:10px; border-radius:10px; border:1px solid #30363d; text-align:center; margin-bottom:10px;">
                <small>{d['symbol']}</small><br>
                <span class="verdict-badge {d['v_class']}">{d['verdict']}</span><br>
                <b>{d['price']:.2f}</b></div>''', unsafe_allow_html=True)

    for d in data_list:
        # Alert jeśli cena spadnie poniżej SL
        alert_class = "sl-alert" if d['price'] <= d['sl'] else ""
        st.markdown(f'<div class="ticker-card {alert_class}">', unsafe_allow_html=True)
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f'### {d["symbol"]} <span class="verdict-badge {d["v_class"]}">{d["verdict"]}</span>', unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            st.markdown(f"""
                <table class="metric-table">
                    <tr><td>PIVOT POINT (Orange)</td><td style="text-align:right; color:orange;">{d['pivot']:.2f}</td></tr>
                    <tr><td>SMA200 (Red)</td><td style="text-align:right; color:#ff4b4b;">{d['sma200']:.2f}</td></tr>
                    <tr><td>SZCZYT / DOŁEK (52w)</td><td style="text-align:right;">{d['peak']:.2f} / {d['bottom']:.2f}</td></tr>
                    <tr><td>RSI (14d)</td><td style="text-align:right;">{d['rsi']:.1f}</td></tr>
                    <tr style="color:#00ff88;"><td><b>TARGET (TP)</b></td><td style="text-align:right;"><b>{d['tp']:.2f}</b></td></tr>
                    <tr style="color:#ff4b4b;"><td><b>STOP LOSS (SL)</b></td><td style="text-align:right;"><b>{d['sl']:.2f}</b></td></tr>
                </table>
            """, unsafe_allow_html=True)

            if api_key and st.button(f"🧠 ANALIZA AI", key=f"ai_{d['symbol']}"):
                try:
                    client = OpenAI(api_key=api_key)
                    prompt = (f"Jesteś starszym traderem. Asset: {d['symbol']}. Cena: {d['price']}, SMA200: {d['sma200']:.2f}, "
                              f"Pivot: {d['pivot']:.2f}, RSI: {d['rsi']:.1f}. "
                              f"PODAJ KONKRET: 1. Werdykt, 2. Cena Wejścia, 3. Krótkie uzasadnienie.")
                    
                    resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                    st.session_state[f"res_{d['symbol']}"] = resp.choices[0].message.content
                except Exception as e:
                    st.error("Błąd API OpenAI. Sprawdź klucz.")
            
            if f"res_{d['symbol']}" in st.session_state:
                st.markdown(f'<div class="analysis-box"><b>ANALIZA PRO:</b><br>{st.session_state[f"res_{d['symbol']}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure()
            # Wyświetlamy ostatnie 100 świec dla czytelności
            df_plot = d['df'].tail(100)
            fig.add_trace(go.Candlestick(
                x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], 
                low=df_plot['Low'], close=df_plot['Close'], name="Cena"
            ))
            fig.add_hline(y=d['pivot'], line_color="orange", line_dash="dot", annotation_text="PIVOT")
            fig.add_hline(y=d['sma200'], line_color="red", line_dash="dash", annotation_text="SMA200")
            fig.update_layout(
                template="plotly_dark", height=400, 
                margin=dict(l=10, r=10, t=10, b=10), 
                xaxis_rangeslider_visible=False
            )
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Oczekiwanie na dane... Sprawdź symbole w Sidebarze.")
