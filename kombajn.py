import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I PAMIĘĆ ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return f.read()
        except: return "NVDA, TSLA, BTC-USD, PKO.WA"
    return "NVDA, TSLA, BTC-USD, PKO.WA"

st.set_page_config(page_title="AI ALPHA GOLDEN v27", page_icon="🚜", layout="wide")

# --- 2. STYLE WIZUALNE ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0f111a, #1a1c2b); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px;
    }
    .top-tile {
        background: #111420; padding: 12px; border-radius: 10px; border-bottom: 3px solid #00ff88; 
        text-align: center; min-height: 200px;
    }
    .metric-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 6px 0; font-size: 0.9rem; }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: monospace; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: monospace; }
    .sig-buy { color: #00ff88; font-weight: bold; }
    .sig-sell { color: #ff4b4b; font-weight: bold; }
    .volume-alert { color: #f1e05a; font-weight: bold; font-size: 0.8rem; border: 1px solid #f1e05a; padding: 2px 5px; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        t = yf.Ticker(symbol)
        
        # Pobieranie danych
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        
        if h1.empty or d1.empty: return None
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        
        price = h1['Close'].iloc[-1]
        
        # Bid/Ask i Spread
        try:
            bid = t.info.get('bid') or price * 0.9998
            ask = t.info.get('ask') or price * 1.0002
        except:
            bid, ask = price * 0.9998, price * 1.0002
        spread = ask - bid
        
        # Wolumen i Wielcy Gracze (Skok > 200% średniej z 20h)
        avg_vol = h1['Volume'].rolling(20).mean().iloc[-1]
        curr_vol = h1['Volume'].iloc[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0
        big_players = vol_ratio > 2.0
        
        # Wskaźniki
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        yearly_high = d1['High'].max()
        yearly_low = d1['Low'].min()
        
        # RSI 1h
        delta = h1['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Werdykt
        if rsi < 32: verd, vcl = "KUP 🔥", "sig-buy"
        elif rsi > 68: verd, vcl = "SPRZEDAJ ⚠️", "sig-sell"
        else: verd, vcl = "CZEKAJ ⏳", ""

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "spread": spread,
            "rsi": rsi, "sma200": sma200, "verdict": verd, "vcl": vcl,
            "y_high": yearly_high, "y_low": yearly_low, "vol_ratio": vol_ratio,
            "big_players": big_players, "df": h1, "change": ((price - d1['Close'].iloc[-2]) / d1['Close'].iloc[-2] * 100)
        }
    except: return None

# --- 4. PANEL BOCZNY ---
with st.sidebar:
    st.title("🚜 GOLDEN v27")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    t_input = st.text_area("Lista Symboli:", value=load_tickers(), height=150)
    if st.button("💾 ZAPISZ LISTĘ"):
        with open(DB_FILE, "w") as f: f.write(t_input)
        st.success("Lista zapisana!")
    refresh = st.select_slider("Odświeżanie (s)", options=[30, 60, 300], value=60)

st_autorefresh(interval=refresh * 1000, key="v27_fsh")

# --- 5. LOGIKA GŁÓWNA ---
tickers = [x.strip().upper() for x in t_input.split(",") if x.strip()]
with ThreadPoolExecutor(max_workers=8) as executor:
    all_data = [d for d in list(executor.map(get_analysis, tickers)) if d is not None]

if all_data:
    # --- RANKING TOP ---
    st.subheader("🏆 SYGNAŁY I WOLUMEN")
    sorted_top = sorted(all_data, key=lambda x: x['rsi'])[:10]
    top_cols = st.columns(5)
    for i, d in enumerate(sorted_top):
        with top_cols[i % 5]:
            vol_alert = "🚀 VOL!" if d['big_players'] else ""
            st.markdown(f"""
                <div class="top-tile">
                    <b style="font-size:1.2rem;">{d['symbol']}</b> <span class="volume-alert">{vol_alert}</span><br>
                    <span style="color:#58a6ff; font-size:1.1rem;">{d['price']:.2f}</span><br>
                    <span class="bid-box">B: {d['bid']:.2f}</span><br>
                    <span class="ask-box">A: {d['ask']:.2f}</span>
                    <div class="{d['vcl']}" style="margin-top:8px; font-size:1.1rem;">{d['verdict']}</div>
                    <small>RSI: {d['rsi']:.1f} | Spread: {d['spread']:.2f}</small>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- LISTA SZCZEGÓŁOWA ---
    for d in all_data:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.3, 2, 1.2])
            
            with c1:
                st.markdown(f"<h3 class='{d['vcl']}'>{d['symbol']} {d['verdict']}</h3>", unsafe_allow_html=True)
                st.metric("AKTUALNA CENA", f"{d['price']:.4f}", f"{d['change']:.2f}%")
                st.markdown(f"""
                    <div style="margin-top:15px;">
                        <div class="metric-row"><span>RSI (1h)</span><b>{d['rsi']:.1f}</b></div>
                        <div class="metric-row"><span>SMA 200</span><b>{d['sma200']:.2f}</b></div>
                        <div class="metric-row"><span style="color:#00ff88;">Szczyt 52t</span><b>{d['y_high']:.2f}</b></div>
                        <div class="metric-row"><span style="color:#ff4b4b;">Dołek 52t</span><b>{d['y_low']:.2f}</b></div>
                    </div>
                """, unsafe_allow_html=True)

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index[-50:], open=d['df']['Open'][-50:], high=d['df']['High'][-50:], low=d['df']['Low'][-50:], close=d['df']['Close'][-50:])])
                fig.update_layout(template="plotly_dark", height=320, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")

            with c3:
                # Panel Handlowy (Bid/Ask/Spread/Volume)
                st.markdown(f"""
                    <div style="background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d;">
                        <div style="color:#ff4b4b; font-size: 0.85rem; margin-bottom:2px;">BID (SPRZEDAJESZ)</div>
                        <div style="font-size: 1.4rem; font-weight: bold; color:#ff4b4b; font-family: monospace;">{d['bid']:.4f}</div>
                        
                        <div style="color:#00ff88; font-size: 0.85rem; margin-top: 10px; margin-bottom:2px;">ASK (KUPUJESZ)</div>
                        <div style="font-size: 1.4rem; font-weight: bold; color:#00ff88; font-family: monospace;">{d['ask']:.4f}</div>
                        
                        <div style="border-top: 1px solid #30363d; margin-top: 10px; padding-top: 8px;">
                            <span style="color:#8b949e;">Spread:</span> <b style="color:#58a6ff;">{d['spread']:.4f}</b>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                # Wskaźnik Wolumenu
                vol_color = "#f1e05a" if d['big_players'] else "#8b949e"
                st.markdown(f"""
                    <div style="margin-top: 15px; padding: 10px; border: 1px solid {vol_color}; border-radius: 10px; background: rgba(241, 224, 90, 0.05);">
                        <span style="font-size: 0.8rem; color: #8b949e;">MOC WOLUMENU (1h):</span><br>
                        <b style="color:{vol_color}; font-size: 1.2rem;">x {d['vol_ratio']:.2f}</b>
                        {"<br><span class='volume-alert'>⚠️ WYKRYTO DUŻEGO GRACZA</span>" if d['big_players'] else ""}
                    </div>
                """, unsafe_allow_html=True)
                
                if api_key and st.button(f"🧠 ANALIZA AI", key=f"ai_{d['symbol']}"):
                    client = OpenAI(api_key=api_key)
                    prompt = (f"Jesteś ekspertem tradingowym. Przeanalizuj {d['symbol']}: "
                             f"Cena {d['price']}, Bid {d['bid']}, Ask {d['ask']}, Spread {d['spread']:.4f}. "
                             f"RSI {d['rsi']:.1f}, Skok wolumenu: x{d['vol_ratio']:.2f}. "
                             f"Szczyt 12m: {d['y_high']}, Dołek 12m: {d['y_low']}. "
                             f"Czy wchodzić? Podaj krótką strategię i poziomy TP/SL.")
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                    st.info(resp.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.warning("Brak danych. Wpisz poprawne symbole (np. BTC-USD, AAPL, PKO.WA) w panelu bocznym.")

