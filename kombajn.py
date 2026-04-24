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
st.set_page_config(page_title="CYBER KOMBAJN v22.0", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    /* Karta spólki */
    .ticker-card { 
        background: linear-gradient(145deg, #0f111a, #1a1c2b); 
        padding: 25px; border-radius: 15px; 
        border: 1px solid #30363d; margin-bottom: 30px;
        box-shadow: 5px 5px 15px rgba(0,0,0,0.5);
    }
    /* Kafelki Top 10 */
    .top-tile {
        background: #111420; padding: 12px; border-radius: 10px;
        border-bottom: 3px solid #00e5ff; text-align: center;
        min-height: 140px; margin-bottom: 10px;
    }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 8px 0; font-size: 0.9rem; }
    .signal-buy { color: #00ff88; text-shadow: 0 0 10px #00ff8855; font-weight: bold; }
    .signal-sell { color: #ff4b4b; text-shadow: 0 0 10px #ff4b4b55; font-weight: bold; }
    .bid-ask { font-family: 'Courier New', monospace; color: #00e5ff; font-weight: bold; font-size: 0.85rem; }
    .pivot-val { color: #f1c40f; font-weight: bold; }
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
        
        # Bid / Ask (Symulacja 0.01% spreadu)
        bid, ask = price * 0.9999, price * 1.0001
        
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
        if rsi < 32: verdict, v_class = "KUP 🔥", "signal-buy"
        elif rsi > 68: verdict, v_class = "SPRZEDAJ ⚠️", "signal-sell"
        else: verdict, v_class = "CZEKAJ", ""

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "verdict": verdict, "v_class": v_class, "pp": pp,
            "sma20": sma20, "sma50": sma50, "sma200": sma200,
            "tp": price + (atr * 1.5), "sl": price - (atr * 1.2),
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 CYBER KOMBAJN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    t_input = st.text_area("Lista Symboli:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ TĘ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista siedzi w pamięci!")
    
    refresh = st.select_slider("Prędkość odświeżania (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="auto_sync")

# --- 5. LOGIKA WYŚWIETLANIA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
all_data = []

for t in tickers:
    res = get_analysis(t)
    if res: all_data.append(res)

if all_data:
    # --- TOP 10 SKANER OKAZJI ---
    st.subheader("🚀 SKANER TOP 10 (RSI 1H)")
    # Sortujemy od najbardziej wyprzedanych (najniższe RSI)
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-tile">
                    <b style="font-size:1.1rem; color:#00e5ff;">{d['symbol']}</b><br>
                    <span style="font-size:1.2rem; font-weight:bold;">{d['price']:.2f}</span><br>
                    <div class="bid-ask">B: {d['bid']:.2f} | A: {d['ask']:.2f}</div>
                    <div class="metric-row"><span style="color:#888;">Pivot:</span> <span class="pivot-val">{d['pp']:.2f}</span></div>
                    <div class="{d['v_class']}" style="margin-top:5px; font-size:0.8rem;">{d['verdict']}</div>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- KARTY SZCZEGÓŁOWE ---
    for data in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            
            with c1:
                st.subheader(data['symbol'])
                ch_col = "#00ff88" if data['change'] >= 0 else "#ff4b4b"
                st.markdown(f"<h2 style='color:{ch_col}; margin-bottom:0;'>{data['price']:.2f} <small style='font-size:1rem;'>({data['change']:.2f}%)</small></h2>", unsafe_allow_html=True)
                st.markdown(f"<div class='bid-ask' style='font-size:1rem;'>BID: {data['bid']:.4f} | ASK: {data['ask']:.4f}</div>", unsafe_allow_html=True)
                
                st.markdown(f"""
                    <div style="margin-top:15px;">
                        <div class="metric-row"><span>RSI (1h)</span><b class="{data['v_class']}">{data['rsi']:.1f}</b></div>
                        <div class="metric-row"><span>Pivot Point</span><b class="pivot-val">{data['pp']:.4f}</b></div>
                        <div class="metric-row"><span>Trend (SMA200)</span><b>{'Wzrost 📈' if data['price'] > data['sma200'] else 'Spadek 📉'}</b></div>
                        <div class="metric-row"><span style="color:#00ff88;">Target TP</span><b>{data['tp']:.2f}</b></div>
                        <div class="metric-row"><span style="color:#ff4b4b;">Stop Loss SL</span><b>{data['sl']:.2f}</b></div>
                    </div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=data['df'].index[-40:], open=data['df']['Open'][-40:], high=data['df']['High'][-40:], low=data['df']['Low'][-40:], close=data['df']['Close'][-40:])])
                # Nakładamy SMA 50 dla koloru
                fig.add_hline(y=data['pp'], line_dash="dot", line_color="#f1c40f", annotation_text="Pivot")
                fig.update_layout(template="plotly_dark", height=320, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{data['symbol']}")

            with c3:
                st.markdown("### 🛠 SMA LEVELS")
                st.write(f"SMA 20: `{data['sma20']:.2f}`")
                st.write(f"SMA 50: `{data['sma50']:.2f}`")
                st.write(f"SMA 200: `{data['sma200']:.2f}`")
                
                if api_key and st.button(f"🧠 AI STRATEGIA {data['symbol']}", key=f"ai_{data['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": f"Werdykt giełdowy dla {data['symbol']}. Cena: {data['price']}, RSI: {data['rsi']:.1f}, Pivot: {data['pp']:.2f}. Podaj wejście i ryzyko."}]
                    )
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj symbole w panelu bocznym (np. BTC-USD, NVDA, PKO.WA)")
