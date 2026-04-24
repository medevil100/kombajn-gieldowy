import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I PAMIĘĆ ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "NVDA, TSLA, BTC-USD, PKO.WA"
    return "NVDA, TSLA, BTC-USD, PKO.WA"

st.set_page_config(page_title="AI ALPHA GOLDEN v26", page_icon="🚜", layout="wide")

# --- 2. STYLE WIZUALNE ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0f111a, #1a1c2b); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px;
    }
    .top-tile {
        background: #111420; padding: 12px; border-radius: 10px; border-bottom: 3px solid #00ff88; 
        text-align: center; min-height: 180px;
    }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; }
    .bid-ask-mini { font-family: monospace; font-size: 0.75rem; color: #58a6ff; }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        
        # Pobieranie danych 1h i 1d (szerszy zakres dla szczytów/dołków)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d") # 1 rok dla ekstremów
        
        if h1.empty or d1.empty: return None
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        if isinstance(d1.columns, pd.MultiIndex): d1.columns = d1.columns.get_level_values(0)
        
        price = h1['Close'].iloc[-1]
        
        # Bid/Ask
        try:
            bid = t.info.get('bid') or price * 0.9998
            ask = t.info.get('ask') or price * 1.0002
        except:
            bid, ask = price * 0.9998, price * 1.0002
        
        # Wskaźniki i Ekstrema (Górki i Dołki)
        sma50 = d1['Close'].rolling(50).mean().iloc[-1]
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        yearly_high = d1['High'].max()
        yearly_low = d1['Low'].min()
        
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI 1h
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Werdykt
        if rsi < 32: verd, vcl = "KUP 🔥", "sig-buy"
        elif rsi > 68: verd, vcl = "SPRZEDAJ ⚠️", "sig-sell"
        else: verd, vcl = "CZEKAJ ⏳", ""

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi, 
            "pp": pp, "sma50": sma50, "sma200": sma200, "verdict": verd, "vcl": vcl,
            "y_high": yearly_high, "y_low": yearly_low,
            "tp": price + (atr * 1.8), "sl": price - (atr * 1.3),
            "df": h1, "change": ((price - cp) / cp * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v26")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana!")
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v26_fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=8) as executor:
    all_data = [d for d in list(executor.map(get_analysis, tickers)) if d is not None]

if all_data:
    # --- TOP 10 RANKING Z BID/ASK ---
    st.subheader("🏆 TOP SYGNAŁY (Bid/Ask w rankingu)")
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-tile">
                    <b>{d['symbol']}</b><br>
                    <span style="font-size:1.1rem; color:#00ff88;">{d['price']:.2f}</span><br>
                    <div class="bid-ask-mini">B: {d['bid']:.2f} | A: {d['ask']:.2f}</div>
                    <div class="{d['vcl']}" style="margin-top:5px;">{d['verdict']}</div>
                    <small>RSI: {d['rsi']:.1f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            
            with c1:
                st.markdown(f"<h3 class='{d['vcl']}'>{d['symbol']} {d['verdict']}</h3>", unsafe_allow_html=True)
                st.metric("CENA", f"{d['price']:.4f}", f"{d['change']:.2f}%")
                st.markdown(f"""
                    <div style="margin-top:15px;">
                        <div class="metric-row"><span>RSI (1h)</span><b>{d['rsi']:.1f}</b></div>
                        <div class="metric-row"><span>SMA 200</span><b>{d['sma200']:.2f}</b></div>
                        <div class="metric-row"><span style="color:#00ff88;">Szczyt 52t</span><b>{d['y_high']:.2f}</b></div>
                        <div class="metric-row"><span style="color:#ff4b4b;">Dołek 52t</span><b>{d['y_low']:.2f}</b></div>
                    </div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-50:], open=d['df']['Open'][-50:], high=d['df']['High'][-50:], low=d['df']['Low'][-50:], close=d['df']['Close'][-50:])])
                # Linie szczytów i dołków na wykresie
                fig.add_hline(y=d['y_high'], line_dash="dash", line_color="#00ff88", annotation_text="High")
                fig.add_hline(y=d['y_low'], line_dash="dash", line_color="#ff4b4b", annotation_text="Low")
                fig.update_layout(template="plotly_dark", height=320, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")

            with c3:
                st.write(f"BID: **{d['bid']:.4f}**")
                st.write(f"ASK: **{d['ask']:.4f}**")
                st.write(f"Pivot: **{d['pp']:.2f}**")
                
                if api_key and st.button(f"🧠 AI STRATEGIA", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    # Wysłanie kompletnych danych historycznych do AI
                    prompt = (f"Przeanalizuj {d['symbol']}. Dane: Cena {d['price']}, Bid {d['bid']}, Ask {d['ask']}. "
                             f"RSI {d['rsi']:.1f}, SMA50 {d['sma50']:.2f}, SMA200 {d['sma200']:.2f}. "
                             f"Szczyt 12m: {d['y_high']}, Dołek 12m: {d['y_low']}. "
                             f"Podaj konkretny werdykt i plan wejścia/wyjścia.")
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.success(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj symbole i OpenAI Key w panelu bocznym.")
