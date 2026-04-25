import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- 1. KONFIGURACJA PLIKÓW I PAMIĘCI ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "NVDA, TSLA, BTC-USD, GC=F, PKO.WA"
        except: return "NVDA, TSLA, BTC-USD, GC=F, PKO.WA"
    return "NVDA, TSLA, BTC-USD, GC=F, PKO.WA"

# Konfiguracja strony
st.set_page_config(page_title="AI ALPHA GOLDEN v38 FULL", page_icon="🚜", layout="wide")

# Inicjalizacja stanów sesji
if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}
if 'risk_cap' not in st.session_state:
    st.session_state.risk_cap = 10000.0
if 'risk_pct' not in st.session_state:
    st.session_state.risk_pct = 1.0

# --- 2. PEŁNA BIBLIOTEKA STYLÓW CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    
    /* Karta spółki */
    .ticker-card { 
        background: linear-gradient(145deg, #0d1117, #050505); 
        padding: 30px; border-radius: 20px; border: 1px solid #30363d; 
        margin-bottom: 30px; box-shadow: 10px 10px 20px rgba(0,0,0,0.5);
    }
    
    /* Kafelki Top 10 z Neonowym Glow */
    .top-tile-buy { 
        border: 1px solid #00ff88; box-shadow: 0px 0px 15px rgba(0, 255, 136, 0.3); 
        text-align: center; padding: 15px; border-radius: 15px; min-height: 220px; background: #0d1117;
    }
    .top-tile-sell { 
        border: 1px solid #ff4b4b; box-shadow: 0px 0px 15px rgba(255, 75, 75, 0.3); 
        text-align: center; padding: 15px; border-radius: 15px; min-height: 220px; background: #0d1117;
    }
    .top-tile-neutral { 
        border: 1px solid #30363d; text-align: center; padding: 15px; border-radius: 15px; 
        min-height: 220px; background: #0d1117;
    }
    
    /* Typografia i kolory */
    .bid-box { color: #ff4b4b; font-weight: bold; font-family: 'Courier New', monospace; font-size: 1.4rem; }
    .ask-box { color: #00ff88; font-weight: bold; font-family: 'Courier New', monospace; font-size: 1.4rem; }
    .sig-buy { color: #00ff88; font-weight: bold; text-shadow: 0 0 10px rgba(0,255,136,0.6); font-size: 1.2rem; }
    .sig-sell { color: #ff4b4b; font-weight: bold; text-shadow: 0 0 10px rgba(255,75,75,0.6); font-size: 1.2rem; }
    
    /* Newsy i Statystyki */
    .news-container { margin-top: 15px; }
    .news-item { 
        font-size: 0.85rem; color: #c9d1d9; background: #161b22; 
        padding: 10px; border-radius: 8px; margin-bottom: 8px; border-left: 4px solid #58a6ff;
    }
    .stat-row { 
        display: flex; justify-content: space-between; border-bottom: 1px solid #21262d; 
        padding: 8px 0; font-size: 0.95rem; 
    }
    .calc-box {
        background: rgba(241, 224, 90, 0.1); border: 1px solid #f1e05a; 
        padding: 15px; border-radius: 12px; margin-bottom: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ROZBUDOWANY SILNIK ANALIZY ---
def get_analysis(symbol):
    try:
        symbol = symbol.strip().upper()
        if not symbol: return None
        t = yf.Ticker(symbol)
        
        # Dane rynkowe (Pancerny pobór)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="1y", interval="1d")
        if h1.empty or d1.empty: return None
        
        price = h1['Close'].iloc[-1]
        
        # Pobieranie Bid/Ask z obsługą błędów
        try:
            bid = t.info.get('bid') or price * 0.9996
            ask = t.info.get('ask') or price * 1.0004
        except:
            bid, ask = price * 0.9996, price * 1.0004
            
        spread = ask - bid
        
        # Newsy rynkowe
        market_news = []
        try:
            if t.news:
                for n in t.news[:3]:
                    market_news.append({
                        "title": n.get('title'),
                        "link": n.get('link'),
                        "publisher": n.get('publisher')
                    })
        except: pass

        # Ekstrema i Pivot Point
        y_high, y_low = d1['High'].max(), d1['Low'].min()
        hp, lp, cp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + cp) / 3
        
        # ATR i Poziomy Ryzyka
        atr = (d1['High'] - d1['Low']).rolling(14).mean().iloc[-1]
        tp_price = price + (atr * 1.8)
        sl_price = price - (atr * 1.3)
        
        # Trend (SMA 200)
        sma200 = d1['Close'].rolling(200).mean().iloc[-1]
        trend_status = "BULL 📈" if price > sma200 else "BEAR 📉"
        
        # RSI 14h
        delta = h1['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi_val = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Wolumen
        vol_avg = h1['Volume'].rolling(20).mean().iloc[-1]
        vol_ratio = h1['Volume'].iloc[-1] / (vol_avg + 1)
        
        # Werdykt techniczny
        v_type = "neutral"
        if rsi_val < 32: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 68: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "", "neutral"

        return {
            "symbol": symbol, "price": price, "bid": bid, "ask": ask, "rsi": rsi_val,
            "verd": verd, "vcl": vcl, "v_type": v_type, "pp": pp, "spread": spread,
            "tp": tp_price, "sl": sl_price, "y_high": y_high, "y_low": y_low,
            "vol_ratio": vol_ratio, "trend": trend_status, "news": market_news, "df": h1
        }
    except: return None

# --- 4. PANEL BOCZNY (USTAWIENIA) ---
with st.sidebar:
    st.title("🚜 GOLDEN v38 PRO")
    st.markdown("---")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    
    st.subheader("💰 KALKULATOR RYZYKA")
    st.session_state.risk_cap = st.number_input("Twój Kapitał ($)", value=st.session_state.risk_cap, step=500.0)
    st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    st.subheader("📝 LISTA SPÓŁEK")
    ticker_area = st.text_area("Symbole (przecinek lub linia):", value=load_tickers(), height=200)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_area)
        st.success("Lista zaktualizowana!")
        st.rerun()
        
    refresh_rate = st.select_slider("Auto-odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_rate * 1000, key="v38_fsh")

# --- 5. GŁÓWNA LOGIKA WYŚWIETLANIA ---
tickers_list = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

if tickers_list:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_analysis, tickers_list))
        data_ready = [r for r in results if r is not None]

    if data_ready:
        # --- TOP 10 SIGNALS (KAFELKI) ---
        st.subheader("🏆 TOP 10 SIGNAL TERMINAL")
        t_cols = st.columns(5)
        for i, d in enumerate(data_ready[:10]):
            with t_cols[i % 5]:
                st.markdown(f"""
                    <div class="top-tile-{d['v_type']}">
                        <b style="font-size:1.3rem;">{d['symbol']}</b><br>
                        <span style="color:#58a6ff; font-size:1.2rem;">{d['price']:.2f}</span><br>
                        <div class="bid-box" style="font-size:0.9rem;">B: {d['bid']:.2f}</div>
                        <div class="ask-box" style="font-size:0.9rem;">A: {d['ask']:.2f}</div>
                        <div class="{d['vcl']}" style="margin-top:10px;">{d['verd']}</div>
                        <small style="color:#8b949e;">RSI: {d['rsi']:.1f}</small>
                    </div>
                """, unsafe_allow_html=True)

        st.divider()

        # --- SZCZEGÓŁOWE KARTY ANALIZY ---
        for d in data_ready:
            with st.container():
                st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns([1.5, 2, 1.5])
                
                with c1:
                    st.markdown(f"<h2 class='{d['vcl']}'>{d['symbol']} | {d['verd']}</h2>", unsafe_allow_html=True)
                    st.metric("CENA BIEŻĄCA", f"{d['price']:.4f}")
                    
                    # Kalkulator wielkości pozycji
                    risk_dollars = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
                    distance_to_sl = abs(d['price'] - d['sl'])
                    shares_to_buy = int(risk_dollars / distance_to_sl) if distance_to_sl > 0 else 0
                    
                    st.markdown(f"""
                        <div class="calc-box">
                            <span style="color:#f1e05a; font-size:1.1rem; font-weight:bold;">KUP: {shares_to_buy} sztuk</span><br>
                            <small>Ryzyko: ${risk_dollars:.2f} | Kapitał: ${st.session_state.risk_cap}</small>
                        </div>
                        <div class="stat-row"><span>Pivot Point:</span><b>{d['pp']:.2f}</b></div>
                        <div class="stat-row"><span>Trend SMA200:</span><b>{d['trend']}</b></div>
                        <div class="stat-row"><span style="color:#00ff88;">Take Profit:</span><b>{d['tp']:.2f}</b></div>
                        <div class="stat-row"><span style="color:#ff4b4b;">Stop Loss:</span><b>{d['sl']:.2f}</b></div>
                        <div class="stat-row"><span>Roczne High/Low:</span><small>{d['y_high']:.2f} / {d['y_low']:.2f}</small></div>
                    """, unsafe_allow_html=True)
                    
                    # Wyświetlanie Newsów
                    if d['news']:
                        st.markdown("<div class='news-container'><b>📰 OSTATNIE NEWSY:</b>", unsafe_allow_html=True)
                        for n in d['news']:
                            st.markdown(f"<div class='news-item'>{n['title']} <br><small>{n['publisher']}</small></div>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                with c2:
                    # Wykres Candlestick
                    fig = go.Figure(data=[go.Candlestick(
                        x=d['df'].index[-50:], open=d['df']['Open'][-50:], 
                        high=d['df']['High'][-50:], low=d['df']['Low'][-50:], 
                        close=d['df']['Close'][-50:],
                        name="Cena"
                    )])
                    fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"fig_{d['symbol']}")

                with c3:
                    # Panel Transakcyjny i AI
                    st.markdown(f"""
                        <div style="background: #000; padding: 20px; border-radius: 15px; border: 1px solid #333; margin-bottom:20px;">
                            <div style="color:#ff4b4b; font-size:0.85rem; letter-spacing:1px;">BID (MARKET SELL)</div>
                            <div class="bid-box">{d['bid']:.4f}</div>
                            <div style="color:#00ff88; font-size:0.85rem; letter-spacing:1px; margin-top:15px;">ASK (MARKET BUY)</div>
                            <div class="ask-box">{d['ask']:.4f}</div>
                            <div style="border-top:1px solid #222; margin-top:15px; padding-top:10px;">
                                <div class="stat-row"><span>Spread:</span><b>{d['spread']:.4f}</b></div>
                                <div class="stat-row"><span>Moc Wolumenu:</span><b style="color:#f1e05a;">x{d['vol_ratio']:.2f}</b></div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"🧠 ANALIZA AI + FUNDAMENTY", key=f"ai_{d['symbol']}"):
                        if not api_key: st.error("Brak klucza API w panelu bocznym!")
                        else:
                            client = OpenAI(api_key=api_key)
                            news_txt = " ".join([n['title'] for n in d['news']])
                            prompt = (f"Jesteś PRO traderem. Analizuj {d['symbol']}. Cena {d['price']}. "
                                      f"RSI {d['rsi']:.1f}, Trend {d['trend']}, Wolumen x{d['vol_ratio']:.2f}. "
                                      f"Ostatnie newsy: {news_txt}. "
                                      f"Podaj: Sentyment, Wpływ newsów na cenę i Strategię (Entry/TP/SL).")
                            
                            response = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "system", "content": "Krótko, technicznie, konkretnie. Zakaz lania wody."},
                                          {"role": "user", "content": prompt}]
                            )
                            st.session_state.ai_cache[d['symbol']] = response.choices[0].message.content
                    
                    if d['symbol'] in st.session_state.ai_cache:
                        st.info(st.session_state.ai_cache[d['symbol']])
                
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.error("Błąd krytyczny pobierania danych. Sprawdź połączenie lub symbole.")
else:
    st.info("System gotowy. Dodaj symbole spółek w panelu bocznym, aby rozpocząć analizę.")

st.caption(f"AI Alpha Golden v38 | News Engine | Risk Calc | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
