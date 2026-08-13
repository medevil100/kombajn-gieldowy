# app.py – Kompletny system analizy GPW (Streamlit)
# Uruchom: streamlit run app.py

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import json
import os
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import openai
from tavily import TavilyClient

# ========================= KONFIGURACJA =========================
# Pobieranie kluczy z secrets Streamlit lub zmiennych środowiskowych
def get_secret(key: str, default: str = None) -> str:
    try:
        return st.secrets[key]
    except:
        return os.getenv(key, default)

TAVILY_API_KEY = get_secret("TAVILY_API_KEY")
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# Inicjalizacja klientów
if TAVILY_API_KEY:
    tavily = TavilyClient(api_key=TAVILY_API_KEY)
else:
    tavily = None

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    openai = None

# ========================= LOGOWANIE =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("gpw_analyzer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========================= CACHE DANYCH (w pamięci) =========================
data_cache = {}
CACHE_EXPIRY = timedelta(minutes=5)

def get_cached_data(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    key = f"{ticker}_{period}_{interval}"
    now = datetime.now()
    if key in data_cache:
        df, timestamp = data_cache[key]
        if now - timestamp < CACHE_EXPIRY:
            logger.info(f"Używam cache dla {ticker}")
            return df
    logger.info(f"Pobieram dane dla {ticker} z yfinance")
    try:
        stock = yf.Ticker(ticker + ".WA")  # GPW
        df = stock.history(period=period, interval=interval)
        if df.empty:
            raise ValueError(f"Brak danych dla {ticker}")
        data_cache[key] = (df, now)
        return df
    except Exception as e:
        logger.error(f"Błąd pobierania {ticker}: {e}")
        return pd.DataFrame()

# ========================= WSKAŹNIKI TECHNICZNE =========================
def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def get_technical_indicators(df: pd.DataFrame) -> Dict:
    if df.empty:
        return {}
    close = df['Close']
    rsi = calculate_rsi(close)
    macd_line, signal_line, hist = calculate_macd(close)
    atr = calculate_atr(df)
    sma20 = close.rolling(window=20).mean()
    
    last_idx = df.index[-1]
    return {
        'RSI': rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None,
        'MACD': macd_line.iloc[-1] if not pd.isna(macd_line.iloc[-1]) else None,
        'MACD_signal': signal_line.iloc[-1] if not pd.isna(signal_line.iloc[-1]) else None,
        'MACD_hist': hist.iloc[-1] if not pd.isna(hist.iloc[-1]) else None,
        'ATR': atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else None,
        'SMA20': sma20.iloc[-1] if not pd.isna(sma20.iloc[-1]) else None,
        'cena': close.iloc[-1],
        'df': df,         # dla wykresów
        'rsi_series': rsi,
        'macd_series': macd_line,
        'signal_series': signal_line,
        'hist_series': hist,
    }

def generate_alerts(indicators: Dict) -> List[str]:
    alerts = []
    if indicators.get('RSI') is not None:
        if indicators['RSI'] > 70:
            alerts.append("⚠️ RSI > 70 – wykupienie")
        elif indicators['RSI'] < 30:
            alerts.append("⚠️ RSI < 30 – wyprzedanie")
    if indicators.get('MACD_hist') is not None:
        if indicators['MACD_hist'] > 0 and indicators['MACD_hist'] > indicators['MACD_hist'] * 1.1:
            alerts.append("📈 MACD histogram rośnie – potencjalny wzrost")
        elif indicators['MACD_hist'] < 0 and indicators['MACD_hist'] < indicators['MACD_hist'] * 1.1:
            alerts.append("📉 MACD histogram maleje – potencjalny spadek")
    # SMA20
    if indicators.get('cena') is not None and indicators.get('SMA20') is not None:
        if indicators['cena'] > indicators['SMA20']:
            alerts.append("✅ Cena powyżej SMA20 – trend wzrostowy")
        else:
            alerts.append("❌ Cena poniżej SMA20 – trend spadkowy")
    return alerts

# ========================= SCANER WIADOMOŚCI (Tavily) =========================
def scan_news(ticker: str) -> List[Dict]:
    if not tavily:
        logger.warning("Brak TAVILY_API_KEY – symulacja newsów")
        return [{"title": "Przykładowy news o spółce", "url": "#", "content": "Symulacja"}]
    try:
        query = f"{ticker} GPW Warsaw Stock Exchange wiadomości"
        response = tavily.search(query=query, search_depth="basic", max_results=5)
        return response.get('results', [])
    except Exception as e:
        logger.error(f"Błąd Tavily: {e}")
        return []

# ========================= OCENA PRZY UŻYCIU GPT-4o =========================
def score_stock(ticker: str, indicators: Dict, news: List[Dict]) -> Dict:
    if not openai:
        logger.warning("Brak OPENAI_API_KEY – symulacja oceny")
        return {"score": 50, "sentiment": "neutral", "recommendation": "trzymaj", "summary": "Symulacja oceny."}
    
    # Przygotowanie danych dla GPT
    news_text = "\n".join([f"- {n['title']}: {n.get('content', '')}" for n in news[:3]])
    prompt = f"""
    Jesteś analitykiem giełdowym. Oceń akcję {ticker} na GPW na podstawie wskaźników technicznych i wiadomości.
    Wskaźniki: RSI={indicators.get('RSI')}, MACD={indicators.get('MACD')}, MACD_signal={indicators.get('MACD_signal')}, ATR={indicators.get('ATR')}, SMA20={indicators.get('SMA20')}, cena={indicators.get('cena')}.
    Wiadomości:
    {news_text}
    Odpowiedz w formacie JSON z polami: score (0-100), sentiment (bullish/bearish/neutral), recommendation (kup/sprzedaj/trzymaj), summary (krótki komentarz).
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"Błąd GPT: {e}")
        return {"score": 50, "sentiment": "neutral", "recommendation": "trzymaj", "summary": "Błąd analizy."}

# ========================= TELEGRAM NOTYFIKACJE =========================
def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Brak konfiguracji Telegram – pomijam")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=5)
        logger.info("Wysłano alert do Telegram")
    except Exception as e:
        logger.error(f"Błąd Telegram: {e}")

# ========================= WYKRESY PLOTLY =========================
def plot_stock(df: pd.DataFrame, rsi_series: pd.Series, macd_series: pd.Series, signal_series: pd.Series, hist_series: pd.Series, title: str):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        row_heights=[0.5, 0.25, 0.25],
                        subplot_titles=("Cena świecowa", "RSI", "MACD"))
    # Świece
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], name="Cena"), row=1, col=1)
    # SMA20
    sma20 = df['Close'].rolling(20).mean()
    fig.add_trace(go.Scatter(x=df.index, y=sma20, line=dict(color='orange', width=1), name="SMA20"), row=1, col=1)
    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=rsi_series, line=dict(color='purple'), name="RSI"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    # MACD
    fig.add_trace(go.Scatter(x=df.index, y=macd_series, line=dict(color='blue'), name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=signal_series, line=dict(color='red'), name="Signal"), row=3, col=1)
    fig.add_trace(go.Bar(x=df.index, y=hist_series, name="Histogram"), row=3, col=1)
    fig.update_layout(title=title, height=800, xaxis_rangeslider_visible=False)
    return fig

# ========================= AUTO-SKAN W TLE =========================
auto_scan_active = False
scan_interval = 60  # sekundy

def background_scan(tickers: List[str]):
    global auto_scan_active
    logger.info("Auto-skan uruchomiony")
    while auto_scan_active:
        for ticker in tickers:
            try:
                df = get_cached_data(ticker)
                if not df.empty:
                    ind = get_technical_indicators(df)
                    alerts = generate_alerts(ind)
                    if alerts:
                        msg = f"<b>Alert dla {ticker}</b>\n" + "\n".join(alerts)
                        send_telegram_alert(msg)
                        logger.info(f"Alert dla {ticker}")
            except Exception as e:
                logger.error(f"Błąd w auto-skanie {ticker}: {e}")
        time.sleep(scan_interval)

def start_auto_scan(tickers: List[str]):
    global auto_scan_active
    if not auto_scan_active:
        auto_scan_active = True
        thread = threading.Thread(target=background_scan, args=(tickers,), daemon=True)
        thread.start()
        st.success("Auto-skan uruchomiony")

def stop_auto_scan():
    global auto_scan_active
    auto_scan_active = False
    st.info("Auto-skan zatrzymany")

# ========================= INTERFEJS STREAMLIT =========================
def main():
    st.set_page_config(page_title="GPW Analyzer Pro", layout="wide")
    st.title("📊 GPW Analyzer – kompletna analiza")
    st.markdown("Pobiera dane z GPW (yfinance), oblicza wskaźniki, newsy, ocenę GPT-4o i wysyła alerty do Telegram.")
    
    # Sidebar konfiguracyjny
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        ticker_input = st.text_input("Ticker GPW (np. PKO, KGHM)", value="PKO")
        period = st.selectbox("Okres", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)
        interval = st.selectbox("Interwał", ["1d", "1h", "15m"], index=0)
        
        st.header("Auto-skan")
        auto_tickers = st.text_area("Ticker do auto-skanu (oddzielone przecinkiem)", value="PKO,KGHM,PKN")
        if st.button("▶️ Start auto-skan"):
            tickers_list = [t.strip() for t in auto_tickers.split(",") if t.strip()]
            if tickers_list:
                start_auto_scan(tickers_list)
            else:
                st.warning("Podaj przynajmniej jeden ticker")
        if st.button("⏹️ Stop auto-skan"):
            stop_auto_scan()
        
        st.header("Powiadomienia")
        if st.button("📨 Wyślij testowy alert"):
            send_telegram_alert("✅ Testowy alert z GPW Analyzer")
            st.success("Wysłano testową wiadomość")
    
    # Główny panel
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("🔍 Skanuj"):
            with st.spinner(f"Skanuję {ticker_input}..."):
                df = get_cached_data(ticker_input, period, interval)
                if df.empty:
                    st.error("Nie udało się pobrać danych")
                else:
                    st.session_state['df'] = df
                    st.session_state['ticker'] = ticker_input
                    st.session_state['indicators'] = get_technical_indicators(df)
                    st.session_state['alerts'] = generate_alerts(st.session_state['indicators'])
                    # Newsy
                    news = scan_news(ticker_input)
                    st.session_state['news'] = news
                    # Ocena GPT
                    score = score_stock(ticker_input, st.session_state['indicators'], news)
                    st.session_state['score'] = score
                    # Wykres
                    ind = st.session_state['indicators']
                    fig = plot_stock(df, ind['rsi_series'], ind['macd_series'], ind['signal_series'], ind['hist_series'], f"{ticker_input} - {period}")
                    st.session_state['fig'] = fig
                    # Alerty Telegram
                    if st.session_state['alerts']:
                        msg = f"<b>Alert dla {ticker_input}</b>\n" + "\n".join(st.session_state['alerts'])
                        send_telegram_alert(msg)
    
    # Wyświetlanie wyników
    if 'df' in st.session_state:
        st.subheader(f"📈 {st.session_state['ticker']}")
        col_wykres, col_info = st.columns([2, 1])
        with col_wykres:
            if 'fig' in st.session_state:
                st.plotly_chart(st.session_state['fig'], use_container_width=True)
        with col_info:
            ind = st.session_state['indicators']
            st.metric("Cena", f"{ind.get('cena', 0):.2f} PLN")
            st.metric("RSI", f"{ind.get('RSI', '--'):.1f}")
            st.metric("MACD", f"{ind.get('MACD', '--'):.2f}")
            st.metric("ATR", f"{ind.get('ATR', '--'):.2f}")
            st.metric("SMA20", f"{ind.get('SMA20', '--'):.2f}")
            
            st.subheader("🔔 Alerty")
            for alert in st.session_state.get('alerts', []):
                st.warning(alert)
            
            st.subheader("🧠 Ocena GPT-4o")
            score = st.session_state.get('score', {})
            st.write(f"**Wynik:** {score.get('score', '--')}/100")
            st.write(f"**Sentiment:** {score.get('sentiment', '--')}")
            st.write(f"**Rekomendacja:** {score.get('recommendation', '--')}")
            st.write(f"**Podsumowanie:** {score.get('summary', '')}")
            
            st.subheader("📰 Newsy")
            for n in st.session_state.get('news', []):
                st.markdown(f"- [{n.get('title')}]({n.get('url')})")

if __name__ == "__main__":
    main()
