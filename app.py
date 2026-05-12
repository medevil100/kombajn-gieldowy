import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import os
import json
import numpy as np

# --- 1. KONFIGURACJA ---
DB_FILE = "tickers_db.txt"
st.set_page_config(page_title="AI ALPHA SUPERKOMBAJN v12.2", page_icon="📈", layout="wide")

def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                content = f.read().strip()
                return content if content else "PKO.WA, BTC-USD, NVDA, TSLA"
        except:
            return "PKO.WA, BTC-USD, NVDA, TSLA"
    return "PKO.WA, BTC-USD, NVDA, TSLA"

# --- 2. STYLE ---
st.markdown("""
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
    """, unsafe_allow_html=True)

# --- 3. SILNIK DANYCH ---
def compute_indicators(df):
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["EMA200"] = df["Close"].ewm(span=200).mean()

    # MACD
    ema12 = df["Close"].ewm(span=12).mean()
    ema26 = df["Close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9).mean()
    df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

    # RSI (14)
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))

    return df

def fibo_levels(df):
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
        "100%": low
    }
    return levels, high, low

def simple_backtest(df):
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["signal"] = 0
    df.loc[df["EMA20"] > df["EMA50"], "signal"] = 1
    df.loc[df["EMA20"] < df["EMA50"], "signal"] = -1
    df["position"] = df["signal"].shift(1).fillna(0)
    df["ret"] = df["Close"].pct_change().fillna(0)
    df["strategy"] = df["position"] * df["ret"]
    equity = (1 + df["strategy"]).cumprod()
    total_ret = equity.iloc[-1] - 1
    max_dd = (equity.cummax() - equity).max()
    trades = (df["position"].diff().abs() > 0).sum()
    return {
        "total_return": float(total_ret * 100),
        "max_drawdown": float(max_dd * 100),
        "trades": int(trades)
    }

def get_analysis(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)

        if d15.empty or d1d.empty:
            return None

        if isinstance(d15.columns, pd.MultiIndex):
            d15.columns = d15.columns.get_level_values(0)
        if isinstance(d1d.columns, pd.MultiIndex):
            d1d.columns = d1d.columns.get_level_values(0)

        d15 = compute_indicators(d15)
        d1d = compute_indicators(d1d)

        price = float(d15['Close'].iloc[-1])
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100

        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#00ff88" if price > sma200 else "#ff4b4b"

        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        pivot = (d1d['High'].iloc[-2] + d1d['Low'].iloc[-2] + d1d['Close'].iloc[-2]) / 3

        rsi = float(d15["RSI"].iloc[-1])

        if rsi < 32:
            rec, rec_col = "KUPUJ", "#22c55e"
        elif rsi > 68:
            rec, rec_col = "SPRZEDAJ", "#ef4444"
        else:
            rec, rec_col = "CZEKAJ", "#8b949e"

        fibo, fib_high, fib_low = fibo_levels(d1d)
        bt = simple_backtest(d1d)

        return {
            "symbol": symbol,
            "price": price,
            "change": change_pct,
            "rsi": rsi,
            "rec": rec,
            "rec_col": rec_col,
            "trend": trend_label,
            "trend_col": trend_color,
            "pivot": pivot,
            "tp": price + (atr * 1.5),
            "sl": price - (atr * 1.2),
            "df_15": d15,
            "df_1d": d1d,
            "fibo": fibo,
            "fibo_high": fib_high,
            "fibo_low": fib_low,
            "backtest": bt
        }
    except Exception as e:
        return None

# --- 4. UI SIDEBAR ---
with st.sidebar:
    st.title("⚙️ KOMB_v12.2")

    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("✅ Klucz aktywny (Secrets)")
    else:
        api_key = st.text_input("OpenAI Key", type="password")
        if not api_key:
            st.warning("Dodaj klucz w Secrets lub wpisz go tutaj.")

    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f:
            f.write(tickers_input)
        st.rerun()

    refresh = st.select_slider("Odśwież (s)", options=[30, 60, 300], value=60)

    st.markdown("### 🔔 Alerty")
    if "alerts" not in st.session_state:
        st.session_state["alerts"] = []

    for a in st.session_state["alerts"][-10:][::-1]:
        st.markdown(f"- <span class='neon-pill'>{a}</span>", unsafe_allow_html=True)

st_autorefresh(interval=refresh * 1000, key="fsh")

