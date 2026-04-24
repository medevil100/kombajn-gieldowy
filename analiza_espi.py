import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA UI I STYLIZACJA ---
st.set_page_config(page_title="AI ALPHA GOLDEN v18.0 TOTAL KOMBAJN", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .top-tile { background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; min-height: 180px; }
    .ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; }
    .tp-target { color: #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 4px 10px; border-radius: 5px; background: rgba(0,255,136,0.1); }
    .sl-stop { color: #ff4b4b; font-weight: bold; border: 1px solid #ff4b4b; padding: 4px 10px; border-radius: 5px; background: rgba(255,75,75,0.1); }
    .pivot-val { color: #f1c40f; font-weight: bold; }
    .bid-val { color: #ff4b4b; font-weight: bold; }
    .ask-val { color: #00ff88; font-weight: bold; }
    .candle-bias { color: #f1c40f; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SILNIK ANALITYCZNY (GŁĘBOKA ANALIZA) ---
def get_total_analysis(symbol):
    try:
        t = yf.Ticker(symbol)
        # Pobieramy dane 1d dla Pivotów i Średnich
        d_long = t.history(period="1y", interval="1d")
        # Pobieramy dane 15m dla analizy ostatnich 10 świec
        d_short = t.history(period="5d", interval="15m") 
        
        if d_long.empty or d_short.empty: return None

        price = d_short['Close'].iloc[-1]
        
        # PIVOTY (S/R 1-3)
        yest = d_long.iloc[-2]
        h, l, c = yest['High'], yest['Low'], yest['Close']
        p = (h + l + c) / 3
        r1, s1 = (2 * p) - l, (2 * p) - h
        r2, s2 = p + (h - l), p - (h - l)
        r3, s3 = h + 2 * (p - l), l - 2 * (h - p)

        # ŚREDNIE KROCZĄCE I RSI
        sma50 = d_long['Close'].rolling(50).mean().iloc[-1]
        sma200 = d_long['Close'].rolling(200).mean().iloc[-1]
        
        delta = d_long['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        # ANALIZA 10 OSTATNICH ŚWIEC (BIAS)
        last_10 = d_short.tail(11).head(10)
        bullish_candles = len(last_10[last_10['Close'] > last_10['Open']])
        bias = "BYCZY" if bullish_candles > 5 else "NIEDŹWIEDZI"
        
        # BID / ASK (Fast Info)
        info = t.info
        bid = info.get('bid') or price * 0.9995
        ask = info.get('ask') or price * 1.0005

        # DYNAMICZNE TP / SL (Zmienna zmienność)
        atr = (d_long['High'] - d_long['Low']).rolling(14).mean().iloc[-1]
        tp_price = price + (atr * 2)
        sl_price = price - (atr * 1.5)

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "p": p, "r1": r1, "s1": s1, "r2": r2, "s2": s2, "r3": r3, "s3": s3,
            "sma50": sma50, "sma200": sma200, "bulls": bullish_candles, "bias": bias,
            "tp": tp_price, "sl": sl_price,
            "change": ((price - c) / c) * 100, "df": d_short.tail(40)
        }
    except Exception as e:
        return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🍯 ALPHA GOLDEN v18.0")
    st.info("Totalny Kombajn Giełdowy")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    t_input = st.text_area("Lista Symboli (oddziel przecinkiem)", 
                           "PKO.WA, ALE.WA, CDR.WA, NVDA, TSLA, BTC-USD, ETH-USD, AAPL, MSFT, META", 
                           height=150)
    
    if st.button("💾 ZAPISZ LISTĘ DO PLIKU"):
        with open("tickers_db.txt", "w") as f:
            f.write(t_input)
        st.success("Lista zapisana!")
        
    refresh = st.slider("Częstotliwość odświeżania (s)", 30, 300, 60)

st_autorefresh(interval=refresh * 1000, key="total_sync")

# --- 4. RENDEROWANIE PANELU GŁÓWNEGO ---
symbols = [s.strip().upper() for s in t_input.split(",") if s.strip()]

with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in list(executor.map(get_total_analysis, symbols)) if r]

if results:
    # --- SEKCYJA TOP 10 (GWARANTOWANE 2 RZĘDY PO 5 KAFELKÓW) ---
    st.subheader("📊 DASHBOARD SYGNAŁÓW (TOP 10)")
    top_10 = results[:10]
    
    # Rząd 1
    c1 = st.columns(5)
    for i in range(min(5, len(top_10))):
        d = top_10[i]
        with c1[i]:
            st.markdown(f"""
            <div class="top-tile">
                <small>{d['symbol']}</small><br>
                <b style="font-size:1.3rem;">{d['price']:.2f}</b><br>
                <div style="margin: 5px 0;">
                    <span class="bid-val">B:{d['bid']:.2f}</span> | <span class="ask-val">A:{d['ask']:.2f}</span>
                </div>
                <div class="metric-row"><small>RSI: {d['rsi']:.1f}</small> <small class="pivot-val">P:{d['p']:.2f}</small></div>
                <div style="font-size:0.7rem; font-weight:bold; color:{'#00ff88' if d['bias']=='BYCZY' else '#ff4b4b'}">
                    BIAS: {d['bias']}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Rząd 2
    if len(top_10) > 5:
        c2 = st.columns(5)
        for i in range(5, len(top_10)):
            d = top_10[i]
            with c2[i-5]:
                st.markdown(f"""
                <div class="top-tile">
                    <small>{d['symbol']}</small><br>
                    <b style="font-size:1.3rem;">{d['price']:.2f}</b><br>
                    <div style="margin: 5px 0;">
                        <span class="bid-val">B:{d['bid']:.2f}</span> | <span class="ask-val">A:{d['ask']:.2f}</span>
                    </div>
                    <div class="metric-row"><small>RSI: {d['rsi']:.1f}</small> <small class="pivot-val">P:{d['p']:.2f}</small></div>
                    <div style="font-size:0.7rem; font-weight:bold; color:{'#00ff88' if d['bias']=='BYCZY' else '#ff4b4b'}">
                        BIAS: {d['bias']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # --- LISTA PEŁNEJ ANALIZY (KARTY) ---
    for d in results:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        col_text, col_pivot, col_chart = st.columns([1, 1, 1.8])
        
        with col_text:
            st.markdown(f"## {d['symbol']}")
            st.metric("CENA BIEŻĄCA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.markdown(f"""
                <div class="metric-row"><span>BID / ASK</span><b><span class="bid-val">{d['bid']:.2f}</span> / <span class="ask-val">{d['ask']:.2f}</span></b></div>
                <div class="metric-row"><span>SMA 50 (Średni)</span><b>{d['sma50']:.2f}</b></div>
                <div class="metric-row"><span>SMA 200 (Długi)</span><b>{d['sma200']:.2f}</b></div>
                <div class="metric-row"><span>Nastroje 10ś (15m)</span><b class="candle-bias">{d['bias']} ({d['bulls']}/10)</b></div>
                <div class="metric-row"><span>Wskaźnik RSI</span><b>{d['rsi']:.1f}</b></div>
                <div style="margin-top:20px; display: flex; gap: 15px;">
                    <span class="tp-target">TARGET TP: {d['tp']:.2f}</span>
                    <span class="sl-stop">STOP SL: {d['sl']:.2f}</span>
                </div>
            """, unsafe_allow_html=True)

        with col_pivot:
            st.markdown("### 🎯 POZIOMY PIVOT")
            st.markdown(f"""
                <div class="metric-row"><span>Resistance 2 (R2)</span><b>{d['r2']:.2f}</b></div>
                <div class="metric-row"><span>Resistance 1 (R1)</span><b>{d['r1']:.2f}</b></div>
                <div class="metric-row"><span>GŁÓWNY PIVOT (P)</span><b class="pivot-val">{d['p']:.2f}</b></div>
                <div class="metric-row"><span>Support 1 (S1)</span><b>{d['s1']:.2f}</b></div>
                <div class="metric-row"><span>Support 2 (S2)</span><b>{d['s2']:.2f}</b></div>
                <div class="metric-row"><span>Support 3 (S3)</span><b style="color:#ff4b4b">{d['s3']:.2f}</b></div>
            """, unsafe_allow_html=True)
            
            if api_key:
                if st.button(f"🧠 WYGENERUJ KOMENDĘ AI: {d['symbol']}", key=f"btn_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    p_prompt = f"Analiza {d['symbol']}: Cena {d['price']}, RSI {d['rsi']:.1f}, Pivot {d['p']:.2f}, Bias 10s: {d['bias']}. Podaj konkret: 1. DECYZJA, 2. TP/SL, 3. RYZYKO."
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "system", "content": "Jesteś suchym traderem. Zero lania wody. Same konkrety i liczby."},
                                  {"role": "user", "content": p_prompt}]
                    )
                    st.success(response.choices[0].message.content)

        with col_chart:
            fig = go.Figure(data=[go.Candlestick(
                x=d['df'].index, open=d['df']['Open'], high=d['df']['High'],
                low=d['df']['Low'], close=d['df']['Close'], name="15m Chart"
            )])
            # Dodanie linii Pivot na wykres
            fig.add_hline(y=d['p'], line_dash="dash", line_color="yellow", annotation_text="PIVOT")
            fig.add_hline(y=d['r1'], line_dash="dot", line_color="rgba(255,255,255,0.3)")
            fig.add_hline(y=d['s1'], line_dash="dot", line_color="rgba(255,255,255,0.3)")
            
            fig.update_layout(height=350, margin=dict(l=0,r=0,b=0,t=0), template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Brak danych. Sprawdź czy symbole są poprawne i oddzielone przecinkami.")
