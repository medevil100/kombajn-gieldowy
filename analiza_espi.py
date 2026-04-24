import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.5", page_icon="📈", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "PKO.WA, BTC-USD, NVDA, TSLA, EURPLN=X"
    return "PKO.WA, BTC-USD, NVDA, TSLA, EURPLN=X"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #1c2128; padding: 10px; border-radius: 8px; border: 1px solid #444c56; text-align: center; min-height: 150px; }
    .bid-ask { font-family: monospace; font-size: 0.85rem; color: #8b949e; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        # Pobieranie danych 1h i 1d
        d1h = yf.download(symbol, period="10d", interval="1h", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if d1h.empty or d1d.empty: return None
        
        # Spłaszczanie MultiIndex jeśli występuje
        for df in [d1h, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d1h['Close'].iloc[-1])
        # Symulacja Bid/Ask (yfinance nie daje real-time L2, stosujemy spread 0.02%)
        bid = price * 0.9999
        ask = price * 1.0001
        
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        
        # Klasyczne punkty Pivot (Standard) z danych dziennych
        high_p = d1d['High'].iloc[-2]
        low_p = d1d['Low'].iloc[-2]
        close_p = d1d['Close'].iloc[-2]
        
        pivot = (high_p + low_p + close_p) / 3
        r1 = 2 * pivot - low_p
        s1 = 2 * pivot - high_p
        
        # Analiza techniczna 1h
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#00ff88" if price > sma200 else "#ff4b4b"
        
        # RSI 1h
        delta = d1h['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Werdykt
        if rsi < 30: rec, rec_col = "MOCNE KUPUJ", "#238636"
        elif rsi > 70: rec, rec_col = "MOCNE SPRZEDAJ", "#da3633"
        else: rec, rec_col = "NEUTRALNY", "#8b949e"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "change": change_pct, 
            "rsi": rsi, "rec": rec, "rec_col": rec_col, "trend": trend_label, 
            "trend_col": trend_color, "pivot": pivot, "r1": r1, "s1": s1,
            "tp": price * 1.05, "sl": price * 0.97, "df": d1h
        }
    except Exception as e:
        return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ KOMB_v12.5")
    api_key = st.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
    
    tickers_input = st.text_area("Symbole (np. BTC-USD, NVDA)", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    
    refresh = st.select_slider("Auto-odświeżanie (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. GŁÓWNA LOGIKA ---
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
data_list = []

for t in tickers:
    res = get_analysis(t)
    if res: data_list.append(res)

if data_list:
    # --- SEKKCJA TOP 10 ---
    st.subheader("🏆 RANKING TOP 10 (Skaner RSI 1h)")
    # Sortowanie po RSI (najbardziej wyprzedane i wykupione)
    sorted_data = sorted(data_list, key=lambda x: x['rsi'])
    top_items = sorted_data[:5] + sorted_data[-5:] # 5 najniższych i 5 najwyższych RSI
    
    top_cols = st.columns(5)
    for i, d in enumerate(top_items[:10]):
        with top_cols[i % 5]:
            st.markdown(f"""
                <div class="top-rank-card">
                    <div style="font-size:1.1rem; font-weight:bold;">{d['symbol']}</div>
                    <div style="color:{d['trend_col']}; font-size:0.8rem;">{d['trend']}</div>
                    <div style="font-size:1.2rem; margin:5px 0;">{d['price']:.2f}</div>
                    <div style="background:{d['rec_col']}; color:white; border-radius:4px; font-size:0.7rem; padding:2px;">{d['rec']}</div>
                    <div class="stat-label" style="margin-top:5px;">RSI: {d['rsi']:.1f}</div>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in data_list:
        with st.container():
            st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.2, 2.5, 1])
            
            with c1:
                st.markdown(f"### {d['symbol']}")
                st.markdown(f"<span class='bid-ask'>BID: {d['bid']:.4f} | ASK: {d['ask']:.4f}</span>", unsafe_allow_html=True)
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                
                st.markdown(f"**Trend:** <span style='color:{d['trend_col']}'>{d['trend']}</span>", unsafe_allow_html=True)
                st.write(f"**RSI (1h):** {d['rsi']:.1f}")
                
                with st.expander("📍 Poziomy Pivot"):
                    st.write(f"Resistance R1: {d['r1']:.2f}")
                    st.write(f"**Pivot Point: {d['pivot']:.2f}**")
                    st.write(f"Support S1: {d['s1']:.2f}")

            with c2:
                # Wykres świecowy 1h
                fig = go.Figure(data=[go.Candlestick(
                    x=d['df'].index[-48:], # Ostatnie 48 świec 1h
                    open=d['df']['Open'][-48:],
                    high=d['df']['High'][-48:],
                    low=d['df']['Low'][-48:],
                    close=d['df']['Close'][-48:],
                    name="H1"
                )])
                # Linie Pivot
                fig.add_hline(y=d['pivot'], line_dash="dash", line_color="orange", annotation_text="P")
                fig.add_hline(y=d['r1'], line_dash="dot", line_color="red", annotation_text="R1")
                fig.add_hline(y=d['s1'], line_dash="dot", line_color="green", annotation_text="S1")
                
                fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

            with c3:
                st.markdown("**Sygnały AI**")
                st.write(f"Target (TP): {d['tp']:.2f}")
                st.write(f"Stop Loss (SL): {d['sl']:.2f}")
                
                if api_key and st.button(f"Analiza GPT", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = f"Analiza techniczna {d['symbol']}: Cena {d['price']}, RSI 1h: {d['rsi']:.1f}, Pivot: {d['pivot']:.2f}. Trend: {d['trend']}. Podaj krótki werdykt buy/sell i ryzyko."
                    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.info(response.choices[0].message.content)

            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.error("Nie udało się pobrać danych. Sprawdź symbole lub połączenie internetowe.")

# Stopka
st.caption("Dane: Yahoo Finance (Interval: 1h). Algorytm: Standard Pivot Points.")
