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
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "NVDA, TSLA, BTC-USD, PKO.WA"
    return "NVDA, TSLA, BTC-USD, PKO.WA"

st.set_page_config(page_title="AI ALPHA GOLDEN v30", page_icon="🚜", layout="wide")

if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #030303; color: #e0e0e0; }
    .ticker-card { background: #0d1117; padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-tile-buy { border: 1px solid #00ff88; box-shadow: 0px 0px 10px rgba(0, 255, 136, 0.2); text-align: center; padding: 15px; border-radius: 12px; }
    .top-tile-sell { border: 1px solid #ff4b4b; box-shadow: 0px 0px 10px rgba(255, 75, 75, 0.2); text-align: center; padding: 15px; border-radius: 12px; }
    .top-tile-neutral { border: 1px solid #30363d; text-align: center; padding: 15px; border-radius: 12px; }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: monospace; font-size: 1.1rem; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: monospace; font-size: 1.1rem; }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        # Realne dane Bid/Ask lub symulacja
        bid = t.info.get('bid') or price * 0.9998
        ask = t.info.get('ask') or price * 1.0002
        
        # Ekstrema i Pivoty
        y_high = d1['High'].max()
        y_low = d1['Low'].min()
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI i Wolumen
        delta = h1['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        vol_ratio = h1['Volume'].iloc[-1] / h1['Volume'].rolling(20).mean().iloc[-1]
        
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp, "spread": ask-bid,
            "tp": price + (atr * 1.6), "sl": price - (atr * 1.2),
            "y_high": y_high, "y_low": y_low, "vol_ratio": vol_ratio, "df": h1
        }
    except: return None

# --- 4. BOCZNY PANEL ---
with st.sidebar:
    st.title("🚜 GOLDEN v30")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole (np. NVDA, BTC-USD):", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
    refresh = st.select_slider("Refresh (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v30_refresh")

# --- 5. GŁÓWNA LOGIKA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=10) as ex:
    all_data = [d for d in list(ex.map(get_analysis, tickers)) if d]

if all_data:
    # NEON TOP 10
    st.subheader("🏆 TOP SYGNAŁY")
    cols = st.columns(5)
    for i, d in enumerate(all_data[:10]):
        with cols[i % 5]:
            st.markdown(f"""<div class="top-tile-{d['v_type']}"><b>{d['symbol']}</b><br><span style="font-size:1.2rem; color:#58a6ff;">{d['price']:.2f}</span><br><div class="bid-box">B: {d['bid']:.2f}</div><div class="ask-box">A: {d['ask']:.2f}</div><div class="{d['vcl']}">{d['verd']}</div></div>""", unsafe_allow_html=True)

    st.divider()

    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.2, 2, 1.4])
            
            with c1:
                st.markdown(f"<h3 class='{d['vcl']}'>{d['symbol']} | {d['verd']}</h3>", unsafe_allow_html=True)
                st.write(f"Cena: **{d['price']:.4f}**")
                st.markdown(f"""
                    <div style="font-size:0.9rem; line-height:1.6;">
                    🔵 Pivot: <b>{d['pp']:.2f}</b><br>
                    🟢 TP: <b>{d['tp']:.2f}</b><br>
                    🔴 SL: <b>{d['sl']:.2f}</b><br>
                    📏 Szczyt/Dołek: {d['y_high']:.2f} / {d['y_low']:.2f}
                    </div>
                """, unsafe_allow_html=True)
            
            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-40:], open=d['df']['Open'][-40:], high=d['df']['High'][-40:], low=d['df']['Low'][-40:], close=d['df']['Close'][-40:])])
                fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"fig_{d['symbol']}")
            
            with c3:
                # Panel Bid/Ask
                st.markdown(f"""
                    <div style="background: #161b22; padding: 10px; border-radius: 8px; border: 1px solid #30363d;">
                        <span style="color:#ff4b4b; font-size:0.75rem;">BID</span><br><span class="bid-box">{d['bid']:.4f}</span><br>
                        <span style="color:#00ff88; font-size:0.75rem;">ASK</span><br><span class="ask-box">{d['ask']:.4f}</span><br>
                        <small style="color:#58a6ff;">Spread: {d['spread']:.4f} | Vol: x{d['vol_ratio']:.2f}</small>
                    </div>
                """, unsafe_allow_html=True)
                
                # AI Sekcja z Cache i solidnym promptem
                if st.button(f"🧠 ANALIZA TECHNICZNA AI", key=f"ai_btn_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = (f"Analiza techniczna dla {d['symbol']}. Cena: {d['price']}. "
                              f"RSI: {d['rsi']:.1f}, Wolumen: x{d['vol_ratio']:.2f} średniej. "
                              f"Pivot: {d['pp']:.2f}, Opór (Szczyt): {d['y_high']:.2f}, Wsparcie (Dołek): {d['y_low']:.2f}. "
                              f"Na podstawie tych danych określ: 1. Sentyment, 2. Czy cena jest blisko ekstremum?, "
                              f"3. Konkretny plan wejścia (Cena) i wyjścia (TP/SL). Mów jak zawodowiec, konkretnie.")
                    
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Jesteś analitykiem technicznym. Twoje odpowiedzi muszą opierać się na dostarczonych liczbach (RSI, Pivot, Szczyty/Dołki). Zakaz lania wody. Formatuj od myślników."},
                                  {"role": "user", "content": prompt}]
                    )
                    st.session_state.ai_cache[d['symbol']] = res.choices[0].message.content
                
                if d['symbol'] in st.session_state.ai_cache:
                    st.markdown(f"""<div style="font-size:0.85rem; color:#d1d5db; margin-top:10px; padding:10px; background:#0d1117; border-left:3px solid #58a6ff;">
                        {st.session_state.ai_cache[d['symbol']]}
                    </div>""", unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

st.caption("AI Alpha Golden v30 | Dane: Yahoo Finance | Technologia: OpenAI GPT-4o-mini")
