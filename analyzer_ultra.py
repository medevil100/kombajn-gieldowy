import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

# Inicjalizacja klienta
client = OpenAI()

BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="Terminal Tradingowy", layout="wide")

# ==========================================
#  GLOBALNY STYL I LOGIKA DANYCH
# ==========================================
def inject_global_css():
    st.markdown(f"""
        <style>
        .stApp {{ background-color: {BACKGROUND}; }}
        html, body, [class*="css"] {{ color: {NEON_YELLOW} !important; }}
        .stButton>button {{ background-color: #111; color: {NEON_BLUE}; border: 1px solid {NEON_BLUE}; border-radius: 6px; }}
        input, select, textarea {{ background-color: #111 !important; color: {NEON_GREEN} !important; border: 1px solid {NEON_GREEN} !important; }}
        section[data-testid="stSidebar"] {{ background-color: #0a0a0a !important; border-right: 2px solid {NEON_BLUE} !important; }}
        </style>
        """, unsafe_allow_html=True)

def get_price_data(symbol, period, interval, live=False):
    if not symbol: return pd.DataFrame()
    # Naprawa błędu MultiIndex w yfinance
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty: return pd.DataFrame()
    
    # Jeśli yfinance zwróci MultiIndex (np. ['Close', 'AAPL']), bierzemy tylko pierwszy poziom
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # Konwersja na float, aby uniknąć błędów w obliczeniach
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    return df.dropna()

# ==========================================
#  WSKAŹNIKI TECHNICZNE
# ==========================================
def sma(series, length): return series.rolling(length).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger(series, length=20, num_std=2):
    ma = series.rolling(length).mean()
    std = series.rolling(length).std()
    return ma, ma + num_std * std, ma - num_std * std

def atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def fibonacci_levels(df):
    h, l = df["High"].max(), df["Low"].min()
    diff = h - l
    return {"0%": h, "23.6%": h - diff * 0.236, "38.2%": h - diff * 0.382, "50%": h - diff * 0.5, "61.8%": h - diff * 0.618, "100%": l}

def detect_trend(series):
    if len(series) < 10: return "NEUTRAL"
    return "BULL" if series.iloc[-1] > series.iloc[-10] else "BEAR"

def detect_multi_trend(df):
    c = df["Close"]
    return {
        "short_term": detect_trend(c[-20:]),
        "medium_term": detect_trend(c[-50:]),
        "long_term": detect_trend(c[-200:]),
        "momentum": float(c.diff().iloc[-1]) if len(c)>1 else 0,
        "strength": abs(float(c.diff().iloc[-1])) if len(c)>1 else 0
    }

def calculate_sl_tp(df, atr_val, trend):
    last_c = float(df["Close"].iloc[-1])
    sl = last_c - (atr_val * 2) if trend == "BULL" else last_c + (atr_val * 2)
    tp = last_c + (atr_val * 4) if trend == "BULL" else last_c - (atr_val * 4)
    return {"close": last_c, "sl": sl, "tp": tp, "risk": "MEDIUM", "neutral": last_c}

# ==========================================
#  MODUŁY WIDOKU
# ==========================================
def sidebar():
    st.sidebar.title("⚙️ Ustawienia")
    sym = st.sidebar.text_input("Podaj symbol:", value="AAPL").upper()
    period = st.sidebar.selectbox("Zakres:", ["1mo", "3mo", "1y", "5y"], index=0)
    interval = st.sidebar.selectbox("Interwał:", ["1h", "1d"], index=1)
    
    return {
        "symbol": sym, "history_period": period, "interval": interval,
        "show_sma": st.sidebar.checkbox("SMA", True),
        "show_rsi": st.sidebar.checkbox("RSI", True),
        "show_boll": st.sidebar.checkbox("Bollinger", True),
        "show_atr": st.sidebar.checkbox("ATR", True),
        "show_fibo": st.sidebar.checkbox("Fibonacci", True),
        "ai_model": st.sidebar.selectbox("Model AI:", ["gpt-4o", "gpt-4o-mini"], index=0),
        "live_data": False
    }

def main():
    inject_global_css()
    conf = sidebar()
    
    if not conf["symbol"]:
        st.info("Wpisz symbol w sidebarze.")
        return

    df = get_price_data(conf["symbol"], conf["history_period"], conf["interval"])
    
    if df.empty:
        st.error("Brak danych.")
        return

    # GŁÓWNY WYKRES
    st.subheader(f"📈 Wykres {conf['symbol']}")
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Cena")])
    
    if conf["show_sma"]:
        fig.add_trace(go.Scatter(x=df.index, y=sma(df["Close"], 20), name="SMA20", line=dict(color=NEON_PINK)))
    
    if conf["show_boll"]:
        ma, upper, lower = bollinger(df["Close"])
        fig.add_trace(go.Scatter(x=df.index, y=upper, name="Boll Upper", line=dict(dash='dash', color='gray')))
        fig.add_trace(go.Scatter(x=df.index, y=lower, name="Boll Lower", line=dict(dash='dash', color='gray')))

    fig.update_layout(template="plotly_dark", height=600)
    st.plotly_chart(fig, use_container_width=True)

    # DODATKOWE WSKAŹNIKI
    c1, c2 = st.columns(2)
    with c1:
        if conf["show_rsi"]:
            st.write("RSI (14)")
            st.line_chart(rsi(df["Close"]))
        if conf["show_fibo"]:
            st.write("Poziomy Fibonacciego", fibonacci_levels(df))
    
    with c2:
        if conf["show_atr"]:
            st.write("ATR")
            st.line_chart(atr(df))
        
        trends = detect_multi_trend(df)
        st.write("Trendy:", trends)

    # SL / TP
    st.divider()
    atr_val = atr(df).iloc[-1]
    trend_val = detect_trend(df["Close"])
    levels = calculate_sl_tp(df, atr_val, trend_val)
    st.subheader("🎯 Poziomy SL/TP")
    st.write(levels)

    # AI CHAT
    st.divider()
    st.subheader("💬 AI Trading Assistant")
    if "messages" not in st.session_state: st.session_state.messages = []
    
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("Zadaj pytanie o wykres..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        response = client.chat.completions.create(
            model=conf["ai_model"],
            messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        )
        msg = response.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": msg})
        with st.chat_message("assistant"): st.markdown(msg)

if __name__ == "__main__":
    main()
