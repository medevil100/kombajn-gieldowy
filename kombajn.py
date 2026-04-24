import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I PAMIĘĆ ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"
    return "PKO.WA, STX.WA, NVDA, TSLA, BTC-USD"

st.set_page_config(page_title="AI ALPHA UNIVERSAL FINAL", page_icon="🚜", layout="wide")

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
        text-align: center; min-height: 160px;
    }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; }
    .bid-ask { font-family: monospace; font-weight: bold; color: #58a6ff; font-size: 0.85rem; }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    .sig-hold { color: #f1c40f; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        # Pobieranie danych 1h i 1d
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="300d", interval="1d")
        
        if h1.empty or d1.empty: return None
        
        # FIX: Prostowanie MultiIndex
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        if isinstance(d1.columns, pd.MultiIndex): d1.columns = d1.columns.get_level_values(0)
        
        price = h1['Close'].iloc[-1]
        
        # Bid / Ask (Fallback)
        info = t.info
        bid = info.get('bid') or price * 0.9998
        ask = info.get('ask') or price * 1.0002
        
        # Średnie kroczące
        sma50 = d1['Close'].rolling(50).mean().iloc[-1]
        sma100 = d1['Close'].rolling(100).mean().iloc[-1]
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        
        # Pivot i ATR
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI 1h
        delta = h1['Close'].diff()
        rsi = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        # Logika Werdyktu
        if rsi < 32 and price > sma200: verdict, v_class = "KUPUJ 🔥", "sig-buy"
        elif rsi > 68: verdict, v_class = "SPRZEDAJ ⚠️", "sig-sell"
        elif price > sma50: verdict, v_class = "TRZYMAJ 👍", "sig-hold"
        else: verdict, v_class = "CZEKAJ ⏳", ""

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "pp": pp, "sma50": sma50, "sma100": sma100, "sma200": sma200,
            "verdict": verdict, "v_class": v_class, "tp": price + (atr * 1.6), "sl": price - (atr * 1.2),
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 UNIVERSAL FINAL")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Twoja Lista Spółek:", value=load_tickers(), height=150)
    
    if st.button("💾 ZAPISZ LISTĘ NA STAŁE"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana!")
    
    # POPRAWIONY SUWAK (Naprawia SyntaxError)
    refresh = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v239_sync")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    all_data = [d for d in list(executor.map(get_analysis, tickers)) if d is not None]

if all_data:
    # --- TOP 10 RANKING ---
    st.subheader("🏆 TOP SYGNAŁY (RSI 1H)")
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-tile">
                    <b>{d['symbol']}</b><br>
                    <span style="font-size:1.1rem; color:#00ff88;">{d['price']:.4f}</span><br>
                    <span class="bid-ask">B:{d['bid']:.2f} | A:{d['ask']:.2f}</span><br>
                    <div class="{d['v_class']}" style="margin-top:5px; font-size:0.8rem; border:1px solid; border-radius:4px; padding:2px;">{d['verdict']}</div>
                    <small style="color:#888;">RSI: {d['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            
            with c1:
                st.subheader(f"{d['symbol']} {d['verdict']}")
                st.markdown(f"## {d['price']:.4f} <small style='font-size:1rem; color:#00ff88;'>({d['change']:.2f}%)</small>", unsafe_allow_html=True)
                st.markdown(f"<div class='bid-ask'>BID: {d['bid']:.4f} | ASK: {d['ask']:.4f}</div>", unsafe_allow_html=True)
                st.markdown(f"""
                    <div style="margin-top:15px;">
                        <div class="metric-row"><span>RSI 1h</span><b class="{d['v_class']}">{d['rsi']:.1f}</b></div>
                        <div class="metric-row"><span>Pivot Point</span><b style="color:#f1c40f;">{d['pp']:.4f}</b></div>
                        <div class="metric-row"><span>SMA 50 / 100</span><b>{d['sma50']:.2f} / {d['sma100']:.2f}</b></div>
                        <div class="metric-row"><span>SMA 200</span><b>{d['sma200']:.2f}</b></div>
                    </div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.add_hline(y=d['pp'], line_dash="dot", line_color="orange")
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")

            with c3:
                st.markdown("🎯 **TARGETS**")
                st.write(f"🟢 TP: {d['tp']:.4f}")
                st.write(f"🔴 SL: {d['sl']:.4f}")
                if api_key and st.button(f"🧠 ANALIZA PRO", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    p = f"Analiza techniczna {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['pp']:.2f}. Podaj krótki werdykt."
                    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": p}])
                    # FIX: Poprawiony dostęp do zawartości
                    st.info(response.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Brak danych. Sprawdź listę symboli i upewnij się, że są oddzielone przecinkiem.")
