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
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# --- 2. KONFIGURACJA I KOLORY ---
st.set_page_config(page_title="AI ALPHA KOMBAJN v23.0", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0f111a, #1a1c2b); 
        padding: 25px; border-radius: 15px; 
        border: 1px solid #30363d; margin-bottom: 30px;
    }
    .top-tile {
        background: #111420; padding: 12px; border-radius: 10px;
        border-bottom: 3px solid #00e5ff; text-align: center;
        min-height: 160px; margin-bottom: 10px;
    }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 8px 0; font-size: 0.9rem; }
    .signal-buy { color: #00ff88; font-weight: bold; text-transform: uppercase; }
    .signal-sell { color: #ff4b4b; font-weight: bold; text-transform: uppercase; }
    .signal-hold { color: #f1c40f; font-weight: bold; text-transform: uppercase; }
    .bid-ask { font-family: monospace; color: #00e5ff; font-weight: bold; font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="250d", interval="1d")
        
        if h1.empty or d1.empty: return None
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        
        price = h1['Close'].iloc[-1]
        bid, ask = price * 0.9999, price * 1.0001
        
        # Wskaźniki
        sma50 = d1['Close'].rolling(50).mean().iloc[-1]
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        delta = h1['Close'].diff()
        rsi = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        # --- LOGIKA KUP / TRZYMAJ / SPRZEDAJ ---
        if rsi < 32:
            verdict, v_class = "KUPUJ 🔥", "signal-buy"
        elif rsi > 68:
            verdict, v_class = "SPRZEDAJ ⚠️", "signal-sell"
        elif price > sma50:
            verdict, v_class = "TRZYMAJ 👍", "signal-hold"
        else:
            verdict, v_class = "CZEKAJ ⏳", ""

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "verdict": verdict, "v_class": v_class, "pp": pp,
            "sma50": sma50, "sma200": sma200,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.2),
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 ALPHA KOMBAJN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista została zapisana!")
    refresh = st.select_slider("Odświeżanie (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v23_sync")

# --- 5. WYŚWIETLANIE ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
all_data = [get_analysis(t) for t in tickers if get_analysis(t)]

if all_data:
    st.subheader("🏆 RANKING I REKOMENDACJE (TOP 10)")
    top_cols = st.columns(5)
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-tile">
                    <b style="color:#00e5ff;">{d['symbol']}</b><br>
                    <span style="font-size:1.1rem; font-weight:bold;">{d['price']:.2f}</span><br>
                    <div class="bid-ask">B: {d['bid']:.2f} | A: {d['ask']:.2f}</div>
                    <div class="{d['v_class']}" style="margin-top:10px; border:1px solid; border-radius:5px; padding:2px;">{d['verdict']}</div>
                    <small style="color:#888;">RSI: {d['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    for data in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            
            with c1:
                st.markdown(f"### {data['symbol']} <span class='{data['v_class']}' style='font-size:0.9rem;'>[{data['verdict']}]</span>", unsafe_allow_html=True)
                ch_col = "#00ff88" if data['change'] >= 0 else "#ff4b4b"
                st.markdown(f"<h2 style='color:{ch_col}; margin-bottom:0;'>{data['price']:.2f} <small style='font-size:0.9rem;'>({data['change']:.2f}%)</small></h2>", unsafe_allow_html=True)
                st.markdown(f"<div class='bid-ask'>BID: {data['bid']:.4f} | ASK: {data['ask']:.4f}</div>", unsafe_allow_html=True)
                
                st.markdown(f"""
                    <div style="margin-top:15px;">
                        <div class="metric-row"><span>RSI (1h)</span><b class="{data['v_class']}">{data['rsi']:.1f}</b></div>
                        <div class="metric-row"><span>Pivot Point</span><b style="color:#f1c40f;">{data['pp']:.4f}</b></div>
                        <div class="metric-row"><span>Cel TP</span><b style="color:#00ff88;">{data['tp']:.2f}</b></div>
                        <div class="metric-row"><span>Stop SL</span><b style="color:#ff4b4b;">{data['sl']:.2f}</b></div>
                    </div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-40:], open=data['df']['Open'][-40:], high=data['df']['High'][-40:], low=data['df']['Low'][-40:], close=data['df']['Close'][-40:])])
                fig.add_hline(y=data['pp'], line_dash="dot", line_color="#f1c40f")
                fig.update_layout(template="plotly_dark", height=320, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{data['symbol']}")

            with c3:
                st.markdown("🔍 **STATUS TRENDU**")
                st.write(f"Trend (SMA200): {'Wzrost 🚀' if data['price'] > data['sma200'] else 'Spadek 📉'}")
                st.write(f"Trend (SMA50): {'Wzrost 🚀' if data['price'] > data['sma50'] else 'Spadek 📉'}")
                
                if api_key and st.button(f"🧠 AI WERDYKT {data['symbol']}", key=f"ai_{data['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": f"Oceń {data['symbol']}. Cena: {data['price']}, Werdykt: {data['verdict']}, RSI: {data['rsi']:.1f}. Podaj 1 konkretny powód dlaczego tak."}]
                    )
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj symbole w panelu bocznym.")
