# kombajn_streamlit_pl.py
"""
Kombajn Scanner (PL)
Intraday 60m, RSI/MACD/ADX/Bollinger/Fibo, zapis wykresow PNG, log CSV, opcjonalne AI.
Uruchom: streamlit run kombajn_streamlit_pl.py
"""

import os
import math
from datetime import datetime
from typing import Optional, Dict, Any, List

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
# Bezpieczny backend (serwer)
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams
from cycler import cycler

# Wymuszone ustawienia kolorow i wygladu wykresow (zapobiega grayscale)
rcParams['axes.prop_cycle'] = cycler(color=['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd', '#17becf'])
rcParams['figure.facecolor'] = 'white'
rcParams['axes.facecolor'] = 'white'
rcParams['savefig.facecolor'] = 'white'
rcParams['savefig.transparent'] = False
rcParams['lines.linewidth'] = 1.0
rcParams['font.size'] = 9
rcParams['legend.frameon'] = False
rcParams['image.cmap'] = 'viridis'

# Opcjonalnie seaborn - tylko jesli zainstalowany (nie wymagane)
try:
    import seaborn as sns
    sns.set_style("darkgrid")
    _HAS_SEABORN = True
except Exception:
    _HAS_SEABORN = False

# OpenAI opcjonalne
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

import streamlit as st

# ---------------- Konfiguracja ----------------
st.set_page_config(page_title="Kombajn Scanner (PL)", layout="wide")

CHART_DIR = "charts"
LOG_CSV = "scanner_log.csv"
PREF_FILE = "ai_model_pref.txt"
os.makedirs(CHART_DIR, exist_ok=True)

# Domyślne tickery (wklej swoją listę)
DEFAULT_TICKERS = [
    "STX.WA", "ACG.WA", "ACP.WA", "ACT.WA"
]

# Lista modeli AI (możesz dopisać własne nazwy)
AVAILABLE_MODELS = [
    "gpt-4o",
    "gpt-4o-large",
    "gpt-4o-16k",
    "gpt-4o-32k",
    "gpt-4o-mini",
    "gpt-4o-mini-2024",
    "gpt-4o-realtime"
]

# ---------------- Funkcje pomocnicze ----------------
def safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (list, tuple, np.ndarray, pd.Series)):
            if isinstance(x, pd.Series):
                return float(x.iloc[-1])
            return float(x[0])
        return float(x)
    except Exception:
        return None

def safe_round(x, ndigits=6):
    try:
        return round(float(x), ndigits)
    except Exception:
        return None

def append_log_csv(row: Dict[str, Any], filename: str = LOG_CSV):
    df_row = pd.DataFrame([row])
    header = not os.path.exists(filename)
    df_row.to_csv(filename, mode='a', index=False, header=header)

def load_model_pref_from_file(filename: str = PREF_FILE) -> Optional[str]:
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return None

def save_model_pref_to_file(model: str, filename: str = PREF_FILE):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(model)
    except Exception:
        pass

# ---------------- Wskaźniki techniczne ----------------
def calculate_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    if len(series) < window:
        return pd.Series([50] * len(series), index=series.index)
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=window).mean()
    loss = -delta.clip(upper=0).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()

def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()

def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def slope_of_series(series: pd.Series, n: int = 10) -> float:
    if len(series) < n:
        return 0.0
    y = series[-n:].values
    x = np.arange(len(y))
    if np.std(y) == 0:
        return 0.0
    y_scaled = (y - y.mean()) / (y.std() if y.std() != 0 else 1)
    coeffs = np.polyfit(x, y_scaled, 1)
    return float(coeffs[0])

def calculate_adx(df: pd.DataFrame, n: int = 14) -> float:
    try:
        high = df['High']
        low = df['Low']
        close = df['Close']
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=n).mean()
        plus_di = 100 * (plus_dm.rolling(window=n).sum() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(window=n).sum() / atr.replace(0, np.nan))
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
        adx = dx.rolling(window=n).mean()
        return float(adx.iloc[-1]) if not adx.isna().all() else 0.0
    except Exception:
        return 0.0

def bollinger_bands(series: pd.Series, window: int = 20, n_std: int = 2):
    ma = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = ma + n_std * std
    lower = ma - n_std * std
    width = (upper - lower) / ma.replace(0, np.nan)
    return upper, lower, width

