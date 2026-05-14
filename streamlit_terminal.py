
import os
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# =========================================================
# KONFIG / STYL
# =========================================================
st.set_page_config(page_title="AI PENNY KOMBAJN ULTRA v6.1 PRO", page_icon="📈", layout="wide")

st.markdown("""
<style>
/* TŁO APLIKACJI */
.stApp { 
    background-color: #02030a; 
    color: #e5e7eb; 
}

/* KONTENER GŁÓWNY */
.block-container { 
    padding-top: 0.5rem; 
}

/* SIDEBAR */
.sidebar .sidebar-content { 
    background: radial-gradient(circle at top left, #020617, #000000); 
    border-right: 1px solid #1f2937;
}

/* KARTY TICKERÓW */
.ticker-card { 
    background: radial-gradient(circle at top left, #020617, #000000); 
    padding: 12px; 
    border-radius: 12px; 
    border: 1px solid #1f2937; 
    margin-bottom: 12px; 
    box-shadow: 0 0 18px rgba(56,189,248,0.18);
}

/* TOP RANK KARTY */
.top-rank-card { 
    background: linear-gradient(135deg, #020617, #000000); 
    padding: 8px; 
    border-radius: 10px; 
    border: 1px solid #1f2937; 
    text-align: center; 
    font-size: 0.8rem; 
    box-shadow: 0 0 20px rgba(34,197,94,0.25);
}

/* METRYKI – NEON */
.metric-good { 
    color: #22c55e; 
    text-shadow: 0 0 8px rgba(34,197,94,0.7);
}
.metric-bad { 
    color: #f97373; 
    text-shadow: 0 0 8px rgba(248,113,113,0.7);
}
.metric-neutral { 
    color: #eab308; 
    text-shadow: 0 0 8px rgba(234,179,8,0.7);
}

/* NAGŁÓWKI */
h1, h2, h3, h4 { 
    color: #f9fafb; 
    text-shadow: 0 0 12px rgba(56,189,248,0.35);
}

/* PRZYCISKI */
.stButton>button {
    background: linear-gradient(135deg, #0f172a, #0369a1);
    color: #e5e7eb;
    border-radius: 999px;
    border: 1px solid #38bdf8;
    padding: 0.35rem 0.9rem;
    font-size: 0.85rem;
    font-weight: 600;
    box-shadow: 0 0 14px rgba(56,189,248,0.35);
}
.stButton>button:hover {
    border-color: #22c55e;
    box-shadow: 0 0 18px rgba(34,197,94,0.55);
}

/* TABELKI */
.table-row-green { background-color: rgba(34,197,94,0.15); }
.table-row-red   { background-color: rgba(239,68,68,0.15); }
.table-row-yellow{ background-color: rgba(234,179,8,0.15); }

</style>
""", unsafe_allow_html=True)

MOJA20_FILE = "watchlist_moja20.txt"

# =========================================================
# PORTFEL – REALNE POZYCJE
# =========================================================
MOJE_AKCJE = {
    "BCS.WA": [5.610, 200],
    "STX.WA": [2.753, 2050],
    "RVU.WA": [25.10, 100],
    "GOSS": [0.45, 2000],
}

def pobierz_kurs_usd():
    try:
        usd = yf.download("USDPLN=X", period="1d", interval="1m", progress=False)
        return float(usd["Close"].iloc[-1])
    except:
        return 4.00

# =========================================================
# PRESET GPW + USA
# =========================================================
def preset_gpw_penny():
    return [
        "STX.WA","BCS.WA","RVU.WA","MAB.WA","SLV.WA","SCP.WA","CLN.WA","BMX.WA","SNT.WA",
        "PHN.WA","MPY.WA","ELQ.WA","ACG.WA","DVL.WA","DCR.WA","CIG.WA","APS.WA","SNK.WA",
        "GTN.WA","MOC.WA","MLS.WA","MLK.WA","NEU.WA","VGO.WA"
    ]

