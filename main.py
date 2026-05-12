
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

# ---------------- Konfiguracja ----------------
st.set_page_config(page_title="Kombajn Scanner — Official v3", layout="wide")
CHART_DIR = "charts"
LOG_CSV = "scanner_log.csv"
os.makedirs(CHART_DIR, exist_ok=True)

DEFAULT_TICKERS = ["CFS.WA", "MER.WA", "HUMA", "STX.WA", "NVG.WA", "TCRX", "HPE.WA", "PLRX"]
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

OPENAI_KEY_ENV = os.getenv("OPENAI_API_KEY", "")

PALETTES = {
    "standard": ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd', '#17becf'],
    "high-contrast": ['#d62728', '#2ca02c', '#1f77b4', '#ff7f0e', '#9467bd', '#17becf']
}

# ---------------- Pomocnicze ----------------
def safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (list, tuple, np.ndarray, pd.Series)):
            if isinstance(x, pd.Series):
                return float(pd.to_numeric(x.iloc[-1], errors='coerce'))
            return float(x[0])
        return float(x)
    except Exception:
        return None

def append_log_csv(row: Dict[str, Any], filename: str = LOG_CSV):
    try:
        df_row = pd.DataFrame([row])
        header = not os.path.exists(filename)
        df_row.to_csv(filename, mode='a', index=False, header=header)
    except Exception:
        pass

# ---------------- Źródło cen (yfinance) ----------------
def get_quote_yfinance(ticker: str) -> Dict[str, Optional[float]]:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        price = safe_float(info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose"))
        bid = safe_float(info.get("bid") or info.get("bidPrice"))
        ask = safe_float(info.get("ask") or info.get("askPrice"))
        return {"price": price, "bid": bid, "ask": ask, "source": "yfinance"}
    except Exception:
        return {"price": None, "bid": None, "ask": None, "source": "yfinance"}

# ---------------- Wskaźniki ----------------
def calculate_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    s = pd.to_numeric(series, errors='coerce')
    if len(s.dropna()) < window:
        return pd.Series([50]*len(s), index=s.index)
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(window=window).mean()
    loss = -delta.clip(upper=0).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def sma(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors='coerce').rolling(window=window).mean()

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    s = pd.to_numeric(series, errors='coerce')
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line.fillna(0), signal_line.fillna(0), hist.fillna(0)

def bollinger_bands(series: pd.Series, window=20, n_std=2):
    s = pd.to_numeric(series, errors='coerce')
    ma = s.rolling(window=window).mean()
    std = s.rolling(window=window).std()
    upper = ma + n_std * std
    lower = ma - n_std * std
    width = (upper - lower) / ma.replace(0, np.nan)
    return upper.fillna(np.nan), lower.fillna(np.nan), width.fillna(np.nan)

# ---------------- Wykres Plotly ----------------
def make_plotly_chart(df: pd.DataFrame, tp: float, sl: float, palette: List[str]):
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        if 'Close' not in df.columns:
            return None
        close = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if close.empty:
            return None
        upper, lower, _ = bollinger_bands(close)
        sma5 = sma(close, 5)
        sma20 = sma(close, 20)
        macd_line, signal_line, hist = macd(close)
        last_price = float(close.iloc[-1])
        tp_level = last_price * (1 + tp)
        sl_level = last_price * (1 - sl)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=close, mode='lines', name='Close', line=dict(color=palette[0])))
        if not sma5.isna().all():
            fig.add_trace(go.Scatter(x=df.index, y=sma5, mode='lines', name='SMA5', line=dict(color=palette[2])))
        if not sma20.isna().all():
            fig.add_trace(go.Scatter(x=df.index, y=sma20, mode='lines', name='SMA20', line=dict(color=palette[3])))
        if not upper.isna().all():
            fig.add_trace(go.Scatter(x=df.index, y=upper, mode='lines', name='BollUpper', line=dict(color=palette[1], dash='dash')))
        if not lower.isna().all():
            fig.add_trace(go.Scatter(x=df.index, y=lower, mode='lines', name='BollLower', line=dict(color=palette[1], dash='dash')))
        fig.add_hline(y=tp_level, line=dict(color=palette[2], dash='dot'), annotation_text=f"TP {tp*100:.1f}%")
        fig.add_hline(y=sl_level, line=dict(color=palette[0], dash='dot'), annotation_text=f"SL {sl*100:.1f}%")
        fig.update_layout(height=420, margin=dict(l=20, r=20, t=30, b=20), template="plotly_white")
        return fig
    except Exception:
        return None