def fib_levels_from_series(series: pd.Series) -> Dict[str, float]:
    high = float(series.max())
    low = float(series.min())
    diff = high - low if high != low else 1.0
    levels = {
        "0.0": low,
        "23.6": high - 0.236 * diff,
        "38.2": high - 0.382 * diff,
        "50.0": high - 0.5 * diff,
        "61.8": high - 0.618 * diff,
        "100.0": high
    }
    return levels

def fib_proximity_level(price: float, levels: Dict[str, float]) -> Dict[str, Any]:
    diffs = {k: abs(price - v) / (v if v != 0 else 1) for k, v in levels.items()}
    nearest = min(diffs.items(), key=lambda x: x[1])
    rel_diff = nearest[1]
    if rel_diff < 0.01:
        cls = "LOW"
    elif rel_diff < 0.03:
        cls = "MEDIUM"
    else:
        cls = "HIGH"
    return {"nearest_level": nearest[0], "rel_diff_pct": rel_diff * 100, "fibo_risk": cls}

def assess_risk(rsi: float, rvol: float, slope: float, macd_hist: float,
                bid: Optional[float], ask: Optional[float], fib_info: Dict[str, Any],
                adx: float, boll_width: Optional[float]) -> Dict[str, Any]:
    score = 0.0
    if rsi < 25 or rsi > 75:
        score += 1.0
    elif rsi < 35 or rsi > 65:
        score += 0.5
    if rvol > 3.0:
        score += 1.5
    elif rvol > 1.5:
        score += 0.8
    elif rvol > 1.0:
        score += 0.3
    if slope < -0.02:
        score += 1.0
    elif slope < -0.005:
        score += 0.5
    if macd_hist < 0:
        score += 0.5
    if bid is not None and ask is not None and bid > 0:
        spread_pct = abs(ask - bid) / bid
        if spread_pct > 0.02:
            score += 1.0
        elif spread_pct > 0.005:
            score += 0.4
    fib_risk = fib_info.get("fibo_risk", "MEDIUM")
    if fib_risk == "HIGH":
        score += 1.0
    elif fib_risk == "MEDIUM":
        score += 0.4
    if adx >= 25:
        if slope > 0 and macd_hist > 0:
            score -= 0.8
        else:
            score += 0.6
    elif adx < 20:
        score += 0.3
    if boll_width is not None and not math.isnan(boll_width):
        if boll_width > 0.08:
            score += 1.0
        elif boll_width > 0.04:
            score += 0.4
    if score <= 1.5:
        category = "LOW"
    elif score <= 3.0:
        category = "MEDIUM"
    else:
        category = "HIGH"
    return {"score": round(score, 2), "category": category}

# ---------------- Rysowanie wykresow ----------------
def plot_and_save(ticker: str, df: pd.DataFrame, levels: Dict[str, float],
                  fib_info: Dict[str, Any], filename: str) -> Optional[str]:
    try:
        close = df['Close']
        macd_line, signal_line, hist = macd(close)
        upper, lower, width = bollinger_bands(close)
        sma5 = sma(close, 5)
        sma20 = sma(close, 20)

        fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                                 gridspec_kw={'height_ratios': [3, 1.2, 0.8]})
        ax_price, ax_macd, ax_adx = axes

        # Wymuszone kolory linii
        ax_price.plot(df.index, close, label='Close', color='#111111', linewidth=1.2)
        ax_price.plot(df.index, sma5, label='SMA5', color='#2ca02c', linewidth=0.9)
        ax_price.plot(df.index, sma20, label='SMA20', color='#1f77b4', linewidth=0.9)
        ax_price.plot(df.index, upper, label='BollUpper', color='#ff7f0e', linestyle='--', linewidth=0.9)
        ax_price.plot(df.index, lower, label='BollLower', color='#ff7f0e', linestyle='--', linewidth=0.9)

        for k, v in levels.items():
            ax_price.axhline(v, color='gray', linestyle=':', linewidth=0.7)
        nearest_level = fib_info.get('nearest_level')
        if nearest_level and nearest_level in levels:
            y = levels[nearest_level]
            ax_price.annotate(f"Nearest Fibo {nearest_level}", xy=(df.index[-1], y),
                              xytext=(-80, 10), textcoords='offset points',
                              arrowprops=dict(arrowstyle="->", color='gray'), fontsize=8, color='gray')

        ax_price.set_title(f"{ticker}  Close / SMA / Bollinger")
        ax_price.legend(loc='upper left', fontsize=8)

        # MACD
        ax_macd.plot(df.index, macd_line, label='MACD', color='#9467bd', linewidth=0.9)
        ax_macd.plot(df.index, signal_line, label='Signal', color='#d62728', linewidth=0.9)
        colors = ['#2ca02c' if h >= 0 else '#d62728' for h in hist]
        ax_macd.bar(df.index, hist, label='Hist', color=colors, alpha=0.6)
        ax_macd.legend(loc='upper left', fontsize=8)
        ax_macd.set_ylabel("MACD")

        # ADX rolling
        try:
            adx_full = []
            for i in range(len(df)):
                if i < 14:
                    adx_full.append(np.nan)
                else:
                    adx_full.append(calculate_adx(df.iloc[:i+1], n=14))
            ax_adx.plot(df.index, adx_full, label='ADX', color='#17becf', linewidth=0.9)
            ax_adx.axhline(25, color='gray', linestyle='--', linewidth=0.7)
            ax_adx.set_ylabel("ADX")
            ax_adx.legend(loc='upper left', fontsize=8)
        except Exception:
            ax_adx.text(0.5, 0.5, "ADX niedostepny", transform=ax_adx.transAxes, ha='center')

        plt.tight_layout()
        fig.savefig(filename, dpi=150)
        plt.close(fig)
        return filename
    except Exception as e:
        try:
            with open("plot_errors.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} - Plot error for {ticker}: {e}\n")
        except Exception:
            pass
        return None

