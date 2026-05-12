
# kombajn_streamlit_onefile.py
import os
import re
import time
from datetime import datetime
from functools import lru_cache
from typing import Optional, Dict, Any, List

import requests
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
from bs4 import BeautifulSoup

# -------------------- Konfiguracja --------------------
st.set_page_config(page_title="Kombajn Scanner", layout="wide")
CHART_DIR = "charts"
LOG_CSV = "scanner_log.csv"
PLOT_ERRORS = "plot_errors.log"
os.makedirs(CHART_DIR, exist_ok=True)

DEFAULT_TICKERS = ["CFS.WA", "MER.WA", "HUMA", "STX.WA", "NVG.WA", "TCRX", "HPE.WA", "PLRX"]
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
OPENAI_KEY_ENV = os.getenv("OPENAI_API_KEY", "")

SCRAPE_TIMEOUT = 8
SCRAPE_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KombajnScanner/1.0)"}
SCRAPE_DELAY = 1.0

PALETTES = {
    "standard": ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd', '#17becf'],
    "warm": ['#d62728', '#ff7f0e', '#ffbb78', '#ff9896', '#e377c2', '#8c564b'],
    "cool": ['#1f77b4', '#17becf', '#2ca02c', '#9467bd', '#7f7f7f', '#bcbd22'],
    "high-contrast": ['#d62728', '#2ca02c', '#1f77b4', '#ff7f0e', '#9467bd', '#17becf']
}

