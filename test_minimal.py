import streamlit as st
import yfinance as yf

st.set_page_config(page_title="TEST KOLUMN", page_icon="📊", layout="wide")
st.title("📊 TEST KOLUMN YFINANCE")

ticker = st.text_input("Ticker:", "STX.WA")

if st.button("POBIERZ"):
    df = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        auto_adjust=True,
        threads=False,
        group_by="ticker",
        progress=False
    )

    st.write("🔍 Kolumny:")
    st.write(df.columns)

    st.write("📈 Podgląd:")
    st.dataframe(df.tail(5))
