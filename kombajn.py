import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. PAMIĘĆ LISTY ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read()
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# --- 2. KONFIGURACJA ---
st.set_page_config(page_title="AI ALPHA KOMBAJN v21.0", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 8px 0; font-size: 0.9rem; }
    .signal-buy { color: #00ff88; font-weight: bold; }
    .signal-sell { color: #ff4b4b; font-weight: bold; }
    .bid-ask { font-family: monospace; color: #58a6ff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="250d", interval="1d")
        
        if h1.empty or d1.empty: return None
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        
        price = h1['Close'].iloc[-1]
        
        # Wskaźniki SMA
        sma20 = d1['Close'].rolling(20).mean().iloc[-1]
        sma50 = d1['Close'].rolling(50).mean().iloc[-1]
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        
        # Pivot Points i ATR
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI 1h
        delta = h1['Close'].diff()
        rsi = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        # Werdykt
        if rsi < 32 and price > sma50: verdict = "KUP 🔥"
        elif rsi > 68: verdict = "SPRZEDAJ ⚠️"
        else: verdict = "CZEKAJ"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "verdict": verdict,
            "sma20": sma20, "sma50": sma50, "sma200": sma200, "pp": pp,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.2),
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. BOCZNY PANEL ---
with st.sidebar:
    st.title("🚜 KOMBAJN PRO v21.0")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    t_input = st.text_area("Twoja Lista:", value=load_tickers(), height=200)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana pomyślnie!")
    
    refresh = st.slider("Odświeżanie (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="auto_fsh")

# --- 5. WYŚWIETLANIE ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
for t in tickers:
    data = get_analysis(t)
    if data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.2, 2, 1.2])
            
            with c1:
                st.subheader(data['symbol'])
                st.metric("CENA", f"{data['price']:.2f}", f"{data['change']:.2f}%")
                st.markdown(f"<div class='bid-ask'>BID: {data['price']*0.9999:.2f} | ASK: {data['price']*1.0001:.2f}</div>", unsafe_allow_html=True)
                
                v_col = "signal-buy" if "KUP" in data['verdict'] else "signal-sell" if "SPRZEDAJ" in data['verdict'] else ""
                st.markdown(f"**SYGNAŁ:** <span class='{v_col}'>{data['verdict']}</span>", unsafe_allow_html=True)
                
                st.markdown(f"""
                    <div style="margin-top:10px;">
                        <div class="metric-row"><span>RSI (1h)</span><b>{data['rsi']:.1f}</b></div>
                        <div class="metric-row"><span>Pivot</span><b>{data['pp']:.2f}</b></div>
                        <div class="metric-row"><span>TP (Cel)</span><b style="color:#00ff88;">{data['tp']:.2f}</b></div>
                        <div class="metric-row"><span>SL (Stop)</span><b style="color:#ff4b4b;">{data['sl']:.2f}</b></div>
                    </div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-50:], open=data['df']['Open'][-50:], high=data['df']['High'][-50:], low=data['df']['Low'][-50:], close=data['df']['Close'][-50:])])
                fig.add_hline(y=data['sma20'], line_color="yellow", line_width=1, annotation_text="SMA20")
                fig.add_hline(y=data['sma50'], line_color="orange", line_width=1, annotation_text="SMA50")
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{data['symbol']}")

            with c3:
                st.write("**POZIOMY SMA**")
                st.write(f"SMA 20: {data['sma20']:.2f}")
                st.write(f"SMA 50: {data['sma50']:.2f}")
                st.write(f"SMA 200: {data['sma200']:.2f}")
                
                if api_key and st.button(f"🧠 ANALIZA AI {data['symbol']}", key=f"ai_{data['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": f"Analiza {data['symbol']}: Cena {data['price']}, RSI {data['rsi']:.1f}, Trend {data['verdict']}. Werdykt?"}]
                    )
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
