# app.py - TERMINAL v15 ULTRA (ATR position sizing + backtest + fibo)
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import math

import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import ta

# ============================================================
# KONFIGURACJA APLIKACJI
# ============================================================
st.set_page_config(layout="wide", page_title="TERMINAL v15 ULTRA", page_icon="⚔️")

# ============================================================
# LOGGER
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("terminal")

# ============================================================
# UI — CSS (opcjonalne)
# ============================================================
st.markdown("""
<style>
/* TWÓJ CSS BEZ ZMIAN */
</style>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR USTAWIENIA
# ============================================================
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

st.sidebar.header("🤖 MODEL AI")
model_choice = st.sidebar.selectbox(
    "Wybierz model",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini"],
    index=0
)

st.sidebar.header("🎨 Styl tabeli")
table_style = st.sidebar.radio(
    "Wybierz styl:",
    ["Kolor wiersza (RSI)", "Gradient RSI", "Ikony ↑↓"],
    index=0
)

# Period / interval / parallelism
period_choice = st.sidebar.selectbox("Okres historyczny", ["1mo","3mo","6mo","1y","2y"], index=2)
interval_choice = st.sidebar.selectbox("Interwał", ["1d","1wk","1h"], index=0)
max_workers = st.sidebar.slider("Wątki (równoległość)", 2, 20, 6)

# Plot/backtest controls
st.sidebar.header("📈 Wykresy i Backtest")
show_sma = st.sidebar.checkbox("Pokaż SMA", value=True)
show_bb = st.sidebar.checkbox("Pokaż Bollinger Bands", value=True)
show_atr = st.sidebar.checkbox("Pokaż ATR", value=True)
show_fibo = st.sidebar.checkbox("Pokaż Fibonacci", value=True)
fibo_lookback = st.sidebar.slider("Fibo lookback (dni)", 20, 200, 50)
enable_backtest = st.sidebar.checkbox("Uruchom backtest prostej strategii", value=False)
initial_capital = st.sidebar.number_input("Kapitał początkowy", value=10000, step=1000)

# ATR position sizing controls
st.sidebar.header("⚖️ Pozycjonowanie (ATR)")
use_atr_positioning = st.sidebar.checkbox("Użyj pozycjonowania opartego na ATR", value=True)
risk_per_trade_pct = st.sidebar.slider("Ryzyko na transakcję (% kapitału)", 0.1, 10.0, 1.0, step=0.1)
atr_multiplier_for_stop = st.sidebar.slider("Stop = ATR *", 0.5, 5.0, 2.0, step=0.1)

# ============================================================
# OPENAI CLIENT
# ============================================================
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", None)
if OPENAI_KEY:
    client = OpenAI(api_key=OPENAI_KEY)
else:
    client = None
    logger.info("Brak OPENAI_API_KEY w st.secrets")

# ============================================================
# INPUTY
# ============================================================
st.sidebar.header("💰 PORTFOLIO (PLN)")
portfolio_input = st.sidebar.text_area("SYMBOL,ILOŚĆ,CENA", "NVDA,1,900\nSTX.WA,100,5.0")

st.sidebar.header("📡 SKANER MASOWY")
default_list = "IOVA, STX.WA, PGV.WA, ATT.WA, NVDA, AAPL, TSLA, AMD"
symbols_input = st.sidebar.text_area("Lista do analizy", default_list)
symbols = [s.strip().upper() for s in re.split(r'[,\s]+', symbols_input) if s.strip()]

st.title(f"⚔️ TERMINAL v15 ULTRA — REFRESH: {refresh_val} MIN")

# ============================================================
# POMOCNICZE FUNKCJE
# ============================================================
@st.cache_data(ttl=3600)
def get_usd_pln():
    try:
        data = yf.Ticker("USDPLN=X").history(period="1d")
        return float(data['Close'].iloc[-1])
    except Exception as e:
        logger.info(f"Nie udało się pobrać kursu USD/PLN: {e}")
        return 4.0

USD_PLN = get_usd_pln()

def safe_last(series):
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) > 0 else np.nan

def is_pln(sym):
    return sym.upper().endswith(".WA")

def get_beast_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = [n.get('title', '') for n in t.news[:2]]
        return " | ".join(news) if news else "Brak newsów."
    except Exception as e:
        logger.info(f"get_beast_news error for {symbol}: {e}")
        return "Brak danych."

def parse_portfolio(text):
    tickers = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r'[,\s]+', line) if p.strip()]
        if len(parts) < 3:
            logger.info(f"Pominięto linię portfolio (niepoprawny format): {line}")
            continue
        sym, qty, b_p = parts[0].upper(), parts[1], parts[2]
        try:
            tickers[sym] = {"qty": float(qty), "buy": float(b_p)}
        except Exception:
            logger.info(f"Nie udało się sparsować linię portfolio: {line}")
            continue
    return tickers

# ============================================================
# ANALIZA SYMBOLI (bezpieczna, z walidacjami)
# ============================================================
def analyze_symbol(symbol, period="3mo", interval="1d"):
    try:
        logger.info(f"Analizuję {symbol}")
        t = yf.Ticker(symbol)
        df = t.history(period=period, interval=interval)

        if df.empty or len(df) < 10:
            logger.info(f"Za mało danych dla {symbol}")
            return None

        last_p = safe_last(df['Close'])
        if np.isnan(last_p):
            return None

        # RSI
        try:
            rsi_series = ta.momentum.RSIIndicator(close=df['Close'], window=14).rsi()
            rsi_value = float(rsi_series.dropna().iloc[-1]) if len(rsi_series.dropna())>0 else np.nan
        except Exception:
            rsi_value = np.nan

        # Momentum 10d
        if len(df['Close'].dropna()) > 10:
            mom = ((last_p - df['Close'].iloc[-10]) / df['Close'].iloc[-10]) * 100
        else:
            mom = np.nan

        # EMA trend
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1] if len(df['Close'].dropna())>=20 else np.nan
        ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1] if len(df['Close'].dropna())>=50 else np.nan
        ema_trend = int(not np.isnan(ema20) and not np.isnan(ema50) and ema20 > ema50)

        # MACD
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_last = float(macd.dropna().iloc[-1]) if len(macd.dropna())>0 else np.nan
        signal_last = float(signal.dropna().iloc[-1]) if len(signal.dropna())>0 else np.nan
        macd_trend = int(not np.isnan(macd_last) and not np.isnan(signal_last) and macd_last > signal_last)

        # Volatility
        vol10 = df['Close'].pct_change().rolling(10).std().iloc[-1] * 100 if len(df['Close'].dropna())>=10 else np.nan

        # Volume surge
        vol_now = safe_last(df['Volume'])
        vol_avg = df['Volume'].rolling(20).mean().iloc[-1] if len(df['Volume'].dropna())>=20 else np.nan
        vol_surge = round((vol_now / vol_avg) * 100, 1) if vol_avg and not np.isnan(vol_avg) and vol_avg > 0 else np.nan

        # High/Low 20
        high20 = df['High'].rolling(20).max().iloc[-1] if len(df['High'].dropna())>=20 else np.nan
        low20 = df['Low'].rolling(20).min().iloc[-1] if len(df['Low'].dropna())>=20 else np.nan

        dist_high20 = round((last_p / high20 - 1) * 100, 2) if not np.isnan(high20) and high20>0 else np.nan
        dist_low20 = round((last_p / low20 - 1) * 100, 2) if not np.isnan(low20) and low20>0 else np.nan

        news = get_beast_news(symbol)

        # scoring
        score = 0
        if not np.isnan(rsi_value):
            if rsi_value < 30: score += 25
            elif rsi_value < 40: score += 15
            elif rsi_value > 70: score -= 20

        if not np.isnan(mom):
            if mom > 5: score += 15
            elif mom < -5: score += 10

        score += 15 if ema_trend else -5
        if macd_trend: score += 15

        if not np.isnan(vol_surge):
            if vol_surge > 150: score += 15
            elif vol_surge > 100: score += 8

        if not np.isnan(dist_low20) and dist_low20 < 5: score += 10
        if not np.isnan(dist_high20) and dist_high20 > -5: score -= 10

        score = max(0, min(100, score))

        if score >= 70: signal_tag = "BUY"
        elif score <= 30: signal_tag = "SELL"
        else: signal_tag = "NEUTRAL"

        # fundamentals (light)
        try:
            info = t.info
            marketCap = info.get("marketCap")
            sector = info.get("sector")
            trailingPE = info.get("trailingPE")
            currency = info.get("currency")
        except Exception:
            marketCap = sector = trailingPE = currency = None

        return {
            "Symbol": symbol,
            "Cena": round(last_p, 2),
            "RSI": round(rsi_value, 1) if not np.isnan(rsi_value) else np.nan,
            "Mom% 10d": round(mom, 2) if not np.isnan(mom) else np.nan,
            "EMA20>EMA50": ema_trend,
            "MACD>Signal": macd_trend,
            "Volatility10d": round(vol10, 2) if not np.isnan(vol10) else np.nan,
            "VolumeSurge%": vol_surge,
            "DistHigh20%": dist_high20,
            "DistLow20%": dist_low20,
            "Score": int(score),
            "Signal": signal_tag,
            "News": news,
            "marketCap": marketCap,
            "sector": sector,
            "trailingPE": trailingPE,
            "currency": currency
        }

    except Exception as e:
        logger.exception(f"Błąd w analyze_symbol dla {symbol}: {e}")
        return None

# ============================================================
# RÓWNOLEGŁE SKANOWANIE
# ============================================================
st.subheader("📊 Wyniki Skanowania")

def scan_symbols_parallel(symbols, period="6mo", interval="1d", max_workers=6):
    results = []
    progress = st.progress(0)
    total = len(symbols) if symbols else 1
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(analyze_symbol, s, period, interval): s for s in symbols}
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

results_list = scan_symbols_parallel(symbols, period=period_choice, interval=interval_choice, max_workers=max_workers)
results = pd.DataFrame(results_list)

# Stylizacja i eksport
def highlight_row_rsi(row):
    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi): return [""] * len(row)
    if rsi < 30: return ["background-color: rgba(0,120,0,0.25)"] * len(row)
    if rsi > 70: return ["background-color: rgba(120,0,0,0.25)"] * len(row)
    return [""] * len(row)

def gradient_rsi(val):
    if pd.isna(val): return ""
    v = max(0, min(float(val), 100))
    r = int(180 * (v / 100))
    g = int(180 * (1 - v / 100))
    return f"background-color: rgba({r},{g},40,0.25)"

def add_icons(df):
    df = df.copy()
    df["RSI"] = df["RSI"].apply(lambda x: f"{x} 🔻" if x < 30 else (f"{x} 🔺" if x > 70 else f"{x} ➖"))
    df["Mom% 10d"] = df["Mom% 10d"].apply(lambda x: f"{x}% 📈" if x > 0 else f"{x}% 📉")
    return df

if results.empty:
    st.info("Brak wyników do wyświetlenia. Sprawdź listę tickerów.")
else:
    if table_style == "Kolor wiersza (RSI)":
        st.dataframe(results.style.apply(highlight_row_rsi, axis=1))
    elif table_style == "Gradient RSI":
        st.dataframe(results.style.map(gradient_rsi, subset=['RSI']))
    elif table_style == "Ikony ↑↓":
        st.dataframe(add_icons(results))

    csv = results.to_csv(index=False).encode('utf-8')
    st.download_button("Pobierz wyniki CSV", data=csv, file_name="scan_results.csv", mime="text/csv")

# ============================================================
# AI — ANALIZA (ograniczony prompt)
# ============================================================
st.divider()
st.subheader(f"🤖 GENESIS AI ({model_choice}) — WYROK ZBIORCZY")

if not results.empty and client:
    top_for_ai = results.sort_values("Score", ascending=False).head(10).to_dict(orient="records")
else:
    top_for_ai = []

prompt = {
    "data": top_for_ai,
    "usd_pln": USD_PLN,
    "task": "Przeanalizuj Score, RSI, Momentum, Trend EMA, MACD, Volume Surge i News. Wybierz Top 3 okazje oraz 3 zagrożenia. Podaj SYMBOL - POWÓD."
}

with st.spinner("AI analizuje rynek..."):
    if client and top_for_ai:
        try:
            res_ai = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "system", "content": "Jesteś brutalnym zarządzającym funduszem hedgingowym."},
                    {"role": "user", "content": str(prompt)}
                ],
                temperature=0.2
            )
            st.warning("RAPORT STRATEGICZNY:")
            st.write(res_ai.choices[0].message.content)
        except Exception as e:
            logger.info(f"Błąd AI: {e}")
            st.error(f"Błąd AI: {e}")
    else:
        if not client:
            st.info("Brak klucza OpenAI — pomijam analizę AI.")
        else:
            st.info("Brak danych do analizy AI.")

st.subheader("🏆 Ranking AI")

# ============================================================
# WYKRESY ŚWIECOWE + SMA/BB/ATR + FIBONACCI + BACKTEST (z ATR sizing)
# ============================================================
st.subheader("📉 Wykresy świecowe + wskaźniki")

selected_symbol = st.selectbox("Wybierz ticker do wykresu", symbols)

# --- pomocnicze funkcje do wykresów, fibo i backtestu ---
def add_indicators_full(df):
    df = df.copy()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    bb = ta.volatility.BollingerBands(close=df["Close"], window=20, window_dev=2)
    df["BB_high"] = bb.bollinger_hband()
    df["BB_low"] = bb.bollinger_lband()
    df["ATR14"] = ta.volatility.AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()
    df["RSI14"] = ta.momentum.RSIIndicator(close=df["Close"], window=14).rsi()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    return df

def find_swing_high_low(df, lookback=50):
    s = df.dropna(subset=["High","Low"])
    if s.empty or len(s) < lookback:
        return None, None
    window = s.iloc[-lookback:]
    swing_high = window["High"].idxmax()
    swing_low = window["Low"].idxmin()
    return swing_high, swing_low

def plot_candles_with_indicators(df, symbol, show_sma=True, show_bb=True, show_atr=True, show_fibo=True, fibo_lookback=50):
    df = df.copy()
    df = add_indicators_full(df)

    fig = go.Figure()

    # Candles
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="Cena", increasing_line_color="#00ff99", decreasing_line_color="#ff4d4d", opacity=0.9
    ))

    # SMA
    if show_sma and "SMA20" in df.columns and "SMA50" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], mode="lines", line=dict(color="#ffd700", width=1), name="SMA20"))
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], mode="lines", line=dict(color="#00bfff", width=1), name="SMA50"))

    # EMA
    if "EMA20" in df.columns and "EMA50" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA20"], mode="lines", line=dict(color="#ffa500", width=1, dash="dash"), name="EMA20"))
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], mode="lines", line=dict(color="#1e90ff", width=1, dash="dash"), name="EMA50"))

    # Bollinger Bands
    if show_bb and "BB_high" in df.columns and "BB_low" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_high"], mode="lines", line=dict(color="rgba(200,200,200,0.3)"), name="BB High", showlegend=False))
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_low"], mode="lines", line=dict(color="rgba(200,200,200,0.3)"), name="BB Low", fill='tonexty', fillcolor='rgba(200,200,200,0.05)', showlegend=False))

    # Volume as bar on secondary y
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Wolumen", marker_color="rgba(100,100,255,0.3)", yaxis="y2"))

    # Layout with secondary y for volume
    fig.update_layout(
        template="plotly_dark",
        height=700,
        xaxis_rangeslider_visible=False,
        yaxis=dict(title="Cena"),
        yaxis2=dict(title="Wolumen", overlaying="y", side="right", showgrid=False, position=0.15),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    # ATR (skalowany i rysowany jako linia pod ceną)
    if show_atr and "ATR14" in df.columns:
        atr = df["ATR14"].fillna(0)
        scale = (df["Close"].max() - df["Close"].min()) / (atr.max() + 1e-9)
        atr_scaled = atr * 0.2 * scale
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"] - atr_scaled, mode="lines", line=dict(color="rgba(255,165,0,0.25)"), name="ATR14 (skala)", showlegend=True))

    # Fibonacci levels
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
                colors = {
                    "0.0":"#ff4d4d","0.236":"#ff944d","0.382":"#ffd24d","0.5":"#ffff66","0.618":"#b3ff66","0.786":"#66ffb3","1.0":"#66d9ff"
                }
                for lvl, price in levels.items():
                    fig.add_hline(y=price, line=dict(color=colors.get(lvl,"#888"), width=1), annotation_text=f"Fibo {lvl} {price:.2f}", annotation_position="right", opacity=0.7)

                # annotate swing points
                fig.add_trace(go.Scatter(x=[sh_idx], y=[high], mode="markers+text", marker=dict(color="#ff4d4d", size=8), text=["Swing High"], textposition="top right", showlegend=False))
                fig.add_trace(go.Scatter(x=[sl_idx], y=[low], mode="markers+text", marker=dict(color="#66d9ff", size=8), text=["Swing Low"], textposition="bottom right", showlegend=False))

    return fig

def backtest_simple_strategy(df, initial_capital=10000, slippage=0.0, fee=0.0,
                             use_atr_positioning=True, risk_per_trade_pct=1.0, atr_multiplier=2.0):
    """
    Backtest z opcjonalnym pozycjonowaniem opartym na ATR.
    - Wejście LONG: EMA20 > EMA50 AND RSI14 < 40
    - Wyjście LONG: EMA20 < EMA50 OR RSI14 > 60
    - Jeśli use_atr_positioning: rozmiar pozycji = floor((kapitał * risk_per_trade_pct) / (atr * atr_multiplier))
      gdzie atr to ATR14 z ostatniej świecy, a stop distance = atr * atr_multiplier.
    - Wejścia/wyjścia po otwarciu następnej świecy.
    """
    df = add_indicators_full(df).copy()
    df = df.dropna(subset=["EMA20","EMA50","RSI14","Open","Close","ATR14"])
    if df.empty:
        return {"trades":[], "equity": pd.Series(dtype=float), "total_return":0.0, "win_rate":None, "max_drawdown":None}

    position = 0
    cash = initial_capital
    shares = 0
    equity_series = []
    trades = []

    for i in range(len(df)-1):
        row = df.iloc[i]
        next_row = df.iloc[i+1]
        date = df.index[i+1]

        enter = (row["EMA20"] > row["EMA50"]) and (row["RSI14"] < 40)
        exit = (row["EMA20"] < row["EMA50"]) or (row["RSI14"] > 60)

        if position == 0 and enter:
            buy_price = next_row["Open"] * (1 + slippage) + fee

            if use_atr_positioning:
                atr = row["ATR14"] if not np.isnan(row["ATR14"]) and row["ATR14"]>0 else None
                if atr is None or atr == 0:
                    # fallback: buy minimal 1 share if no ATR
                    shares = int(cash // buy_price)
                else:
                    stop_distance = atr * atr_multiplier
                    risk_amount = cash * (risk_per_trade_pct / 100.0)
                    # shares = floor(risk_amount / stop_distance / buy_price) * buy_price? No: risk per share = stop_distance
                    # number of shares = floor(risk_amount / (stop_distance))
                    # but stop_distance is in price units, risk per share = stop_distance
                    shares = int(risk_amount // stop_distance)
                    # ensure shares priced fit cash
                    if shares * buy_price > cash:
                        shares = int(cash // buy_price)
            else:
                shares = int(cash // buy_price)

            if shares > 0:
                cost = shares * buy_price
                cash -= cost
                position = 1
                trades.append({"type":"BUY","date":date,"price":buy_price,"shares":shares, "atr": float(row.get("ATR14", np.nan))})
        elif position == 1 and exit:
            sell_price = next_row["Open"] * (1 - slippage) - fee
            cash += shares * sell_price
            trades.append({"type":"SELL","date":date,"price":sell_price,"shares":shares})
            shares = 0
            position = 0

        market_val = shares * row["Close"]
        equity = cash + market_val
        equity_series.append((df.index[i], equity))

    if position == 1 and shares > 0:
        final_price = df.iloc[-1]["Close"]
        cash += shares * final_price
        trades.append({"type":"SELL","date":df.index[-1],"price":final_price,"shares":shares})
        shares = 0
        position = 0

    equity_idx = [d for d,_ in equity_series]
    equity_vals = [v for _,v in equity_series]
    equity_series = pd.Series(data=equity_vals, index=equity_idx) if equity_vals else pd.Series(dtype=float)

    total_return = (equity_series.iloc[-1] - initial_capital) / initial_capital if len(equity_series)>0 else 0.0

    wins = 0
    closed_trades = []
    for i in range(1, len(trades), 2):
        buy = trades[i-1]
        sell = trades[i]
        pnl = (sell["price"] - buy["price"]) * buy["shares"]
        closed_trades.append(pnl)
        if pnl > 0: wins += 1
    win_rate = wins / (len(closed_trades)) if closed_trades else None

    if not equity_series.empty:
        roll_max = equity_series.cummax()
        drawdown = (equity_series - roll_max) / roll_max
        max_dd = drawdown.min()
    else:
        max_dd = None

    return {
        "trades": trades,
        "equity": equity_series,
        "total_return": total_return,
        "win_rate": win_rate,
        "max_drawdown": max_dd,
        "closed_trades": closed_trades
    }

# --- render wykres i backtest ---
if selected_symbol:
    t = yf.Ticker(selected_symbol)
    df_chart = t.history(period=period_choice, interval=interval_choice)
    if not df_chart.empty:
        fig = plot_candles_with_indicators(df_chart, selected_symbol, show_sma=show_sma, show_bb=show_bb, show_atr=show_atr, show_fibo=show_fibo, fibo_lookback=fibo_lookback)
        st.plotly_chart(fig, use_container_width=True)

        # Backtest
        if enable_backtest:
            with st.spinner("Uruchamiam backtest..."):
                bt = backtest_simple_strategy(df_chart, initial_capital=initial_capital,
                                              use_atr_positioning=use_atr_positioning,
                                              risk_per_trade_pct=risk_per_trade_pct,
                                              atr_multiplier=atr_multiplier_for_stop)
                st.subheader("Wyniki backtestu")
                st.write(f"**Łączny zwrot**: {bt['total_return']*100:.2f}%")
                st.write(f"**Liczba transakcji**: {len(bt['trades'])}")
                st.write(f"**Win rate**: {bt['win_rate']*100:.1f}% " if bt['win_rate'] is not None else "Win rate: brak zamkniętych transakcji")
                st.write(f"**Max Drawdown**: {bt['max_drawdown']*100:.2f}%" if bt['max_drawdown'] is not None else "Max Drawdown: brak danych")

                if not bt['equity'].empty:
                    eq_fig = go.Figure()
                    eq_fig.add_trace(go.Scatter(x=bt['equity'].index, y=bt['equity'].values, mode="lines", name="Equity"))
                    eq_fig.update_layout(template="plotly_dark", height=300, yaxis_title="Kapitał")
                    st.plotly_chart(eq_fig, use_container_width=True)

                if bt['trades']:
                    df_trades = pd.DataFrame(bt['trades'])
                    st.table(df_trades)
    else:
        st.info("Brak danych do wykresu dla wybranego symbolu.")

# ============================================================
# PORTFOLIO
# ============================================================
st.divider()
st.subheader(f"📈 Twoje Pozycje (Kurs USD/PLN: {round(USD_PLN, 2)})")

try:
    port_data = []
    tickers = parse_portfolio(portfolio_input)

    for sym, info in tickers.items():
        t = yf.Ticker(sym)
        df_p = t.history(period="1d")
        if df_p.empty:
            logger.info(f"Brak danych dla {sym} w portfolio")
            continue

        price = safe_last(df_p["Close"])
        if np.isnan(price):
            continue

        qty = info["qty"]
        buy = info["buy"]

        cur_val = price * qty * (USD_PLN if not is_pln(sym) else 1)
        buy_val = buy * qty * (USD_PLN if not is_pln(sym) else 1)

        port_data.append({
            "Symbol": sym,
            "Cena (waluta)": price,
            "Wartość PLN": round(cur_val, 2),
            "Zysk PLN": round(cur_val - buy_val, 2)
        })

    if port_data:
        dfp = pd.DataFrame(port_data)
        st.table(dfp)
        st.metric("SUMA ZYSKU (PLN)", f"{round(sum(d['Zysk PLN'] for d in port_data), 2)} PLN")
    else:
        st.info("Brak pozycji do wyświetlenia w portfolio.")

except Exception as e:
    logger.exception(f"Błąd w sekcji portfolio: {e}")
    st.info("Oczekiwanie na poprawne dane portfolio... (Format: SYMBOL,ILOŚĆ,CENA)")

# ============================================================
# KONIEC PLIKU
# ============================================================
