# --- 1. KONFIGURACJA / IMPORTY ---
import os
import json
from datetime import datetime
import numpy as np
import pandas as pd
import requests
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from openai import OpenAI
import uuid
import time

# --- v16.9: MOBILE VIEW + PAGE CONFIG ---
st.set_page_config(
    page_title="Kombajn Giełdowy",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        padding-top: 0.5rem;
    }
    .stButton>button {
        width: 100%;
        font-size: 1.1rem;
        padding: 0.8rem;
    }
    .stSelectbox, .stTextInput, .stNumberInput {
        font-size: 1.1rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1.1rem;
        padding: 0.6rem;
    }
    .stDataFrame {
        font-size: 0.9rem;
    }
}
</style>
""", unsafe_allow_html=True)

# --- AUTO‑KEY ENGINE v16.8 ---
def auto_key(base: str) -> str:
    if "auto_keys" not in st.session_state:
        st.session_state["auto_keys"] = {}
    if base not in st.session_state["auto_keys"]:
        st.session_state["auto_keys"][base] = f"{base}_{uuid.uuid4().hex[:8]}"
    return st.session_state["auto_keys"][base]

# --- PATCH v16.8: TRWAŁE USTAWIENIA + AUTO‑REFRESH ---

defaults = {
    "account_size_v2": 10000.0,
    "risk_pct_v2": 1.0,
    "auto_refresh_minutes": 5,
    "last_refresh": time.time(),
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

st.sidebar.markdown("### 🔄 Auto‑refresh (1–15 min)")
st.session_state["auto_refresh_minutes"] = st.sidebar.slider(
    "Częstotliwość odświeżania (minuty)",
    1,
    15,
    st.session_state["auto_refresh_minutes"],
    key=auto_key("refresh_slider_minutes"),
)

# --- INIT SESSION STATE FOR MODULES 21+22 ---
for key, default in {
    "auto_v2_levels": {},
    "auto_v2_comment": {},
    "auto_v2_mode": {},
    "trades_log": [],
    "alerts": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

APP_TITLE = "AI ALPHA TERMINAL v16.9 PRO PL"
DB_FILE = "tickers_db.txt"

# --- 2. STYL / LAYOUT ---

st.markdown(
    """
    <style>
    .stApp { background-color: #050812; color: #c9d1d9; }
    .ticker-card { 
        background: radial-gradient(circle at top left, #111827, #020617); 
        padding: 20px; 
        border-radius: 16px; 
        border: 1px solid #1f2937; 
        margin-bottom: 24px; 
        box-shadow: 0 0 18px rgba(0,255,180,0.12);
    }
    .top-rank-card { 
        background: linear-gradient(135deg, #020617, #111827); 
        padding: 12px; 
        border-radius: 12px; 
        border: 1px solid #1f2937; 
        text-align: center;
        box-shadow: 0 0 12px rgba(56,189,248,0.25);
        min-height: 120px;
    }
    .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .neon-pill {
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.7rem;
        border: 1px solid rgba(56,189,248,0.6);
        color: #e5e7eb;
        background: rgba(15,23,42,0.9);
    }
    .fibo-box {
        font-size: 0.75rem;
        color: #e5e7eb;
        background: rgba(15,23,42,0.9);
        border-radius: 10px;
        padding: 8px 10px;
        border: 1px solid rgba(94,234,212,0.5);
        margin-top: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 3. FUNKCJE POMOCNICZE (UTILS) ---

def load_tickers(default: str = "PKO.WA, BTC-USD, NVDA, TSLA, BTCUSDT") -> str:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else default
        except Exception:
            return default
    return default

# --- 4. MARKET DATA / WSKAŹNIKI ---

class MarketData:
    @staticmethod
    def get_yf(symbol: str, period: str = "250d", interval: str = "1d") -> pd.DataFrame | None:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df

    @staticmethod
    def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["Close"]

        df["EMA20"] = close.ewm(span=20).mean()
        df["EMA50"] = close.ewm(span=50).mean()
        df["EMA200"] = close.ewm(span=200).mean()

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        df["MACD"] = ema12 - ema26
        df["MACD_signal"] = df["MACD"].ewm(span=9).mean()
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df["RSI"] = 100 - (100 / (1 + rs))

        return df

    @staticmethod
    def fibo_levels(df: pd.DataFrame):
        recent = df.tail(120)
        high = recent["High"].max()
        low = recent["Low"].min()
        diff = high - low
        levels = {
            "0.0%": high,
            "23.6%": high - 0.236 * diff,
            "38.2%": high - 0.382 * diff,
            "50.0%": high - 0.5 * diff,
            "61.8%": high - 0.618 * diff,
            "78.6%": high - 0.786 * diff,
            "100%": low,
        }
        return levels, high, low

    @staticmethod
    def simple_backtest(df: pd.DataFrame, strategy: str = "EMA_CROSS") -> dict:
        df = df.copy()
        df["ret"] = df["Close"].pct_change().fillna(0)

        if strategy == "EMA_CROSS":
            df["EMA20"] = df["Close"].ewm(span=20).mean()
            df["EMA50"] = df["Close"].ewm(span=50).mean()
            df["signal"] = 0
            df.loc[df["EMA20"] > df["EMA50"], "signal"] = 1
            df.loc[df["EMA20"] < df["EMA50"], "signal"] = -1
        elif strategy == "RSI":
            df["RSI"] = MarketData.compute_indicators(df)["RSI"]
            df["signal"] = 0
            df.loc[df["RSI"] < 30, "signal"] = 1
            df.loc[df["RSI"] > 70, "signal"] = -1
        elif strategy == "MACD":
            tmp = MarketData.compute_indicators(df)
            df["MACD"] = tmp["MACD"]
            df["MACD_signal"] = tmp["MACD_signal"]
            df["signal"] = 0
            df.loc[df["MACD"] > df["MACD_signal"], "signal"] = 1
            df.loc[df["MACD"] < df["MACD_signal"], "signal"] = -1
        else:
            df["signal"] = 0

        df["position"] = df["signal"].shift(1).fillna(0)
        df["strategy"] = df["position"] * df["ret"]
        equity = (1 + df["strategy"]).cumprod()
        total_ret = equity.iloc[-1] - 1
        max_dd = (equity.cummax() - equity).max()
        trades = (df["position"].diff().abs() > 0).sum()

        return {
            "total_return": float(total_ret * 100),
            "max_drawdown": float(max_dd * 100),
            "trades": int(trades),
        }

# --- 5. RISK ENGINE ---

class RiskEngine:
    def __init__(self, account_size: float):
        self.account_size = account_size

    def position_size_atr(
        self,
        price: float,
        atr: float,
        risk_pct: float,
        atr_mult: float = 1.5,
    ) -> dict:
        stop_distance = atr * atr_mult
        risk_amount = self.account_size * (risk_pct / 100)
        size = risk_amount / stop_distance if stop_distance > 0 else 0
        return {
            "stop_distance": float(stop_distance),
            "risk_amount": float(risk_amount),
            "size": float(size),
        }

    def compute_r_multiple(
        self,
        entry: float,
        stop: float,
        target: float,
        direction: str = "long",
    ) -> float | None:
        if direction == "long":
            risk = entry - stop
            reward = target - entry
        else:
            risk = stop - entry
            reward = entry - target
        if risk <= 0:
            return None
        return reward / risk

# --- 6. ALERT ENGINE ---

class AlertEngine:
    @staticmethod
    def send_webhook(url: str, payload: dict) -> int | None:
        try:
            r = requests.post(url, json=payload, timeout=3)
            return r.status_code
        except Exception:
            return None

    @staticmethod
    def send_telegram(bot_token: str, chat_id: str, text: str) -> int | None:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=3)
            return r.status_code
        except Exception:
            return None

# --- 7. AI KLIENT ---

class AIClient:
    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def chat(self, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content

    def chat_json(self, prompt: str):
        raw = self.chat(prompt)
        try:
            return json.loads(raw)
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(raw[start : end + 1])
                except Exception:
                    return {"raw": raw}
            return {"raw": raw}

# --- 8. SIDEBAR / USTAWIENIA ---

with st.sidebar:
    st.title("⚙️ TERMINAL v16.9 PRO PL")

    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("✅ OpenAI (Secrets)")
    else:
        api_key = st.text_input("OpenAI Key", type="password", key=auto_key("openai_key_input"))
        if not api_key:
            st.warning("Dodaj klucz w Secrets lub wpisz go tutaj.")

    ai_model = st.selectbox(
        "Model AI",
        [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1",
            "gpt-4.1-large",
        ],
        index=2,
        key=auto_key("ai_model_select"),
    )

    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers(), key=auto_key("tickers_input"))
    if st.button("Zapisz listę", key=auto_key("save_tickers_btn")):
        with open(DB_FILE, "w") as f:
            f.write(tickers_input)
        st.rerun()

    refresh = st.select_slider(
        "Odśwież (s)",
        options=[30, 60, 300],
        value=60,
        key=auto_key("refresh_seconds_slider"),
    )

    st.markdown("### 🔔 Alerty (log)")
    if "alerts" not in st.session_state:
        st.session_state["alerts"] = []
    for a in st.session_state["alerts"][-10:][::-1]:
        st.markdown(f"- <span class='neon-pill'>{a}</span>", unsafe_allow_html=True)

    st.markdown("### 🌐 Push config")
    webhook_url = st.text_input("Webhook URL (opcjonalnie)", key=auto_key("webhook_url"))
    tg_token = st.text_input("Telegram Bot Token (opcjonalnie)", type="password", key=auto_key("tg_token"))
    tg_chat_id = st.text_input("Telegram Chat ID (opcjonalnie)", key=auto_key("tg_chat_id"))

st_autorefresh(interval=refresh * 1000, key=auto_key("auto_refresh_v16"))

if not api_key:
    st.info("Wprowadź OpenAI API Key w pasku bocznym lub dodaj do Secrets.")
    st.stop()

ai = AIClient(api_key=api_key, model=ai_model)

# --- 9. INICJALIZACJA SESSION_STATE ---

for key, default in [
    ("portfolio", []),
    ("trades_log", []),
    ("lab_strategy", None),
    ("lab_desc", None),
    ("last_ai_signal", None),
    ("auto_analysis", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

# --- 10. POBRANIE DANYCH RYNKOWYCH (BLOK BAZOWY) ---

data_map: dict[str, dict] = {}
for sym in tickers:
    d1d = MarketData.get_yf(sym, "250d", "1d")
    d15 = MarketData.get_yf(sym, "5d", "15m")
    if d1d is None or d15 is None:
        continue

    d1d = MarketData.compute_indicators(d1d)
    d15 = MarketData.compute_indicators(d15)

    price = float(d15["Close"].iloc[-1])
    prev_close = float(d1d["Close"].iloc[-2])
    change_pct = (price - prev_close) / prev_close * 100
    sma200 = d1d["Close"].rolling(200).mean().iloc[-1]
    trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
    trend_color = "#22c55e" if price > sma200 else "#ef4444"
    atr = (d1d["High"] - d1d["Low"]).rolling(14).mean().iloc[-1]
    pivot = (d1d["High"].iloc[-2] + d1d["Low"].iloc[-2] + d1d["Close"].iloc[-2]) / 3
    rsi = float(d15["RSI"].iloc[-1])

    if rsi < 32:
        rec, rec_col = "KUPUJ", "#22c55e"
    elif rsi > 68:
        rec, rec_col = "SPRZEDAJ", "#ef4444"
        rec, rec_col = "CZEKAJ", "#8b949e"

    fibo, fib_high, fib_low = MarketData.fibo_levels(d1d)
    bt_ema = MarketData.simple_backtest(d1d, "EMA_CROSS")

    data_map[sym] = {
        "symbol": sym,
        "price": price,
        "change": change_pct,
        "rsi": rsi,
        "rec": rec,
        "rec_col": rec_col,
        "trend": trend_label,
        "trend_col": trend_color,
        "pivot": pivot,
        "tp": price + atr * 1.5,
        "sl": price - atr * 1.2,
        "atr": float(atr),
        "df_1d": d1d,
        "df_15": d15,
        "fibo": fibo,
        "backtest_ema": bt_ema,
    }

if not data_map:
    st.error("Brak danych dla podanych symboli.")
    st.stop()

symbols_available = list(data_map.keys())

# --- 11. TABS / GŁÓWNY DASHBOARD ---

tab_main, tab_strategy, tab_lab, tab_auto, tab_multi, tab_orderbook, tab_patterns, tab_portfolio, tab_risk_ai = st.tabs(
    [
        "📊 Główny",
        "🧮 Strategie & Backtest",
        "🧪 AI Strategy Lab",
        "🤖 AI Auto‑Trader",
        "⏱️ Multi‑Timeframe",
        "📚 Orderbook (Binance)",
        "🕯️ Formacje świecowe + AI",
        "📦 Portfolio & Risk",
        "🛡️ AI Risk & Hedging",
    ]
)

# --- 12. TAB: GŁÓWNY ---

with tab_main:
    st.subheader("🧊 HEATMAPA RYNKU")
    heat_df = pd.DataFrame(
        {
            "Symbol": [d["symbol"] for d in data_map.values()],
            "Change": [d["change"] for d in data_map.values()],
        }
    )
    fig_heat = go.Figure(
        data=go.Treemap(
            labels=heat_df["Symbol"],
            parents=[""] * len(heat_df),
            values=heat_df["Change"].abs() + 0.01,
            marker=dict(
                colors=heat_df["Change"],
                colorscale="RdYlGn",
                reversescale=True,
                line=dict(color="#020617", width=1),
            ),
            textinfo="label+value",
            hovertemplate="<b>%{label}</b><br>Zmiana: %{value:.2f}%<extra></extra>",
        )
    )
    fig_heat.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=260,
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
    )
    st.plotly_chart(fig_heat, use_container_width=True, key=auto_key("heatmap_main"))

    st.subheader("📊 MONITORING RYNKU")
    data_list = list(data_map.values())
    top_cols = st.columns(min(len(data_list), 5))
    for i, d in enumerate(sorted(data_list, key=lambda x: abs(x["change"]), reverse=True)[:10]):
        with top_cols[i % 5]:
            c_col = "#22c55e" if d["change"] >= 0 else "#ef4444"
            st.markdown(
                f"""
                <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                    <b>{d['symbol']}</b><br>
                    <span style="color:{c_col}; font-weight:bold; font-size:1.1rem;">{d['price']:.2f}</span><br>
                    <span style="font-size:0.8rem; color:{d['trend_col']};">{d['trend']}</span><br>
                    <div style="background:{d['rec_col']}; font-size:0.7rem; border-radius:999px; margin:6px 0; color:white; display:inline-block; padding:2px 10px;">
                        {d['rec']}
                    </div><br>
                    <span class="stat-label">Δ {d['change']:.2f}% | RSI: {d['rsi']:.1f}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.subheader("📈 Szczegóły")
    for d in data_list:
        st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1.1, 2.2])

        with c1:
            st.markdown(f"### {d['symbol']} ({d['trend']})")
            st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
            st.write(f"**Pivot:** {d['pivot']:.2f} | **RSI:** {d['rsi']:.1f}")
            st.write(f"**TP:** {d['tp']:.2f} | **SL:** {d['sl']:.2f}")

            bt = d["backtest_ema"]
            st.markdown(
                f"<span class='neon-pill'>Backtest EMA20/50: {bt['total_return']:.1f}% | DD: {bt['max_drawdown']:.1f}% | Trades: {bt['trades']}</span>",
                unsafe_allow_html=True,
            )

            fibo = d["fibo"]
            st.markdown("<div class='fibo-box'><b>Fibonacci (ostatnie 120 sesji)</b><br>", unsafe_allow_html=True)
            st.markdown("<br>".join([f"{lvl}: {val:.2f}" for lvl, val in fibo.items()]), unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with c2:
            df15 = d["df_15"].tail(120)
            fig = make_subplots(
                rows=3,
                cols=1,
                shared_xaxes=True,
                row_heights=[0.55, 0.2, 0.25],
                vertical_spacing=0.03,
            )

            fig.add_trace(
                go.Candlestick(
                    x=df15.index,
                    open=df15["Open"],
                    high=df15["High"],
                    low=df15["Low"],
                    close=df15["Close"],
                    name="Cena",
                    increasing_line_color="#22c55e",
                    decreasing_line_color="#ef4444",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )

            fig.add_trace(
                go.Scatter(
                    x=df15.index,
                    y=df15["EMA20"],
                    line=dict(color="#38bdf8", width=1.2),
                    name="EMA20",
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df15.index,
                    y=df15["EMA50"],
                    line=dict(color="#a855f7", width=1.1),
                    name="EMA50",
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df15.index,
                    y=df15["EMA200"],
                    line=dict(color="#f97316", width=1.1),
                    name="EMA200",
                ),
                row=1,
                col=1,
            )

            fig.add_trace(
                go.Bar(x=df15.index, y=df15["Volume"], marker_color="#4b5563", name="Volume"),
                row=2,
                col=1,
            )

            fig.add_trace(
                go.Scatter(
                    x=df15.index,
                    y=df15["MACD"],
                    line=dict(color="#22c55e", width=1),
                    name="MACD",
                ),
                row=3,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df15.index,
                    y=df15["MACD_signal"],
                    line=dict(color="#ef4444", width=1),
                    name="Signal",
                ),
                row=3,
                col=1,
            )
            fig.add_trace(
                go.Bar(
                    x=df15.index,
                    y=df15["MACD_hist"],
                    marker_color=np.where(df15["MACD_hist"] >= 0, "#22c55e", "#ef4444"),
                    name="Hist",
                ),
                row=3,
                col=1,
            )

            fig.update_layout(
                template="plotly_dark",
                height=420,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_rangeslider_visible=False,
                paper_bgcolor="#020617",
                plot_bgcolor="#020617",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(fig, use_container_width=True, key=auto_key(f"detail_{d['symbol']}"))

        st.markdown("</div>", unsafe_allow_html=True)

# --- 13. TAB: STRATEGIE & BACKTEST ---

with tab_strategy:
    st.subheader("🧮 Panel strategii & Backtest")
    col_s1, col_s2 = st.columns(2)

    with col_s1:
        sym = st.selectbox("Symbol", symbols_available, key=auto_key("strat_sym"))
        strat = st.selectbox("Strategia", ["EMA_CROSS", "RSI", "MACD"], key=auto_key("strat_type"))
        df = data_map[sym]["df_1d"]
        bt_res = MarketData.simple_backtest(df, strat)
        st.write(f"**Wynik backtestu ({strat}):**")
        st.write(f"- Zwrot: {bt_res['total_return']:.2f}%")
        st.write(f"- Max DD: {bt_res['max_drawdown']:.2f}%")
        st.write(f"- Liczba transakcji: {bt_res['trades']}")

    with col_s2:
        if st.button("🧠 AI: wygeneruj strategię (JSON, PL)", key=auto_key("ai_strategy_json")):
            prompt = """
            Wygeneruj agresywną strategię tradingową w formacie JSON po polsku.
            Wszystkie pola muszą być po polsku.

            Pola:
            - name
            - description
            - entry_rules
            - exit_rules
            - indicators
            - timeframe

            Zwróć TYLKO JSON.
            """
            js = ai.chat_json(prompt)
            st.json(js)

# --- 14. TAB: AI STRATEGY LAB ---

with tab_lab:
    st.subheader("🧪 AI Strategy Lab — generator, tester, Pine Script, Auto‑Optimizer (PL)")

    st.markdown("### 🧠 Generuj strategię AI (JSON, PL)")
    if st.button("Generuj strategię AI", key=auto_key("lab_gen")):
        prompt = """
        Wygeneruj agresywną strategię tradingową w formacie JSON po polsku.
        Wszystkie pola muszą być po polsku.
        """
        st.session_state["lab_strategy"] = ai.chat_json(prompt)

    if st.session_state.get("lab_strategy"):
        st.json(st.session_state["lab_strategy"])

        st.markdown("### ✏️ Edytuj strategię AI (JSON)")
        edited = st.text_area(
            "Edytuj JSON strategii",
            json.dumps(st.session_state["lab_strategy"], indent=4, ensure_ascii=False),
            height=260,
            key=auto_key("lab_editor"),
        )
        if st.button("Zapisz zmiany", key=auto_key("lab_save")):
            try:
                st.session_state["lab_strategy"] = json.loads(edited)
                st.success("Zapisano strategię.")
            except Exception:
                st.error("Błąd w JSON.")

        st.markdown("### 🧪 Przetestuj strategię AI na danych")
        sym_lab = st.selectbox("Symbol", symbols_available, key=auto_key("lab_sym_test"))
        df_lab = data_map[sym_lab]["df_1d"]

        if st.button("Uruchom backtest AI", key=auto_key("lab_bt")):
            strat = st.session_state["lab_strategy"]
            df_bt = df_lab.copy()
            df_bt["signal"] = 0

            if "EMA" in " ".join(strat.get("indicators", [])):
                df_bt["EMA20"] = df_bt["Close"].ewm(span=20).mean()
                df_bt["EMA50"] = df_bt["Close"].ewm(span=50).mean()
                df_bt.loc[df_bt["EMA20"] > df_bt["EMA50"], "signal"] = 1
                df_bt.loc[df_bt["EMA20"] < df_bt["EMA50"], "signal"] = -1

            if "RSI" in " ".join(strat.get("indicators", [])):
                df_bt["RSI"] = MarketData.compute_indicators(df_bt)["RSI"]
                df_bt.loc[df_bt["RSI"] < 30, "signal"] = 1
                df_bt.loc[df_bt["RSI"] > 70, "signal"] = -1

            df_bt["position"] = df_bt["signal"].shift(1).fillna(0)
            df_bt["ret"] = df_bt["Close"].pct_change().fillna(0)
            df_bt["strategy"] = df_bt["position"] * df_bt["ret"]
            equity = (1 + df_bt["strategy"]).cumprod()

            st.line_chart(equity)
            st.write(f"Zwrot: {(equity.iloc[-1] - 1) * 100:.2f}%")
            st.write(f"Max DD: {(equity.cummax() - equity).max() * 100:.2f}%")

        st.markdown("### 🧬 AI Auto‑Optimizer (PL)")
        if st.button("Optymalizuj strategię AI", key=auto_key("lab_opt")):
            prompt = f"""
            Popraw strategię JSON pod kątem:
            - lepszego R/R
            - mniejszego DD
            - agresywniejszych wejść

            Strategia:
            {json.dumps(st.session_state["lab_strategy"], indent=4, ensure_ascii=False)}

            Zwróć TYLKO JSON.
            """
            st.session_state["lab_strategy"] = ai.chat_json(prompt)
            st.success("Strategia zoptymalizowana.")
            st.json(st.session_state["lab_strategy"])

        st.markdown("### 📜 Generuj Pine Script")
        if st.button("Generuj Pine Script", key=auto_key("lab_pine")):
            prompt = """
            Zamień tę strategię JSON na kod Pine Script v5.
            Zwróć TYLKO kod.
            """
            code = ai.chat(prompt)
            st.code(code, language="pine")


koniec
