import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.1", page_icon="📈", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                content = f.read().strip()
                return content if content else "PKO.WA, BTC-USD, NVDA, TSLA"
        except: return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieranie danych
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if d15.empty or d1d.empty: return None
        
        # Naprawa nazw kolumn (yfinance multi-index fix)
        if isinstance(d15.columns, pd.MultiIndex): d15.columns = d15.columns.get_level_values(0)
        if isinstance(d1d.columns, pd.MultiIndex): d1d.columns = d1d.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        
        # Trend i Wskaźniki
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#00ff88" if price > sma200 else "#ff4b4b"
        
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        pivot = (d1d['High'].iloc[-2] + d1d['Low'].iloc[-2] + d1d['Close'].iloc[-2]) / 3
        
        # RSI
        delta = d15['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Rekomendacja
        if rsi < 32: rec, rec_col = "KUPUJ", "#238636"
        elif rsi > 68: rec, rec_col = "SPRZEDAJ", "#da3633"
        else: rec, rec_col = "CZEKAJ", "#8b949e"

        return {
            "symbol": symbol, "price": price, "change": change_pct, "rsi": rsi, 
            "rec": rec, "rec_col": rec_col, "trend": trend_label, "trend_col": trend_color,
            "pivot": pivot, "tp": price + (atr * 1.5), "sl": price - (atr * 1.2), "df": d15
        }
    except: return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ KOMB_v12.1")
    
    # Obsługa klucza
    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("✅ Klucz aktywny (Secrets)")
    else:
        api_key = st.text_input("OpenAI Key", type="password")
        if not api_key:
            st.warning("Dodaj klucz w Secrets lub wpisz go tutaj.")

    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
        st.rerun()
    
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. GŁÓWNA LOGIKA ---
if api_key:
    client = OpenAI(api_key=api_key)
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    
    data_list = []
    for t in tickers:
        res = get_analysis(t)
        if res: data_list.append(res)

    if data_list:
        # --- TOP Monitoring ---
        st.subheader("📊 MONITORING RYNKU")
        top_cols = st.columns(min(len(data_list), 5))
        
        for i, d in enumerate(data_list[:10]):
            with top_cols[i % 5]:
                c_col = "#00ff88" if d['change'] >= 0 else "#ff4b4b"
                st.markdown(f"""
                    <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                        <b>{d['symbol']}</b><br>
                        <span style="color:{c_col}; font-weight:bold;">{d['price']:.2f}</span><br>
                        <span style="font-size:0.8rem; color:{d['trend_col']};">{d['trend']}</span><br>
                        <div style="background:{d['rec_col']}; font-size:0.7rem; border-radius:3px; margin:5px 0; color:white;">{d['rec']}</div>
                        <span class="stat-label">RSI: {d['rsi']:.1f} | P: {d['pivot']:.1f}</span>
                    </div>
                """, unsafe_allow_html=True)

        # --- SZCZEGÓŁY ---
        for d in data_list:
            st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f"### {d['symbol']} ({d['trend']})")
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**Pivot:** {d['pivot']:.2f} | **RSI:** {d['rsi']:.1f}")
                st.write(f"**TP:** {d['tp']:.2f} | **SL:** {d['sl']:.2f}")
                
                if st.button(f"🧠 ANALIZA AI {d['symbol']}", key=f"btn_{d['symbol']}"):
                    try:
                        prompt = f"Jako agresywny trader oceń: {d['symbol']}, Cena: {d['price']}, Trend: {d['trend']}, RSI: {d['rsi']:.1f}. Pivot: {d['pivot']:.2f}. Podaj konkretny werdykt i ryzyko 1-10."
                        resp = client.chat.completions.create(
                            model="gpt-4o", 
                            messages=[{"role": "user", "content": prompt}]
                        )
                        st.session_state[f"ai_{d['symbol']}"] = resp.choices[0].message.content
                    except Exception as e:
                        st.error(f"Błąd AI: {e}")
                
                if f"ai_{d['symbol']}" in st.session_state:
                    st.info(st.session_state[f"ai_{d['symbol']}"])
            
            with c2:
                fig = go.Figure(data=[go.Candlestick(
                    x=d['df'].index[-50:], 
                    open=d['df']['Open'][-50:], 
                    high=d['df']['High'][-50:], 
                    low=d['df']['Low'][-50:], 
                    close=d['df']['Close'][-50:]
                )])
                fig.add_hline(y=d['pivot'], line_dash="dot", line_color="white")
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Wprowadź OpenAI API Key w pasku bocznym lub dodaj do Secrets.")
