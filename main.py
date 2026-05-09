# app.py
# TERMINAL v15 ULTRA — zaawansowany backtest, ATR sizing, SL/TP, multi-positions
# UI w języku polskim. Uruchom: streamlit run app.py
# Wymagane pakiety: streamlit, pandas, numpy, yfinance, ta, plotly, streamlit-autorefresh

import logging
import re
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import ta

# ============================================================
# KONFIGURACJA I LOGGER
# ============================================================
st.set_page_config(layout="wide", page_title="TERMINAL v15 ULTRA", page_icon="⚔️")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("terminal")

# ============================================================
# PROSTA STYLISTYKA (neon / glass)
# ============================================================
st.markdown("""
<style>
body { background: #0b1020; color: #e6eef8; }
section.main { background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); border-radius: 12px; padding: 12px; }
.stButton>button { background: linear-gradient(90deg,#0ea5a4,#7c3aed); color: white; border: none; }
.stDownloadButton>button { background: #1f2937; color: #fff; }
h1, h2, h3 { color: #f8fafc; }
.sidebar .stSlider>div>div>input { color: #fff; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR - USTAWIENIA
# ============================================================
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 60, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

st.sidebar.header("📡 Skaner i dane")
period_choice = st.sidebar.selectbox("Okres historyczny", ["1mo","3mo","6mo","1y","2y"], index=2)
interval_choice = st.sidebar.selectbox("Interwał", ["1d","1wk"], index=0)
max_workers = st.sidebar.slider("Wątki (równoległość)", 2, 20, 6)

st.sidebar.header("📈 Wykresy i wskaźniki")
show_sma = st.sidebar.checkbox("Pokaż SMA", value=True)
show_bb = st.sidebar.checkbox("Pokaż Bollinger Bands", value=True)
show_atr = st.sidebar.checkbox("Pokaż ATR", value=True)
show_fibo = st.sidebar.checkbox("Pokaż Fibonacci", value=True)
fibo_lookback = st.sidebar.slider("Fibo lookback (dni)", 20, 200, 50)

st.sidebar.header("⚖️ Pozycjonowanie i backtest")
use_atr_positioning = st.sidebar.checkbox("Użyj pozycjonowania opartego na ATR", value=True)
risk_per_trade_pct = st.sidebar.slider("Ryzyko na transakcję (% kapitału)", 0.1, 10.0, 1.0, step=0.1)
atr_multiplier = st.sidebar.slider("Stop = ATR *", 0.5, 5.0, 2.0, step=0.1)
tp_multiplier = st.sidebar.slider("Take Profit = ATR *", 0.5, 10.0, 2.0, step=0.1)
min_lot = st.sidebar.number_input("Minimalna wielkość lota (akcje)", value=1, step=1)
max_position_cap = st.sidebar.number_input("Maks. wartość pozycji (waluta)", value=5000.0, step=100.0)
fee_per_trade = st.sidebar.number_input("Prowizja na transakcję (waluta)", value=0.0, step=0.1)
slippage_pct = st.sidebar.slider("Poślizg (%)", 0.0, 2.0, 0.1, step=0.01)
max_concurrent_positions = st.sidebar.slider("Max jednoczesnych pozycji", 1, 10, 3)

initial_capital = st.sidebar.number_input("Kapitał początkowy", value=10000.0, step=100.0)

st.sidebar.header("🔎 Lista tickerów i portfolio")
default_list = "AAPL, NVDA, TSLA, AMD, MSFT"
symbols_input = st.sidebar.text_area("Lista tickerów (oddziel przecinkami)", default_list)
symbols = [s.strip().upper() for s in re.split(r'[,\s]+', symbols_input) if s.strip()]

portfolio_input = st.sidebar.text_area("Portfolio (SYMBOL,ILOŚĆ,CENA)", "NVDA,1,900\nSTX.WA,100,5.0")

st.sidebar.markdown("---")
run_scan_btn = st.sidebar.button("Uruchom skan")
run_backtest_btn = st.sidebar.button("Uruchom backtest (dla wybranego symbolu)")

# ============================================================
# OPENAI (opcjonalnie) - nie wymagane do działania
# ============================================================
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", None)
if OPENAI_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
    except Exception:
        client = None
else:
    client = None

# ============================================================
# POMOCNICZE FUNKCJE
# ============================================================
@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        return float(data['Close'].iloc[-1])
    except Exception:
        return 4.0

USD_PLN = get_usd_pln()

def safe_last(series):
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) > 0 else np.nan

def parse_portfolio(text):
    tickers = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r'[,\s]+', line) if p.strip()]
        if len(parts) < 3:
            continue
        sym, qty, b_p = parts[0].upper(), parts[1], parts[2]
        try:
            tickers[sym] = {"qty": float(qty), "buy": float(b_p)}
        except Exception:
            continue
    return tickers

def add_indicators_full(df):
    df = df.copy()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    bb = ta.volatility.BollingerBands(close=df["Close"], window=20, window_dev=2)
    df["BB_high"] = bb.bollinger_hband()
    df["BB_low"] = bb.bollinger_lband()
    df["ATR14"] = ta.volatility.AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()
    df["RSI14"] = ta.momentum.RSIIndicator(close=df["Close"], window=14).rsi()
    return df

def find_swing_high_low(df, lookback=50):
    s = df.dropna(subset=["High","Low"])
    if s.empty or len(s) < lookback:
        return None, None
    window = s.iloc[-lookback:]
    swing_high = window["High"].idxmax()
    swing_low = window["Low"].idxmin()
    return swing_high, swing_low

# ============================================================
# ANALIZA SYMBOLI (równoległe pobieranie)
# ============================================================
def analyze_symbol_basic(symbol, period="3mo", interval="1d"):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period=period, interval=interval)
        if df.empty or len(df) < 10:
            return None
        last_p = safe_last(df['Close'])
        df_ind = add_indicators_full(df)
        rsi = float(df_ind["RSI14"].dropna().iloc[-1]) if len(df_ind["RSI14"].dropna())>0 else np.nan
        ema20 = float(df_ind["EMA20"].dropna().iloc[-1]) if len(df_ind["EMA20"].dropna())>0 else np.nan
        ema50 = float(df_ind["EMA50"].dropna().iloc[-1]) if len(df_ind["EMA50"].dropna())>0 else np.nan
        score = 50
        # prosty scoring
        if not np.isnan(rsi):
            if rsi < 30: score += 20
            elif rsi > 70: score -= 20
        if not np.isnan(ema20) and not np.isnan(ema50) and ema20 > ema50:
            score += 10
        news = []
        try:
            news = [n.get('title','') for n in yf.Ticker(symbol).news[:2]]
        except Exception:
            news = []
        return {"Symbol": symbol, "Cena": round(last_p,2), "RSI": round(rsi,1) if not np.isnan(rsi) else np.nan, "Score": int(score), "News": " | ".join(news)}
    except Exception as e:
        logger.info(f"analyze_symbol_basic error {symbol}: {e}")
        return None

def scan_symbols_parallel(symbols, period="6mo", interval="1d", max_workers=6):
    results = []
    progress = st.progress(0)
    total = len(symbols) if symbols else 1
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(analyze_symbol_basic, s, period, interval): s for s in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception as e:
                logger.info(f"Błąd podczas skanowania {sym}: {e}")
            completed += 1
            progress.progress(int(completed/total * 100))
    return results

# ============================================================
# WYKRESY PLOTLY + FIBO
# ============================================================
def plot_candles_with_indicators(df, symbol, show_sma=True, show_bb=True, show_atr=True, show_fibo=True, fibo_lookback=50):
    df = df.copy()
    df = add_indicators_full(df)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="Cena", increasing_line_color="#00ff99", decreasing_line_color="#ff4d4d", opacity=0.95
    ))
    if show_sma:
        if "SMA20" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], mode="lines", line=dict(color="#ffd700", width=1), name="SMA20"))
        if "SMA50" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], mode="lines", line=dict(color="#00bfff", width=1), name="SMA50"))
    if "EMA20" in df.columns and "EMA50" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA20"], mode="lines", line=dict(color="#ffa500", width=1, dash="dash"), name="EMA20"))
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], mode="lines", line=dict(color="#1e90ff", width=1, dash="dash"), name="EMA50"))
    if show_bb and "BB_high" in df.columns and "BB_low" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_high"], mode="lines", line=dict(color="rgba(200,200,200,0.3)"), name="BB High", showlegend=False))
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_low"], mode="lines", line=dict(color="rgba(200,200,200,0.3)"), name="BB Low", fill='tonexty', fillcolor='rgba(200,200,200,0.05)', showlegend=False))
    # volume
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Wolumen", marker_color="rgba(100,100,255,0.3)", yaxis="y2"))
    fig.update_layout(template="plotly_dark", height=700, xaxis_rangeslider_visible=False,
                      yaxis=dict(title="Cena"), yaxis2=dict(title="Wolumen", overlaying="y", side="right", showgrid=False, position=0.15),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    # ATR scaled
    if show_atr and "ATR14" in df.columns:
        atr = df["ATR14"].fillna(0)
        scale = (df["Close"].max() - df["Close"].min()) / (atr.max() + 1e-9)
        atr_scaled = atr * 0.2 * scale
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"] - atr_scaled, mode="lines", line=dict(color="rgba(255,165,0,0.25)"), name="ATR14 (skala)"))
    # Fibonacci
    if show_fibo:
        sh_idx, sl_idx = find_swing_high_low(df, lookback=fibo_lookback)
        if sh_idx is not None and sl_idx is not None:
            sh = df.loc[sh_idx]["High"]
            sl = df.loc[sl_idx]["Low"]
            high = float(sh)
            low = float(sl)
            if high != low:
                diff = high - low
                levels = {
                    "0.0": high,
                    "0.236": high - 0.236 * diff,
                    "0.382": high - 0.382 * diff,
                    "0.5": high - 0.5 * diff,
                    "0.618": high - 0.618 * diff,
                    "0.786": high - 0.786 * diff,
                    "1.0": low
                }
                colors = {"0.0":"#ff4d4d","0.236":"#ff944d","0.382":"#ffd24d","0.5":"#ffff66","0.618":"#b3ff66","0.786":"#66ffb3","1.0":"#66d9ff"}
                for lvl, price in levels.items():
                    fig.add_hline(y=price, line=dict(color=colors.get(lvl,"#888"), width=1), annotation_text=f"Fibo {lvl} {price:.2f}", annotation_position="right", opacity=0.7)
                fig.add_trace(go.Scatter(x=[sh_idx], y=[high], mode="markers+text", marker=dict(color="#ff4d4d", size=8), text=["Swing High"], textposition="top right", showlegend=False))
                fig.add_trace(go.Scatter(x=[sl_idx], y=[low], mode="markers+text", marker=dict(color="#66d9ff", size=8), text=["Swing Low"], textposition="bottom right", showlegend=False))
    return fig

# ============================================================
# ZAawansowany BACKTEST ENGINE (SL/TP, ATR sizing, multi positions)
# ============================================================
def backtest_advanced(df, initial_capital=10000.0,
                      use_atr_positioning=True, risk_per_trade_pct=1.0, atr_multiplier=2.0, tp_multiplier=2.0,
                      min_lot=1, max_position_cap=5000.0, fee_per_trade=0.0, slippage_pct=0.1,
                      max_concurrent_positions=3):
    """
    Backtest engine:
    - wejście LONG: EMA20 > EMA50 AND RSI14 < 40
    - wyjście LONG: EMA20 < EMA50 OR RSI14 > 60 OR SL/TP hit
    - pozycjonowanie: ATR-based sizing (risk % of equity / (ATR * atr_multiplier))
    - SL = entry_price - stop_distance
    - TP = entry_price + tp_multiplier * stop_distance
    - jeśli SL/TP zostanie naruszony w świecy, zamykamy po otwarciu następnej świecy (prosty model)
    - uwzględnia fee_per_trade i slippage_pct (procent)
    - obsługa max_concurrent_positions (liczba otwartych pozycji jednocześnie)
    """
    df = add_indicators_full(df).copy()
    df = df.dropna(subset=["EMA20","EMA50","RSI14","Open","Close","ATR14"])
    if df.empty:
        return {"trades": [], "equity": pd.Series(dtype=float), "metrics": {}}

    equity = initial_capital
    cash = initial_capital
    open_positions = []  # lista dictów: {entry_idx, entry_price, shares, sl, tp, symbol(optional)}
    trades = []
    equity_series = []

    # helper to compute shares given equity and ATR
    def compute_shares(equity_val, price, atr, risk_pct, atr_mult, min_lot, max_pos_cap, cash_available):
        if atr is None or atr <= 0:
            # fallback: buy as many as possible respecting min_lot and max cap
            raw = int(cash_available // price)
            if raw < min_lot:
                return 0
            # enforce max position cap
            if raw * price > max_pos_cap:
                raw = int(max_pos_cap // price)
            return raw
        stop_distance = atr * atr_mult
        risk_amount = equity_val * (risk_pct / 100.0)
        raw_shares = int(risk_amount // stop_distance) if stop_distance > 0 else 0
        # enforce min lot
        if raw_shares < min_lot:
            raw_shares = 0
        # enforce max position cap
        if raw_shares * price > max_pos_cap:
            raw_shares = int(max_pos_cap // price)
        # enforce cash availability
        if raw_shares * price > cash_available:
            raw_shares = int(cash_available // price)
        if raw_shares < min_lot:
            return 0
        return raw_shares

    # iterate candles
    close_next_open_flags = []  # list of dicts: {pos_index, reason} to close at next open
    for i in range(len(df)-1):
        row = df.iloc[i]
        next_row = df.iloc[i+1]
        date = df.index[i+1]

        # 1) Check if any open position was flagged to close at this open (from previous candle SL/TP breach)
        if close_next_open_flags:
            # close all flagged positions at next_row['Open']
            for flag in close_next_open_flags:
                pos = flag["pos"]
                if pos in open_positions:
                    entry_price = pos["entry_price"]
                    shares = pos["shares"]
                    exit_price = next_row["Open"] * (1 - slippage_pct/100.0)  # assume sell slippage
                    # apply fee
                    cash += shares * exit_price
                    cash -= fee_per_trade
                    trades.append({"type":"SELL", "date": date, "price": exit_price, "shares": shares, "reason": flag.get("reason","SL/TP")})
                    open_positions.remove(pos)
            close_next_open_flags = []

        # 2) Evaluate SL/TP breaches within current candle for each open position
        for pos in list(open_positions):
            sl = pos["sl"]
            tp = pos["tp"]
            # if current candle low <= sl or high >= tp -> schedule close at next open
            if row["Low"] <= sl or row["High"] >= tp:
                close_next_open_flags.append({"pos": pos, "reason": "TP" if row["High"] >= tp else "SL"})

        # 3) Evaluate exit conditions (trend/RSI) for open positions - close at next open if triggered
        for pos in list(open_positions):
            # use indicators from current row to decide exit
            exit_signal = (row["EMA20"] < row["EMA50"]) or (row["RSI14"] > 60)
            if exit_signal:
                close_next_open_flags.append({"pos": pos, "reason": "SignalExit"})

        # 4) If we have capacity for new positions, check entry signal and open positions
        entry_signal = (row["EMA20"] > row["EMA50"]) and (row["RSI14"] < 40)
        while entry_signal and len(open_positions) < max_concurrent_positions:
            price = next_row["Open"] * (1 + slippage_pct/100.0)  # buy with slippage
            atr = row["ATR14"] if not np.isnan(row["ATR14"]) else None
            shares = compute_shares(equity, price, atr, risk_per_trade_pct, atr_multiplier, min_lot, max_position_cap, cash)
            if shares <= 0:
                break  # cannot open more positions
            # cost and fee
            cost = shares * price
            if cost > cash:
                # reduce shares to fit cash
                shares = int(cash // price)
                if shares < min_lot:
                    break
                cost = shares * price
            cash -= cost
            cash -= fee_per_trade
            stop_distance = (atr * atr_multiplier) if atr and atr > 0 else price * 0.02  # fallback 2%
            sl = price - stop_distance
            tp = price + tp_multiplier * stop_distance
            pos = {"entry_idx": i+1, "entry_price": price, "shares": shares, "sl": sl, "tp": tp}
            open_positions.append(pos)
            trades.append({"type":"BUY", "date": date, "price": price, "shares": shares, "atr": float(atr) if atr is not None else None})
            # after opening one position, re-evaluate if still can open another (loop)
            # update equity estimate
            market_val = sum([p["shares"] * row["Close"] for p in open_positions])
            equity = cash + market_val

            # break if cash insufficient for another position
            if cash < min_lot * price:
                break

            # optionally allow multiple entries in same candle if still entry_signal and capacity remains
            # but to avoid infinite loop, recompute shares with updated cash
            # recompute entry_signal remains same for this candle; allow loop to continue

        # 5) Update equity series (mark-to-market using current close)
        market_val = sum([p["shares"] * row["Close"] for p in open_positions])
        equity = cash + market_val
        equity_series.append((df.index[i], equity))

    # After loop, close any remaining open positions at last close price (apply slippage and fee)
    if open_positions:
        last_row = df.iloc[-1]
        for pos in list(open_positions):
            exit_price = last_row["Close"] * (1 - slippage_pct/100.0)
            cash += pos["shares"] * exit_price
            cash -= fee_per_trade
            trades.append({"type":"SELL", "date": df.index[-1], "price": exit_price, "shares": pos["shares"], "reason": "EOD"})
        open_positions = []
        equity = cash
        equity_series.append((df.index[-1], equity))

    equity_idx = [d for d,_ in equity_series]
    equity_vals = [v for _,v in equity_series]
    equity_series = pd.Series(data=equity_vals, index=equity_idx) if equity_vals else pd.Series(dtype=float)

    # METRYKI
    total_return = (equity_series.iloc[-1] - initial_capital) / initial_capital if len(equity_series)>0 else 0.0
    days = (equity_series.index[-1] - equity_series.index[0]).days if len(equity_series)>1 else 1
    cagr = ( (equity_series.iloc[-1] / initial_capital) ** (365.0 / days) - 1.0 ) if days>0 else 0.0
    # returns series (daily pct change)
    returns = equity_series.pct_change().dropna()
    sharpe = (returns.mean() / returns.std() * math.sqrt(252)) if (not returns.empty and returns.std() != 0) else None
    # trades stats
    closed_trades = []
    wins = 0
    for i in range(1, len(trades), 2):
        buy = trades[i-1]
        sell = trades[i] if i < len(trades) else None
        if sell:
            pnl = (sell["price"] - buy["price"]) * buy["shares"] - fee_per_trade*2
            closed_trades.append(pnl)
            if pnl > 0:
                wins += 1
    win_rate = (wins / len(closed_trades)) if closed_trades else None
    avg_win = np.mean([p for p in closed_trades if p>0]) if closed_trades and any(p>0 for p in closed_trades) else None
    avg_loss = np.mean([p for p in closed_trades if p<0]) if closed_trades and any(p<0 for p in closed_trades) else None
    max_dd = None
    if not equity_series.empty:
        roll_max = equity_series.cummax()
        drawdown = (equity_series - roll_max) / roll_max
        max_dd = drawdown.min()
    avg_position_size = np.mean([t["shares"]*t["price"] if t["type"]=="BUY" else 0 for t in trades]) if trades else None

    metrics = {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": max_dd,
        "num_trades": len(trades),
        "avg_position_size": avg_position_size
    }

    return {"trades": trades, "equity": equity_series, "metrics": metrics}

# ============================================================
# UI - GŁÓWNY PANEL
# ============================================================
st.title("⚔️ TERMINAL v15 ULTRA — Zaawansowany Backtest i ATR Sizing")

# Scan section
st.header("📊 Skaner tickerów")
st.write("Lista tickerów do analizy:")
st.write(", ".join(symbols))
if run_scan_btn:
    with st.spinner("Skanuję tickery..."):
        scan_results = scan_symbols_parallel(symbols, period=period_choice, interval=interval_choice, max_workers=max_workers)
        if scan_results:
            df_scan = pd.DataFrame(scan_results)
            st.dataframe(df_scan.sort_values("Score", ascending=False))
            csv = df_scan.to_csv(index=False).encode('utf-8')
            st.download_button("Pobierz wyniki skanu (CSV)", data=csv, file_name="scan_results.csv", mime="text/csv")
        else:
            st.info("Brak wyników skanu. Sprawdź tickery i połączenie internetowe.")

# Chart and backtest section
st.header("📉 Wykresy, Fibonacci i Backtest")
col1, col2 = st.columns([3,1])

with col1:
    selected_symbol = st.selectbox("Wybierz ticker do wykresu i backtestu", symbols)
    if selected_symbol:
        t = yf.Ticker(selected_symbol)
        df_chart = t.history(period=period_choice, interval=interval_choice)
        if df_chart.empty:
            st.info("Brak danych dla wybranego symbolu.")
        else:
            fig = plot_candles_with_indicators(df_chart, selected_symbol, show_sma=show_sma, show_bb=show_bb, show_atr=show_atr, show_fibo=show_fibo, fibo_lookback=fibo_lookback)
            st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("### Opis Fibonacci")
    st.markdown("""
- Poziomy Fibonacciego rysowane są między ostatnim **Swing High** i **Swing Low** w oknie `fibo_lookback`.
- Poziomy: **0.0 (High)**, **0.236**, **0.382**, **0.5**, **0.618**, **0.786**, **1.0 (Low)**.
- Interpretacja: traktuj jako potencjalne wsparcia/opory; używaj razem z RSI, wolumenem i trendem EMA.
""")
    st.markdown("### Parametry backtestu (aktualne)")
    st.write(f"Kapitał początkowy: **{initial_capital:.2f}**")
    st.write(f"ATR sizing: **{use_atr_positioning}**, ryzyko: **{risk_per_trade_pct}%**, ATR stop x{atr_multiplier}, TP x{tp_multiplier}")
    st.write(f"Min lot: **{min_lot}**, Max pos cap: **{max_position_cap}**, Max concurrent pos: **{max_concurrent_positions}**")
    st.write(f"Prowizja: **{fee_per_trade}**, Poślizg: **{slippage_pct}%**")

# Run backtest button
if run_backtest_btn:
    if not selected_symbol:
        st.error("Wybierz symbol do backtestu.")
    else:
        with st.spinner("Uruchamiam zaawansowany backtest..."):
            t = yf.Ticker(selected_symbol)
            df_chart = t.history(period=period_choice, interval=interval_choice)
            if df_chart.empty:
                st.error("Brak danych historycznych dla wybranego symbolu.")
            else:
                res = backtest_advanced(df_chart, initial_capital=initial_capital,
                                        use_atr_positioning=use_atr_positioning,
                                        risk_per_trade_pct=risk_per_trade_pct,
                                        atr_multiplier=atr_multiplier,
                                        tp_multiplier=tp_multiplier,
                                        min_lot=int(min_lot),
                                        max_position_cap=max_position_cap,
                                        fee_per_trade=fee_per_trade,
                                        slippage_pct=slippage_pct,
                                        max_concurrent_positions=int(max_concurrent_positions))
                metrics = res["metrics"]
                st.subheader("📋 Metryki backtestu")
                st.write(f"Łączny zwrot: **{metrics.get('total_return',0.0)*100:.2f}%**")
                st.write(f"CAGR (przybliżone): **{metrics.get('cagr',0.0)*100:.2f}%**")
                st.write(f"Sharpe (przybliżone): **{metrics.get('sharpe'):.2f}**" if metrics.get('sharpe') is not None else "Sharpe: brak danych")
                st.write(f"Win rate: **{metrics.get('win_rate')*100:.1f}%**" if metrics.get('win_rate') is not None else "Win rate: brak danych")
                st.write(f"Max Drawdown: **{metrics.get('max_drawdown')*100:.2f}%**" if metrics.get('max_drawdown') is not None else "Max Drawdown: brak danych")
                st.write(f"Liczba transakcji: **{metrics.get('num_trades',0)}**")
                if not res["equity"].empty:
                    eq_fig = go.Figure()
                    eq_fig.add_trace(go.Scatter(x=res["equity"].index, y=res["equity"].values, mode="lines", name="Equity", line=dict(color="#00ff99")))
                    eq_fig.update_layout(template="plotly_dark", height=300, yaxis_title="Kapitał")
                    st.plotly_chart(eq_fig, use_container_width=True)
                if res["trades"]:
                    df_trades = pd.DataFrame(res["trades"])
                    st.subheader("📑 Lista transakcji")
                    st.table(df_trades)
                    csv_trades = df_trades.to_csv(index=False).encode('utf-8')
                    st.download_button("Pobierz transakcje (CSV)", data=csv_trades, file_name="trades.csv", mime="text/csv")
                else:
                    st.info("Brak transakcji w backtestcie.")

# ============================================================
# PORTFOLIO - wyświetlenie
# ============================================================
st.header("💼 Twoje pozycje (szacunkowo)")
try:
    tickers = parse_portfolio(portfolio_input)
    port_data = []
    for sym, info in tickers.items():
        t = yf.Ticker(sym)
        df_p = t.history(period="1d")
        if df_p.empty:
            continue
        price = safe_last(df_p["Close"])
        qty = info["qty"]
        buy = info["buy"]
        is_pln = sym.endswith(".WA")
        cur_val = price * qty * (1 if is_pln else USD_PLN)
        buy_val = buy * qty * (1 if is_pln else USD_PLN)
        port_data.append({"Symbol": sym, "Cena (waluta)": price, "Wartość PLN": round(cur_val,2), "Zysk PLN": round(cur_val - buy_val,2)})
    if port_data:
        dfp = pd.DataFrame(port_data)
        st.table(dfp)
        st.metric("SUMA ZYSKU (PLN)", f"{round(sum(d['Zysk PLN'] for d in port_data),2)} PLN")
    else:
        st.info("Brak pozycji do wyświetlenia.")
except Exception as e:
    logger.exception(f"Portfolio error: {e}")
    st.info("Błąd przy wczytywaniu portfolio.")

# ============================================================
# KONIEC PLIKU
# ============================================================

# Instrukcja uruchomienia testów (pytest)
# 1) Przygotuj plik testowy (np. test_terminal.py) z testami dla parse_portfolio i backtest_advanced.
# 2) Uruchom: pytest -q
# (Wcześniej upewnij się, że masz zainstalowane pytest: pip install pytest)
#
# Przykładowe testy (nie dołączone jako plik tutaj):
# - test_parse_portfolio_basic: sprawdza, że parse_portfolio poprawnie parsuje linie i pomija błędne.
# - test_backtest_runs: generuje sztuczne OHLCV (pandas DataFrame), wywołuje backtest_advanced i sprawdza, że zwraca dict z kluczami 'trades' i 'equity'.
#
# Powodzenia — w poniedziałek testujemy 1:1.

