import streamlit as st
import yfinance as yf
import pandas as pd
import math
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- 1. KONFIGURACJA I STYL WALL STREET ---
st.set_page_config(layout="wide", page_title="WALL STREET MEGA-KOMBAJN ULTRA PRO", page_icon="💼")

st.markdown("""
    <style>
    body { background-color: #020612; color: #e0e0ff; }
    .stApp { background-color: #020612; }

    .mega-card {
        border: 1px solid #1b2838;
        padding: 24px;
        border-radius: 18px;
        background: linear-gradient(145deg, #050b18 0%, #020612 60%, #0b101f 100%);
        box-shadow: 0 0 25px #000000aa;
        margin-bottom: 24px;
    }

    .top-card {
        border: 1px solid #1b2838;
        padding: 14px;
        border-radius: 12px;
        background: #050b18;
        font-size: 0.95rem;
        line-height: 1.4;
        min-height: 260px;
        text-align: center;
        box-shadow: 0 0 18px #000000aa;
    }

    .ws-title {
        color: #ffd700;
        font-weight: bold;
        font-size: 3.0rem;
        text-shadow: 0 0 15px #000000;
    }

    .price-tag {
        font-size: 2.4rem;
        font-weight: bold;
        color: #fdfdfd;
    }

    .neon-bid { color: #7CFC00; font-weight: bold; font-size: 1.1rem; }
    .neon-ask { color: #ff4b4b; font-weight: bold; font-size: 1.1rem; }

    .tp-val { color: #7CFC00; font-weight: bold; font-size: 1.2rem; }
    .sl-val { color: #ff4b4b; font-weight: bold; font-size: 1.2rem; }

    .signal-KUP {
        color: #ffd700;
        font-weight: bold;
        border: 1px solid #ffd700;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 1.2rem;
    }
    .signal-SPRZEDAJ {
        color: #ff4b4b;
        font-weight: bold;
        border: 1px solid #ff4b4b;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 1.2rem;
    }
    .signal-TRZYMAJ {
        color: #00bcd4;
        font-weight: bold;
        border: 1px solid #00bcd4;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 1.2rem;
    }

    .stButton>button {
        background-color: #08101f;
        color: #ffd700;
        border: 1px solid #ffd700;
        width: 100%;
        font-weight: bold;
        height: 3.2rem;
        font-size: 1.0rem;
        box-shadow: 0 0 15px #000000aa;
    }

    h1, h2, h3 { color: #ffd700; }
    </style>
""", unsafe_allow_html=True)

# --- 2. AI KLIENT ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# --- 3. AUTOREFRESH ---
st_autorefresh(interval=5 * 60 * 1000, key="ws_mega_kombajn_v1")

# --- 4. SESSION STATE NA TICKERY ---
if "tickers_text" not in st.session_state:
    st.session_state["tickers_text"] = "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD"

# --- 5. HEADER + ODSWIEŻ ---
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.markdown("<h1 class='ws-title'>💼 WALL STREET MEGA-KOMBAJN ULTRA PRO</h1>", unsafe_allow_html=True)
with col_btn:
    if st.button("🔄 ODSWIEŻ DANE"):
        st.experimental_rerun()

