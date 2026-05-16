# utils.py

import yfinance as yf
import numpy as np
import pandas as pd

# ================== NORMALIZACJA ==================
def normalize_ticker(t: str) -> str:
    t = t.upper().strip()
    if len(t) <= 4 and "." not in t:
        return t + ".WA"
    return t

# ================== POBIERANIE DANYCH ==================
def get_ohlc(ticker: str, tf: str) -> pd.DataFrame:
    ticker = normalize_ticker(ticker)
    try:
        df = yf.download(
            ticker,
            period="1y" if tf == "D1" else "30d",
            interval="1d" if tf == "D1" else "60m",
            auto_adjust=False
        )
    except:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    df.columns = [str(c).strip() for c in df.columns]

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df = df.fillna(method="ffill").fillna(method="bfill")
    if df.empty:
        return pd.DataFrame()

    return df

# ================== WSKAŹNIKI ==================
def add_indicators(df):
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
    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
    df["RSI14"] = 100 - (100 / (1 + rs))

    tr = pd.concat([
        (df["High"] - df["Low"]),
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()

    df["VolMA20"] = df["Volume"].rolling(20).mean()

    return df

# ================== TREND ==================
def detect_trend_from_df(df):
    last = df.iloc[-1]
    sma50 = last.get("SMA50", np.nan)
    sma200 = last.get("SMA200", np.nan)

    if last["Close"] > sma200 * 1.01:
        return "bull"
    if last["Close"] < sma200 * 0.99:
        return "bear"

    if last["Close"] > sma50:
        return "bull"
    if last["Close"] < sma50:
        return "bear"

    return "side"

# ================== SCORE ==================
def compute_trend_score(df, trend_code):
    last = df.iloc[-1]
    score = 0

    if trend_code == "bull": score += 30
    if last["Close"] < 5: score += 10
    if last["Close"] > last.get("SMA50", 0): score += 15
    if last["Close"] > last.get("SMA200", 0): score += 15
    if last.get("SMA50", 0) > last.get("SMA200", 0): score += 20

    rsi = last.get("RSI14", np.nan)
    if 55 <= rsi <= 70: score += 10
    elif 50 <= rsi < 55: score += 5

    return score

# ================== ALERTY TRENDÓW ==================
def detect_trend_alerts(df, ticker, trend_code):
    alerts = []
    if len(df) < 3: return alerts

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["Close"] > last.get("SMA50", 0) and prev["Close"] < prev.get("SMA50", 0):
        alerts.append(f"🔥 {ticker}: świeży sygnał bull (przebicie SMA50).")

    if last["Close"] < last.get("SMA200", 0) and prev["Close"] > prev.get("SMA200", 0):
        alerts.append(f"⚠️ {ticker}: przebicie SMA200 w dół.")

    return alerts

# ================== ALERTY WOLUMENOWE ==================
def detect_volume_breakout_signals(df, ticker):
    sig = []
    last = df.iloc[-1]
    vol = last["Volume"]
    vol_ma = last["VolMA20"]
    atr = last["ATR14"]

    if vol_ma == 0 or atr == 0 or np.isnan(vol_ma) or np.isnan(atr):
        return sig

    body = abs(last["Close"] - last["Open"])

    if vol > 2 * vol_ma and body > atr and last["Close"] > last["BB_upper"]:
        sig.append(f"🔥 {ticker}: silne wybicie (wolumen>2×, świeca>ATR, wybicie BB).")

    if vol > 1.5 * vol_ma and body > atr:
        sig.append(f"⚡ {ticker}: wybicie wolumenowe (wolumen>1.5×, świeca>ATR).")

    if vol > 2 * vol_ma and body < atr * 0.5 and last["Close"] < last["Open"]:
        sig.append(f"📉 {ticker}: możliwa dystrybucja.")

    if vol > 2 * vol_ma and body < atr * 0.5 and last["Close"] > last["Open"]:
        sig.append(f"📈 {ticker}: możliwa akumulacja.")

    return sig
# ai.py

from openai import OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def ai_swing(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[{"role":"user","content":f"""
Jesteś agresywnym traderem swingowym.
Analiza SWING dla {ticker}:
{text}
Zadanie: 2–3 zdania, dynamicznie.
"""}]
    )
    return r.choices[0].message.content.strip()

def ai_day(ticker, text):
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{"role":"user","content":f"""
Jesteś daytraderem.
Analiza DAYTRADING dla {ticker}:
{text}
Zadanie: 2–3 zdania, szybko i konkretnie.
"""}]
    )
    return r.choices[0].message.content.strip()

