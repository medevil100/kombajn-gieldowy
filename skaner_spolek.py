import streamlit as st
from openai import OpenAI
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
st.set_page_config(page_title="3× AI — Terminal Groszówek", layout="wide")

if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("Brak klucza OPENAI_API_KEY w st.secrets! Dodaj go w konfiguracji Streamlit.")
    st.stop()

# ================== STYLE ==================
st.markdown("""
<style>
body { background-color: #020617; color: #e5e7eb; font-family: system-ui, sans-serif; }
.box { padding: 15px; border-radius: 10px; font-size: 16px; margin-top: 15px; color: white; }
.swing  { background-color: #0f5132; }
.day    { background-color: #0d6efd; }
.long   { background-color: #6f42c1; }
.trend-box { padding: 10px; border-radius: 8px; margin-top: 10px; color: white; font-size: 15px; }
.trend-bear   { background-color: #d9534f; border: 2px solid #b52b27; }
.trend-bull   { background-color: #5cb85c; border: 2px solid #3d8b3d; }
.trend-side   { background-color: #f0ad4e; border: 2px solid #c77c11; }
.info-box { padding: 10px; border-radius: 8px; margin-top: 10px; background-color: #111827; color: #e5e7eb; border: 1px solid #374151; font-size: 14px; }
.plot-border { border: 3px solid #6f42c1; border-radius: 12px; padding: 8px; margin-top: 10px; }
.heatmap-container { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; }
.heatmap-tile { width: 120px; height: 85px; border-radius: 8px; padding: 8px; font-size: 12px; color: white; display: flex; flex-direction: column; justify-content: space-between; }
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Terminal Groszówek (PL + USA)")

# ================== AI MODUŁY (OPISOWE) ==================
def ai_swing(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o-mini", temperature=0.4,
        messages=[{"role": "user", "content": f"Agresywny swing trader. Analiza dla {ticker}: {text}. Zadanie: 2-3 zdania spekulacyjne."}],
    )
    return r.choices[0].message.content.strip()

def ai_day(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o", temperature=0.2,
        messages=[{"role": "user", "content": f"Precyzyjny daytrader. Analiza dla {ticker}: {text}. Zadanie: 2-3 konkretne zdania."}],
    )
    return r.choices[0].message.content.strip()

def ai_long(ticker, text):
    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": f"Długoterminowy analityk ryzyka. Analiza dla {ticker}: {text}. Zadanie: 2-3 zdania oceny stabilności."}],
    )
    return r.choices[0].message.content.strip()

def ai_meta_pick(market_df: pd.DataFrame, alerts: list, volume_signals: list) -> str:
    base_text = "Dane rynku:\n" + (market_df[["Ticker", "Trend", "Close", "TrendScore"]].head(30).to_string(index=False) if not market_df.empty else "Brak danych.\n")
    base_text += "\nAlerty:\n" + "\n".join(alerts[:20]) + "\nSygnały wolumenu:\n" + "\n".join(volume_signals[:20])
    
    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": f"Jesteś ekspertem penny stocks. Wybierz top 3 spółki z danych pod spekulację, podaj ticker i 3 zdania argumentacji bez podawania surowych liczb:\n{base_text}"}],
    )
    return r.choices[0].message.content.strip()

# ================== AI MODUŁY (WERDYKTY / SCORE) ==================
def ai_swing_verdict(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[{
            "role": "user",
            "content": f"Analiza swing trading dla {ticker}. Dane: {text}. "
                       f"Podaj werdykt w formacie: SWING: KUP / CZEKAJ / SPRZEDAJ."
        }],
    )
    out = r.choices[0].message.content.upper()
    if "KUP" in out: return "KUP"
    if "SPRZED" in out: return "SPRZEDAJ"
    return "CZEKAJ"

def ai_day_verdict(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        messages=[{
            "role": "user",
            "content": f"Analiza daytrading dla {ticker}. Dane: {text}. "
                       f"Podaj werdykt w formacie: DAY: KUP / CZEKAJ / SPRZEDAJ."
        }],
    )
    out = r.choices[0].message.content.upper()
    if "KUP" in out: return "KUP"
    if "SPRZED" in out: return "SPRZEDAJ"
    return "CZEKAJ"

def ai_long_verdict(ticker, text):
    r = client.chat.completions.create(
        model="o3-mini",
        temperature=0.1,
        messages=[{
            "role": "user",
            "content": f"Analiza długoterminowa dla {ticker}. Dane: {text}. "
                       f"Podaj werdykt w formacie: LONG: KUP / CZEKAJ / SPRZEDAJ."
        }],
    )
    out = r.choices[0].message.content.upper()
    if "KUP" in out: return "KUP"
    if "SPRZED" in out: return "SPRZEDAJ"
    return "CZEKAJ"

def ai_risk_score(text):
    r = client.chat.completions.create(
        model="o3-mini",
        temperature=0.1,
        messages=[{
            "role": "user",
            "content": f"Oceń ryzyko inwestycyjne (0-100) na podstawie: {text}. "
                       f"Zwróć tylko liczbę."
        }],
    )
    try:
        return int("".join([c for c in r.choices[0].message.content if c.isdigit()]))
    except:
        return 50

def ai_opportunity_score(text):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[{
            "role": "user",
            "content": f"Oceń potencjał spekulacyjny (0-100) na podstawie: {text}. "
                       f"Zwróć tylko liczbę."
        }],
    )
    try:
        return int("".join([c for c in r.choices[0].message.content if c.isdigit()]))
    except:
        return 50

def ai_signal(text):
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{
            "role": "user",
            "content": f"Na podstawie danych: {text}. "
                       f"Zwróć jedną etykietę: BUY, WATCH lub AVOID."
        }],
    )
    out = r.choices[0].message.content.upper()
    if "BUY" in out: return "BUY"
    if "AVOID" in out: return "AVOID"
    return "WATCH"

# ================== DANE I WSKAŹNIKI ==================
def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    period_str = "2y" if tf == "D1" else "60d"
    interval_str = "1d" if tf == "D1" else "60m"
    
    df = yf.download(ticker, period=period_str, interval=interval_str, auto_adjust=False, progress=False)
    
    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    return df

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    for w in [20, 50, 100, 200]:
        df[f"SMA{w}"] = close.rolling(w).mean()

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["BB_upper"] = ma20 + (2 * std20)
    df["BB_lower"] = ma20 - (2 * std20)

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    roll_up = gain.rolling(14).mean()
    roll_down = loss.rolling(14).mean()
    df["RSI14"] = 100 - (100 / (1 + (roll_up / (roll_down + 1e-9))))

    high = df["High"]
    low = df["Low"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()
    df["VolMA20"] = df["Volume"].rolling(20).mean()

    return df
# ================== TREND, SCORE, SYGNAŁY ==================
def detect_trend_from_df(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    close_val = float(last["Close"])
    
    sma200 = float(last["SMA200"]) if "SMA200" in df.columns and pd.notna(last["SMA200"]) else None
    sma50 = float(last["SMA50"]) if "SMA50" in df.columns and pd.notna(last["SMA50"]) else None

    if sma200 is not None:
        if close_val > sma200 * 1.01: return "bull"
        if close_val < sma200 * 0.99: return "bear"
    if sma50 is not None:
        if close_val > sma50: return "bull"
        if close_val < sma50: return "bear"

    return "side"

def trend_label_and_css(code: str):
    if code == "bull": return "Trend wzrostowy (🐂)", "trend-bull"
    if code == "bear": return "Trend spadkowy (🐻)", "trend-bear"
    return "Trend boczny (➖)", "trend-side"

def compute_trend_score(df: pd.DataFrame, trend_code: str) -> float:
    last = df.iloc[-1]
    score = 0.0
    close_val = float(last["Close"])

    if trend_code == "bull": score += 30
    if close_val < 5: score += 10

    sma50 = float(last["SMA50"]) if "SMA50" in df.columns and pd.notna(last["SMA50"]) else None
    sma200 = float(last["SMA200"]) if "SMA200" in df.columns and pd.notna(last["SMA200"]) else None
    rsi = float(last["RSI14"]) if "RSI14" in df.columns and pd.notna(last["RSI14"]) else None

    if sma50 and close_val > sma50: score += 15
    if sma200 and close_val > sma200: score += 15
    if sma50 and sma200 and sma50 > sma200: score += 20
    if rsi and 55 <= rsi <= 70: score += 10

    return score

def detect_volume_breakout_signals(df: pd.DataFrame, ticker: str) -> list:
    sigs = []
    if "VolMA20" not in df.columns or "ATR14" not in df.columns or "BB_upper" not in df.columns:
        return sigs
    last = df.iloc[-1]
    
    vol = float(last["Volume"])
    vol_ma = float(last["VolMA20"])
    atr = float(last["ATR14"])
    close_val = float(last["Close"])
    open_val = float(last["Open"])
    bb_upper = float(last["BB_upper"])

    if pd.isna(vol_ma) or pd.isna(atr) or atr == 0:
        return sigs

    if vol > 2 * vol_ma and abs(close_val - open_val) > atr and close_val > bb_upper:
        sigs.append(f"🔥 {ticker}: Potężne wybicie wolumenu z sygnałem momentum VSA!")
    elif vol > 1.5 * vol_ma:
        sigs.append(f"⚡ {ticker}: Zwiększony obrót spekulacyjny (>1.5x średnia).")
    
    return sigs

def plot_multichart(df: pd.DataFrame, ticker: str):
    df_plot = df.tail(60)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.7, 0.3])
    
    fig.add_trace(go.Candlestick(
        x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name="Kurs"
    ), row=1, col=1)
    
    if "SMA50" in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA50'], line=dict(color='cyan', width=1.5), name="SMA50"), row=1, col=1)
    if "SMA200" in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA200'], line=dict(color='magenta', width=1.5), name="SMA200"), row=1, col=1)
        
    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], name="Wolumen", marker_color='orange'), row=2, col=1)
    fig.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=20, b=10))
    return fig

# ================== PANEL GŁÓWNY STREAMLIT ==================
st.sidebar.header("Ustawienia skanera")
market_selection = st.sidebar.selectbox("Rynek", ["USA Groszówki", "Polska Spekulacja", "Własna lista"])
timeframe = st.sidebar.selectbox("Interwał danych", ["D1", "1H"])

if market_selection == "USA Groszówki":
    tickers_input = st.sidebar.text_area("Lista tickerów", value="SNDL, HUBC, OTLY, KAVL, MVIS")
elif market_selection == "Polska Spekulacja":
    tickers_input = st.sidebar.text_area("Lista tickerów", value="BBD.WA, ATT.WA, COG.WA, BIO.WA")
else:
    tickers_input = st.sidebar.text_area("Wpisz tickery", value="AAPL, TSLA")

ticker_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if st.sidebar.button("Uruchom Skaner i AI 🚀"):
    all_market_data = []
    global_alerts = []
    global_volume_sigs = []
    processed_dfs = {}

    progress_bar = st.progress(0)
    
    for idx, tk in enumerate(ticker_list):
        progress_bar.progress((idx + 1) / len(ticker_list))
        
        df_raw = get_ohlc(tk, timeframe)
        if df_raw.empty or len(df_raw) < 15:
            st.sidebar.warning(f"⚠️ {tk}: Brak wystarczających danych giełdowych.")
            continue
            
        df_feats = add_indicators(df_raw)
        trend_c = detect_trend_from_df(df_feats)
        score_t = compute_trend_score(df_feats, trend_c)
        v_sigs = detect_volume_breakout_signals(df_feats, tk)

        c_val = float(df_feats.iloc[-1]["Close"])
        
        all_market_data.append({"Ticker": tk, "Trend": trend_c, "Close": c_val, "TrendScore": score_t})
        global_volume_sigs.extend(v_sigs)
        
        if trend_c == "bull": global_alerts.append(f"🟢 {tk} - Silny trend wzrostowy.")
        elif trend_c == "bear": global_alerts.append(f"🔴 {tk} - Presja podażowa.")
            
        processed_dfs[tk] = (df_feats, trend_c, score_t)

    if processed_dfs:
        market_summary_df = pd.DataFrame(all_market_data)

        # 1. Heatmapa rynku
        st.subheader("📊 Wizualna mapa skanera (Trend Score)")
        st.markdown('<div class="heatmap-container">', unsafe_allow_html=True)
        for _, row in market_summary_df.iterrows():
            bg_color = "#064e3b" if row["Trend"] == "bull" else ("#7f1d1d" if row["Trend"] == "bear" else "#78350f")
            st.markdown(f"""
                <div class="heatmap-tile" style="background-color: {bg_color};">
                    <b style="font-size:14px;">{row['Ticker']}</b>
                    <span>Cena: {row['Close']:.2f}</span>
                    <span>Score: {row['TrendScore']:.0f}</span>
                </div>
            """, unsafe_allow_html=True)
        st.markdown('</div><br>', unsafe_allow_html=True)
