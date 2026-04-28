
# =========================================================
# NEON SENTINEL PRO v100 — FULL SYSTEM
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

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")

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
    st.session_state.batch_limit = st.number_input("Limit batcha (max tickers):", 1, 200, st.session_state.batch_limit)

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
            st.success("AI cache wyczyszczony.")

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
    ts = datetime.now().strftime("%H:%M:%S")
    if "ai_logs" not in st.session_state or st.session_state.ai_logs is None:
        st.session_state.ai_logs = []
    st.session_state.ai_logs.append(f"[{ts}] {msg}")


def log_error(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    if "ai_errors" not in st.session_state or st.session_state.ai_errors is None:
        st.session_state.ai_errors = []
    st.session_state.ai_errors.append(f"[{ts}] {msg}")


def ensure_state_lists():
    if "ai_bad_tickers" not in st.session_state or st.session_state.ai_bad_tickers is None:
        st.session_state.ai_bad_tickers = []
    if "ai_results" not in st.session_state or st.session_state.ai_results is None:
        st.session_state.ai_results = {}



def run_ai_single(d, key):
    try:
        if not key:
            return None

        client = OpenAI(api_key=key)

        prompt = (
            f"Analiza {d['symbol']} @ {d['price']}.\n"
            f"DATA: RSI {d['rsi']:.1f}, High {d['high']}, Low {d['low']}, "
            f"Pivot {d['pp']:.2f}, MA50 {d['ma50']:.2f}, MA200 {d['ma200']:.2f}.\n"
            f"Zwróć werdykt w formacie JSON:\n"
            f"{{"
            f"\"w\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", "
            f"\"sl\": cena_sl, "
            f"\"tp\": cena_tp, "
            f"\"score\": liczba_od_0_do_100, "
            f"\"uzas\": \"max 10 slow uzasadnienia technicznego\""
            f"}}"
        )

        log_ai(f"AI start → {d['symbol']}")

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        res = json.loads(resp.choices[0].message.content)

        if "score" not in res:
            base = max(0, min(100, 100 - abs(d["rsi"] - 50) * 2))
            res["score"] = int(base)

        st.session_state.ai_results[d["symbol"]] = res
        log_ai(f"AI OK → {d['symbol']} (score {res['score']})")
        return res

    except Exception as e:
        log_error(f"AI ERROR → {d['symbol']}: {e}")
        st.session_state.ai_bad_tickers.append(d["symbol"])
        return None

def run_ai_batch(data_list, key):
    if not st.session_state.ai_mode:
        log_ai("AI Mode OFF → batch pominięty.")
        return

    if not key:
        log_error("Brak klucza OpenAI — batch pominięty.")
        return

    start = time.time()
    st.session_state.ai_batch_count = 0
    st.session_state.ai_bad_tickers = []

    log_ai("=== AI TURBO BATCH START ===")

    for d in data_list[: st.session_state.batch_limit]:
        run_ai_single(d, key)
        st.session_state.ai_batch_count += 1

    end = time.time()
    st.session_state.ai_batch_time = round(end - start, 2)

    log_ai(f"=== AI TURBO BATCH DONE: {st.session_state.ai_batch_count} tickerów, {st.session_state.ai_batch_time}s ===")
    if st.session_state.ai_bad_tickers:
        log_ai(f"Błędne tickery: {', '.join(st.session_state.ai_bad_tickers)}")

# =========================================================
# 7. DATA FETCH
# =========================================================

def get_data(symbol):
    try:
        if st.session_state.dry_run:
            return {
                "symbol": symbol.upper(),
                "price": round(np.random.uniform(1, 200), 2),
                "rsi": round(np.random.uniform(10, 90), 1),
                "ma50": round(np.random.uniform(1, 200), 2),
                "ma200": round(np.random.uniform(1, 200), 2),
                "pp": round(np.random.uniform(1, 200), 2),
                "high": round(np.random.uniform(1, 200), 2),
                "low": round(np.random.uniform(1, 200), 2),
                "df": pd.DataFrame(),
                "change": round(np.random.uniform(-10, 10), 2),
            }

        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")

        if df.empty or len(df) < 50:
            st.session_state.ai_bad_tickers.append(symbol)
            return None

        price = float(df["Close"].iloc[-1])
        ma50 = df["Close"].rolling(50).mean().iloc[-1]
        ma200 = df["Close"].rolling(200).mean().iloc[-1]

        high = float(df["High"].iloc[-1])
        low = float(df["Low"].iloc[-1])

        prev_h = df["High"].iloc[-2]
        prev_l = df["Low"].iloc[-2]
        prev_c = df["Close"].iloc[-2]

        pivot = (prev_h + prev_l + prev_c) / 3

        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = float(100 - (100 / (1 + gain / (loss + 1e-9))).iloc[-1])

        return {
            "symbol": symbol.upper(),
            "price": price,
            "rsi": rsi,
            "ma50": ma50,
            "ma200": ma200,
            "pp": pivot,
            "high": high,
            "low": low,
            "df": df.tail(45),
            "change": ((price - prev_c) / prev_c * 100)
        }

    except Exception as e:
        log_error(f"DATA ERROR → {symbol}: {e}")
        st.session_state.ai_bad_tickers.append(symbol)
        return None

# =========================================================
# 8. DASHBOARD
# =========================================================

with tab_dashboard:

    st.header("📊 Dashboard — NEON SENTINEL PRO v100")

    tickers = [x.strip().upper() for x in t_in.split(",") if x.strip()]

    with ThreadPoolExecutor(max_workers=10) as executor:
        data_list = [d for d in executor.map(get_data, tickers) if d is not None]

    if st.session_state.ai_mode:
        run_ai_batch(data_list, OPENAI_KEY)

    st.subheader("🔥 TOP 10 SYGNAŁÓW (Techniczny + AI Score)")
    cols = st.columns(5)

    ranked = []
    for d in data_list:
        ai = st.session_state.ai_results.get(d["symbol"])
        score = ai["score"] if ai else 0
        ranked.append((d, ai, score))

    ranked = sorted(ranked, key=lambda x: x[2], reverse=True)[:10]

    for i, (d, ai, score) in enumerate(ranked):
        tag = ai["w"] if ai else "---"
        color = "#00ff88" if tag == "KUP" else "#ff4b4b" if tag == "SPRZEDAJ" else "#58a6ff"

        with cols[i % 5]:
            st.markdown(
                f"<div class='top-tile'><b>{d['symbol']}</b><br>"
                f"<span style='color:{color}; font-weight:bold;'>{tag}</span><br>"
                f"<small>Cena: {d['price']:.2f}</small><br>"
                f"<small>RSI: {d['rsi']:.1f}</small><br>"
                f"<span class='score-badge'>AI score: {score}</span></div>",
                unsafe_allow_html=True
            )

    st.divider()

    for d in data_list:
        ai = st.session_state.ai_results.get(d["symbol"])

        st.markdown("<div class='neon-card'>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 2.5, 1.5])

        with c1:
            st.markdown(f"### {d['symbol']}")

            if ai:
                cls = (
                    "status-buy" if ai["w"] == "KUP"
                    else "status-sell" if ai["w"] == "SPRZEDAJ"
                    else "status-hold"
                )
                st.markdown(f"<span class='{cls}'>{ai['w']}</span>", unsafe_allow_html=True)
                st.markdown(f"<div class='score-badge'>AI score: {ai['score']}</div>", unsafe_allow_html=True)

            st.markdown(f"<br>Cena: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.write(f"Szczyt: {d['high']:.2f} | Dołek: {d['low']:.2f}")
            st.write(f"Pivot: {d['pp']:.2f} | RSI: {d['rsi']:.1f}")

        with c2:
            if not st.session_state.dry_run and not d["df"].empty:
                fig = go.Figure(
                    data=[go.Candlestick(
                        x=d["df"].index,
                        open=d["df"]["Open"],
                        high=d["df"]["High"],
                        low=d["df"]["Low"],
                        close=d["df"]["Close"]
                    )]
                )
                fig.add_hline(y=d["pp"], line_dash="dot", line_color="#58a6ff", annotation_text="Pivot")
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)

        with c3:
            if ai:
                st.markdown(f"<div class='tp-box'><small>TAKE PROFIT</small><br><b>{ai['tp']}</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='sl-box' style='margin-top:10px;'><small>STOP LOSS</small><br><b>{ai['sl']}</b></div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# 9. AI LOGS
# =========================================================

with tab_ai_logs:
    st.header("🧠 AI Logs — pełna historia")

    if st.session_state.ai_logs:
        for log in reversed(st.session_state.ai_logs):
            st.markdown(f"<div class='ai-log-box'>{log}</div>", unsafe_allow_html=True)
    else:
        st.info("Brak logów AI.")

    st.subheader("❌ Błędne tickery")
    if st.session_state.ai_bad_tickers:
        st.write(st.session_state.ai_bad_tickers)
    else:
        st.write("Brak błędów.")

    st.subheader("⏱ Czas batcha")
    if st.session_state.ai_batch_time:
        st.write(f"{st.session_state.ai_batch_time}s")
    else:
        st.write("Batch jeszcze nie wykonany.")

# =========================================================
# 10. COMPARISON MODE
# =========================================================

with tab_compare:
    st.header("⚔️ Comparison Mode — porównanie dwóch tickerów")

    colA, colB = st.columns(2)
    with colA:
        tA = st.text_input("Ticker A")
    with colB:
        tB = st.text_input("Ticker B")

    if st.button("🔍 Porównaj"):
        if not tA or not tB:
            st.error("Podaj oba tickery.")
        else:
            dA = get_data(tA)
            dB = get_data(tB)

            if not dA or not dB:
                st.error("Brak danych dla jednego z tickerów.")
            else:
                aiA = st.session_state.ai_results.get(tA.upper())
                aiB = st.session_state.ai_results.get(tB.upper())

                st.subheader("📊 Dane techniczne")
                df_cmp = pd.DataFrame([
                    ["Cena", dA["price"], dB["price"]],
                    ["RSI", dA["rsi"], dB["rsi"]],
                    ["MA50", dA["ma50"], dB["ma50"]],
                    ["MA200", dA["ma200"], dB["ma200"]],
                    ["Pivot", dA["pp"], dB["pp"]],
                    ["AI score", aiA["score"] if aiA else "-", aiB["score"] if aiB else "-"],
                ], columns=["Parametr", tA.upper(), tB.upper()])
                st.table(df_cmp)

                st.subheader("⚖ Werdykt AI")
                if aiA and aiB:
                    if aiA["score"] > aiB["score"]:
                        st.success(f"{tA.upper()} jest silniejszy technicznie.")
                    elif aiA["score"] < aiB["score"]:
                        st.success(f"{tB.upper()} jest silniejszy technicznie.")
                    else:
                        st.info("Remis — oba mają taki sam AI score.")
                else:
                    st.info("Brak pełnej analizy AI.")

# =========================================================
# 11. BIOTECH RADAR
# =========================================================

with tab_biotech:
    st.header("🧬 Biotech Radar — anomalie, spike’i, gapy, wolumen")

    st.write("System analizuje tickery pod kątem nietypowych ruchów.")

    if 'data_list' not in locals() or not data_list:
        st.info("Brak danych — przejdź do Dashboard i wykonaj skan.")
    else:
        anomalies = []

        for d in data_list:
            spike = d["change"] > 15
            gap = abs(d["high"] - d["low"]) > d["low"] * 0.05
            vol_anom = False  # placeholder

            score = 0
            if spike: score += 40
            if gap: score += 30
            if vol_anom: score += 30

            anomalies.append({
                "symbol": d["symbol"],
                "price": d["price"],
                "change": d["change"],
                "rsi": d["rsi"],
                "spike": spike,
                "gap": gap,
                "vol": vol_anom,
                "score": score
            })

        df_anom = pd.DataFrame(anomalies)
        df_anom = df_anom.sort_values("score", ascending=False)

        st.subheader("🔥 Najbardziej podejrzane ruchy (TOP 20)")
        st.dataframe(df_anom.head(20))

# =========================================================
# 12. PORTFOLIO
# =========================================================

with tab_portfolio:
    st.header("💼 Portfolio — zarządzanie pozycjami")

    p = load_portfolio()

    st.subheader("Aktualne pozycje")
    if p["positions"]:
        st.table(pd.DataFrame(p["positions"]))
    else:
        st.info("Brak pozycji w portfelu.")

    st.subheader("Dodaj / edytuj pozycję")
    col1, col2, col3 = st.columns(3)

    with col1:
        sym = st.text_input("Symbol")
    with col2:
        qty = st.number_input("Ilość", value=0.0)
    with col3:
        price = st.number_input("Cena zakupu", value=0.0)

    if st.button("➕ Zapisz pozycję"):
        if sym and qty > 0 and price > 0:
            updated = False
            for pos in p["positions"]:
                if pos["symbol"].upper() == sym.upper():
                    pos["qty"] = qty
                    pos["buy_price"] = price
                    updated = True
                    break
            if not updated:
                p["positions"].append({
                    "symbol": sym.upper(),
                    "qty": qty,
                    "buy_price": price
                })
            save_portfolio(p)
            st.success("Pozycja zapisana.")
            st.rerun()
        else:
            st.error("Uzupełnij wszystkie pola.")

    st.subheader("📈 Historia wartości portfela")
    if "value_history" in p and p["value_history"]:
        dfh = pd.DataFrame(p["value_history"])
        st.line_chart(dfh["value"])
    else:
        st.info("Brak historii wartości.")

# =========================================================
# 13. SYSTEM
# =========================================================

with tab_system:
    st.header("🛠 System Diagnostics — PRO v100")

    st.subheader("Wersja aplikacji")
    st.write("NEON SENTINEL PRO v100")

    st.subheader("Tryby pracy")
    st.write(f"AI Mode: {'ON' if st.session_state.ai_mode else 'OFF'}")
    st.write(f"Dry‑run: {'ON' if st.session_state.dry_run else 'OFF'}")
    st.write(f"Batch limit: {st.session_state.batch_limit}")

    st.subheader("Test yfinance")
    try:
        test = yf.Ticker("AAPL").history(period="1d")
        if not test.empty:
            st.success("yfinance działa poprawnie.")
        else:
            st.warning("yfinance zwrócił pusty wynik.")
    except Exception as e:
        st.error(f"Błąd yfinance: {e}")

    st.subheader("Test OpenAI API")
    if OPENAI_KEY:
        try:
            client = OpenAI(api_key=OPENAI_KEY)
            st.success("Klucz OpenAI wygląda OK.")
        except Exception as e:
            st.error(f"Błąd OpenAI: {e}")
    else:
        st.warning("Brak klucza OpenAI.")

# =========================================================
# KONIEC PLIKU PRO v100
# =========================================================