# -------------------- Pomocnicze --------------------
def log_error(msg: str):
    try:
        with open(PLOT_ERRORS, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")
    except Exception:
        pass

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
    except Exception as e:
        log_error(f"CSV write error: {e}")

# -------------------- Scraping helpers --------------------
@lru_cache(maxsize=1024)
def _cached_get(url: str):
    try:
        time.sleep(SCRAPE_DELAY)
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=SCRAPE_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log_error(f"HTTP error for {url}: {e}")
        return None

def _extract_number_from_text(text: str):
    if not text:
        return None
    text = text.replace('\xa0', ' ')
    m = re.search(r'([0-9]{1,3}(?:[ \u00A0][0-9]{3})*(?:[.,][0-9]+)?)', text)
    if not m:
        return None
    num = m.group(1)
    num = num.replace(' ', '').replace('\u00A0', '').replace(',', '.')
    try:
        return float(num)
    except Exception:
        return None

def quote_from_radarpl(ticker: str) -> Dict[str, Optional[float]]:
    url_candidates = [
        f"https://www.radar.pl/{ticker}",
        f"https://www.radar.pl/spolka/{ticker}",
        f"https://www.radar.pl/akcje/{ticker}"
    ]
    for url in url_candidates:
        html = _cached_get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        meta_price = soup.find("meta", {"property": "og:price:amount"}) or soup.find("meta", {"name": "price"})
        if meta_price and meta_price.get("content"):
            p = _extract_number_from_text(meta_price.get("content"))
            if p:
                return {"price": p, "bid": None, "ask": None, "source": "radar.pl-meta"}
        candidates = soup.find_all(attrs={"class": re.compile(r"(price|cena|kurs|quote)", re.I)})
        for c in candidates:
            txt = c.get_text(" ", strip=True)
            p = _extract_number_from_text(txt)
            if p:
                return {"price": p, "bid": None, "ask": None, "source": url}
        p = _extract_number_from_text(soup.get_text(" ", strip=True)[:4000])
        if p:
            return {"price": p, "bid": None, "ask": None, "source": url}
    return {"price": None, "bid": None, "ask": None, "source": "radar.pl"}

def quote_from_biznespl(ticker: str) -> Dict[str, Optional[float]]:
    url_candidates = [
        f"https://www.biznes.pl/{ticker}",
        f"https://www.biznes.pl/gielda/{ticker}",
        f"https://www.biznes.pl/akcje/{ticker}"
    ]
    for url in url_candidates:
        html = _cached_get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        meta_price = soup.find("meta", {"property": "og:price:amount"}) or soup.find("meta", {"name": "price"})
        if meta_price and meta_price.get("content"):
            p = _extract_number_from_text(meta_price.get("content"))
            if p:
                return {"price": p, "bid": None, "ask": None, "source": "biznes.pl-meta"}
        candidates = soup.find_all(attrs={"class": re.compile(r"(price|cena|kurs|quote)", re.I)})
        for c in candidates:
            txt = c.get_text(" ", strip=True)
            p = _extract_number_from_text(txt)
            if p:
                return {"price": p, "bid": None, "ask": None, "source": url}
        p = _extract_number_from_text(soup.get_text(" ", strip=True)[:4000])
        if p:
            return {"price": p, "bid": None, "ask": None, "source": url}
    return {"price": None, "bid": None, "ask": None, "source": "biznes.pl"}

# -------------------- Quote sources --------------------
def quote_from_yfinance(ticker: str) -> Dict[str, Optional[float]]:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        bid = safe_float(info.get("bid") or info.get("bidPrice"))
        ask = safe_float(info.get("ask") or info.get("askPrice"))
        price = safe_float(info.get("regularMarketPrice") or info.get("previousClose") or info.get("currentPrice"))
        return {"price": price, "bid": bid, "ask": ask, "source": "yfinance"}
    except Exception as e:
        log_error(f"yfinance quote error {ticker}: {e}")
        return {"price": None, "bid": None, "ask": None, "source": "yfinance"}

def quote_from_alphavantage(ticker: str) -> Dict[str, Optional[float]]:
    if not ALPHAVANTAGE_KEY:
        return {"price": None, "bid": None, "ask": None, "source": "alphavantage"}
    try:
        url = "https://www.alphavantage.co/query"
        params = {"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": ALPHAVANTAGE_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json().get("Global Quote", {})
        price = safe_float(data.get("05. price"))
        return {"price": price, "bid": None, "ask": None, "source": "alphavantage"}
    except Exception as e:
        log_error(f"AlphaVantage quote error {ticker}: {e}")
        return {"price": None, "bid": None, "ask": None, "source": "alphavantage"}

def quote_from_finnhub(ticker: str) -> Dict[str, Optional[float]]:
    if not FINNHUB_KEY:
        return {"price": None, "bid": None, "ask": None, "source": "finnhub"}
    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": ticker, "token": FINNHUB_KEY}
        r = requests.get(url, params=params, timeout=10)
        j = r.json()
        price = safe_float(j.get("c"))
        return {"price": price, "bid": None, "ask": None, "source": "finnhub"}
    except Exception as e:
        log_error(f"Finnhub quote error {ticker}: {e}")
        return {"price": None, "bid": None, "ask": None, "source": "finnhub"}

def get_best_quote(ticker: str, allow_scrape: bool = False) -> Dict[str, Optional[float]]:
    q = quote_from_yfinance(ticker)
    if q["price"] is not None:
        return q
    q = quote_from_finnhub(ticker)
    if q["price"] is not None:
        return q
    q = quote_from_alphavantage(ticker)
    if q["price"] is not None:
        return q
    if allow_scrape:
        q = quote_from_radarpl(ticker)
        if q["price"] is not None:
            return q
        q = quote_from_biznespl(ticker)
        if q["price"] is not None:
            return q
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False)
        if not df.empty and 'Close' in df.columns:
            return {"price": float(df['Close'].iloc[-1]), "bid": None, "ask": None, "source": "yfinance-history-fallback"}
    except Exception:
        pass
    return {"price": None, "bid": None, "ask": None, "source": "none"}

# -------------------- Wskaźniki --------------------
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

def fib_levels(series: pd.Series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return {}
    high = float(s.max()); low = float(s.min()); diff = high - low if high != low else 1.0
    return {"0.0": low, "23.6": high - 0.236*diff, "38.2": high - 0.382*diff, "50.0": high - 0.5*diff, "61.8": high - 0.618*diff, "100.0": high}

# -------------------- Wykresy Plotly --------------------
def make_plotly_chart(ticker: str, df: pd.DataFrame, tp: float, sl: float, palette: List[str]):
    try:
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        close = pd.to_numeric(df['Close'], errors='coerce')
        upper, lower, width = bollinger_bands(close)
        sma5 = sma(close, 5)
        sma20 = sma(close, 20)
        macd_line, signal_line, hist = macd(close)

        last_price = float(close.iloc[-1])
        tp_level = last_price * (1 + tp)
        sl_level = last_price * (1 - sl)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=close, mode='lines', name='Close', line=dict(color=palette[0])))
        fig.add_trace(go.Scatter(x=df.index, y=sma5, mode='lines', name='SMA5', line=dict(color=palette[2])))
        fig.add_trace(go.Scatter(x=df.index, y=sma20, mode='lines', name='SMA20', line=dict(color=palette[3])))
        fig.add_trace(go.Scatter(x=df.index, y=upper, mode='lines', name='BollUpper', line=dict(color=palette[1], dash='dash')))
        fig.add_trace(go.Scatter(x=df.index, y=lower, mode='lines', name='BollLower', line=dict(color=palette[1], dash='dash')))
        fig.add_hline(y=tp_level, line=dict(color=palette[2], dash='dot'), annotation_text=f"TP {tp*100:.1f}%")
        fig.add_hline(y=sl_level, line=dict(color=palette[0], dash='dot'), annotation_text=f"SL {sl*100:.1f}%")
        fig.update_layout(height=420, margin=dict(l=20, r=20, t=30, b=20), template="plotly_white")
        return fig
    except Exception as e:
        log_error(f"make_plotly_chart {ticker}: {e}")
        return None

