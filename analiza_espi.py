import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA UI ---
st.set_page_config(page_title="AI ALPHA GOLDEN v17.5", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; min-height: 160px; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    .tp-target { color: #238636; font-weight: bold; border: 1px solid #238636; padding: 3px 8px; border-radius: 5px; }
    .sl-stop { color: #da3633; font-weight: bold; border: 1px solid #da3633; padding: 3px 8px; border-radius: 5px; }
    .pivot-val { color: #f1c40f; font-weight: bold; }
    .bid-val { color: #da3633; font-weight: bold; }
    .ask-val { color: #238636; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK ANALITYCZNY ---
def get_full_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        d_long = t.history(period="1y", interval="1d")
        d_10m = t.history(period="2d", interval="15m") 
        if d_long.empty or d_10m.empty: return None

        price = d_10m['Close'].iloc[-1]
        
        # PIVOTY
        yest = d_long.iloc[-2]
        h, l, c = yest['High'], yest['Low'], yest['Close']
        p = (h + l + c) / 3
        r1, s1 = (2 * p) - l, (2 * p) - h
        r2, s2 = p + (h - l), p - (h - l)
        r3, s3 = h + 2 * (p - l), l - 2 * (h - p)

        # ŚREDNIE I RSI
        sma50 = d_long['Close'].rolling(50).mean().iloc[-1]
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        # ANALIZA 10 ŚWIEC
        last_10 = d_10m.tail(11).head(10)
        bulls = len(last_10[last_10['Close'] > last_10['Open']])
        bias = "BYCZY" if bulls > 5 else "NIEDŹWIEDZI"
        
        # BID/ASK
        info = t.info
        bid = info.get('bid') or price * 0.999
        ask = info.get('ask') or price * 1.001

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "p": p, "r1": r1, "s1": s1, "r2": r2, "s2": s2, "r3": r3, "s3": s3,
            "sma50": sma50, "sma200": sma200, "bulls": bulls, "bias": bias,
            "change": ((price - c) / c) * 100, "df": d_10m.tail(30)
        }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 v17.5 KOMBAJN")
    # Pobieranie klucza z secrets
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key (jeśli brak w secrets)", type="password")
    t_input = st.text_area("Lista Symboli", "PKO.WA, ALE.WA, CDR.WA, NVDA, TSLA, BTC-USD, ETH-USD, AAPL, MSFT, META", height=150)
    refresh = st.slider("Odśwież (s)", 30, 300, 60)
st_autorefresh(interval=refresh * 1000, key="sync_kombajn")

# --- 4. RENDEROWANIE ---
symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]
with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in list(executor.map(get_full_analysis, symbols)) if r]

if results:
    # --- GWARANTOWANE TOP 10 (2 RZĘDY PO 5) ---
    st.subheader("📊 SZYBKI PODGLĄD SYGNAŁÓW (TOP 10)")
    for row in [0, 5]:
        cols = st.columns(5)
        for i in range(5):
            idx = row + i
            if idx < len(results):
                d = results[idx]
                with cols[i]:
                    st.markdown(f"""
                        <div class="top-tile">
                            <small>{d['symbol']}</small><br>
                            <b style="font-size:1.1rem;">{d['price']:.2f}</b><br>
                            <span class="bid-val">B:{d['bid']:.2f}</span> | <span class="ask-val">A:{d['ask']:.2f}</span><br>
                            <small>RSI: {d['rsi']:.1f}</small><br>
                            <span class="pivot-val">Pivot: {d['p']:.2f}</span>
                        </div>
                    """, unsafe_allow_html=True)

    # --- KARTY TOTALNEJ ANALIZY ---
    for d in results:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1.5])
        
        with c1:
            st.markdown(f"### {d['symbol']}")
            st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"""
                <div class="metric-row"><span>BID / ASK</span><b><span class="bid-val">{d['bid']:.2f}</span> / <span class="ask-val">{d['ask']:.2f}</span></b></div>
                <div class="metric-row"><span>SMA 50 / 200</span><b>{d['sma50']:.1f} / {d['sma200']:.1f}</b></div>
                <div class="metric-row"><span>10ś Bias (Wzrosty)</span><b>{d['bias']} ({d['bulls']}/10)</b></div>
                <div style="margin-top:20px; display: flex; gap: 10px;">
                    <span class="tp-target">TP: {(d['price']*1.05):.2f}</span>
                    <span class="sl-stop">SL: {(d['price']*0.97):.2f}</span>
                </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown("**STRATEGIA PIVOT**")
            st.markdown(f"""
                <div class="metric-row"><span>Resistance 2</span><b>{d['r2']:.2f}</b></div>
                <div class="metric-row"><span>Resistance 1</span><b>{d['r1']:.2f}</b></div>
                <div class="metric-row"><span>PIVOT POINT</span><b class="pivot-val">{d['p']:.2f}</b></div>
                <div class="metric-row"><span>Support 1</span><b>{d['s1']:.2f}</b></div>
                <div class="metric-row"><span>Support 2</span><b>{d['s2']:.2f}</b></div>
            """, unsafe_allow_html=True)
            if api_key and st.button(f"🧠 DECYZJA AI", key=f"ai_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = f"Analiza {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['p']:.2f}, Bias: {d['bias']}. Podaj: 1. DECYZJA, 2. TP/SL, 3. RYZYKO."
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Tylko komendy handlowe. Zero lania wody."}, {"role": "user", "content": prompt}])
                st.info(res.choices.message[0].content if hasattr(res.choices[0], 'message') else res.choices[0].message.content)

        with c3:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['p'], line_dash="dash", line_color="yellow", annotation_text="Pivot")
            fig.update_layout(height=300, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