def ai_long(ticker, text):
    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role":"user","content":f"""
Jesteś analitykiem długoterminowym.
Analiza LONG-TERM dla {ticker}:
{text}
Zadanie: 2–3 zdania, spokojnie i analitycznie.
"""}]
    )
    return r.choices[0].message.content.strip()

def ai_meta_pick(market_df, alerts, volume_signals):
    base = "Dane rynku:\n"
    if not market_df.empty:
        base += market_df[["Ticker","Trend","Close","TrendScore"]].head(20).to_string(index=False)

    base += "\n\nAlerty:\n" + "\n".join(alerts[:20])
    base += "\n\nWolumeny:\n" + "\n".join(volume_signals[:20])

    r = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role":"user","content":f"""
Jesteś AI META. Wybierz 3–5 najlepszych groszówek.
Nie kopiuj liczb. Oceń trend, momentum, wolumen, ryzyko.
Dane:
{base}
"""}]
    )
    return r.choices[0].message.content.strip()
# charts.py

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def plot_multichart(df):
    df=df.tail(120)
    x=df.index

    fig=make_subplots(
        rows=3,cols=1,shared_xaxes=True,
        vertical_spacing=0.05,row_heights=[0.55,0.25,0.20]
    )

    fig.add_trace(go.Candlestick(
        x=x,open=df["Open"],high=df["High"],low=df["Low"],close=df["Close"],
        increasing_line_color="#00ff88",
        decreasing_line_color="#ff0055",
        name="Świece"
    ),row=1,col=1)

    for w,c in [(20,"#ffaa00"),(50,"#00e5ff"),(100,"#cc66ff"),(200,"#888888")]:
        col=f"SMA{w}"
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=x,y=df[col],line=dict(color=c,width=1.8),name=col
            ),row=1,col=1)

    fig.add_trace(go.Scatter(
        x=x,y=df["BB_upper"],line=dict(color="#60a5fa",dash="dash"),name="BB Upper"
    ),row=1,col=1)
    fig.add_trace(go.Scatter(
        x=x,y=df["BB_lower"],line=dict(color="#60a5fa",dash="dash"),name="BB Lower"
    ),row=1,col=1)

    fig.add_trace(go.Scatter(
        x=x,y=df["RSI14"],line=dict(color="#ffff00",width=2),name="RSI14"
    ),row=2,col=1)
    fig.add_hline(y=70,line=dict(color="#ff4444",dash="dot"),row=2,col=1)
    fig.add_hline(y=30,line=dict(color="#44ff44",dash="dot"),row=2,col=1)

    fig.add_trace(go.Bar(
        x=x,y=df["Volume"],marker_color="#aa44ff",name="Volume"
    ),row=3,col=1)

    fig.update_layout(
        template="plotly_dark",height=800,
        paper_bgcolor="#020617",plot_bgcolor="#020617",
        font=dict(color="#e5e7eb")
    )

    st.markdown('<div class="plot-border">',unsafe_allow_html=True)
    st.plotly_chart(fig,use_container_width=True)
    st.markdown('</div>',unsafe_allow_html=True)

def render_heatmap(ranking_df):
    for _,row in ranking_df.iterrows():
        t=row["Ticker"]; trend=row["Trend"]
        rsi=row["RSI14"]; atr=row["ATR14"]
        vol=row["Volume"]; vol_ma=row["VolMA20"]

        bg={"bull":"#14532d","bear":"#7f1d1d","side":"#78350f"}[trend]
        border="#4ade80"
        if rsi>70: border="#f97316"
        elif rsi<30: border="#38bdf8"

        icon="🌑"
        if vol_ma>0:
            if vol>2*vol_ma: icon="🔥"
            elif vol>1.5*vol_ma: icon="⚡"

        tile=f"""
        <div class="heatmap-tile" style="background:{bg};border:2px solid {border};">
            <b>{t}</b> {icon}<br/>
            Trend: {trend}<br/>
            RSI: {'' if np.isnan(rsi) else round(rsi,1)}<br/>
            ATR: {'' if np.isnan(atr) else round(atr,3)}
        </div>
        """
        st.markdown(tile,unsafe_allow_html=True)
# scanner.py

import streamlit as st
import numpy as np
import pandas as pd

from kombajn.utils import (
    normalize_ticker, get_ohlc, add_indicators,
    detect_trend_from_df, compute_trend_score,
    detect_trend_alerts, detect_volume_breakout_signals
)

from kombajn.charts import render_heatmap
from kombajn.ai import ai_meta_pick

def run_scanner():
    st.subheader("🧪 Skaner groszówek PL + USA — ranking + heatmapa + alerty")

    tickers_text=st.text_area(
        "Lista tickerów:",
        "HRT.WA,CFS.WA,PRT.WA,ATT.WA,STX.WA,PUR.WA,BCS.WA,KCH.WA,GTN.WA,LBW.WA,"
        "PGV.WA,HPE.WA,DNS.WA,ZUK.WA,VVD.WA,HIVE,MLN.WA,MER.WA,APS.WA,NVG.WA,"
        "IOVA,PLRX,HUMA,TCRX,GOSS,MREO,ADTX",
        height=120
    )

    only_pennies=st.checkbox("Filtruj tylko groszówki (Close < 5)",value=True)
    tf_scan=st.selectbox("Interwał:",["D1","H1"])
    tf_scan_code="D1" if tf_scan=="D1" else "H1"
    run_scan=st.button("Skanuj rynek")

    if not run_scan:
        return None, None, None

    raw=tickers_text.replace("\n",",")
    tickers=[normalize_ticker(t) for t in raw.split(",") if t.strip()]
    tickers=list(dict.fromkeys(tickers))

    rows=[]
    scan_results={}
    all_alerts=[]
    all_volume_signals=[]

    for t in tickers:
        df_t=get_ohlc(t,tf_scan_code)
        if df_t.empty: continue
        df_t=add_indicators(df_t)
        trend=detect_trend_from_df(df_t)
        last=df_t.iloc[-1]

        close=float(last["Close"])
        rsi=float(last.get("RSI14",np.nan))
        atr=float(last.get("ATR14",np.nan))
        vol=float(last.get("Volume",np.nan))
        vol_ma=float(last.get("VolMA20",np.nan))
        score=compute_trend_score(df_t,trend)

        if only_pennies and close>=5: continue

        rows.append({
            "Ticker":t,"Trend":trend,"Close":close,
            "RSI14":rsi,"ATR14":atr,"Volume":vol,
            "VolMA20":vol_ma,"TrendScore":score
        })
        scan_results[t]=df_t

        all_alerts+=detect_trend_alerts(df_t,t,trend)
        all_volume_signals+=detect_volume_breakout_signals(df_t,t)

    if not rows:
        st.warning("Brak danych dla podanych tickerów.")
        return None, None, None

    ranking_df=pd.DataFrame(rows)
    ranking_df=ranking_df.sort_values("TrendScore",ascending=False).reset_index(drop=True)

    st.markdown("### 🏆 Ranking trendów")
    st.dataframe(ranking_df,use_container_width=True)

    st.markdown("### 🌈 Heatmapa PRO")
    render_heatmap(ranking_df)

    st.markdown("### 🚨 Alerty")
    for a in all_alerts:
        css="alert-bull" if ("bull" in a or "🔥" in a) else "alert-bear"
        st.markdown(f'<div class="alert-box {css}">{a}</div>',unsafe_allow_html=True)

    for v in all_volume_signals:
        css="alert-vsa" if ("akumulacja" in v or "dystrybucja" in v) else "alert-vol"
        st.markdown(f'<div class="alert-box {css}">{v}</div>',unsafe_allow_html=True)

    st.markdown("### 🧠 AI META — wybór najlepszych spółek")
    meta = ai_meta_pick(ranking_df, all_alerts, all_volume_signals)
    st.markdown(f'<div class="box long">{meta}</div>',unsafe_allow_html=True)

    return ranking_df, scan_results, tf_scan_code
# main.py

import streamlit as st
from kombajn.scanner import run_scanner
from kombajn.utils import normalize_ticker, get_ohlc, add_indicators, detect_trend_from_df
from kombajn.ai import ai_swing, ai_day, ai_long
from kombajn.charts import plot_multichart

st.title("📈 3× AI — Terminal Groszówek (PL + USA)")

ranking_df, scan_results,
