import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I PLIK BAZY ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            f.write("NVDA, TSLA, BTC-USD, GC=F")
        return "NVDA, TSLA, BTC-USD, GC=F"
    with open(DB_FILE, "r") as f:
        content = f.read().strip()
        return content if content else "NVDA, TSLA, BTC-USD, GC=F"

st.set_page_config(page_title="AI ALPHA GOLDEN v34", page_icon="🚜", layout="wide")

if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. STYLE WIZUALNE ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .ticker-card { background: #0d1117; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px; }
    .top-tile-buy { border: 1px solid #00ff88; box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.2); text-align: center; padding: 15px; border-radius: 12px; }
    .top-tile-sell { border: 1px solid #ff4b4b; box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.2); text-align: center; padding: 15px; border-radius: 12px; }
    .top-tile-neutral { border: 1px solid #30363d; text-align: center; padding: 15px; border-radius: 12px; }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: monospace; font-size: 1.2rem; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: monospace; font-size: 1.2rem; }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        if not symbol: return None
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        # Próba pobrania Bid/Ask, jeśli brak to symulacja
        info = t.info
        bid = info.get('bid') or info.get('regularMarketPrice', price) * 0.9998
        ask = info.get('ask') or info.get('regularMarketPrice', price) * 1.0002
        
        # Matematyka techniczna
        y_high, y_low = d1['High'].max(), d1['Low'].min()
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        
        # RSI
        delta = h1['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        vol_ratio = h1['Volume'].iloc[-1] / (h1['Volume'].rolling(20).mean().iloc[-1] + 1)
        
        trend = "BULL 📈" if price > sma200 else "BEAR 📉"
        
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp, "spread": ask-bid,
            "tp": price + (atr * 1.7), "sl": price - (atr * 1.2),
            "y_high": y_high, "y_low": y_low, "vol_ratio": vol_ratio, 
            "trend": trend, "df": h1
        }
    except Exception as e:
        return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v34")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    # Ładowanie domyślnej listy do pola tekstowego
    if 'ticker_list' not in st.session_state:
        st.session_state.ticker_list = load_tickers()
    
    ticker_text = st.text_area("Lista Symboli:", value=st.session_state.ticker_list, height=150)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_text)
        st.session_state.ticker_list = ticker_text
        st.rerun()
        
    refresh_sec = st.select_slider("Refresh (s)", options=[30, 60, 300, 600], value=60)

st_autorefresh(interval=refresh_sec * 1000, key="v34_fsh")

# --- 5. LOGIKA GŁÓWNA ---
# Parsowanie symboli (przecinki, nowe linie)
current_tickers = [x.strip().upper() for x in ticker_text.replace('\n', ',').split(',') if x.strip()]

if current_tickers:
    with ThreadPoolExecutor(max_workers=10) as ex:
        all_data = [d for d in list(ex.map(get_analysis, current_tickers)) if d is not None]

    if all_data:
        # TOP 10 WIDGETS
        st.subheader("🏆 TOP SIGNALS")
        t_cols = st.columns(min(len(all_data), 5))
        for i, d in enumerate(all_data[:10]):
            with t_cols[i % 5]:
                st.markdown(f"""
                    <div class="top-tile-{d['v_type']}">
                        <b>{d['symbol']}</b><br>
                        <span style="font-size:1.1rem; color:#58a6ff;">{d['price']:.2f}</span><br>
                        <div class="bid-box" style="font-size:0.9rem;">B: {d['bid']:.2f}</div>
                        <div class="ask-box" style="font-size:0.9rem;">A: {d['ask']:.2f}</div>
                        <div class="{d['vcl']}">{d['verd']}</div>
                    </div>
                """, unsafe_allow_html=True)

        st.divider()

        # SZCZEGÓŁOWA LISTA
        for d in all_data:
            with st.container():
                st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns([1.2, 2, 1.4])
                
                with c1:
                    st.markdown(f"<h3 class='{d['vcl']}'>{d['symbol']} | {d['verd']}</h3>", unsafe_allow_html=True)
                    st.metric("CENA", f"{d['price']:.4f}")
                    st.markdown(f"""
                        🔵 Pivot: <b>{d['pp']:.2f}</b><br>
                        🟢 TP: <b style="color:#00ff88;">{d['tp']:.2f}</b><br>
                        🔴 SL: <b style="color:#ff4b4b;">{d['sl']:.2f}</b><br>
                        📊 Trend: <b>{d['trend']}</b><br>
                        📏 Szczyt/Dołek: <small>{d['y_high']:.2f} / {d['y_low']:.2f}</small>
                    """, unsafe_allow_html=True)
                
                with c2:
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-45:], open=d['df']['Open'][-45:], high=d['df']['High'][-45:], low=d['df']['Low'][-45:], close=d['df']['Close'][-45:])])
                    fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")
                
                with c3:
                    st.markdown(f"""
                        <div style="background: #161b22; padding: 15px; border-radius: 12px; border: 1px solid #30363d;">
                            <span style="color:#ff4b4b; font-size:0.8rem;">BID (SPRZEDAJ)</span><br><span class="bid-box">{d['bid']:.4f}</span><br>
                            <span style="color:#00ff88; font-size:0.8rem; margin-top:10px; display:block;">ASK (KUP)</span><span class="ask-box">{d['ask']:.4f}</span><br>
                            <div style="border-top:1px solid #333; margin-top:12px; padding-top:8px;">
                                <span style="color:#58a6ff;">Spread: <b>{d['spread']:.4f}</b></span><br>
                                <span style="color:#f1e05a;">Vol Ratio: <b>x{d['vol_ratio']:.2f}</b></span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"🧠 ANALIZA PRO AI", key=f"ai_{d['symbol']}"):
                        if not api_key: st.error("Wklej klucz API!")
                        else:
                            client = OpenAI(api_key=api_key)
                            prompt = (f"Jako PRO trader przeanalizuj {d['symbol']}. Cena: {d['price']}. "
                                      f"RSI: {d['rsi']:.1f}, Trend: {d['trend']}, Vol: x{d['vol_ratio']:.2f}. "
                                      f"Pivot: {d['pp']:.2f}, High/Low: {d['y_high']:.2f}/{d['y_low']:.2f}. "
                                      f"Podaj: 1. Sentyment, 2. Relację do szczytów, 3. Konkretny plan (Entry, TP, SL). Bez lania wody.")
                            
                            res = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "system", "content": "Jesteś analitykiem technicznym. Tylko fakty i liczby. Punkty."},
                                          {"role": "user", "content": prompt}]
                            )
                            st.session_state.ai_cache[d['symbol']] = res.choices[0].message.content
                    
                    if d['symbol'] in st.session_state.ai_cache:
                        st.info(st.session_state.ai_cache[d['symbol']])
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.error("Błąd pobierania danych. Sprawdź czy symbole są poprawne (np. AAPL, BTC-USD).")
else:
    st.info("Lista symboli jest pusta. Dodaj je w panelu bocznym.")

st.caption("AI Alpha Golden v34 | Hybrid Logic | Real-time Data")
