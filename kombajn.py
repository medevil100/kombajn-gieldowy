import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
        except: return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
    return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"

st.set_page_config(page_title="AI ALPHA GOLDEN v40 MAXI", page_icon="🚜", layout="wide")

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. STYLE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .top-tile { text-align: center; padding: 15px; border-radius: 15px; background: #0d1117; min-height: 380px; position: relative; }
    .sig-buy { color: #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px; border-radius: 5px; }
    .sig-sell { color: #ff4b4b; font-weight: bold; border: 2px solid #ff4b4b; padding: 5px; border-radius: 5px; }
    .ai-box { padding: 10px; border-radius: 8px; margin-top: 10px; font-size: 0.8rem; background: rgba(255,255,255,0.05); }
    .news-box { font-size: 0.7rem; color: #8b949e; text-align: left; margin-top: 10px; border-top: 1px solid #30363d; padding-top: 5px; }
    .pos-calc { background: rgba(88, 166, 255, 0.1); border-radius: 5px; padding: 5px; margin: 10px 0; color: #58a6ff; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol, api_key=None):
    try:
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        df = t.history(period="250d")
        
        if df.empty or len(df) < 200: return None
        
        price = float(df['Close'].iloc[-1])
        
        # Wskaźniki
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
        
        risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_dist = atr * 1.5
        shares = int(risk_val / sl_dist) if sl_dist > 0 else 0
        
        # Newsy (Info z rynku)
        news_list = []
        try:
            raw_news = t.news[:2]
            for n in raw_news: news_list.append(n.get('title')[:50] + "...")
        except: news_list = ["Brak nowych wiadomości"]

        # Sygnał
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        # AI
        ai_comment = "Brak klucza AI"
        if api_key:
            try:
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": f"Analiza: {symbol}, Cena: {price}, RSI: {rsi}. 1 krótkie zdanie."}],
                    max_tokens=25
                )
                ai_comment = resp.choices.message.content
            except: ai_comment = "AI Offline"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "pivot": pivot, "verd": verd, "vcl": vcl, "v_type": v_type, "shares": shares,
            "sl": price - sl_dist, "tp": price + (atr * 3), "ai": ai_comment, "news": news_list, "df": df.tail(40)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN MAXI v40")
    api_key = st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
    ticker_area = st.text_area("Symbole:", value=load_tickers(), height=150)
    if st.button("💾 AKTUALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.rerun()
    refresh_rate = st.select_slider("Auto-refresh (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_rate * 1000, key="v40_refresh")

# --- 5. WIDOK GŁÓWNY ---
tickers = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=60)
def fetch_all(t_list, key):
    with ThreadPoolExecutor(max_workers=5) as ex:
        return [r for r in ex.map(lambda x: get_analysis(x, key), t_list) if r is not None]

data_ready = fetch_all(tickers, api_key)

if data_ready:
    st.subheader("🚀 TERMINAL ALPHA MAXI")
    for i in range(0, len(data_ready), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                border_color = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                    <div class="top-tile" style="border: 1px solid {border_color};">
                        <b style="font-size:1.3rem;">{d['symbol']}</b><br>
                        <span style="color:#58a6ff; font-size:1.1rem;">{d['price']:.2f} PLN</span><br>
                        <div style="margin: 10px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                        <div class="pos-calc">KUP: {d['shares']} szt.</div>
                        <div style="font-size:0.75rem; color:#8b949e; line-height:1.4;">
                            SMA50: {d['sma50']:.2f}<br>
                            SMA200: {d['sma200']:.2f}<br>
                            PIVOT: {d['pivot']:.2f} | RSI: {d['rsi']:.0f}
                        </div>
                        <div class="ai-box" style="color:{border_color};"><b>AI:</b> {d['ai']}</div>
                        <div class="news-box">
                            <b>INFO:</b><br>
                            • {d['news'][0] if len(d['news'])>0 else ""}<br>
                            • {d['news'][1] if len(d['news'])>1 else ""}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                with st.expander("Wykres"):
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Błąd pobierania danych. Sprawdź symbole (np. PKO.WA) lub klucz API.")
