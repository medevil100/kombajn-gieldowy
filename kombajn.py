import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
import time

# --- 1. KONFIGURACJA ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, ALE.WA, KGH.WA"
        except: return "PKO.WA, ALE.WA, KGH.WA"
    return "PKO.WA, ALE.WA, KGH.WA"

st.set_page_config(page_title="AI ALPHA GOLDEN v41.2 FIX", page_icon="🚜", layout="wide")

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. STYLE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .top-tile { text-align: center; padding: 20px; border-radius: 15px; background: #0d1117; min-height: 460px; border: 1px solid #30363d; transition: 0.3s; }
    .top-tile:hover { transform: translateY(-5px); border-color: #58a6ff; }
    .sig-buy { color: #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 10px; border-radius: 8px; background: rgba(0,255,136,0.1); }
    .sig-sell { color: #ff4b4b; font-weight: bold; border: 2px solid #ff4b4b; padding: 5px 10px; border-radius: 8px; background: rgba(255,75,75,0.1); }
    .sig-neutral { color: #8b949e; font-weight: bold; border: 1px solid #30363d; padding: 5px 10px; border-radius: 8px; }
    .pos-calc { background: rgba(88, 166, 255, 0.1); border-radius: 8px; padding: 12px; margin: 15px 0; border: 1px solid #58a6ff; color: #58a6ff; font-weight: bold; }
    .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.75rem; text-align: left; margin-top: 10px; }
    .stat-item { border-bottom: 1px solid #21262d; padding: 2px 0; }
    .ai-box { padding: 10px; border-radius: 8px; margin-top: 10px; font-size: 0.8rem; background: rgba(255,255,255,0.03); min-height: 50px; }
    .news-box { font-size: 0.7rem; color: #8b949e; text-align: left; margin-top: 10px; border-top: 1px dashed #30363d; padding-top: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY (Z OCHRONĄ PRZED RATE LIMIT) ---
def get_analysis(symbol, api_key=None):
    try:
        time.sleep(0.6) # Ochrona przed "Too Many Requests"
        symbol = symbol.strip().upper()
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="250d", interval="1d")
        
        if df.empty or len(df) < 50: return None
        
        price = float(df['Close'].iloc[-1])
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # Pivot
        hp, lp, cp = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pivot = (hp + lp + cp) / 3
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # ATR i Ryzyko
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        risk_money = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.5
        shares = int(risk_money / sl_dist) if sl_dist > 0 else 0
        
        # Newsy (Bezpieczne pobieranie)
        news_data = []
        try:
            raw_news = ticker.news
            if raw_news:
                for n in raw_news[:2]:
                    news_data.append({"title": n.get('title', '')[:50] + "...", "link": n.get('link', '#')})
        except: pass
        if not news_data: news_data = [{"title": "Brak newsów rynkowych", "link": "#"}]

        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        ai_msg = "Podaj klucz AI"
        if api_key and len(api_key) > 20:
            try:
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": f"Symbol: {symbol}, Price: {price}, RSI: {rsi:.0f}. Napisz 1 konkretne zdanie analizy."}],
                    max_tokens=30
                )
                ai_msg = resp.choices.message.content
            except: ai_msg = "AI Offline"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "pivot": pivot, "verd": verd, "vcl": vcl, "v_type": v_type, "shares": shares,
            "sl": price - sl_dist, "tp": price + (atr * 3), "ai": ai_msg, 
            "news": news_data, "df": df.tail(40), "val": shares * price
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v41.2")
    api_key = st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
    ticker_area = st.text_area("Symbole:", value=load_tickers(), height=150)
    if st.button("💾 AKTUALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.rerun()
    refresh = st.select_slider("Refresh (s)", options=[60, 120, 300, 600], value=60)

st_autorefresh(interval=refresh * 1000, key="v412_refresh")

# --- 5. WYŚWIETLANIE ---
tickers = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

data_ready = []
progress_bar = st.progress(0)
for i, t in enumerate(tickers):
    res = get_analysis(t, api_key)
    if res: data_ready.append(res)
    progress_bar.progress((i + 1) / len(tickers))

if data_ready:
    st.subheader(f"📊 TERMINAL ALPHA GOLDEN - {datetime.now().strftime('%H:%M:%S')}")
    for i in range(0, len(data_ready), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                border = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="top-tile" style="border: 2px solid {border};">
                    <div style="font-size:1.4rem; font-weight:bold;">{d['symbol']}</div>
                    <div style="color:#58a6ff; font-size:1.1rem;">{d['price']:.2f} PLN</div>
                    <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    <div class="pos-calc">KUP: {d['shares']} szt.<br><small>{d['val']:.0f} PLN</small></div>
                    <div class="stat-grid">
                        <div class="stat-item"><b>SMA50:</b> {d['sma50']:.2f}</div>
                        <div class="stat-item"><b>SMA200:</b> {d['sma200']:.2f}</div>
                        <div class="stat-item"><b>PIVOT:</b> {d['pivot']:.2f}</div>
                        <div class="stat-item"><b>RSI:</b> {d['rsi']:.0f}</div>
                    </div>
                    <div class="ai-box"><b>AI:</b> {d['ai']}</div>
                    <div class="news-box">
                        <b>INFO:</b><br>
                        • <a style="color:#58a6ff;text-decoration:none;" href="{d['news'][0]['link']}" target="_blank">{d['news'][0]['title']}</a>
                        {('<br>• <a style="color:#58a6ff;text-decoration:none;" href="'+d['news'][1]['link']+'" target="_blank">'+d['news'][1]['title']+'</a>') if len(d['news']) > 1 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander("Wykres"):
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
