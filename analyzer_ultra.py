
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

APP_TITLE = "AI ALPHA TERMINAL v16 PRO PL"
DB_FILE = "tickers_db.txt"


# --- 2. STYL / LAYOUT ---

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")

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
    st.title("⚙️ TERMINAL v16 PRO PL")

    # --- API KEY ---
    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("✅ OpenAI (Secrets)")
    else:
        api_key = st.text_input("OpenAI Key", type="password")
        if not api_key:
            st.warning("Dodaj klucz w Secrets lub wpisz go tutaj.")

    # --- WYBÓR MODELU AI ---
    ai_model = st.selectbox(
        "Model AI",
        [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1",
            "gpt-4.1-large",
        ],
        index=1,
    )

    # --- LISTA TICKERÓW ---
    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f:
            f.write(tickers_input)
        st.rerun()

    # --- AUTOREFRESH ---
    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

    # --- ALERTY ---
    st.markdown("### 🔔 Alerty (log)")
    if "alerts" not in st.session_state:
        st.session_state["alerts"] = []
    for a in st.session_state["alerts"][-10:][::-1]:
        st.markdown(f"- <span class='neon-pill'>{a}</span>", unsafe_allow_html=True)

    # --- PUSH CONFIG ---
    st.markdown("### 🌐 Push config")
    webhook_url = st.text_input("Webhook URL (opcjonalnie)")
    tg_token = st.text_input("Telegram Bot Token (opcjonalnie)", type="password")
    tg_chat_id = st.text_input("Telegram Chat ID (opcjonalnie)")

# --- AUTOREFRESH ---
st_autorefresh(interval=refresh * 1000, key="auto_refresh_v16")

# --- API KEY CHECK ---
if not api_key:
    st.info("Wprowadź OpenAI API Key w pasku bocznym lub dodaj do Secrets.")
    st.stop()

# --- AI CLIENT ---
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
    else:
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

# --- SZKIELET TABS (WYPEŁNIMY W CZĘŚCI 2/3/4) ---

tab_main, tab_strategy, tab_lab, tab_auto, tab_multi, tab_orderbook, tab_patterns, tab_portfolio = st.tabs(
    [
        "📊 Główny",
        "🧮 Strategie & Backtest",
        "🧪 AI Strategy Lab",
        "🤖 AI Auto‑Trader",
        "⏱️ Multi‑Timeframe",
        "📚 Orderbook (Binance)",
        "🕯️ Formacje świecowe + AI",
        "📦 Portfolio & Risk",
    ]
)

with tab_main:
    st.subheader("📊 Główny — szkielet v16 (wypełnimy w części 2)")
    st.write("Dane zostały pobrane poprawnie. Moduły wizualizacji i AI dojdą w kolejnych częściach.")

with tab_strategy:
    st.subheader("🧮 Strategie & Backtest — szkielet v16")
    st.write("Panel strategii zostanie rozbudowany w części 2/3.")

with tab_lab:
    st.subheader("🧪 AI Strategy Lab — szkielet v16")
    st.write("Pełny AI Strategy Lab (PL) dojdzie w części 2.")

with tab_auto:
    st.subheader("🤖 AI Auto‑Trader — szkielet v16")
    st.write("Auto‑Trader v2 + poziomy SL/TP 1‑2‑3 dojdą w części 2/4.")

with tab_multi:
    st.subheader("⏱️ Multi‑Timeframe — szkielet v16")
    st.write("Dashboard multi‑TF przeniesiemy i ulepszymy w części 2.")

with tab_orderbook:
    st.subheader("📚 Orderbook (Binance) — szkielet v16")
    st.write("Orderbook zostanie przeniesiony i dopracowany w części 2.")

with tab_patterns:
    st.subheader("🕯️ Formacje świecowe + AI — szkielet v16")
    st.write("Zaawansowane AI Pattern Recognition PRO dojdzie w części 2/3.")

with tab_portfolio:
    st.subheader("📦 Portfolio & Risk — szkielet v16")
    st.write("Portfolio, RiskEngine i przyszły AI Portfolio Optimizer dojdą w części 3.")
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
    st.plotly_chart(fig_heat, use_container_width=True, key="heatmap_main")

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
            st.plotly_chart(fig, use_container_width=True, key=f"detail_{d['symbol']}")

        st.markdown("</div>", unsafe_allow_html=True)

# --- 13. TAB: STRATEGIE & BACKTEST ---

with tab_strategy:
    st.subheader("🧮 Panel strategii & Backtest")
    col_s1, col_s2 = st.columns(2)

    with col_s1:
        sym = st.selectbox("Symbol", symbols_available, key="strat_sym")
        strat = st.selectbox("Strategia", ["EMA_CROSS", "RSI", "MACD"], key="strat_type")
        df = data_map[sym]["df_1d"]
        bt_res = MarketData.simple_backtest(df, strat)
        st.write(f"**Wynik backtestu ({strat}):**")
        st.write(f"- Zwrot: {bt_res['total_return']:.2f}%")
        st.write(f"- Max DD: {bt_res['max_drawdown']:.2f}%")
        st.write(f"- Liczba transakcji: {bt_res['trades']}")

    with col_s2:
        if st.button("🧠 AI: wygeneruj strategię (JSON, PL)", key="ai_strategy_json"):
            prompt = """
            Wygeneruj agresywną strategię tradingową w formacie JSON po polsku.
            Wszystkie pola muszą być po polsku.

            Pola:
            - name (string, po polsku)
            - description (string, po polsku)
            - entry_rules (lista krótkich zasad po polsku)
            - exit_rules (lista krótkich zasad po polsku)
            - indicators (lista nazw wskaźników po polsku lub standardowych nazw angielskich)
            - timeframe (np. 1m, 5m, 15m, 1h, 1d)

            Zwróć TYLKO JSON.
            """
            js = ai.chat_json(prompt)
            st.json(js)

# --- 14. TAB: AI STRATEGY LAB ---