# -------------------- News scraping (Google News heuristic) --------------------
def search_news_google(ticker: str, limit: int = 5) -> List[Dict[str, str]]:
    try:
        query = requests.utils.requote_uri(f"{ticker} news")
        url = f"https://www.google.com/search?q={query}&tbm=nws"
        html = _cached_get(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        items = []
        for g in soup.select("div.dbsr")[:limit]:
            a = g.find("a")
            title = g.find("div", {"role": "heading"})
            snippet = g.find("div", {"class": "Y3v8qd"})
            link = a['href'] if a else None
            items.append({
                "title": title.get_text(strip=True) if title else "",
                "snippet": snippet.get_text(strip=True) if snippet else "",
                "link": link or ""
            })
        return items
    except Exception as e:
        log_error(f"news search error {ticker}: {e}")
        return []

# -------------------- AI helper (optional) --------------------
def ai_commentary_for_rows(rows: List[Dict[str, Any]], model: str, openai_key: str) -> str:
    if not openai_key or not model:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        header = "| TICKER | PRICE | BID | ASK | RSI | ADX | RISK | TP | SL |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|"
        lines = [header]
        for r in rows:
            lines.append(f"| {r['ticker']} | {r.get('price')} | {r.get('bid')} | {r.get('ask')} | {r.get('rsi')} | {r.get('adx')} | {r.get('risk_category')} | {r.get('tp_pct')} | {r.get('sl_pct')} |")
        table_text = "\n".join(lines)
        prompt_system = "Jestes ekspertem gieldowym. Otrzymasz tabele w markdown. Dla kazdego wiersza podaj skrocony komentarz i priorytet (LOW/MEDIUM/HIGH). Uzywaj tylko informacji dostarczonych. Nie dawaj polecen kupna/sprzedazy."
        user_content = f"DANE:\n{table_text}"
        res = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content":prompt_system},{"role":"user","content":user_content}],
            max_tokens=500
        )
        return res.choices[0].message.content
    except Exception as e:
        log_error(f"AI error: {e}")
        return ""

