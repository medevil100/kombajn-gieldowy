import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import matplotlib.pyplot as plt

# --- KONFIG ---
st.set_page_config(layout="wide", page_title="NEON ULTRA PRO MAX", page_icon="🚀")

# --- CSS NEON + HEATMAP + ALERTY ---
st.markdown("""
<style>
body { background:#050510; color:#e0e0ff; }
.stApp { background:#050510; }

.tile {
    border-radius:18px; padding:18px; text-align:center;
    border:1px solid #222; box-shadow:0 0 25px #39FF1422;
    min-height:330px;
}

/* ALERTY */
.tile-KUP { background:#002000; box-shadow:0 0 25px #00FF0044; }
.tile-SPRZEDAJ { background:#200000; box-shadow:0 0 25px #FF000044; }
.tile-TRZYMAJ { background:#001820; box-shadow:0 0 25px #00FFFF44; }

/* HEATMAP TRENDÓW */
.trend-strong-up { border:2px solid #00FF00; }
.trend-up { border:2px solid #39FF14; }
.trend-neutral { border:2px solid #888; }
.trend-down { border:2px solid #FF3131; }
.trend-strong-down { border:2px solid #FF0000; }

.price { font-size:2.2rem; font-weight:bold; color:white; }
.bid { color:#00FF00; font-weight:bold; }
.ask { color:#FF3131; font-weight:bold; }

.tp { color:#00FF00; font-weight:bold; }
.sl { color:#FF3131; font-weight:bold; }

.signal-KUP {
    color:#39FF14; border:2px solid #39FF14;
    padding:6px; border-radius:10px; font-weight:bold;
}
.signal-SPRZEDAJ {
    color:#FF3131; border:2px solid #FF3131;
    padding:6px; border-radius:10px; font-weight:bold;
}
.signal-TRZYMAJ {
    color:#00FFFF; border:2px solid #00FFFF;
    padding:6px; border-radius:10px; font-weight:bold;
}

.stButton>button {
    background:#111; border:2px solid #39FF14;
    color:#39FF14; font-weight:bold; width:100%;
    box-shadow:0 0 15px #39FF1444;
}
</style>
""", unsafe_allow_html=True)

# --- AI ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# --- AUTOREFRESH ---
st_autorefresh(interval=5 * 60 * 1000, key="mega_ultra_v3")

# --- ULTRA ENGINE ---
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
        ma200 = df["Close"].rolling(200).mean().iloc[-1]
        ema200 = df["Close"].ewm(span=200).mean().iloc[-1]

        # Trend score
        t1 = 1 if last > ma20 else -1
        t2 = 2 if last > ma50 else -2
        t3 = 3 if last > ma200 else -3
        score = t1 + t2 + t3

        # RSI
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss if loss != 0 else 0)))

        # ATR
        tr = pd.concat([
            df["High"] - df["Low"],
            abs(df["High"] - df["Close"].shift()),
            abs(df["Low"] - df["Close"].shift())
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
        if score >= 4 and rsi < 70:
            signal = "KUP"
        elif score <= -3 and rsi > 30:
            signal = "SPRZEDAJ"
        else:
            signal = "TRZYMAJ"

        # Heatmap trend
        if score >= 5:
            trend_class = "trend-strong-up"
        elif score >= 2:
            trend_class = "trend-up"
        elif score <= -5:
            trend_class = "trend-strong-down"
        elif score <= -2:
            trend_class = "trend-down"
        else:
            trend_class = "trend-neutral"

        return {
            "symbol": symbol,
            "price": last,
            "bid": tk.info.get("bid", "-"),
            "ask": tk.info.get("ask", "-"),
            "ma20": ma20, "ma50": ma50, "ma200": ma200,
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
            "df": df.tail(60)  # do mini-wykresu
        }

    except:
        return None

# --- UI ---
st.markdown("<h1 style='color:#39FF14; text-shadow:0 0 15px #39FF14;'>🚀 NEON ULTRA PRO MAX</h1>", unsafe_allow_html=True)

st.sidebar.title("💠 KONTROLA")
tickers_in = st.sidebar.text_area("Tickery:", "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD", height=200)
tickers = [x.strip().upper() for x in tickers_in.replace(",", " ").split() if x.strip()]

if not tickers:
    st.info("Wklej tickery w sidebarze.")
    st.stop()

results = []
for t in tickers:
    r = ultra(t)
    if r:
        results.append(r)

# --- KAFELKI ---
cols = st.columns(3)

for i, r in enumerate(results):
    with cols[i % 3]:

        # Mini wykres
        fig, ax = plt.subplots(figsize=(3, 1.2))
        ax.plot(r["df"]["Close"].values, color="#39FF14")
        ax.set_axis_off()

        st.markdown(
            f"<div class='tile tile-{r['signal']} {r['trend_class']}'>",
            unsafe_allow_html=True
        )

        st.pyplot(fig)

        st.markdown(f"""
        <div style="font-size:1.6rem; color:#39FF14; font-weight:bold;">{r['symbol']}</div>
        <div class="price">{r['price']:.2f}</div>
        <span class="bid">B: {r['bid']}</span> | <span class="ask">A: {r['ask']}</span>
        <hr>
        MA20: {r['ma20']:.2f}<br>
        MA50: {r['ma50']:.2f}<br>
        MA200: {r['ma200']:.2f}
        <hr>
        Swing High: {r['swing_high']:.2f}<br>
        Swing Low: {r['swing_low']:.2f}
        <hr>
        <b>TP:</b> <span class="tp">{r['tp']:.2f}</span><br>
        <b>SL:</b> <span class="sl">{r['sl']:.2f}</span>
        <hr>
        <div class="signal-{r['signal']}">{r['signal']}</div>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        if st.button(f"AI – {r['symbol']}", key=f"ai_{r['symbol']}"):
            if client:
                with st.spinner("Analiza AI..."):
                    prompt = (
                        f"Analiza {r['symbol']}: Kurs {r['price']}, Trend score {r['score']}, "
                        f"RSI {r['rsi']:.1f}, ATR {r['atr']:.2f}, TP {r['tp']:.2f}, SL {r['sl']:.2f}. "
                        "Podaj: 1. Ocena wejścia, 2. Ryzyko, 3. Werdykt. Zero lania wody."
                    )
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Jesteś bezdusznym systemem operacyjnym. Mówisz tylko o faktach."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1
                    )
                    st.info(resp.choices[0].message.content)
