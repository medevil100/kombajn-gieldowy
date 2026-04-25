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
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "NVDA, TSLA, BTC-USD, GC=F"
        except: return "NVDA, TSLA, BTC-USD, GC=F"
    return "NVDA, TSLA, BTC-USD, GC=F"

st.set_page_config(page_title="AI ALPHA GOLDEN v37 FINAL", page_icon="🚜", layout="wide")

if 'ai_cache' not in st.session_state: st.session_state.ai_cache = {}
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 10000.0

# --- 2. STYLE WIZUALNE (NEON & GLOW) ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .ticker-card { background: #0d1117; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px; }
    .top-tile-buy { border: 1px solid #00ff88; box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.2); text-align: center; padding: 15px; border-radius: 12px; min-height: 200px; }
    .top-tile-sell { border: 1px solid #ff4b4b; box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.2); text-align: center; padding: 15px; border-radius: 12px; min-height: 200px; }
    .top-tile-neutral { border: 1px solid #30363d; text-align: center; padding: 15px; border-radius: 12px; min-height: 200px; }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: monospace; font-size: 1.3rem; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: monospace; font-size: 1.3rem; }
    .sig-buy { color: #00ff88; font-weight: bold; text-shadow: 0 0 10px rgba(0,255,136,0.5); }
    .sig-sell { color: #ff4b4b; font-weight: bold; text-shadow: 0 0 10px rgba(255,75,75,0.5); }
    .news-box { font-size: 0.8rem; color: #8b949e; background: #050505; padding: 10px; border-radius: 8px; margin-top: 8px; border-left: 3px solid #58a6ff; }
    .stat-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        if not symbol: return None
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        try:
            bid = t.info.get('bid') or price * 0.9997
            ask = t.info.get('ask') or price * 1.0003
        except: bid, ask = price * 0.9997, price * 1.0003
        
        # News
        news_list = [n.get('title') for n in t.news[:3]] if t.news else []
        
        # Wskaźniki
        y_high, y_low = d1['High'].max(), d1['Low'].min()
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI
        delta = h1['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        vol_ratio = h1['Volume'].iloc[-1] / (h1['Volume'].rolling(20).mean().iloc[-1] + 1)
        
        trend = "BULL 📈" if price > sma200 else "BEAR 📉"
        
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp, "spread": ask-bid,
            "tp": price + (atr * 1.8), "sl": price - (atr * 1.3),
            "y_high": y_high, "y_low": y_low, "vol_ratio": vol_ratio, 
            "trend": trend, "news": news_list, "df": h1
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🚜 GOLDEN v37")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    st.subheader("💰 Risk Management")
    st.session_state.risk_cap = st.number_input("Kapitał ($)", value=st.session_state.risk_cap)
    risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, 1.0)
    
    ticker_input = st.text_area("Lista:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ I START"):
        with open(DB_FILE, "w") as f: f.write(ticker_input)
        st.rerun()
    refresh_val = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh_val * 1000, key="v37_refresh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in ticker_input.replace('\n', ',').split(',') if x.strip()]
with ThreadPoolExecutor(max_workers=10) as ex:
    all_data = [d for d in list(ex.map(get_analysis, tickers)) if d]

if all_data:
    st.subheader("🏆 TOP SIGNALS (Neon Glow)")
    t_cols = st.columns(5)
    for i, d in enumerate(all_data[:10]):
        with t_cols[i % 5]:
            st.markdown(f'<div class="top-tile-{d["v_type"]}"><b>{d["symbol"]}</b><br><span style="color:#58a6ff; font-size:1.1rem;">{d["price"]:.2f}</span><br><div class="bid-box" style="font-size:0.9rem;">B: {d["bid"]:.2f}</div><div class="ask-box" style="font-size:0.9rem;">A: {d["ask"]:.2f}</div><div class="{d["vcl"]}">{d["verd"]}</div></div>', unsafe_allow_html=True)

    st.divider()

    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.4])
            
            with c1:
                st.markdown(f"<h2 class='{d['vcl']}'>{d['symbol']} | {d['verd']}</h2>", unsafe_allow_html=True)
                st.metric("PRICE", f"{d['price']:.4f}")
                
                # KALKULATOR
                risk_val = st.session_state.risk_cap * (risk_pct / 100)
                sl_dist = abs(d['price'] - d['sl'])
                pos_size = int(risk_val / sl_dist) if sl_dist > 0 else 0
                
                st.markdown(f"""
                    <div style="background:#161b22; padding:10px; border-radius:8px; border:1px solid #f1e05a22;">
                        <span style="color:#f1e05a;">Wielkość pozycji: <b>{pos_size} szt.</b></span><br>
                        <small>Ryzykujesz: ${risk_val:.2f} | Przy SL: {d['sl']:.2f}</small>
                    </div>
                    <div style="margin-top:10px;">
                        <div class="stat-row"><span>Pivot:</span><b>{d['pp']:.2f}</b></div>
                        <div class="stat-row"><span>Trend:</span><b>{d['trend']}</b></div>
                        <div class="stat-row"><span style="color:#00ff88;">TP:</span><b>{d['tp']:.2f}</b></div>
                        <div class="stat-row"><span style="color:#ff4b4b;">SL:</span><b>{d['sl']:.2f}</b></div>
                    </div>
                """, unsafe_allow_html=True)
                
                if d['news']:
                    st.write("📰 Newsy:")
                    for n in d['news']: st.markdown(f"<div class='news-box'>{n}</div>", unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-45:], open=d['df']['Open'][-45:], high=d['df']['High'][-45:], low=d['df']['Low'][-45:], close=d['df']['Close'][-45:])])
                fig.update_layout(template="plotly_dark", height=320, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"p_{d['symbol']}")

            with c3:
                st.markdown(f'<div style="background:#000; padding:15px; border-radius:12px; border:1px solid #333;"><div style="color:#ff4b4b; font-size:0.8rem;">BID</div><div class="bid-box">{d["bid"]:.4f}</div><div style="color:#00ff88; font-size:0.8rem; margin-top:10px;">ASK</div><div class="ask-box">{d["ask"]:.4f}</div><div style="border-top:1px solid #222; margin-top:12px; padding-top:8px;"><small>Spread: {d["spread"]:.4f} | Vol: x{d["vol_ratio"]:.2f}</small></div></div>', unsafe_allow_html=True)
                
                if st.button(f"🧠 ANALIZA AI + NEWS", key=f"ai_{d['symbol']}"):
                    if api_key:
                        client = OpenAI(api_key=api_key)
                        prompt = f"Analiza {d['symbol']}. Cena {d['price']}, RSI {d['rsi']:.1f}, Trend {d['trend']}. News: {'. '.join(d['news'])}. Podaj diagnozę i plan Trade (Entry, TP, SL)."
                        r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "Jesteś traderem. Analizuj technikę i newsy. Konkretnie."}, {"role": "user", "content": prompt}])
                        st.session_state.ai_cache[d['symbol']] = r.choices[0].message.content
                
                if d['symbol'] in st.session_state.ai_cache:
                    st.info(st.session_state.ai_cache[d['symbol']])
            st.markdown('</div>', unsafe_allow_html=True)

st.caption("AI Alpha Golden v37 | News Scanner | Position Sizing | Full Engine")
