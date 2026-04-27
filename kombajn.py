import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
import time

# --- 1. KONFIGURACJA PLIKÓW I PAMIĘCI ---
DB_FILE = "moje_spolki.txt"

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
        except: return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"
    return "PKO.WA, ALE.WA, KGH.WA, PKN.WA, BTC-USD, NVDA"

# Konfiguracja strony
st.set_page_config(page_title="AI ALPHA GOLDEN v41 MAXI PRO", page_icon="🚜", layout="wide")

# Inicjalizacja stanów sesji
if 'risk_cap' not in st.session_state: st.session_state.risk_cap = 50000.0
if 'risk_pct' not in st.session_state: st.session_state.risk_pct = 1.0

# --- 2. PEŁNA BIBLIOTEKA STYLÓW CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #020202; color: #e0e0e0; }
    
    /* Karta sygnału */
    .top-tile { 
        text-align: center; padding: 20px; border-radius: 15px; 
        background: #0d1117; min-height: 450px; border: 1px solid #30363d;
        transition: transform 0.3s;
    }
    .top-tile:hover { transform: translateY(-5px); border-color: #58a6ff; }
    
    /* Sygnały */
    .sig-buy { color: #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 8px; background: rgba(0,255,136,0.1); font-size: 1.2rem; }
    .sig-sell { color: #ff4b4b; font-weight: bold; border: 2px solid #ff4b4b; padding: 5px 15px; border-radius: 8px; background: rgba(255,75,75,0.1); font-size: 1.2rem; }
    .sig-neutral { color: #8b949e; font-weight: bold; border: 1px solid #30363d; padding: 5px 15px; border-radius: 8px; }
    
    /* Kalkulator i Dane */
    .pos-calc { background: rgba(88, 166, 255, 0.1); border-radius: 8px; padding: 12px; margin: 15px 0; border: 1px solid #58a6ff; }
    .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.8rem; text-align: left; margin-top: 10px; }
    .stat-item { border-bottom: 1px solid #21262d; padding: 3px 0; }
    
    /* AI i News */
    .ai-box { padding: 12px; border-radius: 10px; margin-top: 15px; font-size: 0.85rem; background: rgba(255,255,255,0.03); min-height: 60px; line-height: 1.3; }
    .news-box { font-size: 0.75rem; color: #8b949e; text-align: left; margin-top: 15px; border-top: 1px dashed #30363d; padding-top: 10px; }
    .news-title { color: #58a6ff; text-decoration: none; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ROZBUDOWANY SILNIK ANALIZY ---
def get_analysis(symbol, api_key=None):
    try:
        symbol = symbol.strip().upper()
        ticker = yf.Ticker(symbol)
        
        # Pobór danych historycznych (250 dni dla SMA 200)
        df = ticker.history(period="250d", interval="1d")
        if df.empty or len(df) < 200: return None
        
        price = float(df['Close'].iloc[-1])
        
        # 1. Wskaźniki Średnie
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # 2. Pivot Point (Klasyczny)
        prev_h = df['High'].iloc[-2]
        prev_l = df['Low'].iloc[-2]
        prev_c = df['Close'].iloc[-2]
        pivot = (prev_h + prev_l + prev_c) / 3
        
        # 3. RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # 4. ATR i Zarządzanie Ryzykiem (Ilość akcji)
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        risk_money_pln = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        sl_distance = atr * 1.5
        shares = int(risk_money_pln / sl_distance) if sl_distance > 0 else 0
        
        # 5. Newsy z rynku
        market_news = []
        try:
            raw_news = ticker.news[:2]
            for n in raw_news:
                market_news.append({"title": n.get('title')[:60] + "...", "link": n.get('link')})
        except: market_news = [{"title": "Brak bieżących newsów", "link": "#"}]

        # 6. Werdykt Techniczny
        v_type = "neutral"
        if rsi < 33: verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 67: verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        # 7. Analiza AI (Krótka)
        ai_msg = "Wprowadź klucz OpenAI"
        if api_key and len(api_key) > 20:
            try:
                client = OpenAI(api_key=api_key)
                prompt = f"Symbol: {symbol}, Cena: {price}, RSI: {rsi:.0f}, SMA200: {sma200:.2f}. Podaj 1 konkretne zdanie analizy."
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=40
                )
                ai_msg = response.choices.message.content
            except: ai_msg = "Limit AI wyczerpany"

        return {
            "symbol": symbol, "price": price, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "pivot": pivot, "verd": verd, "vcl": vcl, "v_type": v_type, "shares": shares,
            "sl": price - sl_distance, "tp": price + (atr * 3), "ai": ai_msg, 
            "news": market_news, "df": df.tail(50), "pos_val": shares * price
        }
    except Exception as e:
        st.error(f"Błąd dla {symbol}: {e}")
        return None

# --- 4. PANEL BOCZNY (USTAWIENIA) ---
with st.sidebar:
    st.title("🚜 ALPHA GOLDEN v41")
    st.markdown("---")
    api_key = st.text_input("OpenAI API Key", type="password", help="Wymagany do analizy AI")
    
    st.subheader("💰 PORTFEL (PLN)")
    st.session_state.risk_cap = st.number_input("Twój Kapitał (zł)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    st.subheader("📝 LISTA SPÓŁEK")
    ticker_area = st.text_area("Symbole (np. PKO.WA, BTC-USD):", value=load_tickers(), height=150)
    
    if st.button("💾 ZAPISZ I START"):
        with open(DB_FILE, "w") as f: f.write(ticker_area)
        st.cache_data.clear()
        st.success("Lista zapisana!")
        st.rerun()
        
    refresh_rate = st.select_slider("Odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_rate * 1000, key="v41_refresh")

# --- 5. LOGIKA WYŚWIETLANIA ---
tickers_list = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

if tickers_list:
    # Pobieranie danych (sekwencyjne dla stabilności na Streamlit Cloud)
    data_ready = []
    with st.spinner('Pobieranie danych z GPW i rynków światowych...'):
        for t in tickers_list:
            res = get_analysis(t, api_key)
            if res: data_ready.append(res)

    if data_ready:
        st.subheader(f"🏆 SYGNAŁY I ANALIZA RYNKOWA ({datetime.now().strftime('%H:%M:%S')})")
        
        # Wyświetlanie w siatce po 4 kafelki
        for i in range(0, len(data_ready), 4):
            cols = st.columns(4)
            for idx, d in enumerate(data_ready[i:i+4]):
                with cols[idx]:
                    # Kolor obramowania zależny od sygnału
                    b_color = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                    
                    st.markdown(f"""
                        <div class="top-tile" style="border: 2px solid {b_color};">
                            <div style="font-size:1.6rem; font-weight:bold;">{d['symbol']}</div>
                            <div style="color:#58a6ff; font-size:1.3rem; margin-bottom:10px;">{d['price']:.2f} PLN</div>
                            <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                            
                            <div class="pos-calc">
                                <span style="font-size:0.8rem; color:#8b949e;">ILOŚĆ DO KUPNA:</span><br>
                                <span style="font-size:1.4rem;">{d['shares']} szt.</span><br>
                                <small>Wartość: {d['pos_val']:.0f} PLN</small>
                            </div>
                            
                            <div class="stat-grid">
                                <div class="stat-item"><b>SMA50:</b> {d['sma50']:.2f}</div>
                                <div class="stat-item"><b>SMA200:</b> {d['sma200']:.2f}</div>
                                <div class="stat-item"><b>PIVOT:</b> {d['pivot']:.2f}</div>
                                <div class="stat-item"><b>RSI(14):</b> {d['rsi']:.1f}</div>
                            </div>
                            
                            <div class="ai-box" style="border-left: 3px solid {b_color};">
                                <b>🤖 AI:</b> {d['ai']}
                            </div>
                            
                            <div class="news-box">
                                <b>📢 INFO Z RYNKU:</b><br>
                                • <a class="news-title" href="{d['news'][0]['link']}" target="_blank">{d['news'][0]['title']}</a><br>
                                {"• <a class='news-title' href='"+d['news'][1]['link']+"' target='_blank'>"+d['news'][1]['title']+"</a>" if len(d['news'])>1 else ""}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    with st.expander("📈 Wykres i Poziomy"):
                        st.write(f"**Stop Loss:** {d['sl']:.2f} | **Take Profit:** {d['tp']:.2f}")
                        fig = go.Figure(data=[go.Candlestick(
                            x=d['df'].index, open=d['df']['Open'], 
                            high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close']
                        )])
                        fig.add_hline(y=d['sma200'], line_color="red", line_dash="dash", annotation_text="SMA200")
                        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)

    else:
        st.error("Błąd: Nie udało się pobrać danych. Sprawdź symbole i połączenie.")
else:
    st.info("Dodaj symbole spółek w panelu bocznym, aby rozpocząć analizę.")

# --- 6. STOPKA ---
st.markdown("---")
st.markdown(f"<div style='text-align:center; color:#8b949e;'>AI ALPHA GOLDEN v41.0 MAXI | Kapitał: {st.session_state.risk_cap} PLN | Ryzyko: {st.session_state.risk_pct}%</div>", unsafe_allow_html=True)