# ---------------- Logika skanowania ----------------
def classify_trend(close_series: pd.Series):
    short_w, long_w = 5, 20
    if len(close_series) < long_w:
        return "UNKNOWN", {}
    sma_short = sma(close_series, short_w).iloc[-1]
    sma_long = sma(close_series, long_w).iloc[-1]
    slp = slope_of_series(close_series, n=10)
    macd_line, signal_line, hist = macd(close_series)
    macd_val = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    if sma_short > sma_long and slp > 0.01 and macd_val > signal_val:
        trend = "UP"
    elif sma_short < sma_long and slp < -0.01 and macd_val < signal_val:
        trend = "DOWN"
    else:
        trend = "SIDEWAYS"
    details = {
        "sma_short": float(sma_short),
        "sma_long": float(sma_long),
        "slope": float(slp),
        "macd": float(macd_val),
        "macd_signal": float(signal_val),
        "macd_hist": float(hist.iloc[-1]) if len(hist) else 0.0
    }
    return trend, details

def scan_tickers(tickers: List[str], client: Optional[Any], MODEL: Optional[str],
                 show_progress: bool = True) -> List[Dict[str, Any]]:
    results = []
    total = len(tickers)
    progress = 0
    if show_progress:
        progress_bar = st.progress(0)
        status_text = st.empty()
    for s in tickers:
        try:
            df = yf.download(s, period="30d", interval="60m", progress=False)
            if df.empty or len(df) < 20:
                if show_progress:
                    status_text.text(f"Brak danych intraday dla {s} (pomijam)")
                progress += 1
                if show_progress:
                    progress_bar.progress(int(progress / total * 100))
                continue

            _close = df['Close']
            _vol = df['Volume']
            close = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            vol = _vol.iloc[:, 0] if isinstance(_vol, pd.DataFrame) else _vol

            try:
                c_dzis = float(close.iloc[-1])
            except Exception:
                if show_progress:
                    status_text.text(f"Nie mozna pobrac ceny dla {s} (pomijam)")
                progress += 1
                if show_progress:
                    progress_bar.progress(int(progress / total * 100))
                continue
            c_wczoraj = float(close.iloc[-2]) if len(close) >= 2 else c_dzis

            rsi = float(calculate_rsi(close).iloc[-1])
            rvol = float(vol.iloc[-1] / vol.mean()) if vol.mean() > 0 else 1.0
            zmiana = ((c_dzis - c_wczoraj) / c_wczoraj) * 100 if c_wczoraj != 0 else 0.0

            bid, ask = None, None
            try:
                t = yf.Ticker(s)
                info = t.info or {}
                raw_bid = info.get('bid') or info.get('bidPrice') or None
                raw_ask = info.get('ask') or info.get('askPrice') or None
                bid = safe_float(raw_bid)
                ask = safe_float(raw_ask)
            except Exception:
                bid, ask = None, None

            trend, details = classify_trend(close)
            macd_line, signal_line, hist = macd(close)
            macd_hist = float(hist.iloc[-1]) if len(hist) else 0.0
            slp = slope_of_series(close, n=10)
            adx = calculate_adx(df, n=14)
            upper, lower, width = bollinger_bands(close, window=20, n_std=2)
            boll_upper = float(upper.iloc[-1]) if not upper.isna().all() else float('nan')
            boll_lower = float(lower.iloc[-1]) if not lower.isna().all() else float('nan')
            boll_width = float(width.iloc[-1]) if not width.isna().all() else float('nan')

            levels = fib_levels_from_series(close)
            fib_info = fib_proximity_level(c_dzis, levels)

            risk = assess_risk(rsi=rsi, rvol=rvol, slope=slp, macd_hist=macd_hist,
                               bid=bid, ask=ask, fib_info=fib_info, adx=adx, boll_width=boll_width)

            show = False
            if s.upper() == "STX.WA":
                show = True
            if rsi < 35 and details.get("sma_short", 999) < details.get("sma_long", -999):
                show = True
            if rvol > 3.0:
                show = True

            if show:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                chart_file = os.path.join(CHART_DIR, f"{s.replace('/', '_')}_{timestamp}.png")
                row = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ticker": s,
                    "price": safe_round(c_dzis, 6),
                    "rsi": safe_round(rsi, 3),
                    "trend": trend,
                    "slope": safe_round(slp, 6),
                    "macd_hist": safe_round(macd_hist, 6),
                    "bid": safe_round(bid, 6),
                    "ask": safe_round(ask, 6),
                    "fibo_nearest": fib_info['nearest_level'],
                    "fibo_rel_pct": round(fib_info['rel_diff_pct'], 3),
                    "fibo_risk": fib_info['fibo_risk'],
                    "rvol": round(rvol, 3),
                    "adx": round(adx, 3),
                    "boll_upper": safe_round(boll_upper, 6),
                    "boll_lower": safe_round(boll_lower, 6),
                    "boll_width": safe_round(boll_width, 6),
                    "risk_score": risk['score'],
                    "risk_category": risk['category'],
                    "change_pct": round(zmiana, 3),
                    "chart_file": chart_file
                }
                append_log_csv(row)
                saved = plot_and_save(s, df, levels, fib_info, chart_file)
                if saved is None:
                    row["chart_file"] = None
                results.append(row)

            progress += 1
            if show_progress:
                progress_bar.progress(int(progress / total * 100))
                status_text.text(f"Skanowanie: {s} ({progress}/{total})")

        except Exception as e:
            if show_progress:
                status_text.text(f"Błąd przy {s}: {e}")
            progress += 1
            if show_progress:
                progress_bar.progress(int(progress / total * 100))
            continue

    if show_progress:
        status_text.text("Skanowanie zakończone.")
    return results

