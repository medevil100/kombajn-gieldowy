import streamlit as st
import yfinance as yf

st.set_page_config(page_title="TEST YF", page_icon="📉", layout="wide")
st.title("📉 TEST YFINANCE")

ticker = "STX.WA"
st.write("Pobieram dane dla:", ticker)

df = yf.download(ticker, period="1mo", interval="1d", progress=False)

if df.empty:
    st.error("❌ yfinance zwrócił pusty dataframe")
else:
    st.success("✔ yfinance działa")
    st.dataframe(df.tail(5))
