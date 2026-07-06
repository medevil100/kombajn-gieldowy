import streamlit as st
import yfinance as yf
import pandas as pd
import traceback
from datetime import datetime
import matplotlib.pyplot as plt
import base64
from io import BytesIO

# =====================================================================
# CONFIG
# =====================================================================
st.set_page_config(page_title="KOMBAJN PRO", page_icon="📈", layout="wide")
st.title("📈 KOMBAJN PRO — działająca wersja z poprawionymi kolumnami")

def show_error(e):
    st.error(f"❌ Błąd: {e}")
    st.code(traceback.format_exc())

# =====================================================================
# Pobieranie danych — KLUCZOWA POPRAWKA: usuwanie prefiksów
# =====================================================================
def pobierz_df(ticker):
    df = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        auto_adjust=True,
        threads=False,
        group_by="ticker",
        progress=False
    )

    if df.empty:
        raise ValueError(f"Brak danych dla {ticker}")

    # Jeśli MultiIndex → spłaszczamy
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # KLUCZ: usuwamy wszystko przed spacją → zostaje "Open", "Close", "Volume"
    df.columns = [col.split(" ")[-1] for col in df.columns]

    return df

# =====================================================================
# Mini wykres
# =====================================================================
def mini_chart(df):
    try:
        df = df.tail(20)

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(1.6, 1.0),
            gridspec_kw={"height_ratios": [3, 1]},
            dpi=75
        )

        for i, row in enumerate(df.itertuples()):
            o, h, l, c = row.Open, row.High, row.Low, row.Close
            color = "#00ff00" if c >= o else "#ff0000"
            ax1.vlines(i, l, h, color=color, linewidth=0.8)
            ax1.vlines(i, o, c, color=color, linewidth=2)

        ax1.set_xticks([]); ax1.set_yticks([]); ax1.set_facecolor("#000000")
        ax2.bar(range(len(df)), df["Volume"], color="#666666", width=0.6)
        ax2.set_xticks([]); ax2.set_yticks([]); ax2.set_facecolor("#000000")

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
        fig.clf(); plt.close(fig)

        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        show_error(e)
        return ""

# =====================================================================
# Analiza spółki — teraz działa
# =====================================================================
def analizuj(ticker):
    try:
        df = pobierz_df(ticker)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        cena = float(last["Close"])
        zmiana = ((last["Close"] - prev["Close"]) / prev["Close"]) * 100
        wolumen_x = float(last["Volume"]) / df["Volume"].mean()

        chart = mini_chart(df)

        return {
            "Ticker": ticker,
            "Cena": cena,
            "Zmiana %": zmiana,
            "Wolumen x": wolumen_x,
            "MiniWykres": chart
        }
    except Exception as e:
        show_error(e)
        return None

# =====================================================================
# UI
# =====================================================================
user_input = st.text_area("Wklej swoje spółki:", "APS.WA, STX.WA, AIT.WA")
MARKET_DATABASE = [t.strip() for t in user_input.replace("\n", ",").split(",") if t.strip()]

if st.button("🚀 SKANUJ TERAZ"):
    wyniki = []
    for t in MARKET_DATABASE:
        res = analizuj(t)
        if res:
            wyniki.append(res)
    st.session_state.scanned_details = wyniki
    st.session_state.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

st.write("---")
st.write(f"📅 Ostatni skan: {st.session_state.last_scan_time}")

if "scanned_details" in st.session_state and st.session_state.scanned_details:
    df = pd.DataFrame(st.session_state.scanned_details)
    df["MiniWykres"] = df["MiniWykres"].apply(
        lambda x: f'<img src="data:image/png;base64,{x}" width="120" height="80"/>' if x else "Brak"
    )
    st.markdown(df.to_html(escape=False), unsafe_allow_html=True)
else:
    st.info("Brak danych — kliknij SKANUJ TERAZ.")