with tab_lab:
    st.subheader("🧪 AI Strategy Lab — generator, tester, Pine Script, Auto‑Optimizer (PL)")

    st.markdown("### 🧠 Generuj strategię AI (JSON, PL)")
    if st.button("Generuj strategię AI", key="lab_gen"):
        prompt = """
        Wygeneruj agresywną strategię tradingową w formacie JSON po polsku.
        Wszystkie pola muszą być po polsku.

        Pola:
        - name (string, po polsku)
        - description (string, po polsku)
        - entry_rules (lista krótkich zasad po polsku)
        - exit_rules (lista krótkich zasad po polsku)
        - indicators (lista nazw wskaźników po polsku lub standardowych nazw angielskich)
        - timeframe (np. 1m, 5m, 15m, 1h, 1d)

        Zwróć TYLKO JSON.
        """
        st.session_state["lab_strategy"] = ai.chat_json(prompt)

    if st.session_state["lab_strategy"]:
        st.json(st.session_state["lab_strategy"])

        st.markdown("### ✏️ Edytuj strategię AI (JSON)")
        edited = st.text_area(
            "Edytuj JSON strategii",
            json.dumps(st.session_state["lab_strategy"], indent=4, ensure_ascii=False),
            height=260,
            key="lab_editor",
        )
        if st.button("Zapisz zmiany", key="lab_save"):
            try:
                st.session_state["lab_strategy"] = json.loads(edited)
                st.success("Zapisano strategię.")
            except Exception:
                st.error("Błąd w JSON.")

        st.markdown("### 🧪 Przetestuj strategię AI na danych")
        sym_lab = st.selectbox("Symbol", symbols_available, key="lab_sym_test")
        df_lab = data_map[sym_lab]["df_1d"]

        if st.button("Uruchom backtest AI", key="lab_bt"):
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

            st.line_chart(equity, key=f"lab_bt_{sym_lab}")
            st.write(f"Zwrot: {(equity.iloc[-1]-1)*100:.2f}%")
            st.write(f"Max DD: {(equity.cummax()-equity).max()*100:.2f}%")

        st.markdown("### 🧬 AI Auto‑Optimizer (popraw strategię, PL)")
        if st.button("Optymalizuj strategię AI", key="lab_opt"):
            prompt = f"""
            Masz strategię w JSON (po polsku) i chcesz ją poprawić pod kątem:
            - lepszego stosunku zysku do ryzyka
            - mniejszego DD
            - bardziej agresywnych wejść, ale kontrolowanego ryzyka

            Strategia:
            {json.dumps(st.session_state["lab_strategy"], indent=4, ensure_ascii=False)}

            Zwróć NOWĄ strategię w tym samym formacie JSON, również po polsku.
            """
            st.session_state["lab_strategy"] = ai.chat_json(prompt)
            st.success("Strategia zoptymalizowana przez AI.")
            st.json(st.session_state["lab_strategy"])

        st.markdown("### 📜 Generuj Pine Script z tej strategii")
        if st.button("Generuj Pine Script", key="lab_pine"):
            prompt = f"""
            Zamień tę strategię JSON na kod Pine Script v5.
            Strategia jest opisana po polsku, ale kod ma być standardowy.

            Strategia JSON:
            {json.dumps(st.session_state["lab_strategy"], indent=4, ensure_ascii=False)}

            Zwróć TYLKO kod Pine Script.
            """
            code = ai.chat(prompt)
            st.code(code, language="pine")

# --- 15. TAB: AI AUTO-TRADER (wersja v1, PL) ---

