import streamlit as st
import pandas as pd
import yfinance as yf
import time
import requests
from datetime import datetime
from plotly.subplots import make_subplots
import plotly.graph_objects as go

# =====================================================================
# LISTY GPW + USA
# =====================================================================

GPW_LIST = [
    "APS.WA","STX.WA","AIT.WA","CLD.WA","NVS.WA","PTN.WA","IFR.WA","KCH.WA","ENG.WA",
    "MDF.WA","BIM.WA","BML.WA","VVD.WA","MIR.WA","QNT.WA","MGT.WA","SYN.WA","OAT.WA","IGN.WA",
    "GT.WA","BIO.WA","PHR.WA","PURE.WA","MAB.WA","VIV.WA","ULT.WA","HUG.WA","TEN.WA","RDS.WA",
    "MOV.WA","FOR.WA","PCF.WA","CIG.WA","BBT.WA","RFK.WA","PXM.WA","MSW.WA","ZRE.WA","TRK.WA"
]

USA_LIST = [
    "PLRX","HUMA","FATE","TCRX","IOVA","MREO","GOSS","SNTI","VINC","ACRS",
    "SLS","TTWOQ","ATNXQ","MNTS","BBIG","NBY","AEMD","XELA","COMS","HC"
]

MARKET_DATABASE = GPW_LIST + USA_LIST

# =====================================================================
# WSKAŹNIKI: RSI, MACD, Bollinger
# =====================================================================

def oblicz_rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def oblicz_macd(df):
    df["EMA12"] = df["Close"].ewm(span=12).mean()
    df["EMA26"] = df["Close"].ewm(span=26).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["Signal"] = df["MACD"].ewm(span=9).mean()
    return df

def oblicz_bollinger(df, period=20, std_mult=2):
    df["BB_MID"] = df["Close"].rolling(period).mean()
    df["BB_STD"] = df["Close"].rolling(period).std()
    df["BB_UP"] = df["BB_MID"] + std_mult * df["BB_STD"]
    df["BB_DOWN"] = df["BB_MID"] - std_mult * df["BB_STD"]
    return df

# =====================================================================
# NEWS + pseudo-AI sentyment
# =====================================================================

def pobierz_newsy(ticker):
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={ticker}"
    try:
        r = requests.get(url, timeout=5).json()
        return r.get("news", [])[:5]
    except:
        return []

def ocen_news_ai(news_list):
    if not news_list:
        return "Brak newsów", "neutralny"

    tekst = " ".join([n.get("title","") for n in news_list]).lower()

    pozytywne = ["growth","beat","strong","upgrade","profit","record","buyback"]
    negatywne = ["loss","downgrade","fraud","bankruptcy","drop","weak","selloff"]

    score = 0
    for p in pozytywne:
        if p in tekst:
            score += 1
    for n in negatywne:
        if n in tekst:
            score -= 1

    if score >= 2:
        return "🟢 Mocno pozytywne", "mocny"
    elif score == 1:
        return "🟡 Lekko pozytywne", "średni"
    elif score == 0:
        return "⚪ Neutralne", "neutralny"
    elif score == -1:
        return "🟠 Negatywne", "średni"
    else:
        return "🔴 Mocno negatywne", "mocny"

# =====================================================================
# ANALIZA SPÓŁKI
# =====================================================================

def analizuj_spolke(ticker, df):
    close = float(df["Close"].iloc[-1])

    df["RSI"] = oblicz_rsi(df)
    df = oblicz_macd(df)
    df = oblicz_bollinger(df)

    rsi = float(df["RSI"].iloc[-1])
    macd = float(df["MACD"].iloc[-1])
    signal = float(df["Signal"].iloc[-1])
    bb_up = float(df["BB_UP"].iloc[-1])
    bb_mid = float(df["BB_MID"].iloc[-1])
    bb_down = float(df["BB_DOWN"].iloc[-1])

    sl = round(close * 0.90, 2)
    tp = round(close * 1.15, 2)

    if rsi < 30 and macd > signal and close < bb_mid:
        ocena = "🟢 Kupuj"
        alert = True
    elif rsi > 70 and macd < signal and close > bb_mid:
        ocena = "🔴 Sprzedaj"
        alert = False
    else:
        ocena = "🟡 Trzymaj"
        alert = False

    news = pobierz_newsy(ticker)
    ocena_news, sila_news = ocen_news_ai(news)
    alert_news = sila_news == "mocny"

    return {
        "Ticker": ticker,
        "Cena": close,
        "RSI": rsi,
        "MACD": macd,
        "Signal": signal,
        "BB_UP": bb_up,
        "BB_MID": bb_mid,
        "BB_DOWN": bb_down,
        "SL": sl,
        "TP": tp,
        "Ocena": ocena,
        "News AI": ocena_news,
        "News Sila": sila_news,
        "Alert": alert,
        "Alert News": alert_news
    }
# =====================================================================
# TELEGRAM
# =====================================================================

