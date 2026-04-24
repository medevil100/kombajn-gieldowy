import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA UI (FULL VERSION) ---
st.set_page_config(page_title="AI ALPHA GOLDEN v16.5", page_icon="🍯", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; margin-bottom: 10px; min-height: 160px; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .verdict-badge { padding: 3px 10px; border-radius: 15px; font-weight: bold; text-transform: uppercase; font-size: 0.7rem; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    .trend-up { color: #238636; font-weight: bold; }
    .trend-down { color: #da3633; font-weight: bold; }
    .candle-signal { color: #f1c40f; font-weight: bold; }
    .bid-ask-box { font-size: 0.75rem; background: #0d1117; padding: 5px; border-radius: 5px; margin-top: 8px; border: 1px solid #21262d; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ANALIZA ŚWIEC (FULL) ---
def analyze_candles(df):
    if len(df) < 3: return "Brak danych"
    last, prev = df.iloc[-1], df.iloc[-2]
    body = abs(last['Close'] - last['Open'])
    upper_wick = last['High'] - max(last['Open'], last['Close'])
    lower_wick = min(last['Open'], last['Close']) - last['Low']
    
    if lower_wick > (2 * body) and upper_wick < (0.5 * body) and body > 0: return "🔨 MŁOT"
    if last['Close'] > prev['Open'] and last['Open'] < prev['Close'] and prev['Close'] < prev['Open']: return "🟢 OBJĘCIE HOSSY"
    if last['Close'] < prev['Open'] and last['Open'] > prev['Close'] and prev['Close'] > prev['Open']: return "🔴 OBJĘCIE BESSY"
    if upper_wick > (2 * body) and lower_wick < (0.5 * body) and body > 0: return "☄️ GWIAZDA"
    return "Brak formacji"

# --- 3. SILNIK DANYCH ---
def get_data(symbol):
    try:
        t = yf.Ticker(symbol)
        d_long = t.history(period="1y", interval="1d")
        d15 = t.history(period="5d", interval="15m")
        if d15.empty or d_long.empty: return None

        price = d15['Close'].iloc[-1]
        # Pobieranie Bid/Ask z fallbackiem
        info = t.info
        bid = info.get('bid') or info.get('regularMarketPreviousClose') or price
        ask = info.get('ask') or info.get('regularMarketOpen') or price

        # RSI i Średnie
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        trend_val = "WZROSTOWY" if price > sma200 else "SPADKOWY"
        
        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "candle": analyze_candles(d15), "trend": trend_val,
            "verdict": "KUP" if rsi < 32 else "SPRZEDAJ" if rsi > 68 else "CZEKAJ",
            "v_class": "v-buy" if rsi < 32 else "v-sell" if rsi > 68 else "v-wait",
            "df": d15, "change": ((price - d_long['Close'].iloc[-2])/d_long['Close'].iloc[-2])*100
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.5 GOLDEN")
    api_key = st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole", "BTC-USD, ETH-USD, NVDA, TSLA, PKO.WA, ALE.WA, CDR.WA, AAPL, MSFT, META", height=150)
    refresh = st.slider("Odśwież (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="fsh_refresh")

# --- 5. LOGIKA GŁÓWNA ---
t_list = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    # --- TOP 10 (GWARANTOWANE 2 RZĘDY) ---
    st.subheader("🔥 TOP 10 SYGNAŁÓW (RSI + TREND + BID/ASK)")
    sorted_top = sorted(data_list, key=lambda x: abs(50 - x['rsi']), reverse=True)[:10]
    
    r1_cols = st.columns(5)
    for i in range(min(5, len(sorted_top))):
        d = sorted_top[i]
        with r1_cols[i]:
            t_col = "#238636" if d['trend'] == "WZROSTOWY" else "#da3633"
            st.markdown(f"""<div class="top-tile"><small>{d['symbol']}</small><br><b>{d['price']:.2f}</b><br><span class="verdict-badge {d['v_class']}">{d['verdict']}</span><br><span style="color:{t_col}; font-size:0.7rem; font-weight:bold;">{d['trend']}</span><div class="bid-ask-box"><span style="color:#da3633">B: {d['bid']:.2f}</span> | <span style="color:#238636">A: {d['ask']:.2f}</span></div></div>""", unsafe_allow_html=True)

    if len(sorted_top) > 5:
        r2_cols = st.columns(5)
        for i in range(5, len(sorted_top)):
            d = sorted_top[i]
            with r2_cols[i-5]:
                t_col = "#238636" if d['trend'] == "WZROSTOWY" else "#da3633"
                st.markdown(f"""<div class="top-tile"><small>{d['symbol']}</small><br><b>{d['price']:.2f}</b><br><span class="verdict-badge {d['v_class']}">{d['verdict']}</span><br><span style="color:{t_col}; font-size:0.7rem; font-weight:bold;">{d['trend']}</span><div class="bid-ask-box"><span style="color:#da3633">B: {d['bid']:.2f}</span> | <span style="color:#238636">A: {d['ask']:.2f}</span></div></div>""", unsafe_allow_html=True)

    # --- LISTA KART SZCZEGÓŁOWYCH ---
    for d in data_list:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"### {d['symbol']} <span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"""
                <div class="metric-row"><span>BID / ASK</span><b>{d['bid']:.2f} / {d['ask']:.2f}</b></div>
                <div class="metric-row"><span>Analiza Świec</span><span class="candle-signal">{d['candle']}</span></div>
                <div class="metric-row"><span>RSI (14d)</span><b>{d['rsi']:.1f}</b></div>
                <div class="metric-row"><span>Trend Długi</span><b class="{'trend-up' if d['trend']=='WZROSTOWY' else 'trend-down'}">{d['trend']}</b></div>
            """, unsafe_allow_html=True)
            
            if api_key and st.button(f"🚀 DECYZJA AI", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = f"Ticker: {d['symbol']}, Cena: {d['price']}, RSI: {d['rsi']:.1f}, Swieca: {d['candle']}. Podaj tylko: 1. DECYZJA, 2. TP/SL, 3. POWÓD (1 zdanie)."
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Jesteś suchym traderem."}, {"role": "user", "content": prompt}])
                st.info(res.choices[0].message.content) # Poprawione wybieranie treści
        with col2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(height=280, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.error("Błąd pobierania danych. Upewnij się, że symbole są poprawne (np. BTC-USD, NVDA, PKO.WA).")
