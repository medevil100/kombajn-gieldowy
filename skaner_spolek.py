import streamlit as st
from openai import OpenAI
import yfinance as yf
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
.plot-border { border: 3px solid #6f42c1; border-radius: 12px; padding: 8px; margin-top: 10px; }
.heatmap-container { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; }
.heatmap-tile { width: 120px; height: 85px; border-radius: 8px; padding: 8px; font-size: 12px; color: white; display: flex; flex-direction: column; justify-content: space-between; }
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Terminal Groszówek (PL + USA)")

# ================== AI – OPISOWE ==================
def ai_swing(ticker: str, text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[{
                "role": "user",
                "content": (
                    f"Jesteś agresywnym swing traderem. "
                    f"Analizujesz spółkę {ticker}. Dane: {text}. "
                    f"Napisz 2–3 krótkie, konkretne zdania po polsku."
                )
            }],
        )
        return r.choices[0].message.content.strip()
    except:
        return "(SWING AI — błąd)"

def ai_day(ticker: str, text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": (
                    f"Jesteś daytraderem. "
                    f"Analizujesz spółkę {ticker}. Dane: {text}. "
                    f"Napisz 2–3 zdania po polsku."
                )
            }],
        )
        return r.choices[0].message.content.strip()
    except:
        return "(DAY AI — błąd)"

def ai_long(ticker: str, text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": (
                    f"Jesteś analitykiem długoterminowym. "
                    f"Analizujesz spółkę {ticker}. Dane: {text}. "
                    f"Napisz 2–3 zdania po polsku."
                )
            }],
        )
        return r.choices[0].message.content.strip()
    except:
        return "(LONG AI — błąd)"

# ================== AI – WERDYKTY / SCORE / SIGNAL ==================
def clean_payload(df, trend, score):
    last = df.iloc[-1]

    def safe(v, prec=4):
        try:
            if pd.isna(v):
                return "brak"
            return f"{float(v):.{prec}f}"
        except:
            return "brak"

    return (
        f"Cena: {safe(last['Close'])}, "
        f"RSI14: {safe(last.get('RSI14'), 1)}, "
        f"SMA50: {safe(last.get('SMA50'))}, "
        f"SMA200: {safe(last.get('SMA200'))}, "
        f"Trend: {trend}, "
        f"TrendScore: {score}"
    )

def ai_swing_verdict(ticker, text):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": f"Swing trading. Dane: {text}. Werdykt: SWING = KUP / CZEKAJ / SPRZEDAJ."
            }],
        )
        out = r.choices[0].message.content.upper()
        if "KUP" in out: return "KUP"
        if "SPRZED" in out: return "SPRZEDAJ"
        return "CZEKAJ"
    except:
        return "CZEKAJ"

def ai_day_verdict(ticker, text):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": f"Daytrading. Dane: {text}. Werdykt: DAY = KUP / CZEKAJ / SPRZEDAJ."
            }],
        )
        out = r.choices[0].message.content.upper()
        if "KUP" in out: return "KUP"
        if "SPRZED" in out: return "SPRZEDAJ"
        return "CZEKAJ"
    except:
        return "CZEKAJ"

def ai_long_verdict(ticker, text):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": f"Long-term. Dane: {text}. Werdykt: LONG = KUP / CZEKAJ / SPRZEDAJ."
            }],
        )
        out = r.choices[0].message.content.upper()
        if "KUP" in out: return "KUP"
        if "SPRZED" in out: return "SPRZEDAJ"
        return "CZEKAJ"
    except:
        return "CZEKAJ"

def ai_risk_score(text):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": f"Oceń ryzyko (0-100). Dane: {text}. Zwróć tylko liczbę."
            }],
        )
        raw = r.choices[0].message.content
        digits = "".join(c for c in raw if c.isdigit())
        return int(digits) if digits else 50
    except:
        return 50

def ai_opportunity_score(text):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": f"Oceń potencjał (0-100). Dane: {text}. Zwróć tylko liczbę."
            }],
        )
        raw = r.choices[0].message.content
        digits = "".join(c for c in raw if c.isdigit())
        return int(digits) if digits else 50
    except:
        return 50

def ai_signal(text):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": f"Sygnał: BUY / WATCH / AVOID. Dane: {text}."
            }],
        )
        out = r.choices[0].message.content.upper()
        if "BUY" in out: return "BUY"
        if "AVOID" in out: return "AVOID"
        return "WATCH"
    except:
        return "WATCH"

# ================== DANE ==================
def get_ohlc(ticker, tf):
    period = "2y" if tf == "D1" else "60d"
    interval = "1d" if tf == "D1" else "60m"
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(subset=["Open","High","Low","Close","Volume"])

