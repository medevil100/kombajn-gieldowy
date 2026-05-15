import streamlit as st
from openai import OpenAI

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
