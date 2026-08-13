import os
import re
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

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
    mode = st.radio(
        "Tryb pracy:",
        [
            "🤖 Czat AI (internet + trading)",
            "📈 Kombajn tradingowy",
            "🧪 Skaner spółek (wpisz własne tickery)",
        ],
    )

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
   def to_scalar(x):
    import pandas as pd
    import numpy as np

    if isinstance(x, (pd.Series, np.ndarray, list)):
        if len(x) == 0:
            return np.nan
        try:
            val = np.asarray(x).ravel()[0]
        except Exception:
            return np.nan
    else:
        val = x

    try:
        return float(val)
    except (ValueError, TypeError):
        return np.nan

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

# ------------------ MODUŁ: TRADING ------------------
def render_trading():
    st.title("📈 Kombajn tradingowy – pełny panel")
    ticker = st.text_input("Ticker (np. AAPL, MSFT, STX.WA):", "AAPL")
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

                st.subheader("🤖 Analiza")
                c1, c2 = st.columns(2)
                c1.metric("Cena", f"{price:.2f}")
                c1.metric("RSI", f"{ind['rsi']:.1f}" if not np.isnan(ind['rsi']) else "Brak")
                c1.metric("Trend", ind['trend'])
                c1.metric("Sygnał", signal)
                c2.metric("Scoring", f"{scoring}/100")
                c2.metric("ADX", f"{ind['adx']:.1f}" if not np.isnan(ind['adx']) else "Brak")
                c2.metric("RVOL", f"{ind['rvol']:.2f}" if not np.isnan(ind['rvol']) else "Brak")
                c2.metric("Sentyment", sentiment)

                with st.expander("📊 Wszystkie wskaźniki"):
                    for k, v in ind.items():
                        if not isinstance(v, pd.Series) and not np.isnan(v):
                            st.write(f"**{k}:** {v:.2f}" if isinstance(v, float) else f"**{k}:** {v}")

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
                    "scoring": scoring, "period": period, "interval": interval
                }
                st.success("✅ Analiza zapisana.")
        except Exception as e:
            st.error(f"❌ Błąd: {str(e)}")

# ------------------ MODUŁ: SKANER ------------------
def render_scanner():
    st.title("🧪 Skaner spółek – własne tickery → TOP N")
    tickers_text = st.text_area("Tickery (oddzielone spacją, przecinkiem lub nową linią):",
                                "AAPL MSFT NVDA TSLA AMZN META GOOGL NFLX AMD INTC", height=120)
    max_to_show = st.slider("TOP N:", 5, 20, 10)

    if st.button("🔍 Skanuj", use_container_width=True):
        raw = re.split(r'[,\s\n]+', tickers_text)
        tickers = list(dict.fromkeys([t.strip().upper() for t in raw if t.strip()]))
        if not tickers:
            st.error("Brak tickerów.")
            return

        results = []
        progress_bar = st.progress(0)
        status = st.empty()
        for i, ticker in enumerate(tickers):
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
                results.append({
                    "Ticker": ticker, "Cena": price, "Trend": ind["trend"],
                    "RSI": ind["rsi"], "ADX": ind["adx"], "RVOL": ind["rvol"],
                    "Sentyment": sentiment, "Scoring": scoring
                })
            except:
                continue
        progress_bar.empty()
        status.empty()

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
                Cena: {row['Cena']:.2f} | Trend: {row['Trend']} | RSI: {row['RSI']:.1f}<br>
                ADX: {row['ADX']:.1f} | RVOL: {row['RVOL']:.2f} | Sentyment: {row['Sentyment']}<br>
                <b>Scoring: {score}/100</b> — {label}
            </div>
            """, unsafe_allow_html=True)

        if st.button("💾 Zapisz CSV"):
            st.download_button("Pobierz", df.to_csv(index=False), "skaner.csv", "text/csv")

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
        if not np.isnan(trading_data["price"]): lines.append(f"Cena: {trading_data['price']:.2f}")
        lines.append(f"Sygnał: {trading_data['signal']}")
        lines.append(f"Scoring: {scoring}")
        if not np.isnan(ind["rsi"]): lines.append(f"RSI: {ind['rsi']:.1f}")
        if not np.isnan(ind["ma_fast"]) and not np.isnan(ind["ma_slow"]):
            lines.append(f"MA10: {ind['ma_fast']:.2f}, MA30: {ind['ma_slow']:.2f}")
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
    st.rerun()

# ------------------ ROUTING ------------------
if mode == "🤖 Czat AI (internet + trading)":
    render_ai_chat()
elif mode == "📈 Kombajn tradingowy":
    render_trading()
else:
    render_scanner()