# ---------------- AI helper (OpenAI) ----------------
def ai_commentary_for_rows(rows: List[Dict[str, Any]], model: str, openai_key: str) -> str:
    if not openai_key or not model:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        header = "| TICKER | PRICE | BID | ASK | RSI | ADX | STATUS | TP | SL |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|"
        lines = [header]
        for r in rows:
            lines.append(
                f"| {r['ticker']} | {r.get('price')} | {r.get('bid')} | {r.get('ask')} | "
                f"{r.get('rsi')} | {r.get('adx')} | {r.get('status')} | {r.get('tp_pct')} | {r.get('sl_pct')} |"
            )
        table_text = "\n".join(lines)
        prompt_system = (
            "Jestes ekspertem gieldowym. Otrzymasz tabele w markdown. "
            "Dla kazdego wiersza podaj skrocony komentarz i priorytet (BUY/HOLD/SELL). "
            "Uzywaj tylko informacji dostarczonych. Nie dawaj polecen kupna/sprzedazy."
        )
        user_content = f"DANE:\n{table_text}"
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": prompt_system},
                      {"role": "user", "content": user_content}],
            max_tokens=500
        )
        return res.choices[0].message.content
    except Exception:
        return ""

# ---------------- Skan i analiza ----------------
def scan_and_analyze(tickers: List[str], tp_pct: float, sl_pct: float, period: str, interval: str, palette_name: str,
                     rsi_threshold: int, rvol_threshold: float) -> (List[Dict[str, Any]], List[str]):
    results = []
    errors: List[str] = []
    palette = PALETTES.get(palette_name, PALETTES["standard"])
    for t in tickers:
        try:
            df = yf.download(t, period=period, interval=interval, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(-1)
            if df is None or df.empty or 'Close' not in df.columns or df['Close'].dropna().empty:
                df = yf.download(t, period=period, interval="1d", progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(-1)
                if df is None or df.empty or 'Close' not in df.columns or df['Close'].dropna().empty:
                    errors.append(f"{t}: brak danych intraday i brak danych dziennych")
                    continue
                used_interval = "1d"
            else:
                used_interval = interval

            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if df['Close'].dropna().empty:
                errors.append(f"{t}: brak poprawnych danych Close po konwersji")
                continue

            close = df['Close'].dropna()
            rsi = float(calculate_rsi(close).iloc[-1])
            macd_line, signal_line, hist = macd(close)
            macd_hist = float(hist.iloc[-1]) if len(hist) else 0.0

            adx = 0.0
            try:
                if all(c in df.columns for c in ['High', 'Low', 'Close']):
                    tmp = df[['High', 'Low', 'Close']].dropna()
                    if tmp.shape[0] >= 15:
                        high = tmp['High']; low = tmp['Low']; close_col = tmp['Close']
                        plus_dm = high.diff()
                        minus_dm = -low.diff()
                        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
                        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
                        tr1 = high - low
                        tr2 = (high - close_col.shift()).abs()
                        tr3 = (low - close_col.shift()).abs()
                        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                        atr = tr.rolling(window=14).mean()
                        plus_di = 100 * (plus_dm.rolling(window=14).sum() / atr.replace(0, np.nan))
                        minus_di = 100 * (minus_dm.rolling(window=14).sum() / atr.replace(0, np.nan))
                        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
                        adx_series = dx.rolling(window=14).mean()
                        if not adx_series.isna().all():
                            adx = float(adx_series.iloc[-1])
            except Exception:
                adx = 0.0

            rvol = float(df['Volume'].iloc[-1] / (df['Volume'].mean() if df['Volume'].mean() else 1.0))

            q = get_quote_yfinance(t)
            price = q.get("price") or float(close.iloc[-1])
            bid = q.get("bid")
            ask = q.get("ask")

            score = 0.0
            if rsi < 30:
                score += 1.0
            if rvol > 3.0:
                score += 1.0
            if macd_hist > 0:
                score -= 0.5
            if adx >= 25:
                score -= 0.3
            if score <= 0.5:
                status = "BUY"
            elif score <= 1.5:
                status = "HOLD"
            else:
                status = "SELL"

            sma5 = sma(close, 5).iloc[-1] if len(close) >= 5 else None
            sma20 = sma(close, 20).iloc[-1] if len(close) >= 20 else None
            if sma5 is not None and sma20 is not None:
                if sma5 > sma20:
                    trend = "byczy"
                elif sma5 < sma20:
                    trend = "niedzwiedzi"
                else:
                    trend = "neutralny"
            else:
                trend = "unknown"

            fig = make_plotly_chart(df, tp_pct, sl_pct, palette)

            row = {
                "ticker": t,
                "price": safe_float(price),
                "bid": safe_float(bid),
                "ask": safe_float(ask),
                "rsi": round(rsi, 2),
                "rvol": round(rvol, 2),
                "adx": round(adx, 2),
                "macd_hist": round(macd_hist, 4),
                "status": status,
                "trend": trend,
                "chart": fig,
                "df": df,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "quote_source": q.get("source"),
                "used_interval": used_interval
            }
            results.append(row)
        except Exception as e:
            errors.append(f"{t}: {repr(e)}")
            continue
    return results, errors

# ---------------- UI helpers ----------------
def color_for_status(status: str):
    if status == "SELL":
        return "#ff4d4d"
    if status == "HOLD":
        return "#ffb347"
    if status == "BUY":
        return "#2ca02c"
    return "#d3d3d3"

# ---------------- Streamlit UI ----------------
def main():
    st.title("Kombajn Scanner — Official v3")
    st.markdown("Ustaw tickery, TP/SL i interwał. Wyniki pojawią się poniżej. Skrypt używa tylko yfinance.")

    with st.sidebar:
        st.header("Ustawienia")
        tickers_input = st.text_area("Tickery (oddzielone przecinkiem)", value=",".join(DEFAULT_TICKERS), height=140)
        tickers = [x.strip() for x in tickers_input.split(",") if x.strip()]
        period = st.selectbox("Okres historyczny", ["60d", "30d", "90d"], index=0)
        interval = st.selectbox("Interwał", ["60m", "30m", "15m"], index=0)
        st.markdown("TP / SL")
        tp_pct = st.slider("Take Profit (%)", 0.5, 20.0, 3.0, 0.5) / 100.0
        sl_pct = st.slider("Stop Loss (%)", 0.5, 20.0, 2.0, 0.5) / 100.0
        st.markdown("Wygląd")
        palette_name = st.selectbox("Paleta kolorów", list(PALETTES.keys()), index=0)
        st.markdown("AI (opcjonalne)")
        openai_key_input = st.text_input("OPENAI_API_KEY (opcjonalne)", type="password", value=OPENAI_KEY_ENV)
        use_ai = st.checkbox("Włącz AI podsumowanie", value=False)
        model_choice = st.selectbox("Model AI", AVAILABLE_MODELS, index=0)
        run = st.button("Uruchom skan teraz")

    if run:
        st.info("Skanowanie... poczekaj chwilę.")
        results, errors = scan_and_analyze(tickers, tp_pct, sl_pct, period, interval, palette_name, rsi_threshold=35, rvol_threshold=3.0)

        if not results:
            st.warning("Brak wyników. Sprawdź tickery i ustawienia.")
        else:
            df_table = pd.DataFrame([{
                "Ticker": r["ticker"],
                "Cena": r["price"],
                "Bid": r["bid"],
                "Ask": r["ask"],
                "Trend": r["trend"],
                "Status": r["status"],
                "RSI": r["rsi"],
                "RVol": r["rvol"],
                "Źródło": r["quote_source"],
                "Interwał": r["used_interval"]
            } for r in results])
            df_table['StatusOrder'] = df_table['Status'].map({"BUY": 0, "HOLD": 1, "SELL": 2}).fillna(3)
            df_table = df_table.sort_values(by=['StatusOrder', 'RSI'], ascending=[True, True]).drop(columns=['StatusOrder'])
            st.markdown("### Tabela wyników (posortowana)")
            st.dataframe(df_table)

            st.markdown("### Szybki przegląd")
            preview_html = []
            for r in results:
                color = color_for_status(r['status'])
                preview_html.append(
                    f"<div style='background:{color};padding:8px;border-radius:6px;margin-bottom:6px;'>"
                    f"<b>{r['ticker']}</b> — Cena: <b>{r['price']}</b> | Bid: {r['bid']} | Ask: {r['ask']} | "
                    f"Trend: {r['trend']} | <b>{r['status']}</b> | TP: {r['tp_pct']*100:.1f}% SL: {r['sl_pct']*100:.1f}%"
                    f"</div>"
                )
            st.markdown("\n".join(preview_html), unsafe_allow_html=True)

            st.markdown("### Szczegóły spółek")
            for r in results:
                st.markdown(f"#### {r['ticker']}  —  {r.get('quote_source','yfinance')}  (interwał: {r.get('used_interval')})")
                cols = st.columns([1, 2])
                with cols[0]:
                    st.write(f"**Cena:** {r['price']}")
                    st.write(f"**Bid:** {r['bid']}   **Ask:** {r['ask']}")
                    st.write(f"**Trend:** {r['trend']}   **Status:** {r['status']}")
                    st.write(f"**RSI:** {r['rsi']}   **RVol:** {r['rvol']}   **ADX:** {r['adx']}")
                    st.write(f"**TP:** {r['tp_pct']*100:.1f}%   **SL:** {r['sl_pct']*100:.1f}%")
                    if st.button(f"Odśwież cenę {r['ticker']}", key=f"refresh_{r['ticker']}"):
                        q = get_quote_yfinance(r['ticker'])
                        st.write(f"Nowa cena: {q.get('price')} (Bid: {q.get('bid')}, Ask: {q.get('ask')})")
                with cols[1]:
                    if r['chart'] is not None:
                        st.plotly_chart(r['chart'], use_container_width=True)
                    else:
                        st.write("Brak wykresu (dane niekompletne)")

            if use_ai and openai_key_input:
                st.markdown("### AI - skrócone komentarze")
                ai_text = ai_commentary_for_rows([
                    {
                        "ticker": r["ticker"],
                        "price": r["price"],
                        "bid": r["bid"],
                        "ask": r["ask"],
                        "rsi": r["rsi"],
                        "adx": r["adx"],
                        "status": r["status"],
                        "tp_pct": f"{r['tp_pct']*100:.1f}%",
                        "sl_pct": f"{r['sl_pct']*100:.1f}%"
                    } for r in results
                ], model_choice, openai_key_input)
                if ai_text:
                    st.text(ai_text)
                else:
                    st.warning("AI nie zwróciło odpowiedzi (sprawdź klucz/model).")

            for r in results:
                row = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ticker": r["ticker"],
                    "price": r["price"],
                    "bid": r["bid"],
                    "ask": r["ask"],
                    "rsi": r["rsi"],
                    "rvol": r["rvol"],
                    "adx": r["adx"],
                    "status": r["status"],
                    "trend": r["trend"],
                    "tp_pct": r["tp_pct"],
                    "sl_pct": r["sl_pct"]
                }
                append_log_csv(row)
            st.success("Skan zakończony. Wyniki zapisane do scanner_log.csv")

        if errors:
            st.markdown("### Błędy i uwagi")
            for e in errors:
                st.markdown(f"- {e}")

    st.markdown("---")
    st.markdown("Uwaga: skrypt korzysta wyłącznie z yfinance jako oficjalnego źródła cen.")
    st.markdown("Decyzje inwestycyjne podejmujesz samodzielnie.")

if __name__ == "__main__":
    main()
