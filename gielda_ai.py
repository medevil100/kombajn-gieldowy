import streamlit as st
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("3× AI — Swing / Day / Long (czytelne dane + różne modele GPT)")

# ================== 3 MODELE AI ==================

def ai_swing(ticker, text):
    prompt = f"""
Analiza SWING dla {ticker}.
Dane techniczne:
{text}

Zadanie:
- Zrób analizę swing (kilka dni–tygodni)
- 2–3 zdania
- Bez kopiowania danych
"""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


def ai_day(ticker, text):
    prompt = f"""
Analiza DAYTRADING dla {ticker}.
Dane techniczne:
{text}

Zadanie:
- Zrób analizę daytrading (krótkie ruchy)
- 2–3 zdania
- Bez kopiowania danych
"""
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


def ai_long(ticker, text):
    prompt = f"""
Analiza LONG-TERM dla {ticker}.
Dane techniczne:
{text}

Zadanie:
- Zrób analizę długoterminową
- 2–3 zdania
- Bez kopiowania danych
"""
    r = client.chat.completions.create(
        model="o3-mini",
        reasoning_effort="high",
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
        "Swing (gpt‑4o‑mini)",
        "Day (gpt‑4o)",
        "Long (o3‑mini)"
    ]
)

if st.button("Analizuj"):
    if "Swing" in ai_choice:
        wynik = ai_swing(ticker, dane)
    elif "Day" in ai_choice:
        wynik = ai_day(ticker, dane)
    else:
        wynik = ai_long(ticker, dane)

    st.subheader("Wynik AI:")
    st.write(wynik)
