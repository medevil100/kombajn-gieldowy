
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

st.set_page_config(page_title="AI PENNY KOMBAJN ULTRA v6.1 PRO", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #02030a; color: #e5e7eb; }
.block-container { padding-top: 0.5rem; }
.sidebar .sidebar-content { background: radial-gradient(circle at top left, #020617, #000000); border-right: 1px solid #1f2937; }
.ticker-card { background: radial-gradient(circle at top left, #020617, #000000); padding: 12px; border-radius: 12px; border: 1px solid #1f2937; margin-bottom: 12px; box-shadow: 0 0 18px rgba(56,189,248,0.18); }
.metric-good { color: #22c55e; text-shadow: 0 0 8px rgba(34,197,94,0.7); }
.metric-bad { color: #f97373; text-shadow: 0 0 8px rgba(248,113,113,0.7); }
.metric-neutral { color: #eab308; text-shadow: 0 0 8px rgba(234,179,8,0.7); }
h1, h2, h3, h4 { color: #f9fafb; text-shadow: 0 0 12px rgba(56,189,248,0.35); }
.stButton>button { background: linear-gradient(135deg, #0f172a, #0369a1); color: #e5e7eb; border-radius: 999px; border: 1px solid #38bdf8; padding: 0.35rem 0.9rem; font-size: 0.85rem; font-weight: 600; box-shadow: 0 0 14px rgba(56,189,248,0.35); }
.stButton>button:hover { border-color: #22c55e; box-shadow: 0 0 18px rgba(34,197,94,0.55); }
.stSelectbox>div>div, .stRadio>div, .stTextArea textarea, .stTextInput input {
    background-color: #020617 !important;
    border-radius: 8px !important;
    border: 1px solid #1f2937 !important;
    color: #e5e7eb !important;
}
.js-plotly-plot .plotly .main-svg { filter: drop-shadow(0 0 12px rgba(56,189,248,0.25)); }
</style>
""", unsafe_allow_html=True)

MOJA20_FILE = "watchlist_moja20.txt"

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
                txt = f.read().strip()
                if txt:
                    return txt
        except:
            pass
    return ", ".join((preset_gpw_penny() + preset_usa_penny())[:20])

def save_moja20(text):
    with open(MOJA20_FILE, "w", encoding="utf-8") as f:
        f.write(text)

def calculate_rsi(series, window=14):
    if len(series) < window:
        return pd.Series([50] * len(series), index=series.index)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def is_gpw(symbol): 
    return symbol.upper().endswith(".WA")

def is_usa(symbol): 
    return not symbol.upper().endswith(".WA")

def is_market_open(symbol):
    now = datetime.now().time()
    if is_gpw(symbol):
        return dtime(9, 0) <= now <= dtime(17, 5)
    return dtime(15, 30) <= now <= dtime(22, 5)

@st.cache_data(show_spinner=False)
def yf_cached(symbol, period, interval):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_analysis(symbol):
    try:
        d15 = yf_cached(symbol, "5d", "15m")
        d1d = yf_cached(symbol, "250d", "1d")
        if d15.empty or d1d.empty:
            return None
        price = float(d15["Close"].iloc[-1])
        prev = float(d1d["Close"].iloc[-2])
        change = (price - prev) / prev * 100
        sma200 = d1d["Close"].rolling(200).mean().iloc[-1]
        trend = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        atr = (d1d["High"] - d1d["Low"]).rolling(14).mean().iloc[-1]
        pivot = (d1d["High"].iloc[-2] + d1d["Low"].iloc[-2] + d1d["Close"].iloc[-2]) / 3
        rsi = float(calculate_rsi(d15["Close"]).iloc[-1])
        return {
            "symbol": symbol,
            "price": price,
            "change": change,
            "rsi": rsi,
            "trend": trend,
            "pivot": pivot,
            "tp": price + atr * 1.5,
            "sl": price - atr * 1.2,
            "df": d15,
        }
    except:
        return None

def get_openai_client(api_key):
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except:
        return None

def build_trading_system_prompt(style):
    return (
        "Jesteś analitykiem technicznym. Masz wydać decyzję KUP/SPRZEDAJ/TRZYMAJ.\n"
        "Podawaj:\n"
        "- RSI\n- Trend\n- Momentum\n- Wolumen\n- Poziomy\n- Świece\n- Kontekst\n\n"
        "Format A2-FULL, numerowane bloki:\n"
        "#1 DECYZJA: KUP / SPRZEDAJ / TRZYMAJ\n"
        "#2 UZASADNIENIE:\n"
        "- RSI:\n- Trend:\n- Momentum:\n- Wolumen:\n- Poziomy:\n- Świece:\n- Kontekst:\n"
        "#3 PLAN TRANSAKCJI:\n"
        "ENTRY:\nSL:\nTP:\n"
        "#4 RYZYKO:\n"
        "#5 UWAGI:\n"
        "Trend HOSSA traktuj jako pozytywny, BESSA jako negatywny.\n"
    )

def call_gpt(client, system_prompt, user_prompt):
    if client is None:
        return "(AI OFF)"
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"(AI ERROR: {e})"

def ai_growth_probability(client, symbol, price, rsi, change, trend, pivot):
    system_prompt = (
        "Oszacuj prawdopodobieństwo ruchu w górę i w dół.\n"
        "Format:\n"
        "#1 WZROST: xx%\n"
        "#2 SPADEK: xx%\n"
        "#3 KOMENTARZ:\n"
    )
    user_prompt = (
        f"Symbol: {symbol}\nCena: {price}\nRSI: {rsi}\nZmiana: {change}\nTrend: {trend}\nPivot: {pivot}"
    )
    return call_gpt(client, system_prompt, user_prompt)

def auto_scalper_scan(tickers):
    out = []
    for t in tickers:
        try:
            df = yf_cached(t, "2d", "15m")
            if df.empty or len(df) < 30:
                continue
            close = df["Close"]
            rsi = float(calculate_rsi(close).iloc[-1])
            price = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            zmiana = (price - prev) / prev * 100
            vol = df["Volume"]
            rvol = float(vol.iloc[-1] / (vol.rolling(20).mean().iloc[-1] + 1e-9))
            if (rsi < 30 or rsi > 70) and rvol > 2:
                out.append({"symbol": t, "price": price, "rsi": rsi, "zmiana": zmiana, "rvol": rvol})
        except:
            continue
    return out

def analiza_portfela():
    kurs = pobierz_kurs_usd()
    rows = []
    total = 0
    invested = 0
    for t, (entry, qty) in MOJE_AKCJE.items():
        try:
            df = yf_cached(t, "60d", "1d")
            if df.empty:
                continue
            price = float(df["Close"].iloc[-1])
            zysk = (price - entry) / entry * 100
            mult = kurs if ".WA" not in t else 1
            val = price * qty * mult
            inv = entry * qty * mult
            total += val
            invested += inv
            sma20 = float(df["Close"].rolling(20).mean().iloc[-1])
            status = "OK" if price > sma20 else "SŁABNIE"
            rows.append({
                "Ticker": t,
                "Cena wejścia": entry,
                "Cena teraz": price,
                "Ilość": qty,
                "Zysk %": round(zysk, 2),
                "Wartość PLN": round(val, 2),
                "Status": status,
            })
        except:
            continue
    summary = None
    if invested > 0:
        summary = {
            "total": total,
            "profit": total - invested,
            "profit_pct": (total - invested) / invested * 100,
            "kurs": kurs,
        }
    return rows, summary

with st.sidebar:
    st.title("⚙️ ULTRA v6.1 PRO")

    api_key = st.secrets.get("OPENAI_API_KEY")
    if api_key:
        st.success("Klucz z Secrets")
    else:
        api_key = st.text_input("OpenAI Key", type="password")

    client = get_openai_client(api_key)

    ai_style = st.radio("Styl AI", ["SCALP", "DAY", "SWING", "LONG"], horizontal=True)

    model = st.selectbox(
        "Model GPT",
        ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
        index=0
    )

    preset_choice = st.selectbox(
        "Preset tickerów",
        ["MIX", "Tylko GPW", "Tylko USA", "MOJE 20"],
    )

    if preset_choice == "MIX":
        base_list = load_tickers_default()
    elif preset_choice == "Tylko GPW":
        base_list = ", ".join(preset_gpw_penny())
    elif preset_choice == "Tylko USA":
        base_list = ", ".join(preset_usa_penny())
    else:
        base_list = load_moja20()

    with st.form("tickers_form"):
        tickers_input = st.text_area("Symbole", value=base_list, height=120)
        if st.form_submit_button("OK"):
            if preset_choice == "MOJE 20":
                save_moja20(tickers_input)
            st.rerun()

    market_filter = st.radio("Filtr rynku", ["MIX", "GPW", "USA"], horizontal=True)

    mode = st.selectbox(
        "Tryb",
        [
            "Monitoring rynku",
            "Heatmapa trendu",
            "AUTO‑SCALPER PRO",
            "AI TREND MAPA",
            "AI analiza listy",
            "STX + Portfel",
            "Moje typy",
        ],
    )

    if mode == "AUTO‑SCALPER PRO":
        st_autorefresh(interval=15 * 60 * 1000, key="auto_scalper")
    else:
        refresh = st.slider("Odświeżanie (min)", 15, 60, 30)
        st_autorefresh(interval=refresh * 60 * 1000, key="auto_refresh")

tickers_all = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if market_filter == "GPW":
    tickers_all = [t for t in tickers_all if is_gpw(t)]
elif market_filter == "USA":
    tickers_all = [t for t in tickers_all if is_usa(t)]

tickers_active = [t for t in tickers_all if is_market_open(t)][:20]

st.title("📈 AI PENNY KOMBAJN ULTRA v6.1 PRO")

def style_top_table(df):
    def color_trend(val):
        if isinstance(val, str):
            if "HOSSA" in val:
                return "color: #22c55e; font-weight: 600;"
            if "BESSA" in val:
                return "color: #ef4444; font-weight: 600;"
        return ""
    def color_change(val):
        try:
            v = float(val)
        except:
            return ""
        if v > 0:
            return "color: #22c55e;"
        if v < 0:
            return "color: #ef4444;"
        return "color: #eab308;"
    styler = df.style.background_gradient(
        subset=["rsi", "change"],
        cmap="RdYlGn_r"
    ).applymap(color_trend, subset=["trend"]).applymap(color_change, subset=["change"])
    return styler

def top_okazje_zagrozenia(data):
    if not data:
        return None, None
    df = pd.DataFrame([
        {"symbol": d["symbol"], "change": d["change"], "rsi": d["rsi"], "trend": d["trend"]}
        for d in data
    ])
    ok = df.sort_values(["rsi", "change"]).head(5)
    zag = df.sort_values(["rsi", "change"], ascending=[False, False]).head(5)
    return ok, zag

if mode == "Monitoring rynku":
    if not tickers_active:
        st.info("Brak aktywnych tickerów.")
    else:
        sort_key = st.selectbox("Sortowanie", ["RSI ↑", "Zmiana % ↓"])
        data_list = []
        for t in tickers_active:
            a = get_analysis(t)
            if a:
                data_list.append(a)

        if not data_list:
            st.warning("Brak danych.")
        else:
            if sort_key.startswith("RSI"):
                data_list = sorted(data_list, key=lambda x: x["rsi"])
            else:
                data_list = sorted(data_list, key=lambda x: x["change"], reverse=True)

            st.subheader("Monitoring rynku")

            ok, zag = top_okazje_zagrozenia(data_list)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🟢 TOP 5 okazji")
                if ok is not None and not ok.empty:
                    st.dataframe(style_top_table(ok.set_index("symbol")), use_container_width=True)
            with c2:
                st.markdown("#### 🔴 TOP 5 zagrożeń")
                if zag is not None and not zag.empty:
                    st.dataframe(style_top_table(zag.set_index("symbol")), use_container_width=True)

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
                    st.write(f"Pivot: {d['pivot']:.4f} | RSI: {d['rsi']:.1f}")
                    st.write(f"TP: {d['tp']:.4f} | SL: {d['sl']:.4f}")

                    if st.button(f"AI decyzja {d['symbol']}", key=f"ai_{d['symbol']}"):
                        system_prompt = build_trading_system_prompt(ai_style)
                        prompt = (
                            f"Symbol: {d['symbol']}\n"
                            f"Cena: {d['price']:.4f}\n"
                            f"Trend: {d['trend']}\n"
                            f"RSI: {d['rsi']:.1f}\n"
                            f"Pivot: {d['pivot']:.4f}\n"
                            f"TP: {d['tp']:.4f}\n"
                            f"SL: {d['sl']:.4f}\n"
                            f"Zmiana: {d['change']:.2f}%\n"
                            "Wydaj decyzję w formacie A2-FULL z blokami #1–#5."
                        )
                        ans = call_gpt(client, system_prompt, prompt)
                        st.markdown(ans, unsafe_allow_html=True)

                    if st.button(f"Wzrost % {d['symbol']}", key=f"grow_{d['symbol']}"):
                        ans = ai_growth_probability(
                            client,
                            d["symbol"],
                            d["price"],
                            d["rsi"],
                            d["change"],
                            d["trend"],
                            d["pivot"],
                        )
                        st.markdown(ans, unsafe_allow_html=True)

                with c2:
                    df = d["df"]
                    if df is None or df.empty or len(df) < 2:
                        st.warning("Brak danych do wykresu.")
                        continue

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

elif mode == "Heatmapa trendu":
    st.subheader("🔥 NEON HEATMAPA TRENDÓW (RSI / Zmiana % / Trend)")

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
                sma200 = float(close.rolling(200).mean().iloc[-1])
                trend = 1 if price > sma200 else -1
                rows.append({
                    "Ticker": t,
                    "RSI": rsi,
                    "Zmiana %": zmiana,
                    "Trend": trend
                })
            except:
                continue

        if not rows:
            st.warning("Brak danych do heatmapy.")
        else:
            df_hm = pd.DataFrame(rows).set_index("Ticker")
            metric = st.selectbox("Metryka", ["RSI", "Zmiana %", "Trend"])
            fig = px.imshow(
                df_hm[[metric]].T,
                color_continuous_scale=[
                    "#22c55e",
                    "#eab308",
                    "#ef4444"
                ],
                aspect="auto"
            )
            fig.update_layout(
                template="plotly_dark",
                height=260,
                margin=dict(l=0, r=0, t=0, b=0),
                coloraxis_colorbar=dict(
                    title=metric,
                    tickfont=dict(color="#e5e7eb"),
                    titlefont=dict(color="#e5e7eb")
                )
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                df_hm.sort_values(metric, ascending=(metric == "RSI")).style.background_gradient(
                    subset=[metric],
                    cmap="RdYlGn_r"
                ),
                use_container_width=True
            )

elif mode == "AUTO‑SCALPER PRO":
    st.subheader("AUTO‑SCALPER PRO – sygnały 15m")

    if not tickers_active:
        st.info("Brak aktywnych tickerów.")
    else:
        sygnaly = auto_scalper_scan(tickers_active)

        if not sygnaly:
            st.warning("Brak sygnałów scalp.")
        else:
            df_sig = pd.DataFrame(sygnaly)
            st.success(f"Znaleziono {len(sygnaly)} sygnałów.")
            st.dataframe(
                df_sig.style.background_gradient(
                    subset=["rsi", "zmiana", "rvol"],
                    cmap="RdYlGn_r"
                ),
                use_container_width=True
            )

            opis = "Sygnały scalp:\n"
            for s in sygnaly:
                opis += f"- {s['symbol']}: {s['price']:.4f}, RSI {s['rsi']:.1f}, zmiana {s['zmiana']:.2f}%, RVOL {s['rvol']:.1f}x\n"

            system_prompt = build_trading_system_prompt("SCALP")
            ans = call_gpt(client, system_prompt, opis + "\nWybierz najlepsze wejścia scalp w formacie A2-FULL.")
            st.markdown(ans, unsafe_allow_html=True)

elif mode == "AI TREND MAPA":
    st.subheader("AI TREND MAPA – ocena rynku")

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
                sma200 = float(close.rolling(200).mean().iloc[-1])
                trend = "HOSSA" if price > sma200 else "BESSA"
                rows.append({"symbol": t, "price": price, "rsi": rsi, "zmiana": zmiana, "trend": trend})
            except:
                continue

        if not rows:
            st.warning("Brak danych.")
        else:
            text = "Oceń rynek na podstawie listy spółek.\n\n"
            for r in rows:
                text += f"- {r['symbol']}: {r['price']:.4f}, RSI {r['rsi']:.1f}, zmiana {r['zmiana']:.2f}%, {r['trend']}\n"

            system_prompt = (
                "Oceń rynek: dominujący trend, ryzyko, najlepsze sektory, agresywne czy selektywne wejścia.\n"
                "Użyj numerowanych bloków:\n"
                "#1 DOMINUJĄCY TREND\n#2 RYZYKO\n#3 NAJLEPSZE SEKTORY\n#4 STYL WEJŚĆ\n#5 PODSUMOWANIE\n"
                "Trend HOSSA traktuj jako zielony, BESSA jako czerwony (w opisie)."
            )
            ans = call_gpt(client, system_prompt, text)
            st.markdown(ans, unsafe_allow_html=True)

elif mode == "AI analiza listy":
    st.subheader("AI analiza – 20 aktywnych")

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
            st.warning("Brak danych.")
        else:
            text = "Analiza listy w stylu " + ai_style + ":\n\n"
            for r in rows:
                text += f"- {r['symbol']}: {r['price']:.4f}, RSI {r['rsi']:.1f}, zmiana {r['zmiana']:.2f}%\n"

            system_prompt = build_trading_system_prompt(ai_style)
            ans = call_gpt(client, system_prompt, text + "\nWydaj decyzje A2-FULL dla każdej spółki, z blokami #1–#5.")
            st.markdown(ans, unsafe_allow_html=True)

elif mode == "STX + Portfel":
    st.subheader("STX + Portfel")

    rows, summary = analiza_portfela()
    if rows:
        st.dataframe(
            pd.DataFrame(rows).style.background_gradient(
                subset=["Zysk %", "Wartość PLN"],
                cmap="RdYlGn"
            ),
            use_container_width=True
        )

        if summary:
            c1, c2, c3 = st.columns(3)
            c1.metric("Wartość portfela", f"{summary['total']:.2f} PLN")
            c2.metric("Zysk/Strata", f"{summary['profit']:.2f} PLN")
            c3.metric("USD/PLN", f"{summary['kurs']:.2f}")

    st.markdown("---")
    st.markdown("### STX.WA – wykres + AI")

    stx = get_analysis("STX.WA")
    if stx:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Cena", f"{stx['price']:.4f}", f"{stx['change']:.2f}%")
            st.write(f"Pivot: {stx['pivot']:.4f}")
            st.write(f"RSI: {stx['rsi']:.1f}")
            st.write(f"TP: {stx['tp']:.4f}")
            st.write(f"SL: {stx['sl']:.4f}")

            if st.button("AI STX.WA", key="ai_stx"):
                system_prompt = build_trading_system_prompt(ai_style)
                prompt = (
                    f"Symbol: STX.WA\nCena: {stx['price']:.4f}\nTrend: {stx['trend']}\n"
                    f"RSI: {stx['rsi']:.1f}\nPivot: {stx['pivot']:.4f}\nTP: {stx['tp']:.4f}\n"
                    f"SL: {stx['sl']:.4f}\nZmiana: {stx['change']:.2f}%\n"
                    "Wydaj decyzję A2-FULL z blokami #1–#5."
                )
                ans = call_gpt(client, system_prompt, prompt)
                st.markdown(ans, unsafe_allow_html=True)

        with c2:
            df = stx["df"]
            if df is None or df.empty or len(df) < 2:
                st.warning("Brak danych do wykresu.")
            else:
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
                fig.add_hline(y=stx["pivot"], line_dash="dot", line_color="#e5e7eb")
                fig.update_layout(template="plotly_dark", height=360, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)

elif mode == "Moje typy":
    st.subheader("MOJE 20 – aktywne")

    moja20_raw = load_moja20()
    moja20_list = [t.strip().upper() for t in moja20_raw.split(",") if t.strip()]
    moja20_active = [t for t in moja20_list if is_market_open(t)][:20]

    if not moja20_active:
        st.info("Brak aktywnych spółek.")
    else:
        data_list = []
        for t in moja20_active:
            a = get_analysis(t)
            if a:
                data_list.append(a)

        if not data_list:
            st.warning("Brak danych.")
        else:
            st.markdown("#### Mini‑monitor")
            cols = st.columns(2)

            for i, d in enumerate(data_list):
                with cols[i % 2]:
                    st.markdown(f"**{d['symbol']}** – {d['price']:.4f} ({d['change']:.2f}%) | RSI {d['rsi']:.1f}")
                    df = d["df"]
                    if df is None or df.empty or len(df) < 2:
                        st.warning("Brak danych do wykresu.")
                        continue
                    fig = go.Figure(
                        data=[
                            go.Candlestick(
                                x=df.index[-40:],
                                open=df["Open"][-40:],
                                high=df["High"][-40:],
                                low=df["Low"][-40:],
                                close=df["Close"][-40:],
                                increasing_line_color="#22c55e",
                                decreasing_line_color="#ef4444",
                            )
                        ]
                    )
                    fig.update_layout(template="plotly_dark", height=180, margin=dict(l=0, r=0, t=0, b=0))
                    st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.markdown("### AI analiza MOJE 20")

            if st.button("AI analiza MOJE 20", key="ai_moje20"):
                text = "Analiza MOJE 20:\n\n"
                for d in data_list:
                    text += (
                        f"- {d['symbol']}: {d['price']:.4f}, RSI {d['rsi']:.1f}, "
                        f"zmiana {d['change']:.2f}%, {d['trend']}\n"
                    )
                system_prompt = build_trading_system_prompt(ai_style)
                ans = call_gpt(client, system_prompt, text + "\nWydaj decyzje A2-FULL z blokami #1–#5.")
                st.markdown(ans, unsafe_allow_html=True)
