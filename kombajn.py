import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime

# --- 1. KONFIGURACJA PLIKÓW ---
DB_FILE = "moje_spolki.txt"

st.set_page_config(page_title="ULTIMATE COMMANDER v89", page_icon="🚜", layout="wide")

# Inicjalizacja pamięci AI (żeby wyniki nie znikały)
if "ai_mem" not in st.session_state:
    st.session_state.ai_mem = {}

def get_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: return f.read()
    return "NVDA, TSLA, BTC-USD"

# --- 2. NEONOWY DESIGN ---
st.markdown("""
    <style>
    @keyframes pulse { 0% { box-shadow: 0 0 5px #fff; } 50% { box-shadow: 0 0 20px #fff; } 100% { box-shadow: 0 0 5px #fff; } }
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 25px; }
    .vol-spike { animation: pulse 2s infinite; border: 1px solid #ffffff !important; }
    .buy-tag { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 3px 10px; border-radius: 5px; }
    .sell-tag { color: #ff4b4b; text-shadow: 0 0 10px #ff4b4b; font-weight: bold; border: 1px solid #ff4b4b; padding: 3px 10px; border-radius: 5px; }
    .tp-label { color: #00ff88; border-left: 4px solid #00ff88; padding-left: 10px; font-weight: bold; }
    .sl-label { color: #ff4b4b; border-left: 4px solid #ff4b4b; padding-left: 10px; font-weight: bold; }
    .top-rank { background: #161b22; padding: 10px; border-radius: 10px; text-align: center; border-bottom: 2px solid #00ff88; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. ANALIZA TECHNICZNA ---
def fix_cols(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        df = fix_cols(df)
        
        p = float(df['Close'].iloc[-1])
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # Pivot Points
        h, l, c = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pp = (h + l + c) / 3
        
        # Wolumen i RSI
        vol_rel = df['Volume'].iloc[-1] / (df['Volume'].tail(20).mean() + 1e-9)
        delta = df['Close'].diff()
        rsi = (100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9))))).iloc[-1]
        
        return {
            "symbol": symbol.strip().upper(), "price": p, "rsi": rsi, "ma50": ma50, "ma200": ma200, 
            "pp": pp, "vol": vol_rel, "df": df.tail(40), "change": ((p - c) / c * 100)
        }
    except: return None

def call_ai(d, key):
    # Sprawdzamy czy mamy już analizę w tej sesji
    if d['symbol'] in st.session_state.ai_mem:
        return st.session_state.ai_mem[d['symbol']]
    
    try:
        client = OpenAI(api_key=key)
        prompt = (f"Jesteś traderem. Analizuj {d['symbol']} cena {d['price']}. RSI:{d['rsi']:.1f}, MA50:{d['ma50']:.1f}, Pivot:{d['pp']:.2f}. "
                  f"Ostatnie 5 dni: {d['df']['Close'].tail(5).tolist()}. "
                  f"Daj JSON: {{\"w\": \"KUP/SPRZEDAJ/TRZYMAJ\", \"sl\": cena, \"tp\": cena, \"u\": \"max 8 slow\"}}")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_mem[d['symbol']] = res
        return res
    except: return None

# --- 4. PANEL STEROWANIA ---
with st.sidebar:
    st.title("🚜 MONSTER v89")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("Klucz OpenAI", type="password")
    user_cap = st.number_input("Kapitał Portfela:", value=10000.0)
    ticker_list = st.text_area("Lista Tickerów (CSV):", value=get_tickers(), height=150)
    
    if st.button("💾 ZAPISZ I SKANUJ"):
        with open(DB_FILE, "w", encoding="utf-8") as f: f.write(ticker_list)
        st.session_state.ai_mem = {} # Resetujemy AI przy nowej liście
        st.rerun()
    
    st_autorefresh(interval=120000, key="refresh_v89")

# --- 5. DASHBOARD GŁÓWNY ---
tickers = [s.strip().upper() for s in ticker_list.split(",") if s.strip()]

with ThreadPoolExecutor(max_workers=10) as executor:
    full_results = [r for r in list(executor.map(get_data, tickers)) if r is not None]

if full_results:
    # --- RANKING TOP 10 ---
    st.subheader("🔥 RANKING OKAZJI (RSI)")
    rank_cols = st.columns(5)
    for i, r in enumerate(sorted(full_results, key=lambda x: x['rsi'])[:10]):
        with rank_cols[i % 5]:
            st.markdown(f"<div class='top-rank'><b>{r['symbol']}</b><br><small>RSI: {r['rsi']:.1f}</small></div>", unsafe_allow_html=True)

    st.divider()

    # --- KARTY INSTRUMENTÓW ---
    for d in full_results:
        # Pobieranie werdyktu AI (automatyczne)
        ai = call_ai(d, api_key) if api_key else None
        
        # Efekt Volume Spike (biała ramka)
        spike = "vol-spike" if d['vol'] > 2.0 else ""
        
        st.markdown(f'<div class="neon-card {spike}">', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1.5, 3, 1.5])
        
        with col1:
            st.markdown(f"## {d['symbol']} {'🔥' if d['vol'] > 2.0 else ''}")
            if ai:
                tag = "buy-tag" if "KUP" in ai['w'].upper() else "sell-tag" if "SPRZEDAJ" in ai['w'].upper() else ""
                st.markdown(f'<span class="{tag}">{ai["w"]}</span>', unsafe_allow_html=True)
            st.markdown(f"<br>Cena: **{d['price']:.2f}** ({d['change']:.2f}%)<br>R-Vol: x{d['vol']:.2f}", unsafe_allow_html=True)

        with col2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.add_hline(y=d['pp'], line_dash="dot", line_color="#58a6ff", annotation_text="Pivot")
            fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")

        with col3:
            if ai:
                st.markdown(f'<div class="tp-label">TAKE PROFIT: {ai["tp"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="sl-label">STOP LOSS: {ai["sl"]}</div>', unsafe_allow_html=True)
                
                # Szybki kalkulator
                try:
                    diff = abs(d['price'] - float(ai['sl']))
                    risk_cash = user_cap * 0.02 # 2% ryzyka
                    shares = int(risk_cash / diff) if diff > 0 else 0
                    st.markdown(f"""<div style='background:#111; padding:10px; border-radius:10px; border:1px solid #333; margin-top:10px; text-align:center;'>
                        KUP: <b style='color:#00ff88; font-size:1.2rem;'>{shares} szt.</b><br><small>{ai['u']}</small></div>""", unsafe_allow_html=True)
                except: pass
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Dodaj spółki w panelu bocznym. Upewnij się, że tickery są poprawne (np. NVDA, TSLA, PKO.WA).")
