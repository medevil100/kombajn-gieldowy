import time
import schedule
import requests
import yfinance as yf
import pandas as pd
import streamlit as st
from openai import OpenAI
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import matplotlib.pyplot as plt
import base64
from io import BytesIO

# =====================================================================
# KONFIG STREAMLIT
# =====================================================================
st.set_page_config(page_title="KOMBAJN PRO", page_icon="📈", layout="wide")
st.title("📈 KOMBAJN PRO — AI + Tavily + Mini‑Świece + Telegram")

# =====================================================================
# SESSION STATE
# =====================================================================
if "alerts_history" not in st.session_state:
    st.session_state.alerts_history = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = "Nigdy"
if "scanned_details" not in st.session_state:
    st.session_state.scanned_details = []

# =====================================================================
# SECRETS
# =====================================================================
try:
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]
except Exception as e:
    st.error(f"❌ Brak kluczy w secrets.toml: {e}")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================================
# LISTA SPÓŁEK + CZAS SKANU
# =====================================================================
user_input = st.text_area(
    "Wklej swoje spółki (np. STX.WA, AAPL, NVDA):",
    value="",
    height=120,
    placeholder="Np. STX.WA, AAPL, NVDA..."
)

MARKET_DATABASE = [t.strip().upper() for t in user_input.split(",") if t.strip()]

scan_minutes = st.slider(
    "⏱️ Czas między skanami (minuty)",
    min_value=15,
    max_value=120,
    value=60,
    step=15
)

# =====================================================================
# TELEGRAM
# =====================================================================
def send_telegram_message(msg: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

# =====================================================================
# TAVILY NEWS + AI SENTIMENT
# =====================================================================
def tavily_news(query: str):
    try:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "max_results": 5,
            "include_answer": True
        }
        r = requests.post(url, json=payload, timeout=10).json()
        return r.get("results", [])
    except Exception:
        return []

def ai_news_sentiment(ticker: str, news: list):
    if not news:
        return "neutralny"

    text = "\n".join([f"{n['title']}: {n['snippet']}" for n in news])

    prompt = (
        f"Analizujesz newsy o spółce {ticker}.\n"
        f"{text}\n"
        f"Podaj jedno słowo: pozytywny / neutralny / negatywny."
    )

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return "neutralny"

# =====================================================================
# MINI‑ŚWIECA + WOLUMEN (120x80 px)
# =====================================================================
def mini_chart(df: pd.DataFrame) -> str:
    try:
        df = df.tail(20)
        fig, (ax1, ax2) = plt.subplots(
            2, 1,
            figsize=(1.6, 1.0),
            gridspec_kw={"height_ratios": [3, 1]},
            dpi=75
        )

        for i, row in enumerate(df.itertuples()):
            o, h, l, c = row.Open, row.High, row.Low, row.Close
            color = "#00ff00" if c >= o else "#ff0000"
            ax1.vlines(i, l, h, color=color, linewidth=0.8)
            ax1.vlines(i, o, c, color=color, linewidth=2)

        ax1.set_xticks([])
        ax1.set_yticks([])
        ax1.set_facecolor("#000000")

        ax2.bar(range(len(df)), df["Volume"], color="#666666", width=0.6)
        ax2.set_xticks([])
        ax2.set_yticks([])
        ax2.set_facecolor("#000000")

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
        plt.close(fig)

        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return ""
# =====================================================================
# RSI
# =====================================================================
def oblicz_rsi(df: pd.DataFrame, period: int = 14):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =====================================================================
# FORMACJE
# =====================================================================
def wykryj_formacje(df: pd.DataFrame) -> str:
    if len(df) < 3:
        return "Brak"
    o1, h1, l1, c1 = df.iloc[-1][["Open","High","Low","Close"]]
    o2, h2, l2, c2 = df.iloc[-2][["Open","High","Low","Close"]]
    if c1 > o1 and c2 < o2 and o1 < c2 and c1 > o2:
        return "🟢 Bullish Engulfing"
    if c1 < o1 and c2 > o2 and o1 > c2 and c1 < o2:
        return "🔴 Bearish Engulfing"
    return "Brak"

# =====================================================================
# AI PREDYKCJA / TREND / RYZYKO / SCORING / REKOMENDACJA
# =====================================================================
def predykcja_ai(ticker, zmiana, rsi, wolumen_x):
    prompt = (
        f"{ticker}: zmiana {zmiana:.2f}%, RSI {rsi:.1f}, wolumen {wolumen_x:.1f}x.\n"
        f"Przewidź: UP / DOWN / SIDEWAYS."
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0
        )
        out = r.choices[0].message.content.upper()
        if "UP" in out:
            return "📈 UP"
        if "DOWN" in out:
            return "📉 DOWN"
        return "➡️ SIDEWAYS"
    except Exception:
        return "➡️ SIDEWAYS"

def trend_ai(zmiana, rsi):
    if zmiana > 0.5 and rsi < 70:
        return "📈 UP"
    if zmiana < -0.5 and rsi > 30:
        return "📉 DOWN"
    return "➡️ SIDEWAYS"

def ryzyko_ai(rsi, wolumen_x):
    if rsi > 75 or wolumen_x > 3:
        return "🔴 HIGH"
    if 40 <= rsi <= 60:
        return "🟡 MEDIUM"
    return "🟢 LOW"

def scoring_ai(zmiana, rsi, wolumen_x, pred):
    score = 50 + zmiana*2 + (wolumen_x-1)*10
    if 45 <= rsi <= 60:
        score += 10
    if rsi < 30 or rsi > 75:
        score -= 15
    if "UP" in pred:
        score += 15
    if "DOWN" in pred:
        score -= 15
    return max(0, min(100, int(score)))

