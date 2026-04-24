import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="RESET KOMBAJN", layout="wide")

# Silnik z filtrem na dzisiejszy błąd Yahoo
def get_data(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="1h")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except: return None

st.title("🚜 KOMBAJN - TWARDY RESET")
symbol = st.sidebar.text_input("Symbol", "BTC-USD")
st_autorefresh(interval=30000, key="fsh")

data = get_data(symbol)
if data is not None and not data.empty:
    st.metric("CENA", f"{data['Close'].iloc[-1]:.2f}")
    fig = go.Figure(data=[go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'])])
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Błąd pobierania danych. Sprawdź symbol.")
