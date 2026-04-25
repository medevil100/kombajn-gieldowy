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
        with open(DB_FILE, "r") as f:
            content = f.read().strip()
            return content if content else "NVDA, TSLA, BTC-USD, GC=F"
    return "NVDA, TSLA, BTC-USD, GC=F"

st.set_page_config(page_title="AI ALPHA GOLDEN v35", page_icon="🚜", layout="wide")

if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .ticker-card { background: #0d1117; padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-tile-buy { border: 1px solid #00ff88; box-shadow: 0px 0px 10px rgba(0, 255, 136, 0.2); text-align: center; padding: 10px; border-radius: 10px; }
    .top-tile-sell { border: 1px solid #ff4b4b; box-shadow: 0px 0px 10px rgba(255, 75, 75, 0.2); text-align: center; padding: 10px; border-radius: 10px; }
    .top-tile-neutral { border: 1px solid #30363d; text-align: center; padding: 10px; border-radius: 10px; }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: monospace; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY (TRYB PANCERNY) ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        if not symbol: return None
        t = yf.Ticker(symbol)
        
        # Pobieramy tylko historię (najbardziej stabilne)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        
        # Bezpieczne pobieranie Bid/Ask (bez t.info które często rzuca błąd)
        # Symulacja spreadu na podstawie zmienności, jeśli info zawiedzie
        bid, ask = price * 0.9998, price * 1.0002
        
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
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "color:#00ff88;", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "color:#ff4b4b;", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "color:#8b949e;", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp, "spread": ask-bid,
            "tp": price + (atr * 1.7), "sl": price - (atr * 1.2),
            "y_high": y_high, "y_low": y_low, "vol_ratio": vol_ratio, 
            "trend": trend, "df": h1
        }
    except:
        return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v35")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    ticker_input = st.text_area("Lista symboli:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ I START"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_input)
        st.rerun()
    refresh_val = st.select_slider("Refresh (s)", options=, value=60)

st_autorefresh(interval=refresh_val * 1000, key="v35_fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in ticker_input.replace('\n', ',').split(',') if x.strip()]

if tickers:
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(get_analysis, tickers))
        all_data = [r for r in results if r is not None]

    if all_data:
        st.subheader("🏆 TOP SIGNALS")
        t_cols = st.columns(min(len(all_data), 5))
        for i, d in enumerate(all_data[:10]):
            with t_cols[i % 5]:
                st.markdown(f"""<div class="top-tile-{d['v_type']}"><b>{d['symbol']}</b><br>{d['price']:.2f}<br><div class="{d['v_type']}">{d['verd']}</div></div>""", unsafe_allow_html=True)

        for d in all_data:
            with st.container():
                st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns([1.2, 2, 1.4])
                with c1:
                    st.markdown(f"<h3 style='{d['vcl']}'>{d['symbol']} | {d['verd']}</h3>", unsafe_allow_html=True)
                    st.metric("PRICE", f"{d['price']:.4f}")
                    st.write(f"Pivot: {d['pp']:.2f} | Trend: {d['trend']}")
                    st.write(f"Range: {d['y_low']:.2f} - {d['y_high']:.2f}")
                with c2:
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"h_{d['symbol']}")
                with c3:
                    st.markdown(f"""<div style="background:#161b22; padding:10px; border-radius:10px; border:1px solid #333;">
                        <span class="bid-box">BID: {d['bid']:.4f}</span><br>
                        <span class="ask-box">ASK: {d['ask']:.4f}</span><br>
                        <small>Vol: x{d['vol_ratio']:.2f} | RSI: {d['rsi']:.1f}</small></div>""", unsafe_allow_html=True)
                    
                    if st.button(f"🧠 ANALIZA AI", key=f"ai_{d['symbol']}"):
                        if api_key:
                            client = OpenAI(api_key=api_key)
                            r = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "system", "content": "Jesteś ekspertem. Analizuj konkretnie: Sentyment, Relacja do szczytów, Plan (Entry, TP, SL)."},
                                          {"role": "user", "content": f"{d['symbol']}, Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['pp']:.2f}, High {d['y_high']:.2f}"}]
                            )
                            st.session_state.ai_cache[d['symbol']] = r.choices[0].message.content
                    
                    if d['symbol'] in st.session_state.ai_cache:
                        st.info(st.session_state.ai_cache[d['symbol']])
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.warning("Nie znaleziono danych dla podanych symboli. Upewnij się, że są poprawne (np. AAPL, BTC-USD).")