TELEGRAM_BOT_TOKEN = "WPISZ_SWÓJ_TOKEN"
TELEGRAM_CHAT_ID = "WPISZ_SWÓJ_CHAT_ID"

def telegram_alerty(wyniki):
    alerty = [w for w in wyniki if w["Alert"] or w["Alert News"]]
    if not alerty:
        return

    tekst = "🟢 ALERTY GIEŁDOWE\n\n"
    for a in alerty:
        tekst += (
            f"{a['Ticker']} — {a['Ocena']}\n"
            f"Cena: {a['Cena']}\n"
            f"RSI: {a['RSI']} | MACD: {a['MACD']} | Signal: {a['Signal']}\n"
            f"Bollinger: UP {a['BB_UP']:.2f} | MID {a['BB_MID']:.2f} | DOWN {a['BB_DOWN']:.2f}\n"
            f"News: {a['News AI']} (siła: {a['News Sila']})\n\n"
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": tekst})

# =====================================================================
# JSON PACZKI
# =====================================================================

def df_to_json_batches(df, batch_size=10):
    batches = []
    for i in range(0, len(df), batch_size):
        batches.append(df.iloc[i:i+batch_size].to_dict(orient="records"))
    return batches

# =====================================================================
# SKANER
# =====================================================================

if "last_scanned_tickers" not in st.session_state:
    st.session_state.last_scanned_tickers = []

def job_skanera(status_ph, prog_bar):
    st.session_state.last_scanned_tickers = []

    total = len(MARKET_DATABASE)
    for idx, ticker in enumerate(MARKET_DATABASE, start=1):
        try:
            df = yf.download(ticker, period="90d", interval="1d", progress=False)
            if df.empty:
                continue

            wynik = analizuj_spolke(ticker, df)
            st.session_state.last_scanned_tickers.append(wynik)

        except:
            continue

        prog_bar.progress(idx / total)

    telegram_alerty(st.session_state.last_scanned_tickers)

# =====================================================================
# UI — PRZYCISKI
# =====================================================================

st.title("📈 Kombajn Giełdowy — GPW + USA + RSI/MACD/Bollinger + News AI")

col1, col2 = st.columns(2)
with col1:
    uruchom_skan = st.button("🚀 Uruchom Skaner", key="btn_skaner")
with col2:
    if st.button("🗑️ Wyczyść Historię", key="btn_clear"):
        st.session_state.last_scanned_tickers = []
        st.rerun()

status_ph = st.empty()
prog_bar = st.empty()

if uruchom_skan:
    status_ph.write("⌛ Trwa skanowanie…")
    job_skanera(status_ph, prog_bar)
    status_ph.success("Skan zakończony")

# =====================================================================
# WYNIKI — TECHNIKA
# =====================================================================

if st.session_state.last_scanned_tickers:
    st.subheader("📊 Wyniki techniczne")

    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    st.dataframe(
        df_wyniki[
            ["Ticker","Cena","RSI","MACD","Signal","BB_UP","BB_MID","BB_DOWN","SL","TP","Ocena"]
        ],
        use_container_width=True
    )

# =====================================================================
# WYNIKI — NEWS AI
# =====================================================================

if st.session_state.last_scanned_tickers:
    st.subheader("🧠 Ocena AI (news + sentyment)")

    df_ai = pd.DataFrame(st.session_state.last_scanned_tickers)[
        ["Ticker","News AI","News Sila"]
    ]
    st.dataframe(df_ai, use_container_width=True)

# =====================================================================
# JSON PACZKI
# =====================================================================

if st.session_state.last_scanned_tickers:
    st.subheader("📦 JSON — paczki po 10")

    df_all = pd.DataFrame(st.session_state.last_scanned_tickers)
    for idx, batch in enumerate(df_to_json_batches(df_all, 10), start=1):
        st.write(f"### Paczka {idx}")
        st.json(batch)
       # =====================================================================
# STAŁE TICKERY + OKNO PODGLĄDU
# =====================================================================

st.subheader("📌 Stałe tickery — szybki wybór spółki")

# Twoje listy
all_tickers = GPW_LIST + USA_LIST

# Dropdown z wyborem spółki
selected_ticker = st.selectbox("Wybierz spółkę:", all_tickers, key="selected_ticker")

if selected_ticker:
    df_s = yf.download(selected_ticker, period="30d", interval="1d", progress=False)

    if df_s is None or df_s.empty:
        st.error("Brak danych dla wybranego tickera.")
    else:
        df_s["RSI"] = oblicz_rsi(df_s)
        df_s = oblicz_macd(df_s)
        df_s = oblicz_bollinger(df_s)

        last = df_s.iloc[-1]

        # Pobieramy pojedyncze wartości
        cena_s   = float(last["Close"])
        rsi_s    = float(last["RSI"])
        macd_s   = float(last["MACD"])
        signal_s = float(last["Signal"])
        bb_up_s  = float(last["BB_UP"])
        bb_mid_s = float(last["BB_MID"])
        bb_down_s= float(last["BB_DOWN"])

        # Wyświetlamy panel
        st.markdown(f"""
        ### 🔍 Podgląd: **{selected_ticker}**
        **Cena:** {cena_s:.2f}  
        **RSI:** {rsi_s:.1f}  
        **MACD:** {macd_s:.4f}  
        **Signal:** {signal_s:.4f}  
        **Bollinger:** UP {bb_up_s:.2f} | MID {bb_mid_s:.2f} | DOWN {bb_down_s:.2f}
        """)

        # Mini-wykres
        fig2 = make_subplots(rows=3, cols=1, shared_xaxes=True)

        fig2.add_trace(go.Candlestick(
            x=df_s.index,
            open=df_s["Open"],
            high=df_s["High"],
            low=df_s["Low"],
            close=df_s["Close"]
        ), row=1, col=1)

        fig2.add_trace(go.Scatter(x=df_s.index, y=df_s["RSI"]), row=2, col=1)
        fig2.add_trace(go.Scatter(x=df_s.index, y=df_s["MACD"]), row=3, col=1)
        fig2.add_trace(go.Scatter(x=df_s.index, y=df_s["Signal"]), row=3, col=1)

        fig2.update_layout(template="plotly_dark", height=700)
        st.plotly_chart(fig2, use_container_width=True)
 
# =====================================================================
# SZYBKI PODGLĄD TICKERA — ODDZIELONY OD SKANERA I JSON
# =====================================================================

st.subheader("🔎 Szybki podgląd tickera (RSI / MACD / Bollinger / Świece)")

quick_ticker = st.text_input("Ticker:", key="quick_ticker")

if quick_ticker:

    # Pobieramy TYLKO z YF — nigdy z JSON, nigdy ze skanera
    df_q = yf.download(quick_ticker, period="10d", interval="30m", progress=False)

    if df_q is None or df_q.empty:
        st.error("Brak danych z Yahoo Finance.")
    else:

        # Wskaźniki liczone TYLKO na df_q
        df_q["RSI"] = oblicz_rsi(df_q)
        df_q = oblicz_macd(df_q)
        df_q = oblicz_bollinger(df_q)

        # Ostatni wiersz — PRAWDZIWE DANE Z YF
        ostatnia = df_q.iloc[-1]

        # DEBUG — zobaczysz dokładnie co tam jest
        st.write("DEBUG ostatnia:", ostatnia)

        # Pobieramy POJEDYNCZE wartości, nie Series
        try:
            close_val  = float(ostatnia["Close"].item())
            rsi_val    = float(ostatnia["RSI"].item())
            macd_val   = float(ostatnia["MACD"].item())
            signal_val = float(ostatnia["Signal"].item())
            bb_up      = float(ostatnia["BB_UP"].item())
            bb_mid     = float(ostatnia["BB_MID"].item())
            bb_down    = float(ostatnia["BB_DOWN"].item())
        except Exception as e:
            st.error(f"Nie można przetworzyć danych tickera: {e}")
            st.stop()

        # Wyświetlanie
        st.write(f"**Cena:** {close_val:.2f}")
        st.write(f"**RSI:** {rsi_val:.1f}")
        st.write(f"**MACD:** {macd_val:.4f}")
        st.write(f"**Signal:** {signal_val:.4f}")
        st.write(f"**Bollinger:** UP {bb_up:.2f} | MID {bb_mid:.2f} | DOWN {bb_down:.2f}")

        # Wykres
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            vertical_spacing=0.02, row_heights=[0.55, 0.20, 0.25]
        )

        fig.add_trace(
            go.Candlestick(
                x=df_q.index,
                open=df_q["Open"],
                high=df_q["High"],
                low=df_q["Low"],
                close=df_q["Close"],
                increasing_line_color="lime",
                decreasing_line_color="red",
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(x=df_q.index, y=df_q["RSI"], mode="lines", line=dict(color="orange")),
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(x=df_q.index, y=df_q["MACD"], mode="lines", line=dict(color="cyan")),
            row=3, col=1
        )

        fig.add_trace(
            go.Scatter(x=df_q.index, y=df_q["Signal"], mode="lines", line=dict(color="white")),
            row=3, col=1
        )

        fig.update_layout(template="plotly_dark", height=900, width=1200)
        st.plotly_chart(fig, use_container_width=True)


# =====================================================================
# AUTO-SCAN
# =====================================================================

auto_scan = st.selectbox("Auto-skan:", ["Wyłączony","Co 1 minutę","Co 5 minut","Co 15 minut"])

if auto_scan == "Co 1 minutę":
    time.sleep(60)
    st.rerun()
elif auto_scan == "Co 5 minut":
    time.sleep(300)
    st.rerun()
elif auto_scan == "Co 15 minut":
    time.sleep(900)
    st.rerun()