with tab_auto:
    st.subheader("🤖 AI Auto‑Trader (wirtualny, z RiskEngine, PL)")

    col_a1, col_a2 = st.columns(2)
    with col_a1:
        sym = st.selectbox("Symbol do AI Auto‑Trader", symbols_available, key="auto_sym")
        d = data_map[sym]

        account_size = st.number_input("Wielkość konta (RiskEngine)", value=10000.0, step=100.0, key="auto_acc")
        risk_pct = st.slider("Ryzyko na trade (%)", 0.1, 5.0, 1.0, 0.1, key="auto_risk")
        risk_engine = RiskEngine(account_size)

        st.markdown("### 🧠 Generuj sygnał AI (JSON, PL)")
        if st.button("Generuj sygnał AI", key="auto_ai_sig"):
            prompt = f"""
            Jesteś agresywnym traderem. Oceń instrument {d['symbol']}.

            Dane:
            - Cena: {d['price']:.2f}
            - Zmiana % (D1): {d['change']:.2f}
            - Trend (SMA200): {d['trend']}
            - RSI (15m): {d['rsi']:.1f}
            - Pivot (D1): {d['pivot']:.2f}
            - TP (propozycja): {d['tp']:.2f}
            - SL (propozycja): {d['sl']:.2f}

            Zwróć TYLKO JSON po polsku w formacie:
            {{
              "symbol": "...",
              "bias": "long" lub "short" lub "neutral",
              "confidence": liczba 1-10,
              "risk_score": liczba 1-10,
              "action": "kup", "sprzedaj" lub "czekaj",
              "comment": "krótki komentarz po polsku"
            }}
            """
            sig = ai.chat_json(prompt)
            st.session_state["last_ai_signal"] = sig

            desc_prompt = f"""
            Na podstawie tego sygnału AI (JSON, po polsku):

            {json.dumps(sig, indent=2, ensure_ascii=False)}

            Napisz krótki, konkretny komentarz po polsku dla tradera:
            - co AI sugeruje (kupno/sprzedaż/obserwacja),
            - jaki jest bias (long/short),
            - jak duże jest ryzyko,
            - na co uważać.

            Maksymalnie 4-5 zdań.
            """
            analysis_text = ai.chat(desc_prompt)
            st.session_state["auto_analysis"] = analysis_text

            msg = f"AI {sig.get('action','?').upper()} {sym} | bias {sig.get('bias')} | risk {sig.get('risk_score')}"
            st.session_state["alerts"].append(msg)
            if webhook_url:
                AlertEngine.send_webhook(webhook_url, {"type": "ai_signal", "symbol": sym, "signal": sig})
            if tg_token and tg_chat_id:
                AlertEngine.send_telegram(tg_token, tg_chat_id, msg)

        if st.session_state["last_ai_signal"]:
            sig = st.session_state["last_ai_signal"]
            st.markdown("### Ostatni sygnał AI (JSON)")
            st.json(sig)

            if st.session_state["auto_analysis"]:
                st.markdown("### Komentarz AI (PL)")
                st.info(st.session_state["auto_analysis"])

            atr = d["atr"]
            sizing = risk_engine.position_size_atr(
                price=d["price"],
                atr=atr,
                risk_pct=risk_pct,
                atr_mult=1.5,
            )
            direction = "long" if sig.get("bias") == "long" else "short"
            r_mult = risk_engine.compute_r_multiple(
                entry=d["price"],
                stop=d["sl"],
                target=d["tp"],
                direction=direction,
            )

            st.markdown("### RiskEngine (na podstawie ATR)")
            st.write(f"ATR(14): {atr:.2f}")
            st.write(f"Stop distance (1.5 ATR): {sizing['stop_distance']:.2f}")
            st.write(f"Ryzyko nominalne: {sizing['risk_amount']:.2f}")
            st.write(f"Proponowany size (szt.): {sizing['size']:.4f}")
            st.write(f"R-multiple (TP/SL): {r_mult:.2f}" if r_mult is not None else "R-multiple: n/a")

            if st.button("📥 Zasymuluj trade (dodaj do logu)", key="auto_add_trade"):
                trade = {
                    "time": datetime.utcnow().isoformat(),
                    "symbol": sym,
                    "price": d["price"],
                    "action": sig.get("action"),
                    "bias": sig.get("bias"),
                    "risk": sig.get("risk_score"),
                    "size": sizing["size"],
                    "risk_pct": risk_pct,
                    "r_multiple": r_mult,
                }
                st.session_state["trades_log"].append(trade)

    with col_a2:
        st.write("Log transakcji (ostatnie 10):")
        st.json(st.session_state["trades_log"][-10:])

        st.markdown("### 🧾 AI → TradingView Pine Script (PL opis, kod standard)")
        if st.button("Generuj Pine Script dla strategii EMA/RSI", key="ai_pine"):
            prompt = """
            Napisz strategię w Pine Script v5 dla TradingView.

            Opis strategii (po polsku):
            - Użyj przecięcia EMA20/EMA50 jako głównego sygnału.
            - RSI 14 jako filtr: nie kupuj gdy RSI > 70, nie sprzedawaj gdy RSI < 30.
            - Dodaj parametry wejściowe (input) dla długości EMA i poziomów RSI.

            Zwróć TYLKO kod Pine Script, bez dodatkowego tekstu poza kodem.
            """
            code = ai.chat(prompt)
            st.code(code, language="pine")

# --- 16. TAB: MULTI-TIMEFRAME ---

