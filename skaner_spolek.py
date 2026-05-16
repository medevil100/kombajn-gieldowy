
import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from openai import OpenAI

# ================== KONFIGURACJA STRONY ==================
st.set_page_config(page_title="3× Prawdziwe AI — Skaner Groszówek (PL + USA)", layout="wide")

st.markdown("""
<style>
body { background-color: #020617; color: #e5e7eb; }
.box { padding: 10px; border-radius: 10px; margin-top: 10px; color: white; font-size: 14px; }
.trend-box { padding: 8px; border-radius: 8px; margin-top: 10px; color: white; font-size: 14px; }
.trend-bull { background-color: #14532d; border: 2px solid #22c55e; }
.trend-bear { background-color: #7f1d1d; border: 2px solid #ef4444; }
.trend-side { background-color: #78350f; border: 2px solid #fbbf24; }
.plot-border { border: 3px solid #6f42c1; border-radius: 12px; padding: 8px; margin-top: 10px; }
.alert-box { padding:8px; border-radius:8px; margin-top:6px; font-size:13px; color:#e5e7eb; }
.alert-bull { background:#064e3b; border:1px solid #22c55e; }
.alert-bear { background:#7f1d1d; border:1px solid #ef4444; }
.alert-vol { background:#1e293b; border:1px solid #facc15; }
.alert-vsa { background:#111827; border:1px solid #38bdf8; }
.info-box { padding:10px; border-radius:8px; margin-top:10px; background:#020617; border:1px solid #374151; font-size:13px; }
</style>
""", unsafe_allow_html=True)

st.title("📈 3× Prawdziwe AI — Skaner Groszówek (PL + USA) — wiele spółek, 3 werdykty, 1 tabela")

# ================== OPENAI CLIENT ==================
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ================== NARZĘDZIA ==================
def normalize_ticker(t: str) -> str:
    t = t.upper().strip()
    if len(t) <= 4 and "." not in t:
        return t + ".WA"
    return t

def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    ticker = normalize_ticker(ticker)

    is_gpw = ticker.endswith(".WA")
    if is_gpw and tf != "D1":
        return pd.DataFrame()

    interval = "1d" if tf == "D1" else "60m"
    period = "1y" if tf == "D1" else "60d"

    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=False
        )
    except Exception:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        try:
            df.columns = df.columns.get_level_values(-1)
        except:
            df.columns = [c[-1] if isinstance(c, tuple) else c for c in df.columns]

    df.columns = [str(c).strip() for c in df.columns]

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(set(df.columns)):
        return pd.DataFrame()

    df = df.fillna(method="ffill").fillna(method="bfill")
    if df.empty or df["Close"].isna().all():
        return pd.DataFrame()

    return df

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    for w in [20, 50, 100, 200]:
        df[f"SMA{w}"] = close.rolling(w).mean()

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["BB_upper"] = ma20 + 2 * std20
    df["BB_lower"] = ma20 - 2 * std20

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    roll_up = gain.rolling(14).mean()
    roll_down = loss.rolling(14).mean()
    rs = roll_up / (roll_down + 1e-9)
    df["RSI14"] = 100 - (100 / (1 + rs))

    high = df["High"]
    low = df["Low"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()

    df["VolMA20"] = df["Volume"].rolling(20).mean()

    return df

def detect_trend_from_df(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)

    if pd.notna(sma200):
        if last["Close"] > sma200 * 1.01:
            return "bull"
        if last["Close"] < sma200 * 0.99:
            return "bear"

    if pd.notna(sma50):
        if last["Close"] > sma50:
            return "bull"
        if last["Close"] < sma50:
            return "bear"

    return "side"

def compute_trend_score(df: pd.DataFrame, trend_code: str) -> float:
    last = df.iloc[-1]
    score = 0

    if trend_code == "bull": score += 30
    if last["Close"] < 5: score += 10

    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)
    rsi = last.get("RSI14", np.nan)

    if pd.notna(sma50) and last["Close"] > sma50: score += 15
    if pd.notna(sma200) and last["Close"] > sma200: score += 15
    if pd.notna(sma50) and pd.notna(sma200) and sma50 > sma200: score += 20

    if pd.notna(rsi):
        if 55 <= rsi <= 70: score += 10
        elif 50 <= rsi < 55: score += 5

    return score

