import streamlit as st
import yfinance as yf
import pandas as pd
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- KONFIG ---
st.set_page_config(layout="wide", page_title="WALL STREET ULTRA AI", page_icon="💼")

# --- CSS WALL STREET ---
st.markdown("""
<style>
body { background:#020612; color:#e0e0ff; }
.stApp { background:#020612; }

.tile {
    border-radius:18px; padding:18px; text-align:center;
    border:1px solid #1b2838; box-shadow:0 0 25px #000000aa;
    min-height:420px;
    background:linear-gradient(145deg, #050b18 0%, #020612 60%, #0b101f 100%);
}

.signal-KUP { color:#ffd700; border:1px solid #ffd700; padding:6px; border-radius:10px; font-weight:bold; }
.signal-SPRZEDAJ { color:#ff4b4b; border:1px solid #ff4b4b; padding:6px; border-radius:10px; font-weight:bold; }
.signal-TRZYMAJ { color:#00bcd4; border:1px solid #00bcd4; padding:6px; border-radius:10px; font-weight:bold; }

.price { font-size:2.2rem; font-weight:bold; color:white; }
.neon-bid { color:#7CFC00; font-weight:bold; }
.neon-ask { color:#ff4b4b; font-weight:bold; }

.stButton>button {
    background:#08101f; border:1px solid #ffd700;
    color:#ffd700; font-weight:bold; width:100%;
    box-shadow:0 0 15px #000000aa;
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
</style>
""", unsafe_allow_html=True)

# --- AI ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# --- AUTOREFRESH ---
st_autorefresh(interval=5 * 60 * 1000, key="ws_ultra_v1")

# --- SESSION STATE NA TICKERY ---
if "tickers_text" not in st.session_state:
    st.session_state["tickers_text"] = "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD"

if "ai_single" not in st.session_state:
    st.session_state["ai_single"] = {}

if "ai_portfolio" not in st.session_state:
    st.session_state["ai_portfolio"] = None

# --- HEADER ---
col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    st.markdown("<h1 style='color:#ffd700;'>💼 WALL STREET ULTRA AI</h1>", unsafe_allow_html=True)
with col2:
    if st.button("🔄 ODSWIEŻ"):
        st.experimental_rerun()
with col3:
    st.write("")  # placeholder

# --- ULTRA ENGINE ---
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

        # MA / EMA
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
        rsi = 100 - (100 / (1 + (gain / loss if loss != 0 else 0.0001)))

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

        # Pivot
        pivot = (high.iloc[-1] + low.iloc[-1] + last) / 3
        r1 = 2 * pivot - low.iloc[-1]
        s1 = 2 * pivot - high.iloc[-1]

        # Vol rel
        vol_rel = df["Volume"].iloc[-1] / df["Volume"].tail(20).mean()

        # Trend score
        score = sum([
            1 if last > ma20 else -1,
            2 if last > ma50 else -2,
            2 if last > ma100 else -2,
            3 if last > ma200 else -3
        ])

        # Signal
        if score >= 6 and macd > macd_sig:
            signal = "KUP"
        elif score <= -4 and macd < macd_sig:
            signal = "SPRZEDAJ"
        else:
            signal = "TRZYMAJ"

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
            "df": df.tail(120)
        }
    except Exception:
        return None

# --- SIDEBAR ---
st.sidebar.markdown("## ⚙️ Ustawienia")
tickers_text = st.sidebar.text_area("Tickery:", st.session_state["tickers_text"], height=200)
st.session_state["tickers_text"] = tickers_text
tickers = [x.strip().upper() for x in tickers_text.replace(",", " ").split() if x.strip()]

# --- LICZENIE ---
results = []
for t in tickers:
    data = ultra(t)
    if data:
        results.append(data)

if not results:
    st.warning("Brak danych.")
    st.stop()

# --- AI PODSUMOWANIE PORTFELA ---
st.subheader("🧠 AI – podsumowanie portfela")

colp1, colp2 = st.columns([3, 1])
with colp1:
    if client:
        if st.button("🤖 Wygeneruj AI podsumowanie portfela"):
            with st.spinner("AI analizuje cały portfel..."):
                summary_prompt = f"""
Jesteś profesjonalnym analitykiem rynków finansowych.
Masz portfel złożony z następujących instrumentów (każdy w osobnym wierszu):

{chr(10).join([f"{r['symbol']}: cena {r['price']:.2f}, sygnał {r['signal']}, RSI {r['rsi']:.1f}, MACD {r['macd']:.2f}, score trendu {r['score']}" for r in results])}

Zrób:
1. Ogólną ocenę portfela (ryzyko, ekspozycja, momentum).
2. Wskaż najmocniejsze i najsłabsze pozycje.
3. Zaproponuj, które spółki są kandydatami do:
   - DOKUPIENIA
   - REDUKCJI
   - OBSERWACJI
4. Podsumuj w max 5 zdaniach.
Pisz po polsku, konkretnie, bez lania wody.
"""
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": summary_prompt}]
                )
                st.session_state["ai_portfolio"] = resp.choices[0].message.content

    else:
        st.info("Dodaj OPENAI_API_KEY do st.secrets, aby włączyć AI.")

