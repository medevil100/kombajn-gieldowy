import streamlit as st
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("3× AI — Swing / Day / Long")

# ================== 3 MODELE AI ==================

def ai_swing(ticker, data):
    prompt = f"Swing analiza {ticker}. Dane: {data}. 2 zdania, bez kopiowania danych."
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()

def ai_day(ticker, data):
    prompt = f"Daytrading analiza {ticker}. Dane: {data}. 2 zdania, bez kopiowania danych."
    r = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()

def ai_long(ticker, data):
    prompt = f"Long-term analiza {ticker}. Dane: {data}. 2 zdania, bez kopiowania danych."
    r = client.chat.completions.create(
        model="o3-mini",
        reasoning_effort="high",
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()

# ================== UI ==================

ticker = st.text_input("Ticker:", "AAPL")
data = st.text_area("Dane techniczne:", "{'close': 190, 'rsi': 55, 'vol': 1.2}")

ai_choice = st.selectbox(
    "Wybierz AI:",
    ["Swing (gpt‑4o‑mini)", "Day (gpt‑4o)", "Long (o3‑mini)"]
)

if st.button("Analizuj"):
    if "Swing" in ai_choice:
        out = ai_swing(ticker, data)
    elif "Day" in ai_choice:
        out = ai_day(ticker, data)
    else:
        out = ai_long(ticker, data)

    st.subheader("Wynik AI:")
    st.write(out)
