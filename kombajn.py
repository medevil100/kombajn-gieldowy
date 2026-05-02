import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- KONFIG ---
st.set_page_config(layout="wide", page_title="WALL STREET ULTRA TERMINAL", page_icon="💼")

# --- CSS WALL STREET ---
st.markdown("""
<style>
body { background:#020612; color:#e0e0ff; }
.stApp { background:#020612; }

.tile {
    border-radius:18px; padding:18px; text-align:center;
    border:1px solid #1b2838; box-shadow:0 0 25px #000000aa;
    min-height:360px;
    background:linear-gradient(145deg, #050b18 0%, #020612 60%, #0b101f 100%);
}

/* ALERTY */
.tile-KUP { box-shadow:0 0 25px #ffd70055; border-color:#ffd700; }
.tile-SPRZEDAJ { box-shadow:0 0 25px #ff4b4b55; border-color:#ff4b4b; }
.tile-TRZYMAJ { box-shadow:0 0 25px #00bcd455; border-color:#00bcd4; }

/* HEATMAP TRENDÓW */
.trend-strong-up { border-width:2px; border-color:#00ff7f !important; }
.trend-up { border-width:2px; border-color:#32cd32 !important; }
.trend-neutral { border-width:2px; border-color:#888 !important; }
.trend-down { border-width:2px; border-color:#ff6347 !important; }
.trend-strong-down { border-width:2px; border-color:#ff0000 !important; }

.price { font-size:2.2rem; font-weight:bold; color:#fdfdfd; }
.bid { color:#7CFC00; font-weight:bold; }
.ask { color:#ff4b4b; font-weight:bold; }

.tp { color:#7CFC00; font-weight:bold; }
.sl { color:#ff4b4b; font-weight:bold; }

.signal-KUP {
    color:#ffd700; border:1px solid #ffd700;
    padding:6px; border-radius:10px; font-weight:bold;
}
.signal-SPRZEDAJ {
    color:#ff4b4b; border:1px solid #ff4b4b;
    padding:6px; border-radius:10px; font-weight:bold;
}
.signal-TRZYMAJ {
    color:#00bcd4; border:1px solid #00bcd4;
    padding:6px; border-radius:10px; font-weight:bold;
}

.stButton>button {
    background:#08101f; border:1px solid #ffd700;
    color:#ffd700; font-weight:bold; width:100%;
    box-shadow:0 0 15px #000000aa;
}

h1, h2, h3 { color:#ffd700; }
</style>
""", unsafe_allow_html=True)

# --- AI ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# --- AUTOREFRESH ---
st_autorefresh(interval=5 * 60 * 1000, key="wall_street_ultra_v1")

# --- SESSION STATE NA TICKERY ---
if "tickers_text" not in st.session_state:
    st.session_state["tickers_text"] = "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD"

# --- HEADER + ODSWIEŻ ---
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.markdown("<h1>💼 WALL STREET ULTRA TERMINAL</h1>", unsafe_allow_html=True)
with col_btn:
    if st.button("🔄 ODSWIEŻ DANE"):
        st.experimental_rerun()

# --- ULTRA ENGINE (pełny, poprawiony, z MA100) ---
def ultra(symbol):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty:
            return None

        last = df["Close"].iloc[-1]
        high = df["High"].iloc[-1]
        low = df["Low"].iloc[-1]
        open_ = df["Open"].iloc[-1]

        # Świeca
        body = abs(last - open_)
        range_ = high - low
        body_pct = (body / range_ * 100) if range_ != 0 else 0
        direction = "BYCZA" if last > open_ else "NIEDŹWIEDZIA"

        # MA / EMA
        ma20 = df["Close"].rolling(20).mean().iloc[-1]
        ma50 = df["Close"].rolling(50).mean().iloc[-1]
        ma100 = df["Close"].rolling(100).mean().iloc[-1]
        ma200 = df["Close"].rolling(200).mean().iloc[-1]
        ema200 = df["Close"].ewm(span=200).mean().iloc[-1]

        # Trend score
        t1 = 1 if last > ma20 else -1
        t2 = 2 if last > ma50 else -2
        t3 = 2 if last > ma100 else -2
        t4 = 3 if last > ma200 else -3
        score = t1 + t2 + t3 + t4

        # RSI
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))

        # ATR
        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"] - df["Close"].shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # Swing
        swing_high = df["High"].tail(10).max()
        swing_low = df["Low"].tail(10).min()

        # TP/SL
        tp = max(last + atr * 2, swing_high)
        sl = min(last - atr * 1.5, swing_low)

        # Pivot
        pivot = (high + low + last) / 3
        r1 = 2 * pivot - low
        s1 = 2 * pivot - high

        # Wolumen
        vol_rel = df["Volume"].iloc[-1] / df["Volume"].tail(20).mean()

        # Sygnał
        if score >= 6 and rsi < 70:
            signal = "KUP"
        elif score <= -4 and rsi > 30:
            signal = "SPRZEDAJ"
        else:
            signal = "TRZYMAJ"

        # Heatmap trend
        if score >= 7:
            trend_class = "trend-strong-up"
        elif score >= 3:
            trend_class = "trend-up"
        elif score <= -7:
            trend_class = "trend-strong-down"
        elif score <= -3:
            trend_class = "trend-down"
        else:
            trend_class = "trend-neutral"

        return {
            "symbol": symbol,
            "price": last,
            "bid": tk.info.get("bid", "-"),
            "ask": tk.info.get("ask", "-"),
            "ma20": ma20, "ma50": ma50, "ma100": ma100, "ma200": ma200,
            "ema200": ema200,
            "body_pct": body_pct,
            "direction": direction,
            "score": score,
            "rsi": rsi,
            "atr": atr,
            "swing_high": swing_high,
            "swing_low": swing_low,
            "tp": tp, "sl": sl,
            "pivot": pivot, "r1": r1, "s1": s1,
            "vol": vol_rel,
            "signal": signal,
            "trend_class": trend_class,
            "df": df.tail(60)
        }

    except Exception:
        return None
