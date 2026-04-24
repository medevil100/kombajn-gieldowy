import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA UI ---
st.set_page_config(page_title="AI ALPHA GOLDEN v18.5 KOMBAJN", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; min-height: 180px; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; }
    .tp-target { color: #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 5px 10px; border-radius: 5px; background: rgba(0,255,136,0.1); }
    .sl-stop { color: #ff4b4b; font-weight: bold; border: 1px solid #ff4b4b; padding: 5px 10px; border-radius: 5px; background: rgba(255,75,75,0.1); }
    .pivot-val { color: #f1c40f; font-weight: bold; }
    .bid-val { color: #ff4b4b; font-weight: bold; }
    .ask-val { color: #00ff88; font-weight: bold; }
    .candle-alert { color: #f1c40f; font-weight: bold; font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK ANALIZY ŚWIEC ---
def analyze_candle_patterns(df):
    if len(df) < 5: return "Brak danych", 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Parametry świecy
    body = abs(last['Close'] - last['Open'])
    upper_wick = last['High'] - max(last['Open'], last['Close'])
    lower_wick = min(last['Open'], last['Close']) - last['Low']
    
    # 1. Młot (Hammer)
    if lower_wick > (2 * body) and upper_wick < (0.5 * body) and body > 0:
        pattern = "🔨 MŁOT (Wzrostowy)"
    # 2. Objęcie Hossy (Bullish Engulfing)
    elif last['Close'] > prev['Open'] and last['Open'] < prev['Close'] and prev['Close'] < prev['Open']:
        pattern = "🟢 OBJĘCIE HOSSY"
    # 3. Spadająca Gwiazda (Shooting Star)
    elif upper_wick > (2 * body) and lower_wick < (0.5 * body) and body > 0:
        pattern = "☄️ SPADAJĄCA GWIAZDA"
    else:
        pattern = "Brak formacji"

    # Statystyka ostatnich 10 świec
    last_10 = df.tail(10)
    bulls = len(last_10[last_10['Close'] > last_10['Open']])
    return pattern, bulls

# --- 3. SILNIK DANYCH ---
def get_kombajn_data(symbol):
    try:
        t = yf.Ticker(symbol)
        d_long = t.history(period="1y", interval="1d")
        d_short = t.history(period="5d", interval="15m")
        if d_long.empty or d_short.empty: return None

        price = d_short['Close'].iloc[-1]
        yest = d_long.iloc[-2]
        h_y, l_y, c_y = yest['High'], yest['Low'], yest['Close']
        
        # PIVOTY I SMA
        p = (h_y + l_y + c_y) / 3
        r1, s1 = (2 * p) - l_y, (2 * p) - h_y
        sma50 = d_long['Close'].rolling(50).mean().iloc[-1]
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        
        # RSI
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        # ANALIZA ŚWIEC
        pattern, bulls = analyze_candle_patterns(d_short)
        
        # WERDYKT
        if rsi < 32 and "🔨" in pattern: verdict = "KUP"
        elif rsi > 68: verdict = "SPRZEDAJ"
        elif price > sma50: verdict = "TRZYMAJ"
        else: verdict = "CZEKAJ"
        
        # BID / ASK
        info = t.info
        bid = info.get('bid', price * 0.999)
        ask = info.get('ask', price * 1.001

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "p": p, "r1": r1, "s1": s1, "sma50": sma50, "sma200": sma200, 
            "pattern": pattern, "bulls": bulls, "verdict": verdict,
            "tp": price * 1.05, "sl": price * 0.97,
            "change": ((price - c_y) / c_y) * 100, "df": d_short.tail(40)
        }
    except: return None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🍯 v18.5 KOMBAJN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole", "PKO.WA, ALE.WA, CDR.WA, NVDA, TSLA, BTC-USD, ETH-USD, AAPL, MSFT, META", height=150)
    refresh = st.slider("Odśwież (s)", 30, 300, 60)
st_autorefresh(interval=refresh * 1000, key="kombajn_sync")

# --- 5. RENDEROWANIE ---
symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in list(executor.map(get_kombajn_data, symbols)) if r]

if results:
    st.subheader("📊 DASHBOARD TOP 10")
    top_10 = results[:10]
    # Rząd 1
    c1 = st.columns(5)
    for i in range(min(5, len(top_10))):
        d = top_10[i]
        with c1[i]:
            st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b style="font-size:1.3rem;">{d["price"]:.2f}</b><br><span style="color:#00ff88; font-weight:bold;">{d["verdict"]}</span><br><div class="metric-row"><span class="bid-val">B:{d["bid"]:.2f}</span><span class="ask-val">A:{d["ask"]:.2f}</span></div><small>RSI: {d["rsi"]:.1f}</small></div>', unsafe_allow_html=True)
    # Rząd 2
    if len(top_10) > 5:
        c2 = st.columns(5)
        for i in range(5, len(top_10)):
            d = top_10[i]
            with c2[i-5]:
                st.markdown(f'<div class="top-tile"><small>{d["symbol"]}</small><br><b style="font-size:1.3rem;">{d["price"]:.2f}</b><br><span style="color:#00ff88; font-weight:bold;">{d["verdict"]}</span><br><div class="metric-row"><span class="bid-val">B:{d["bid"]:.2f}</span><span class="ask-val">A:{d["ask"]:.2f}</span></div><small>RSI: {d["rsi"]:.1f}</small></div>', unsafe_allow_html=True)

    for d in results:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1.8])
        with col1:
            st.markdown(f"## {d['symbol']} - {d['verdict']}")
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"""
                <div class="metric-row"><span>Analiza Świec</span><span class="candle-alert">{d['pattern']}</span></div>
                <div class="metric-row"><span>Ostatnie 10ś</span><b>{d['bulls']}/10 (Wzrost)</b></div>
                <div class="metric-row"><span>SMA 50 / 200</span><b>{d['sma50']:.1f} / {d['sma200']:.1f}</b></div>
                <div style="margin-top:20px; display:flex; gap:10px;"><span class="tp-target">TP: {d['tp']:.2f}</span> <span class="sl-stop">SL: {d['sl']:.2f}</span></div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown("### POZIOMY PIVOT")
            st.markdown(f"""
                <div class="metric-row"><span>Resistance 1</span><b>{d['r1']:.2f}</b></div>
                <div class="metric-row"><span>PIVOT POINT</span><b class="pivot-val">{d['p']:.2f}</b></div>
                <div class="metric-row"><span>Support 1</span><b>{d['s1']:.2f}</b></div>
            """, unsafe_allow_html=True)
            if api_key and st.button(f"🚀 AI DECYZJA", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Tylko komendy: KUP/SPRZEDAJ/TRZYMAJ, TP/SL, POWÓD."}, {"role": "user", "content": f"{d['symbol']} RSI:{d['rsi']:.1f}, Swieca:{d['pattern']}"}])
                st.success(res.choices[0].message.content) # POPRAWKA BŁĘDU
        with col3:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['p'], line_dash="dash", line_color="yellow", annotation_text="P")
            fig.update_layout(height=300, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
