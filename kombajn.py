# =========================================================
# NEON SENTINEL PRO v100 — FULL SYSTEM FIXED
# =========================================================

import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import time
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# =========================================================
# 1. SESSION STATE & CONFIG
# =========================================================

# Funkcja pomocnicza chroniąca przed AttributeError w wątkach
def ensure_state_lists():
    for key in ["ai_logs", "ai_errors", "ai_results"]:
        if key not in st.session_state:
            st.session_state[key] = [] if "log" in key or "error" in key else {}

DEFAULTS = {
    "risk_cap": 10000.0,
    "risk_pct": 2.0,
    "ai_results": {},
    "alerts": {},
    "portfolio": None,
    "ai_logs": [],
    "ai_errors": [],
    "ai_batch_time": None,
    "ai_batch_count": 0,
    "ai_bad_tickers": [],
    "ai_mode": False,
    "dry_run": False,
    "batch_limit": 50,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

DB_FILE = "moje_spolki.txt"
PORTFOLIO_FILE = "portfolio.json"

st.set_page_config(
    page_title="NEON SENTINEL PRO v100",
    page_icon="⚡",
    layout="wide"
)

key = st.secrets.get("OPENAI_API_KEY", "")

# =========================================================
# 2. CSS — NEON DARK STYLE
# =========================================================

st.markdown("""
<style>
.stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
.neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 25px; border-radius: 20px; margin-bottom: 30px; }
.status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 10px; }
.status-sell { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; border: 2px solid #ff0055; padding: 5px 15px; border-radius: 10px; }
.status-hold { color: #58a6ff; text-shadow: 0 0 10px #58a6ff; font-weight: bold; border: 2px solid #58a6ff; padding: 5px 15px; border-radius: 10px; }
.tp-box { border: 1px solid #00ff88; padding: 12px; border-radius: 10px; color: #00ff88; text-align: center; background: rgba(0,255,136,0.1); font-weight: bold; }
.sl-box { border: 1px solid #ff0055; padding: 12px; border-radius: 10px; color: #ff0055; text-align: center; background: rgba(255,0,85,0.1); font-weight: bold; }
.top-tile { background: #111; border: 1px solid #333; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #58a6ff; }
.score-badge { margin-top:6px; display:inline-block; padding:4px 10px; border-radius:999px; font-size:0.8rem; border:1px solid #58a6ff; color:#58a6ff; }
.alert-badge { display:inline-block; margin-top:6px; font-size:0.75rem; color:#ffcc00; }
.ai-log-box { background:#111; padding:15px; border-radius:10px; border:1px solid #333; margin-bottom:10px; font-size:0.8rem; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 3. HELPERS
# =========================================================

def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "NVDA, TSLA, BTC-USD, PKO.WA"

def load_portfolio():
    if st.session_state.portfolio is not None:
        return st.session_state.portfolio
    if not os.path.exists(PORTFOLIO_FILE):
        st.session_state.portfolio = {"positions": [], "history": [], "value_history": []}
        return st.session_state.portfolio
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            st.session_state.portfolio = json.load(f)
    except:
        st.session_state.portfolio = {"positions": [], "history": [], "value_history": []}
    return st.session_state.portfolio

def save_portfolio(p):
    st.session_state.portfolio = p
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=4)

# =========================================================
# 4. SIDEBAR
# =========================================================

with st.sidebar:
    st.title("⚡ PRO v100 — Panel Sterowania")

    st.session_state.ai_mode = st.checkbox("AI Mode (ON/OFF)", value=st.session_state.ai_mode)
    st.session_state.dry_run = st.checkbox("Dry‑run (bez yfinance)", value=st.session_state.dry_run)
    st.session_state.batch_limit = st.number_input("Limit batcha (max tickers):", 1, 200, int(st.session_state.batch_limit))

    st.markdown("---")

    t_in = st.text_area("Lista Symboli:", value=load_tickers(), height=150)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Zapisz listę"):
            with open(DB_FILE, "w", encoding="utf-8") as f:
                f.write(t_in)
            st.success("Zapisano listę tickerów.")

    with col2:
        if st.button("🧹 Reset AI Cache"):
            st.session_state.ai_results = {}
            st.session_state.ai_logs = []
            st.session_state.ai_errors = []
            st.session_state.ai_bad_tickers = []
            st.rerun()

    st.markdown("---")
    st.subheader("📡 AI LOGS (Live)")

    if st.session_state.ai_logs:
        for log in st.session_state.ai_logs[-10:]:
            st.markdown(f"<div class='ai-log-box'>{log}</div>", unsafe_allow_html=True)
    else:
        st.info("Brak logów AI.")

    st_autorefresh(interval=60000, key="v100_ref")

# =========================================================
# 5. TABS
# =========================================================

tab_dashboard, tab_ai_logs, tab_ai_settings, tab_compare, tab_biotech, tab_portfolio, tab_system = st.tabs([
    "📊 Dashboard",
    "🧠 AI Logs",
    "⚙️ AI Settings",
    "⚔️ Comparison Mode",
    "🧬 Biotech Radar",
    "💼 Portfolio",
    "🛠 System"
])

# =========================================================
# 6. AI ENGINE
# =========================================================

def log_ai(msg):
    ensure_state_lists()
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.ai_logs.append(f"[{ts}] {msg}")

def log_error(msg):
    ensure_state_lists()
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.ai_errors.append(f"[{ts}] {msg}")

def run_ai_single(d, key):
    try:
        ensure_state_lists()
        if not key:
            return None

        client = OpenAI(api_key=key)

        prompt = (
            f"Analiza {d['symbol']} @ {d['price']}.\n"
            f"DATA: RSI {d['rsi']:.1f}, High {d['high']}, Low {d['low']}, "
            f"Pivot {d['pp']:.2f}, MA50 {d['ma50']:.2f}, MA200 {d['ma200']:.2f}.\n"
            f"Zwróć JSON: { '{\"w\":\"\",\"sl\":0,\"tp\":0,\"score\":0,\"uzas\":\"\"}' }"
        )

        log_ai(f"AI start → {d['symbol']}")

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        # POPRAWKA: Prawidłowe odwołanie do zawartości wiadomości
        res = json.loads(resp.choices[0].message.content)

        if "score" not in res:
            res["score"] = int(max(0, min(100, 100 - abs(d["rsi"] - 50) * 2)))

        st.session_state.ai_results[d["symbol"]] = res
        log_ai(f"AI OK → {d['symbol']} (score {res['score']})")
        return res

    except Exception as e:
        log_error(f"AI ERROR → {d['symbol']}: {e}")
        st.session_state.ai_bad_tickers.append(d["symbol"])
        return None

# =========================================================
# 7. DATA FETCH
# =========================================================

def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol):
    try:
        # W wątku NIE używamy log_error do session_state (to wywala błąd)
        symbol = symbol.strip().upper()
        if st.session_state.dry_run:
            return {"symbol": symbol, "price": 0.0, "rsi": 50.0, "high": 0.0, "low": 0.0, "pp": 0.0, "ma50": 0.0, "ma200": 0.0, "change": 0.0, "df": pd.DataFrame()}
        
        t = yf.Ticker(symbol)
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        df = fix_col(df)
        
        p = float(df['Close'].iloc[-1])
        ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
        ma200 = float(df['Close'].rolling(200).mean().iloc[-1])
        h_prev, l_prev, c_prev = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
        pp = (h_prev + l_prev + c_prev) / 3
        
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = float(100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1])
        
        return {
            "symbol": symbol, "price": p, "rsi": rsi, "high": df['High'].iloc[-1], "low": df['Low'].iloc[-1],
            "pp": pp, "ma50": ma50, "ma200": ma200, "change": ((p - c_prev) / c_prev * 100), "df": df.tail(60)
        }
    except:
        return None

# --- GŁÓWNA LOGIKA DASHBOARDU ---
with tab_dashboard:
    symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
    with ThreadPoolExecutor(max_workers=10) as executor:
        data_list = [d for d in list(executor.map(get_data, symbols)) if d is not None]

    if data_list:
        st.subheader("🔥 Top 5 Okazji (RSI)")
        cols = st.columns(5)
        for i, r in enumerate(sorted(data_list, key=lambda x: x['rsi'])[:5]):
            with cols[i]:
                st.markdown(f"<div class='top-tile'><b>{r['symbol']}</b><br>RSI: {r['rsi']:.1f}</div>", unsafe_allow_html=True)

        st.divider()

        for d in data_list:
            ai = run_ai_single(d, key) if st.session_state.ai_mode else st.session_state.ai_results.get(d['symbol'])
            
            st.markdown('<div class="neon-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1.2])
            
            with c1:
                st.subheader(d['symbol'])
                if ai:
                    v_class = "status-buy" if "KUP" in str(ai.get('w','')).upper() else "status-sell" if "SPRZEDAJ" in str(ai.get('w','')).upper() else "status-hold"
                    st.markdown(f'<span class="{v_class}">{ai.get("w","ANALIZA...")}</span>', unsafe_allow_html=True)
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"RSI: {d['rsi']:.1f} | Pivot: {d['pp']:.2f}")

            with c2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"fig_{d['symbol']}")

            with c3:
                if ai:
                    st.markdown(f'<div class="tp-box">TP: {ai.get("tp",0)}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="sl-box">SL: {ai.get("sl",0)}</div>', unsafe_allow_html=True)
                    st.write(f"**Uzasadnienie:** {ai.get('uzas','')}")
                    risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
                    diff = abs(d['price'] - float(ai.get('sl', d['price']*0.95)))
                    shares = int(risk_val / diff) if diff > 0 else 0
                    st.write(f"KUP: **{shares} szt.**")
            st.markdown('</div>', unsafe_allow_html=True)

# Puste sekcje dla zachowania struktury v100
with tab_ai_logs: st.write(st.session_state.ai_logs)
with tab_portfolio: st.write(load_portfolio())