# --- 6. SILNIK ULTRA: MA, EMA, MACD, RSI, ATR, SWING, PIVOT, TP/SL ---
def get_ultra_engine(symbol: str):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty:
            return None

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        open_ = df["Open"]

        last = close.iloc[-1]
        last_high = high.iloc[-1]
        last_low = low.iloc[-1]
        last_open = open_.iloc[-1]

        # MA / EMA
        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        ma100 = close.rolling(100).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        ema200 = close.ewm(span=200).mean().iloc[-1]

        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        macd_val = macd_line.iloc[-1]
        macd_signal = signal_line.iloc[-1]
        macd_hist = macd_val - macd_signal

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain / loss if loss != 0 else 0)))

        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # Swing
        swing_high = high.tail(10).max()
        swing_low = low.tail(10).min()

        # TP/SL
        tp = max(last + atr * 2, swing_high)
        sl = min(last - atr * 1.5, swing_low)

        # Pivot + R1/S1
        pivot = (last_high + last_low + last) / 3
        r1 = 2 * pivot - last_low
        s1 = 2 * pivot - last_high

        # Wolumen relatywny
        vol_rel = df["Volume"].iloc[-1] / df["Volume"].tail(20).mean()

        # Świeca / presja
        body = abs(last - last_open)
        rng = last_high - last_low
        body_pct = (body / rng * 100) if rng != 0 else 0
        pattern = "MOCNA BYCZA" if (last - last_open) > 0.6 * rng else "NEUTRALNA"
        pressure = "BYKI" if last > last_open else "NIEDŹWIEDZIE"

        # Trend score (MA20/50/100/200)
        t1 = 1 if last > ma20 else -1
        t2 = 2 if last > ma50 else -2
        t3 = 2 if last > ma100 else -2
        t4 = 3 if last > ma200 else -3
        score = t1 + t2 + t3 + t4
        trends = f"{'W' if last > ma20 else 'S'}|{'W' if last > ma50 else 'S'}|{'W' if last > ma100 else 'S'}|{'W' if last > ma200 else 'S'}"

        # Sygnał
        if score >= 6 and rsi < 70 and macd_val > macd_signal:
            signal = "KUP"
        elif score <= -4 and rsi > 30 and macd_val < macd_signal:
            signal = "SPRZEDAJ"
        else:
            signal = "TRZYMAJ"

        return {
            "symbol": symbol,
            "price": float(last),
            "bid": tk.info.get("bid", "-"),
            "ask": tk.info.get("ask", "-"),
            "ma20": float(ma20),
            "ma50": float(ma50),
            "ma100": float(ma100),
            "ma200": float(ma200),
            "ema200": float(ema200),
            "macd": float(macd_val),
            "macd_signal": float(macd_signal),
            "macd_hist": float(macd_hist),
            "rsi": float(rsi),
            "atr": float(atr),
            "swing_high": float(swing_high),
            "swing_low": float(swing_low),
            "tp": float(tp),
            "sl": float(sl),
            "pivot": float(pivot),
            "r1": float(r1),
            "s1": float(s1),
            "vol": float(vol_rel),
            "body_pct": float(body_pct),
            "pattern": pattern,
            "pressure": pressure,
            "score": int(score),
            "trends": trends,
            "signal": signal,
            "df": df.tail(120)
        }
    except Exception:
        return None

# --- 7. SIDEBAR: TICKERY (ZAPIS) ---
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

# --- 8. LICZENIE WYNIKÓW ---
results = []
for t in tickers:
    r = get_ultra_engine(t)
    if r:
        results.append(r)

if not results:
    st.warning("Brak danych dla podanych tickerów.")
    st.stop()

# --- 9. TOP 10 WYBICIA (RADAR) ---
st.subheader("🔥 TOP 10 – Największa możliwość wybicia")

def breakout_score(r):
    rsi_factor = max(0, 70 - abs(r["rsi"] - 60))
    macd_factor = max(0, r["macd_hist"]) * 10
    return r["vol"] * 2 + r["score"] * 3 + rsi_factor + macd_factor

top10 = sorted(results, key=lambda x: breakout_score(x), reverse=True)[:10]

cols_top = st.columns(5)
for i, r in enumerate(top10):
    with cols_top[i % 5]:
        st.markdown("<div class='top-card'>", unsafe_allow_html=True)

        # mini-wykres
        chart_df = pd.DataFrame({"Close": r["df"]["Close"].values})
        st.line_chart(chart_df, height=80)

        st.markdown(
            f"<div style='color:#ffd700; font-weight:bold; font-size:1.2rem;'>{r['symbol']}</div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div class='price-tag' style='font-size:1.6rem;'>{r['price']:.2f}</div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<span class='neon-bid'>B: {r['bid']}</span> | "
            f"<span class='neon-ask'>A: {r['ask']}</span>",
            unsafe_allow_html=True
        )
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(
            f"Score: <b>{r['score']}</b> | RSI: <b>{r['rsi']:.1f}</b><br>"
            f"MACD: <b>{r['macd']:.2f}</b> / {r['macd_signal']:.2f}<br>"
            f"Vol x: <b>{r['vol']:.2f}</b>",
            unsafe_allow_html=True
        )
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='signal-{r['signal']}'>{r['signal']}</div>",
            unsafe_allow_html=True
        )

        st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# --- 10. LISTA GŁÓWNA: KAFELKI WALL STREET ---
st.subheader("📊 ANALIZA GŁÓWNA")

