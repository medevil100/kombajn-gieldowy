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
        except: return "NVDA, TSLA, BTC-USD, GC=F"
    return "NVDA, TSLA, BTC-USD, GC=F"

st.set_page_config(page_title="AI ALPHA GOLDEN v31", page_icon="🚜", layout="wide")

if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. STYLE WIZUALNE ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .ticker-card { background: #0d1117; padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-tile-buy { border: 1px solid #00ff88; box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.25); text-align: center; padding: 15px; border-radius: 12px; }
    .top-tile-sell { border: 1px solid #ff4b4b; box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.25); text-align: center; padding: 15px; border-radius: 12px; }
    .top-tile-neutral { border: 1px solid #30363d; text-align: center; padding: 15px; border-radius: 12px; }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: monospace; font-size: 1.1rem; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: monospace; font-size: 1.1rem; }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    .trend-up { color: #00ff88; font-size: 0.8rem; }
    .trend-down { color: #ff4b4b; font-size: 0.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        bid = t.info.get('bid') or price * 0.9998
        ask = t.info.get('ask') or price * 1.0002
        
        # Matematyka: Pivot, ATR, Trend
        y_high, y_low = d1['High'].max(), d1['Low'].min()
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI & Volume
        delta = h1['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        vol_ratio = h1['Volume'].iloc[-1] / h1['Volume'].rolling(20).mean().iloc[-1]
        
        # Trend D1
        trend_status = "BULL" if price > sma200 else "BEAR"
        
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp, "spread": ask-bid,
            "tp": price + (atr * 1.8), "sl": price - (atr * 1.3),
            "y_high": y_high, "y_low": y_low, "vol_ratio": vol_ratio, 
            "trend": trend_status, "sma200": sma200, "df": h1
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v31")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
    refresh = st.select_slider("Auto-refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v31_fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as ex:
    all_data = [d for d in list(ex.map(get_analysis, tickers)) if d]

if all_data:
    st.subheader("🏆 TOP 10 SIGNALS (Glow Mode)")
    cols = st.columns(5)
    for i, d in enumerate(all_data[:10]):
        with cols[i % 5]:
            trend_icon = "📈" if d['trend'] == "BULL" else "📉"
            st.markdown(f"""
                <div class="top-tile-{d['v_type']}">
                    <b>{d['symbol']} {trend_icon}</b><br>
                    <span style="font-size:1.2rem; color:#58a6ff;">{d['price']:.2f}</span><br>
                    <div class="bid-box">B: {d['bid']:.2f}</div>
                    <div class="ask-box">A: {d['ask']:.2f}</div>
                    <div class="{d['vcl']}" style="margin-top:5px;">{d['verd']}</div>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.2, 2, 1.4])
            
            with c1:
                st.markdown(f"<h3 class='{d['vcl']}'>{d['symbol']} | {d['verd']}</h3>", unsafe_allow_html=True)
                st.metric("CENA", f"{d['price']:.4f}")
                st.markdown(f"""
                    <div style="font-size:0.9rem; line-height:1.5; background: #161b22; padding: 10px; border-radius: 8px;">
                    🔵 Pivot: <b>{d['pp']:.2f}</b><br>
                    🟢 TP: <b>{d['tp']:.2f}</b><br>
                    🔴 SL: <b>{d['sl']:.2f}</b><br>
                    📏 Range 12m: {d['y_low']:.2f} - {d['y_high']:.2f}<br>
                    📊 Trend D1: <b class="{'trend-up' if d['trend'] == 'BULL' else 'trend-down'}">{d['trend']}</b>
                    </div>
                """, unsafe_allow_html=True)
            
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")
            
            with c3:
                st.markdown(f"""
                    <div style="background: #000; padding: 10px; border-radius: 8px; border: 1px solid #30363d;">
                        <span style="color:#ff4b4b; font-size:0.75rem;">BID</span><br><span class="bid-box">{d['bid']:.4f}</span><br>
                        <span style="color:#00ff88; font-size:0.75rem; margin-top:5px; display:block;">ASK</span><span class="ask-box">{d['ask']:.4f}</span><br>
                        <div style="border-top:1px solid #222; margin-top:10px; padding-top:5px;">
                            <small style="color:#58a6ff;">Spread: {d['spread']:.4f}</small><br>
                            <small style="color:#f1e05a;">Vol Ratio: x{d['vol_ratio']:.2f}</small>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"🧠 ANALIZA PRO AI", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = (f"Jako PRO trader przeanalizuj {d['symbol']}. Cena: {d['price']}. "
                              f"Technicznie: RSI {d['rsi']:.1f}, Wolumen x{d['vol_ratio']:.2f}, Trend D1 {d['trend']}. "
                              f"Poziomy: Pivot {d['pp']:.2f}, Szczyt {d['y_high']:.2f}, Dołek {d['y_low']:.2f}. "
                              f"Podaj: 1. Diagnozę (czy to okazja?), 2. Relację ceny do ekstremów, 3. Dokładny plan Trade (Entry, TP, SL).")
                    
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Jesteś ekspertem analizy technicznej. Używasz tylko faktów i liczb. Nie lejesz wody. Formatuj w punktach."},
                                  {"role": "user", "content": prompt}]
                    )
                    st.session_state.ai_cache[d['symbol']] = res.choices[0].message.content
                
                if d['symbol'] in st.session_state.ai_cache:
                    st.markdown(f"""<div style="font-size:0.85rem; color:#d1d5db; margin-top:10px; padding:12px; background:#111; border-left:4px solid #00ff88; border-radius: 4px;">
                        {st.session_state.ai_cache[d['symbol']]}
                    </div>""", unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

st.caption("AI Alpha Golden v31 | SMA200 Trend Engine | Hybrid Analysis")