def detect_trend_alerts(df: pd.DataFrame, ticker: str, trend_code: str) -> list:
    alerts = []
    if len(df) < 3:
        return alerts

    last = df.iloc[-1]
    prev = df.iloc[-2]
    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)

    if pd.notna(sma50) and pd.notna(prev.get("SMA50", np.nan)):
        prev_rel = prev["Close"] > prev["SMA50"]
        now_rel = last["Close"] > sma50
        if not prev_rel and now_rel and trend_code == "bull":
            alerts.append(f"🔥 {ticker}: świeży sygnał bull (Close przebił SMA50, trend wzrostowy).")

    if pd.notna(sma200) and pd.notna(prev.get("SMA200", np.nan)):
        prev_below = prev["Close"] > prev["SMA200"]
        now_below = last["Close"] < sma200
        if prev_below and now_below:
            alerts.append(f"⚠️ {ticker}: przełamanie wsparcia SMA200 (możliwa zmiana trendu).")

    return alerts

def detect_volume_breakout_signals(df: pd.DataFrame, ticker: str) -> list:
    sigs = []
    if "VolMA20" not in df.columns or "ATR14" not in df.columns:
        return sigs
    last = df.iloc[-1]
    vol = last["Volume"]
    vol_ma = last["VolMA20"]
    atr = last["ATR14"]
    if pd.isna(vol_ma) or pd.isna(atr) or atr == 0:
        return sigs

    body = abs(last["Close"] - last["Open"])
    cond_vol2 = vol > 2 * vol_ma
    cond_vol15 = vol > 1.5 * vol_ma
    cond_body = body > atr
    cond_bb = (last["Close"] > last["BB_upper"]) or (last["Close"] < last["BB_lower"])

    if cond_vol2 and cond_body and cond_bb:
        sigs.append(f"🔥 {ticker}: silne wybicie (wolumen >2×, świeca > ATR, wybicie z BB).")
    elif cond_vol15 and cond_body:
        sigs.append(f"⚡ {ticker}: wybicie wolumenowe (wolumen >1.5×, świeca > ATR).")

    if cond_vol2 and body < atr * 0.5 and last["Close"] < last["Open"]:
        sigs.append(f"📉 {ticker}: możliwa dystrybucja (duży wolumen, słaba świeca).")
    if cond_vol2 and body < atr * 0.5 and last["Close"] > last["Open"]:
        sigs.append(f"📈 {ticker}: możliwa akumulacja (duży wolumen, świeca z małym spreadem).")

    return sigs

def plot_multichart(df: pd.DataFrame, ticker: str):
    df = df.tail(120)
    x = df.index

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.05, row_heights=[0.55, 0.25, 0.20]
    )

    fig.add_trace(go.Candlestick(
        x=x, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        increasing_line_color="#00ff88",
        decreasing_line_color="#ff0055",
        name="Świece"
    ), row=1, col=1)

    for w, color in [(20, "#ffaa00"), (50, "#00e5ff"), (100, "#cc66ff"), (200, "#888888")]:
        col = f"SMA{w}"
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=x, y=df[col],
                line=dict(color=color, width=1.8),
                name=f"SMA{w}"
            ), row=1, col=1)

    if "BB_upper" in df.columns and "BB_lower" in df.columns:
        fig.add_trace(go.Scatter(
            x=x, y=df["BB_upper"],
            line=dict(color="#60a5fa", dash="dash", width=1.5),
            name="BB Upper"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=x, y=df["BB_lower"],
            line=dict(color="#60a5fa", dash="dash", width=1.5),
            name="BB Lower"
        ), row=1, col=1)

    if "RSI14" in df.columns:
        fig.add_trace(go.Scatter(
            x=x, y=df["RSI14"],
            line=dict(color="#ffff00", width=2),
            name="RSI14"
        ), row=2, col=1)
        fig.add_hline(y=70, line=dict(color="#ff4444", dash="dot"), row=2, col=1)
        fig.add_hline(y=30, line=dict(color="#44ff44", dash="dot"), row=2, col=1)

    fig.add_trace(go.Bar(
        x=x, y=df["Volume"],
        marker_color="#aa44ff",
        name="Volume"
    ), row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=800,
        margin=dict(l=20, r=20, t=30, b=20),
        paper_bgcolor="#020617",
        plot_bgcolor="#020617",
        font=dict(color="#e5e7eb"),
        title=f"📊 MULTICHART — {ticker}"
    )

    st.markdown('<div class="plot-border">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ================== PRAWIDZWE AI — WERDYKT DLA JEDNEJ SPÓŁKI ==================
def build_tech_summary_for_ai(df: pd.DataFrame, row: pd.Series) -> str:
    last = df.iloc[-1]
    close = last["Close"]
    rsi = last.get("RSI14", np.nan)
    atr = last.get("ATR14", np.nan)
    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)
    bb_upper = last.get("BB_upper", np.nan)
    bb_lower = last.get("BB_lower", np.nan)

    trend = row["Trend"]
    score = row["TrendScore"]

    txt = f"""
Ticker: {row['Ticker']}
Close: {close:.4f}
Trend: {trend}
TrendScore: {score:.2f}
RSI14: {rsi:.2f if not np.isnan(rsi) else 'brak'}
ATR14: {atr:.4f if not np.isnan(atr) else 'brak'}
SMA50: {sma50:.4f if not np.isnan(sma50) else 'brak'}
SMA200: {sma200:.4f if not np.isnan(sma200) else 'brak'}
BB_upper: {bb_upper:.4f if not np.isnan(bb_upper) else 'brak'}
BB_lower: {bb_lower:.4f if not np.isnan(bb_lower) else 'brak'}
"""
    return txt

