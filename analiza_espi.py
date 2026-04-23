import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.5", page_icon="🚀", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "BTC-USD, NVDA, TSLA, PKO.WA"
    return "BTC-USD, NVDA, TSLA, PKO.WA"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .ticker-card { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 20px; }
    .top-rank-card { background: #0d1117; padding: 12px; border-radius: 10px; border: 1px solid #30363d; text-align: center; }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .orderbook-box { background: #010409; padding: 8px; border-radius: 5px; border: 1px solid #30363d; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def get_analysis(symbol):
    try:
        t_obj = yf.Ticker(symbol)
        inf = t_obj.info
        
        # Pobieranie danych Bid/Ask/Spread
        bid = inf.get('bid', 0)
        ask = inf.get('ask', 0)
        spread = ask - bid if (ask and bid) else 0
        spread_pct = (spread / bid * 100) if (bid > 0) else 0

        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        
        if d15.empty or d1d.empty: return None
        
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        
        # Techniczne
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
        
        if rsi < 32: rec, rec_col = "KUPUJ", "#238636"
        elif rsi > 68: rec, rec_col = "SPRZEDAJ", "#da3633"
        else: rec, rec_col = "CZEKAJ", "#8b949e"

        return {
            "symbol": symbol, "price": price, "change": change_pct, "rsi": rsi, 
            "rec": rec, "rec_col": rec_col, "trend": trend_label, "trend_col": trend_color,
            "pivot": pivot, "tp": price + (atr * 1.5), "sl": price - (atr * 1.2), "df": d15,
            "bid": bid, "ask": ask, "spread": spread, "spread_pct": spread_pct
        }
    except Exception as e:
        return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ KOMB_v12.5")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    if not api_key:
        st.warning("Brak klucza OpenAI!")

    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f: f.write(tickers_input)
    
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. GŁÓWNA LOGIKA ---
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
data_list = []

progress_bar = st.progress(0)
for idx, t in enumerate(tickers):
    res = get_analysis(t)
    if res: data_list.append(res)
    progress_bar.progress((idx + 1) / len(tickers))
progress_bar.empty()

if data_list:
    # --- TOP DASHBOARD ---
    st.subheader("📊 RANKING RSI (OKAZJE)")
    top_cols = st.columns(5)
    sorted_top = sorted(data_list, key=lambda x: x['rsi'])
    
    for i, d in enumerate(sorted_top[:10]):
        with top_cols[i % 5]:
            c_col = "#00ff88" if d['change'] >= 0 else "#ff4b4b"
            st.markdown(f"""
                <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                    <small>{d['symbol']}</small><br>
                    <b style="color:{c_col}; font-size:1.1rem;">{d['price']:.2f}</b><br>
                    <div style="background:{d['rec_col']}; font-size:0.7rem; border-radius:3px; margin:5px 0; color:white;">{d['rec']}</div>
                    <span class="stat-label">RSI: {d['rsi']:.1f}</span>
                </div>
            """, unsafe_allow_html=True)

    # --- LISTA SZCZEGÓŁOWA ---
    for d in data_list:
        st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown(f"### {d['symbol']} <span style='font-size:0.8rem; color:{d['trend_col']}'>{d['trend']}</span>", unsafe_allow_html=True)
            st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            
            # --- SEKCJA BID/ASK / SPREAD ---
            st.markdown(f"""
                <div class="orderbook-box">
                    <table style="width:100%; font-size:0.85rem;">
                        <tr>
                            <td style="color:#00ff88;">BID: <b>{d['bid'] if d['bid'] > 0 else '-'}</b></td>
                            <td style="color:#ff4b4b; text-align:right;">ASK: <b>{d['ask'] if d['ask'] > 0 else '-'}</b></td>
                        </tr>
                        <tr>
                            <td colspan="2" style="text-align:center; color:#8b949e; font-size:0.7rem; border-top:1px solid #30363d; padding-top:5px;">
                                SPREAD: {d['spread']:.4f} ({d['spread_pct']:.3f}%)
                            </td>
                        </tr>
                    </table>
                </div>
            """, unsafe_allow_html=True)

            st.write(f"**Pivot:** {d['pivot']:.2f} | **RSI:** {d['rsi']:.1f}")
            st.write(f"🎯 **TP:** {d['tp']:.2f} | 🛡️ **SL:** {d['sl']:.2f}")
            
            if api_key and st.button(f"🧠 ANALIZA AI {d['symbol']}", key=f"btn_{d['symbol']}"):
                client = OpenAI(api_key=api_key)
                prompt = f"Jako agresywny trader oceń: {d['symbol']}, Cena: {d['price']}, Spread: {d['spread_pct']:.3f}%, RSI: {d['rsi']:.1f}. Pivot: {d['pivot']:.2f}. Podaj konkretny werdykt i ryzyko 1-10."
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                st.info(resp.choices[0].message.content)
        
        with c2:
            fig = go.Figure(data=[go.Candlestick(
                x=d['df'].index[-60:], open=d['df']['Open'][-60:], 
                high=d['df']['High'][-60:], low=d['df']['Low'][-60:], 
                close=d['df']['Close'][-60:], name="Cena"
            )])
            fig.add_hline(y=d['pivot'], line_dash="dot", line_color="orange", annotation_text="PIVOT")
            fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Nie znaleziono danych dla podanych tickerów.")

# Stopka
st.caption("Alpha Superkombajn v12.5 | Dane: Yahoo Finance | AI: GPT-4o")
