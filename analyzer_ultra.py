import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh # Wymaga pip install streamlit-autorefresh

# Inicjalizacja OpenAI
client = OpenAI()

BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="Terminal Tradingowy", layout="wide")

# AUTOMATYCZNE ODŚWIEŻANIE CO 5 MINUT (5 * 60 * 1000 ms)
st_autorefresh(interval=5 * 60 * 1000, key="datarefresh")

def inject_global_css():
    st.markdown(f"""
        <style>
        .stApp {{ background-color: {BACKGROUND}; }}
        html, body, [class*="css"]  {{ color: {NEON_YELLOW} !important; }}
        .stButton>button {{ background-color: #111; color: {NEON_BLUE}; border: 1px solid {NEON_BLUE}; border-radius: 6px; }}
        input, select, textarea {{ background-color: #111 !important; color: {NEON_GREEN} !important; border: 1px solid {NEON_GREEN} !important; }}
        section[data-testid="stSidebar"] {{ background-color: #0a0a0a !important; border-right: 2px solid {NEON_BLUE} !important; }}
        </style>
        """, unsafe_allow_html=True)

# ==========================================
#  NAPRAWIONA LOGIKA DANYCH (Błąd MultiIndex)
# ==========================================
def _to_scalar(x):
    if hasattr(x, "item"): return x.item()
    return x

def get_price_data(symbol, period, interval, live=False):
    if not symbol: return pd.DataFrame()
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty: return pd.DataFrame()
    
    # Rozwiązanie błędu MultiIndex i wymiarowości
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    for col in df.columns:
        df[col] = df[col].apply(_to_scalar)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna()

# ==========================================
#  TWOJE WSKAŹNIKI I ANALIZA
# ==========================================
def sma(series, length): return series.rolling(length).mean()
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))

def bollinger(series, length=20, num_std=2):
    ma = series.rolling(length).mean()
    std = series.rolling(length).std()
    return ma, ma + num_std * std, ma - num_std * std

def atr(df, period=14):
    tr = pd.concat([(df["High"]-df["Low"]), (df["High"]-df["Close"].shift()).abs(), (df["Low"]-df["Close"].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def fibonacci_levels(df):
    h, l = df["High"].max(), df["Low"].min()
    diff = h - l
    return {"0%": h, "23.6%": h-diff*0.236, "38.2%": h-diff*0.382, "50%": h-diff*0.5, "61.8%": h-diff*0.618, "100%": l}

def detect_trend(series):
    s = series.dropna()
    if len(s) < 10: return "NEUTRAL"
    return "BULL" if s.iloc[-1] > s.iloc[-10] else "BEAR"

def detect_multi_trend(df):
    c = df["Close"]
    return {
        "short_term": detect_trend(c[-20:]), "medium_term": detect_trend(c[-50:]),
        "long_term": detect_trend(c[-200:]), "momentum": float(c.diff().iloc[-1]) if len(c)>1 else 0,
        "strength": abs(float(c.diff().iloc[-1])) if len(c)>1 else 0
    }

def get_bid_ask(symbol):
    try:
        t = yf.Ticker(symbol); info = t.fast_info
        p = info.get("last_price", 0)
        return p, p*1.001, 0.001
    except: return 0, 0, 0

def calculate_sl_tp(df, atr_val, trend):
    last_c = float(df["Close"].iloc[-1])
    sl = last_c - (atr_val * 2) if trend == "BULL" else last_c + (atr_val * 2)
    tp = last_c + (atr_val * 4) if trend == "BULL" else last_c - (atr_val * 4)
    return {"close": last_c, "sl": sl, "tp": tp, "risk": "MEDIUM", "neutral": last_c}

def position_risk(price, atr_val, spread, qty, sl):
    pos_val = price * qty
    total_risk = abs(price - sl) * qty
    risk_pct = (total_risk/pos_val)*100 if pos_val != 0 else 0
    return {"position_value": pos_val, "total_risk": total_risk, "risk_%": f"{risk_pct:.2f}%"}

# ==========================================
#  WIDOKI OKIENKOWE (Zgodne z Twoim skryptem)
# ==========================================
def sidebar():
    st.sidebar.title("⚙️ Konfiguracja")
    symbol = st.sidebar.text_input("Symbol główny:", "AAPL").upper()
    period = st.sidebar.selectbox("Zakres:", ["1mo", "3mo", "1y", "5y"])
    interval = st.sidebar.selectbox("Interwał:", ["5m", "15m", "1h", "1d"])
    
    # WYBÓR 1 Z 4 MODELI AI
    ai_model = st.sidebar.selectbox(
        "Model AI:",
        ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview"],
        index=0
    )

    return {
        "symbol": symbol, "history_period": period, "interval": interval, "ai_model": ai_model,
        "show_sma": st.sidebar.checkbox("Wskaźnik SMA", True),
        "show_rsi": st.sidebar.checkbox("Wskaźnik RSI", True),
        "show_boll": st.sidebar.checkbox("Wstęgi Bollingera", True),
        "show_atr": st.sidebar.checkbox("Wskaźnik ATR", True),
        "show_fibo": st.sidebar.checkbox("Poziomy Fibonacci", True),
        "show_scanner": st.sidebar.checkbox("📡 Skaner", True),
        "show_ai_chat": st.sidebar.checkbox("💬 AI Czat", True),
        "show_sl_tp": st.sidebar.checkbox("🎯 Poziomy SL/TP", True),
        "show_portfolio": st.sidebar.checkbox("💼 Portfel", True)
    }

def main():
    inject_global_css()
    conf = sidebar()
    if not conf["symbol"]: return

    df = get_price_data(conf["symbol"], conf["history_period"], conf["interval"])
    if df.empty:
        st.warning("Oczekiwanie na dane...")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        # Wykres główny
        st.subheader(f"📈 {conf['symbol']} - Interwał {conf['interval']}")
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=600, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

        # Dodatkowe wskaźniki pod wykresem
        if conf["show_rsi"]:
            st.write("Relative Strength Index (RSI)")
            st.line_chart(rsi(df["Close"]))
        
        if conf["show_sl_tp"]:
            st.divider()
            atr_v = atr(df).iloc[-1]
            tr = detect_trend(df["Close"])
            st.subheader("🎯 Kalkulacja SL / TP")
            st.json(calculate_sl_tp(df, atr_v, tr))

    with col2:
        if conf["show_ai_chat"]:
            st.subheader("💬 AI Trading Assistant")
            if "messages" not in st.session_state: st.session_state.messages = []
            for m in st.session_state.messages: st.write(f"**{m['role']}**: {m['content']}")
            if p := st.chat_input("Pytaj o strategię..."):
                st.session_state.messages.append({"role": "user", "content": p})
                res = client.chat.completions.create(model=conf["ai_model"], messages=st.session_state.messages)
                st.session_state.messages.append({"role": "assistant", "content": res.choices.message.content})
                st.rerun()

        if conf["show_scanner"]:
            st.divider()
            st.subheader("📡 Skaner Sektorowy")
            if "scan_list" not in st.session_state: st.session_state.scan_list = ["AAPL", "TSLA", "BTC-USD"]
            for s in st.session_state.scan_list:
                sd = get_price_data(s, "5d", "1h")
                if not sd.empty:
                    st.write(f"**{s}**: {sd['Close'].iloc[-1]:.2f} ({detect_trend(sd['Close'])})")

if __name__ == "__main__":
    main()
