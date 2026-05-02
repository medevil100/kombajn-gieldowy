import streamlit as st
import yfinance as yf
import pandas as pd
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# ============================================================
# 1. KONFIG + NEON STYL
# ============================================================

st.set_page_config(layout="wide", page_title="NEON MEGA-KOMBAJN AI PRO", page_icon="🚀")

st.markdown("""
<style>
body { background-color: #050510; color: #e0e0ff; }
.stApp { background-color: #050510; }

.mega-card {
    border: 2px solid #222;
    padding: 30px;
    border-radius: 20px;
    background: #0a0a18;
    box-shadow: 0 0 25px #39FF1422;
    margin-bottom: 30px;
}
.top-card {
    border: 1px solid #333;
    padding: 15px;
    border-radius: 12px;
    background: #0c0c1e;
    font-size: 1rem;
    line-height: 1.4;
    min-height: 300px;
    text-align: center;
}
.neon-title {
    color: #39FF14;
    font-weight: bold;
    font-size: 3.5rem;
    text-shadow: 0 0 15px #39FF14;
}
.price-tag {
    font-size: 2.8rem;
    font-weight: bold;
    color: #ffffff;
}
.neon-bid {
    color: #00FF00;
    font-weight: bold;
    font-size: 1.2rem;
    text-shadow: 0 0 5px #00FF00;
}
.neon-ask {
    color: #FF0000;
    font-weight: bold;
    font-size: 1.2rem;
    text-shadow: 0 0 5px #FF0000;
}
.tp-val {
    color: #00FF00;
    font-weight: bold;
    font-size: 1.3rem;
}
.sl-val {
    color: #FF3131;
    font-weight: bold;
    font-size: 1.3rem;
}
.signal-KUP {
    color: #39FF14;
    font-weight: bold;
    text-shadow: 0 0 10px #39FF14;
    border: 2px solid #39FF14;
    padding: 10px;
    border-radius: 10px;
    font-size: 1.4rem;
}
.signal-SPRZEDAJ {
    color: #FF3131;
    font-weight: bold;
    text-shadow: 0 0 10px #FF3131;
    border: 2px solid #FF3131;
    padding: 10px;
    border-radius: 10px;
    font-size: 1.4rem;
}
.signal-TRZYMAJ {
    color: #00FFFF;
    font-weight: bold;
    border: 2px solid #00FFFF;
    padding: 10px;
    border-radius: 10px;
    font-size: 1.4rem;
}
.stButton>button {
    background-color: #1a1a1a;
    color: #39FF14;
    border: 2px solid #39FF14;
    width: 100%;
    font-weight: bold;
    height: 3.2rem;
    font-size: 1.1rem;
    box-shadow: 0 0 20px #39FF1444;
}
.ai-box {
    margin-top:10px;
    padding:10px;
    border-radius:12px;
    border:1px solid #303f9f;
    background:rgba(10,15,35,0.9);
    text-align:left;
    font-size:0.9rem;
}
.pro-box {
    margin-top:8px;
    padding:8px;
    border-radius:10px;
    border:1px dashed #607d8b;
    background:rgba(5,10,25,0.9);
    text-align:left;
    font-size:0.85rem;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 2. AI
# ============================================================

client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st_autorefresh(interval=5 * 60 * 1000, key="neon_ai_pro_v1")

# ============================================================
# 3. SESSION STATE
# ============================================================

if "tickers_text" not in st.session_state:
    st.session_state["tickers_text"] = "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD"

if "ai_single" not in st.session_state:
    st.session_state["ai_single"] = {}

if "ai_portfolio" not in st.session_state:
    st.session_state["ai_portfolio"] = None

if "ai_top10" not in st.session_state:
    st.session_state["ai_top10"] = None

# ============================================================
# 4. HEADER Z PRZYCISKAMI (NAPRAWIONE)
# ============================================================

col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    st.markdown("<h1 class='neon-title'>🚀 MEGA-KOMBAJN ULTRA AI PRO</h1>", unsafe_allow_html=True)

with col2:
    if st.button("🔄 ODSWIEŻ"):
        st.rerun()

with col3:
    if st.button("💾 ZAPISZ LISTĘ"):
        st.session_state["tickers_text"] = st.session_state["tickers_text"]
        st.success("Lista spółek zapisana!")

# ============================================================
# 5. SIDEBAR — TICKERY (NAPRAWIONE)
# ============================================================

st.sidebar.title("💠 KONTROLA")

tickers_text = st.sidebar.text_area(
    "Wklej tickery:",
    value=st.session_state["tickers_text"],
    height=200
)

# aktualizacja session_state
st.session_state["tickers_text"] = tickers_text

tickers = [x.strip().upper() for x in tickers_text.replace(",", " ").split() if x.strip()]

# ============================================================
# 6. SILNIK ANALITYCZNY AI PRO
# ============================================================

def detect_candle_pattern(df):
    if len(df) < 3:
        return "Brak wystarczającej liczby świec."
    last = df.iloc[-1]
    prev = df.iloc[-2]

    o, h, l, c = last["Open"], last["High"], last["Low"], last["Close"]
    po, ph, pl, pc = prev["Open"], prev["High"], prev["Low"], prev["Close"]

    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l

    out = []

    if lower > body * 2 and upper < body:
        out.append("Młot (odbicie).")

    if upper > body * 2 and lower < body:
        out.append("Młot odwrotny (odwrócenie).")

    if pc < po and c > o and c > pc and o < po:
        out.append("Objęcie wzrostowe.")

    if pc > po and c < o and c < pc and o > po:
        out.append("Objęcie spadkowe.")

    return " ".join(out) if out else "Brak formacji świecowych."

def ultra(symbol):
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

        # MA
        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        ma100 = close.rolling(100).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        ema200 = close.ewm(span=200).mean().iloc[-1]

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9).mean()
        macd = macd_line.iloc[-1]
        macd_sig = macd_signal.iloc[-1]
        macd_hist = macd - macd_sig

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rs = gain / loss if loss != 0 else 999
        rsi = 100 - (100 / (1 + rs))

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

        tp = max(last + atr * 2, swing_high)
        sl = min(last - atr * 1.5, swing_low)

        pivot = (high.iloc[-1] + low.iloc[-1] + last) / 3
        r1 = 2 * pivot - low.iloc[-1]
        s1 = 2 * pivot - high.iloc[-1]

        vol_rel = df["Volume"].iloc[-1] / df["Volume"].tail(20).mean()

        score = sum([
            1 if last > ma20 else -1,
            2 if last > ma50 else -2,
            2 if last > ma100 else -2,
            3 if last > ma200 else -3
        ])

        if score >= 6 and macd > macd_sig:
            signal = "KUP"
        elif score <= -4 and macd < macd_sig:
            signal = "SPRZEDAJ"
        else:
            signal = "TRZYMAJ"

        candle_comment = detect_candle_pattern(df.tail(30))

        return {
            "symbol": symbol,
            "price": float(last),
            "bid": tk.info.get("bid", "-"),
            "ask": tk.info.get("ask", "-"),
            "ma20": float(ma20), "ma50": float(ma50),
            "ma100": float(ma100), "ma200": float(ma200),
            "ema200": float(ema200),
            "macd": float(macd), "macd_sig": float(macd_sig), "macd_hist": float(macd_hist),
            "rsi": float(rsi), "atr": float(atr),
            "swing_high": float(swing_high), "swing_low": float(swing_low),
            "tp": float(tp), "sl": float(sl),
            "pivot": float(pivot), "r1": float(r1), "s1": float(s1),
            "vol": float(vol_rel),
            "score": int(score),
            "signal": signal,
            "candle_comment": candle_comment,
            "df": df.tail(120)
        }
    except:
        return None

# ============================================================
# 7. LICZENIE (NAPRAWIONE)
# ============================================================

results = []
for t in tickers:
    data = ultra(t)
    if data:
        results.append(data)

if not results:
    st.warning("Brak danych — sprawdź tickery.")
    st.stop()

# ============================================================
# 8. TOP 10 + AI PORTFEL + AI TOP10
# ============================================================

df_res = pd.DataFrame([
    {
        "symbol": r["symbol"],
        "price": r["price"],
        "score": r["score"],
        "signal": r["signal"],
        "rsi": r["rsi"],
        "macd": r["macd"],
        "vol": r["vol"],
    }
    for r in results
])

df_sorted = df_res.sort_values(by=["score", "macd"], ascending=[False, False])
top10_symbols = df_sorted.head(10)["symbol"].tolist()

st.subheader("🧠 AI – portfel i TOP 10")

colp1, colp2 = st.columns([3, 1])

with colp1:
    if client:
        if st.button("🤖 AI podsumowanie portfela"):
            with st.spinner("AI analizuje portfel..."):
                prompt = f"""
Analiza portfela:
{chr(10).join([f"{r['symbol']}: cena {r['price']}, score {r['score']}, RSI {r['rsi']}, MACD {r['macd']}" for r in results])}

TOP10: {", ".join(top10_symbols)}

Zrób analizę ryzyka, momentum, siły trendu i rekomendacje.
"""
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}]
                )
                st.session_state["ai_portfolio"] = resp.choices[0].message.content

        if st.button("🤖 AI analiza TOP 10"):
            with st.spinner("AI analizuje TOP 10..."):
                prompt = f"""
TOP10:
{chr(10).join(top10_symbols)}

Zrób ranking, 3 najlepsze okazje i 3 ostrzeżenia.
"""
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}]
                )
                st.session_state["ai_top10"] = resp.choices[0].message.content

    if st.session_state["ai_portfolio"]:
        st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
        st.write(st.session_state["ai_portfolio"])
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state["ai_top10"]:
        st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
        st.write(st.session_state["ai_top10"])
        st.markdown("</div>", unsafe_allow_html=True)

with colp2:
    st.markdown("### 🏆 TOP 10")
    st.dataframe(df_sorted.head(10))

st.divider()

# ============================================================
# 9. RADAR WYBIĆ (VOL)
# ============================================================

st.subheader("🔥 RADAR WYBIĆ (wolumen relatywny)")

top_vol = df_res.sort_values(by="vol", ascending=False).head(10)

for i in range(0, len(top_vol), 5):
    cols = st.columns(5)
    for j, (_, item) in enumerate(top_vol.iloc[i:i+5].iterrows()):
        with cols[j]:
            r = next(x for x in results if x["symbol"] == item["symbol"])
            st.markdown(f"""
            <div class="top-card">
                <div style="color:#39FF14; font-weight:bold; font-size:1.4rem;">{r['symbol']}</div>
                <div style="font-size:1.6rem; font-weight:bold;">{r['price']:.2f}</div>
                <span class="neon-bid">B: {r['bid']}</span> | <span class="neon-ask">A: {r['ask']}</span><hr>
                <b>TP: <span class="tp-val">{r['tp']:.2f}</span></b><br>
                <b>SL: <span class="sl-val">{r['sl']:.2f}</span></b><hr>
                <b>Score:</b> {r['score']} | <b>RSI:</b> {r['rsi']:.1f}<br>
                <div class="signal-{r['signal']}" style="margin-top:10px; font-size:1rem;">{r['signal']}</div>
            </div>
            """, unsafe_allow_html=True)

st.divider()

# ============================================================
# 10. KAFLE GŁÓWNE — SPÓŁKI
# ============================================================

st.subheader("📊 Analiza główna – spółki")

for r in results:
    with st.container():
        st.markdown("<div class='mega-card'>", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns([1.8, 1.5, 1.3, 2.5])

        with c1:
            st.markdown(f"<div class='neon-title' style='font-size:3rem;'>{r['symbol']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='price-tag'>{r['price']:.2f}</div>", unsafe_allow_html=True)
            st.markdown(
                f"Bid: <span class='neon-bid'>{r['bid']}</span> | "
                f"Ask: <span class='neon-ask'>{r['ask']}</span>",
                unsafe_allow_html=True
            )

        with c2:
            st.write(f"MA20: **{r['ma20']:.2f}** | MA50: **{r['ma50']:.2f}**")
            st