def preset_usa_penny():
    return [
        "GOSS","TTOO","PLRX","IMUX","IMMP","VINC","VTVT","ACRS","AGEN","ALDX",
        "ANIX","ARDX","AVXL","BOLT","CRBP","CRDF","CRIS","CYCN","DRUG",
        "ENLV","EVGN","FATE","FEMY","GERN","GOVX","IBRX","INMB","IOVA",
        "ITRM","LGVN","MNKD","MREO","OCEA","OCUL","OGEN","PDSB",
        "PLSE","PMVP","PRAX","PRQR","RLMD","SANA","SCLX","SENS","TGTX","TNXP"
    ]

def load_tickers_default():
    return ", ".join(preset_gpw_penny() + preset_usa_penny())

def load_moja20():
    if os.path.exists(MOJA20_FILE):
        try:
            with open(MOJA20_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except:
            pass
    return ", ".join((preset_gpw_penny() + preset_usa_penny())[:20])

def save_moja20(text):
    with open(MOJA20_FILE, "w", encoding="utf-8") as f:
        f.write(text)

# =========================================================
# POMOCNICZE
# =========================================================
def calculate_rsi(series, window=14):
    if len(series) < window:
        return pd.Series([50] * len(series), index=series.index)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def is_gpw(symbol: str) -> bool:
    return symbol.upper().endswith(".WA")

def is_usa(symbol: str) -> bool:
    return not symbol.upper().endswith(".WA")

def is_market_open(symbol: str) -> bool:
    now = datetime.now().time()
    if is_gpw(symbol):
        return dtime(9, 0) <= now <= dtime(17, 5)
    else:
        return dtime(15, 30) <= now <= dtime(22, 5)

# =========================================================
# CACHE
# =========================================================
@st.cache_data(show_spinner=False)
def yf_cached(symbol, period, interval):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

# =========================================================
# AI – FORMAT #1–#5
# =========================================================
def get_openai_client(api_key: str | None):
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except:
        return None

def build_trading_system_prompt(style: str) -> str:
    base = (
        "Jesteś analitykiem technicznym. Oceniaj każdą spółkę konkretnie, bez lania wody.\n"
        "FORMAT A2-FULL (#1–#5):\n\n"
        "#1 DECYZJA: KUP / SPRZEDAJ / TRZYMAJ\n\n"
        "#2 UZASADNIENIE:\n"
        "- RSI: poziom + kierunek\n"
        "- Trend: SMA200 + struktura świec\n"
        "- Momentum: rosnące / słabnące\n"
        "- Wolumen: vs średnia\n"
        "- Poziomy: wsparcia / opory / pivot\n"
        "- Sygnały świecowe\n\n"
        "#3 PLAN TRANSAKCJI:\n"
        "- ENTRY: dokładny poziom wejścia\n"
        "- SL: poziom + uzasadnienie\n"
        "- TP1 / TP2\n\n"
        "#4 RYZYKO: ocena 1–10 + komentarz\n\n"
        "#5 UWAGI: płynność / gapy / newsy / fałszywe wybicia\n\n"
    )
    return base + f"Styl analizy: {style}."

def call_gpt(client: OpenAI | None, system_prompt: str, user_prompt: str) -> str:
    if client is None:
        return "(AI OFF – brak poprawnego klucza OpenAI)"
    try:
        r = client.chat.completions.create(
            model=model,  # model z sidebaru
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"(AI ERROR: {e})"
# =========================================================
# SIDEBAR – USTAWIENIA
# =========================================================
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU AI ULTRA v6.1 PRO")

api_key = st.sidebar.text_input("🔑 OpenAI API Key", type="password")
model = st.sidebar.selectbox(
    "🤖 Model GPT",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini"],
    index=0
)

ai_style = st.sidebar.selectbox(
    "🎨 Styl analizy AI",
    ["Ultra krótko", "Technicznie", "Swing", "Daytrading", "Price Action", "Momentum", "Konserwatywnie"],
    index=1
)

auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh (co 60s)")
if auto_refresh:
    st_autorefresh(interval=60000, key="refresh")

# =========================================================
# TRYBY APLIKACJI
# =========================================================
mode = st.sidebar.radio(
    "📌 TRYB APLIKACJI",
    [
        "📊 Skaner Rynku",
        "📈 Wykres + AI",
        "📉 Portfel",
        "⭐ Moja20",
        "🧪 Backtest",
        "🧠 AI Multi-Analiza",
    ]
)

# =========================================================
# INPUT TICKERÓW
# =========================================================
if mode == "⭐ Moja20":
    st.header("⭐ MOJA20 – Twoja własna lista 20 tickerów")
    moja20_text = st.text_area("Edytuj listę tickerów:", load_moja20(), height=200)
    if st.button("💾 Zapisz MOJA20"):
        save_moja20(moja20_text)
        st.success("Zapisano!")
    tickers_input = moja20_text

elif mode == "📊 Skaner Rynku":
    st.header("📊 SKANER RYNKU – GPW + USA")
    tickers_input = load_tickers_default()

else:
    tickers_input = st.text_input(
        "Wpisz tickery (oddzielone przecinkami):",
        load_tickers_default()
    )

tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

# =========================================================
# FUNKCJA POBIERANIA DANYCH
# =========================================================
def get_data(symbol, period="3mo", interval="1d"):
    df = yf_cached(symbol, period, interval)
    if df.empty:
        return pd.DataFrame()

    df["RSI"] = calculate_rsi(df["Close"])
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["Change"] = df["Close"].pct_change() * 100
    df["VolumeAvg"] = df["Volume"].rolling(20).mean()
    return df

# =========================================================
# PATCH NA PUSTE WYKRESY
# =========================================================
def safe_plot(df, symbol):
    if df.empty or len(df) < 2:
        fig = go.Figure()
        fig.update_layout(
            title=f"{symbol} – brak danych",
            template="plotly_dark",
            height=400
        )
        return fig

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name="OHLC"
    ))

    fig.update_layout(
        title=f"{symbol} – Wykres",
        template="plotly_dark",
        height=500,
        xaxis_rangeslider_visible=False
    )
    return fig