def call_model_for_verdict(model_name: str, role_desc: str, summary: str) -> str:
    """
    Zwraca jedno słowo: KUP / CZEKAJ / SPRZEDAJ
    """
    resp = client.chat.completions.create(
        model=model_name,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": f"""
Jesteś {role_desc}.
Masz podjąć decyzję tradingową dla groszówki na podstawie danych technicznych.
Odpowiadasz TYLKO jednym słowem (bez kropki, bez komentarza):
KUP
CZEKAJ
SPRZEDAJ
Nic więcej.
"""
            },
            {
                "role": "user",
                "content": f"Dane techniczne spółki:\n{summary}\n\nJaki jest Twój werdykt?"
            }
        ]
    )
    raw = resp.choices[0].message.content.strip().upper()
    if "KUP" in raw:
        return "KUP"
    if "SPRZED" in raw:
        return "SPRZEDAJ"
    if "CZEKAJ" in raw:
        return "CZEKAJ"
    # fallback gdyby model odleciał
    return "CZEKAJ"

def verdict_for_single_stock_real_ai(df: pd.DataFrame, row: pd.Series):
    summary = build_tech_summary_for_ai(df, row)

    v1 = call_model_for_verdict("o3-mini", "ostrożnym modelem rozumującym (o3-mini)", summary)
    v2 = call_model_for_verdict("gpt-4o", "głównym analitykiem technicznym (gpt-4o)", summary)
    v3 = call_model_for_verdict("gpt-4o-mini", "szybkim weryfikatorem sygnałów (gpt-4o-mini)", summary)

    votes = [v1, v2, v3]
    final = max(set(votes), key=votes.count)

    return v1, v2, v3, final

# ================== UI — SKANER WIELU SPÓŁEK ==================
st.markdown("---")
st.subheader("🧪 Skaner groszówek PL + USA — ranking + 3× prawdziwe AI dla każdej spółki")

col_left, col_right = st.columns([2, 1])

with col_left:
    tickers_text = st.text_area(
        "Lista tickerów (oddzielone przecinkami lub nową linią):",
        "HRT.WA,CFS.WA,PRT.WA,ATT.WA,STX.WA,PUR.WA,BCS.WA,KCH.WA,GTN.WA,LBW.WA,"
        "PGV.WA,HPE.WA,DNS.WA,ZUK.WA,VVD.WA,HIVE,MLN.WA,MER.WA,APS.WA,NVG.WA,"
        "IOVA,PLRX,HUMA,TCRX,GOSS,MREO,ADTX",
        height=140,
    )
    only_pennies = st.checkbox("Filtruj tylko groszówki (Close < 5)", value=True)
    tf_scan = st.selectbox("Interwał skanera:", ["D1", "H1"])
    tf_scan_code = "D1" if tf_scan == "D1" else "H1"
    run_scan = st.button("Skanuj rynek + odpal 3× AI dla każdej spółki")

with col_right:
    st.markdown("""
    <div class="info-box">
    <b>Uwaga:</b><br/>
    • To są prawdziwe modele OpenAI (o3-mini, gpt-4o, gpt-4o-mini).<br/>
    • Dla każdej spółki są 3 osobne wywołania API → 100 spółek = 300 requestów.<br/>
    • Będzie to kosztować i chwilę potrwa, ale werdykty są realne, nie symulowane.<br/>
    • GPW w Yahoo ma tylko D1, USA ma D1/H1.
    </div>
    """, unsafe_allow_html=True)

ranking_df = None
scan_results = {}
all_alerts = []
all_volume_signals = []

if run_scan:
    raw = tickers_text.replace("\n", ",")
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    tickers = list(dict.fromkeys(tickers))
    tickers = [normalize_ticker(t) for t in tickers]

    rows = []
    progress = st.progress(0.0, text="Pobieranie danych i liczenie wskaźników...")
    total = len(tickers)
    done = 0

    for t in tickers:
        df_t = get_ohlc(t, tf_scan_code)
        done += 1
        progress.progress(done / total, text=f"Pobieranie i analiza: {t} ({done}/{total})")

        if df_t.empty:
            continue
        df_t = add_indicators(df_t)
        trend_code = detect_trend_from_df(df_t)
        last = df_t.iloc[-1]

        close = float(last["Close"])
        rsi = float(last.get("RSI14", np.nan)) if not pd.isna(last.get("RSI14", np.nan)) else np.nan
        atr = float(last.get("ATR14", np.nan)) if not pd.isna(last.get("ATR14", np.nan)) else np.nan
        vol = float(last.get("Volume", np.nan)) if not pd.isna(last.get("Volume", np.nan)) else np.nan
        vol_ma = float(last.get("VolMA20", np.nan)) if not pd.isna(last.get("VolMA20", np.nan)) else np.nan
        score = compute_trend_score(df_t, trend_code)

        if only_pennies and close >= 5:
            continue

        rows.append({
            "Ticker": t,
            "Trend": trend_code,
            "Close": round(close, 4),
            "RSI14": round(rsi, 2) if not np.isnan(rsi) else np.nan,
            "ATR14": round(atr, 4) if not np.isnan(atr) else np.nan,
            "Volume": vol,
            "VolMA20": vol_ma,
            "TrendScore": round(score, 2),
        })
        scan_results[t] = df_t

        all_alerts.extend(detect_trend_alerts(df_t, t, trend_code))
        all_volume_signals.extend(detect_volume_breakout_signals(df_t, t))

    progress.empty()

    if rows:
        ranking_df = pd.DataFrame(rows)
        ranking_df = ranking_df.sort_values("TrendScore", ascending=False).reset_index(drop=True)

        st.markdown("### 🏆 Ranking spółek (wg TrendScore)")
        st.dataframe(ranking_df, use_container_width=True)

        st.markdown("### 🧠 3× Prawdziwe AI — Werdykty dla wszystkich spółek")
        verdict_rows = []
        total_ai = len(ranking_df)
        ai_prog = st.progress(0.0, text="Modele AI analizują spółki...")
        done_ai = 0

        for _, row in ranking_df.iterrows():
            t = row["Ticker"]
            df_t = scan_results.get(t)
            if df_t is None or df_t.empty:
                continue

            done_ai += 1
            ai_prog.progress(done_ai / total_ai, text=f"AI analizuje: {t} ({done_ai}/{total_ai})")

            v1, v2, v3, final = verdict_for_single_stock_real_ai(df_t, row)
            verdict_rows.append({
                "Ticker": t,
                "Trend": row["Trend"],
                "Close": row["Close"],
                "RSI14": row["RSI14"],
                "Score": row["TrendScore"],
                "o3-mini": v1,
                "gpt-4o": v2,
                "gpt-4o-mini": v3,
                "FINAL": final,
            })

        ai_prog.empty()

        if verdict_rows:
            verdict_df = pd.DataFrame(verdict_rows)
            verdict_df["FINAL_rank"] = verdict_df["FINAL"].map({"KUP": 0, "CZEKAJ": 1, "SPRZEDAJ": 2})
            verdict_df = verdict_df.sort_values(["FINAL_rank", "Score"], ascending=[True, False]).drop(columns=["FINAL_rank"])
            st.dataframe(verdict_df, use_container_width=True)
        else:
            st.info("Brak spółek do oceny werdyktów.")

        st.markdown("### 🚨 Alerty trendów i wolumenów")
        if not all_alerts and not all_volume_signals:
            st.info("Brak silnych alertów dla podanych tickerów.")
        else:
            for a in all_alerts:
                css = "alert-bull" if ("bull" in a or "🔥" in a) else "alert-bear"
                st.markdown(f'<div class="alert-box {css}">{a}</div>', unsafe_allow_html=True)
            for v in all_volume_signals:
                css = "alert-vsa" if ("akumulacja" in v or "dystrybucja" in v) else "alert-vol"
                st.markdown(f'<div class="alert-box {css}">{v}</div>', unsafe_allow_html=True)

        st.markdown("### 🔍 Podgląd wykresu wybranej spółki")
        tickers_list = ranking_df["Ticker"].tolist()
        sel = st.selectbox("Wybierz ticker do podglądu wykresu:", tickers_list)
        if sel:
            df_sel = scan_results.get(sel)
            if df_sel is not None and not df_sel.empty:
                plot_multichart(df_sel, sel)
    else:
        st.warning("Brak danych dla podanych tickerów (dla wybranego interwału i filtrów).")

st.markdown("""
<div class="info-box">
To narzędzie używa prawdziwych modeli OpenAI (o3-mini, gpt-4o, gpt-4o-mini)
do wydawania werdyktów KUP / CZEKAJ / SPRZEDAJ dla wielu spółek jednocześnie.
To nie jest rekomendacja inwestycyjna — traktuj to jako zaawansowany filtr / skaner.
</div>
""", unsafe_allow_html=True)
