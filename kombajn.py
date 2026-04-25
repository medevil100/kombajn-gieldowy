import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "NVDA, TSLA, BTC-USD, PKO.WA"
    return "NVDA, TSLA, BTC-USD, PKO.WA"

st.set_page_config(page_title="AI ALPHA GOLDEN v29", page_icon="🚜", layout="wide")

# Inicjalizacja pamięci dla AI (żeby nie znikało i nie kosztowało przy każdym refreshu)
if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. STYLE NEONOWE ---
st.markdown("""
    <style>
    .stApp { background-color: #030303; color: #e0e0e0; }
    .ticker-card { background: #0d1117; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px; }
    .top-tile-buy { background: #0d1117; padding: 15px; border-radius: 12px; border: 1px solid #00ff88; box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.3); text-align: center; min-height: 210px; }
    .top-tile-sell { background: #0d1117; padding: 15px; border-radius: 12px; border: 1px solid #ff4b4b; box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.3); text-align: center; min-height: 210px; }
    .top-tile-neutral { background: #0d1117; padding: 15px; border-radius: 12px; border: 1px solid #30363d; text-align: center; min-height: 210px; }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: monospace; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: monospace; }
    .sig-buy { color: #00ff88; text-shadow: 0 0 10px rgba(0,255,136,0.5); font-weight: bold; }
    .sig-sell { color: #ff4b4b; text-shadow: 0 0 10px rgba(255,75,75,0.5); font-weight: bold; }
    .pivot-val { color: #58a6ff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ANALIZA ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty: return None
        
        price = h1['Close'].iloc[-1]
        try:
            bid = t.info.get('bid') or price * 0.9995
            ask = t.info.get('ask') or price * 1.0005
        except: bid, ask = price * 0.9995, price * 1.0005
        
        # PIVOT & ATR (ST/TP)
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        spread = ask - bid
        vol_ratio = h1['Volume'].iloc[-1] / h1['Volume'].rolling(20).mean().iloc[-1]
        
        # RSI
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "spread": spread,
            "rsi": rsi, "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.2),
            "vol_ratio": vol_ratio, "df": h1
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🚜 GOLDEN v29")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh_v29")

# --- 5. LOGIKA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as ex:
    all_data = [d for d in list(ex.map(get_analysis, tickers)) if d]

if all_data:
    # TOP 10 NEON
    st.subheader("🚀 NEON SIGNALS")
    cols = st.columns(5)
    for i, d in enumerate(all_data[:10]):
        with cols[i % 5]:
            st.markdown(f'<div class="top-tile-{d["v_type"]}"><b>{d["symbol"]}</b><br><span style="font-size:1.2rem;">{d["price"]:.2f}</span><br><div class="bid-box">B: {d["bid"]:.2f}</div><div class="ask-box">A: {d["ask"]:.2f}</div><div class="{d["vcl"]}">{d["verd"]}</div><small>RSI: {d["rsi"]:.1f}</small></div>', unsafe_allow_html=True)

    st.divider()

    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.2, 2, 1.3])
            
            with c1:
                st.markdown(f"<h2 class='{d['vcl']}'>{d['symbol']} {d['verd']}</h2>", unsafe_allow_html=True)
                st.metric("CENA", f"{d['price']:.4f}")
                st.markdown(f"""
                    Pivot: <span class="pivot-val">{d['pp']:.2f}</span><br>
                    <span style="color:#00ff88;">TP: {d['tp']:.2f}</span><br>
                    <span style="color:#ff4b4b;">SL: {d['sl']:.2f}</span><br>
                    RSI: <b>{d['rsi']:.1f}</b> | Vol: <b>x{d['vol_ratio']:.2f}</b>
                """, unsafe_allow_html=True)
            
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"c_{d['symbol']}")
            
            with c3:
                st.markdown(f"""
                    <div style="background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d; margin-bottom:10px;">
                        <div style="color:#ff4b4b; font-size: 0.8rem;">BID</div><div class="bid-box" style="font-size: 1.3rem;">{d['bid']:.4f}</div>
                        <div style="color:#00ff88; font-size: 0.8rem; margin-top:5px;">ASK</div><div class="ask-box" style="font-size: 1.3rem;">{d['ask']:.4f}</div>
                        <div style="border-top: 1px solid #30363d; margin-top: 8px; color:#58a6ff;">Spr: <b>{d['spread']:.4f}</b></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Przycisk AI z pamięcią (Cache)
                if st.button(f"🧠 ANALIZA AI", key=f"btn_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Krótko: WERDYKT, WEJŚCIE, TP, SL. Bez lania wody."},
                                  {"role": "user", "content": f"{d['symbol']}, Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['pp']:.2f}"}]
                    )
                    st.session_state.ai_cache[d['symbol']] = res.choices[0].message.content
                
                # Wyświetl z cache jeśli istnieje
                if d['symbol'] in st.session_state.ai_cache:
                    st.info(st.session_state.ai_cache[d['symbol']])
            st.markdown('</div>', unsafe_allow_html=True)

# Stopka dla oszczędności
st.caption("AI Alpha Golden v29 | Dane odświeżane automatycznie | Cache AI aktywny")
