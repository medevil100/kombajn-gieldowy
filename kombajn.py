import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. KONFIGURACJA I TRWAŁOŚĆ DANYCH ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "NVDA, TSLA, BTC-USD, PKO.WA, GC=F"
        except: return "NVDA, TSLA, BTC-USD, PKO.WA, GC=F"
    return "NVDA, TSLA, BTC-USD, PKO.WA, GC=F"

st.set_page_config(page_title="AI ALPHA GOLDEN v36", page_icon="🚜", layout="wide")

if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. ZAAWANSOWANE STYLE WIZUALNE (NEON & TERMINAL) ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    .ticker-card { 
        background: linear-gradient(145deg, #0d1117, #050505); 
        padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 25px;
        box-shadow: 5px 5px 15px rgba(0,0,0,0.5);
    }
    .top-tile-buy { 
        border: 1px solid #00ff88; box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.2); 
        text-align: center; padding: 15px; border-radius: 12px; min-height: 200px;
    }
    .top-tile-sell { 
        border: 1px solid #ff4b4b; box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.2); 
        text-align: center; padding: 15px; border-radius: 12px; min-height: 200px;
    }
    .top-tile-neutral { 
        border: 1px solid #30363d; text-align: center; padding: 15px; border-radius: 12px; min-height: 200px;
    }
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: 'Courier New', monospace; font-size: 1.3rem; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: 'Courier New', monospace; font-size: 1.3rem; }
    .sig-buy { color: #00ff88; font-weight: bold; text-shadow: 0 0 8px rgba(0,255,136,0.5); }
    .sig-sell { color: #ff4b4b; font-weight: bold; text-shadow: 0 0 8px rgba(255,75,75,0.5); }
    .stat-row { display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; padding: 5px 0; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SILNIK ANALIZY TECHNICZNEJ ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        if not symbol: return None
        t = yf.Ticker(symbol)
        
        # Pobieranie danych (H1 dla RSI/Vol, D1 dla Trendu i Szczytów)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        
        # Bezpieczny Bid/Ask (Próba z info, w razie błędu symulacja)
        try:
            bid = t.info.get('bid') or price * 0.9997
            ask = t.info.get('ask') or price * 1.0003
        except:
            bid, ask = price * 0.9997, price * 1.0003
            
        spread = ask - bid
        
        # Statystyki roczne i Pivoty
        y_high, y_low = d1['High'].max(), d1['Low'].min()
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3 # Klasyczny Pivot Point
        
        # ATR do wyznaczania TP/SL
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp_level = price + (atr * 1.8)
        sl_level = price - (atr * 1.3)
        
        # Trend długoterminowy (SMA 200)
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        trend = "BULL 📈" if price > sma200 else "BEAR 📉"
        
        # RSI (14h)
        delta = h1['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        # Wolumen (relatywny do średniej z 20h)
        vol_avg = h1['Volume'].rolling(20).mean().iloc[-1]
        vol_ratio = h1['Volume'].iloc[-1] / (vol_avg + 1)
        
        # Logika werdyktu
        v_type = "neutral"
        if rsi < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi,
            "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp, "spread": spread,
            "tp": tp_level, "sl": sl_level, "y_high": y_high, "y_low": y_low,
            "vol_ratio": vol_ratio, "trend": trend, "df": h1, "sma200": sma200
        }
    except:
        return None

# --- 4. PANEL STEROWANIA (SIDEBAR) ---
with st.sidebar:
    st.title("🚜 GOLDEN v36")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    ticker_input = st.text_area("Twoje Spółki:", value=load_tickers(), height=200)
    
    if st.button("💾 ZAPISZ I URUCHOM"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_input)
        st.success("Lista zapisana!")
        st.rerun()
        
    refresh_val = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_val * 1000, key="v36_fsh")

# --- 5. LOGIKA WYŚWIETLANIA ---
# Przetwarzanie listy symboli
tickers = [x.strip().upper() for x in ticker_input.replace('\n', ',').split(',') if x.strip()]

if tickers:
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(get_analysis, tickers))
        all_data = [r for r in results if r is not None]

    if all_data:
        # --- SEKCJA TOP 10 (KAFELKI) ---
        st.subheader("🏆 TOP SYGNAŁY")
        t_cols = st.columns(5)
        for i, d in enumerate(all_data[:10]):
            with t_cols[i % 5]:
                st.markdown(f"""
                    <div class="top-tile-{d['v_type']}">
                        <b style="font-size:1.3rem;">{d['symbol']}</b><br>
                        <span style="font-size:1.1rem; color:#58a6ff;">{d['price']:.2f}</span><br>
                        <div class="bid-box" style="font-size:0.9rem;">B: {d['bid']:.2f}</div>
                        <div class="ask-box" style="font-size:0.9rem;">A: {d['ask']:.2f}</div>
                        <div class="{d['vcl']}" style="margin-top:5px;">{d['verd']}</div>
                        <small style="color:#8b949e;">Trend: {d['trend'][:4]}</small>
                    </div>
                """, unsafe_allow_html=True)

        st.divider()

        # --- SEKCJA SZCZEGÓŁOWA (KARTY) ---
        for d in all_data:
            with st.container():
                st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns([1.3, 2, 1.4])
                
                with c1:
                    st.markdown(f"<h2 class='{d['vcl']}'>{d['symbol']} | {d['verd']}</h2>", unsafe_allow_html=True)
                    st.metric("AKTUALNA CENA", f"{d['price']:.4f}")
                    st.markdown(f"""
                        <div style="margin-top:10px;">
                            <div class="stat-row"><span>Pivot Point:</span><b style="color:#58a6ff;">{d['pp']:.2f}</b></div>
                            <div class="stat-row"><span>Take Profit:</span><b style="color:#00ff88;">{d['tp']:.2f}</b></div>
                            <div class="stat-row"><span>Stop Loss:</span><b style="color:#ff4b4b;">{d['sl']:.2f}</b></div>
                            <div class="stat-row"><span>Trend SMA200:</span><b>{d['trend']}</b></div>
                            <div class="stat-row"><span>Roczne High:</span><b>{d['y_high']:.2f}</b></div>
                            <div class="stat-row"><span>Roczne Low:</span><b>{d['y_low']:.2f}</b></div>
                        </div>
                    """, unsafe_allow_html=True)
                
                with c2:
                    # Wykres Świecowy
                    fig = go.Figure(data=[go.Candlestick(
                        x=d['df'].index[-45:], open=d['df']['Open'][-45:], 
                        high=d['df']['High'][-45:], low=d['df']['Low'][-45:], 
                        close=d['df']['Close'][-45:]
                    )])
                    fig.update_layout(template="plotly_dark", height=320, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"plot_{d['symbol']}")
                
                with c3:
                    # Panel Handlowy i AI
                    st.markdown(f"""
                        <div style="background: #000; padding: 15px; border-radius: 12px; border: 1px solid #30363d; margin-bottom:15px;">
                            <div style="color:#ff4b4b; font-size:0.8rem;">BID (TY SPRZEDAJSZ)</div>
                            <div class="bid-box">{d['bid']:.4f}</div>
                            <div style="color:#00ff88; font-size:0.8rem; margin-top:10px;">ASK (TY KUPUJESZ)</div>
                            <div class="ask-box">{d['ask']:.4f}</div>
                            <div style="border-top:1px solid #222; margin-top:12px; padding-top:8px;">
                                <span style="color:#8b949e; font-size:0.85rem;">Spread: <b style="color:#58a6ff;">{d['spread']:.4f}</b></span><br>
                                <span style="color:#8b949e; font-size:0.85rem;">Moc Wolumenu: <b style="color:#f1e05a;">x{d['vol_ratio']:.2f}</b></span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"🧠 GENERUJ ANALIZĘ AI", key=f"ai_btn_{d['symbol']}"):
                        if not api_key: st.error("Wklej klucz OpenAI w panelu bocznym!")
                        else:
                            client = OpenAI(api_key=api_key)
                            prompt_text = (f"Analiza techniczna {d['symbol']}. Cena {d['price']}. "
                                           f"RSI {d['rsi']:.1f}, Trend {d['trend']}, Wolumen x{d['vol_ratio']:.2f}. "
                                           f"Szczyt 12m {d['y_high']:.2f}, Dołek 12m {d['y_low']:.2f}. "
                                           f"Podaj konkretnie: Sentyment, Relację do ekstremów i Plan (Entry, TP, SL).")
                            
                            response = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "system", "content": "Jesteś ekspertem giełdowym. Piszesz tylko fakty techniczne. Zero lania wody. Formatuj od myślników."},
                                          {"role": "user", "content": prompt_text}]
                            )
                            st.session_state.ai_cache[d['symbol']] = response.choices[0].message.content
                    
                    if d['symbol'] in st.session_state.ai_cache:
                        st.info(st.session_state.ai_cache[d['symbol']])
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.warning("Nie udało się pobrać danych. Sprawdź poprawność symboli.")
else:
    st.info("Dodaj symbole (np. BTC-USD, AAPL, PKO.WA) w panelu bocznym.")

st.caption("AI Alpha Golden v36 | SMA200 Trend Engine | Hybrid Analysis")