with colp1:
    if st.session_state["ai_portfolio"]:
        st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
        st.markdown("### 📊 AI podsumowanie portfela")
        st.write(st.session_state["ai_portfolio"])
        st.markdown("</div>", unsafe_allow_html=True)

# --- KAFELKI GŁÓWNE ---
st.subheader("📊 Analiza główna – spółki")

cols = st.columns(3)

for i, r in enumerate(results):
    with cols[i % 3]:
        st.markdown(f"<div class='tile'>", unsafe_allow_html=True)

        # mini chart
        st.line_chart(pd.DataFrame({"Close": r["df"]["Close"]}), height=80)

        st.markdown(
            f"<div class='price'>{r['symbol']} — {r['price']:.2f}</div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<span class='neon-bid'>B: {r['bid']}</span> | "
            f"<span class='neon-ask'>A: {r['ask']}</span>",
            unsafe_allow_html=True
        )

        st.markdown("<hr>", unsafe_allow_html=True)

        st.write(f"MA20: {r['ma20']:.2f} | MA50: {r['ma50']:.2f}")
        st.write(f"MA100: {r['ma100']:.2f} | MA200: {r['ma200']:.2f}")
        st.write(f"EMA200: {r['ema200']:.2f}")

        st.markdown("<hr>", unsafe_allow_html=True)

        st.write(f"MACD: {r['macd']:.2f}")
        st.write(f"Signal: {r['macd_sig']:.2f}")
        st.write(f"Histogram: {r['macd_hist']:.2f}")

        st.markdown("<hr>", unsafe_allow_html=True)

        st.write(f"RSI: {r['rsi']:.1f} | ATR: {r['atr']:.2f}")
        st.write(f"Swing High: {r['swing_high']:.2f}")
        st.write(f"Swing Low: {r['swing_low']:.2f}")

        st.markdown("<hr>", unsafe_allow_html=True)

        st.write(f"TP: {r['tp']:.2f} | SL: {r['sl']:.2f}")
        st.write(f"Pivot: {r['pivot']:.2f} | R1: {r['r1']:.2f} | S1: {r['s1']:.2f}")

        st.markdown(f"<div class='signal-{r['signal']}'>{r['signal']}</div>", unsafe_allow_html=True)

        # --- AI ANALIZA DLA POJEDYNCZEJ SPÓŁKI ---
        if client:
            if st.button(f"🤖 AI analiza – {r['symbol']}", key=f"ai_{r['symbol']}"):
                with st.spinner(f"AI analizuje {r['symbol']}..."):
                    prompt = f"""
Jesteś profesjonalnym analitykiem rynków finansowych.
Przeanalizuj instrument {r['symbol']} na podstawie danych:

Cena: {r['price']:.2f}
MA20: {r['ma20']:.2f}, MA50: {r['ma50']:.2f}, MA100: {r['ma100']:.2f}, MA200: {r['ma200']:.2f}
EMA200: {r['ema200']:.2f}

MACD: {r['macd']:.2f}
MACD sygnał: {r['macd_sig']:.2f}
MACD histogram: {r['macd_hist']:.2f}

RSI: {r['rsi']:.1f}
ATR: {r['atr']:.2f}
Wolumen relatywny (ostatnia sesja / średnia 20): {r['vol']:.2f}

Swing High: {r['swing_high']:.2f}
Swing Low: {r['swing_low']:.2f}

TP (take profit): {r['tp']:.2f}
SL (stop loss): {r['sl']:.2f}

Pivot: {r['pivot']:.2f}
R1: {r['r1']:.2f}
S1: {r['s1']:.2f}

Trend score: {r['score']}
Sygnał systemu: {r['signal']}

Zrób:
1. Analizę trendu (krótki / średni / długi termin).
2. Analizę momentum (MACD, RSI) – czy jest przyspieszenie, dywergencje, wykupienie/wyprzedanie.
3. Analizę wolumenową – czy ruch jest wsparty wolumenem.
4. Wskaż kluczowe poziomy techniczne (wsparcia, opory, TP, SL, pivot).
5. Zaproponuj scenariusz wzrostowy i spadkowy z konkretnymi poziomami.
6. Podsumuj w max 4 zdaniach, czy bardziej wygląda to na:
   - okazję do wejścia
   - trzymanie pozycji
   - realizację zysków / redukcję
Pisz po polsku, konkretnie, bez lania wody.
"""
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    st.session_state["ai_single"][r["symbol"]] = resp.choices[0].message.content

        if r["symbol"] in st.session_state["ai_single"]:
            st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
            st.markdown("#### 🤖 AI analiza")
            st.write(st.session_state["ai_single"][r["symbol"]])
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
