import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.6", page_icon="📈", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #1c2128; padding: 10px; border-radius: 8px; border: 1px solid #444c56; text-align: center; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieranie danych: 1h do wykresu i 1d do Pivotów
        d1h = yf.download(symbol, period="5d", interval="1h", progress=False)
        d1d = yf.download(symbol, period="5d", interval="1d", progress=False)
        
        if d1h.empty or d1d.empty: return None
        
        # Naprawa struktury kolumn (YFinance MultiIndex fix)
        for df in [d1h, d1d]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        
        current_price = float(d1h['Close'].iloc[-1])
        # Symulacja Bid/Ask
        bid = current_price * 0.9998
        ask = current_price * 1.0002
        
        # Pivot Points (z ostatniej pełnej sesji dziennej)
        h, l, c = d1d['High'].iloc[-2], d1d['Low'].iloc[-2], d1d['Close'].iloc[-2]
        pivot = (h + l + c) / 3
        r1 = (2 * pivot) - l
        s1 = (2 * pivot) - h

        # RSI 1h
        delta = d1h['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        # Trend (SMA 200 na 1h jako przybliżenie trendu)
        sma = d1h['Close'].rolling(20).mean().iloc[-1]
        trend = "Wzrostowy 🚀" if current_price > sma else "Spadkowy 📉"
        t_col = "#00ff88" if current_price > sma else "#ff4b4b"

        return {
            "symbol": symbol, "price": current_price, "bid": bid, "ask": ask,
            "rsi": rsi, "pivot": pivot, "r1": r1, "s1": s1,
            "trend": trend, "t_col": t_col, "df": d1h
        }
    except:
        return None

# --- 4. BOCZNY PANEL ---
with st.sidebar:
    st.title("🚀 KOMB_v12.6")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    
    tickers_input = st.text_area("Symbole", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    
    refresh_sec = st.slider("Odświeżanie (s)", 30, 300, 60)

st_autorefresh(interval=refresh_sec * 1000, key="auto_refresh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
results = []

for t in tickers:
    data = get_analysis(t)
    if data: results.append(data)

if results:
    # Sekcja TOP 10 (Ranking RSI)
    st.subheader("📊 TOP 10 - Skaner Okazji (RSI 1h)")
    sorted_res = sorted(results, key=lambda x: x['rsi'])
    top_cols = st.columns(min(len(results), 5))
    
    for i, res in enumerate(sorted_res[:5]):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-rank-card">
                    <b>{res['symbol']}</b><br>
                    <span style="font-size:1.1rem;">{res['price']:.2f}</span><br>
                    <span style="color:{res['t_col']}; font-size:0.7rem;">{res['trend']}</span><br>
                    <span class="stat-label">RSI: {res['rsi']:.1f}</span>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Detale każdego symbolu
    for res in results:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                st.subheader(res['symbol'])
                st.write(f"**Cena:** {res['price']:.2f}")
                st.markdown(f"<span style='color:gray; font-size:0.8rem;'>BID: {res['bid']:.4f} | ASK: {res['ask']:.4f}</span>", unsafe_allow_html=True)
                st.write(f"**RSI 1h:** {res['rsi']:.1f}")
                st.write(f"**Trend:** {res['trend']}")
                
                with st.expander("Punkty Pivot"):
                    st.write(f"Opór R1: {res['r1']:.2f}")
                    st.write(f"**Pivot: {res['pivot']:.2f}**")
                    st.write(f"Wsparcie S1: {res['s1']:.2f}")

            with col2:
                fig = go.Figure(data=[go.Candlestick(
                    x=res['df'].index[-40:],
                    open=res['df']['Open'][-40:],
                    high=res['df']['High'][-40:],
                    low=res['df']['Low'][-40:],
                    close=res['df']['Close'][-40:]
                )])
                fig.add_hline(y=res['pivot'], line_dash="dash", line_color="orange")
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

            with col3:
                st.write("**AI ANALYST**")
                if api_key and st.button(f"Skanuj {res['symbol']}", key=f"ai_{res['symbol']}"):
                    try:
                        client = OpenAI(api_key=api_key)
                        prompt = f"Analiza {res['symbol']}: Cena {res['price']}, RSI {res['rsi']:.1f}, Pivot {res['pivot']:.2f}. Co robić?"
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        st.info(response.choices[0].message.content)
                    except Exception as e:
                        st.error("Błąd API OpenAI")
                elif not api_key:
                    st.warning("Brak klucza API")

            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj symbole w panelu bocznym (np. BTC-USD), aby rozpocząć.")