def add_indicators(df):
    df = df.copy()
    close = df["Close"]

    for w in [20,50,100,200]:
        df[f"SMA{w}"] = close.rolling(w).mean()

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["BB_upper"] = ma20 + 2*std20
    df["BB_lower"] = ma20 - 2*std20

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    roll_up = gain.rolling(14).mean()
    roll_down = loss.rolling(14).mean()
    df["RSI14"] = 100 - (100/(1+(roll_up/(roll_down+1e-9))))

    high = df["High"]
    low = df["Low"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ],axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()
    df["VolMA20"] = df["Volume"].rolling(20).mean()

    return df

# ================== TREND ==================
def detect_trend_from_df(df):
    last = df.iloc[-1]
    c = last["Close"]
    sma50 = last.get("SMA50")
    sma200 = last.get("SMA200")

    if pd.notna(sma200):
        if c > sma200*1.01: return "bull"
        if c < sma200*0.99: return "bear"
    if pd.notna(sma50):
        if c > sma50: return "bull"
        if c < sma50: return "bear"
    return "side"

def trend_label_and_css(code):
    if code=="bull": return "Trend wzrostowy (🐂)", "trend-bull"
    if code=="bear": return "Trend spadkowy (🐻)", "trend-bear"
    return "Trend boczny (➖)", "trend-side"

def compute_trend_score(df, trend):
    last = df.iloc[-1]
    score = 0
    c = last["Close"]

    if trend=="bull": score+=30
    if c<5: score+=10

    sma50 = last.get("SMA50")
    sma200 = last.get("SMA200")
    rsi = last.get("RSI14")

    if pd.notna(sma50) and c>sma50: score+=15
    if pd.notna(sma200) and c>sma200: score+=15
    if pd.notna(sma50) and pd.notna(sma200) and sma50>sma200: score+=20
    if pd.notna(rsi) and 55<=rsi<=70: score+=10

    return score

# ================== WYKRES ==================
def plot_multichart(df, ticker):
    dfp=df.tail(60)
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.7,0.3],vertical_spacing=0.06)

    fig.add_trace(go.Candlestick(
        x=dfp.index,open=dfp["Open"],high=dfp["High"],low=dfp["Low"],close=dfp["Close"]
    ),row=1,col=1)

    if "SMA50" in dfp:
        fig.add_trace(go.Scatter(x=dfp.index,y=dfp["SMA50"],line=dict(color="cyan")),row=1,col=1)
    if "SMA200" in dfp:
        fig.add_trace(go.Scatter(x=dfp.index,y=dfp["SMA200"],line=dict(color="magenta")),row=1,col=1)

    fig.add_trace(go.Bar(x=dfp.index,y=dfp["Volume"],marker_color="orange"),row=2,col=1)

    fig.update_layout(template="plotly_dark",height=450,xaxis_rangeslider_visible=False)
    return fig
# ================== UI ==================
st.sidebar.header("Ustawienia skanera")
market = st.sidebar.selectbox("Rynek", ["USA Groszówki", "Polska Spekulacja", "Własna lista"])
tf = st.sidebar.selectbox("Interwał", ["D1", "1H"])

if market == "USA Groszówki":
    tickers_text = st.sidebar.text_area("Tickery", "SNDL, HUBC, OTLY, KAVL, MVIS")
elif market == "Polska Spekulacja":
    tickers_text = st.sidebar.text_area("Tickery", "BBD.WA, ATT.WA, COG.WA, BIO.WA")
else:
    tickers_text = st.sidebar.text_area("Tickery", "AAPL, TSLA")

tickers = [t.strip().upper() for t in tickers_text.split(",") if t.strip()]

if st.sidebar.button("Uruchom skaner i 3×AI 🚀"):
    all_rows = []
    dfs = {}
    vol_sigs = []

    prog = st.progress(0)

    for i, tk in enumerate(tickers):
        prog.progress((i + 1) / len(tickers))
        df_raw = get_ohlc(tk, tf)
        if df_raw.empty or len(df_raw) < 15:
            st.sidebar.warning(f"{tk}: brak wystarczających danych.")
            continue

        df = add_indicators(df_raw)
        trend = detect_trend_from_df(df)
        score = compute_trend_score(df, trend)
        vs = detect_volume_breakout_signals(df, tk)
        vol_sigs.extend(vs)

        last = df.iloc[-1]
        all_rows.append({
            "Ticker": tk,
            "Trend": trend,
            "Close": float(last["Close"]),
            "TrendScore": score
        })
        dfs[tk] = (df, trend, score)

    if not dfs:
        st.error("Brak przetworzonych spółek.")
        st.stop()

    mdf = pd.DataFrame(all_rows)

    # HEATMAP
    st.subheader("📊 Heatmapa rynku (TrendScore)")
    st.markdown('<div class="heatmap-container">', unsafe_allow_html=True)
    for _, r in mdf.iterrows():
        col = "#064e3b" if r["Trend"] == "bull" else "#7f1d1d" if r["Trend"] == "bear" else "#78350f"
        st.markdown(f"""
