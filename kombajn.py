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
        except: return "NVDA, TSLA, BTC-USD, PKO.WA"
    return "NVDA, TSLA, BTC-USD, PKO.WA"

st.set_page_config(page_title="AI ALPHA UNIVERSAL v24.1", page_icon="🚜", layout="wide")

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
    .v-power { color: #f1c40f; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    symbol = symbol.strip().upper()
    if not symbol: return None
    try:
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="300d", interval="1d")
        
        if h1.empty or d1.empty: return None
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        
        price = h1['Close'].iloc[-1]
        
        # Wolumen i Bid/Ask
        avg_vol = h1['Volume'].tail(20).mean()
        vol_p = "WYSOKI 🔥" if h1['Volume'].iloc[-1] > avg_vol * 1.5 else "NORMAL"
        info = t.info
        bid = info.get('bid') or price * 0.9998
        ask = info.get('ask') or price * 1.0002
        
        # Średnie
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
        
        # Werdykt
        if rsi < 33: verd, vcl = "KUPUJ 🔥", "sig-buy"
        elif rsi > 67: verd, vcl = "SPRZEDAJ ⚠️", "sig-sell"
        else: verd, vcl = "TRZYMAJ 👍" if price > sma50 else "CZEKAJ ⏳", ""

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "pp": pp, "sma50": sma50, "sma100": sma100, "sma200": sma200, "vol": vol_p,
            "verdict": verd, "vcl": vcl, "tp": price + (atr * 1.6), "sl": price - (atr * 1.2),
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 ULTIMATE v24.1")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    raw_input = st.text_area("Lista Symboli (oddziel przecinkiem):", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(raw_input)
        st.success("Lista zapisana!")
    refresh = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v241_sync")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [s.strip().upper() for s in raw_input.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    all_data = [d for d in list(executor.map(get_analysis, tickers)) if d is not None]

if all_data:
    # TOP 10
    st.subheader("🏆 TOP SYGNAŁY (Wyprzedane RSI)")
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""<div class="top-tile"><b>{d['symbol']}</b><br><span style="font-size:1.1rem; color:#00ff88;">{d['price']:.2f}</span><br><div class="{d['vcl']}">{d['verdict']}</div><small>RSI: {d['rsi']:.1f}</small></div>""", unsafe_allow_html=True)

    st.divider()

    # DETALE
    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            with c1:
                st.subheader(f"{d['symbol']} {d['verdict']}")
                st.metric("CENA", f"{d['price']:.4f}", f"{d['change']:.2f}%")
                st.markdown(f"<div class='bid-ask'>BID: {d['bid']:.4f} | ASK: {d['ask']:.4f}</div>", unsafe_allow_html=True)
                st.markdown(f"""<div style="margin-top:15px;"><div class="metric-row"><span>RSI 1h</span><b class="{d['vcl']}">{d['rsi']:.1f}</b></div><div class="metric-row"><span>Pivot Point</span><b style="color:#f1c40f;">{d['pp']:.4f}</b></div><div class="metric-row"><span>V-Power</span><b class="v-power">{d['vol']}</b></div></div>""", unsafe_allow_html=True)
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.add_hline(y=d['pp'], line_dash="dot", line_color="orange")
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")
            with c3:
                st.write(f"🟢 TP: **{d['tp']:.4f}**")
                st.write(f"🔴 SL: **{d['sl']:.4f}**")
                if api_key and st.button(f"🧠 ANALIZA AI", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": f"Werdykt dla {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, SMA200 {d['sma200']:.2f}. Podaj krótki argument."}])
                    st.success(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Brak danych. Sprawdź czy symbole są poprawne i oddzielone przecinkami (np. AAPL, NVDA, BTC-USD).")
