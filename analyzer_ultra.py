import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI

# Inicjalizacja klienta OpenAI (wymaga klucza w zmiennych środowiskowych)
client = OpenAI()

BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="Terminal Tradingowy", layout="wide")

# ==========================================
#  FUNKCJE POMOCNICZE I OBLICZENIA (z części 1)
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

def _to_scalar(x):
    if isinstance(x, (list, tuple)): return x[0]
    if hasattr(x, "item"): 
        try: return x.item()
        except: return x
    return x

def get_price_data(symbol, period, interval, live=False):
    if not symbol: return pd.DataFrame()
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty: return pd.DataFrame()
    for col in df.columns:
        df[col] = df[col].apply(_to_scalar)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna()

def sma(series, length): return series.rolling(length).mean()

def rsi(series, period=14):
    s = pd.to_numeric(pd.Series(series), errors="coerce")
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger(series, length=20, num_std=2):
    s = pd.to_numeric(pd.Series(series), errors="coerce")
    ma = s.rolling(length).mean()
    std = s.rolling(length).std()
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
    s = pd.to_numeric(pd.Series(series), errors="coerce").dropna()
    if len(s) < 10: return "NEUTRAL"
    return "BULL" if s.iloc[-1] > s.iloc[-10] else "BEAR"

def detect_multi_trend(df):
    close = df["Close"]
    return {
        "short_term": detect_trend(close[-20:]),
        "medium_term": detect_trend(close[-50:]),
        "long_term": detect_trend(close[-200:]),
        "momentum": float(close.diff().iloc[-1]) if len(close)>1 else 0,
        "strength": abs(float(close.diff().iloc[-1])) if len(close)>1 else 0
    }

def get_bid_ask(symbol):
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        return info.get("last_price", 0), info.get("last_price", 0) * 1.001, 0.01
    except: return None, None, None

# ==========================================
#  NOWE FUNKCJE (NAPRAWA BRAKÓW Z CZĘŚCI 2)
# ==========================================
def calculate_sl_tp(df, atr_val, trend):
    last_c = float(df["Close"].iloc[-1])
    if trend == "BULL":
        sl, tp = last_c - (atr_val * 2), last_c + (atr_val * 4)
    else:
        sl, tp = last_c + (atr_val * 2), last_c - (atr_val * 4)
    return {"close": last_c, "sl": sl, "tp": tp, "neutral": last_c, "risk": "MEDIUM"}

def position_risk(price, atr_val, spread, qty, sl):
    pos_val = price * qty
    risk_per_share = abs(price - sl)
    total_risk = risk_per_share * qty
    risk_pct = (total_risk / pos_val) * 100 if pos_val != 0 else 0
    return {"position_value": pos_val, "risk_per_share": risk_per_share, "total_risk": total_risk, "risk_percent": risk_pct, "level": "HIGH" if risk_pct > 2 else "LOW"}

# ==========================================
#  WIDOKI (Z CZĘŚCI 2)
# ==========================================
def show_price_chart(df, symbol):
    st.subheader(f"📈 Wykres — {symbol}")
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
    fig.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

def charts_window(symbol, settings):
    df = get_price_data(symbol, settings["history_period"], settings["interval"])
    if df.empty: return st.error("Brak danych.")
    show_price_chart(df, symbol)
    if settings["show_sma"]: st.line_chart(sma(df["Close"], 20))
    if settings["show_rsi"]: st.line_chart(rsi(df["Close"]))
    if settings["show_fibo"]: 
        levels = fibonacci_levels(df)
        st.write("Fibo:", levels)

def scanner_window(settings):
    st.subheader("📡 Skaner")
    if "symbols_list" not in st.session_state: st.session_state.symbols_list = ["AAPL", "TSLA", "BTC-USD"]
    
    new_sym = st.text_input("Dodaj symbol:")
    if st.button("➕ Dodaj"):
        if new_sym and new_sym.upper() not in st.session_state.symbols_list:
            st.session_state.symbols_list.append(new_sym.upper())
            st.rerun()

    for sym in st.session_state.symbols_list:
        df = get_price_data(sym, "1mo", "1d")
        if not df.empty:
            st.write(f"**{sym}**: {df['Close'].iloc[-1]:.2f} | Trend: {detect_trend(df['Close'])}")

def ai_chat_window(settings):
    st.subheader("💬 AI Czat")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    
    user_msg = st.chat_input("Zapytaj AI o rynek...")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        # Tutaj następuje wywołanie OpenAI
        response = client.chat.completions.create(
            model=settings["ai_model"] if settings["ai_model"] != "gpt-4.1" else "gpt-4o",
            messages=st.session_state.chat_history
        )
        st.session_state.chat_history.append({"role": "assistant", "content": response.choices[0].message.content})

    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]): st.write(m["content"])

def portfolio_window():
    st.subheader("💼 Portfel")
    if "portfolio" not in st.session_state: st.session_state.portfolio = {}
    
    with st.form("add_pos"):
        s = st.text_input("Symbol").upper()
        q = st.number_input("Ilość", min_value=0.0)
        if st.form_submit_button("Dodaj do portfela"):
            st.session_state.portfolio[s] = st.session_state.portfolio.get(s, 0) + q
            st.rerun()
    
    st.write(st.session_state.portfolio)

# ==========================================
#  MAIN APP
# ==========================================
def sidebar():
    st.sidebar.title("⚙️ Ustawienia")
    symbol = st.sidebar.text_input("Symbol", value="AAPL").upper()
    period = st.sidebar.selectbox("Zakres", ["1mo", "3mo", "1y"])
    interval = st.sidebar.selectbox("Interwał", ["1h", "1d"])
    ai_model = st.sidebar.selectbox("Model AI", ["gpt-4o-mini", "gpt-4o"])
    
    return {
        "symbol": symbol, "history_period": period, "interval": interval, "ai_model": ai_model,
        "show_sma": st.sidebar.checkbox("SMA", True), "show_rsi": st.sidebar.checkbox("RSI", True),
        "show_boll": True, "show_atr": True, "show_fibo": True, "live_data": False,
        "show_scanner": st.sidebar.checkbox("Skaner", True),
        "show_ai_chat": st.sidebar.checkbox("Czat AI", True),
        "show_portfolio": st.sidebar.checkbox("Portfel", True)
    }

def main():
    inject_global_css()
    settings = sidebar()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if settings["symbol"]:
            charts_window(settings["symbol"], settings)
    
    with col2:
        if settings["show_ai_chat"]: ai_chat_window(settings)
        if settings["show_scanner"]: scanner_window(settings)
        if settings["show_portfolio"]: portfolio_window()

if __name__ == "__main__":
    main()
