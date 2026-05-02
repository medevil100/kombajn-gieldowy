import streamlit as st
import yfinance as yf
from analyzer_ultra import analyze_ultra
import json
import os

# =========================
# KONFIGURACJA
# =========================
st.set_page_config(page_title="NEON KOMBAJN ULTRA", layout="wide")

EAI_KEY = os.getenv("EAI_KEY")  # klucz w secret

st.markdown("""
<style>
body { background-color: #050510; color: #e0e0ff; }
.block {
    background: #0a0a18;
    padding: 20px;
    margin-bottom: 25px;
    border-radius: 12px;
    border: 1px solid #222;
    box-shadow: 0 0 12px #00eaff33;
}
.title {
    font-size: 26px;
    font-weight: bold;
    color: #00eaff;
}
.section {
    font-size: 18px;
    margin-top: 12px;
    color: #9ad7ff;
}
.value {
    font-size: 18px;
    font-weight: bold;
    color: #ffffff;
}
.ai-block {
    background: #111122;
    padding: 15px;
    border-radius: 10px;
    margin-top: 10px;
    border: 1px solid #333;
}
</style>
""", unsafe_allow_html=True)

# =========================
# INPUT SPÓŁEK
# =========================
symbols_input = st.text_input(
    "Wpisz spółki oddzielone przecinkami:",
    "AAPL, MSFT, TSLA, NVDA"
)

symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

# =========================
# FUNKCJA POBIERANIA DANYCH
# =========================
def load_candles(symbol):
    data = yf.download(symbol, period="6mo", interval="1d")
    data = data.dropna()
    candles = []
    for idx, row in data.iterrows():
        candles.append({
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"])
        })
    return candles

# =========================
# ANALIZA PER SPÓŁKA
# =========================
for symbol in symbols:

    st.markdown(f"<div class='block'><div class='title'>{symbol}</div>", unsafe_allow_html=True)

    try:
        candles = load_candles(symbol)
        ultra = analyze_ultra(symbol, candles)
    except Exception as e:
        st.error(f"❌ Błąd pobierania danych dla {symbol}: {e}")
        continue

    # =========================
    # BLOK ANALITYCZNY
    # =========================
    st.markdown("<div class='section'>Kurs:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.last:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Trend:</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='value'>{ultra.trend.short} / {ultra.trend.mid} / {ultra.trend.long} (score: {ultra.trend.score})</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div class='section'>Momentum:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.momentum:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Zmienność:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.volatility:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>RSI14 / ATR14:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.rsi14:.2f} / {ultra.atr14:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>MACD:</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='value'>{ultra.macd:.2f} | sygnał: {ultra.macd_signal:.2f} | hist: {ultra.macd_hist:.2f}</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div class='section'>Wolumen relatywny:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.volume_rel:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Breakout score:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.breakout_score:.2f}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Pivot P / R1 / S1:</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='value'>{ultra.pivot.P:.2f} / {ultra.pivot.R1:.2f} / {ultra.pivot.S1:.2f}</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div class='section'>TP / SL:</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='value'>{ultra.tpsl.tp:.2f} / {ultra.tpsl.sl:.2f}</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div class='section'>Presja rynku:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.pressure}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Formacja świecowa:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.candle_pattern}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Formacja techniczna:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.formation}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Dywergencja:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.divergence}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Setup:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.setup}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Ryzyko:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.risk}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section'>Sygnał końcowy:</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='value'>{ultra.signal}</div>", unsafe_allow_html=True)

    # =========================
    # AI ANALIZA — TYLKO NA KLIK
    # =========================
    if st.button(f"🤖 Analiza AI dla {symbol}", key=f"ai_{symbol}"):

        payload = {
            "symbol": symbol,
            "analysis": ultra.__dict__,
        }

        st.markdown("<div class='ai-block'>", unsafe_allow_html=True)
        st.markdown("🔍 **AI analiza wygenerowana:**")
        st.json(payload)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