# =========================================================
# FUNKCJE TABEL – KOLOROWANIE HTML
# =========================================================
def color_row_html(row):
    if row["Change"] > 0:
        return 'class="table-row-green"'
    elif row["Change"] < 0:
        return 'class="table-row-red"'
    else:
        return 'class="table-row-yellow"'


# =========================================================
# TRYB: 📊 SKANER RYNKU
# =========================================================
if mode == "📊 Skaner Rynku":
    st.header("📊 SKANER RYNKU – GPW + USA")

    rows = []
    for sym in tickers:
        df = get_data(sym)
        if df.empty:
            continue

        last = df.iloc[-1]
        rows.append({
            "Ticker": sym,
            "Close": round(last["Close"], 4),
            "Change": round(last["Change"], 2),
            "RSI": round(last["RSI"], 1),
            "SMA200": round(last["SMA200"], 4),
            "Vol/Avg": round(last["Volume"] / (last["VolumeAvg"] + 1e-9), 2),
        })

    if rows:
        df_scan = pd.DataFrame(rows)
        df_scan_html = df_scan.to_html(
            classes="scan-table",
            escape=False,
            index=False,
            table_id="scan"
        )

        # kolorowanie
        for i, row in df_scan.iterrows():
            cls = color_row_html(row)
            df_scan_html = df_scan_html.replace(
                f"<tr><td>{row['Ticker']}</td>",
                f"<tr {cls}><td>{row['Ticker']}</td>"
            )

        st.markdown(df_scan_html, unsafe_allow_html=True)
    else:
        st.warning("Brak danych.")


# =========================================================
# TRYB: ⭐ MOJA20
# =========================================================
elif mode == "⭐ Moja20":
    st.header("⭐ MOJA20 – Twoje ulubione tickery")

    rows = []
    for sym in tickers:
        df = get_data(sym)
        if df.empty:
            continue
        last = df.iloc[-1]
        rows.append({
            "Ticker": sym,
            "Close": round(last["Close"], 4),
            "Change": round(last["Change"], 2),
            "RSI": round(last["RSI"], 1),
        })

    if rows:
        df_m20 = pd.DataFrame(rows)
        df_m20_html = df_m20.to_html(
            classes="moja20-table",
            escape=False,
            index=False
        )

        for i, row in df_m20.iterrows():
            cls = color_row_html(row)
            df_m20_html = df_m20_html.replace(
                f"<tr><td>{row['Ticker']}</td>",
                f"<tr {cls}><td>{row['Ticker']}</td>"
            )

        st.markdown(df_m20_html, unsafe_allow_html=True)
    else:
        st.warning("Brak danych.")