# ---------------- Interfejs Streamlit (PL) ----------------
def main_ui():
    st.title("Kombajn Scanner — intraday 60m")
    st.markdown("Analiza techniczna: RSI, MACD, ADX, Bollinger, Fibo. Zapis wykresów PNG i log CSV.")

    st.sidebar.header("Ustawienia")
    tickers_input = st.sidebar.text_area("Tickery (oddzielone przecinkiem)", value=",".join(DEFAULT_TICKERS), height=140)
    tickers = [t.strip() for t in tickers_input.split(",") if t.strip()]

    st.sidebar.markdown("---")
    openai_key = st.sidebar.text_input("OPENAI_API_KEY (opcjonalne)", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    use_ai = st.sidebar.checkbox("Włącz AI podsumowanie (opcjonalne)", value=False)
    saved_model = load_model_pref_from_file() or os.getenv("OPENAI_MODEL", "")
    chosen_model = saved_model if saved_model in AVAILABLE_MODELS else AVAILABLE_MODELS[0] if AVAILABLE_MODELS else None
    if use_ai:
        st.sidebar.markdown("Wybierz model AI")
        chosen_model = st.sidebar.selectbox("Model", options=AVAILABLE_MODELS, index=AVAILABLE_MODELS.index(chosen_model) if chosen_model in AVAILABLE_MODELS else 0)
        if st.sidebar.button("Zapisz preferencję modelu"):
            save_model_pref_to_file(chosen_model)
            st.sidebar.success(f"Zapisano preferencję: {chosen_model}")

    st.sidebar.markdown("---")
    st.sidebar.write("Interwał: 60m, okres: 30d (intraday).")
    run_now = st.sidebar.button("Uruchom skan teraz")

    st.sidebar.markdown("---")
    st.sidebar.write(f"Log CSV: `{LOG_CSV}`")
    st.sidebar.write(f"Wykresy: `{CHART_DIR}/`")

    if run_now:
        client = None
        MODEL = None
        if use_ai and openai_key and OpenAI:
            try:
                client = OpenAI(api_key=openai_key)
                MODEL = chosen_model
            except Exception as e:
                st.warning(f"Nie można zainicjalizować klienta OpenAI: {e}")
                client = None
                MODEL = None
        elif use_ai and not openai_key:
            st.warning("Włączono AI, ale nie podano OPENAI_API_KEY. AI zostanie wyłączone.")
            client = None
            MODEL = None

        with st.spinner("Skanowanie..."):
            results = scan_tickers(tickers, client=client, MODEL=MODEL, show_progress=True)

        if results:
            st.success(f"Znaleziono {len(results)} pozycje spełniające kryteria.")
            df_results = pd.DataFrame(results)
            st.dataframe(df_results.sort_values(by=["risk_score", "rsi"], ascending=[True, True]))

            st.markdown("### Wykresy i status")
            cols = st.columns(3)
            for i, row in enumerate(results):
                col = cols[i % 3]
                chart_file = row.get("chart_file")
                if chart_file and os.path.exists(chart_file):
                    try:
                        col.image(chart_file, use_column_width=True, caption=f"{row['ticker']} | Risk: {row['risk_category']}")
                        with open(chart_file, "rb") as f:
                            col.download_button(label="Pobierz PNG", data=f, file_name=os.path.basename(chart_file), mime="image/png")
                    except Exception:
                        col.write(f"{row['ticker']} - wykres niedostępny")
                else:
                    col.write(f"{row['ticker']} - brak wykresu")
                    if os.path.exists("plot_errors.log"):
                        try:
                            with open("plot_errors.log", "r", encoding="utf-8") as f:
                                lines = f.readlines()[-50:]
                                for ln in lines[-10:]:
                                    if row['ticker'] in ln:
                                        col.text(ln.strip())
                        except Exception:
                            pass

            # AI podsumowanie
            if client and results:
                try:
                    table_lines = []
                    header = "| TICKER | TREND | RISK | RSI | ADX | FIBO | BOLLW |"
                    sep = "|---|---|---|---:|---:|---|---:|"
                    table_lines.append(header); table_lines.append(sep)
                    for r in results:
                        table_lines.append(f"| {r['ticker']} | {r['trend']} | {r['risk_category']} | {r['rsi']} | {r['adx']} | {r['fibo_risk']} | {r['boll_width']} |")
                    table_text = "\n".join(table_lines)
                    prompt_system = (
                        "Jestes ekspertem gieldowym. Otrzymasz tabele w markdown. "
                        "Dla kazdego wiersza podaj skrocony komentarz i priorytet (LOW/MEDIUM/HIGH). "
                        "Uzywaj tylko informacji dostarczonych. Nie dawaj polecen kupna/sprzedazy. Nie uzywaj polskich znakow."
                    )
                    user_content = f"DANE:\n{table_text}\n"
                    res = client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": prompt_system},
                            {"role": "user", "content": user_content}
                        ],
                        max_tokens=500
                    )
                    ai_text = res.choices[0].message.content if hasattr(res, "choices") else str(res)
                    st.markdown("### AI - skrócony komentarz")
                    st.text(ai_text)
                except Exception as e:
                    st.warning(f"Błąd AI: {e}")
        else:
            st.info("Brak pozycji do raportu w tym przebiegu.")

    st.markdown("---")
    st.markdown("### Ostatnie wpisy w logu")
    if os.path.exists(LOG_CSV):
        try:
            df_log = pd.read_csv(LOG_CSV)
            st.dataframe(df_log.tail(50))
            with open(LOG_CSV, "rb") as f:
                st.download_button("Pobierz log CSV", data=f, file_name=LOG_CSV, mime="text/csv")
        except Exception as e:
            st.write(f"Nie można wczytać logu: {e}")
    else:
        st.write("Brak pliku logu jeszcze.")

    st.markdown("---")
    st.markdown("Uwaga: yfinance intraday może nie zwracać danych dla wszystkich tickerów. Bid/Ask dostępne tylko jeśli źródło je udostępnia.")
    st.markdown("Skrypt nie daje porad inwestycyjnych. Decyzje należą do Ciebie.")

if __name__ == "__main__":
    main_ui()
