import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v11", page_icon="🏦", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return f.read()
    return "PKO.WA, BTC-USD, NVDA, TSLA, ALE.WA"

# --- STYLE GITHUB DARK PRO ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .buy-signal { border: 2px solid #238636 !important; box-shadow: 0 0 15px rgba(35, 134, 54, 0.3); }
    .top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; min-width: 150px; }
    .stat-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; }
    .stat-value { font-family: 'Courier New', monospace; font-weight: bold; color: #58a6ff; }
    .verdict-kup { color: #39d353; font-weight: bold; }
    .verdict-sprz { color: #f85149; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- SILNIK ANALITYCZNY ---
def get_analysis(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        if d15.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        
        # Wskaźniki Techniczne
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        # RSI
        delta = d15['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Poziomy: Pivot, TP, SL
        pivot = (d1d['High'].iloc[-2] + d1d['Low'].iloc[-2] + d1d['Close'].iloc[-2]) / 3
        tp = price + (atr * 1.5)
        sl = price - (atr * 1.2)
        
        # Logika Rekomendacji
        if rsi < 32: rec, color = "KUPUJ", "#238636"
        elif rsi > 68: rec, color = "SPRZEDAJ", "#da3633"
        else: rec, color = "CZEKAJ", "#8b949e"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "rec": rec, "color": color,
            "pivot": pivot, "tp": tp, "sl": sl, "df": d15, "trend": "UP" if price > sma200 else "DOWN"
        }
    except: return None

# --- UI ---
with st.sidebar:
    st.title("⚙️ KOMB_v11")
    api_key = st.text_input("OpenAI Key", type="password")
    tickers_input = st.text_area("Lista symboli", value=load_tickers())
    if st.button("Zapisz"): 
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="refresh")
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if api_key:
    client = OpenAI(api_key=api_key)
    data_list = [get_analysis(t) for t in tickers if get_analysis(t)]

    # --- TOP 10 DASHBOARD ---
    st.subheader("📊 RANKING SYGNAŁÓW")
    top_cols = st.columns(5)
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]
    
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-rank-card">
                    <b style="font-size:1.1rem;">{d['symbol']}</b><br>
                    <span class="price-tag" style="color:{d['color']}">{d['rec']}</span><br>
                    <span class="stat-label">Cena:</span> <span class="stat-value">{d['price']:.2f}</span><br>
                    <span class="stat-label">Pivot:</span> <span class="stat-value" style="color:white">{d['pivot']:.2f}</span><br>
                    <span class="stat-label">RSI:</span> <span style="color:#58a6ff">{d['rsi']:.1f}</span>
                </div>
            """, unsafe_allow_html=True)

    # --- KARTY ANALITYCZNE ---
    for d in data_list:
        st.markdown(f'<div class="ticker-card {"buy-signal" if d["rec"]=="KUPUJ" else ""}">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown(f"### {d['symbol']}")
            st.markdown(f"**STATUS: <span style='color:{d['color']}'>{d['rec']}</span>**", unsafe_allow_html=True)
            
            col_a, col_b = st.columns(2)
            col_a.metric("PIVOT", f"{d['pivot']:.2f}")
            col_a.metric("TP (CEL)", f"{d['tp']:.2f}", delta=f"{(d['tp']-d['price'])/d['price']*100:.1f}%")
            col_b.metric("RSI", f"{d['rsi']:.1f}")
            col_b.metric("SL (STOP)", f"{d['sl']:.2f}", delta=f"{(d['sl']-d['price'])/d['price']*100:.1f}%", delta_color="inverse")

            if st.button(f"🧠 EKSPERTYZA AI: {d['symbol']}", key=f"ai_{d['symbol']}"):
                prompt = (f"Jesteś agresywnym analitykiem giełdowym. Symbol: {d['symbol']}. "
                          f"Cena: {d['price']}, RSI: {d['rsi']:.1f}, Pivot: {d['pivot']:.2f}, TP: {d['tp']:.2f}, SL: {d['sl']:.2f}. "
                          f"Trend długoterminowy: {d['trend']}. "
                          f"WYMÓG: Podaj krótki, konkretny werdykt. Dlaczego KUPUJ/SPRZEDAJ? "
                          f"Jakie jest ryzyko w skali 1-10? Nie owijaj w bawełnę.")
                
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"msg_{d['symbol']}"] = resp.choices[0].message.content
            
            if f"msg_{d['symbol']}" in st.session_state:
                st.info(st.session_state[f"msg_{d['symbol']}"])

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-60:], open=d['df']['Open'][-60:], high=d['df']['High'][-60:], low=d['df']['Low'][-60:], close=d['df']['Close'][-60:])])
            # Linie poziomów
            fig.add_hline(y=d['pivot'], line_dash="dot", line_color="white", annotation_text="PIVOT")
            fig.add_hline(y=d['tp'], line_dash="dash", line_color="#00ff88", annotation_text="TP")
            fig.add_hline(y=d['sl'], line_dash="dash", line_color="#ff4b4b", annotation_text="SL")
            
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Podaj OpenAI API Key, aby aktywować Superkombajn.")
