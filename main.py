import streamlit as st
import yfinance as yf
import pandas as pd
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

# --- KONFIG ---
st.set_page_config(layout="wide", page_title="NEON MEGA-KOMBAJN AI PRO", page_icon="🚀")

# --- STYL NEONOWY ---
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

# --- AI ---
client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# --- AUTOREFRESH ---
st_autorefresh(interval=5 * 60 * 1000, key="neon_ai_pro_v1")

# --- SESSION STATE ---
if "tickers_text" not in st.session_state:
    st.session_state["tickers_text"] = "CDR.WA PKO.WA AAPL NVDA TSLA BTC-USD"

if "ai_single" not in st.session_state:
    st.session_state["ai_single"] = {}

if "ai_portfolio" not in st.session_state:
    st.session_state["ai_portfolio"] = None

if "ai_top10" not in st.session_state:
    st.session_state["ai_top10"] = None

# --- HEADER Z PRZYCISKAMI ---
col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    st.markdown("<h1 class='neon-title'>🚀 MEGA-KOMBAJN ULTRA AI PRO</h1>", unsafe_allow_html=True)
with col2:
    if st.button("🔄 ODSWIEŻ"):
        st.experimental_rerun()
with col3:
    if st.button("💾 ZAPISZ LISTĘ"):
        st.session_state["tickers_text"] = st.session_state["tickers_text"]

# --- FUNKCJE ANALITYCZNE ---

def detect_candle_pattern(df):
    if len(df) < 3:
        return "Brak wystarczającej liczby świec do analizy."
    last = df.iloc[-1]
    prev = df.iloc[-2]

    o, h, l, c = last["Open"], last["High"], last["Low"], last["Close"]
    po, ph, pl, pc = prev["Open"], prev["High"], prev["Low"], prev["Close"]

    body = abs(c - o)
    range_ = h - l
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    txt = []

    if lower_wick > body * 2 and upper_wick < body and c > o:
        txt.append("Możliwy młot (sygnał potencjalnego odbicia wzrostowego).")

    if upper_wick > body * 2 and lower_wick < body and c < o:
        txt.append("Możliwy młot odwrotny (sygnał potencjalnego odwrócenia spadków).")

    if pc > po and c > o and o < pc and c > po and c > pc and o < po:
        txt.append("Możliwe objęcie wzrostowe (byczy sygnał odwrócenia).")

    if pc < po and c < o and o > pc and c < po and c < pc and o > po:
        txt.append("Możliwe objęcie spadkowe (niedźwiedzi sygnał odwrócenia).")

    if not txt:
        txt.append("Brak wyraźnej klasycznej formacji świecowej na ostatniej świecy.")

    return " ".join(txt)


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
    except Exception:
        return None

# --- SIDEBAR: TICKERY ---
st.sidebar.title("💠 KONTROLA")

# Pole tekstowe
tickers_text = st.sidebar.text_area(
    "Wklej tickery:",
    st.session_state["tickers_text"],
    height=200
)

# Zapis do session_state
if st.sidebar.button("💾 ZAPISZ LISTĘ"):
    st.session_state["tickers_text"] = tickers_text
    st.sidebar.success("Lista zapisana!")

# Odświeżanie
if st.sidebar.button("🔄 ODSWIEŻ"):
    st.experimental_rerun()

# Finalna lista tickerów
tickers = [x.strip().upper() for x in st.session_state["tickers_text"].replace(",", " ").split() if x.strip()]

# --- LICZENIE (NAPRAWIONE) ---
results = []
for t in tickers:
    data = ultra(t)
    if data:
        results.append(data)

if not results:
    st.warning("Brak danych — sprawdź tickery.")
    st.stop()


# --- TOP 10 (score + MACD) ---
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

# --- AI PODSUMOWANIE PORTFELA + TOP 10 ---
st.subheader("🧠 AI – portfel i TOP 10")

