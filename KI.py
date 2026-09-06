import os
import re
import json
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ------------------ PERSYSTENCJA ------------------
_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

def _load_state():
    """Wczytuje zapisane tickery i ustawienia z state.json."""
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_state(data: dict):
    """Zapisuje tickery i ustawienia do state.json."""
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def _load_user_tickers() -> list:
    d = _load_state()
    return d.get("tickers", [])

def _save_user_tickers(tickers: list):
    d = _load_state()
    d["tickers"] = tickers
    _save_state(d)

def _load_last_scan() -> dict:
    d = _load_state()
    return d.get("last_scan", {})

def _save_last_scan(results: dict):
    d = _load_state()
    d["last_scan"] = results
    _save_state(d)

def _load_settings() -> dict:
    d = _load_state()
    return d.get("settings", {})

def _save_settings(settings: dict):
    d = _load_state()
    d["settings"] = settings
    _save_state(d)

def _load_alerts() -> dict:
    d = _load_state()
    return d.get("alerts", {})

def _save_alerts(alerts: dict):
    d = _load_state()
    d["alerts"] = alerts
    _save_state(d)

def _load_backtest_results() -> dict:
    d = _load_state()
    return d.get("backtest", {})

def _save_backtest_results(data: dict):
    d = _load_state()
    d["backtest"] = data
    _save_state(d)

def _load_portfolio() -> list:
    """Ładuje portfel: lista dict {ticker, shares, avg_price}."""
    d = _load_state()
    return d.get("portfolio", [])

def _save_portfolio(portfolio: list):
    d = _load_state()
    d["portfolio"] = portfolio
    _save_state(d)

# ------------------ KONFIGURACJA ------------------
st.set_page_config(page_title="CYBER DESK PRO", page_icon="💠", layout="wide")

