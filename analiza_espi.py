import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA GOLDEN v16.3", page_icon="💰", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .status-hossa { color: #238636; font-weight: bold; }
    .status-bessa { color: #da3633; font-weight: bold; }
    .verdict-badge { padding: 5px 12px; border-radius: 15px; font-weight: bold; text-transform: uppercase; }
    .v-buy { background: #238636; color: white; }
    .v-sell { background: #da3633; color: white; }
    .v-wait { background: #8b949e; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- SILNIK DANYCH ---
def get_data(symbol):
    try:
        d1d = yf.download(symbol, period="2y", interval="1d", progress=False, auto_adjust=True)
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False, auto_adjust=True)
        if d15.empty or d1d.empty: return None
        if isinstance(d15.columns, pd.MultiIndex): d15.columns = d15.columns.get_level_values(0)
        if isinstance(d1d.columns, pd.MultiIndex): d1d.columns = d1d.columns.get_level_values(0)

        price = float(d15['Close'].iloc[-1])
        sma200 = float(d1d['Close'].rolling(200).mean().iloc[-1])
        
        # Statystyki Historyczne
        high_52w = float(d1d['High'].max())
        low_52w = float(d1d['Low'].min())
        dist_from_high = ((price - high_52w) / high_52w) * 100
        
        # Wskaźniki Techniczne
        h_p, l_p, c_p = float(d1d['High'].iloc[-2]), float(d1d['Low'].iloc[-2]), float(d1d['Close'].iloc[-2])
        pivot = (h_p + l_p + c_p) / 3
        
        delta = d1d['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        atr = float((d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1])

        # Logika sygnałów
        trend = "HOSSA" if price > sma200 else "BESSA"
        if rsi < 30: verdict, v_class = "KUP", "v-buy"
        elif rsi > 70: verdict, v_class = "SPRZEDAJ", "v-sell"
        else: verdict, v_class = "CZEKAJ", "v-wait"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma200": sma200, "pivot": pivot,
            "verdict": verdict, "v_class": v_class, "trend": trend,
            "peak": high_52w, "bottom": low_52w, "dist_high": dist_from_high,
            "tp": price + (atr * 2), "sl": price - (atr * 1.5), "df": d15
        }
    except: return None

# --- UI SIDEBAR ---
with st.sidebar:
    st.title("🍯 v16.3 GOLDEN")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Symbole", value="PKO.WA, STX.WA, NVDA, BTC-USD")
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)
st_autorefresh(interval=refresh * 1000, key="fsh")

# --- ANALIZA ---
t_list = [t.strip().upper() for t in t_input.split(",") if t.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [r for r in list(executor.map(get_data, t_list)) if r]

if data_list:
    # --- TABELA TOP 10 (SZYBKI PODGLĄD) ---
    st.subheader("📊 RANKING I SYGNAŁY")
    summary_df = pd.DataFrame([
        {"Symbol": d['symbol'], "Cena": f"{d['price']:.2f}", "Trend": d['trend'], 
         "RSI": round(d['rsi'], 1), "Werdykt": d['verdict'], "Od Szczytu %": f"{d['dist_high']:.1f}%"}
        for d in data_list
    ])
    st.table(summary_df)

    # --- KARTY ANALITYCZNE ---
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 2])
        
        with c1:
            st.markdown(f"### {d['symbol']}")
            st.markdown(f"Status: <span class='{'status-hossa' if d['trend'] == 'HOSSA' else 'status-bessa'}'>{d['trend']}</span>", unsafe_allow_html=True)
            st.markdown(f"<span class='verdict-badge {d['v_class']}'>{d['verdict']}</span>", unsafe_allow_html=True)
            st.write(f"Cena: **{d['price']:.2f}**")
            st.write(f"RSI: {d['rsi']:.1f}")

        with c2:
            st.write("📍 **Poziomy Techniczne**")
            st.write(f"Target (TP): {d['tp']:.2f}")
            st.write(f"Stop Loss (SL): {d['sl']:.2f}")
            st.write(f"Pivot: {d['pivot']:.2f}")
            st.write(f"Dołek 52t: {d['bottom']:.2f}")

        with c3:
            if api_key and st.button(f"🧠 AI STRATEGIA: {d['symbol']}", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = (f"Jesteś ekspertem giełdowym. Symbol: {d['symbol']}, Cena: {d['price']}, "
                          f"SMA200: {d['sma200']}, RSI: {d['rsi']}, Szczyt: {d['peak']}, Trend: {d['trend']}. "
                          f"Podaj: 1. KRÓTKI WERDYKT, 2. CENA WEJŚCIA, 3. RYZYKO (skala 1-10).")
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.session_state[f"res_{d['symbol']}"] = resp.choices[0].message.content
            
            if f"res_{d['symbol']}" in st.session_state:
                st.info(st.session_state[f"res_{d['symbol']}"])

        # Wykres na pełną szerokość pod danymi
        fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
