import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. PAMIĘĆ SPÓŁEK ---
DB_FILE = "moje.txt" 

def save_tickers(text):
    try:
        with open(DB_FILE, "w") as f: f.write(text)
    except: pass

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, IOVA"
    return "PKO.WA, BTC-USD, NVDA, IOVA"

# --- 2. KONFIGURACJA I STYLE ---
st.set_page_config(page_title="AI Alpha Terminal v9.2 PRO", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #ffffff; }
    .ticker-card { background: #0a0b10; padding: 20px; border-radius: 15px; border: 1px solid #1a1c23; margin-bottom: 25px; }
    .buy-signal { border: 2px solid #00ff88 !important; box-shadow: 0 0 20px rgba(0, 255, 136, 0.2); }
    .verdict-box { background: #07121d; padding: 15px; border-radius: 10px; border-left: 5px solid #00e5ff; margin-top: 10px; font-size: 0.95rem; font-weight: 500; }
    .tf-badge { background: #1a1a1a; padding: 6px 12px; border-radius: 6px; font-size: 0.85rem; color: #00e5ff; border: 1px solid #333; margin-right: 8px; }
    .price-text { font-size: 2.2rem; font-weight: 800; color: #ffffff; margin: 0; }
    .vol-spike { color: #ff00ff; font-weight: bold; font-size: 0.9rem; display: block; margin: 5px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIKA DANYCH ---
def play_sound():
    st.components.v1.html('<audio autoplay><source src="https://mixkit.co" type="audio/mpeg"></audio>', height=0)

def get_data(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        if d15.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        sma20 = d15['Close'].rolling(20).mean()
        std20 = d15['Close'].rolling(20).std()
        upper_bb, lower_bb = sma20 + (std20 * 2), sma20 - (std20 * 2)

        avg_vol = d15['Volume'].rolling(30).mean().iloc[-1]
        vol_spike = d15['Volume'].iloc[-1] > (avg_vol * 1.8)

        # Fix RSI - obsługa NaN
        delta = d15['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        if pd.isna(rsi): rsi = 50.0 # Neutralny jeśli brak danych
        
        sma_d = d1d['Close'].rolling(100).mean().iloc[-1]
        prev = d1d.iloc[-2]
        pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
        atr = (d1d['High'] - d1d['Low']).rolling(20).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": price, "rsi": rsi, "pivot": pivot,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.0),
            "trend": "BULL 🐂" if price > sma_d else "BEAR 🐻",
            "vol_spike": vol_spike, "df": d15, "lbb": lower_bb.iloc[-1],
            "lower_bb": lower_bb, "upper_bb": upper_bb
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.header("⚙️ TERMINAL")
    api_key = st.text_input("OpenAI API Key:", type="password")
    saved_list = load_tickers()
    tickers_input = st.text_area("Lista Spółek:", value=saved_list, height=150)
    if tickers_input != saved_list: save_tickers(tickers_input)
    tickers = [x.strip().upper() for x in tickers_input.split(",") if x.strip()]
    refresh_val = st.select_slider("Odświeżanie (sek)", options=[30, 60, 300, 600], value=60)

st_autorefresh(interval=refresh_val * 1000, key="fscounter")

# --- 5. WYŚWIETLANIE ---
if api_key:
    client = OpenAI(api_key=api_key)
    for t in tickers:
        data = get_data(t)
        if not data: continue
        
        if data['rsi'] < 32 or data['vol_spike']: play_sound()

        card_style = "border-right: 6px solid #00ff88;" if data['trend'] == "BULL 🐂" else "border-right: 6px solid #ff4b4b;"
        st.markdown(f'<div class="ticker-card {"buy-signal" if data["rsi"] < 32 else ""}" style="{card_style}">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader(t)
            st.markdown(f"<p class='price-text'>{data['price']:.4f}</p>", unsafe_allow_html=True)
            if data['vol_spike']: st.markdown('<span class="vol-spike">🔥 SKOK WOLUMENU (AKTYWNOŚĆ)</span>', unsafe_allow_html=True)
            
            st.markdown(f"<span class='tf-badge'>{data['trend']}</span><span class='tf-badge'>RSI: {data['rsi']:.1f}</span>", unsafe_allow_html=True)
            
            st.markdown(f"""<div style="background:#12141d; padding:12px; border-radius:8px; margin:15px 0; border:1px solid #333;">
                <b style="color:#00ff88; font-size:1.1rem;">🎯 TP: {data['tp']:.3f}</b><br>
                <b style="color:#ff4b4b; font-size:1.1rem;">🛑 SL: {data['sl']:.3f}</b><br>
                <span style='color:#888; font-size:0.9rem;'>Pivot: {data['pivot']:.3f} | BB Dół: {data['lbb']:.3f}</span>
            </div>""", unsafe_allow_html=True)

            if st.button(f"🧠 WYSTAW WERDYKT {t}", key=f"ai_{t}"):
                prompt = f"""
                Jesteś ekspertem giełdowym. Na podstawie danych dla {t}:
                - Cena: {data['price']}, RSI: {data['rsi']:.1f}, Trend: {data['trend']}, Skok wolumenu: {data['vol_spike']}
                TWOJE ZADANIE:
                1. Daj ocenę wejścia od 1 do 10.
                2. Wybierz jeden status: KUPUJ, CZEKAJ lub SPRZEDAJ.
                3. Uzasadnij w jednym, konkretnym zdaniu (dlaczego tak, a nie inaczej).
                Bądź zdecydowany, unikaj ogólników.
                """
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"v_{t}"] = res.choices[0].message.content

            if f"v_{t}" in st.session_state:
                st.markdown(f'<div class="verdict-box">{st.session_state[f"v_{t}"]}</div>', unsafe_allow_html=True)

        with c2:
            fig = go.Figure(data=[go.Candlestick(
                x=data['df'].index[-60:], open=data['df']['Open'][-60:], high=data['df']['High'][-60:], 
                low=data['df']['Low'][-60:], close=data['df']['Close'][-60:], name="Cena"
            )])
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['upper_bb'][-60:], line=dict(color='rgba(0, 229, 255, 0.3)', width=1), name="BB Góra"))
            fig.add_trace(go.Scatter(x=data['df'].index[-60:], y=data['lower_bb'][-60:], line=dict(color='rgba(0, 229, 255, 0.3)', width=1), fill='tonexty', name="BB Dół"))
            fig.add_hline(y=data['pivot'], line_dash="dot", line_color="white", annotation_text="PIVOT")
            fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=10,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_{t}", config={'displayModeBar': False})
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Wprowadź API Key OpenAI.")