with tab_multi:
    st.subheader("⏱️ Dashboard Multi‑Timeframe")
    sym = st.selectbox("Symbol", symbols_available, key="mtf_sym")

    tf_map = {
        "1m": ("1d", "1m"),
        "5m": ("5d", "5m"),
        "15m": ("5d", "15m"),
        "1h": ("1mo", "60m"),
        "1d": ("1y", "1d"),
    }

    mtf_tabs = st.tabs(list(tf_map.keys()))
    for (tf, (period, interval)), tab in zip(tf_map.items(), mtf_tabs):
        with tab:
            df = MarketData.get_yf(sym, period, interval)
            if df is None:
                st.write("Brak danych.")
                continue
            df = MarketData.compute_indicators(df)
            df = df.tail(200)

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(
                go.Candlestick(
                    x=df.index,
                    open=df["Open"],
                    high=df["High"],
                    low=df["Low"],
                    close=df["Close"],
                    increasing_line_color="#22c55e",
                    decreasing_line_color="#ef4444",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["EMA20"],
                    line=dict(color="#38bdf8", width=1.1),
                    name="EMA20",
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["EMA50"],
                    line=dict(color="#a855f7", width=1.0),
                    name="EMA50",
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Bar(x=df.index, y=df["Volume"], marker_color="#4b5563", name="Volume"),
                row=2,
                col=1,
            )

            fig.update_layout(
                template="plotly_dark",
                height=380,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_rangeslider_visible=False,
                paper_bgcolor="#020617",
                plot_bgcolor="#020617",
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"mtf_{sym}_{tf}")

# --- 17. TAB: ORDERBOOK ---

with tab_orderbook:
    st.subheader("📚 Orderbook (Binance spot)")
    sym = st.text_input("Symbol Binance (np. BTCUSDT, ETHUSDT)", value="BTCUSDT")
    depth_limit = st.selectbox("Limit", [5, 10, 20, 50], index=1)

    if st.button("Pobierz orderbook", key="ob_btn"):
        try:
            url = f"https://api.binance.com/api/v3/depth?symbol={sym}&limit={depth_limit}"
            r = requests.get(url, timeout=3)
            ob = r.json()
            bids = pd.DataFrame(ob["bids"], columns=["price", "qty"]).astype(float)
            asks = pd.DataFrame(ob["asks"], columns=["price", "qty"]).astype(float)

            col_ob1, col_ob2 = st.columns(2)
            with col_ob1:
                st.write("Bids")
                st.dataframe(bids)
            with col_ob2:
                st.write("Asks")
                st.dataframe(asks)

            fig = go.Figure()
            fig.add_trace(go.Bar(x=bids["price"], y=bids["qty"], name="Bids", marker_color="#22c55e"))
            fig.add_trace(go.Bar(x=asks["price"], y=asks["qty"], name="Asks", marker_color="#ef4444"))
            fig.update_layout(
                barmode="relative",
                template="plotly_dark",
                height=350,
                paper_bgcolor="#020617",
                plot_bgcolor="#020617",
                xaxis_title="Price",
                yaxis_title="Qty",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"orderbook_{sym}_{depth_limit}")
        except Exception as e:
            st.error(f"Błąd pobierania orderbook: {e}")

# --- 18. TAB: FORMACJE ŚWIECOWE + AI ---

def detect_candle_patterns(df: pd.DataFrame):
    patterns = []
    last = df.iloc[-1]
    body = abs(last["Close"] - last["Open"])
    range_ = last["High"] - last["Low"]
    upper_wick = last["High"] - max(last["Close"], last["Open"])
    lower_wick = min(last["Close"], last["Open"]) - last["Low"]

    if range_ > 0:
        if body / range_ < 0.2 and upper_wick / range_ > 0.4 and lower_wick / range_ < 0.2:
            patterns.append("Spinning Top / możliwa niepewność")
        if body / range_ < 0.2 and upper_wick / range_ < 0.2 and lower_wick / range_ > 0.4:
            patterns.append("Młot / potencjalne odwrócenie w górę")
        if body / range_ < 0.2 and upper_wick / range_ > 0.4 and lower_wick / range_ > 0.4:
            patterns.append("Doji / silna niepewność")

    return patterns


with tab_patterns:
    st.subheader("🕯️ Formacje świecowe + AI opis (PL)")
    sym = st.selectbox("Symbol", symbols_available, key="pat_sym")
    df = data_map[sym]["df_1d"]
    patterns = detect_candle_patterns(df)
    st.write("Wykryte formacje (heurystycznie):")
    if patterns:
        for p in patterns:
            st.markdown(f"- {p}")
    else:
        st.write("Brak wyraźnych formacji wg prostych reguł.")

    if st.button("🧠 AI: opisz sytuację świecową", key="ai_pattern"):
        last = df.tail(5)[["Open", "High", "Low", "Close"]].to_dict(orient="records")
        prompt = f"""
        Masz ostatnie 5 świec dziennych dla {sym}: {last}.
        Opisz sytuację świecową, potencjalne formacje i co może oznaczać dla agresywnego tradera.
        Krótko, konkretnie, po polsku.
        """
        desc = ai.chat(prompt)
        st.info(desc)

# --- 19. TAB: PORTFOLIO & RISK ---

with tab_portfolio:
    st.subheader("📦 Portfolio & Risk Management (ATR sizing, PL)")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        account_size = st.number_input("Wielkość konta", value=10000.0, step=100.0)
        risk_pct = st.slider("Ryzyko na trade (%)", 0.1, 5.0, 1.0, 0.1)
        sym = st.selectbox("Symbol do nowej pozycji", symbols_available, key="port_sym")
        d = data_map[sym]
        df = d["df_1d"]
        atr = (df["High"] - df["Low"]).rolling(14).mean().iloc[-1]

        risk_engine = RiskEngine(account_size)
        sizing = risk_engine.position_size_atr(
            price=d["price"],
            atr=atr,
            risk_pct=risk_pct,
            atr_mult=1.5,
        )

        st.write(f"ATR(14): {atr:.2f}")
        st.write(f"Stop distance (1.5 ATR): {sizing['stop_distance']:.2f}")
        st.write(f"Ryzyko nominalne: {sizing['risk_amount']:.2f}")
        st.write(f"Proponowany size (szt.): {sizing['size']:.4f}")

        if st.button("➕ Dodaj pozycję do portfolio", key="add_pos"):
            pos = {
                "symbol": sym,
                "price": d["price"],
                "size": sizing["size"],
                "atr": float(atr),
                "stop_distance": sizing["stop_distance"],
                "risk_pct": risk_pct,
            }
            st.session_state["portfolio"].append(pos)

    with col_p2:
        st.write("Aktualne portfolio (wirtualne):")
        if st.session_state["portfolio"]:
            st.json(st.session_state["portfolio"])
        else:
            st.write("Brak pozycji.")

        total_risk = sum(p["risk_pct"] for p in st.session_state["portfolio"])
        st.markdown(f"**Łączne ryzyko (suma %):** {total_risk:.2f}%")
# --- 20. MODUŁ AI: MARKET REGIME DETECTOR PRO ---

st.markdown("---")
st.subheader("🧭 AI Market Regime Detector PRO")

col_r1, col_r2 = st.columns(2)

with col_r1:
    sym_reg = st.selectbox("Symbol do analizy reżimu rynku", symbols_available, key="regime_sym")
    d_reg = data_map[sym_reg]
    df_reg = d_reg["df_1d"]

    # proste metryki reżimu
    close = df_reg["Close"]
    sma200 = close.rolling(200).mean()
    sma50 = close.rolling(50).mean()
    ret_5 = close.pct_change(5)
    ret_20 = close.pct_change(20)
    vol_20 = close.pct_change().rolling(20).std()

    last_price = float(close.iloc[-1])
    last_sma200 = float(sma200.iloc[-1])
    last_sma50 = float(sma50.iloc[-1])
    last_ret_5 = float(ret_5.iloc[-1])
    last_ret_20 = float(ret_20.iloc[-1])
    last_vol_20 = float(vol_20.iloc[-1])

    trend = "hossa" if last_price > last_sma200 else "bessa"
    momentum = "dodatnie" if last_ret_20 > 0 else "ujemne"
    vol_level = "wysoka" if last_vol_20 > vol_20.median() else "niska/średnia"

    st.markdown("### Metryki reżimu (surowe)")
    st.write(f"Trend (SMA200): **{trend}**")
    st.write(f"Momentum 20 dni: **{last_ret_20*100:.2f}%** ({momentum})")
    st.write(f"Zmienność 20 dni (σ): **{last_vol_20*100:.2f}%** ({vol_level})")
    st.write(f"SMA50 vs SMA200: {'byczo' if last_sma50 > last_sma200 else 'niedźwiedzio'}")

with col_r2:
    st.markdown("### 🧠 AI ocena reżimu rynku (JSON + komentarz PL)")
    if st.button("Analizuj reżim rynku AI", key="regime_ai_btn"):
        prompt = f"""
        Jesteś zaawansowanym analitykiem rynku.

        Dane dla instrumentu {sym_reg}:
        - Trend (SMA200): {trend}
        - Cena vs SMA200: {last_price:.2f} vs {last_sma200:.2f}
        - Cena vs SMA50: {last_price:.2f} vs {last_sma50:.2f}
        - Momentum 5 dni: {last_ret_5*100:.2f}%
        - Momentum 20 dni: {last_ret_20*100:.2f}%
        - Zmienność 20 dni (odchylenie standardowe zwrotów): {last_vol_20*100:.2f}%
        - Poziom zmienności: {vol_level}

        Oceń reżim rynku i zwróć TYLKO JSON po polsku w formacie:
        {{
          "symbol": "...",
          "trend": "hossa" lub "bessa" lub "konsolidacja",
          "momentum": "dodatnie" lub "ujemne" lub "neutralne",
          "volatility": "wysoka" lub "średnia" lub "niska",
          "regime_type": "trend-following" lub "mean-reversion" lub "mieszany",
          "bias": "agresywny long" lub "ostrożny long" lub "agresywny short" lub "ostrożny short" lub "flat",
          "risk_level": "wysokie" lub "umiarkowane" lub "niskie",
          "comment": "krótki komentarz po polsku dla tradera",
          "tactical_hint": "krótka wskazówka jak grać ten reżim (np. kupuj wybicia, graj mean-reversion, unikaj lewara)"
        }}
        """
        regime_json = ai.chat_json(prompt)
        st.json(regime_json)

        # komentarz tekstowy
        desc_prompt = f"""
        Na podstawie tego JSON-a (po polsku):

        {json.dumps(regime_json, indent=2, ensure_ascii=False)}

        Napisz krótki komentarz (3-5 zdań) po polsku:
        - jaki jest reżim rynku,
        - jaki bias (long/short/flat),
        - jak agresywnie można grać,
        - na co szczególnie uważać.
        """
        regime_desc = ai.chat(desc_prompt)
        st.info(regime_desc)


# --- 21. MODUŁ AI: PATTERN RECOGNITION PRO ---

st.markdown("---")
st.subheader("📈 AI Pattern Recognition PRO")

col_patt1, col_patt2 = st.columns(2)

with col_patt1:
    sym_pat = st.selectbox("Symbol do AI Pattern Recognition", symbols_available, key="pat_ai_sym")
    d_pat = data_map[sym_pat]
    df_daily = d_pat["df_1d"].tail(200)
    df_intraday = d_pat["df_15"].tail(200)

    st.markdown("### Dane wejściowe (skrót)")
    st.write(f"Ostatnie świece D1: {len(df_daily)}")
    st.write(f"Ostatnie świece 15m: {len(df_intraday)}")

    st.dataframe(df_daily[["Open", "High", "Low", "Close"]].tail(5))

with col_patt2:
    st.markdown("### 🧠 AI: wykryj formacje (harmoniczne, klasyczne, świecowe, wolumenowe)")
    if st.button("Analizuj formacje AI", key="pat_ai_btn"):
        daily_ohlc = df_daily[["Open", "High", "Low", "Close"]].reset_index().to_dict(orient="records")
        intr_ohlc = df_intraday[["Open", "High", "Low", "Close", "Volume"]].reset_index().to_dict(orient="records")

        prompt = f"""
        Jesteś zaawansowanym systemem rozpoznawania formacji.

        Masz dane:
        - Świece dzienne (D1) dla {sym_pat}: {daily_ohlc}
        - Świece intraday (15m) dla {sym_pat}: {intr_ohlc}

        Wykryj:
        - formacje harmoniczne (np. Gartley, Bat, Crab),
        - formacje klasyczne (flagi, trójkąty, kanały, głowa z ramionami),
        - formacje wolumenowe (np. VCP, akumulacja/dystrybucja w stylu Wyckoff),
        - formacje świecowe (engulfing, pin bar, fakey, inside bar).

        Zwróć TYLKO JSON po polsku w formacie:
        {{
          "symbol": "...",
          "harmonic_patterns": [
            {{
              "name": "Gartley" lub inna,
              "timeframe": "D1" lub "15m",
              "direction": "bycza" lub "niedźwiedzia",
              "confidence": 1-10,
              "comment": "krótki opis po polsku"
            }}
          ],
          "classical_patterns": [
            {{
              "name": "flaga", "trójkąt", "kanał", "RGR", "odwrócony RGR" itd.,
              "timeframe": "D1" lub "15m",
              "direction": "kontynuacja" lub "odwrócenie",
              "confidence": 1-10,
              "comment": "krótki opis po polsku"
            }}
          ],
          "volume_patterns": [
            {{
              "name": "VCP", "akumulacja", "dystrybucja" itd.,
              "timeframe": "D1" lub "15m",
              "confidence": 1-10,
              "comment": "krótki opis po polsku"
            }}
          ],
          "candle_patterns": [
            {{
              "name": "bullish engulfing", "pin bar", "inside bar" itd.,
              "timeframe": "D1" lub "15m",
              "direction": "bycza" lub "niedźwiedzia",
              "confidence": 1-10,
              "comment": "krótki opis po polsku"
            }}
          ],
          "summary": "krótkie podsumowanie po polsku: co to oznacza dla agresywnego tradera",
          "tactical_hint": "konkretna sugestia: graj wybicia, graj mean-reversion, poczekaj na potwierdzenie itd."
        }}
        """
        patt_json = ai.chat_json(prompt)
        st.json(patt_json)

        desc_prompt = f"""
        Na podstawie tego JSON-a (po polsku):

        {json.dumps(patt_json, indent=2, ensure_ascii=False)}

        Napisz krótki komentarz (3-6 zdań) po polsku:
        - jakie najważniejsze formacje widzisz,
        - czy przewaga jest po stronie byków czy niedźwiedzi,
        - czy lepiej grać wybicia czy powroty do średniej,
        - czy ryzyko jest wysokie czy umiarkowane.
        """
        patt_desc = ai.chat(desc_prompt)
        st.info(patt_desc)
# --- 22. AUTO-TRADER v2: AI + SL/TP 1-2-3 NA WYKRESIE ---

st.markdown("---")
st.subheader("🤖 AI Auto‑Trader v2 — SL/TP 1‑2‑3 + kontekst wykresu (PL)")

col_v1, col_v2 = st.columns([2, 1])

with col_v1:
    sym_v2 = st.selectbox("Symbol do Auto‑Trader v2", symbols_available, key="auto_v2_sym")
    d_v2 = data_map[sym_v2]
    df15_v2 = d_v2["df_15"].tail(200)
    df1d_v2 = d_v2["df_1d"].tail(200)

    # Podstawowe dane
    price = d_v2["price"]
    atr = d_v2["atr"]
    rsi = d_v2["rsi"]
    change = d_v2["change"]
    trend = d_v2["trend"]

    st.markdown(f"**{sym_v2}** — cena: `{price:.2f}`, zmiana D1: `{change:.2f}%`, RSI(15m): `{rsi:.1f}`, trend: `{trend}`")
    st.markdown("### Wykres 15m z kontekstem")

    fig_v2 = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.2, 0.25],
        vertical_spacing=0.03,
    )

    fig_v2.add_trace(
        go.Candlestick(
            x=df15_v2.index,
            open=df15_v2["Open"],
            high=df15_v2["High"],
            low=df15_v2["Low"],
            close=df15_v2["Close"],
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    fig_v2.add_trace(
        go.Scatter(
            x=df15_v2.index,
            y=df15_v2["EMA20"],
            line=dict(color="#38bdf8", width=1.1),
            name="EMA20",
        ),
        row=1,
        col=1,
    )
    fig_v2.add_trace(
        go.Scatter(
            x=df15_v2.index,
            y=df15_v2["EMA50"],
            line=dict(color="#a855f7", width=1.0),
            name="EMA50",
        ),
        row=1,
        col=1,
    )
    fig_v2.add_trace(
        go.Bar(x=df15_v2.index, y=df15_v2["Volume"], marker_color="#4b5563", name="Volume"),
        row=2,
        col=1,
    )
    fig_v2.add_trace(
        go.Scatter(
            x=df15_v2.index,
            y=df15_v2["MACD"],
            line=dict(color="#22c55e", width=1),
            name="MACD",
        ),
        row=3,
        col=1,
    )
    fig_v2.add_trace(
        go.Scatter(
            x=df15_v2.index,
            y=df15_v2["MACD_signal"],
            line=dict(color="#ef4444", width=1),
            name="Signal",
        ),
        row=3,
        col=1,
    )
    fig_v2.add_trace(
        go.Bar(
            x=df15_v2.index,
            y=df15_v2["MACD_hist"],
            marker_color=np.where(df15_v2["MACD_hist"] >= 0, "#22c55e", "#ef4444"),
            name="Hist",
        ),
        row=3,
        col=1,
    )

    fig_v2.update_layout(
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
    fig_v2.update_xaxes(showgrid=False)
    fig_v2.update_yaxes(showgrid=False)

    # Jeśli mamy już wyliczone poziomy SL/TP, dorysujemy je na wykresie
    if "auto_v2_levels" in st.session_state and st.session_state["auto_v2_levels"].get(sym_v2):
    lv = st.session_state["auto_v2_levels"][sym_v2]

    def add_level(y, label, color):
        fig_v2.add_hline(
            y=y,
            line=dict(color=color, width=1.2, dash="dot"),
            annotation_text=label,
            annotation_position="top left",
            annotation_font_color=color,
        )

    add_level(lv["sl1"], "SL1", "#f97316")
    add_level(lv["sl2"], "SL2", "#fb923c")
    add_level(lv["sl3"], "SL3", "#ef4444")

    add_level(lv["tp1"], "TP1", "#22c55e")
    add_level(lv["tp2"], "TP2", "#16a34a")
    add_level(lv["tp3"], "TP3", "#15803d")
st.plotly_chart(fig_v2, use_container_width=True)

    if "auto_v2_levels" in st.session_state and st.session_state["auto_v2_levels"].get(sym_v2):
        lv = st.session_state["auto_v2_levels"][sym_v2]
        last_x = df15_v2.index[-1]

        def add_hline(y, name, color):
            fig_v2.add_hline(
                y=y,
                line=dict(color=color, width=1, dash="dot"),
                annotation_text=name,
                annotation_position="top left",
                annotation_font_color=color,
            )

        add_hline(lv["sl1"], "SL1", "#f97316")
        add_hline(lv["sl2"], "SL2", "#fb923c")
        add_hline(lv["sl3"], "SL3", "#ef4444")
        add_hline(lv["tp1"], "TP1", "#22c55e")
        add_hline(lv["tp2"], "TP2", "#16a34a")
        add_hline(lv["tp3"], "TP3", "#15803d")

    st.plotly_chart(fig_v2, use_container_width=True, key=f"auto_v2_chart_{sym_v2}")

with col_v2:
    if "auto_v2_levels" not in st.session_state:
        st.session_state["auto_v2_levels"] = {}
    if "auto_v2_comment" not in st.session_state:
        st.session_state["auto_v2_comment"] = {}
    if "auto_v2_mode" not in st.session_state:
        st.session_state["auto_v2_mode"] = {}

    st.markdown("### 🧠 AI: czy to dobry moment na wejście?")
    trade_style = st.selectbox(
        "Styl wejścia",
        ["scalping", "day trading", "swing trading"],
        key="auto_v2_style",
    )

    account_size_v2 = st.number_input("Wielkość konta (Auto‑Trader v2)", value=10000.0, step=100.0, key="auto_v2_acc")
    risk_pct_v2 = st.slider("Ryzyko na trade (%)", 0.1, 5.0, 1.0, 0.1, key="auto_v2_risk")
    risk_engine_v2 = RiskEngine(account_size_v2)

    if st.button("Analiza AI + SL/TP 1‑2‑3", key="auto_v2_btn"):
        # Dane wejściowe dla AI
        daily_ohlc = df1d_v2[["Open", "High", "Low", "Close"]].reset_index().to_dict(orient="records")
        intr_ohlc = df15_v2[["Open", "High", "Low", "Close", "Volume"]].reset_index().to_dict(orient="records")

        prompt = f"""
        Jesteś zaawansowanym traderem i risk managerem.

        Masz dane dla instrumentu {sym_v2}:
        - Cena bieżąca: {price:.2f}
        - Zmiana D1: {change:.2f}%
        - RSI (15m): {rsi:.1f}
        - ATR (D1): {atr:.2f}
        - Trend (SMA200): {trend}
        - Styl wejścia: {trade_style}

        Dane świec:
        - Ostatnie świece dzienne (D1): {daily_ohlc}
        - Ostatnie świece 15m: {intr_ohlc}

        Oceń, czy to jest dobry moment na wejście dla stylu: {trade_style}.
        Następnie zaproponuj poziomy SL/TP 1-2-3.

        Zwróć TYLKO JSON po polsku w formacie:
        {{
          "symbol": "...",
          "is_good_moment": true lub false,
          "reason": "krótko po polsku dlaczego tak/nie",
          "recommended_style": "scalping" lub "day trading" lub "swing trading",
          "bias": "long" lub "short" lub "neutral",
          "sl_levels": {{
            "sl1": liczba,
            "sl2": liczba,
            "sl3": liczba
          }},
          "tp_levels": {{
            "tp1": liczba,
            "tp2": liczba,
            "tp3": liczba
          }},
          "comment": "krótki komentarz po polsku dla tradera (3-5 zdań)",
          "tactical_hint": "konkretna sugestia: np. 'to nie jest dobry moment, jeśli już to tylko scalping z małą pozycją'"
        }}
        """
        res = ai.chat_json(prompt)
        st.session_state["auto_v2_levels"][sym_v2] = {
            "sl1": float(res["sl_levels"]["sl1"]),
            "sl2": float(res["sl_levels"]["sl2"]),
            "sl3": float(res["sl_levels"]["sl3"]),
            "tp1": float(res["tp_levels"]["tp1"]),
            "tp2": float(res["tp_levels"]["tp2"]),
            "tp3": float(res["tp_levels"]["tp3"]),
            "bias": res.get("bias", "neutral"),
            "is_good_moment": res.get("is_good_moment", False),
        }
        st.session_state["auto_v2_comment"][sym_v2] = res
        st.session_state["auto_v2_mode"][sym_v2] = trade_style

        st.success("AI wyliczyło poziomy SL/TP 1‑2‑3 i oceniło moment wejścia.")
        st.json(res)

    if st.session_state["auto_v2_comment"].get(sym_v2):
        res = st.session_state["auto_v2_comment"][sym_v2]
        st.markdown("### Komentarz AI (PL)")
        st.info(res.get("comment", ""))

        st.markdown("### Taktyczna sugestia AI")
        st.warning(res.get("tactical_hint", ""))

        lv = st.session_state["auto_v2_levels"][sym_v2]
        st.markdown("### Poziomy SL/TP 1‑2‑3 (AI)")
        st.write(f"SL1: {lv['sl1']:.2f} | SL2: {lv['sl2']:.2f} | SL3: {lv['sl3']:.2f}")
        st.write(f"TP1: {lv['tp1']:.2f} | TP2: {lv['tp2']:.2f} | TP3: {lv['tp3']:.2f}")
        st.write(f"Bias: {lv['bias']} | Dobry moment?: {'TAK' if lv['is_good_moment'] else 'NIE'}")

        # RiskEngine na podstawie SL2 (główny stop)
        main_stop = lv["sl2"] if lv["bias"] == "long" else lv["tp2"]
        stop_distance = abs(price - main_stop)
        risk_amount = account_size_v2 * (risk_pct_v2 / 100)
        size = risk_amount / stop_distance if stop_distance > 0 else 0

        st.markdown("### RiskEngine (Auto‑Trader v2)")
        st.write(f"Stop distance (główny): {stop_distance:.2f}")
        st.write(f"Ryzyko nominalne: {risk_amount:.2f}")
        st.write(f"Proponowany size (szt.): {size:.4f}")

        # R-multiple dla TP2 względem SL2
        if lv["bias"] == "long":
            risk = price - lv["sl2"]
            reward = lv["tp2"] - price
        elif lv["bias"] == "short":
            risk = lv["sl2"] - price
            reward = price - lv["tp2"]
        else:
            risk = 0
            reward = 0
        r_mult = reward / risk if risk > 0 else None
        st.write(f"R-multiple (TP2/SL2): {r_mult:.2f}" if r_mult else "R-multiple: n/a")

        if st.button("📥 Zasymuluj trade Auto‑Trader v2", key=f"auto_v2_trade_{sym_v2}"):
            trade = {
                "time": datetime.utcnow().isoformat(),
                "symbol": sym_v2,
                "price": price,
                "style": st.session_state["auto_v2_mode"][sym_v2],
                "bias": lv["bias"],
                "is_good_moment": lv["is_good_moment"],
                "sl1": lv["sl1"],
                "sl2": lv["sl2"],
                "sl3": lv["sl3"],
                "tp1": lv["tp1"],
                "tp2": lv["tp2"],
                "tp3": lv["tp3"],
                "size": size,
                "risk_pct": risk_pct_v2,
                "r_multiple": r_mult,
            }
            st.session_state["trades_log"].append(trade)
            msg = f"Auto‑Trader v2 {sym_v2} | {lv['bias']} | good={lv['is_good_moment']} | style={st.session_state['auto_v2_mode'][sym_v2]}"
            st.session_state["alerts"].append(msg)
            if webhook_url:
                AlertEngine.send_webhook(webhook_url, {"type": "auto_trader_v2", "trade": trade})
            if tg_token and tg_chat_id:
                AlertEngine.send_telegram(tg_token, tg_chat_id, msg)
            st.success("Trade zapisany w logu (wirtualnie).")
# --- 23. TAB: AI RISK MATRIX & AUTO-HEDGING ---

with tab_risk_ai:
    st.subheader("🛡️ AI Risk Matrix & Auto‑Hedging (PL)")

    if "portfolio" not in st.session_state or len(st.session_state["portfolio"]) == 0:
        st.info("Brak pozycji w wirtualnym portfolio. Dodaj coś w zakładce 📦 Portfolio & Risk.")
    else:
        port = st.session_state["portfolio"]
        st.markdown("### Aktualne portfolio (input dla AI)")
        st.json(port)

        # prosty risk snapshot
        total_risk_pct = sum(p.get("risk_pct", 0) for p in port)
        symbols_in_port = list({p["symbol"] for p in port})

        st.markdown(f"**Łączne ryzyko (suma %):** {total_risk_pct:.2f}%")
        st.markdown(f"**Liczba instrumentów w portfelu:** {len(symbols_in_port)}")

        # przygotowanie danych dla AI
        port_compact = []
        for p in port:
            sym = p["symbol"]
            d = data_map.get(sym)
            if not d:
                continue
            port_compact.append(
                {
                    "symbol": sym,
                    "price": float(d["price"]),
                    "size": float(p["size"]),
                    "risk_pct": float(p.get("risk_pct", 0)),
                    "atr": float(p.get("atr", d.get("atr", 0))),
                    "trend": d.get("trend", ""),
                    "change_d1": float(d.get("change", 0)),
                }
            )

        st.markdown("### 🧠 AI Risk Matrix (ocena portfela)")

        if st.button("Analizuj ryzyko portfela AI", key="ai_risk_matrix_btn"):
            prompt = f"""
            Jesteś zaawansowanym risk managerem.

            Masz portfel (lista pozycji, po polsku, uproszczona):
            {json.dumps(port_compact, indent=2, ensure_ascii=False)}

            Oceń:
            - koncentrację ryzyka (czy za dużo w jednym kierunku / sektorze / instrumencie),
            - ogólny poziom ryzyka (niski / umiarkowany / wysoki),
            - czy portfel jest bardziej pro‑risk (long beta) czy defensywny,
            - które pozycje są najbardziej ryzykowne.

            Zwróć TYLKO JSON po polsku w formacie:
            {{
              "risk_level": "niski" lub "umiarkowany" lub "wysoki",
              "concentration_comment": "krótki komentarz po polsku",
              "top_risk_positions": [
                {{
                  "symbol": "...",
                  "reason": "dlaczego jest ryzykowna (po polsku)"
                }}
              ],
              "beta_bias": "pro‑risk" lub "neutralny" lub "defensywny",
              "summary": "krótkie podsumowanie po polsku (3-5 zdań)"
            }}
            """
            risk_json = ai.chat_json(prompt)
            st.session_state["ai_risk_matrix"] = risk_json
            st.json(risk_json)

        if "ai_risk_matrix" in st.session_state:
            st.markdown("### Komentarz AI (Risk Matrix)")
            st.info(st.session_state["ai_risk_matrix"].get("summary", ""))

        st.markdown("---")
        st.markdown("### 🧠 AI Auto‑Hedging (propozycja zabezpieczenia)")

        hedge_notional = st.number_input(
            "Docelowa wielkość hedge (w % wartości portfela, orientacyjnie)",
            min_value=5.0,
            max_value=100.0,
            value=30.0,
            step=5.0,
            key="hedge_notional_pct",
        )

        if st.button("Generuj propozycję hedge AI", key="ai_hedge_btn"):
            prompt = f"""
            Jesteś zaawansowanym traderem i risk managerem.

            Masz portfel:
            {json.dumps(port_compact, indent=2, ensure_ascii=False)}

            Chcesz zaproponować hedge na poziomie około {hedge_notional:.1f}% wartości portfela.

            Zaproponuj:
            - jaki instrument lub instrumenty użyć do hedge (np. short indeksu, ETF, kontrakt futures, opcje),
            - w jakim kierunku (short/long),
            - orientacyjną wielkość (w % portfela),
            - w jakich warunkach hedge powinien być aktywny (np. tylko przy spadku indeksu o X%).

            Zwróć TYLKO JSON po polsku w formacie:
            {{
              "hedge_idea": [
                {{
                  "instrument": "np. short S&P500 futures / short DAX ETF / long VIX",
                  "direction": "long" lub "short",
                  "notional_pct": liczba (procent portfela),
                  "condition": "kiedy hedge ma być aktywny (po polsku)",
                  "comment": "krótki komentarz po polsku"
                }}
              ],
              "global_comment": "krótkie podsumowanie po polsku (3-5 zdań)"
            }}
            """
            hedge_json = ai.chat_json(prompt)
            st.session_state["ai_hedge"] = hedge_json
            st.json(hedge_json)

        if "ai_hedge" in st.session_state:
            st.markdown("### Komentarz AI (Hedge)")
            st.info(st.session_state["ai_hedge"].get("global_comment", ""))
# --- AUTO‑FIX TABS v16.4 ---
# Usuwa duplikaty tabów i wymusza jedną poprawną definicję

def ensure_single_tabs():
    """
    Ten patch gwarantuje, że w aplikacji istnieje TYLKO jedna definicja st.tabs().
    Jeśli przypadkiem w kodzie pojawiły się 2 lub więcej definicji,
    ta funkcja nadpisze je jedną poprawną wersją.
    """

    # Definicja JEDYNEGO poprawnego zestawu tabów
    correct_tabs = [
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

    # Tworzymy globalną zmienną, która nadpisze wszystkie inne taby
    global tab_main, tab_strategy, tab_lab, tab_auto, tab_multi, tab_orderbook, tab_patterns, tab_portfolio, tab_risk_ai
    tab_main, tab_strategy, tab_lab, tab_auto, tab_multi, tab_orderbook, tab_patterns, tab_portfolio, tab_risk_ai = st.tabs(correct_tabs)

# Wymuszenie poprawnej definicji tabów
ensure_single_tabs()