colp1, colp2 = st.columns([3, 1])
with colp1:
    if client:
        if st.button("🤖 AI podsumowanie portfela"):
            with st.spinner("AI analizuje cały portfel..."):
                summary_prompt = f"""
Jesteś profesjonalnym analitykiem rynków finansowych.
Masz portfel złożony z następujących instrumentów (każdy w osobnym wierszu):

{chr(10).join([f"{r['symbol']}: cena {r['price']:.2f}, sygnał {r['signal']}, RSI {r['rsi']:.1f}, MACD {r['macd']:.2f}, score trendu {r['score']}" for r in results])}

Dodatkowo, TOP 10 według trend score i MACD to:
{", ".join(top10_symbols)}

Zrób:
1. Ogólną ocenę portfela (ryzyko, ekspozycja, momentum).
2. Wskaż najmocniejsze i najsłabsze pozycje.
3. Zaproponuj, które spółki są kandydatami do:
   - DOKUPIENIA
   - REDUKCJI
   - OBSERWACJI
4. Skup się szczególnie na TOP 10.
5. Podsumuj w max 5 zdaniach.
Pisz po polsku, konkretnie, bez lania wody.
"""
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": summary_prompt}]
                )
                st.session_state["ai_portfolio"] = resp.choices[0].message.content

        if st.button("🤖 AI analiza TOP 10"):
            if client:
                with st.spinner("AI analizuje TOP 10..."):
                    top10_data = [r for r in results if r["symbol"] in top10_symbols]
                    top10_prompt = f"""
Jesteś profesjonalnym analitykiem technicznym.
Masz listę TOP 10 instrumentów (najmocniejsze sygnały trendu):

{chr(10).join([f"{r['symbol']}: cena {r['price']:.2f}, score {r['score']}, sygnał {r['signal']}, RSI {r['rsi']:.1f}, MACD {r['macd']:.2f}" for r in top10_data])}

Zrób:
1. Krótki ranking (1–10) z komentarzem, dlaczego dana spółka jest wyżej/niżej.
2. Wskaż 3 najlepsze kandydatury do agresywnego wejścia.
3. Wskaż 3 spółki, przy których zalecasz ostrożność (np. wykupienie, słaby wolumen, ryzyko odwrócenia).
4. Podsumuj w max 4 zdaniach.
Pisz po polsku, konkretnie.
"""
                    resp2 = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": top10_prompt}]
                    )
                    st.session_state["ai_top10"] = resp2.choices[0].message.content
    else:
        st.info("Dodaj OPENAI_API_KEY do st.secrets, aby włączyć AI.")

with colp1:
    if st.session_state["ai_portfolio"]:
        st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
        st.markdown("### 📊 AI podsumowanie portfela")
        st.write(st.session_state["ai_portfolio"])
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state["ai_top10"]:
        st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
        st.markdown("### 🏆 AI analiza TOP 10")
        st.write(st.session_state["ai_top10"])
        st.markdown("</div>", unsafe_allow_html=True)

with colp2:
    st.markdown("### 🏆 TOP 10 (score + MACD)")
    st.dataframe(df_sorted.head(10).reset_index(drop=True))

st.divider()

# --- RADAR WYBIĆ (VOL) ---
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

# --- KAFLE GŁÓWNE – SPÓŁKI ---
st.subheader("📊 Analiza główna – spółki")

for r in results:
    with st.container():
        st.markdown(f"<div class='mega-card'>", unsafe_allow_html=True)
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
            st.write(f"MA100: **{r['ma100']:.2f}** | MA200: **{r['ma200']:.2f}**")
            st.write(f"EMA200: **{r['ema200']:.2f}**")
            st.write(f"Score trendu: **{r['score']}** | Sygnał: **{r['signal']}**")

        with c3:
            st.write(f"MACD: **{r['macd']:.2f}**")
            st.write(f"Signal: **{r['macd_sig']:.2f}**")
            st.write(f"Histogram: **{r['macd_hist']:.2f}**")
            st.write(f"RSI: **{r['rsi']:.1f}** | ATR: **{r['atr']:.2f}**")

        with c4:
            st.markdown(f"<div class='signal-{r['signal']}'>{r['signal']}</div>", unsafe_allow_html=True)
            st.markdown("<div class='pro-box'><b>PRO – świece:</b><br>" + r["candle_comment"] + "</div>", unsafe_allow_html=True)
            st.markdown(f"TP: <span class='tp-val'>{r['tp']:.2f}</span> | SL: <span class='sl-val'>{r['sl']:.2f}</span>", unsafe_allow_html=True)
            st.write(f"Pivot: {r['pivot']:.2f} | R1: {r['r1']:.2f} | S1: {r['s1']:.2f}")

            if client:
                if st.button(f"PEŁNA DIAGNOZA AI 🤖 ({r['symbol']})", key=f"ai_{r['symbol']}"):
                    with st.spinner("SYSTEM ANALIZUJE..."):
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
Wolumen relatywny: {r['vol']:.2f}

Swing High: {r['swing_high']:.2f}
Swing Low: {r['swing_low']:.2f}

TP: {r['tp']:.2f}
SL: {r['sl']:.2f}

Pivot: {r['pivot']:.2f}
R1: {r['r1']:.2f}
S1: {r['s1']:.2f}

Trend score: {r['score']}
Sygnał systemu: {r['signal']}
Komentarz świecowy: {r['candle_comment']}

Zrób:
1. Analizę trendu (krótki / średni / długi termin).
2. Analizę momentum (MACD, RSI) – przyspieszenie, dywergencje, wykupienie/wyprzedanie.
3. Analizę wolumenową – czy ruch jest wsparty wolumenem.
4. Interpretację formacji świecowej (jeśli jest sensowna).
5. Wskaż kluczowe poziomy techniczne (wsparcia, opory, TP, SL, pivot).
6. Zaproponuj scenariusz wzrostowy i spadkowy z konkretnymi poziomami.
7. Podsumuj w max 4 zdaniach, czy bardziej wygląda to na:
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
