### Gotowy pełny skrypt – tani GPW/USA, heatmapa, AUTO‑SCALPER (15 min, AI)
import os
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from openai import OpenAI
from sklearn.ensemble import RandomForestClassifier
from streamlit_autorefresh import st_autorefresh

# =========================================================
# KONFIG / STYL
# =========================================================
st.set_page_config(page_title="AI PENNY KOMBAJN ULTRA", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #0d1117; color: #c9d1d9; }
.block-container { padding-top: 0.5rem; }
.ticker-card { background: #161b22; padding: 12px; border-radius: 10px; border: 1px solid #30363d; margin-bottom: 12px; }
.top-rank-card { background: #0d1117; padding: 8px; border-radius: 8px; border: 1px solid #30363d; text-align: center; font-size: 0.8rem; }
.stat-label { font-size: 0.65rem; color: #8b949e; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

DB_FILE = "tickers_db.txt"

# =========================================================
# PRESET – TYLKO TANIE GPW + TANIE USA (bez NVDA/TSLA)
# =========================================================
def load_tickers_default():
    gpw_penny = [
        "STX.WA","BCS.WA","RVU.WA","MAB.WA","SLV.WA","SCP.WA","CLN.WA","BMX.WA","SNT.WA",
        "PHN.WA","MPY.WA","ELQ.WA","ACG.WA","DVL.WA","DCR.WA","CIG.WA","APS.WA","SNK.WA",
        "GTN.WA","MOC.WA","MLS.WA","MLK.WA","NEU.WA","BHW.WA","BNP.WA","KCH.WA","PUR.WA",
        "VGO.WA","XTB.WA","TEN.WA","CDR.WA"  # kilka znanych, ale nadal GPW
    ]
    usa_penny = [
        "GOSS","TTOO","PLRX","IMUX","IMMP","VINC","VTVT","ACRS","AGEN","ALDX",
        "ANIX","ARDX","AVXL","BOLT","CRBP","CRDF","CRIS","CYCN","DRUG",
        "ENLV","EVGN","FATE","FEMY","GERN","GOVX","IBRX","INMB","IOVA",
        "ITRM","LGVN","MNKD","MREO","OCEA","OCUL","OGEN","PDSB",
        "PLSE","PMVP","PRAX","PRQR","RLMD","SANA","SCLX","SENS","TGTX","TNXP"
    ]
    preset = gpw_penny + usa_penny
    return ", ".join(preset)

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

def get_yf_ohlc(symbol, period="1y", interval="1d"):
    df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df["time"] = df.index
    return df.reset_index(drop=True)

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
# ANALIZA 15m + D1 (monitoring)
# =========================================================
def get_analysis(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)

        if d15.empty or d1d.empty:
            return None

        if isinstance(d15.columns, pd.MultiIndex):
            d15.columns = d15.columns.get_level_values(0)
        if isinstance(d1d.columns, pd.MultiIndex):
            d1d.columns = d1d.columns.get_level_values(0)

        price = float(d15["Close"].iloc[-1])
        prev_close = float(d1d["Close"].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100

        sma200 = d1d["Close"].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#00ff88" if price > sma200 else "#ff4b4b"

        atr = (d1d["High"] - d1d["Low"]).rolling(14).mean().iloc[-1]
        pivot = (d1d["High"].iloc[-2] + d1d["Low"].iloc[-2] + d1d["Close"].iloc[-2]) / 3

        delta = d15["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        if rsi < 32:
            rec, rec_col = "KUPUJ", "#238636"
        elif rsi > 68:
            rec, rec_col = "SPRZEDAJ", "#da3633"
        else:
            rec, rec_col = "CZEKAJ", "#8b949e"

        return {
            "symbol": symbol,
            "price": price,
            "change": change_pct,
            "rsi": rsi,
            "rec": rec,
            "rec_col": rec_col,
            "trend": trend_label,
            "trend_col": trend_color,
            "pivot": pivot,
            "tp": price + (atr * 1.5),
            "sl": price - (atr * 1.2),
            "df": d15,
        }
    except:
        return None

# =========================================================
# SZYBKI ML SCORE (do rankingu)
# =========================================================
def quick_ml_score(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False)
        if df.empty:
            return 0.0
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df["RSI"] = calculate_rsi(df["Close"])
        df["Trend"] = (df["Close"] > df["Close"].rolling(20).mean()).astype(int)
        df["Vol"] = df["Volume"].pct_change()
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.dropna(inplace=True)
        if len(df) < 40:
            return 0.0
        X = df[["Close", "RSI", "Trend", "Vol"]]
        y = (df["Close"].shift(-1) > df["Close"]).astype(int)
        y = y.loc[X.index]
        X = X.iloc[:-1]
        y = y.iloc[:-1]
        if len(X) < 30:
            return 0.0
        model = RandomForestClassifier(n_estimators=40, random_state=42)
        model.fit(X[:-5], y[:-5])
        return float(model.predict_proba(X.tail(1))[0][1] * 100)
    except:
        return 0.0

# =========================================================
# BIOTECH RADAR (ML)
# =========================================================
USA_BIOTECH = [
    "GOSS","TTOO","PLRX","IMUX","IMMP","VINC","VTVT","ACRS","AGEN","ALDX",
    "ANIX","ARDX","AVXL","BOLT","CRBP","CRDF","CRIS","CYCN","DRUG",
    "ENLV","EVGN","FATE","FEMY","GERN","GOVX","IBRX","INMB","IOVA",
    "ITRM","LGVN","MNKD","MREO","OCEA","OCUL","OGEN","PDSB",
    "PLSE","PMVP","PRAX","PRQR","RLMD","SANA","SCLX","SENS","TGTX","TNXP"
]
POLSKA_BIOTECH = [
    "BCS.WA","STX.WA","RVU.WA","MAB.WA","SLV.WA","SCP.WA","CLN.WA","BMX.WA","SNT.WA","PHN.WA"
]
WSZYSTKIE_SPOLKI_BIOTECH = USA_BIOTECH + POLSKA_BIOTECH

def przygotuj_dane_biotech(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df["RSI"] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    df["RVOL"] = df["Volume"] / df["Volume"].rolling(window=20).mean()
    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["Trend"] = np.where(df["Close"] > df["SMA_20"], 1, 0)
    df["Target"] = (df["Close"].shift(-3) > df["Close"]).astype(int)
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)
    return df

def biotech_radar():
    ranking = []
    for ticker in WSZYSTKIE_SPOLKI_BIOTECH:
        try:
            df = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
            if df.empty or len(df) < 30:
                continue
            df = przygotuj_dane_biotech(df)
            if df.empty:
                continue
            features = ["Close", "RSI", "Trend", "RVOL"]
            X = df[features]
            y = df["Target"]
            if len(X) < 30:
                continue
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model.fit(X[:-3], y[:-3])
            ostatnie = X.tail(1)
            szansa = model.predict_proba(ostatnie)[0][1] * 100
            rvol = float(df["RVOL"].iloc[-1])
            cena = float(df["Close"].iloc[-1])
            ranking.append(
                {
                    "Ticker": ticker,
                    "Szansa %": round(szansa, 1),
                    "RVOL": round(rvol, 2),
                    "Cena": round(cena, 4 if (".WA" not in ticker and cena < 1) else 2),
                }
            )
        except:
            continue
    if not ranking:
        return pd.DataFrame()
    return pd.DataFrame(ranking).sort_values(by="Szansa %", ascending=False)

# =========================================================
# AI
# =========================================================
def get_openai_client(api_key: str | None):
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except:
        return None

def build_trading_system_prompt(style: str) -> str:
    if style == "SCALP":
        return "Jestes ultra-agresywnym scalperem. Liczy sie ruch w ciagu minut-godzin, szybkie wejscie/wyjscie."
    if style == "DAY":
        return "Jestes daytraderem. Horyzont 1 dzien, zamykasz pozycje przed koncem sesji."
    if style == "LONG":
        return "Jestes swing/position traderem. Horyzont od kilku dni do tygodni, patrzysz na trend i ryzyko."
    return "Jestes systemem tradingowym."

def call_gpt(client: OpenAI | None, system_prompt: str, user_prompt: str) -> str:
    if client is None:
        return "(AI OFF – brak poprawnego klucza OpenAI)"
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"(AI ERROR: {e})"

# =========================================================
# AUTO‑SCALPER (15m, AI)
# =========================================================
def auto_scalper_scan(tickers):
    sygnaly = []
    for t in tickers:
        try:
            df = yf.download(t, period="2d", interval="15m", progress=False)
            if df.empty or len(df) < 30:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close = df["Close"]
            rsi = calculate_rsi(close)
            rsi_last = float(rsi.iloc[-1])
            price = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            zmiana = (price - prev) / prev * 100
            vol = df["Volume"]
            rvol = float(vol.iloc[-1] / (vol.rolling(20).mean().iloc[-1] + 1e-9))

            # prosty warunek scalp: skrajny RSI + podbity wolumen
            if (rsi_last < 30 or rsi_last > 70) and rvol > 2.0:
                sygnaly.append(
                    {
                        "symbol": t,
                        "price": price,
                        "rsi": rsi_last,
                        "zmiana": zmiana,
                        "rvol": rvol,
                    }
                )
        except:
            continue
    return sygnaly

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.title("⚙️ PENNY KOMBAJN ULTRA")

    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("✅ OpenAI Key z Secrets")
    else:
        api_key = st.text_input("OpenAI Key", type="password")
        if not api_key:
            st.warning("Dodaj klucz w Secrets lub wpisz go tutaj.")

    client = get_openai_client(api_key)

    tickers_input = st.text_area("Symbole (przecinek)", value=load_tickers_default())
    if st.button("Zapisz listę"):
        with open(DB_FILE, "w") as f:
            f.write(tickers_input)
        st.rerun()

    market_filter = st.radio("Rynek", ["MIX", "GPW", "USA"], horizontal=True)

    ai_style = st.radio("Styl AI", ["SCALP", "DAY", "LONG"], horizontal=True)

    mode = st.selectbox(
        "Tryb",
        [
            "Monitoring rynku",
            "Heatmapa rynku",
            "Biotech Radar (ML)",
            "AI alerty z listy",
            "AUTO‑SCALPER (15 min, AI)",
        ],
    )

    # AUTO‑SCALPER – wymuszone 15 min
    if mode == "AUTO‑SCALPER (15 min, AI)":
        st_autorefresh(interval=15 * 60 * 1000, key="auto_scalper_refresh")
        st.info("AUTO‑SCALPER odświeża się co 15 minut. Dźwięk systemowy ustawiasz w telefonie/PC (powiadomienia przeglądarki).")
    else:
        refresh_min = st.slider("Odświeżanie (minuty)", 15, 60, 30, step=5)
        st_autorefresh(interval=refresh_min * 60 * 1000, key="auto_refresh")

# =========================================================
# LISTA TICKERÓW + FILTR RYNKU + AKTYWNOŚĆ
# =========================================================
tickers_all = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if market_filter == "GPW":
    tickers_all = [t for t in tickers_all if is_gpw(t)]
elif market_filter == "USA":
    tickers_all = [t for t in tickers_all if is_usa(t)]

tickers_active = [t for t in tickers_all if is_market_open(t)]

st.title("📈 AI PENNY KOMBAJN ULTRA (tanie GPW + USA)")

# =========================================================
# TRYB: MONITORING + MINI‑RANKING
# =========================================================
if mode == "Monitoring rynku":
    if not tickers_active:
        st.info("Brak aktywnych tickerów dla bieżącej godziny (GPW 9–17, USA 15:30–22).")
    else:
        ranking_sort = st.selectbox(
            "Sortowanie monitoringu",
            ["RSI ↑", "Zmiana % ↓", "ML‑szansa ↓"],
        )

        data_list = []
        for t in tickers_active:
            res = get_analysis(t)
            if res:
                data_list.append(res)

        if not data_list:
            st.warning("Brak danych dla aktywnych tickerów.")
        else:
            # sortowanie
            if ranking_sort == "RSI ↑":
                data_list = sorted(data_list, key=lambda x: x["rsi"])
            elif ranking_sort == "Zmiana % ↓":
                data_list = sorted(data_list, key=lambda x: x["change"], reverse=True)
            elif ranking_sort == "ML‑szansa ↓":
                for d in data_list:
                    d["ml_score"] = quick_ml_score(d["symbol"])
                data_list = sorted(data_list, key=lambda x: x.get("ml_score", 0), reverse=True)

            st.subheader("📊 Monitoring rynku (tylko aktywne)")

            top_cols = st.columns(min(len(data_list), 4))
            for i, d in enumerate(data_list[:12]):
                with top_cols[i % 4]:
                    c_col = "#00ff88" if d["change"] >= 0 else "#ff4b4b"
                    extra = ""
                    if "ml_score" in d:
                        extra = f" | ML: {d['ml_score']:.0f}%"
                    st.markdown(
                        f"""
                        <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                            <b>{d['symbol']}</b><br>
                            <span style="color:{c_col}; font-weight:bold;">{d['price']:.4f}</span><br>
                            <span style="font-size:0.75rem; color:{d['trend_col']};">{d['trend']}</span><br>
                            <div style="background:{d['rec_col']}; font-size:0.65rem; border-radius:3px; margin:4px 0; color:white;">{d['rec']}</div>
                            <span class="stat-label">RSI: {d['rsi']:.1f} | Zm: {d['change']:.2f}%{extra}</span>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

            for d in data_list:
                st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.markdown(f"#### {d['symbol']} ({d['trend']})")
                    st.metric("Cena", f"{d['price']:.4f}", f"{d['change']:.2f}%")
                    st.write(f"**Pivot:** {d['pivot']:.4f} | **RSI:** {d['rsi']:.1f}")
                    st.write(f"**TP:** {d['tp']:.4f} | **SL:** {d['sl']:.4f}")
                    if "ml_score" in d:
                        st.write(f"**ML‑szansa wzrostu:** {d['ml_score']:.1f}%")

                    if st.button(f"🧠 AI {d['symbol']}", key=f"btn_{d['symbol']}"):
                        system_prompt = build_trading_system_prompt(ai_style)
                        prompt = (
                            f"Styl: {ai_style}. "
                            f"Symbol: {d['symbol']}, Cena: {d['price']}, Trend: {d['trend']}, "
                            f"RSI: {d['rsi']:.1f}, Pivot: {d['pivot']:.4f}, TP: {d['tp']:.4f}, SL: {d['sl']:.4f}. "
                            f"Podaj konkretny werdykt, plan wejscia/wyjscia i ryzyko 1-10."
                        )
                        ans = call_gpt(client, system_prompt, prompt)
                        st.session_state[f"ai_{d['symbol']}"] = ans

                    if f"ai_{d['symbol']}" in st.session_state:
                        st.info(st.session_state[f"ai_{d['symbol']}"])

                with c2:
                    df = d["df"]
                    fig = go.Figure(
                        data=[
                            go.Candlestick(
                                x=df.index[-80:],
                                open=df["Open"][-80:],
                                high=df["High"][-80:],
                                low=df["Low"][-80:],
                                close=df["Close"][-80:],
                                increasing_line_color="#00ff88",
                                decreasing_line_color="#ff4b4b",
                            )
                        ]
                    )
                    fig.add_hline(y=d["pivot"], line_dash="dot", line_color="white")
                    fig.update_layout(
                        template="plotly_dark",
                        height=360,
                        margin=dict(l=0, r=0, t=0, b=0),
                        xaxis_rangeslider_visible=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# TRYB: HEATMAPA RYNKU (RSI / ZMIANA / ML)
# =========================================================
elif mode == "Heatmapa rynku":
    st.subheader("Heatmapa rynku – RSI / Zmiana / ML‑szansa")
    if not tickers_active:
        st.info("Brak aktywnych tickerów.")
    else:
        rows = []
        for t in tickers_active:
            try:
                df = yf.download(t, period="60d", interval="1d", progress=False)
                if df.empty:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                close = df["Close"]
                rsi = float(calculate_rsi(close).iloc[-1])
                price = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                zmiana = (price - prev) / prev * 100
                ml = quick_ml_score(t)
                rows.append({"Ticker": t, "RSI": rsi, "Zmiana %": zmiana, "ML %": ml})
            except:
                continue

        if not rows:
            st.warning("Brak danych do heatmapy.")
        else:
            df_hm = pd.DataFrame(rows).set_index("Ticker")
            metric = st.selectbox("Metryka do heatmapy", ["RSI", "Zmiana %", "ML %"])
            fig = px.imshow(
                df_hm[[metric]].T,
                color_continuous_scale="RdYlGn",
                aspect="auto",
            )
            fig.update_layout(template="plotly_dark", height=260)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_hm.sort_values(metric, ascending=(metric == "RSI")), use_container_width=True)

# =========================================================
# TRYB: BIOTECH RADAR
# =========================================================
elif mode == "Biotech Radar (ML)":
    st.subheader("Biotech Radar – ML skaner okazji (USA + PL)")
    if st.button("Skanuj biotechy"):
        with st.spinner("Skanuję i trenuję modele..."):
            df_bio = biotech_radar()
        if df_bio.empty:
            st.error("Brak wyników.")
        else:
            st.dataframe(df_bio.head(50), use_container_width=True)

# =========================================================
# TRYB: AI ALERTY
# =========================================================
elif mode == "AI alerty z listy":
    st.subheader("AI alerty – analiza listy spółek (tylko aktywne)")
    rows = []
    for t in tickers_active:
        try:
            df = get_yf_ohlc(t, period="200d", interval="1d")
            if df.empty:
                continue
            close = df["Close"]
            rsi = float(calculate_rsi(close).iloc[-1])
            price = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            mom = (price - prev) / prev
            rows.append({"symbol": t, "price": price, "rsi": rsi, "mom20": mom})
        except:
            continue

    if not rows:
        st.warning("Brak danych do analizy (lub brak aktywnych tickerów).")
    else:
        text = "Wygeneruj alerty tradingowe dla spolek w stylu " + ai_style + ":\n\n"
        for r in rows:
            text += f"- {r['symbol']}: cena {r['price']:.4f}, RSI {r['rsi']:.1f}, momentum {r['mom20']:.2%}\n"

        system_prompt = build_trading_system_prompt(ai_style)
        ans = call_gpt(client, system_prompt, text)
        st.write(ans)

# =========================================================
# TRYB: AUTO‑SCALPER (15 min, AI)
# =========================================================
elif mode == "AUTO‑SCALPER (15 min, AI)":
    st.subheader("AUTO‑SCALPER – sygnały co 15 minut (RSI + RVOL + AI)")
    if not tickers_active:
        st.info("Brak aktywnych tickerów.")
    else:
        sygnaly = auto_scalper_scan(tickers_active)
        if not sygnaly:
            st.warning("Brak świeżych sygnałów scalp na tej świecy 15m.")
        else:
            df_sig = pd.DataFrame(sygnaly)
            st.success(f"Znaleziono {len(sygnaly)} sygnałów scalp.")
            st.dataframe(df_sig, use_container_width=True)

            # AI podsumowanie scalp
            opis = "Sygnały scalp (RSI skrajny + RVOL>2):\n"
            for s in sygnaly:
                opis += f"- {s['symbol']}: cena {s['price']:.4f}, RSI {s['rsi']:.1f}, zmiana {s['zmiana']:.2f}%, RVOL {s['rvol']:.1f}x\n"

            system_prompt = build_trading_system_prompt("SCALP")
            ans = call_gpt(client, system_prompt, opis + "\nPodaj 2-3 najlepsze wejscia scalp z konkretnym planem.")
            st.write(ans)

            st.markdown("**Dźwięk systemowy:** ustawiasz w telefonie/PC (powiadomienia przeglądarki / systemu). Tu masz wizualny alert + AI.")