st.markdown(
    """
    <style>
    body, .stApp { background-color: #050816; color: #E0E0FF; }
    .stSidebar, section[data-testid="stSidebar"] { background: radial-gradient(circle at top, #111827 0, #020617 60%); color: #E0E0FF; }
    .stButton>button { background: linear-gradient(90deg, #0ea5e9, #6366f1); color: white; border-radius: 8px; border: none; }
    .stButton>button:hover { background: linear-gradient(90deg, #22c55e, #6366f1); color: #e5e7eb; }
    .stTextInput>div>div>input { background-color: #020617; color: #e5e7eb; }
    .stSelectbox>div>div>div { background-color: #020617; color: #e5e7eb; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 💠 CYBER DESK PRO")
    st.caption("Czat + Trading + Skaner · GPT-4.1 + Tavily + yfinance")
    _saved_settings = _load_settings()
    _saved_tickers = _load_user_tickers()

    mode = st.radio(
        "Tryb pracy:",
        [
            "🏠 Dashboard portfela",
            "🤖 Czat AI (internet + trading)",
            "📈 Kombajn tradingowy",
            "🧪 Skaner spółek (wpisz własne tickery)",
            "🔔 Alerty cenowe",
            "📊 Backtesting sygnałów",
        ],
    )
    st.divider()
    tg_enabled = st.checkbox("📲 Telegram – wysyłaj wyniki",
                             value=_saved_settings.get("telegram", True),
                             help="Wysyła sygnały BUY/SELL, skany i odpowiedzi AI na Telegram")
    st.caption("Token i chat ID z secrets.toml")
    st.session_state["telegram_enabled"] = tg_enabled
    if tg_enabled != _saved_settings.get("telegram", True):
        _s = _load_settings()
        _s["telegram"] = tg_enabled
        _save_settings(_s)

    st.divider()
    st.markdown("⏰ **Auto-skaner**")
    _auto_interval_options = [0, 15, 30, 60]
    _saved_auto_val = _saved_settings.get("auto_scan_interval", 0)
    _auto_index = _auto_interval_options.index(_saved_auto_val) if _saved_auto_val in _auto_interval_options else 0
    auto_interval = st.selectbox(
        "Skanuj co:",
        options=_auto_interval_options,
        format_func=lambda x: "Wyłączony" if x == 0 else f"Co {x} min",
        index=_auto_index,
        key="auto_interval"
    )
    st.caption("Automatycznie skanuje zapisane tickery")
    st.session_state["auto_scan_interval"] = auto_interval
    _s = _load_settings()
    _s["auto_scan_interval"] = auto_interval
    _save_settings(_s)

# ------------------ FUNKCJE POMOCNICZE ------------------
def detect_ticker_from_text(text: str):
    pattern = r"\b[A-Z0-9]{2,5}\.[A-Z]{2,3}\b|\b[A-Z]{1,5}\b"
    matches = re.findall(pattern, text)
    stop_words = {'I', 'A', 'THE', 'TO', 'FOR', 'OF', 'WITH', 'ON', 'AT', 'BY', 'IN', 'IS', 'IT', 'AS', 'OR', 'AND', 'BUT'}
    for m in matches:
        if m not in stop_words and len(m) >= 2:
            return m
    return None

def to_scalar(x):
    if isinstance(x, (pd.Series, np.ndarray, list)):
        if len(x) == 0:
            return np.nan
        try:
            return float(np.asarray(x).ravel()[-1])
        except Exception:
            return np.nan
    try:
        return float(x)
    except Exception:
        return np.nan

def fmt_price(price: float) -> str:
    """Formatuje cenę – dla groszówek więcej miejsc po przecinku."""
    if np.isnan(price) or price == 0:
        return "Brak"
    if price < 0.01:
        return f"{price:.6f}"
    elif price < 1:
        return f"{price:.4f}"
    elif price < 10:
        return f"{price:.3f}"
    else:
        return f"{price:.2f}"

def fmt_price_short(price: float) -> str:
    """Krótki format ceny dla metryk."""
    if np.isnan(price) or price == 0:
        return "Brak"
    if price < 0.01:
        return f"{price:.4f}"
    elif price < 1:
        return f"{price:.3f}"
    else:
        return f"{price:.2f}"

# ------------------ TELEGRAM ------------------
def send_telegram(message: str, parse_mode: str = "HTML"):
    """Wysyła wiadomość przez Telegram Bot API.
       Token i chat ID czyta z st.secrets – nie hardcoduje."""
    try:
        token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": parse_mode}
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False

# ------------------ WSKAŹNIKI TECHNICZNE ------------------
def compute_indicators(close, volume):
    close = close.copy()
    volume = volume.copy()
    if len(close) < 30:
        return {"rsi": np.nan, "ma_fast": np.nan, "ma_slow": np.nan,
                "upper_bb": pd.Series([np.nan]), "lower_bb": pd.Series([np.nan]),
                "last_upper_bb": np.nan, "last_lower_bb": np.nan,
                "macd": pd.Series([np.nan]), "macd_signal": pd.Series([np.nan]),
                "macd_hist": pd.Series([np.nan]),
                "last_macd": np.nan, "last_macd_signal": np.nan, "last_macd_hist": np.nan,
                "vol": np.nan, "volume": np.nan,
                "sl": np.nan, "tp": np.nan,
                "trend": "Unknown", "atr": np.nan, "adx": np.nan,
                "obv": np.nan, "vwap": np.nan, "roc": np.nan,
                "stoch_k": np.nan, "stoch_d": np.nan, "rvol": np.nan}

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi_series = 100 - (100 / (1 + rs)).dropna()
    last_rsi = to_scalar(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

    # MA
    ma_fast = close.rolling(10).mean()
    ma_slow = close.rolling(30).mean()
    last_ma_fast = to_scalar(ma_fast.iloc[-1]) if not ma_fast.dropna().empty else np.nan
    last_ma_slow = to_scalar(ma_slow.iloc[-1]) if not ma_slow.dropna().empty else np.nan

    # BB
    ma_bb = close.rolling(20).mean()
    std_bb = close.rolling(20).std()
    upper_bb = ma_bb + 2 * std_bb
    lower_bb = ma_bb - 2 * std_bb
    last_upper_bb = to_scalar(upper_bb.iloc[-1]) if not upper_bb.dropna().empty else np.nan
    last_lower_bb = to_scalar(lower_bb.iloc[-1]) if not lower_bb.dropna().empty else np.nan

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_series = ema12 - ema26
    macd_signal_series = macd_series.ewm(span=9, adjust=False).mean()
    macd_hist_series = macd_series - macd_signal_series
    last_macd = to_scalar(macd_series.iloc[-1]) if not macd_series.empty else np.nan
    last_macd_signal = to_scalar(macd_signal_series.iloc[-1]) if not macd_signal_series.empty else np.nan
    last_macd_hist = to_scalar(macd_hist_series.iloc[-1]) if not macd_hist_series.empty else np.nan

    # Volatility
    vol_series = close.pct_change().rolling(20).std().dropna()
    last_vol = to_scalar(vol_series.iloc[-1]) if not vol_series.empty else np.nan

    # Volume
    last_volume = to_scalar(volume.iloc[-1]) if not volume.empty else np.nan

    # ATR
    high = close.rolling(1).max()
    low = close.rolling(1).min()
    tr = pd.concat([(high - low).abs(),
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_series = tr.rolling(14).mean()
    last_atr = to_scalar(atr_series.iloc[-1]) if not atr_series.dropna().empty else np.nan

    # ADX (uproszczony)
    try:
        plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0.0)
        minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0.0)
        atr_adx = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_adx + 1e-9))
        minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_adx + 1e-9))
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
        adx_series = dx.rolling(14).mean()
        last_adx = to_scalar(adx_series.iloc[-1]) if not adx_series.dropna().empty else np.nan
    except:
        last_adx = np.nan

    # OBV
    try:
        obv = volume.where(close == close.shift(1), np.where(close > close.shift(1), volume, -volume)).cumsum()
        last_obv = to_scalar(obv.iloc[-1]) if not obv.empty else np.nan
    except:
        last_obv = np.nan

    # VWAP
    try:
        vwap_series = (close * volume).rolling(20).sum() / (volume.rolling(20).sum() + 1e-9)
        last_vwap = to_scalar(vwap_series.iloc[-1]) if not vwap_series.dropna().empty else np.nan
    except:
        last_vwap = np.nan

    # ROC
    try:
        roc_series = close.pct_change(10) * 100
        last_roc = to_scalar(roc_series.iloc[-1]) if not roc_series.dropna().empty else np.nan
    except:
        last_roc = np.nan

    # Stochastic
    try:
        low14 = close.rolling(14).min()
        high14 = close.rolling(14).max()
        stoch_k = (close - low14) / (high14 - low14 + 1e-9) * 100
        stoch_d = stoch_k.rolling(3).mean()
        last_stoch_k = to_scalar(stoch_k.iloc[-1]) if not stoch_k.dropna().empty else np.nan
        last_stoch_d = to_scalar(stoch_d.iloc[-1]) if not stoch_d.dropna().empty else np.nan
    except:
        last_stoch_k = np.nan
        last_stoch_d = np.nan

    # RVOL
    try:
        avg_vol_20 = volume.rolling(20).mean()
        rvol_series = volume / (avg_vol_20 + 1e-9)
        last_rvol = to_scalar(rvol_series.iloc[-1]) if not rvol_series.dropna().empty else np.nan
    except:
        last_rvol = np.nan

    # SL/TP
    sl_level = last_lower_bb if not np.isnan(last_lower_bb) else np.nan
    tp_level = last_upper_bb if not np.isnan(last_upper_bb) else np.nan

    # Trend
    if not np.isnan(last_ma_fast) and not np.isnan(last_ma_slow):
        if last_ma_fast > last_ma_slow * 1.01:
            trend = "Uptrend"
        elif last_ma_fast < last_ma_slow * 0.99:
            trend = "Downtrend"
        else:
            trend = "Sideways"
    else:
        trend = "Unknown"

    return {
        "rsi": last_rsi, "ma_fast": last_ma_fast, "ma_slow": last_ma_slow,
        "upper_bb": upper_bb, "lower_bb": lower_bb,
        "last_upper_bb": last_upper_bb, "last_lower_bb": last_lower_bb,
        "macd": macd_series, "macd_signal": macd_signal_series, "macd_hist": macd_hist_series,
        "last_macd": last_macd, "last_macd_signal": last_macd_signal, "last_macd_hist": last_macd_hist,
        "vol": last_vol, "volume": last_volume,
        "sl": sl_level, "tp": tp_level,
        "trend": trend,
        "atr": last_atr, "adx": last_adx,
        "obv": last_obv, "vwap": last_vwap, "roc": last_roc,
        "stoch_k": last_stoch_k, "stoch_d": last_stoch_d, "rvol": last_rvol,
    }

def compute_scoring_pro(ind, sentiment=None):
    score = 0
    if ind["trend"] == "Uptrend": score += 20
    elif ind["trend"] == "Sideways": score += 10

    adx = ind.get("adx", np.nan)
    if not np.isnan(adx):
        if adx > 40: score += 20
        elif adx > 25: score += 15
        elif adx > 20: score += 10

    rsi = ind.get("rsi", np.nan)
    if not np.isnan(rsi):
        if 30 <= rsi <= 50: score += 15
        elif rsi < 30: score += 10
        elif 50 < rsi <= 70: score += 5

    k, d = ind.get("stoch_k", np.nan), ind.get("stoch_d", np.nan)
    if not np.isnan(k) and not np.isnan(d):
        if k < 20 and d < 20: score += 10
        elif k > 80 and d > 80: score += 0
        else: score += 5

    rvol = ind.get("rvol", np.nan)
    if not np.isnan(rvol):
        if rvol > 1.5: score += 15
        elif rvol > 1.0: score += 10
        elif rvol > 0.7: score += 5

    if not np.isnan(ind.get("last_macd", np.nan)) and not np.isnan(ind.get("last_macd_signal", np.nan)):
        if ind["last_macd"] > ind["last_macd_signal"]: score += 10

    if not np.isnan(ind.get("last_lower_bb", np.nan)): score += 5
    if not np.isnan(ind.get("last_upper_bb", np.nan)): score += 5

    if not np.isnan(ind.get("atr", np.nan)): score += 5

    if sentiment == "Bullish": score += 10
    elif sentiment == "Bearish": score -= 10

    return max(0, min(score, 100))

def generate_signal(price, ind):
    rsi, ma_fast, ma_slow, trend = ind["rsi"], ind["ma_fast"], ind["ma_slow"], ind["trend"]
    adx, rvol, stoch_k, stoch_d = ind.get("adx", np.nan), ind.get("rvol", np.nan), ind.get("stoch_k", np.nan), ind.get("stoch_d", np.nan)
    sl, tp = ind["sl"], ind["tp"]

    if any(np.isnan(x) for x in [rsi, ma_fast, ma_slow]):
        return "HOLD", "Za mało danych."

    reasons = []
    signal = "HOLD"

    if trend == "Uptrend": reasons.append("📈 Trend wzrostowy (MA10 > MA30)")
    elif trend == "Downtrend": reasons.append("📉 Trend spadkowy (MA10 < MA30)")
    else: reasons.append("➡️ Trend boczny")

    if not np.isnan(adx):
        if adx < 20: reasons.append(f"🔹 ADX {adx:.1f} → słaby trend")
        elif adx < 40: reasons.append(f"🔸 ADX {adx:.1f} → umiarkowany")
        else: reasons.append(f"🔺 ADX {adx:.1f} → silny")

    if rsi < 30: reasons.append(f"📊 RSI {rsi:.1f} → wyprzedanie")
    elif rsi > 70: reasons.append(f"📊 RSI {rsi:.1f} → wykupienie")
    else: reasons.append(f"📊 RSI {rsi:.1f} → neutralny")

    if not np.isnan(stoch_k) and not np.isnan(stoch_d):
        if stoch_k < 20 and stoch_d < 20: reasons.append(f"🔻 Stochastic → wyprzedanie")
        elif stoch_k > 80 and stoch_d > 80: reasons.append(f"🔺 Stochastic → wykupienie")

    if not np.isnan(rvol):
        if rvol > 1.5: reasons.append(f"📊 RVOL {rvol:.2f} → wysoki wolumen")
        elif rvol < 0.7: reasons.append(f"📊 RVOL {rvol:.2f} → niski wolumen")

    if trend == "Uptrend" and rsi < 40:
        signal = "BUY"
        reasons.append("✅ Sygnał BUY: trend wzrostowy + RSI < 40")
    elif trend == "Downtrend" and rsi > 60:
        signal = "SELL"
        reasons.append("⛔ Sygnał SELL: trend spadkowy + RSI > 60")
    elif trend == "Uptrend" and 30 < rsi < 50:
        signal = "BUY"
        reasons.append("✅ Sygnał BUY: trend wzrostowy + RSI w strefie akumulacji")
    elif trend == "Downtrend" and rsi < 30:
        signal = "BUY"
        reasons.append("✅ Sygnał BUY: wyprzedanie w trendzie spadkowym")
    else:
        signal = "HOLD"
        reasons.append("⏸️ HOLD: brak jednoznacznego sygnału")

    if not np.isnan(sl): reasons.append(f"🛑 SL: {sl:.2f}")
    if not np.isnan(tp): reasons.append(f"🎯 TP: {tp:.2f}")

    return signal, "\n".join(f"- {r}" for r in reasons)

def fetch_news_sentiment(ticker):
    try:
        t = yf.Ticker(ticker)
        news = t.news if hasattr(t, "news") else []
    except:
        news = []
    titles = [n.get("title", "") for n in news if isinstance(n.get("title", ""), str)][:5]
    if not titles:
        return "Mixed", [], "Brak newsów."
    score = 0
    pos = ["beat","strong","growth","upgrade","profit","record","surge","rally","positive"]
    neg = ["miss","weak","downgrade","fall","loss","cut","crash","negative","concern"]
    for title in titles:
        tl = title.lower()
        if any(w in tl for w in pos): score += 1
        if any(w in tl for w in neg): score -= 1
    sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"
    return sentiment, titles, ""

# ------------------ KLASYFIKACJA TYPÓW RUCHU ------------------
def classify_movement(close: pd.Series, price: float, ind: dict) -> tuple:
    """Rozpoznaje typ ruchu cenowego (breakout, pullback, konsolidacja itd.).
    Zwraca (etykieta_z_emoją, opis, ranking_wagowy)."""
    trend = ind.get("trend", "Unknown")
    adx = ind.get("adx", np.nan)
    rvol = ind.get("rvol", np.nan)
    roc = ind.get("roc", np.nan)
    rsi = ind.get("rsi", np.nan)
    obv = ind.get("obv", np.nan)
    last_upper = ind.get("last_upper_bb", np.nan)
    last_lower = ind.get("last_lower_bb", np.nan)
    ma_fast = ind.get("ma_fast", np.nan)
    ma_slow = ind.get("ma_slow", np.nan)
    vol = ind.get("vol", np.nan)

    has_all = not any(np.isnan(x) for x in [price, ma_fast, ma_slow])
    candidates = []

    # --- Gwałtowny ruch (Pump / Dump) ---
    if not np.isnan(roc) and not np.isnan(rvol):
        if roc > 4 and rvol > 2.0:
            candidates.append(("⚡ Gwałtowny wzrost (pump)", 40))
        elif roc < -4 and rvol > 2.0:
            candidates.append(("⚡ Gwałtowny spadek (dump)", 40))

    # --- Breakout / Breakdown ---
    if has_all and not np.isnan(last_upper) and not np.isnan(last_lower):
        if price > last_upper and trend == "Uptrend" and not np.isnan(rvol) and rvol > 1.3:
            candidates.append(("🚀 Breakout (przebicie górnego BB)", 50))
        elif price < last_lower and trend == "Downtrend" and not np.isnan(rvol) and rvol > 1.3:
            candidates.append(("💥 Breakdown (przebicie dolnego BB)", 50))

    # --- Reversal warning (dywergencja RSI) ---
    if len(close) >= 10 and not np.isnan(rsi):
        try:
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            rsi_vals = 100 - (100 / (1 + rs))
            last5_rsi = rsi_vals.iloc[-5:]
            last5_price = close.iloc[-5:]
            if not last5_rsi.dropna().empty and not last5_price.dropna().empty:
                if (last5_price.iloc[-1] > last5_price.max() - 1e-9 and
                    last5_rsi.iloc[-1] < last5_rsi.max() - 1e-9 and
                    last5_rsi.iloc[-1] < last5_rsi.iloc[0]):
                    candidates.append(("⚠️ Reversal (dywergencja RSI – niedźwiedzia)", 30))
                if (last5_price.iloc[-1] < last5_price.min() + 1e-9 and
                    last5_rsi.iloc[-1] > last5_rsi.min() + 1e-9 and
                    last5_rsi.iloc[-1] > last5_rsi.iloc[0]):
                    candidates.append(("⚠️ Reversal (dywergencja RSI – bycza)", 30))
        except Exception:
            pass

    # --- Kontynuacja trendu ---
    if has_all and not np.isnan(adx) and adx > 22:
        if trend == "Uptrend" and price > ma_fast:
            candidates.append(("📈 Kontynuacja wzrostu", 25))
        elif trend == "Downtrend" and price < ma_fast:
            candidates.append(("📉 Kontynuacja spadku", 25))

    # --- Pullback ---
    if has_all and not np.isnan(adx) and adx > 22:
        if trend == "Uptrend" and ma_slow < price < ma_fast * 1.02:
            candidates.append(("🔄 Pullback (cofnięcie do MA w trendzie wzrostowym)", 20))
        elif trend == "Downtrend" and ma_fast * 0.98 < price < ma_slow:
            candidates.append(("🔄 Pullback (cofnięcie do MA w trendzie spadkowym)", 20))

    # --- Konsolidacja ---
    if trend == "Sideways" or (not np.isnan(adx) and adx < 18):
        if not np.isnan(vol) and vol < 0.015:
            candidates.append(("⏸️ Konsolidacja / brak kierunku", 10))

    # --- Domyślny ---
    if not has_all:
        candidates.append(("❓ Nieznany (brak danych)", 0))
    elif not candidates:
        if trend == "Uptrend":
            candidates.append(("📈 Ruch wzrostowy (bez sygnału specjalnego)", 15))
        elif trend == "Downtrend":
            candidates.append(("📉 Ruch spadkowy (bez sygnału specjalnego)", 15))
        else:
            candidates.append(("➡️ Ruch boczny (bez sygnału specjalnego)", 5))

    candidates.sort(key=lambda x: -x[1])
    best_label, best_weight = candidates[0]
    short_desc = best_label.split("(")[0].strip() if "(" in best_label else best_label
    return best_label, short_desc, best_weight

# ------------------ DASHBOARD PORFELA ------------------
def render_dashboard():
    st.title("🏠 Dashboard portfela")
    portfolio = _load_portfolio()
    last_scan = _load_last_scan()
    user_tickers = _load_user_tickers()

    # --- Sekcja zarządzania portfelem ---
    with st.expander("💼 **Mój portfel – dodaj/edytuj akcje**", expanded=True):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        new_ticker = col1.text_input("Ticker", placeholder="np. STX.WA", key="pf_ticker", label_visibility="collapsed")
        new_shares = col2.number_input("Liczba akcji", min_value=0.0, step=1.0, format="%g", key="pf_shares", label_visibility="collapsed")
        new_price = col3.number_input("Średnia cena zakupu", min_value=0.0, step=0.01, format="%f", key="pf_price", label_visibility="collapsed")
        if col4.button("➕ Dodaj", use_container_width=True):
            if new_ticker and new_shares > 0 and new_price > 0:
                t = new_ticker.strip().upper()
                found = False
                for item in portfolio:
                    if item["ticker"] == t:
                        item["shares"] += new_shares
                        item["avg_price"] = new_price
                        found = True
                        break
                if not found:
                    portfolio.append({"ticker": t, "shares": new_shares, "avg_price": new_price})
                _save_portfolio(portfolio)
                st.rerun()

    # --- Tabela portfela ---
        if portfolio:
            st.divider()
            st.markdown("**📋 Twoje pozycje:**")
            cols_tab = st.columns([3, 2, 2, 2, 2, 2, 1])
            cols_tab[0].markdown("**Spółka**")
            cols_tab[1].markdown("**Akcje**")
            cols_tab[2].markdown("**Śr. cena**")
            cols_tab[3].markdown("**Kurs**")
            cols_tab[4].markdown("**Wartość**")
            cols_tab[5].markdown("**Zysk/Strata**")
            cols_tab[6].markdown("")

            total_value = 0
            total_cost = 0
            for item in portfolio[:25]:
                t = item["ticker"]; shares = item["shares"]; avg_price = item["avg_price"]
                price_live = None; change_pct = 0
                try:
                    d = yf.download(t, period="5d", interval="1d", progress=False)
                    if not d.empty:
                        c = d["Close"].iloc[:, 0] if isinstance(d.columns, pd.MultiIndex) else d["Close"]
                        price_live = to_scalar(c.iloc[-1])
                        if len(c) > 1:
                            change_pct = (price_live - to_scalar(c.iloc[-2])) / (to_scalar(c.iloc[-2]) + 1e-9) * 100
                except: pass
                if price_live is None or np.isnan(price_live): price_live = avg_price
                cur_val = price_live * shares
                cost_val = avg_price * shares
                pnl = cur_val - cost_val
                pnl_pct = (pnl / cost_val) * 100 if cost_val > 0 else 0
                total_value += cur_val; total_cost += cost_val
                pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
                cols_tab[0].write("**" + t + "**")
                cols_tab[1].write(str(int(shares) if shares == int(shares) else f"{shares:.1f}"))
                cols_tab[2].write(fmt_price_short(avg_price))
                cols_tab[3].write(fmt_price_short(price_live) + (" <span style='color:#22c55e'>▲</span>" if change_pct > 0 else " <span style='color:#ef4444'>▼</span>" if change_pct < 0 else ""), unsafe_allow_html=True)
                cols_tab[4].write(fmt_price_short(cur_val))
                cols_tab[5].write(f"<span style='color:{pnl_color}'>{'📈' if pnl >= 0 else '📉'} {fmt_price_short(abs(pnl))} ({pnl_pct:+.1f}%)</span>", unsafe_allow_html=True)
                if cols_tab[6].button("🗑️", key="del_" + t):
                    portfolio = [p for p in portfolio if p["ticker"] != t]
                    _save_portfolio(portfolio)
                    st.rerun()

            st.divider()
            total_pnl = total_value - total_cost
            tpc = "#22c55e" if total_pnl >= 0 else "#ef4444"
            st.markdown(f"""
            <div style="background:#1e293b; padding:14px; border-radius:10px; border:1px solid #334155;">
                <b>💰 Podsumowanie</b><br>
                Wartość: <b>{fmt_price_short(total_value)}</b> •
                Koszt: <b>{fmt_price_short(total_cost)}</b> •
                <span style="color:{tpc};font-size:17px;">{total_pnl:+.2f} ({total_pnl/total_cost*100:+.1f}%)</span>
            </div>
            """, unsafe_allow_html=True)

    # --- Obserwowane ---
    if user_tickers:
        st.divider()
        st.markdown("**👀 Obserwowane (" + str(len(user_tickers)) + " spółek):**")
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=60 * 1000, key="dash_refresh")
        ch = st.columns([2, 1, 1, 1, 1, 1])
        ch[0].markdown("**Ticker**"); ch[1].markdown("**Cena**"); ch[2].markdown("**Zmiana**"); ch[3].markdown("**Score**"); ch[4].markdown("**Trend**"); ch[5].markdown("**Ruch**")
        for t in user_tickers:
            c = last_scan.get(t, {}); pl = None; cp = 0
            try:
                d = yf.download(t, period="5d", interval="1d", progress=False)
                if not d.empty:
                    cl = d["Close"].iloc[:, 0] if isinstance(d.columns, pd.MultiIndex) else d["Close"]
                    pl = to_scalar(cl.iloc[-1])
                    if len(cl) > 1: cp = (pl - to_scalar(cl.iloc[-2])) / (to_scalar(cl.iloc[-2]) + 1e-9) * 100
            except: pass
            if pl is None or np.isnan(pl): pl = c.get("price", None); cp = 0
            ps = fmt_price_short(pl) if pl is not None and not np.isnan(pl) else "?"
            cs = f"{cp:+.2f}%" if cp != 0 else "0.00%"
            cc = "#22c55e" if cp > 0 else "#ef4444" if cp < 0 else "#888"
            sc = c.get("scoring"); tr = c.get("trend", "?"); ru = c.get("ruch", "?")
            bg = "🟢" if sc is not None and sc >= 70 else "🟡" if sc is not None and sc >= 40 else "🔴"
            cr = st.columns([2, 1, 1, 1, 1, 1])
            cr[0].write("**" + bg + " " + t + "**")
            cr[1].write(ps)
            cr[2].write(f"<span style='color:{cc}'>{cs}</span>", unsafe_allow_html=True)
            cr[3].write(f"{sc if sc is not None else '?'}/100")
            cr[4].write(tr); cr[5].write(ru)

        if last_scan:
            st.divider()
            st.markdown("**📋 Podsumowanie dla Telegram:**")
            tg = [f"<b>🏠 Dashboard – {len(user_tickers)} spółek</b>"]
            for t in user_tickers:
                d = last_scan.get(t, {}); p = d.get("price", "?")
                tg.append(f"• {t} – {fmt_price(p) if p != '?' else '?'} | {d.get('scoring','?')}/100 | {d.get('trend','?')} | {d.get('ruch','?')}")
            st.code("\n".join(tg), language="text")
    elif not portfolio:
        st.info("📌 Dodaj spółki do portfela powyżej lub zapisz tickery w skanerze.")

# ------------------ MODUŁ: TRADING ------------------
def render_trading():
    st.title("📈 Kombajn tradingowy – pełny panel")
    ticker = st.text_input("Ticker (np. AAPL, MSFT, STX.WA):", "",
                           placeholder="Wpisz ticker, np. STX.WA")
    col1, col2 = st.columns(2)
    period = col1.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
    interval = col2.selectbox("Interwał:", ["15m", "30m", "1h", "1d"], index=3)

    if st.button("Pobierz dane i policz sygnały", use_container_width=True):
        try:
            with st.spinner(f"Pobieram dane dla {ticker}..."):
                data = yf.download(ticker, period=period, interval=interval, progress=False)
                if data.empty:
                    st.error("Brak danych.")
                    return
                if len(data) < 60:
                    st.info("Za mało danych, używam 6mo/1d")
                    data = yf.download(ticker, period="6mo", interval="1d", progress=False)
                    if data.empty:
                        st.error("Brak danych.")
                        return

                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"].iloc[:, 0]
                    open_ = data["Open"].iloc[:, 0]
                    high = data["High"].iloc[:, 0]
                    low = data["Low"].iloc[:, 0]
                    volume = data["Volume"].iloc[:, 0]
                else:
                    close, open_, high, low, volume = data["Close"], data["Open"], data["High"], data["Low"], data["Volume"]

                ind = compute_indicators(close, volume)
                price = to_scalar(close.iloc[-1])

                # Wykres
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=data.index, open=open_, high=high, low=low, close=close, name="Świece"))
                if not ind["upper_bb"].isna().all():
                    fig.add_trace(go.Scatter(x=data.index, y=ind["upper_bb"], line=dict(color="rgba(34,197,94,0.5)", width=1), name="BB górna"))
                    fig.add_trace(go.Scatter(x=data.index, y=ind["lower_bb"], line=dict(color="rgba(239,68,68,0.5)", width=1), name="BB dolna"))
                fig.update_layout(height=500, title=f"{ticker} - {period} ({interval})", paper_bgcolor="#020617", plot_bgcolor="#020617", font=dict(color="#E5E7EB"))
                st.plotly_chart(fig, use_container_width=True)

                sentiment, titles, _ = fetch_news_sentiment(ticker)
                signal, explanation = generate_signal(price, ind)
                scoring = compute_scoring_pro(ind, sentiment)
                movement_label, movement_short, movement_weight = classify_movement(close, price, ind)

                st.subheader("🤖 Analiza")
                c1, c2 = st.columns(2)
                c1.metric("Cena", fmt_price_short(price))
                c1.metric("RSI", f"{ind['rsi']:.1f}" if not np.isnan(ind['rsi']) else "Brak")
                c1.metric("Trend", ind['trend'])
                c1.metric("Sygnał", signal)
                c2.metric("Scoring", f"{scoring}/100")
                c2.metric("ADX", f"{ind['adx']:.1f}" if not np.isnan(ind['adx']) else "Brak")
                c2.metric("RVOL", f"{ind['rvol']:.2f}" if not np.isnan(ind['rvol']) else "Brak")
                c2.metric("Sentyment", sentiment)

                st.info(f"🧠 **Typ ruchu:** {movement_label} (waga: {movement_weight}/50)")

                with st.expander("📊 Wszystkie wskaźniki"):
                    for k, v in ind.items():
                        if isinstance(v, pd.Series):
                            continue
                        try:
                            if not np.isnan(v):
                                val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
                                st.write(f"**{k}:** {val_str}")
                        except TypeError:
                            st.write(f"**{k}:** {v}")

                st.markdown("**Uzasadnienie:**")
                st.markdown(explanation)
                st.subheader("📰 News")
                st.write(f"Sentyment: {sentiment}")
                for t in titles:
                    st.write(f"- {t}")

                st.session_state["last_analysis"] = {
                    "ticker": ticker, "price": price, "indicators": ind,
                    "signal": signal, "explanation": explanation,
                    "sentiment": sentiment, "news_titles": titles,
                    "scoring": scoring, "period": period, "interval": interval,
                    "movement_label": movement_label, "movement_short": movement_short
                }
                st.success("✅ Analiza zapisana.")

                if st.session_state.get("telegram_enabled", True) and signal in ("BUY", "SELL"):
                    tg_msg = (
                        f"🚀 <b>{ticker}</b> – sygnał: <b>{signal}</b>\n"
                        f"{movement_label}\n"
                        f"💰 Cena: {fmt_price(price)} | Scoring: {scoring}/100\n"
                        f"📈 Trend: {ind['trend']} | RSI: {ind['rsi']:.1f}\n"
                        f"📊 ADX: {ind['adx']:.1f} | RVOL: {ind['rvol']:.2f}\n"
                        f"📰 Sentyment: {sentiment}\n"
                        f"📅 {period} ({interval})"
                    )
                    if send_telegram(tg_msg):
                        st.toast("📲 Telegram wysłany", icon="✅")
                    else:
                        st.toast("📲 Telegram: brak tokena lub błąd", icon="⚠️")
        except Exception as e:
            st.error(f"❌ Błąd: {str(e)}")

# ------------------ MODUŁ: SKANER ------------------
def render_scanner():
    st.title("🧪 Skaner spółek – własne tickery → TOP N")

    # --- Auto-refresh ---
    auto_interval = st.session_state.get("auto_scan_interval", 0)
    is_auto_scan = False
    if auto_interval > 0:
        # odśwież stronę co N minut (st_autorefresh w ms)
        st_autorefresh(interval=auto_interval * 60 * 1000, key="autoscan")
        # sprawdź czy to auto-odświeżenie (brak kliknięcia przycisku)
        last_auto = st.session_state.get("last_auto_scan_time", 0)
        now = time.time()
        if now - last_auto > auto_interval * 60 - 5 and st.session_state.get("auto_scan_trigger", False):
            is_auto_scan = True
        st.session_state["auto_scan_trigger"] = True

    _saved_tickers_list = _load_user_tickers()
    _default_tickers_str = " ".join(_saved_tickers_list)
    tickers_text = st.text_area("Tickery (oddzielone spacją, przecinkiem lub nową linią):",
                                _default_tickers_str, height=120,
                                placeholder="Wpisz tickery, np. STX.WA, ACP.WA, TUP.WA")
    max_to_show = st.slider("TOP N:", 5, 20, 10)

    if is_auto_scan and _saved_tickers_list:
        st.info(f"⏰ Auto-skaner aktywny (co {auto_interval} min) – automatycznie skanuję: {' '.join(_saved_tickers_list[:8])}" +
                ("..." if len(_saved_tickers_list) > 8 else ""))

    # --- Decyzja: czy uruchomić skanowanie ---
    _should_scan = False
    _auto_mode = False
    if st.button("🔍 Skanuj", use_container_width=True):
        _should_scan = True
    elif is_auto_scan and _saved_tickers_list:
        # auto-skan: użyj zapisanych tickerów
        _should_scan = True
        _auto_mode = True
        tickers_text = _default_tickers_str

    if _should_scan:
        raw = re.split(r'[,\s\n]+', tickers_text)
        tickers = list(dict.fromkeys([t.strip().upper() for t in raw if t.strip()]))
        if not tickers:
            st.error("Brak tickerów.")
            if not _auto_mode:
                return

        results = []
        progress_bar = st.progress(0) if not _auto_mode else st.empty()
        status = st.empty()
        for i, ticker in enumerate(tickers):
            if not _auto_mode:
                status.text(f"Skanuję: {ticker} ({i+1}/{len(tickers)})")
                progress_bar.progress((i+1)/len(tickers))
            try:
                data = yf.download(ticker, period="6mo", interval="1d", progress=False)
                if data.empty or len(data) < 30:
                    continue
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"].iloc[:, 0]
                    volume = data["Volume"].iloc[:, 0]
                else:
                    close, volume = data["Close"], data["Volume"]
                ind = compute_indicators(close, volume)
                price = to_scalar(close.iloc[-1])
                sentiment, _, _ = fetch_news_sentiment(ticker)
                scoring = compute_scoring_pro(ind, sentiment)
                _, movement_short, _ = classify_movement(close, price, ind)
                results.append({
                    "Ticker": ticker, "Cena": price, "Trend": ind["trend"],
                    "RSI": ind["rsi"], "ADX": ind["adx"], "RVOL": ind["rvol"],
                    "Sentyment": sentiment, "Scoring": scoring,
                    "Ruch": movement_short
                })
            except:
                continue
        if not _auto_mode:
            progress_bar.empty()
        status.empty()

        # --- Zapisz tickery do state.json ---
        _save_user_tickers(tickers)

        # --- Sprawdź alerty cenowe ---
        try:
            alert_price_data = {}
            for r in results:
                alert_price_data[r["Ticker"]] = {"price": r["Cena"]}
            check_alerts(results, alert_price_data)
        except Exception:
            pass

        if not results:
            st.error("Brak wyników.")
            return

        df = pd.DataFrame(results).sort_values("Scoring", ascending=False).head(max_to_show)
        st.subheader(f"🏆 TOP {len(df)} spółek")

        for _, row in df.iterrows():
            score = row["Scoring"]
            if score >= 70:
                color, border, label = "rgba(34,197,94,0.25)", "2px solid #22c55e", "🔥 Mocny sygnał"
            elif score >= 40:
                color, border, label = "rgba(251,146,60,0.25)", "2px solid #fb923c", "📊 Obserwacja"
            else:
                color, border, label = "rgba(239,68,68,0.25)", "2px solid #ef4444", "⚠️ Słaby sygnał"
            st.markdown(f"""
            <div style="background-color:{color}; padding:15px; border-radius:10px; margin-bottom:10px; border:{border};">
                <b style="font-size:18px;">{row['Ticker']}</b><br>
                Cena: {fmt_price(row['Cena'])} | Trend: {row['Trend']} | RSI: {row['RSI']:.1f}<br>
                ADX: {row['ADX']:.1f} | RVOL: {row['RVOL']:.2f} | Sentyment: {row['Sentyment']}<br>
                🧠 Ruch: {row['Ruch']}<br>
                <b>Scoring: {score}/100</b> — {label}
            </div>
            """, unsafe_allow_html=True)

        if st.button("💾 Zapisz CSV"):
            st.download_button("Pobierz", df.to_csv(index=False), "skaner.csv", "text/csv")

        # --- Telegram z detekcją zmian ---
        if st.session_state.get("telegram_enabled", True):
            last_scan = _load_last_scan()
            changes = []
            for _, r in df.iterrows():
                ticker = r["Ticker"]
                price_now = float(r["Cena"])
                vol_now = float(r["RVOL"])
                old = last_scan.get(ticker, {})
                old_price = old.get("price", None)
                old_vol = old.get("rvol", None)
                # porównaj z pewnym progiem (0.5% zmiany ceny lub 10% zmiany RVOL)
                price_changed = old_price is None or (
                    old_price != 0 and abs(price_now - old_price) / max(abs(old_price), 0.0001) > 0.005
                )
                vol_changed = old_vol is None or (
                    old_vol != 0 and abs(vol_now - old_vol) / max(abs(vol_now), 0.0001) > 0.10
                )
                if price_changed or vol_changed:
                    changes.append(ticker)

            if changes:
                top3 = df.head(3)
                tg_lines = [f"<b>📊 SKANER – TOP {len(df)} spółek (zmiana: {', '.join(changes[:5])})</b>"]
                for _, r in top3.iterrows():
                    tg_lines.append(
                        f"• {r['Ticker']} – {fmt_price(r['Cena'])} | {r['Scoring']}/100 | {r['Trend']} | {r['Ruch']}"
                    )
                tg_lines.append(f"📅 Pełna lista: {len(df)} spółek")
                if send_telegram("\n".join(tg_lines)):
                    st.toast("📲 Telegram wysłany (wykryto zmiany)", icon="✅")
            else:
                st.toast("📲 Telegram: brak zmian – pominięto", icon="ℹ️")

            # Zapisz bieżące wyniki jako last_scan
            scan_data = {}
            for _, r in df.iterrows():
                scan_data[r["Ticker"]] = {
                    "price": float(r["Cena"]),
                    "rvol": float(r["RVOL"]),
                    "scoring": int(r["Scoring"]),
                    "trend": str(r["Trend"]),
                    "ruch": str(r["Ruch"]),
                    "rsi": float(r["RSI"]) if not np.isnan(r["RSI"]) else None
                }
            _save_last_scan(scan_data)

        # --- Aktualizuj znacznik czasu auto-skanu ---
        if not _auto_mode:
            st.session_state["last_auto_scan_time"] = time.time()
            st.session_state["auto_scan_trigger"] = False
        else:
            st.session_state["last_auto_scan_time"] = time.time()
            st.rerun()  # wymuś odświeżenie by zaktualizować widok

# ------------------ ALERTY CENOWE ------------------
def check_alerts(tickers_data: list, price_data: dict):
    """Sprawdza alerty i wysyła Telegram dla trafionych."""
    alerts = _load_alerts()
    if not alerts:
        return
    triggered = []
    for t in alerts:
        a = alerts[t]
        target_type = a.get("type", "BUY")
        target_price = a.get("price", 0)
        active = a.get("active", True)
        if not active:
            continue
        price_now = price_data.get(t, {}).get("price", None)
        if price_now is None or np.isnan(price_now):
            continue
        hit = False
        if target_type == "BUY_TARGET" and price_now <= target_price:
            hit = True
        elif target_type == "SELL_TARGET" and price_now >= target_price:
            hit = True
        elif target_type == "STOP_LOSS" and price_now <= target_price:
            hit = True
        if hit:
            triggered.append((t, target_type, target_price, price_now))
            alerts[t]["active"] = False  # deaktywuj po trafieniu
    if triggered:
        _save_alerts(alerts)
        lines = [f"<b>🔔 ALERTY – trafione:</b>"]
        for t, typ, tp, pn in triggered:
            emoji = "🟢" if "BUY" in typ else ("🔴" if "STOP" in typ else "🟡")
            lines.append(f"{emoji} {t}: {typ} @ {fmt_price(tp)} → teraz {fmt_price(pn)}")
        msg = "\n".join(lines)
        if st.session_state.get("telegram_enabled", True):
            send_telegram(msg)

def render_alerts():
    st.title("🔔 Alerty cenowe")
    st.caption("Ustaw cele cenowe – gdy cena osiągnie target, dostaniesz powiadomienie Telegram")
    tickers = _load_user_tickers()
    if not tickers:
        st.info("📌 Najpierw dodaj tickery w skanerze.")
        return

    alerts = _load_alerts()
    col_ticker, col_type, col_price, col_btn = st.columns([2, 2, 2, 1])
    ticker_sel = col_ticker.selectbox("Spółka", tickers, key="alert_ticker")
    type_sel = col_type.selectbox("Typ", ["BUY_TARGET", "SELL_TARGET", "STOP_LOSS"], key="alert_type")
    price_inp = col_price.number_input("Cena docelowa", min_value=0.0, step=0.01, format="%f", key="alert_price")
    if col_btn.button("➕ Dodaj", use_container_width=True):
        if ticker_sel and price_inp > 0:
            alerts[ticker_sel] = {"type": type_sel, "price": price_inp, "active": True}
            _save_alerts(alerts)
            st.toast(f"✅ Alert {type_sel} dla {ticker_sel} @ {fmt_price(price_inp)}", icon="🔔")

    st.divider()
    st.markdown("**Aktywne alerty:**")
    if not alerts:
        st.info("Brak alertów. Dodaj nowy powyżej.")
    else:
        to_delete = []
        for t, a in alerts.items():
            active = a.get("active", True)
            typ = a.get("type", "?")
            price = a.get("price", 0)
            if not active:
                continue
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
            c1.write(f"**{t}**")
            c2.write(typ)
            c3.write(fmt_price(price))
            if c4.button("🗑️", key=f"del_{t}_{typ}_{price}"):
                to_delete.append(t)
        for t in to_delete:
            if t in alerts:
                del alerts[t]
                _save_alerts(alerts)
                st.rerun()

    st.divider()
    st.markdown("**Historia trafionych alertów:**")
    hit_any = False
    for t, a in alerts.items():
        if not a.get("active", True):
            hit_any = True
            typ = a.get("type", "?")
            price = a.get("price", 0)
            st.write(f"✅ {t} – {typ} @ {fmt_price(price)} (trafiony)")
    if not hit_any:
        st.caption("Brak trafionych alertów.")

# ------------------ BACKTESTING SYGNAŁÓW ------------------
def render_backtest():
    st.title("📊 Backtesting sygnałów")
    st.caption("Sprawdź, jak nasze sygnały sprawdziłyby się na historycznych danych")

    tickers = _load_user_tickers()
    if not tickers:
        st.info("📌 Najpierw dodaj tickery w skanerze.")
        return

    period_map = {"3 miesiące": "3mo", "6 miesięcy": "6mo", "1 rok": "1y"}
    period_sel = st.selectbox("Okres testu:", list(period_map.keys()), index=1)
    period = period_map[period_sel]

    if st.button("🔍 Uruchom backtest", use_container_width=True):
        results = []
        progress_bar = st.progress(0)
        status = st.empty()

        for i, ticker in enumerate(tickers):
            status.text(f"Testuję: {ticker} ({i+1}/{len(tickers)})")
            progress_bar.progress((i + 1) / len(tickers))

            try:
                data = yf.download(ticker, period=period, interval="1d", progress=False)
                if data.empty or len(data) < 30:
                    continue
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"].iloc[:, 0]
                else:
                    close = data["Close"]

                # Symulacja sygnałów na historycznych danych
                # Dzielimy dane na segmenty co 10 dni
                window = 30
                buy_hold_start = to_scalar(close.iloc[0])
                buy_hold_end = to_scalar(close.iloc[-1])
                buy_hold_return = (buy_hold_end - buy_hold_start) / (buy_hold_start + 1e-9) * 100

                signal_trades = []
                for start_idx in range(0, len(close) - window, window):
                    seg = close.iloc[start_idx:start_idx + window]
                    if len(seg) < window:
                        continue
                    price_now_sim = to_scalar(seg.iloc[-1])
                    # Oblicz wskaźniki dla tego okna
                    vol_seg = volume.iloc[start_idx:start_idx + window] if not isinstance(data.columns, pd.MultiIndex) else data["Volume"].iloc[:, 0].iloc[start_idx:start_idx + window]
                    ind_sim = compute_indicators(seg, vol_seg)
                    sig_sim, _ = generate_signal(price_now_sim, ind_sim)
                    if sig_sim == "BUY":
                        # kup na początku następnego okna, sprzedaj na końcu
                        next_start = start_idx + window
                        next_end = min(next_start + window, len(close))
                        if next_end > next_start:
                            buy_p = to_scalar(close.iloc[next_start])
                            sell_p = to_scalar(close.iloc[next_end - 1])
                            ret = (sell_p - buy_p) / (buy_p + 1e-9) * 100
                            signal_trades.append(ret)

                if signal_trades:
                    avg_trade = sum(signal_trades) / len(signal_trades)
                    total_trades = len(signal_trades)
                    win_rate = sum(1 for r in signal_trades if r > 0) / total_trades * 100
                else:
                    avg_trade = 0
                    total_trades = 0
                    win_rate = 0

                results.append({
                    "Ticker": ticker,
                    "BH_Return": buy_hold_return,
                    "Signal_Return": avg_trade * max(1, total_trades // 2),  # approx cumulative
                    "Avg_Trade%": avg_trade,
                    "Win_Rate%": win_rate,
                    "Total_Trades": total_trades,
                    "BH_vs_Signal": avg_trade * max(1, total_trades // 2) - buy_hold_return
                })
            except:
                continue

        progress_bar.empty()
        status.empty()

        if not results:
            st.error("Brak wyników.")
            return

        df = pd.DataFrame(results)
        df = df.sort_values("Avg_Trade%", ascending=False)

        st.subheader(f"📊 Wyniki backtestu ({period_sel})")

        for _, r in df.iterrows():
            color = "rgba(34,197,94,0.2)" if r["Avg_Trade%"] > 0 else "rgba(239,68,68,0.2)"
            border = "2px solid #22c55e" if r["Avg_Trade%"] > 0 else "2px solid #ef4444"
            st.markdown(f"""
            <div style="background:{color}; padding:12px; border-radius:10px; margin-bottom:8px; border:{border};">
                <b style="font-size:16px;">{r['Ticker']}</b><br>
                📈 Kup i trzymaj: <b>{r['BH_Return']:+.2f}%</b><br>
                🎯 Sygnały: <b>{r['Avg_Trade%']:+.2f}% średnio</b> ({"+" if r["Avg_Trade%"] > 0 else ""}{r['Avg_Trade%']:.2f}%)<br>
                ✅ Win rate: {r['Win_Rate%']:.0f}% | Liczba transakcji: {r['Total_Trades']}<br>
                <span style="color:{"#22c55e" if r["BH_vs_Signal"] > 0 else "#ef4444"}">
                📊 Sygnały vs Kup-Trzymaj: <b>{r['BH_vs_Signal']:+.2f}%</b></span>
            </div>
            """, unsafe_allow_html=True)

        # Zapis do state.json
        backtest_data = {}
        for _, r in df.iterrows():
            backtest_data[r["Ticker"]] = {
                "bh": round(r["BH_Return"], 2),
                "signal": round(r["Avg_Trade%"], 2),
                "winrate": round(r["Win_Rate%"], 1),
                "trades": int(r["Total_Trades"])
            }
        _save_backtest_results(backtest_data)

        if st.button("💾 Zapisz CSV"):
            st.download_button("Pobierz CSV", df.to_csv(index=False), f"backtest_{period}.csv", "text/csv")

        # Podsumowanie
        avg_bh = df["BH_Return"].mean()
        avg_sig = df["Avg_Trade%"].mean()
        st.divider()
        if avg_sig > avg_bh:
            st.success(f"🏆 **Sygnały średnio lepsze od Kup-Trzymaj o {avg_sig - avg_bh:+.2f}%**")
        else:
            st.info(f"📊 Kup-Trzymaj lepsze o {avg_bh - avg_sig:+.2f}% – sygnały wymagają optymalizacji")

# ------------------ MODUŁ: CZAT AI ------------------
def tavily_research(tavily_key, ticker, question):
    if not tavily_key:
        return "Brak klucza Tavily.", False
    queries = [question]
    if ticker:
        queries.extend([f"{ticker} company profile", f"{ticker} stock news", f"{ticker} analyst ratings"])
    all_answers, all_results = [], []
    for q in queries[:3]:
        try:
            resp = requests.post("https://api.tavily.com/search",
                                 headers={"Authorization": f"Bearer {tavily_key}"},
                                 json={"query": q, "topic": "finance", "max_results": 3,
                                       "include_answer": True, "include_raw_content": False},
                                 timeout=15)
            if resp.status_code == 200:
                j = resp.json()
                if j.get("answer"): all_answers.append(j["answer"])
                all_results.extend(j.get("results", []))
        except:
            continue
    bullets = []
    for item in all_results[:5]:
        title, url = item.get("title", ""), item.get("url", "")
        if title or url:
            bullets.append(f"- {title} ({url})")
    merged = "\n\n".join(all_answers)
    research = ""
    if merged: research += f"Podsumowanie Tavily:\n{merged}\n\n"
    if bullets: research += "Źródła:\n" + "\n".join(bullets)
    return research if research else "Brak danych z Tavily.", bool(research)

def render_ai_chat():
    st.title("🤖 Czat AI – Analityk finansowy")
    st.caption("Zero zgadywania – tylko dane z Trading Engine + Tavily.")

    if "OPENAI_API_KEY" not in st.secrets:
        st.error("❌ Brak OPENAI_API_KEY w secrets.toml")
        return
    if "TAVILY_API_KEY" not in st.secrets:
        st.error("❌ Brak TAVILY_API_KEY w secrets.toml")
        return

    openai_key = st.secrets["OPENAI_API_KEY"]
    tavily_key = st.secrets["TAVILY_API_KEY"]

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.markdown("### Historia rozmowy")
    for sender, msg in st.session_state.chat_history:
        st.markdown(f"**{sender}:** {msg}")

    user_input = st.text_input("Twoja wiadomość:")
    col_send, col_clear = st.columns([3,1])
    send = col_send.button("Wyślij")
    clear = col_clear.button("Wyczyść")

    if clear:
        st.session_state.chat_history = []
        st.rerun()

    if not send or not user_input.strip():
        return

    question = user_input.strip()
    st.session_state.chat_history.append(("Ty", question))

    ticker = detect_ticker_from_text(question)
    if not ticker and "last_analysis" in st.session_state:
        ticker = st.session_state["last_analysis"].get("ticker")

    trading_data = st.session_state.get("last_analysis", None)
    trading_summary = "Brak danych z Trading Engine."
    if trading_data:
        ind = trading_data["indicators"]
        scoring = trading_data.get("scoring", compute_scoring_pro(ind, trading_data.get("sentiment")))
        lines = [f"Ticker: {trading_data['ticker']}"]
        if not np.isnan(trading_data["price"]): lines.append(f"Cena: {fmt_price(trading_data['price'])}")
        lines.append(f"Sygnał: {trading_data['signal']}")
        lines.append(f"Scoring: {scoring}")
        if not np.isnan(ind["rsi"]): lines.append(f"RSI: {ind['rsi']:.1f}")
        if not np.isnan(ind["ma_fast"]) and not np.isnan(ind["ma_slow"]):
            lines.append(f"MA10: {fmt_price(ind['ma_fast'])}, MA30: {fmt_price(ind['ma_slow'])}")
        lines.append(f"Trend: {ind['trend']}")
        if not np.isnan(ind["adx"]): lines.append(f"ADX: {ind['adx']:.1f}")
        if not np.isnan(ind["atr"]): lines.append(f"ATR: {ind['atr']:.2f}")
        if not np.isnan(ind["vol"]): lines.append(f"Volatility: {ind['vol']:.4f}")
        if not np.isnan(ind["volume"]): lines.append(f"Volume: {ind['volume']:.0f}")
        if not np.isnan(ind["rvol"]): lines.append(f"RVOL: {ind['rvol']:.2f}")
        if not np.isnan(ind["vwap"]): lines.append(f"VWAP: {ind['vwap']:.2f}")
        if not np.isnan(ind["roc"]): lines.append(f"ROC: {ind['roc']:.2f}%")
        if not np.isnan(ind["stoch_k"]) and not np.isnan(ind["stoch_d"]):
            lines.append(f"Stochastic: {ind['stoch_k']:.1f}/{ind['stoch_d']:.1f}")
        if not np.isnan(ind["sl"]): lines.append(f"SL: {ind['sl']:.2f}")
        if not np.isnan(ind["tp"]): lines.append(f"TP: {ind['tp']:.2f}")
        lines.append(f"Sentyment newsów: {trading_data['sentiment']}")
        if "movement_label" in trading_data:
            lines.append(f"Typ ruchu: {trading_data['movement_label']}")
        trading_summary = "\n".join(lines)

    research_text, has_fund = tavily_research(tavily_key, ticker, question)

    try:
        system_prompt = (
            "Jesteś analitykiem finansowym. Masz dwa źródła: Trading Engine (dane techniczne) i Tavily (fundamenty/newsy). "
            "Nie zgaduj – odpowiadaj tylko na podstawie podanych danych. Jeśli brak danych, powiedz to wprost. "
            "Odpowiadaj po polsku, konkretnie."
        )
        def ask_gpt():
            return requests.post("https://api.openai.com/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {openai_key}"},
                                 json={"model": "gpt-4.1", "messages": [
                                     {"role": "system", "content": system_prompt},
                                     {"role": "system", "content": f"Dane z Trading Engine:\n{trading_summary}"},
                                     {"role": "system", "content": f"Research Tavily:\n{research_text}"}
                                 ] + [{"role": "user" if s=="Ty" else "assistant", "content": c}
                                      for s,c in st.session_state.chat_history],
                                      "temperature": 0.1}, timeout=60)
        resp = ask_gpt()
        if resp.status_code != 200:
            resp = ask_gpt()
        resp.raise_for_status()
        ai_msg = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        ai_msg = f"[Błąd GPT] {e}"

    st.session_state.chat_history.append(("AI", ai_msg))

    if st.session_state.get("telegram_enabled", True):
        tg_text = f"🤖 <b>AI – {ticker or 'bez tickera'}</b>\n{question[:200]}\n\n{ai_msg[:500]}"
        send_telegram(tg_text)

    st.rerun()

# ------------------ ROUTING ------------------
if mode == "🏠 Dashboard portfela":
    render_dashboard()
elif mode == "🤖 Czat AI (internet + trading)":
    render_ai_chat()
elif mode == "📈 Kombajn tradingowy":
    render_trading()
elif mode == "🔔 Alerty cenowe":
    render_alerts()
elif mode == "📊 Backtesting sygnałów":
    render_backtest()
else:
    render_scanner()
