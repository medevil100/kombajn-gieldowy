import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# Inicjalizacja OpenAI - Streamlit Cloud pobierze klucz z "Secrets"
# Jeśli uruchamiasz lokalnie, upewnij się, że masz klucz w systemie
client = OpenAI()

# Kolory Terminala
BACKGROUND = "#000000"
NEON_GREEN = "#39FF14"
NEON_PINK = "#FF1493"
NEON_BLUE = "#00FFFF"
NEON_YELLOW = "#F5FF00"

st.set_page_config(page_title="Terminal Tradingowy", layout="wide")

# Odświeżanie co 5 minut
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

# --- Logika Danych ---
def get_price_data(symbol, period, interval):
    if not symbol: return pd.DataFrame()
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty: return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.astype(float).dropna()

# --- Naprawione Wskaźniki ---
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean().abs()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    tr = pd.concat([
        (df["High"] - df["Low"]), 
        (df["High"] - df["Close"].shift()).abs(), 
        (df["Low"] - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# --- UI GŁÓWNE ---
def main():
    inject_global_css()
    
    st.sidebar.title("⚙️ Terminal")
    sym = st.sidebar.text_input("Symbol:", "AAPL").upper()
    range_p = st.sidebar.selectbox("Zakres:", ["1mo", "3mo", "1y", "5y"], index=0)
    tf = st.sidebar.selectbox("Interwał:", ["5m", "15m", "1h", "1d"], index=2)
    
    # 4 Modele AI do wyboru
    ai_mod = st.sidebar.selectbox("Model AI:", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview"])
    
    st.sidebar.markdown("---")
    show_rsi = st.sidebar.checkbox("RSI (14)", True)
    show_atr = st.sidebar.checkbox("ATR (14)", True)
    show_scanner = st.sidebar.checkbox("Skaner", True)

    df = get_price_data(sym, range_p, tf)
    if df.empty:
        st.info("Podaj poprawny symbol, aby załadować dane.")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader(f"📈 Wykres {sym}")
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0,r=0,t=20,b=0))
        st.plotly_chart(fig, use_container_width=True)

        if show_rsi:
            st.write("📊 RSI")
            st.line_chart(rsi(df["Close"]).dropna())
        
        if show_atr:
            st.write("📊 ATR")
            st.line_chart(atr(df).dropna())

    with col2:
        st.subheader("💬 AI Assistant")
        if "chat" not in st.session_state: st.session_state.chat = []
        
        for m in st.session_state.chat:
            with st.chat_message(m["role"]): st.write(m["content"])
            
        if p := st.chat_input("Pytaj AI..."):
            st.session_state.chat.append({"role": "user", "content": p})
            res = client.chat.completions.create(
                model=ai_mod,
                messages=[{"role": "system", "content": "Jesteś ekspertem giełdowym."}] + st.session_state.chat
            )
            st.session_state.chat.append({"role": "assistant", "content": res.choices.message.content})
            st.rerun()

        if show_scanner:
            st.divider()
            st.subheader("📡 Skaner (Podgląd)")
            for s in ["BTC-USD", "TSLA", "NVDA"]:
                d = get_price_data(s, "1d", "1h")
                if not d.empty:
                    st.write(f"**{s}**: {d['Close'].iloc[-1]:.2f}")

if __name__ == "__main__":
    main()
