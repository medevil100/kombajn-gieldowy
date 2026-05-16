import streamlit as st
from openai import OpenAI
import matplotlib.pyplot as plt
import numpy as np

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="3× AI — Swing / Day / Long", layout="centered")

# ================== STYLE ==================
st.markdown("""
<style>
.box {
    padding: 15px;
    border-radius: 10px;
    font-size: 18px;
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
    font-size: 16px;
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
    font-size: 15px;
}
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Swing / Day / Long (3 modele GPT)")


# ================== AI #1 — SWING (gpt‑4o‑mini) ==================
def ai_swing(ticker, text):
    prompt = f"""
Jesteś agresywnym traderem swingowym.
Patrzysz na momentum, RSI, wolumen i wybicia.

Analiza SWING dla {ticker}:
{text}

Zadanie:
- 2–3 zdania
- dynamiczny styl
- zero kopiowania danych
"""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


# ================== AI #2 — DAY (gpt‑4o) ==================
def ai_day(ticker, text):
    prompt = f"""
Jesteś precyzyjnym daytraderem.
Analizujesz mikro‑ruchy, momentum 3, RSI7, wolumen intraday.

Analiza DAYTRADING dla {ticker}:
{text}

Zadanie:
- 2–3 zdania
- styl szybki, konkretny
- zero kopiowania danych
"""
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


# ================== AI #3 — LONG (o3‑mini) ==================
def ai_long(ticker, text):
    prompt = f"""
Jesteś spokojnym analitykiem długoterminowym.
Patrzysz na trend EMA50/100/200, stabilność i wolumen.

Analiza LONG-TERM dla {ticker}:
{text}

Zadanie:
- 2–3 zdania
- styl spokojny, analityczny
- zero kopiowania danych
"""
    r = client.chat.completions.create(
        model="o3-mini",
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


# ================== MODUŁY ANALIZY TEKSTOWEJ ==================

def detect_patterns(text: str):
    text_low = text.lower()
    patterns = []

    # Trendy
    if "wzrost" in text_low or "rosną" in text_low or "rosnie" in text_low:
        patterns.append("Trend wzrostowy")
    if "spad" in text_low:
        patterns.append("Trend spadkowy")
    if "boczny" in text_low or "konsolidacja" in text_low or "range" in text_low:
        patterns.append("Trend boczny / konsolidacja")

    # Momentum
    if "momentum dodatnie" in text_low:
        patterns.append("Momentum dodatnie")
    if "momentum ujemne" in text_low:
        patterns.append("Momentum ujemne")

    # EMA / MA
    if "ema20 > ema50" in text_low:
        patterns.append("Wybicie krótkoterminowe (EMA20 ponad EMA50)")
    if "ema50 > ema200" in text_low:
        patterns.append("Długoterminowy trend wzrostowy (EMA50 ponad EMA200)")
    if "ema50 < ema200" in text_low:
        patterns.append("Długoterminowy trend spadkowy (EMA50 poniżej EMA200)")

    # RSI
    if "rsi" in text_low:
        if "powyżej 70" in text_low or "powyzej 70" in text_low:
            patterns.append("RSI w strefie wykupienia")
        if "poniżej 30" in text_low or "ponizej 30" in text_low:
            patterns.append("RSI w strefie wyprzedania")
        if "powyżej 50" in text_low or "powyzej 50" in text_low:
            patterns.append("RSI wspiera trend wzrostowy")

    # Formacje świecowe
    if "doji" in text_low:
        patterns.append("Formacja Doji — sygnał niezdecydowania")
    if "młot" in text_low or "mlot" in text_low or "hammer" in text_low:
        patterns.append("Formacja Hammer — potencjalne odbicie")
    if "objęcie hossy" in text_low or "objecie hossy" in text_low:
        patterns.append("Bullish Engulfing — silny sygnał wzrostowy")
    if "objęcie bessy" in text_low or "objecie bessy" in text_low:
        patterns.append("Bearish Engulfing — sygnał spadkowy")

    return patterns


def analyze_sma(text: str):
    t = text.lower()
    res = []

    if "sma20" in t or "ma20" in t:
        res.append("SMA20: krótkoterminowy kierunek rynku.")
    if "sma50" in t or "ma50" in t:
        res.append("SMA50: średnioterminowy trend kontroluje ruch.")
    if "sma100" in t or "ma100" in t:
        res.append("SMA100: filtruje szum, pokazuje głębszy trend.")
    if "sma200" in t or "ma200" in t:
        res.append("SMA200: kluczowa granica byków i niedźwiedzi.")

    if "sma50 > sma200" in t or "ma50 > ma200" in t:
        res.append("Golden cross (SMA50 ponad SMA200) — silny sygnał byczy.")
    if "sma50 < sma200" in t or "ma50 < ma200" in t:
        res.append("Death cross (SMA50 poniżej SMA200) — przewaga niedźwiedzi.")

    return res


def analyze_sl_tp(text: str):
    t = text.lower()
    res = []

    if "atr" in t:
        res.append("Możliwy SL: ~1.5× ATR poniżej kluczowego swingu.")
        res.append("Możliwy TP: 2–3× ATR w kierunku dominującego trendu.")
    if "swing low" in t or "lokalne minimum" in t:
        res.append("Logiczny SL pod ostatnim lokalnym minimum (swing low).")
    if "opór" in t or "opor" in t:
        res.append("TP można rozważyć przy najbliższej strefie oporu.")
    if not res:
        res.append("Brak jednoznacznych danych — SL/TP do doprecyzowania względem zmienności i ostatnich swingów.")

    return res


def analyze_fibo(text: str):
    t = text.lower()
    res = []

    if "0.382" in t:
        res.append("Reakcja na 0.382 — płytka korekta, trend wciąż silny.")
    if "0.5" in t:
        res.append("Poziom 0.5 — klasyczna, symetryczna korekta.")
    if "0.618" in t:
        res.append("Złoty poziom 0.618 — kluczowa strefa decyzyjna.")
    if "0.786" in t:
        res.append("Głęboka korekta 0.786 — często ostatnia linia obrony trendu.")

    return res


def analyze_bollinger(text: str):
    t = text.lower()
    res = []

    if "wybicie górnej" in t or "wybicie gornej" in t:
        res.append("Wybicie górnej wstęgi — silne momentum wzrostowe.")
    if "odbicie od dolnej" in t:
        res.append("Odbicie od dolnej wstęgi — potencjalne odbicie w górę.")
    if "squeeze" in t or "ścisk" in t or "scisk" in t:
        res.append("Squeeze Bollingera — możliwy silny ruch po wybiciu.")
    if not res:
        res.append("Brak wyraźnych sygnałów z wstęg Bollingera w danych tekstowych.")

    return res


def detect_trend(text: str):
    t = text.lower()
    if "trend: wzrostowy" in t or "trend wzrostowy" in t or "byczy" in t:
        return "bull"
    if "trend: spadkowy" in t or "trend spadkowy" in t or "niedźwiedzi" in t or "niedzwiedzi" in t:
        return "bear"
    if "boczny" in t or "konsolidacja" in t or "range" in t:
        return "side"
    # fallback na podstawie słów
    if "wzrost" in t:
        return "bull"
    if "spad" in t:
        return "bear"
    return "side"


def trend_label_and_color(trend_code: str):
    if trend_code == "bull":
        return "Trend wzrostowy (🐂 byczy)", "trend-bull", "green"
    if trend_code == "bear":
        return "Trend spadkowy (🐻 niedźwiedzi)", "trend-bear", "red"
    return "Trend boczny / konsolidacja (➖)", "trend-side", "yellow"


def plot_trend_chart(trend_code: str):
    # prosta syntetyczna seria tylko do wizualizacji
    x = np.arange(50)
    if trend_code == "bull":
        y = np.linspace(1, 1.8, 50) + np.random.normal(0, 0.02, 50)
        color = "lime"
    elif trend_code == "bear":
        y = np.linspace(1, 0.4, 50) + np.random.normal(0, 0.02, 50)
        color = "red"
    else:
        y = 1 + 0.05 * np.sin(np.linspace(0, 6, 50)) + np.random.normal(0, 0.01, 50)
        color = "gold"

    # Bollinger na syntetycznych danych
    ma = np.convolve(y, np.ones(5)/5, mode="same")
    std = np.std(y)
    upper = ma + 2 * std
    lower = ma - 2 * std

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(x, y, color=color, label="Cena (syntetyczna)")
    ax.plot(x, ma, color="white", linewidth=1.2, label="Środkowa banda (MA)")
    ax.plot(x, upper, color="#60a5fa", linestyle="--", linewidth=0.8, label="Górna banda")
    ax.plot(x, lower, color="#60a5fa", linestyle="--", linewidth=0.8, label="Dolna banda")
    ax.fill_between(x, lower, upper, color="#4c1d95", alpha=0.15)

    ax.set_facecolor("#020617")
    fig.patch.set_facecolor("#020617")
    ax.tick_params(colors="#9ca3af")
    for spine in ax.spines.values():
        spine.set_color("#4b5563")
    ax.legend(facecolor="#020617", edgecolor="#4b5563", labelcolor="#e5e7eb", fontsize=8)
    ax.set_title("Syntetyczny wykres trendu + Bollinger Bands", color="#e5e7eb", fontsize=10)

    st.pyplot(fig)


# ================== UI ==================

ticker = st.text_input("Ticker:", "AAPL")

dane = st.text_area(
    "Dane techniczne (czytelne):",
    """Close: 190.20
RSI14: 55
Volume ratio: 1.2
Trend: wzrostowy
Sygnały:
- EMA20 > EMA50
- RSI powyżej 50
- Momentum dodatnie"""
)

# --- Analiza tekstowa przed wyborem AI ---

patterns = detect_patterns(dane)
sma_info = analyze_sma(dane)
sl_tp_info = analyze_sl_tp(dane)
fibo_info = analyze_fibo(dane)
bb_info = analyze_bollinger(dane)
trend_code = detect_trend(dane)
trend_label, trend_css, trend_color = trend_label_and_color(trend_code)

st.subheader("🔍 Wykryte elementy techniczne")

# Trend (kolorowe ramki + niedźwiedź/byk)
st.markdown(
    f"""
    <div class="trend-box {trend_css}">
        <b>Trend główny:</b> {trend_label}
    </div>
    """,
    unsafe_allow_html=True,
)

if patterns:
    st.markdown("**Formacje / sygnały:**")
    for p in patterns:
        st.markdown(f"- {p}")

if sma_info:
    st.markdown("**SMA / średnie kroczące:**")
    for s in sma_info:
        st.markdown(f"- {s}")

if fibo_info:
    st.markdown("**Poziomy Fibonacciego:**")
    for f in fibo_info:
        st.markdown(f"- {f}")

if bb_info:
    st.markdown("**Wstęgi Bollingera:**")
    for b in bb_info:
        st.markdown(f"- {b}")

if sl_tp_info:
    st.markdown("**Propozycje SL / TP (logika tekstowa):**")
    for r in sl_tp_info:
        st.markdown(f"- {r}")

with st.expander("📊 Podgląd syntetycznego wykresu trendu + Bollinger"):
    plot_trend_chart(trend_code)

st.markdown(
    """
    <div class="info-box">
        Powyższa analiza jest oparta na danych tekstowych, bez realnych notowań.
        Służy jako szybki, wizualny i logiczny kontekst przed uruchomieniem jednego z trzech modeli GPT.
    </div>
    """,
    unsafe_allow_html=True,
)

ai_choice = st.selectbox(
    "Wybierz AI:",
    [
        "AI Swing — gpt‑4o‑mini",
        "AI Day — gpt‑4o",
        "AI Long — o3‑mini"
    ]
)

if st.button("Analizuj"):
    if "Swing" in ai_choice:
        wynik = ai_swing(ticker, dane)
        css = "swing"
    elif "Day" in ai_choice:
        wynik = ai_day(ticker, dane)
        css = "day"
    else:
        wynik = ai_long(ticker, dane)
        css = "long"

    st.markdown(f"""
    <div class="box {css}">
        <b>Wynik AI:</b><br>{wynik}
    </div>
    """, unsafe_allow_html=True)
