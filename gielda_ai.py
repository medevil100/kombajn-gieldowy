
import streamlit as st
from openai import OpenAI
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
st.set_page_config(page_title="3× AI — Terminal Groszówek", layout="wide")
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ================== STYLE ==================
st.markdown("""
<style>
body {
    background-color: #020617;
    color: #e5e7eb;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.box {
    padding: 15px;
    border-radius: 10px;
    font-size: 16px;
    margin-top: 15px;
    color: white;
}
.swing  { background-color: #0f5132; }
.day    { background-color: #0d6efd; }
.long   { background-color: #6f42c1; }

.trend-box {
    padding: 10px;
    border-radius: 8px;
    margin-top: 10px;
    color: white;
    font-size: 15px;
}
.trend-bear   { background-color: #d9534f; border: 2px solid #b52b27; }
.trend-bull   { background-color: #5cb85c; border: 2px solid #3d8b3d; }
.trend-side   { background-color: #f0ad4e; border: 2px solid #c77c11; }

.info-box {
    padding: 10px;
    border-radius: 8px;
    margin-top: 10px;
    background-color: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
    font-size: 14px;
}

.plot-border {
    border: 3px solid #6f42c1;
    border-radius: 12px;
    padding: 8px;
    margin-top: 10px;
}

.heatmap-tile {
    display: inline-block;
    width: 110px;
    height: 80px;
    margin: 4px;
    border-radius: 8px;
    padding: 6px;
    font-size: 12px;
    color: #e5e7eb;
    box-shadow: 0 0 10px rgba(0,0,0,0.6);
}

.alert-box {
    padding: 8px 10px;
    border-radius: 8px;
    margin-top: 6px;
    font-size: 13px;
    color: #e5e7eb;
}
.alert-bull { background-color: #064e3b; border: 1px solid #22c55e; }
.alert-bear { background-color: #7f1d1d; border: 1px solid #f97373; }
.alert-vol  { background-color: #1e293b; border: 1px solid #facc15; }
.alert-vsa  { background-color: #111827; border: 1px solid #38bdf8; }
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Terminal Groszówek (PL + USA)")

# ================== AI MODUŁY ==================

def ai_swing(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[{"role": "user", "content": f"""
Jesteś agresywnym traderem swingowym.
Analiza SWING dla {ticker} (groszówka / spekulacyjna spółka):
{text}
Zadanie: 2–3 zdania, dynamicznie, bez kopiowania liczb, skup się na kierunku i ryzyku.
"""}],
    )
    return r.choices[0].message.content.strip()

def ai_day(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{"role": "user", "content": f"""
Jesteś precyzyjnym daytraderem.
Analiza DAYTRADING dla {ticker}:
{text}
Zadanie: 2–3 zdania, szybko i konkretnie, bez kopiowania liczb.
"""}],
    )
    return r.choices[0].message.content.strip()

def ai_long(ticker, text):
    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": f"""
Jesteś spokojnym analitykiem długoterminowym.
Analiza LONG-TERM dla {ticker} (wysokie ryzyko, groszówka):
{text}
Zadanie: 2–3 zdania, spokojnie i analitycznie, bez kopiowania liczb.
"""}],
    )
    return r.choices[0].message.content.strip()

def ai_meta_pick(market_df: pd.DataFrame, alerts: list, volume_signals: list) -> str:
    base_text = "Dane rynku (wybrane kolumny):\n"
    if not market_df.empty:
        sample = market_df[["Ticker", "Trend", "Close", "TrendScore"]].head(30)
        base_text += sample.to_string(index=False)
    else:
        base_text += "Brak danych.\n"

    base_text += "\n\nAlerty trendów i wolumenów:\n"
    if alerts:
        for a in alerts[:30]:
            base_text += f"- {a}\n"
    if volume_signals:
        base_text += "\nSygnały wolumenowe:\n"
        for v in volume_signals[:30]:
            base_text += f"- {v}\n"

    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": f"""
Jesteś zaawansowanym analitykiem rynku groszówek (PL + USA).
Masz dane o trendach, wolumenie, momentum i alertach.
Na tej podstawie zbuduj własny scoring META i wybierz 3–5 najlepszych spółek
pod kątem potencjału spekulacyjnego (krótko- i średnioterminowego).

Zasady:
- nie kopiuj liczb z danych
- podaj ticker + krótkie uzasadnienie (3–4 zdania)
- uwzględnij: trend, momentum, wolumen, ryzyko, zmienność
- bądź konkretny, ale nie dawaj rekomendacji inwestycyjnych

Dane wejściowe:
{base_text}
"""}],
    )
    return r.choices[0].message.content.strip()

# ================== DANE I WSKAŹNIKI ==================

def normalize_ticker(t: str) -> str:
    t = t.upper().strip()
    if len(t) <= 4 and "." not in t:
        return t + ".WA"
    return t

def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    try:
        if tf == "D1":
            df = yf.download(ticker, period="1y", interval="1d", auto_adjust=False)
        else:
            df = yf.download(ticker, period="30d", interval="60m", auto_adjust=False)
    except:
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

    df = df.dropna()
    if df.empty:
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

# ================== TREND, SCORE, SYGNAŁY ==================

def detect_trend_from_df(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    sma200 = last.get("SMA200", np.nan)
    sma50 = last.get("SMA50", np.nan)

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

def trend_label_and_css(code: str):
    if code == "bull": return "Trend wzrostowy (🐂)", "trend-bull"
    if code == "bear": return "Trend spadkowy (🐻)", "trend-bear"
    return "Trend boczny (➖)", "trend-side"

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

def detect_trend_alerts(df: pd.DataFrame, ticker: str, trend_code: str) -> list:
    alerts = []
    if len(df) < 3:
        return alerts
    last = df.iloc[-1]
    prev = df.iloc[-2]
    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)

    if pd.notna(sma50) and pd.notna(sma200):
        prev_rel = prev["Close"] > prev["SMA50"]
        now_rel = last["Close"] > sma50
        if not prev_rel and now_rel and trend_code == "bull":
            alerts.append(f"🔥 {ticker}: świeży sygnał bull (Close przebił SMA50, trend wzrostowy).")

    if pd.notna(sma200):
        prev_below = prev["Close"] > prev["SMA200"]
        now_below = last["Close"] < sma200
        if prev_below and now_below:
            alerts.append(f"⚠️ {ticker}: przełamanie wsparcia SMA200 (możliwa zmiana trendu).")

    return alerts

# ================== MULTICHART ==================

def plot_multichart(df: pd.DataFrame):
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
        title="📊 MULTICHART — neonowa analiza techniczna"
    )

    st.markdown('<div class="plot-border">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ================== UI: SKANER RYNKU ==================

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("🧪 Skaner groszówek PL + USA — ranking trendów + heatmapa")
    tickers_text = st.text_area(
        "Lista tickerów (oddzielone przecinkami lub nową linią):",
        "AAPL, TSLA, NVDA, CDR, AMC, MULN",
        height=100,
    )
    only_pennies = st.checkbox("Filtruj tylko groszówki (Close < 5)", value=True)
    tf_scan = st.selectbox("Interwał skanera:", ["D1", "H1"])
    tf_scan_code = "D1" if tf_scan == "D1" else "H1"
    run_scan = st.button("Skanuj rynek i zbuduj ranking")

with col_right:
    st.subheader("⚙️ Ustawienia AI META")
    use_ai_meta = st.checkbox("Uruchom AI META po skanie (wybór najlepszych spółek)", value=True)

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
    for t in tickers:
        try:
            df_t = get_ohlc(t, tf_scan_code)
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
        except Exception:
            continue

    if rows:
        ranking_df = pd.DataFrame(rows)
        ranking_df = ranking_df.sort_values("TrendScore", ascending=False).reset_index(drop=True)

        st.markdown("### 🏆 Ranking spółek (wg TrendScore)")
        st.dataframe(ranking_df, use_container_width=True)

        st.markdown("### 🌈 Heatmapa PRO (trend + RSI + wolumen + ATR)")
        if not ranking_df.empty:
            for _, row in ranking_df.iterrows():
                t = row["Ticker"]
                trend = row["Trend"]
                rsi = row["RSI14"]
                atr = row["ATR14"]
                vol = row["Volume"]
                vol_ma = row["VolMA20"]

                if trend == "bull":
                    bg = "#14532d"
                elif trend == "bear":
                    bg = "#7f1d1d"
                else:
                    bg = "#78350f"

                border_color = "#4ade80"
                if not np.isnan(rsi):
                    if rsi > 70:
                        border_color = "#f97316"
                    elif rsi < 30:
                        border_color = "#38bdf8"

                vol_icon = "🌑"
                if not np.isnan(vol) and not np.isnan(vol_ma) and vol_ma > 0:
                    if vol > 2 * vol_ma:
                        vol_icon = "🔥"
                    elif vol > 1.5 * vol_ma:
                        vol_icon = "⚡"

                sat = 0.6
                if not np.isnan(atr) and row["Close"] > 0:
                    rel_vol = min(atr / row["Close"], 0.2)
                    sat = 0.4 + rel_vol

                tile_html = f"""
                <div class="heatmap-tile" style="background: {bg}; border: 2px solid {border_color}; opacity:{0.8 + sat*0.2};">
                    <b>{t}</b> {vol_icon}<br/>
                    Trend: {trend}<br/>
                    RSI: {'' if np.isnan(rsi) else round(rsi,1)}<br/>
                    ATR: {'' if np.isnan(atr) else round(atr,3)}
                </div>
                """
                st.markdown(tile_html, unsafe_allow_html=True)
        st.markdown("---")

        st.subheader("🚨 Alerty trendów i wolumenów")
        if not all_alerts and not all_volume_signals:
            st.info("Brak silnych alertów dla podanych tickerów.")
        else:
            for a in all_alerts:
                css = "alert-bull" if "bull" in a or "🔥" in a else "alert-bear"
                st.markdown(f'<div class="alert-box {css}">{a}</div>', unsafe_allow_html=True)
            for v in all_volume_signals:
                css = "alert-vol"
                if "akumulacja" in v or "dystrybucja" in v:
                    css = "alert-vsa"
                st.markdown(f'<div class="alert-box {css}">{v}</div>', unsafe_allow_html=True)

        if use_ai_meta:
            st.subheader("🧠 AI META — wybór najlepszych spółek")
            meta_text = ai_meta_pick(ranking_df, all_alerts, all_volume_signals)
            st.markdown(f'<div class="box long"><b>Wynik AI META:</b><br>{meta_text}</div>', unsafe_allow_html=True)

    else:
        st.warning("Brak danych dla podanych tickerów.")

# ================== ANALIZA POJEDYNCZEJ SPÓŁKI + AI ==================

st.markdown("---")
st.subheader("🤖 Analiza AI wybranej spółki + MULTICHART")

col_a, col_b, col_c = st.columns(3)
with col_a:
    if ranking_df is not None and not ranking_df.empty:
        selected_ticker = st.selectbox("Ticker z rankingu:", ranking_df["Ticker"].tolist())
    else:
        selected_ticker = st.text_input("Ticker:", "AAPL")

with col_b:
    tf_detail = st.selectbox("Interwał analizy:", ["D1", "H1"])
    tf_detail_code = "D1" if tf_detail == "D1" else "H1"

with col_c:
    ai_choice = st.selectbox(
        "Wybierz AI:",
        ["AI Swing — gpt‑4o‑mini", "AI Day — gpt‑4o", "AI Long — o3‑mini"]
    )

user_notes = st.text_area("Twoje notatki / kontekst:", "")

if st.button("Analizuj wybraną spółkę (AI + wykres)"):
    try:
        norm_ticker = normalize_ticker(selected_ticker)
        if ranking_df is not None and norm_ticker in scan_results:
            df_single = scan_results[norm_ticker]
        else:
            df_single = get_ohlc(norm_ticker, tf_detail_code)
            if df_single.empty:
                st.error("Brak danych dla tego tickera / interwału.")
                st.stop()
            df_single = add_indicators(df_single)
    except Exception as e:
        st.error(f"Problem z pobraniem danych dla {selected_ticker}: {e}")
        st.stop()

    trend_code = detect_trend_from_df(df_single)
    trend_label, trend_css = trend_label_and_css(trend_code)

    st.markdown(
        f'<div class="trend-box {trend_css}"><b>Trend główny:</b> {trend_label}</div>',
        unsafe_allow_html=True,
    )

    last = df_single.iloc[-1]
    rsi_val = last.get("RSI14", np.nan)
    rsi_txt = "brak" if pd.isna(rsi_val) else f"{rsi_val:.2f}"

    summary = f"""
Ticker: {norm_ticker}
Interwał: {tf_detail_code}
Trend: {trend_label}
Close: {last['Close']:.2f}
RSI14: {rsi_txt}
Notatki użytkownika: {user_notes}
"""

    if "Swing" in ai_choice:
        wynik = ai_swing(norm_ticker, summary)
        css = "swing"
    elif "Day" in ai_choice:
        wynik = ai_day(norm_ticker, summary)
        css = "day"
    else:
        wynik = ai_long(norm_ticker, summary)
        css = "long"

    st.markdown(f'<div class="box {css}"><b>Wynik AI ({ai_choice}):</b><br>{wynik}</div>', unsafe_allow_html=True)

    with st.expander("📈 MULTICHART — pełna analiza techniczna (realne dane)"):
        plot_multichart(df_single)

st.markdown(
    """
<div class="info-box">
To narzędzie jest eksperymentalnym terminalem analitycznym dla groszówek (PL + USA).
Łączy skaner trendów, heatmapę, alerty wolumenowe, analizę AI META oraz trzy tryby AI (Swing / Day / Long).
Nie jest to rekomendacja inwestycyjna. Zawsze używaj własnego planu i risk managementu.
</div>
""",
    unsafe_allow_html=True,
)
