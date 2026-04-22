import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. PAMIĘĆ SPÓŁEK ---
DB_FILE = "moje.txt" # Ustawione na Twoją nazwę pliku

def save_tickers(text):
    with open(DB_FILE, "w") as f:
        f.write(text)

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, IOVA"
    return "PKO.WA, BTC-USD, NVDA, IOVA"

# --- 2. KONFIGURACJA ---
st.set_page_config(page_title="AI Alpha Kombajn v9 GOLD", page_icon="💰", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; }
    .ticker-card { background: #0a0b10; padding: 25px; border-radius: 15px; border: 1px solid #1a1c23; margin-bottom: 25px; border-right: 5px solid #333; }
    .buy-signal { border: 2px solid #00ff88 !important; box-shadow: 0 0 20px rgba(0, 255, 136, 0.2); }
    .verdict-box { background: #07121d; padding: 15px; border-radius: 10px; border-left: 5px solid #00e5ff; margin-top: 10px; }
    .tf-badge { background: #1a1a1a; padding: 4px 8px; border-radius: 6px; font-size: 0.75rem; color: #00e5ff; border: 1px solid #333; margin-right: 5px; }
    .vol-spike { color: #ff00ff; font-weight: bold; font-size: 0.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIKA DANYCH ---
def play_sound():
    st.components.v1.html('<audio autoplay><source src="https://mixkit.co" type="audio/mpeg"></audio>', height=0)

def get_data(symbol):
    try:
        d15 = yf.download(symbol, period="3d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="200d", interval="1d", progress=False)
        if d15.empty or d1d.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        
        # --- WSTĘGI BOLLINGERA ---
        sma20 = d15['Close'].rolling(20).mean()
        std20 = d15['Close'].rolling(20).std()
        upper_bb = sma20 + (std20 * 2)
        lower_bb = sma20 - (std20 * 2)

        # --- WOLUMEN ---
        avg_vol = d15['Volume'].rolling(20).mean().iloc[-1]
        curr_vol = d15['Volume'].iloc[-1]
        vol_spike = curr_vol > (avg_vol * 1.5) # Skok o 50%

        # --- RSI ---
        delta = d15['Close'].diff()
        rsi = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))).iloc[-1]
        
        # --- PIVOT I TRENDY ---
        sma_d = d1d['Close'].rolling(100).mean().iloc[-1]
        prev = d1d.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "pivot": pivot,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.0),
            "trend": "BULL 🐂" if price > sma_d else "BEAR 🐻",
            "vol_spike": vol_spike, "df": d15, "lbb": lower_bb.iloc[-1], "ubb": upper_bb.iloc[-1],
            "sma20": sma20, "lower_bb": lower_bb, "upper_bb": upper_bb
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.header("⚙️ PRO SETTINGS")
    api_key = st.text_input("OpenAI API Key:", type="password")
    saved_list = load_tickers()
    tickers_input = st.text_area("Lista Spółek:", value=saved_list, height=200)
    if tickers_input != saved_list: save_tickers(tickers_input)
    tickers = [x.strip().upper() for x in tickers_input.split(",") if x.strip()]
    refresh_val = st.select_slider("Odświeżanie (sek)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh_val * 1000, key="fscounter")

# --- 5. WYŚWIETLANIE ---
if api_key:
    client = OpenAI(api_key=api_key)
    for t in tickers:
        data = get_data(t)
        if not data: continue
        
        if data['rsi'] < 35 or data['vol_spike']: play_sound()

        card_style = "border-right: 5px solid #00ff88;" if data['trend'] == "BULL 🐂" else "border-right: 5px solid #ff4b4b;"
        st.markdown(f'<div class="ticker-card {"buy-signal" if data["rsi"] < 35 else ""}" style="{card_style}">', unsafe_allow_html=True)
        c1, c2 = st.columns([1.5, 2.5])
        
        with c1:
            st.subheader(t)
            st.markdown(f"## {data['price']:.4f}")
            if data['vol_spike']: st.markdown('<span class="vol-spike">🔥 WYSTRZAŁ WOLUMENU!</span>', unsafe_allow_html=True)
            
            st.markdown(f"<span class='tf-badge'>{data['trend']}</span><span class='tf-badge'>RSI: {data['rsi']:.1f}</span>", unsafe_allow_html=True)
            
            st.markdown(f"""<div style="background:#12141d; padding:10px; border-radius:8px; margin:10px 0; border:1px solid #333;">
                <b style="color:#00ff88">🎯 TP: {data['tp']:.4f}</b> | <b style="color:#ff4b4b">🛑 SL: {data['sl']:.4f}</b><br>
                <small style="color:#888;">PIVOT: {data['pivot']:.4f} | BB DOLNA: {data['lbb']:.4f}</small>
            </div>""", unsafe_allow_html=True)

            if st.button(f"🧠 ANALIZA PRO {t}", key=f"ai_{t}"):
                p = f"Analiza {t}: Cena {data['price']}, RSI {data['rsi']:.1f}, Skok Wolumenu: {data['vol_spike']}, Trend {data['trend']}. Daj werdykt (KUP/CZEKAJ/SPRZEDAJ) i krótkie uzasadnienie techniczne."
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": p}])
                st.session_state[f"v_{t}"] = res.choices.message.content

            if f"v_{t}" in st.session_state:
                st.markdown(f'<div class="verdict-box">{st.session_state[f"v_{t}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-60:], open=data['df']['Open'][-60:], high=data['df']['High'][-60:], low=data['df']['Low'][-60:], close=data['df']['Close'][-60:], name="Cena")])
            # Rysowanie Wstęg Bollingera
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['upper_bb'][-60:], line=dict(color='rgba(173, 216, 230, 0.2)'), name="BB Góra"))
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['lower_bb'][-60:], line=dict(color='rgba(173, 216, 230, 0.2)'), fill='tonexty', name="BB Dół"))
            
            fig.add_hline(y=data['pivot'], line_dash="dot", line_color="white")
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{t}")
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Wprowadź API Key OpenAI.")
