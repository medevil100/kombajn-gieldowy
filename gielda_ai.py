import streamlit as st
from openai import OpenAI
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
st.set_page_config(page_title="3× AI — Terminal Groszówek", layout="wide")

if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("Brak klucza OPENAI_API_KEY w st.secrets! Dodaj go w konfiguracji Streamlit.")
    st.stop()

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

.heatmap-container {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 15px;
}

.heatmap-tile {
    width: 120px;
    height: 85px;
    border-radius: 8px;
    padding: 8px;
    font-size: 12px;
    color: white;
    box-shadow: 0 0 10px rgba(0,0,0,0.6);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
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

def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    try:
        if tf == "D1":
            df = yf.download(ticker, period="1y", interval="1d", auto_adjust=False, progress=False)
        else:
            df = yf.download(ticker, period="30d", interval="60m", auto_adjust=False, progress=False)

        if df.empty:
            return pd.DataFrame()

        # POPRAWKA: Bezpieczne czyszczenie MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)

        df.columns = [str(c).strip() for c in df.columns]

        if "Close" not in df.columns:
            return pd.DataFrame()

        return df.dropna()
    except Exception:
        return pd.DataFrame()

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
    
    # POPRAWKA: wyciąganie czystych wartości float
    close_val = float(last["Close"].iloc[0]) if isinstance(last["Close"], pd.Series) else float(last["Close"])
    sma200 = float(last["SMA200"].iloc[0]) if isinstance(last.get("SMA200"), pd.Series) else float(last.get("SMA200", np.nan))
    sma50 = float(last["SMA50"].iloc[0]) if isinstance(last.get("SMA50"), pd.Series) else float(last.get("SMA50", np.nan))

    if pd.notna(sma200):
        if close_val > sma200 * 1.01: return "bull"
        if close_val < sma200 * 0.99: return "bear"

    if pd.notna(sma50):
        if close_val > sma50: return "bull"
        if close_val < sma50: return "bear"

    return "side"

def trend_label_and_css(code: str):
    if code == "bull": return "Trend wzrostowy (🐂)", "trend-bull"
    if code == "bear": return "Trend spadkowy (🐻)", "trend-bear"
    return "Trend boczny (➖)", "trend-side"

def compute_trend_score(df: pd.DataFrame, trend_code: str) -> float:
    last = df.iloc[-1]
    score = 0

    close_val = float(last["Close"].iloc[0]) if isinstance(last["Close"], pd.Series) else float(last["Close"])
    sma50 = float(last["SMA50"].iloc[0]) if isinstance(last.get("SMA50"), pd.Series) else float(last.get("SMA50", np.nan))
    sma200 = float(last["SMA200"].iloc[0]) if isinstance(last.get("SMA200"), pd.Series) else float(last.get("SMA200", np.nan))
    rsi = float(last["RSI14"].iloc[0]) if isinstance(last.get("RSI14"), pd.Series) else float(last.get("RSI14", np.nan))

    if trend_code == "bull": score += 30
    if close_val < 5: score += 10

    if pd.notna(sma50) and close_val > sma50: score += 15
    if pd.notna(sma200) and close_val > sma200: score += 15
    if pd.notna(sma50) and pd.notna(sma200) and sma50 > sma200: score += 20

    if pd.notna(rsi):
        if 55 <= rsi <= 70: score += 10
        elif 50 <= rsi < 55: score += 5

    return score

# POPRAWKA: Dokończona funkcja detekcji wolumenu (VSA)
def detect_volume_breakout_signals(df: pd.DataFrame, ticker: str) -> list:
    sigs = []
    if "VolMA20" not in df.columns or "ATR14" not in df.columns:
        return sigs
    last = df.iloc[-1]
    
    vol = float(last["Volume"].iloc[0]) if isinstance(last["Volume"], pd.Series) else float(last["Volume"])
    vol_ma = float(last["VolMA20"].iloc[0]) if isinstance(last["VolMA20"], pd.Series) else float(last["VolMA20"])
    atr = float(last["ATR14"].iloc[0]) if isinstance(last["ATR14"], pd.Series) else float(last["ATR14"])
    close_val = float(last["Close"].iloc[0]) if isinstance(last["Close"], pd.Series) else float(last["Close"])
    open_val = float(last["Open"].iloc[0]) if isinstance(last["Open"], pd.Series) else float(last["Open"])
    bb_upper = float(last["BB_upper"].iloc[0]) if isinstance(last["BB_upper"], pd.Series) else float(last["BB_upper"])
    bb_lower = float(last["BB_lower"].iloc[0]) if isinstance(last["BB_lower"], pd.Series) else float(last["BB_lower"])

    if pd.isna(vol_ma) or pd.isna(atr) or atr == 0:
        return sigs

    body = abs(close_val - open_val)
    cond_vol2 = vol > 2 * vol_ma
    cond_vol15 = vol > 1.5 * vol_ma
    cond_body = body > atr
    cond_bb = (close_val > bb_upper) or (close_val < bb_lower)

    if cond_vol2 and cond_body and cond_bb:
        sigs.append(f"🔥 {ticker}: Silne wybicie VSA z potężnym wolumenem!")
    elif cond_vol15:
        sigs.append(f"⚡ {ticker}: Podwyższony obrót wolumenu (>1.5x MA).")
    
    return sigs

# ================== FUNKCJA WYKRESU PLOTLY ==================
def plot_multichart(df: pd.DataFrame, ticker: str):
    df_plot = df.tail(90)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
    
    # Świecznik
    fig.add_trace(go.Candlestick(
        x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'],
        name="Kurs", legendgroup="1"
    ), row=1, col=1)
    
    # Wskaźniki SMA
    if "SMA50" in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA50'], line=dict(color='cyan', width=1.5), name="SMA50", legendgroup="1"), row=1, col=1)
    if "SMA200" in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA200'], line=dict(color='magenta', width=1.5), name="SMA200", legendgroup="1"), row=1, col=1)
        
    # Wolumen
    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], name="Wolumen", marker_color='orange', legendgroup="2"), row=2, col=1)
    
    fig.update_layout(title=f"Wykres techniczny {ticker}", template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# ================== INTERFEJS I PĘTLA GŁÓWNA ==================
st.sidebar.header("Ustawienia skanera")
market_selection = st.sidebar.selectbox("Wybierz rynek domyślny", ["USA Groszówki", "Polska Spekulacja", "Własna lista"])
timeframe = st.sidebar.selectbox("Interwał danych", ["D1", "1H"])

# Definiowanie list tickerów
if market_selection == "USA Groszówki":
    tickers_input = st.sidebar.text_area("Lista tickerów (rozdziel przecinkami)", value="SNDL, HUBC, OTLY, KAVL, MVIS")
elif market_selection == "Polska Spekulacja":
    tickers_input = st.sidebar.text_area("Lista tickerów (GPW / NewConnect)", value="BBD.WA, ATT.WA, COG.WA, BIO.WA")
else:
    tickers_input = st.sidebar.text_area("Wpisz tickery", value="AAPL, TSLA")

ticker_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if st.sidebar.button("Uruchom Skaner i AI 🚀"):
    all_market_data = []
    global_alerts = []
    global_volume_sigs = []
    processed_dfs = {}

    progress_bar = st.progress(0)
    
    for idx, tk in enumerate(ticker_list):
        progress_bar.progress((idx + 1) / len(ticker_list))
        df_raw = get_ohlc(tk, timeframe)
        
        if df_raw.empty or len(df_raw) < 20:
            continue
            
        df_feats = add_indicators(df_raw)
        trend_c = detect_trend_from_df(df_feats)
        score_t = compute_trend_score(df_feats, trend_c)
        v_sigs = detect_volume_breakout_signals(df_feats, tk)
        
        last_row = df_feats.iloc[-1]
        c_val = float(last_row["Close"].iloc[0]) if isinstance(last_row["Close"], pd.Series) else float(last_row["Close"])
        
        all_market_data.append({
            "Ticker": tk,
            "Trend": trend_c,
            "Close": c_val,
            "TrendScore": score_t
        })
        
        global_volume_sigs.extend(v_sigs)
        if trend_c == "bull":
            global_alerts.append(f"🟢 {tk} - Sygnał silnego trendu wzrostowego (Bull).")
        elif trend_c == "bear":
            global_alerts.append(f"🔴 {tk} - Presja niedźwiedzia (Bear).")
            
        processed_dfs[tk] = (df_feats, trend_c, score_t)

    market_summary_df = pd.DataFrame(all_market_data)

    # 1. Mapa Heatmap wizualna rynku
    st.subheader("📊 Mapa Skanera (Trend Score)")
    if not market_summary_df.empty:
        st.markdown('<div class="heatmap-container">', unsafe_allow_html=True)
        for _, row in market_summary_df.iterrows():
            bg_color = "#064e3b" if row["Trend"] == "bull" else ("#7f1d1d" if row["Trend"] == "bear" else "#78350f")
            st.markdown(f"""
                <div class="heatmap-tile" style="background-color: {bg_color};">
                    <b style="font-size:15px;">{row['Ticker']}</b>
                    <span>Cena: {row['Close']:.2f}</span>
                    <span>Score: {row['TrendScore']:.0f}</span>
                </div>
            """, unsafe_allow_html=True)
        st.markdown('</div><br>', unsafe_allow_html=True)
    else:
        st.warning("Brak wystarczających danych do zbudowania mapy rynkowej.")

    # 2. Raport META Analizy AI
    st.subheader("🤖 Globalny Raport Strategiczny META AI")
    with st.spinner("Model o3-mini analizuje strukturę rynkową..."):
        meta_opinion = ai_meta_pick(market_summary_df, global_alerts, global_volume_sigs)
        st.info(meta_opinion)

    # 3. Indywidualny Podgląd Techniczny Wybranej Spółki
    st.subheader("🔍 Szczegółowa inspekcja spółki")
    if processed_dfs:
        selected_tk = st.selectbox("Wybierz spółkę z przeskanowanych, aby zobaczyć wykres i analizę 3 modeli AI:", list(processed_dfs.keys()))
        
        if selected_tk:
            df_selected, trend_c, score_t = processed_dfs[selected_tk]
            label, css_class = trend_label_and_css(trend_c)
            
            st.markdown(f'<div class="trend-box {css_class}">Wybrany walor: {selected_tk} — {label} (Score: {score_t:.0f}/100)</div>', unsafe_allow_html=True)
            
            # Renderowanie wykresu Plotly w ładnej ramce
            st.markdown('<div class="plot-border">', unsafe_allow_html=True)
            st.plotly_chart(plot_multichart(df_selected, selected_tk), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Indywidualne analizy trzech modeli AI
            st.markdown("### 💬 Konsylium analityczne modeli AI dla pojedynczej spółki")
            c1, c2, c3 = st.columns(3)
            
            # Przygotowanie uproszczonego zestawu tekstowego pod prompt pojedynczy
            last_bar = df_selected.iloc[-1]
            raw_close = float(last_bar["Close"].iloc[0]) if isinstance(last_bar["Close"], pd.Series) else float(last_bar["Close"])
            raw_rsi = float(last_bar["RSI14"].iloc[0]) if isinstance(last_bar["RSI14"], pd.Series) else float(last_bar["RSI14"]) if pd.notna(last_bar.get("RSI14")) else 50.0
            
            summary_prompt_payload = f"Cena: {raw_close:.4f}, RSI14: {raw_rsi:.1f}, Trend bazowy: {trend_c}, Score: {score_t}"
            
            with c1:
                st.markdown('<div class="box swing">🎯 SWING TRADER (gpt-4o-mini)</div>', unsafe_allow_html=True)
                st.write(ai_swing(selected_tk, summary_prompt_payload))
            with c2:
                st.markdown('<div class="box day">⚡ DAYTRADER (gpt-4o)</div>', unsafe_allow_html=True)
                st.write(ai_day(selected_tk, summary_prompt_payload))
            with c3:
                st.markdown('<div class="box long">⏳ LONG-TERM (o3-mini)</div>', unsafe_allow_html=True)
                st.write(ai_long(selected_tk, summary_prompt_payload))
    else:
        st.error("Brak przetworzonych spółek. Sprawdź poprawność wprowadzonych tickerów.")
