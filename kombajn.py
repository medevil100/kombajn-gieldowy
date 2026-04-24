import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. PAMIĘĆ LISTY ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, META, NFLX, AMD, BABA"
    return "AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, META, NFLX, AMD, BABA"

# --- 2. KONFIGURACJA ---
st.set_page_config(page_title="AI USA STABLE KOMBAJN", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .ticker-card { background: linear-gradient(145deg, #0f111a, #1a1c2b); padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 25px; }
    .top-tile { background: #111420; padding: 10px; border-radius: 8px; border-bottom: 3px solid #00e5ff; text-align: center; min-height: 150px; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.85rem; }
    .signal-buy { color: #00ff88; font-weight: bold; }
    .signal-sell { color: #ff4b4b; font-weight: bold; }
    .bid-ask { font-family: monospace; font-weight: bold; font-size: 0.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY (Zoptymalizowany pod USA) ---
def get_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        # Pobieramy dane zbiorczo (szybsze niż osobne wywołania)
        h1 = t.history(period="10d", interval="1h")
        if h1.empty: 
            return None
        
        # Pobieramy dane dzienne dla trendów i pivotów
        d1 = t.history(period="250d", interval="1d")
        if d1.empty: 
            return None

        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        
        price = h1['Close'].iloc[-1]
        
        # Stabilne Bid/Ask dla USA
        info = t.info
        bid = info.get('bid') or info.get('regularMarketPreviousClose') * 0.9999
        ask = info.get('ask') or info.get('regularMarketPreviousClose') * 1.0001
        
        sma50 = d1['Close'].rolling(50).mean().iloc[-1]
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        delta = h1['Close'].diff()
        rsi = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        if rsi < 33: verdict, v_class = "KUPUJ 🔥", "signal-buy"
        elif rsi > 67: verdict, v_class = "SPRZEDAJ ⚠️", "signal-sell"
        else: verdict, v_class = "CZEKAJ", ""

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "verdict": verdict, "v_class": v_class, "pp": pp, "sma50": sma50,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.2),
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except Exception:
        return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 KOMBAJN USA PRO")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole USA (po przecinku):", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana!")
    refresh = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="usa_sync")

# --- 5. LOGIKA GŁÓWNA (Wielowątkowość) ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]

# Pobieranie danych równolegle (ThreadPoolExecutor) - to klucz do stabilności
with ThreadPoolExecutor(max_workers=10) as executor:
    all_data_raw = list(executor.map(get_analysis, tickers))

all_data = [d for d in all_data_raw if d is not None]

if all_data:
    st.subheader(f"📊 MONITORING RYNKU ({len(all_data)} spółek aktywnych)")
    
    # TOP 10 Ranking
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-tile">
                    <b>{d['symbol']}</b><br>
                    <span style="font-size:1.1rem; color:#00ff88;">{d['price']:.2f}</span><br>
                    <span class="bid-ask" style="color:#ff4b4b;">B: {d['bid']:.2f}</span> | 
                    <span class="bid-ask" style="color:#00ff88;">A: {d['ask']:.2f}</span><br>
                    <div class="{d['v_class']}" style="font-size:0.75rem; margin-top:5px;">{d['verdict']}</div>
                    <small style="color:#888;">RSI: {d['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Detale
    for data in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.2, 2, 1])
            with c1:
                st.subheader(data['symbol'])
                st.markdown(f"## {data['price']:.2f}")
                st.markdown(f"<span class='bid-ask'>BID: {data['bid']:.4f} | ASK: {data['ask']:.4f}</span>", unsafe_allow_html=True)
                st.markdown(f"""
                    <div class="metric-row"><span>RSI (1h):</span><b class="{data['v_class']}">{data['rsi']:.1f}</b></div>
                    <div class="metric-row"><span>Pivot:</span><b>{data['pp']:.2f}</b></div>
                    <div class="metric-row"><span>Trend SMA50:</span><b>{'UP' if data['price']>data['sma50'] else 'DOWN'}</b></div>
                """, unsafe_allow_html=True)
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-40:], open=data['df']['Open'][-40:], high=data['df']['High'][-40:], low=data['df']['Low'][-40:], close=data['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{data['symbol']}")
            with c3:
                st.write(f"**TP:** {data['tp']:.2f}")
                st.write(f"**SL:** {data['sl']:.2f}")
                if api_key and st.button(f"🧠 AI", key=f"ai_{data['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user", "content":f"Oceń {data['symbol']} przy cenie {data['price']}"}])
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Oczekiwanie na dane z USA... Jeśli nic się nie pojawia, sprawdź czy symbole są poprawne.")
