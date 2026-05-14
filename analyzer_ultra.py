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
st.set_page_config(page_title="AI PENNY KOMBAJN ULTRA v4", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #050810; color: #c9d1d9; }
.block-container { padding-top: 0.5rem; }
.sidebar .sidebar-content { background-color: #050810; }
.ticker-card { background: radial-gradient(circle at top left, #111827, #020617); padding: 12px; border-radius: 12px; border: 1px solid #1f2937; margin-bottom: 12px; }
.top-rank-card { background: linear-gradient(135deg, #020617, #111827); padding: 8px; border-radius: 10px; border: 1px solid #1f2937; text-align: center; font-size: 0.8rem; box-shadow: 0 0 12px rgba(56,189,248,0.15); }
.stat-label { font-size: 0.65rem; color: #9ca3af; text-transform: uppercase; }
.metric-good { color: #22c55e; }
.metric-bad { color: #ef4444; }
.metric-neutral { color: #eab308; }
h1, h2, h3, h4 { color: #e5e7eb; }
</style>
""", unsafe_allow_html=True)

DB_FILE = "tickers_db.txt"
MOJA20_FILE = "watchlist_moja20.txt"

# =========================================================
# PORTFEL – STX + REALNE POZYCJE
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
# PRESET – TYLKO TANIE GPW + TANIE USA (bez drogich blue chipów)
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
    # domyślnie weź 20 z presetów
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
# CACHE DANYCH – PRZYSPIESZENIE
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
# ANALIZA 15m + D1 (monitoring) – BEZ ML
# =========================================================
def get_analysis(symbol):
    try:
        d15 = yf_cached(symbol, "5d", "15m")
        d1d = yf_cached(symbol, "250d", "1d")
        if d15.empty or d1d.empty:
            return None

        price = float(d15["Close"].iloc[-1])
        prev_close = float(d1d["Close"].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100

        sma200 = d1d["Close"].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#22c55e" if price > sma200 else "#ef4444"

        atr = (d1d["High"] - d1d["Low"]).rolling(14).mean().iloc[-1]
        pivot = (d1d["High"].iloc[-2] + d1d["Low"].iloc[-2] + d1d["Close"].iloc[-2]) / 3

        delta = d15["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (delta.where(delta < 0, 0).abs()).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]

        if rsi < 30:
            rec, rec_col = "STREFA DOŁU (potencjalne KUPNO)", "#22c55e"
        elif rsi > 70:
            rec, rec_col = "STREFA GÓRY (potencjalna SPRZEDAŻ)", "#ef4444"
        else:
            rec, rec_col = "ŚRODEK (obserwacja)", "#eab308"

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
# AI – 4 STYLE: SCALP / DAY / SWING / LONG
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
        "Jestes systemem tradingowym. Oceniaj kazda spolke w trzech kategoriach: "
        "GORA (przewaga kupujacych), DOL (przewaga sprzedajacych), SRODEK (konsolidacja / brak przewagi). "
        "Podawaj: 1) werdykt GORA/DOL/SRODEK, 2) strefe wejscia (konkretne poziomy), "
        "3) gdzie UWAZAC (slaba plynnosc, duze knoty, gapy, newsy), 4) ryzyko 1-10. "
        "Nie pisz ogolnych ostrzezen typu 'pamietaj ze inwestowanie jest ryzykowne'. "
        "Krotko, konkretnie, jak do tradera."
    )
    if style == "SCALP":
        return base + " Styl: SCALP – horyzont minuty-godziny, liczy sie szybki ruch i wyjscie."
    if style == "DAY":
        return base + " Styl: DAY – horyzont 1 dzien, pozycje zamykane przed koncem sesji."
    if style == "SWING":
        return base + " Styl: SWING – horyzont kilka dni, grasz fale w trendzie."
    if style == "LONG":
        return base + " Styl: LONG – horyzont kilka tygodni, wazny trend i poziomy wsparcia/oporu."
    return base

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
            temperature=0.25,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"(AI ERROR: {e})"

# =========================================================
# AUTO‑SCALPER – OSOBNY TRYB
# =========================================================
def auto_scalper_scan(tickers):
    sygnaly = []
    for t in tickers:
        try:
            df = yf_cached(t, "2d", "15m")
            if df.empty or len(df) < 30:
                continue
            close = df["Close"]
            rsi = calculate_rsi(close)
            rsi_last = float(rsi.iloc[-1])
            price = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            zmiana = (price - prev) / prev * 100
            vol = df["Volume"]
            rvol = float(vol.iloc[-1] / (vol.rolling(20).mean().iloc[-1] + 1e-9))

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
# PANEL PORTFELA – STX + MOJE_AKCJE
# =========================================================
def analiza_portfela():
    kurs_usd = pobierz_kurs_usd()
    rows = []
    total_pln = 0
    total_invested_pln = 0

    for ticker, dane in MOJE_AKCJE.items():
        try:
            cena_wejscia, ilosc = dane
            df = yf_cached(ticker, "60d", "1d")
            if df.empty:
                continue
            cena_teraz = float(df["Close"].iloc[-1])
            zysk_proc = ((cena_teraz - cena_wejscia) / cena_wejscia) * 100

            mnoznik = kurs_usd if ".WA" not in ticker else 1
            wartosc_pln = (cena_teraz * ilosc) * mnoznik
            invested_pln = (cena_wejscia * ilosc) * mnoznik

            total_pln += wartosc_pln
            total_invested_pln += invested_pln

            sma20 = float(df["Close"].rolling(window=20).mean().iloc[-1])
            status = "OK (nad SMA20)" if cena_teraz > sma20 else "SŁABNIE (pod SMA20)"

            rows.append(
                {
                    "Ticker": ticker,
                    "Cena wejścia": round(cena_wejscia, 4),
                    "Cena teraz": round(cena_teraz, 4),
                    "Ilość": ilosc,
                    "Zysk %": round(zysk_proc, 2),
                    "Wartość PLN": round(wartosc_pln, 2),
                    "Status": status,
                }
            )
        except:
            continue

    summary = None
    if total_invested_pln > 0:
        calkowity_zysk = total_pln - total_invested_pln
        summary = {
            "total_pln": total_pln,
            "calkowity_zysk": calkowity_zysk,
            "zysk_proc": (calkowity_zysk / total_invested_pln) * 100,
            "kurs_usd": kurs_usd,
        }
    return rows, summary

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.title("⚙️ PENNY KOMBAJN ULTRA v4")

    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("✅ OpenAI Key z Secrets")
    else:
        api_key = st.text_input("OpenAI Key", type="password")
        if not api_key:
            st.warning("Dodaj klucz w Secrets lub wpisz go tutaj.")

    client = get_openai_client(api_key)

    preset_choice = st.selectbox(
        "Preset tickerów",
        ["MIX (Penny GPW + USA)", "Tylko GPW (penny)", "Tylko USA (penny)", "MOJA 20‑TKA"],
    )

    if preset_choice == "MIX (Penny GPW + USA)":
        base_list = load_tickers_default()
    elif preset_choice == "Tylko GPW (penny)":
        base_list = ", ".join(preset_gpw_penny())
    elif preset_choice == "Tylko USA (penny)":
        base_list = ", ".join(preset_usa_penny())
    else:
        base_list = load_moja20()

    tickers_input = st.text_area("Symbole (przecinek)", value=base_list, height=120)

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        if st.button("💾 Zapisz jako MOJA 20‑TKA"):
            save_moja20(tickers_input)
            st.success("Zapisano MOJA 20‑TKA do pliku.")
    with col_w2:
        if st.button("🔁 Wczytaj MOJA 20‑TKA"):
            tickers_input = load_moja20()
            st.experimental_rerun()

    market_filter = st.radio("Filtr rynku", ["MIX", "GPW", "USA"], horizontal=True)

    ai_style = st.radio("Styl AI", ["SCALP", "DAY", "SWING", "LONG"], horizontal=True)

    mode = st.selectbox(
        "Tryb",
        [
            "Monitoring rynku",
            "Heatmapa rynku",
            "AUTO‑SCALPER (15 min, AI)",
            "AI analiza listy (20 wybranych)",
            "STX + Mój portfel",
        ],
    )

    if mode == "AUTO‑SCALPER (15 min, AI)":
        st_autorefresh(interval=15 * 60 * 1000, key="auto_scalper_refresh")
        st.info("AUTO‑SCALPER odświeża się co 15 minut. Dźwięk ustawiasz w telefonie/PC (powiadomienia przeglądarki).")
    else:
        refresh_min = st.slider("Odświeżanie (minuty)", 15, 60, 30, step=5)
        st_autorefresh(interval=refresh_min * 60 * 1000, key="auto_refresh")

# =========================================================
# LISTA TICKERÓW + FILTR RYNKU + LIMIT 20
# =========================================================
tickers_all = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if market_filter == "GPW":
    tickers_all = [t for t in tickers_all if is_gpw(t)]
elif market_filter == "USA":
    tickers_all = [t for t in tickers_all if is_usa(t)]

tickers_active = [t for t in tickers_all if is_market_open(t)]
tickers_active = tickers_active[:20]

st.title("📈 AI PENNY KOMBAJN ULTRA v4")

# =========================================================
# TRYB: MONITORING – LEKKI, BEZ ML
# =========================================================
if mode == "Monitoring rynku":
    if not tickers_active:
        st.info("Brak aktywnych tickerów dla bieżącej godziny (GPW 9–17, USA 15:30–22).")
    else:
        sort_key = st.selectbox(
            "Sortowanie",
            ["RSI ↑ (od wyczerpania do przegrzania)", "Zmiana % ↓"],
        )

        data_list = []
        for t in tickers_active:
            res = get_analysis(t)
            if res:
                data_list.append(res)

        if not data_list:
            st.warning("Brak danych dla aktywnych tickerów.")
        else:
            if sort_key.startswith("RSI"):
                data_list = sorted(data_list, key=lambda x: x["rsi"])
            else:
                data_list = sorted(data_list, key=lambda x: x["change"], reverse=True)

            st.subheader("📊 Monitoring rynku (max 20, tylko aktywne)")

            top_cols = st.columns(min(len(data_list), 4))
            for i, d in enumerate(data_list[:12]):
                with top_cols[i % 4]:
                    c_col = "#22c55e" if d["change"] >= 0 else "#ef4444"
                    st.markdown(
                        f"""
                        <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                            <b style="color:#e5e7eb;">{d['symbol']}</b><br>
                            <span style="color:{c_col}; font-weight:bold;">{d['price']:.4f}</span><br>
                            <span style="font-size:0.75rem; color:{d['trend_col']};">{d['trend']}</span><br>
                            <div style="background:{d['rec_col']}; font-size:0.65rem; border-radius:4px; margin:4px 0; color:#020617; font-weight:600;">
                                {d['rec']}
                            </div>
                            <span class="stat-label">RSI: {d['rsi']:.1f} | Zm: {d['change']:.2f}%</span>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

            for d in data_list:
                st.markdown('<div class="ticker-card">', unsafe_allow_html=True)
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.markdown(f"#### {d['symbol']} ({d['trend']})")
                    delta_class = "metric-good" if d["change"] >= 0 else "metric-bad"
                    st.markdown(
                        f"<span class='{delta_class}'>Cena: {d['price']:.4f} ({d['change']:.2f}%)</span>",
                        unsafe_allow_html=True,
                    )
                    st.write(f"**Pivot:** {d['pivot']:.4f} | **RSI:** {d['rsi']:.1f}")
                    st.write(f"**TP:** {d['tp']:.4f} | **SL:** {d['sl']:.4f}")
                    st.caption("RSI < 30 – dół, > 70 – góra, 30–70 – środek (obserwacja).")

                    if st.button(f"🧠 AI {d['symbol']}", key=f"btn_{d['symbol']}"):
                        system_prompt = build_trading_system_prompt(ai_style)
                        prompt = (
                            f"Symbol: {d['symbol']}, Cena: {d['price']:.4f}, Trend: {d['trend']}, "
                            f"RSI: {d['rsi']:.1f}, Pivot: {d['pivot']:.4f}, TP: {d['tp']:.4f}, SL: {d['sl']:.4f}. "
                            f"Podaj: 1) GORA/DOL/SRODEK, 2) strefe wejscia, 3) gdzie UWAZAC, 4) ryzyko 1-10."
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
                                increasing_line_color="#22c55e",
                                decreasing_line_color="#ef4444",
                            )
                        ]
                    )
                    fig.add_hline(y=d["pivot"], line_dash="dot", line_color="#e5e7eb")
                    fig.update_layout(
                        template="plotly_dark",
                        height=360,
                        margin=dict(l=0, r=0, t=0, b=0),
                        xaxis_rangeslider_visible=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# TRYB: HEATMAPA – OSOBNY, LEKKI
# =========================================================
elif mode == "Heatmapa rynku":
    st.subheader("Heatmapa rynku – RSI / Zmiana % (max 20, aktywne)")
    if not tickers_active:
        st.info("Brak aktywnych tickerów.")
    else:
        rows = []
        for t in tickers_active:
            try:
                df = yf_cached(t, "60d", "1d")
                if df.empty:
                    continue
                close = df["Close"]
                rsi = float(calculate_rsi(close).iloc[-1])
                price = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                zmiana = (price - prev) / prev * 100
                rows.append({"Ticker": t, "RSI": rsi, "Zmiana %": zmiana})
            except:
                continue

        if not rows:
            st.warning("Brak danych do heatmapy.")
        else:
            df_hm = pd.DataFrame(rows).set_index("Ticker")
            metric = st.selectbox("Metryka do heatmapy", ["RSI", "Zmiana %"])
            fig = px.imshow(
                df_hm[[metric]].T,
                color_continuous_scale="RdYlGn",
                aspect="auto",
            )
            fig.update_layout(template="plotly_dark", height=260)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_hm.sort_values(metric, ascending=(metric == "RSI")), use_container_width=True)

# =========================================================
# TRYB: AUTO‑SCALPER – OSOBNY WORKER
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

            opis = "Sygnały scalp (RSI skrajny + RVOL>2):\n"
            for s in sygnaly:
                opis += f"- {s['symbol']}: cena {s['price']:.4f}, RSI {s['rsi']:.1f}, zmiana {s['zmiana']:.2f}%, RVOL {s['rvol']:.1f}x\n"

            system_prompt = build_trading_system_prompt("SCALP")
            ans = call_gpt(
                client,
                system_prompt,
                opis + "\nWybierz 2-3 najlepsze wejscia scalp, podaj strefe wejscia, SL i gdzie UWAZAC.",
            )
            st.write(ans)
            st.caption("Dźwięk systemowy ustawiasz w telefonie/PC (powiadomienia przeglądarki).")

# =========================================================
# TRYB: AI ANALIZA LISTY (20 WYBRANYCH)
# =========================================================
elif mode == "AI analiza listy (20 wybranych)":
    st.subheader("AI analiza – 20 wybranych, tylko aktywne")
    if not tickers_active:
        st.info("Brak aktywnych tickerów.")
    else:
        rows = []
        for t in tickers_active:
            try:
                df = yf_cached(t, "120d", "1d")
                if df.empty or len(df) < 20:
                    continue
                close = df["Close"]
                rsi = float(calculate_rsi(close).iloc[-1])
                price = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                zmiana = (price - prev) / prev * 100
                rows.append({"symbol": t, "price": price, "rsi": rsi, "zmiana": zmiana})
            except:
                continue

        if not rows:
            st.warning("Brak danych do AI analizy.")
        else:
            text = "Oceń te spolki w stylu " + ai_style + ":\n\n"
            for r in rows:
                text += f"- {r['symbol']}: cena {r['price']:.4f}, RSI {r['rsi']:.1f}, zmiana {r['zmiana']:.2f}%\n"

            system_prompt = build_trading_system_prompt(ai_style)
            ans = call_gpt(
                client,
                system_prompt,
                text + "\nDla kazdej: GORA/DOL/SRODEK, strefa wejscia, gdzie UWAZAC, ryzyko 1-10.",
            )
            st.write(ans)

# =========================================================
# TRYB: STX + MÓJ PORTFEL
# =========================================================
elif mode == "STX + Mój portfel":
    st.subheader("STX + Mój portfel (realne pozycje)")

    rows, summary = analiza_portfela()
    if not rows:
        st.info("Brak danych portfela.")
    else:
        df_port = pd.DataFrame(rows)
        st.dataframe(df_port, use_container_width=True)

        if summary:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Łączna wartość portfela (PLN)", f"{summary['total_pln']:.2f}")
            with col2:
                delta_class = "metric-good" if summary["calkowity_zysk"] >= 0 else "metric-bad"
                st.markdown(
                    f"<span class='{delta_class}'>Zysk/Strata: {summary['calkowity_zysk']:.2f} PLN ({summary['zysk_proc']:.1f}%)</span>",
                    unsafe_allow_html=True,
                )
            with col3:
                st.metric("Kurs USD/PLN", f"{summary['kurs_usd']:.2f}")

    st.markdown("---")
    st.markdown("### STX.WA – wykres + AI")

    stx_data = get_analysis("STX.WA")
    if not stx_data:
        st.warning("Brak danych dla STX.WA.")
    else:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"#### STX.WA ({stx_data['trend']})")
            st.metric("Cena", f"{stx_data['price']:.4f}", f"{stx_data['change']:.2f}%")
            st.write(f"**Pivot:** {stx_data['pivot']:.4f} | **RSI:** {stx_data['rsi']:.1f}")
            st.write(f"**TP:** {stx_data['tp']:.4f} | **SL:** {stx_data['sl']:.4f}")
            if st.button("🧠 AI STX.WA", key="ai_stx"):
                system_prompt = build_trading_system_prompt(ai_style)
                prompt = (
                    f"Symbol: STX.WA, Cena: {stx_data['price']:.4f}, Trend: {stx_data['trend']}, "
                    f"RSI: {stx_data['rsi']:.1f}, Pivot: {stx_data['pivot']:.4f}, TP: {stx_data['tp']:.4f}, SL: {stx_data['sl']:.4f}. "
                    f"Podaj: 1) GORA/DOL/SRODEK, 2) strefe wejscia, 3) gdzie UWAZAC, 4) ryzyko 1-10."
                )
                ans = call_gpt(client, system_prompt, prompt)
                st.session_state["ai_stx"] = ans

            if "ai_stx" in st.session_state:
                st.info(st.session_state["ai_stx"])

        with c2:
            df = stx_data["df"]
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=df.index[-80:],
                        open=df["Open"][-80:],
                        high=df["High"][-80:],
                        low=df["Low"][-80:],
                        close=df["Close"][-80:],
                        increasing_line_color="#22c55e",
                        decreasing_line_color="#ef4444",
                    )
                ]
            )
            fig.add_hline(y=stx_data["pivot"], line_dash="dot", line_color="#e5e7eb")
            fig.update_layout(
                template="plotly_dark",
                height=360,
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)