# =========================================================
# TRYB: 📉 PORTFEL
# =========================================================
elif mode == "📉 Portfel":
    st.header("📉 PORTFEL – Realne pozycje")

    usd = pobierz_kurs_usd()
    rows = []

    for sym, (buy_price, qty) in MOJE_AKCJE.items():
        df = get_data(sym)
        if df.empty:
            continue

        last = df.iloc[-1]["Close"]
        pnl = (last - buy_price) * qty
        if is_usa(sym):
            pnl *= usd

        rows.append({
            "Ticker": sym,
            "Buy": buy_price,
            "Last": round(last, 4),
            "Qty": qty,
            "PnL PLN": round(pnl, 2),
        })

    df_p = pd.DataFrame(rows)
    df_p_html = df_p.to_html(index=False)

    st.markdown(df_p_html, unsafe_allow_html=True)


# =========================================================
# TRYB: 📈 WYKRES + AI
# =========================================================
elif mode == "📈 Wykres + AI":
    st.header("📈 WYKRES + ANALIZA AI")

    symbol = st.selectbox("Wybierz ticker:", tickers)

    df = get_data(symbol)
    fig = safe_plot(df, symbol)
    st.plotly_chart(fig, use_container_width=True)

    if st.button("🔮 Analiza AI"):
        client = get_openai_client(api_key)
        system_prompt = build_trading_system_prompt(ai_style)
        user_prompt = f"Przeanalizuj spółkę {symbol} na podstawie danych technicznych."
        out = call_gpt(client, system_prompt, user_prompt)
        st.markdown(f"### 🧠 AI ANALIZA\n{out}")


# =========================================================
# TRYB: 🧠 AI MULTI-ANALIZA
# =========================================================
elif mode == "🧠 AI Multi-Analiza":
    st.header("🧠 AI – Analiza wielu spółek")

    client = get_openai_client(api_key)
    system_prompt = build_trading_system_prompt(ai_style)

    for sym in tickers:
        st.subheader(f"📌 {sym}")
        df = get_data(sym)
        fig = safe_plot(df, sym)
        st.plotly_chart(fig, use_container_width=True)

        user_prompt = f"Przeanalizuj spółkę {sym}."
        out = call_gpt(client, system_prompt, user_prompt)
        st.markdown(out)
        st.markdown("---")


# =========================================================
# TRYB: 🧪 BACKTEST
# =========================================================
elif mode == "🧪 Backtest":
    st.header("🧪 BACKTEST – RSI + SMA200")

    symbol = st.selectbox("Ticker:", tickers)
    df = get_data(symbol, period="1y")

    if df.empty:
        st.warning("Brak danych.")
    else:
        df["Signal"] = 0
        df.loc[(df["RSI"] < 30) & (df["Close"] > df["SMA200"]), "Signal"] = 1
        df.loc[(df["RSI"] > 70) & (df["Close"] < df["SMA200"]), "Signal"] = -1

        df["Strategy"] = df["Signal"].shift(1) * df["Change"]
        df["Equity"] = (1 + df["Strategy"] / 100).cumprod()

        st.line_chart(df["Equity"])
        st.success(f"Zwrot strategii: {round((df['Equity'].iloc[-1] - 1) * 100, 2)}%")
# =========================================================
# STOPKA + STABILIZACJA UI
# =========================================================
st.markdown("""
<hr style='border: 1px solid #1f2937; margin-top: 40px;'>
<div style='text-align: center; color: #6b7280; font-size: 0.8rem;'>
    AI PENNY KOMBAJN ULTRA v6.1 PRO • Neon UI • Zero Styler • Zero Matplotlib • 2026<br>
    Wersja finalna – pełna automatyzacja, stabilność i kompatybilność z Streamlit Cloud.
</div>
""", unsafe_allow_html=True)