for r in results:
    with st.container():
        st.markdown("<div class='mega-card'>", unsafe_allow_html=True)

        # mini-wykres na górze
        chart_df = pd.DataFrame({"Close": r["df"]["Close"].values})
        st.line_chart(chart_df, height=120)

        c1, c2, c3, c4 = st.columns([1.8, 1.6, 1.6, 2.0])

        with c1:
            st.markdown(
                f"<div class='ws-title' style='font-size:2.2rem;'>{r['symbol']}</div>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"<div class='price-tag'>{r['price']:.2f}</div>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"Bid: <span class='neon-bid'>{r['bid']}</span> | "
                f"Ask: <span class='neon-ask'>{r['ask']}</span>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"<br><b>Presja:</b> {r['pressure']}<br>"
                f"<b>Świeca:</b> {r['pattern']} ({r['body_pct']:.1f}% zakresu)",
                unsafe_allow_html=True
            )

        with c2:
            st.markdown("**ŚREDNIE I TREND**")
            st.write(f"MA20: {r['ma20']:.2f}")
            st.write(f"MA50: {r['ma50']:.2f}")
            st.write(f"MA100: {r['ma100']:.2f}")
            st.write(f"MA200: {r['ma200']:.2f}")
            st.write(f"EMA200: {r['ema200']:.2f}")
            st.write(f"Trend: {r['trends']} (Score: {r['score']})")

        with c3:
            st.markdown("**POZIOMY I ZMIENNOŚĆ**")
            st.write(f"Swing High: {r['swing_high']:.2f}")
            st.write(f"Swing Low: {r['swing_low']:.2f}")
            st.write(f"Pivot: {r['pivot']:.2f}")
            st.write(f"R1: {r['r1']:.2f}")
            st.write(f"S1: {r['s1']:.2f}")
            st.write(f"ATR: {r['atr']:.2f}")
            st.write(f"RSI: {r['rsi']:.1f}")
            st.write(f"Vol x: {r['vol']:.2f}")

        with c4:
            st.markdown("**SYGNAŁ I AI**")
            st.markdown(
                f"<div class='signal-{r['signal']}'>{r['signal']}</div>",
                unsafe_allow_html=True
            )
            st.markdown("<br>", unsafe_allow_html=True)
            st.write(f"MACD: {r['macd']:.2f}")
            st.write(f"Signal: {r['macd_signal']:.2f}")
            st.write(f"Histogram: {r['macd_hist']:.2f}")

            if client and st.button(f"PEŁNA DIAGNOZA AI – {r['symbol']}", key=f"ai_{r['symbol']}"):
                with st.spinner("SYSTEM ANALIZUJE..."):
                    prompt = (
                        f"Spółka {r['symbol']}.\n"
                        f"Kurs: {r['price']:.2f}\n"
                        f"Bid/Ask: {r['bid']} / {r['ask']}\n"
                        f"MA20/50/100/200: {r['ma20']:.2f} / {r['ma50']:.2f} / {r['ma100']:.2f} / {r['ma200']:.2f}\n"
                        f"EMA200: {r['ema200']:.2f}\n"
                        f"MACD: {r['macd']:.2f}, sygnał: {r['macd_signal']:.2f}, histogram: {r['macd_hist']:.2f}\n"
                        f"RSI: {r['rsi']:.1f}\n"
                        f"ATR: {r['atr']:.2f}\n"
                        f"Swing High / Low: {r['swing_high']:.2f} / {r['swing_low']:.2f}\n"
                        f"Pivot: {r['pivot']:.2f}, R1: {r['r1']:.2f}, S1: {r['s1']:.2f}\n"
                        f"Trend score: {r['score']} ({r['trends']})\n"
                        f"Wolumen relatywny: {r['vol']:.2f}\n"
                        f"Świeca: {r['pattern']} ({r['body_pct']:.1f}% zakresu), presja: {r['pressure']}\n"
                        f"Sygnał systemowy: {r['signal']}\n\n"
                        "Podaj w 3 punktach:\n"
                        "1) Ocena wejścia (konkretne poziomy, bez definicji)\n"
                        "2) Ryzyko (SL, ATR, zagrożenia)\n"
                        "3) Werdykt (KUP / OBSERWUJ / ODRZUĆ) — krótko, technicznie."
                    )
                    try:
                        resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "Jesteś bezdusznym systemem tradingowym. Mówisz krótko, technicznie, zero lania wody, zero definicji."
                                },
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.05
                        )
                        st.info(resp.choices[0].message.content)
                    except Exception:
                        st.error("Błąd API AI.")
        st.markdown("</div>", unsafe_allow_html=True)