def rekomendacja_pro(trend, score, sentiment, rsi, pred):
    s = sentiment.lower()
    if trend == "📈 UP" and score >= 60 and "pozy" in s and rsi < 70:
        return "🟢 KUP"
    if trend == "📉 DOWN" and score <= 40 and "neg" in s and rsi > 70:
        return "🔴 SPRZEDAJ"
    if "DOWN" in pred and score < 50:
        return "🔴 SPRZEDAJ"
    if "UP" in pred and score > 50:
        return "🟢 KUP"
    return "🟡 TRZYMAJ"

# =====================================================================
# ANALIZA SPÓŁKI
# =====================================================================
def analizuj_jedna_spolke(ticker: str, now: str):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        df["RSI"] = oblicz_rsi(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        cena = float(last["Close"])
        cena_prev = float(prev["Close"])
        rsi = float(last["RSI"])
        zmiana = ((cena - cena_prev) / cena_prev) * 100
        wolumen_x = float(last["Volume"]) / float(df["Volume"].mean())

        formacja = wykryj_formacje(df)
        pred = predykcja_ai(ticker, zmiana, rsi, wolumen_x)
        trend = trend_ai(zmiana, rsi)
        ryzyko = ryzyko_ai(rsi, wolumen_x)
        score = scoring_ai(zmiana, rsi, wolumen_x, pred)

        news = tavily_news(ticker)
        sentiment = ai_news_sentiment(ticker, news)

        rekom = rekomendacja_pro(trend, score, sentiment, rsi, pred)
        chart_b64 = mini_chart(df)

        info = {
            "Ticker": ticker,
            "Cena": cena,
            "RSI": rsi,
            "Zmiana %": zmiana,
            "Wolumen x": wolumen_x,
            "Trend": trend,
            "Ryzyko": ryzyko,
            "Scoring": score,
            "Sentiment": sentiment,
            "Rekomendacja": rekom,
            "Chart": chart_b64,
        }

        if rekom == "🟢 KUP":
            send_telegram_message(f"🟢 KUP: {ticker} ({cena:.2f})")
        elif rekom == "🔴 SPRZEDAJ":
            send_telegram_message(f"🔴 SPRZEDAJ: {ticker} ({cena:.2f})")

        return info

    except Exception:
        return None

# =====================================================================
# SKANER
# =====================================================================
def job_skanera(status=None, bar=None):
    st.session_state.scanned_details = []

    total = len(MARKET_DATABASE)
    if total == 0:
        return

    with ThreadPoolExecutor(max_workers=15) as ex:
        tasks = {ex.submit(analizuj_jedna_spolke, t, datetime.now().isoformat()): t for t in MARKET_DATABASE}
        done = 0
        for fut in as_completed(tasks):
            done += 1
            ticker = tasks[fut]
            if status:
                status.write(f"🔍 {done}/{total} — {ticker}")
            if bar:
                bar.progress(done/total)

            res = fut.result()
            if res:
                st.session_state.scanned_details.append(res)

    st.session_state.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_telegram_message(f"🤖 Skan zakończony. Kolejny za ~{scan_minutes} min.")

# =====================================================================
# SCHEDULER (wywoływany w UI)
# =====================================================================
schedule.clear()
schedule.every(scan_minutes).minutes.do(job_skanera)

def run_scheduler():
    schedule.run_pending()
# =====================================================================
# UI — STATUS + RĘCZNY SKAN
# =====================================================================
st.write("---")
st.success(f"⚙️ Ostatni skan: {st.session_state.last_scan_time}")

status = st.empty()
bar = st.empty()

col1, col2 = st.columns(2)
with col1:
    if st.button("🚀 SKANUJ TERAZ"):
        job_skanera(status, bar)
        if st.button("🚀 SKANUJ TERAZ"):
    job_skanera(status, bar)
    st.rerun()

with col2:
    st.write(f"⏲️ Auto-skan co {scan_minutes} min")

# uruchom scheduler przy każdym odświeżeniu
run_scheduler()

# =====================================================================
# TABELA PRO — MINI‑ŚWIECE + KOLOROWANIE
# =====================================================================
st.write("---")
st.subheader("📊 KOMBAJN PRO — pełna analiza AI")

if st.session_state.scanned_details:

    df = pd.DataFrame(st.session_state.scanned_details)

    def kolor(row):
        if "🟢" in row["Rekomendacja"]:
            return ["background-color: #003300; color: #00ff00"] * len(row)
        if "🔴" in row["Rekomendacja"]:
            return ["background-color: #330000; color: #ff4444"] * len(row)
        return ["background-color: #333300; color: #ffff66"] * len(row)

    df["MiniWykres"] = df["Chart"].apply(
        lambda x: f'<img src="data:image/png;base64,{x}" width="120" height="80"/>'
    )

    styled = df.style.apply(kolor, axis=1)

    html = styled.to_html(escape=False)
    st.markdown(html, unsafe_allow_html=True)

else:
    st.info("Brak danych — skaner jeszcze nie wykonał cyklu.")

# =====================================================================
# PODGLĄD TICKERA
# =====================================================================
st.write("---")
st.subheader("🔎 Szybki podgląd tickera")

quick = st.text_input("Ticker:")

if quick:
    df_q = yf.download(quick.strip().upper(), period="3mo", interval="1d", progress=False)
    if df_q.empty:
        st.error("Brak danych.")
    else:
        df_q["RSI"] = oblicz_rsi(df_q)
        last = df_q.iloc[-1]
        st.write(f"**Cena:** {last['Close']:.2f}")
        st.write(f"**RSI:** {last['RSI']:.1f}")
