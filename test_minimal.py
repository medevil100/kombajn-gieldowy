import streamlit as st
import yfinance as yf

st.set_page_config(page_title="TEST YF2", page_icon="📉", layout="wide")
st.title("📉 TEST YFINANCE — WERSJA DZIAŁAJĄCA")

ticker = "STX.WA"
st.write("Pobieram dane dla:", ticker)

df = yf.download(
    ticker,
    period="6mo",
    interval="1d",
    auto_adjust=True,
    threads=False,
    group_by="ticker"
)

if df.empty:
    st.error("❌ yfinance nadal zwraca pusty dataframe")
else:
    st.success("✔ yfinance działa poprawnie")
    st.dataframe(df.tail(5))
