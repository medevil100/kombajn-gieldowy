import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="AI KOMBAJN v20.0", layout="wide")

st.markdown("""<style>.stApp { background-color: #0d1117; color: #c9d1d9; }
.ticker-card { background: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 30px; }</style>""", unsafe_allow_html=True)

def pobierz_dane(symbol):
    try:
        t = yf.Ticker(symbol)
        h1 = t.history(period="10d", interval="1h")
        d1 = t.history(period="5d", interval="1d")
        if h1.empty or d1.empty: return None
        if isinstance(h1.columns, pd.MultiIndex): h1.columns = h1.columns.get_level_values(0)
        
        cena = h1['Close'].iloc[-1]
        cp = d1['Close'].iloc[-2]
        
        # Pivot i ATR (TP/SL)
        hp, lp, clp = d1['High'].iloc[-2], d1['Low'].iloc[-2], d1['Close'].iloc[-2]
        pp = (hp + lp + clp) / 3
        atr = (d1['High'] - d1['Low']).rolling(5).mean().iloc[-1]
        
        return {
            "symbol": symbol, "price": cena, "df": h1, 
            "change": ((cena - cp) / cp * 100), "pp": pp,
            "tp": cena + (atr * 1.5), "sl": cena - (atr * 1.2)
        }
    except: return None

# --- 2. INTERFEJS ---
st.sidebar.title("🚜 KOMBAJN v20.0")
klucz = st.sidebar.text_input("OpenAI Key", type="password") or st.secrets.get("OPENAI_API_KEY")
symbole_raw = st.sidebar.text_area("Symbole", "PKO.WA, BTC-USD, NVDA")
st_autorefresh(interval=60000, key="refresh_v20")

lista = [s.strip().upper() for s in symbole_raw.split(",") if s.strip()]

for s in lista:
    d = pobierz_dane(s)
    if d:
        with st.container():
            st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1.2])
            with col1:
                st.subheader(d['symbol'])
                st.metric("CENA", f"{d['price']:.2f}", f"{d['change']:.2f}%")
                st.write(f"**B/A:** {d['price']*0.999:.2f}/{d['price']*1.001:.2f}")
                st.write(f"**Pivot:** {d['pp']:.2f}")
                st.write(f"**TP:** {d['tp']:.2f} | **SL:** {d['sl']:.2f}")
            with col2:
                fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True, key=f"ch_{d['symbol']}")
            with col3:
                if klucz and st.button(f"MÓZG AI {d['symbol']}", key=f"btn_{d['symbol']}"):
                    client = OpenAI(api_key=klucz)
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": f"Oceń {d['symbol']}, cena {d['price']}"}]
                    )
                    st.info(response.choices[0].message.content)
            st.markdown('</div>', unsafe_allow_html=True)
