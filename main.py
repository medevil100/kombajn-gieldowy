import streamlit as st
import yfinance as yf
import pandas as pd
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import requests
import time
import datetime
import xml.etree.ElementTree as ET

# ============================================================
# 1. KONFIG + NEON STYL (ciemniejszy zielony)
# ============================================================

st.set_page_config(
    layout="wide",
    page_title="NEON MEGA-KOMBAJN ULTRA AI PRO",
    page_icon="🚀"
)

st.markdown("""
<style>
body { background-color: #050510; color: #e0e0ff; }
.stApp { background-color: #050510; }

.mega-card {
    border: 2px solid #222;
    padding: 30px;
    border-radius: 20px;
    background: #07140a;
    box-shadow: 0 0 25px #0aff0a22;
    margin-bottom: 30px;
}
.top-card {
    border: 1px solid #333;
    padding: 15px;
    border-radius: 12px;
    background: #07140a;
    font-size: 1rem;
    line-height: 1.4;
    min-height: 300px;
    text-align: center;
}
.neon-title {
    color: #0aff0a;
    font-weight: bold;
    font-size: 3.5rem;
    text-shadow: 0 0 15px #0aff0a;
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
# 2. AI KLIENT + AUTOREFRESH
# ============================================================

client = None
if "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st_autorefresh(interval=5 * 60 * 1000, key="neon_ai_pro_v1")

# ============================================================
# 3. SESSION STATE
# ============================================================

if "tickers_text" not in st.session_state:
    st.session_state["tickers_text"] = "HUMA, TCRX, GOSS, PLRX, TTOO, BNOX, IMUX, SLS, DRMA, BDRX, MREO, XLO, TCON, VIRI, ACRS, AURA, KTRA, VINC, NRSN, ANIX, CRVS, ADVM, APM, SABS, HILS, RNAZ, SLNO, IMNN, BCTX, ATHE, MNOV, BOLT, INFI, APLT, CLRB, ENLV, EVGN, GRTS, HSTO, IMMP,ADV.WA, MDB.WA, ONO.WA, PUR.WA, NNG.WA, GX1.WA, GMT.WA, RDG.WA, MAB.WA, SEL.WA, BIO.WA, BML.WA, BPC.WA, BRS.WA, COG.WA, CRL.WA, CRP.WA, DCR.WA, DRP.WA, ENP.WA, EPC.WA, ERG.WA, FHD.WA, GRC.WA, INC.WA, ITP.WA, KPL.WA, MNC.WA, MZN.WA, ONC.WA, PCF.WA, PGM.WA, PMG.WA, PNT.WA, SNP.WA, SNT.WA, TXM.WA, URS.WA, VRC.WA, VRG.WA,"

if "ai_single" not in st.session_state:
    st.session_state["ai_single"] = {}

if "ai_portfolio" not in st.session_state:
    st.session_state["ai_portfolio"] = None

if "ai_top10" not in st.session_state:
    st.session_state["ai_top10"] = None

if "news_auto_mode" not in st.session_state:
    st.session_state["news_auto_mode"] = False

if "news_last_run" not in st.session_state:
    st.session_state["news_last_run"] = None

# ============================================================
# 4. HEADER Z ODSWIEŻ + ZAPISZ LISTĘ
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
# 5. SIDEBAR — LISTA TICKERÓW + NEWS STEROWANIE
# ============================================================

st.sidebar.title("💠 KONTROLA")

tickers_text = st.sidebar.text_area(
    "Wklej tickery:",
    value=st.session_state["tickers_text"],
    height=200
)

st.session_state["tickers_text"] = tickers_text

tickers = [
    x.strip().upper()
    for x in tickers_text.replace(",", " ").split()
    if x.strip()
]

st.sidebar.markdown("---")
st.sidebar.subheader("📰 NEWS IMPACT ENGINE 3.0")

news_auto = st.sidebar.checkbox("Auto monitoring newsów", value=st.session_state["news_auto_mode"])
st.session_state["news_auto_mode"] = news_auto
news_manual_scan = st.sidebar.button("Ręczne skanowanie newsów")
news_restart = st.sidebar.button("Restart cyklu newsów")

if news_restart:
    st.session_state["news_last_run"] = None

# ============================================================
# 6. SILNIK ANALITYCZNY AI PRO (NIETKNIĘTY)
# ============================================================

def detect_candle_pattern(df: pd.DataFrame) -> str:
    if len(df) < 3:
        return "Brak wystarczającej liczby świec do analizy."

    last = df.iloc[-1]
    prev = df.iloc[-2]

    o, h, l, c = last["Open"], last["High"], last["Low"], last["Close"]
    po, ph, pl, pc = prev["Open"], prev["High"], prev["Low"], prev["Close"]

    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l

    sygnaly = []

    if lower > body * 2 and upper < body and c > o:
        sygnaly.append("Możliwy młot (bycze odbicie).")

    if upper > body * 2 and lower < body and c < o:
        sygnaly.append("Możliwy młot odwrotny (potencjalne odwrócenie).")

    if pc < po and c > o and c > pc and o < po:
        sygnaly.append("Możliwe objęcie wzrostowe (bycze odwrócenie).")

    if pc > po and c < o and c < pc and o > po:
        sygnaly.append("Możliwe objęcie spadkowe (niedźwiedzie odwrócenie).")

    if not sygnaly:
        return "Brak wyraźnej klasycznej formacji świecowej."

    return " ".join(sygnaly)


def ultra(symbol: str):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period="1y")
        if df.empty:
            return None

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        last = float(close.iloc[-1])

        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma100 = float(close.rolling(100).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        ema200 = float(close.ewm(span=200).mean().iloc[-1])

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9).mean()
        macd = float(macd_line.iloc[-1])
        macd_sig = float(macd_signal.iloc[-1])
        macd_hist = float(macd - macd_sig)

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).rolling(14).mean().iloc[-1]
        rs = gain / loss if loss != 0 else 999
        rsi = float(100 - (100 / (1 + rs)))

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

        swing_high = float(high.tail(10).max())
        swing_low = float(low.tail(10).min())

        tp = max(last + atr * 2, swing_high)
        sl = min(last - atr * 1.5, swing_low)

        ph, pl, pc = float(high.iloc[-1]), float(low.iloc[-1]), last
        pivot = (ph + pl + pc) / 3
        r1 = 2 * pivot - pl
        s1 = 2 * pivot - ph

        vol_rel = float(df["Volume"].iloc[-1] / df["Volume"].tail(20).mean())

        score = 0
        score += 1 if last > ma20 else -1
        score += 2 if last > ma50 else -2
        score += 2 if last > ma100 else -2
        score += 3 if last > ma200 else -3

        if score >= 6 and macd > macd_sig and rsi < 70:
            signal = "KUP"
        elif score <= -4 and macd < macd_sig and rsi > 30:
            signal = "SPRZEDAJ"
        else:
            signal = "TRZYMAJ"

        candle_comment = detect_candle_pattern(df.tail(30))

        return {
            "symbol": symbol,
            "price": last,
            "bid": tk.info.get("bid", "-"),
            "ask": tk.info.get("ask", "-"),
            "ma20": ma20,
            "ma50": ma50,
            "ma100": ma100,
            "ma200": ma200,
            "ema200": ema200,
            "macd": macd,
            "macd_sig": macd_sig,
            "macd_hist": macd_hist,
            "rsi": rsi,
            "atr": atr,
            "swing_high": swing_high,
            "swing_low": swing_low,
            "tp": tp,
            "sl": sl,
            "pivot": pivot,
            "r1": r1,
            "s1": s1,
            "vol": vol_rel,
            "score": int(score),
            "signal": signal,
            "candle_comment": candle_comment,
            "df": df.tail(120)
        }
    except Exception:
        return None

# ============================================================
# NEWS IMPACT ENGINE 3.0 — FUNKCJE
# ============================================================

RSS_SOURCES = [
    "https://www.bankier.pl/rss/wiadomosci.xml",
    "https://stooq.pl/rss/news.xml",
    "https://www.money.pl/rss/wiadomosci.xml",
    "https://www.parkiet.com/rss",
    "https://biznes.interia.pl/feed",
]

GPW_ESPI = [
    "https://www.gpw.pl/rss/komunikaty_espi",
    "https://www.gpw.pl/rss/komunikaty_ebi",
]

MACRO_SOURCES = [
    "https://www.forexfactory.com/ffcal_week_this.xml",
]

NEWS_API_KEY = st.secrets.get("NEWS_API_KEY", None)
TWITTER_BEARER = st.secrets.get("TWITTER_BEARER", None)

def parse_rss(url):
    items = []
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return items
        root = ET.fromstring(r.content)
        for item in root.iter("item"):
            title = item.findtext("title", default="").strip()
            link = item.findtext("link", default="").strip()
            pub = item.findtext("pubDate", default="").strip()
            desc = item.findtext("description", default="").strip()
            items.append(
                {
                    "source": url,
                    "title": title,
                    "link": link,
                    "published": pub,
                    "summary": desc,
                }
            )
    except Exception:
        pass
    return items

def fetch_newsapi_for_ticker(ticker):
    if not NEWS_API_KEY:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": ticker,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": NEWS_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        out = []
        for a in data.get("articles", []):
            out.append(
                {
                    "source": a.get("source", {}).get("name", ""),
                    "title": a.get("title", ""),
                    "link": a.get("url", ""),
                    "published": a.get("publishedAt", ""),
                    "summary": a.get("description", "") or "",
                }
            )
        return out
    except Exception:
        return []

def fetch_twitter_for_ticker(ticker):
    if not TWITTER_BEARER:
        return []
    url = "https://api.twitter.com/2/tweets/search/recent"
    query = f"{ticker} lang:en -is:retweet"
    headers = {"Authorization": f"Bearer {TWITTER_BEARER}"}
    params = {
        "query": query,
        "max_results": 20,
        "tweet.fields": "created_at,text",
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        out = []
        for t in data.get("data", []):
            out.append(
                {
                    "source": "Twitter",
                    "title": t.get("text", "")[:120],
                    "link": f"https://twitter.com/i/web/status/{t.get('id')}",
                    "published": t.get("created_at", ""),
                    "summary": t.get("text", ""),
                }
            )
        return out
    except Exception:
        return []

POSITIVE_WORDS = [
    "profit", "zysk", "record", "rekord", "upgrade", "podwyższa", "raise",
    "contract", "kontrakt", "acquisition", "przejęcie", "buyback", "skup akcji",
    "dividend", "dywidenda", "beats", "powyżej oczekiwań",
]

NEGATIVE_WORDS = [
    "loss", "strata", "downgrade", "obniża", "lawsuit", "pozew", "emission",
    "emisja akcji", "warning", "profit warning", "bankruptcy", "upadłość",
    "suspension", "zawieszenie", "problem", "awaria",
]

HIGH_IMPACT_WORDS = [
    "emisja akcji", "profit warning", "upadłość", "bankruptcy", "wezwanie",
    "tender offer", "acquisition", "przejęcie", "merger", "fuzja",
    "results", "wyniki finansowe", "dywidenda", "dividend",
]

def classify_impact(text):
    t = text.lower()
    score = 0
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    high = sum(1 for w in HIGH_IMPACT_WORDS if w in t)

    score += pos * 10
    score -= neg * 10
    score += high * 15

    sentiment = "neutral"
    if pos > neg:
        sentiment = "positive"
    elif neg > pos:
        sentiment = "negative"

    direction = "neutral"
    if sentiment == "positive":
        direction = "bullish"
    elif sentiment == "negative":
        direction = "bearish"

    impact_abs = abs(score)
    if impact_abs >= 70:
        impact_level = "HIGH"
        color = "red"
    elif impact_abs >= 40:
        impact_level = "MEDIUM"
        color = "orange"
    elif impact_abs >= 15:
        impact_level = "LOW"
        color = "green"
    else:
        impact_level = "NONE"
        color = "gray"

    impact_score = max(0, min(100, impact_abs))

    return {
        "sentiment": sentiment,
        "direction": direction,
        "impact_level": impact_level,
        "impact_color": color,
        "impact_score": impact_score,
    }

def detect_market(ticker):
    t = ticker.upper().strip()
    if t.endswith(".WA") or t.endswith(".PL"):
        return "GPW"
    if t in ["SPY", "VOO", "IVV"]:
        return "S&P500"
    if t in ["QQQ", "NDX", "IXIC"]:
        return "NASDAQ"
    return "UNKNOWN"

def filter_items_for_tickers(items, tickers):
    out = []
    for it in items:
        text = (it.get("title", "") + " " + it.get("summary", "")).upper()
        for tk in tickers:
            if tk and tk.upper() in text:
                c = classify_impact(it.get("title", "") + " " + it.get("summary", ""))
                market = detect_market(tk)
                it2 = it.copy()
                it2["ticker"] = tk.upper()
                it2["market"] = market
                it2.update(c)
                out.append(it2)
                break
    return out

def run_news_scan(tickers):
    all_items = []
    for url in RSS_SOURCES + GPW_ESPI + MACRO_SOURCES:
        all_items.extend(parse_rss(url))
    for tk in tickers:
        all_items.extend(fetch_newsapi_for_ticker(tk))
        all_items.extend(fetch_twitter_for_ticker(tk))
    alerts = filter_items_for_tickers(all_items, tickers)
    alerts_sorted = sorted(alerts, key=lambda x: x.get("impact_score", 0), reverse=True)
    return alerts_sorted

# ============================================================
# 7. LICZENIE WYNIKÓW (NIETKNIĘTE)
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
# 8. TABS: ANALIZA / NEWS / MANUAL
# ============================================================

tab_analiza, tab_news, tab_manual = st.tabs(
    ["📊 Analiza techniczna", "📰 News impact", "📝 Manual impact"]
)

# ============================================================
# 8A. ANALIZA TECHNICZNA — PORTFEL, TOP10, RADAR, KAFELKI
# ============================================================

with tab_analiza:
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
                    opis = "\n".join(
                        f"{r['symbol']}: cena {r['price']:.2f}, score {r['score']}, RSI {r['rsi']:.1f}, MACD {r['macd']:.2f}"
                        for r in results
                    )
                    prompt = f"""
Analiza portfela:
{opis}

TOP10: {", ".join(top10_symbols)}

Zrób surową analizę techniczną portfela:
1. Ocena trendu i momentum.
2. Ryzyko i zmienność.
3. 3 najmocniejsze i 3 najsłabsze pozycje.
4. Werdykt ogólny (bez lania wody).
"""
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1
                    )
                    st.session_state["ai_portfolio"] = resp.choices[0].message.content

            if st.button("🤖 AI analiza TOP 10"):
                with st.spinner("AI analizuje TOP 10..."):
                    prompt = f"""
TOP10 (po score + MACD):
{chr(10).join(top10_symbols)}

Zrób:
1. Ranking siły trendu.
2. 3 najlepsze okazje do wejścia.
3. 3 ostrzeżenia (przegrzanie / słabość).
4. Krótki werdykt.
"""
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1
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
        st.markdown("### 🏆 TOP 10 (score + MACD)")
        st.dataframe(df_sorted.head(10), use_container_width=True)

    st.divider()

    st.subheader("🔥 RADAR WYBIĆ (wolumen relatywny)")

    top_vol = df_res.sort_values(by="vol", ascending=False).head(10)

    for i in range(0, len(top_vol), 5):
        cols = st.columns(5)
        for j, (_, row) in enumerate(top_vol.iloc[i:i+5].iterrows()):
            with cols[j]:
                r = next(x for x in results if x["symbol"] == row["symbol"])
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

    st.subheader("📊 Analiza główna – spółki")

    for r in results:
        with st.container():
            st.markdown("<div class='mega-card'>", unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns([1.8, 1.5, 1.3, 2.4])

            with c1:
                st.markdown(
                    f"<div class='neon-title' style='font-size:3rem;'>{r['symbol']}</div>",
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
                st.write(f"Wolumen relatywny: {r['vol']:.2f}x")

            with c2:
                st.write(f"Score trendu: **{r['score']}**")
                st.write(f"RSI: **{r['rsi']:.1f}**")
                st.write(f"ATR: **{r['atr']:.2f}**")
                st.write(f"Swing High: {r['swing_high']:.2f}")
                st.write(f"Swing Low: {r['swing_low']:.2f}")

            with c3:
                st.markdown(
                    f"**TP: <span class='tp-val'>{r['tp']:.2f}</span>**",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"**SL: <span class='sl-val'>{r['sl']:.2f}</span>**",
                    unsafe_allow_html=True
                )
                st.write(f"Pivot: {r['pivot']:.2f}")
                st.write(f"R1: {r['r1']:.2f}")
                st.write(f"S1: {r['s1']:.2f}")

            with c4:
                st.markdown(
                    f"<div class='signal-{r['signal']}'>{r['signal']}</div>",
                    unsafe_allow_html=True
                )

                if client and st.button(f"🤖 DIAGNOZA AI – {r['symbol']}", key=f"ai_{r['symbol']}"):
                    with st.spinner("AI analizuje tę spółkę..."):
                        prompt = f"""
Analiza spółki {r['symbol']}:
Cena: {r['price']:.2f}
Score trendu: {r['score']}
RSI: {r['rsi']:.1f}
MACD: {r['macd']:.2f}, sygnał: {r['macd_sig']:.2f}, histogram: {r['macd_hist']:.2f}
ATR: {r['atr']:.2f}
Swing High / Low: {r['swing_high']:.2f} / {r['swing_low']:.2f}
Pivot / R1 / S1: {r['pivot']:.2f} / {r['r1']:.2f} / {r['s1']:.2f}
TP / SL: {r['tp']:.2f} / {r['sl']:.2f}
Formacje świecowe: {r['candle_comment']}

Zrób surową analizę techniczną:
1. Ocena wejścia (krótko).
2. Ryzyko (zmienność, poziomy obrony).
3. Werdykt (KUP / TRZYMAJ / SPRZEDAJ) z jednym zdaniem uzasadnienia.
Bez definicji, bez lania wody.
"""
                        resp = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "Jesteś bezdusznym systemem analitycznym. Mówisz krótko, konkretnie, tylko o faktach i liczbach."
                                },
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.1
                        )
                        st.session_state["ai_single"][r["symbol"]] = resp.choices[0].message.content

                if r["symbol"] in st.session_state["ai_single"]:
                    st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
                    st.write(st.session_state["ai_single"][r["symbol"]])
                    st.markdown("</div>", unsafe_allow_html=True)

                with st.expander("📊 Szczegóły PRO"):
                    st.markdown("<div class='pro-box'>", unsafe_allow_html=True)
                    st.write(f"MA20: {r['ma20']:.2f}")
                    st.write(f"MA50: {r['ma50']:.2f}")
                    st.write(f"MA100: {r['ma100']:.2f}")
                    st.write(f"MA200: {r['ma200']:.2f}")
                    st.write(f"EMA200: {r['ema200']:.2f}")
                    st.write(f"MACD: {r['macd']:.2f}")
                    st.write(f"MACD sygnał: {r['macd_sig']:.2f}")
                    st.write(f"MACD histogram: {r['macd_hist']:.2f}")
                    st.write(f"Formacje świecowe: {r['candle_comment']}")
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# 8B. NEWS IMPACT ENGINE — AUTO + MANUAL SCAN
# ============================================================

with tab_news:
    st.subheader("📰 NEWS IMPACT ENGINE 3.0 — akcja / reakcja GPW / NASDAQ / S&P500")

    run_scan = False
    if news_manual_scan:
        run_scan = True
    if st.session_state["news_auto_mode"]:
        if st.session_state["news_last_run"] is None or (
            time.time() - st.session_state["news_last_run"] > 60
        ):
            run_scan = True

    if run_scan and tickers:
        st.session_state["news_last_run"] = time.time()
        with st.spinner("Skanuję źródła newsów..."):
            alerts = run_news_scan(tickers)
        if alerts:
            for a in alerts:
                color = a.get("impact_color", "gray")
                if color == "red":
                    bg = "#ff4b4b22"
                    badge = "🟥 HIGH"
                elif color == "orange":
                    bg = "#ffa50022"
                    badge = "🟧 MEDIUM"
                elif color == "green":
                    bg = "#00c85322"
                    badge = "🟩 LOW"
                else:
                    bg = "#cccccc22"
                    badge = "⬜ NONE"

                ticker = a.get("ticker", "")
                market = a.get("market", "UNKNOWN")
                title = a.get("title", "")
                link = a.get("link", "")
                published = a.get("published", "")
                source = a.get("source", "")
                sentiment = a.get("sentiment", "")
                direction = a.get("direction", "")
                impact_score = a.get("impact_score", 0)

                st.markdown(
                    f"""
<div style="background-color:{bg}; padding:10px; border-radius:8px; margin-bottom:8px;">
<b>{badge}</b> — <b>{ticker}</b> ({market}) — impact score: <b>{impact_score}</b><br>
<b>Źródło:</b> {source} | <b>Czas:</b> {published}<br>
<b>Tytuł:</b> {title}<br>
<b>Sentyment:</b> {sentiment} | <b>Kierunek:</b> {direction}<br>
<a href="{link}" target="_blank">🔗 Link</a>
</div>
""",
                    unsafe_allow_html=True,
                )
        else:
            st.info("Brak nowych istotnych newsów dla podanych tickerów.")
    else:
        st.write("Użyj przycisku w sidebarze lub włącz auto monitoring, aby rozpocząć skanowanie newsów.")

    st.markdown("---")
    st.markdown(
        """
**Legenda kolorów:**

- 🟥 **Czerwony** — HIGH IMPACT (silna akcja/reakcja)
- 🟧 **Pomarańczowy** — MEDIUM IMPACT
- 🟩 **Zielony** — LOW IMPACT
- ⬜ Szary — brak istotnego wpływu
        """
    )

# ============================================================
# 8C. MANUAL IMPACT ANALYZER
# ============================================================

with tab_manual:
    st.subheader("📝 Manual impact analyzer — wklej dowolną informację")

    manual_text = st.text_area(
        "Wklej treść komunikatu / newsa / plotki / opisu wydarzenia:",
        height=200,
    )

    if st.button("Analizuj wpływ na cenę"):
        if manual_text.strip():
            res = classify_impact(manual_text)
            color = res["impact_color"]
            if color == "red":
                badge = "🟥 HIGH"
                bg = "#ff4b4b22"
            elif color == "orange":
                badge = "🟧 MEDIUM"
                bg = "#ffa50022"
            elif color == "green":
                badge = "🟩 LOW"
                bg = "#00c85322"
            else:
                badge = "⬜ NONE"
                bg = "#cccccc22"

            st.markdown(
                f"""
<div style="background-color:{bg}; padding:10px; border-radius:8px;">
<b>{badge}</b> — impact score: <b>{res['impact_score']}</b><br>
<b>Sentyment:</b> {res['sentiment']} | <b>Kierunek:</b> {res['direction']}
</div>
""",
                unsafe_allow_html=True,
            )
        else:
            st.warning("Wklej najpierw jakiś tekst do analizy.")