# --- 5. GŁÓWNA LOGIKA ---
if api_key:
    client = OpenAI(api_key=api_key)
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

    data_list = []
    for t in tickers:
        res = get_analysis(t)
        if res:
            data_list.append(res)

    if data_list:
        # --- HEATMAPA RYNKU ---
        st.subheader("🧊 HEATMAPA RYNKU")
        heat_df = pd.DataFrame({
            "Symbol": [d["symbol"] for d in data_list],
            "Change": [d["change"] for d in data_list]
        })
        heat_df["Color"] = heat_df["Change"].apply(lambda x: "green" if x >= 0 else "red")

        fig_heat = go.Figure(data=go.Treemap(
            labels=heat_df["Symbol"],
            parents=[""] * len(heat_df),
            values=heat_df["Change"].abs() + 0.01,
            marker=dict(
                colors=heat_df["Change"],
                colorscale="RdYlGn",
                reversescale=True,
                line=dict(color="#020617", width=1)
            ),
            textinfo="label+value",
            hovertemplate="<b>%{label}</b><br>Zmiana: %{value:.2f}%<extra></extra>"
        ))
        fig_heat.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=260,
            paper_bgcolor="#020617",
            plot_bgcolor="#020617"
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        # --- TOP Monitoring ---
        st.subheader("📊 MONITORING RYNKU")
        top_cols = st.columns(min(len(data_list), 5))

        for i, d in enumerate(sorted(data_list, key=lambda x: abs(x["change"]), reverse=True)[:10]):
            with top_cols[i % 5]:
                c_col = "#22c55e" if d['change'] >= 0 else "#ef4444"
                st.markdown(f"""
                    <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                        <b>{d['symbol']}</b><br>
                        <span style="color:{c_col}; font-weight:bold; font-size:1.1rem;">{d['price']:.2f}</span><br>
                        <span style="font-size:0.8rem; color:{d['trend_col']};">{d['trend']}</span><br>
                        <div style="background:{d['rec_col']}; font-size:0.7rem; border-radius:999px; margin:6px 0; color:white; display:inline-block; padding:2px 10px;">
                            {d['rec']}
                        </div><br>
                        <span class="stat-label">Δ {d['change']:.2f}% | RSI: {d['rsi']:.1f}</span>
                    </div>
                """, unsafe_allow_html=True)

        # --- SZCZEGÓŁY ---
        for d in data_list:
            st.markdown(f'<div class="ticker-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([1.1, 2.2])

            # --- LEWA KOLUMNA ---
            with c1:
                st.markdown(f"### {d['symbol']} ({d['trend']})")
                st.metric("Cena", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**Pivot:** {d['pivot']:.2f} | **RSI:** {d['rsi']:.1f}")
                st.write(f"**TP:** {d['tp']:.2f} | **SL:** {d['sl']:.2f}")

                bt = d["backtest"]
                st.markdown(
                    f"<span class='neon-pill'>Backtest EMA20/50: {bt['total_return']:.1f}% | DD: {bt['max_drawdown']:.1f}% | Trades: {bt['trades']}</span>",
                    unsafe_allow_html=True
                )

                # Fibo opis
                fibo = d["fibo"]
                st.markdown("<div class='fibo-box'><b>Fibonacci (ostatnie 120 sesji)</b><br>", unsafe_allow_html=True)
                st.markdown(
                    "<br>".join([f"{lvl}: {val:.2f}" for lvl, val in fibo.items()]),
                    unsafe_allow_html=True
                )
                st.markdown("</div>", unsafe_allow_html=True)

                # ALERTY LOGICZNE
                alerts_local = []
                if d["rsi"] < 30:
                    alerts_local.append(f"{d['symbol']}: RSI < 30 (przeciążona wyprzedaż)")
                if d["rsi"] > 70:
                    alerts_local.append(f"{d['symbol']}: RSI > 70 (przeciążony popyt)")
                if d["df_15"]["EMA20"].iloc[-1] > d["df_15"]["EMA50"].iloc[-1] and d["df_15"]["EMA20"].iloc[-2] <= d["df_15"]["EMA50"].iloc[-2]:
                    alerts_local.append(f"{d['symbol']}: BULLISH EMA20>EMA50 (15m)")
                if d["df_15"]["EMA20"].iloc[-1] < d["df_15"]["EMA50"].iloc[-1] and d["df_15"]["EMA20"].iloc[-2] >= d["df_15"]["EMA50"].iloc[-2]:
                    alerts_local.append(f"{d['symbol']}: BEARISH EMA20<EMA50 (15m)")

                if alerts_local:
                    st.markdown("#### 🔔 Lokalne alerty")
                    for a in alerts_local:
                        st.markdown(f"- {a}")
                        st.session_state["alerts"].append(a)

                # AI JSON SIGNAL
                if st.button(f"🧠 AI SYGNAŁ JSON {d['symbol']}", key=f"btn_ai_{d['symbol']}"):
                    try:
                        prompt = f"""
                        Jesteś agresywnym traderem. Oceń instrument {d['symbol']} na podstawie:
                        Cena: {d['price']:.2f}
                        Zmiana %: {d['change']:.2f}
                        Trend: {d['trend']}
                        RSI: {d['rsi']:.1f}
                        Pivot: {d['pivot']:.2f}
                        TP: {d['tp']:.2f}
                        SL: {d['sl']:.2f}
                        Zwróć TYLKO JSON w formacie:
                        {{
                          "symbol": "...",
                          "bias": "long/short/neutral",
                          "confidence": 1-10,
                          "risk_score": 1-10,
                          "comment": "krótki komentarz",
                          "action": "buy/sell/wait"
                        }}
                        """
                        resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        raw = resp.choices[0].message.content
                        try:
                            sig = json.loads(raw)
                        except:
                            # awaryjnie spróbuj wyciągnąć JSON z tekstu
                            start = raw.find("{")
                            end = raw.rfind("}")
                            sig = json.loads(raw[start:end+1]) if start != -1 and end != -1 else {"raw": raw}

                        st.session_state[f"ai_json_{d['symbol']}"] = sig
                    except Exception as e:
                        st.error(f"Błąd AI: {e}")

                if f"ai_json_{d['symbol']}" in st.session_state:
                    st.markdown("#### 📡 AI Sygnał (JSON)")
                    st.json(st.session_state[f"ai_json_{d['symbol']}"])

            # --- PRAWA KOLUMNA: WYKRESY ---
            with c2:
                df15 = d["df_15"].tail(120)

                fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    row_heights=[0.55, 0.2, 0.25],
                    vertical_spacing=0.03
                )

                # ŚWIECE
                fig.add_trace(go.Candlestick(
                    x=df15.index,
                    open=df15["Open"],
                    high=df15["High"],
                    low=df15["Low"],
                    close=df15["Close"],
                    name="Cena",
                    increasing_line_color="#22c55e",
                    decreasing_line_color="#ef4444",
                    showlegend=False
                ), row=1, col=1)

                # EMA
                fig.add_trace(go.Scatter(
                    x=df15.index, y=df15["EMA20"],
                    line=dict(color="#38bdf8", width=1.2),
                    name="EMA20"
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=df15.index, y=df15["EMA50"],
                    line=dict(color="#a855f7", width=1.1),
                    name="EMA50"
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=df15.index, y=df15["EMA200"],
                    line=dict(color="#f97316", width=1.1),
                    name="EMA200"
                ), row=1, col=1)

                # Pivot + Fibo (tylko linie poziome)
                fig.add_hline(y=d["pivot"], line_dash="dot", line_color="#e5e7eb", annotation_text="Pivot", row=1, col=1)
                for lvl_name, lvl_val in d["fibo"].items():
                    fig.add_hline(y=lvl_val, line_dash="dot", line_color="rgba(94,234,212,0.35)", row=1, col=1)

                # Wolumen
                fig.add_trace(go.Bar(
                    x=df15.index,
                    y=df15["Volume"],
                    marker_color="#4b5563",
                    name="Volume"
                ), row=2, col=1)

                # MACD
                fig.add_trace(go.Scatter(
                    x=df15.index, y=df15["MACD"],
                    line=dict(color="#22c55e", width=1),
                    name="MACD"
                ), row=3, col=1)
                fig.add_trace(go.Scatter(
                    x=df15.index, y=df15["MACD_signal"],
                    line=dict(color="#ef4444", width=1),
                    name="Signal"
                ), row=3, col=1)
                fig.add_trace(go.Bar(
                    x=df15.index, y=df15["MACD_hist"],
                    marker_color=np.where(df15["MACD_hist"] >= 0, "#22c55e", "#ef4444"),
                    name="Hist"
                ), row=3, col=1)

                fig.update_layout(
                    template="plotly_dark",
                    height=420,
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis_rangeslider_visible=False,
                    paper_bgcolor="#020617",
                    plot_bgcolor="#020617",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                fig.update_xaxes(showgrid=False)
                fig.update_yaxes(showgrid=False)

                st.plotly_chart(fig, use_container_width=True)

            st.markdown('</div>', unsafe_allow_html=True)

else:
    st.info("Wprowadź OpenAI API Key w pasku bocznym lub dodaj do Secrets.")
