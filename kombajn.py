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

st.set_page_config(page_title="AI ALPHA GOLDEN v28", page_icon="🚜", layout="wide")

# --- 2. STYLE NEONOWE ---
st.markdown("""
    <style>
    .stApp { background-color: #030303; color: #e0e0e0; }
    .ticker-card { 
        background: #0d1117; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px;
    }
    /* Neonowe kafelki TOP 10 */
    .top-tile-buy {
        background: #0d1117; padding: 15px; border-radius: 12px; border: 1px solid #00ff88;
        box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.3); text-align: center; min-height: 200px;
    }
    .top-tile-sell {
        background: #0d1117; padding: 15px; border-radius: 12px; border: 1px solid #ff4b4b;
        box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.3); text-align: center; min-height: 200px;
    }
    .top-tile-neutral {
        background: #0d1117; padding: 15px; border-radius: 12px; border: 1px solid #30363d;
        text-align: center; min-height: 200px;
    }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: 'Courier New', monospace; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: 'Courier New', monospace; }
    .sig-buy { color: #00ff88; text-shadow: 0 0 10px rgba(0,255,136,0.5); font-weight: bold; }
    .sig-sell { color: #ff4b4b; text-shadow: 0 0 10px rgba(255,75,75,0.5); font-weight: bold; }
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
        
        spread = ask - bid
        avg_vol = h1['Volume'].rolling(20).mean().iloc[-1]
        curr_vol = h1['Volume'].iloc[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0
        
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
            "rsi": rsi, "verd": verd, "vcl": vcl, "v_type": v_type,
            "y_high": d1['High'].max(), "y_low": d1['Low'].min(),
            "vol_ratio": vol_ratio, "df": h1
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🚜 GOLDEN v28")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh_v28")

# --- 5. PANEL GŁÓWNY ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as ex:
    all_data = [d for d in list(ex.map(get_analysis, tickers)) if d]

if all_data:
    st.subheader("🚀 NEON TOP 10")
    top_cols = st.columns(5)
    for i, d in enumerate(all_data[:10]):
        with top_cols[i % 5]:
            tile_class = f"top-tile-{d['v_type']}"
            st.markdown(f"""
                <div class="{tile_class}">
                    <b style="font-size:1.3rem;">{d['symbol']}</b><br>
                    <span style="color:#58a6ff; font-size:1.1rem;">{d['price']:.2f}</span><br>
                    <div style="margin: 10px 0;">
                        <span class="bid-box">B: {d['bid']:.2f}</span><br>
                        <span class="ask-box">A: {d['ask']:.2f}</span>
                    </div>
                    <div class="{d['vcl']}" style="font-size:1.1rem; border-top:1px solid #30363d; padding-top:5px;">{d['verd']}</div>
                    <small style="color:#8b949e;">RSI: {d['rsi']:.1f} | Spr: {d['spread']:.2f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1.2])
            with c1:
                st.markdown(f"<h2 class='{d['vcl']}'>{d['symbol']}</h2>", unsafe_allow_html=True)
                st.metric("CENA", f"{d['price']:.4f}")
                st.write(f"RSI: {d['rsi']:.1f}")
                st.write(f"Vol Ratio: **x{d['vol_ratio']:.2f}**")
            
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"c_{d['symbol']}")
            
            with c3:
                st.markdown(f"""
                    <div style="background: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d;">
                        <div style="color:#ff4b4b; font-size: 0.8rem;">BID (SPRZEDAJ)</div>
                        <div class="bid-box" style="font-size: 1.4rem;">{d['bid']:.4f}</div>
                        <div style="color:#00ff88; font-size: 0.8rem; margin-top:10px;">ASK (KUPUJ)</div>
                        <div class="ask-box" style="font-size: 1.4rem;">{d['ask']:.4f}</div>
                        <div style="border-top: 1px solid #30363d; margin-top: 10px; padding-top: 5px; color:#58a6ff;">
                            Spread: <b>{d['spread']:.4f}</b>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                if api_key and st.button(f"🧠 AI: {d['symbol']}", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    # Konkretny system prompt dla AI
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{
                            "role": "system", "content": "Jesteś agresywnym traderem. Mów krótko, tylko fakty. Format: WERDYKT, WEJŚCIE, CEL, STOP LOSS."
                        }, {
                            "role": "user", "content": f"Analiza: {d['symbol']}, Cena {d['price']}, RSI {d['rsi']:.1f}, Vol x{d['vol_ratio']:.2f}, Spread {d['spread']:.4f}. Dawaj konkrety."
                        }]
                    )
                    st.success(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
