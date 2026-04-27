import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime

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

st.set_page_config(page_title="AI ALPHA GOLDEN v40.1 FIX", page_icon="🚜", layout="wide")

if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. STYLE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .top-tile { text-align: center; padding: 15px; border-radius: 15px; background: #0d1117; min-height: 400px; border: 1px solid #30363d; }
    .sig-buy { color: #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 3px 8px; border-radius: 5px; background: rgba(0,255,136,0.1); }
    .sig-sell { color: #ff4b4b; font-weight: bold; border: 1px solid #ff4b4b; padding: 3px 8px; border-radius: 5px; background: rgba(255,75,75,0.1); }
    .ai-box { padding: 10px; border-radius: 8px; margin-top: 10px; font-size: 0.8rem; background: rgba(255,255,255,0.05); min-height: 50px; }
    .news-box { font-size: 0.7rem; color: #8b949e; text-align: left; margin-top: 10px; border-top: 1px solid #30363d; padding-top: 5px; }
    .pos-calc { background: rgba(88, 166, 255, 0.1); border-radius: 5px; padding: 8px; margin: 10px 0; color: #58a6ff; font-weight: bold; font-size: 1.1rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol, api_key=None):
    try:
        symbol = symbol.strip().upper()
        # Stabilniejsze pobieranie historii
        df = yf.download(symbol, period="250d", interval="1d", progress=False, group_by='ticker')
        
        if isinstance(df.columns, pd.MultiIndex):
            df = df[symbol] if symbol in df.columns.levels[0] else df.iloc[:, :6]
            
        if df.empty or len(df) < 50: return None
        
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
        
        # Newsy (Osobny try-except)
        news_list = []
        try:
            t_obj = yf.Ticker(symbol)
            raw_news = t_obj.news[:2]
            for n in raw_news: news_list.append(n.get('title')[:45] + "...")
        except: news_list = ["Brak info rynkowego"]

        # Sygnał
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        # AI
        ai_comment = "Brak klucza"
        if api_key and len(api_key) > 10:
            try:
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": f"Analiza: {symbol}, RSI: {rsi:.0f}, Trend: {'Wzrost' if price > sma200 else 'Spadek'}. Podaj 1 zdanie opinii."}],
                    max_tokens=25
                )
                ai_comment = resp.choices.message.content
            except: ai_comment = "AI Busy"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "pivot": pivot, "verd": verd, "vcl": vcl, "v_type": v_type, "shares": shares,
            "sl": price - sl_dist, "tp": price + (atr * 3), "ai": ai_comment, "news": news_list, "df": df.tail(40)
        }
    except Exception as e:
        print(f"Error for {symbol}: {e}")
        return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 ALPHA FIX v40.1")
    api_key = st.text_input("OpenAI Key", type="password")
    st.session_state.risk_cap = st.number_input("Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko (%)", 0.1, 5.0, st.session_state.risk_pct)
    ticker_area = st.text_area("Symbole (przecinek):", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.rerun()
    refresh_rate = st.select_slider("Odświeżanie (s)", options=, value=60)

st_autorefresh(interval=refresh_rate * 1000, key="v401_refresh")

# --- 5. WIDOK GŁÓWNY ---
tickers = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=60)
def get_results(t_list, key):
    results = []
    for t in t_list:
        res = get_analysis(t, key)
        if res: results.append(res)
    return results

data_ready = get_results(tickers, api_key)

if data_ready:
    st.subheader("🚀 TERMINAL ALPHA GOLDEN (PLN)")
    for i in range(0, len(data_ready), 5):
        cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with cols[idx]:
                border_color = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                    <div class="top-tile" style="border: 2px solid {border_color};">
                        <b style="font-size:1.4rem;">{d['symbol']}</b><br>
                        <span style="color:#58a6ff; font-size:1.2rem;">{d['price']:.2f} PLN</span><br>
                        <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                        <div class="pos-calc">KUP: {d['shares']} szt.</div>
                        <div style="font-size:0.75rem; color:#8b949e; line-height:1.5; text-align: left;">
                            <b>SMA50:</b> {d['sma50']:.2f}<br>
                            <b>SMA200:</b> {d['sma200']:.2f}<br>
                            <b>PIVOT:</b> {d['pivot']:.2f}<br>
                            <b>RSI:</b> {d['rsi']:.0f}
                        </div>
                        <div class="ai-box"><b>AI:</b> {d['ai']}</div>
                        <div class="news-box">
                            <b>NEWS:</b><br>
                            • {d['news'][0] if len(d['news'])>0 else "---"}<br>
                            • {d['news'][1] if len(d['news'])>1 else "---"}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                with st.expander("Wykres i Poziomy"):
                    st.write(f"SL: {d['sl']:.2f} | TP: {d['tp']:.2f}")
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=200, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Błąd pobierania. 1. Sprawdź czy symbole mają .WA (np. KGH.WA). 2. Sprawdź internet. 3. Yahoo może tymczasowo blokować Twój adres IP.")

st.markdown(f"<p style='text-align:center; color:gray; font-size:0.8rem;'>v40.1 | Ostatnie odświeżenie: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)