# --- SIDEBAR TICKERY (zapis w session_state) ---
st.sidebar.title("📋 LISTA SPÓŁEK")
tickers_text = st.sidebar.text_area(
    "Tickery (spacje / przecinki):",
    st.session_state["tickers_text"],
    height=200
)
st.session_state["tickers_text"] = tickers_text
tickers = [x.strip().upper() for x in tickers_text.replace(",", " ").split() if x.strip()]

if not tickers:
    st.info("Wklej tickery w sidebarze.")
    st.stop()

# --- LICZENIE WYNIKÓW ---
results = []
for t in tickers:
    r = ultra(t)
    if r:
        results.append(r)

if not results:
    st.warning("Brak danych dla podanych tickerów.")
    st.stop()

# --- TOP 10 WYBICIA ---
st.subheader("🔥 TOP 10 – Największa możliwość wybicia")

def breakout_score(r):
    # wolumen + trend + RSI w strefie wybicia (55–65)
    rsi_factor = max(0, 70 - abs(r["rsi"] - 60))
    return r["vol"] * 2 + r["score"] * 3 + rsi_factor

top10 = sorted(results, key=lambda x: breakout_score(x), reverse=True)[:10]

cols_top = st.columns(5)

for i, r in enumerate(top10):
    with cols_top[i % 5]:
        st.markdown(
            f"<div class='tile tile-{r['signal']} {r['trend_class']}'>",
            unsafe_allow_html=True
        )

        chart_df = pd.DataFrame({"Close": r["df"]["Close"].values})
        st.line_chart(chart_df, height=70)

        st.markdown(f"""
        <div style="font-size:1.1rem; color:#ffd700; font-weight:bold;">{r['symbol']}</div>
        <div class="price">{r['price']:.2f}</div>
        <b>Score:</b> {r['score']}<br>
        <b>RSI:</b> {r['rsi']:.1f}<br>
        <b>Vol x:</b> {r['vol']:.2f}<br>
        <div class="signal-{r['signal']}'>{r['signal']}</div>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

# --- KAFELKI GŁÓWNE ---
st.subheader("📊 ANALIZA GŁÓWNA")

cols = st.columns(3)

for i, r in enumerate(results):
    with cols[i % 3]:
        st.markdown(
            f"<div class='tile tile-{r['signal']} {r['trend_class']}'>",
            unsafe_allow_html=True
        )

        chart_df = pd.DataFrame({"Close": r["df"]["Close"].values})
        st.line_chart(chart_df, height=80)

        st.markdown(f"""
        <div style="font-size:1.4rem; color:#ffd700; font-weight:bold;">{r['symbol']}</div>
        <div class="price">{r['price']:.2f}</div>
        <span class="bid">B: {r['bid']}</span> | <span class="ask">A: {r['ask']}</span>
        <hr>
        MA20: {r['ma20']:.2f} | MA50: {r['ma50']:.2f} | MA100: {r['ma100']:.2f} | MA200: {r['ma200']:.2f}<br>
        EMA200: {r['ema200']:.2f}
        <hr>
        Swing High: {r['swing_high']:.2f} | Swing Low: {r['swing_low']:.2f}<br>
        Pivot: {r['pivot']:.2f} | R1: {r['r1']:.2f} | S1: {r['s1']:.2f}
        <hr>
        <b>TP:</b> <span class="tp">{r['tp']:.2f}</span> |
        <b>SL:</b> <span class="sl">{r['sl']:.2f}</span><br>
        ATR: {r['atr']:.2f} | RSI: {r['rsi']:.1f}
        <hr>
        <div class="signal-{r['signal']}'>{r['signal']}</div>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # --- AI DIAGNOZA ---
        if client and st.button(f"AI – {r['symbol']}", key=f"ai_{r['symbol']}"):
            with st.spinner("Analiza AI..."):
                prompt = (
                    f"Analiza techniczna spółki {r['symbol']}.\n"
                    f"Kurs: {r['price']:.2f}\n"
                    f"MA20/50/100/200: {r['ma20']:.2f} / {r['ma50']:.2f} / {r['ma100']:.2f} / {r['ma200']:.2f}\n"
                    f"EMA200: {r['ema200']:.2f}\n"
                    f"RSI: {r['rsi']:.1f}\n"
                    f"ATR: {r['atr']:.2f}\n"
                    f"Swing High / Low: {r['swing_high']:.2f} / {r['swing_low']:.2f}\n"
                    f"Pivot: {r['pivot']:.2f}, R1: {r['r1']:.2f}, S1: {r['s1']:.2f}\n"
                    f"Trend score: {r['score']}\n"
                    f"Wolumen relatywny: {r['vol']:.2f}\n"
                    f"Sygnał systemowy: {r['signal']}\n\n"
                    "Podaj w 3 punktach:\n"
                    "1) Ocena wejścia (konkretne poziomy, bez definicji)\n"
                    "2) Ryzyko (SL, ATR, zagrożenia)\n"
                    "3) Werdykt (KUP / OBSERWUJ / ODRZUĆ) — krótko, technicznie."
                )

                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "Jesteś bezdusznym systemem tradingowym. Mówisz krótko, technicznie, zero lania wody."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.05
                )
                st.info(resp.choices[0].message.content)