# -------------------- Skan i analiza --------------------
def scan_and_analyze(tickers: List[str], tp_pct: float, sl_pct: float, period: str, interval: str, palette_name: str,
                     rsi_threshold: int, rvol_threshold: float, allow_scrape: bool) -> List[Dict[str, Any]]:
    results = []
    palette = PALETTES.get(palette_name, PALETTES["standard"])
    for t in tickers:
        try:
            df = yf.download(t, period=period, interval=interval, progress=False)
            if df is None or df.empty or 'Close' not in df.columns:
                log_error(f"No intraday data for {t}")
                continue
            for col in ['Open','High','Low','Close','Volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            close = df['Close'].dropna()
            if close.empty:
                log_error(f"No close after sanitize for {t}")
                continue

            rsi = float(calculate_rsi(close).iloc[-1])
            macd_line, signal_line, hist = macd(close)
            macd_hist = float(hist.iloc[-1]) if len(hist) else 0.0

            # ADX local
            adx = 0.0
            try:
                tmp = df[['High','Low','Close']].copy()
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
                adx = float(adx_series.iloc[-1]) if not adx_series.isna().all() else 0.0
            except Exception:
                adx = 0.0

            rvol = float(df['Volume'].iloc[-1] / (df['Volume'].mean() if df['Volume'].mean() else 1.0))

            q = get_best_quote(t, allow_scrape=allow_scrape)
            price = q.get("price") or float(close.iloc[-1])
            bid = q.get("bid")
            ask = q.get("ask")

            levels = fib_levels(close)

            # risk simple
            risk_score = 0.0
            if rsi < 25 or rsi > 75:
                risk_score += 1.0
            if rvol > 3.0:
                risk_score += 1.0
            if adx < 20:
                risk_score += 0.5
            if macd_hist < 0:
                risk_score += 0.5
            if risk_score <= 1.0:
                risk_cat = "LOW"
            elif risk_score <= 2.5:
                risk_cat = "MEDIUM"
            else:
                risk_cat = "HIGH"

            # trend simple
            sma5 = sma(close, 5).iloc[-1] if len(close) >= 5 else None
            sma20 = sma(close, 20).iloc[-1] if len(close) >= 20 else None
            if sma5 is not None and sma20 is not None:
                if sma5 > sma20:
                    trend = "UP"
                elif sma5 < sma20:
                    trend = "DOWN"
                else:
                    trend = "SIDEWAYS"
            else:
                trend = "UNKNOWN"

            fig = make_plotly_chart(t, df, tp_pct, sl_pct, palette)

            row = {
                "ticker": t,
                "price": safe_float(price),
                "bid": safe_float(bid),
                "ask": safe_float(ask),
                "rsi": round(rsi, 2),
                "rvol": round(rvol, 2),
                "adx": round(adx, 2),
                "macd_hist": round(macd_hist, 4),
                "risk_score": round(risk_score, 2),
                "risk_category": risk_cat,
                "trend": trend,
                "levels": levels,
                "chart": fig,
                "df": df,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "show": True,
                "quote_source": q.get("source")
            }
            results.append(row)
        except Exception as e:
            log_error(f"scan error {t}: {e}")
            continue
    return results

# -------------------- UI --------------------
def color_for_row(r: Dict[str, Any]):
    # priority: SELL (risk HIGH & trend DOWN) -> red; LOW risk & trend UP -> green; neutral -> gray
    if r['risk_category'] == "HIGH" and r['trend'] == "DOWN":
        return "#ff4d4d"  # strong red
    if r['risk_category'] == "LOW" and r['trend'] == "UP":
        return "#2ca02c"  # green
    if r['trend'] == "UP":
        return "#8fd19e"  # light green
    if r['trend'] == "DOWN":
        return "#ffb3b3"  # light red
    return "#d3d3d3"  # gray

def main():
    st.title("Kombajn Scanner — All-in-One")
    st.markdown("Wklej tickery, ustaw TP/SL i interwał. Wyniki pojawią się poniżej — każda spółka ma: ticker, cena, bid/ask, trend, TP/SL i kolor statusu.")

    with st.sidebar:
        st.header("Ustawienia")
        tickers_input = st.text_area("Tickery (oddzielone przecinkiem)", value=",".join(DEFAULT_TICKERS), height=140)
        tickers = [x.strip() for x in tickers_input.split(",") if x.strip()]
        period = st.selectbox("Okres historyczny", ["30d", "60d", "90d"], index=0)
        interval = st.selectbox("Interwał", ["60m", "30m", "15m"], index=0)
        st.markdown("TP / SL")
        tp_pct = st.slider("Take Profit (%)", 0.5, 20.0, 3.0, 0.5) / 100.0
        sl_pct = st.slider("Stop Loss (%)", 0.5, 20.0, 2.0, 0.5) / 100.0
        st.markdown("Filtry (oznaczenia)")
        rsi_threshold = st.slider("Pokaż jeśli RSI <", 10, 50, 35)
        rvol_threshold = st.slider("Pokaż jeśli RVol >", 1.0, 10.0, 3.0, 0.1)
        palette_name = st.selectbox("Paleta kolorów", list(PALETTES.keys()), index=0)
        allow_scrape = st.checkbox("Włącz scraping Radar.pl / Biznes.pl (fallback)", value=False)
        openai_key_input = st.text_input("OPENAI_API_KEY (opcjonalne)", type="password", value=OPENAI_KEY_ENV)
        use_ai = st.checkbox("Włącz AI podsumowanie", value=False)
        model_choice = st.selectbox("Model AI", AVAILABLE_MODELS, index=0)
        run = st.button("Uruchom skan teraz")

    if run:
        st.info("Skanowanie... poczekaj chwilę.")
        results = scan_and_analyze(tickers, tp_pct, sl_pct, period, interval, palette_name, rsi_threshold, rvol_threshold, allow_scrape)

        # Top summary table (compact, color-coded)
        st.markdown("### Szybki przegląd")
        rows_md = []
        for r in results:
            color = color_for_row(r)
            badge = ""
            if r['risk_category'] == "HIGH":
                badge = "🔴 SELL"
            elif r['risk_category'] == "MEDIUM":
                badge = "🟠 NEUTRAL"
            else:
                badge = "🟢 LOW"
            rows_md.append(f"<div style='background:{color};padding:8px;border-radius:6px;margin-bottom:6px;'>"
                           f"<b>{r['ticker']}</b> — Cena: <b>{r['price']}</b> | Bid: {r['bid']} | Ask: {r['ask']} | Trend: {r['trend']} | {badge} | TP: {r['tp_pct']*100:.1f}% SL: {r['sl_pct']*100:.1f}%"
                           f"</div>")
        st.markdown("\n".join(rows_md), unsafe_allow_html=True)

        st.markdown("### Szczegóły spółek")
        for r in results:
            st.markdown(f"#### {r['ticker']} — {r['quote_source']}")
            cols = st.columns([1, 2])
            with cols[0]:
                st.write(f"**Cena:** {r['price']}")
                st.write(f"**Bid:** {r['bid']}   **Ask:** {r['ask']}")
                st.write(f"**Trend:** {r['trend']}   **Ryzyko:** {r['risk_category']} ({r['risk_score']})")
                st.write(f"**RSI:** {r['rsi']}   **RVol:** {r['rvol']}   **ADX:** {r['adx']}")
                st.write(f"**TP:** {r['tp_pct']*100:.1f}%   **SL:** {r['sl_pct']*100:.1f}%")
                if r['levels']:
                    lv = ", ".join([f"{k}:{v:.2f}" for k,v in r['levels'].items()])
                    st.write("**Fibo:** " + lv)
                # news button
                if st.button(f"Sprawdź wiadomości: {r['ticker']}", key=f"news_{r['ticker']}"):
                    news = search_news_google(r['ticker'], limit=5)
                    if news:
                        for n in news:
                            st.markdown(f"- [{n['title']}]({n['link']})  \n  {n['snippet']}")
                    else:
                        st.write("Brak wyników wiadomości.")
                # download CSV
                try:
                    csv_bytes = r['df'].to_csv().encode('utf-8')
                    st.download_button("Pobierz dane CSV", data=csv_bytes, file_name=f"{r['ticker']}_data.csv", mime="text/csv")
                except Exception:
                    pass
            with cols[1]:
                if r['chart'] is not None:
                    st.plotly_chart(r['chart'], use_container_width=True)
                else:
                    st.write("Brak wykresu (sprawdź plot_errors.log)")

        # AI summary
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
                    "risk_category": r["risk_category"],
                    "tp_pct": f"{r['tp_pct']*100:.1f}%",
                    "sl_pct": f"{r['sl_pct']*100:.1f}%"
                } for r in results
            ], model_choice, openai_key_input)
            if ai_text:
                st.text(ai_text)
            else:
                st.warning("AI nie zwróciło odpowiedzi (sprawdź klucz/model).")

        # Save summary to CSV log (optional)
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
                "risk_score": r["risk_score"],
                "risk_category": r["risk_category"],
                "tp_pct": r["tp_pct"],
                "sl_pct": r["sl_pct"]
            }
            append_log_csv(row)

        st.success("Skan zakończony.")

    st.markdown("---")
    st.markdown("### Ostatnie błędy (tail plot_errors.log)")
    if os.path.exists(PLOT_ERRORS):
        try:
            with open(PLOT_ERRORS, "r", encoding="utf-8") as f:
                lines = f.readlines()[-30:]
                st.text("".join(lines[-10:]))
        except Exception:
            st.write("Brak dostępu do logu błędów.")
    else:
        st.write("Brak błędów zarejestrowanych.")

if __name__ == "__main__":
    main()
