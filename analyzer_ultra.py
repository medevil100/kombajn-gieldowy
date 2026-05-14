import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta 
import plotly.express as px
from datetime import datetime, timedelta
import json
import requests

# ---------------------------------------------------------
# KONFIGURACJA APLIKACJI
# ---------------------------------------------------------
st.set_page_config(
    page_title="GPW Momentum Screener",
    layout="wide",
    menu_items={
        "About": "GPW Momentum Screener – day & swing trading (akcje, nie CFD)"
    }
)

st.title("📈 GPW Momentum Screener – akcje (day + swing)")

# ---------------------------------------------------------
# MOCK XTB CLIENT – DO TESTÓW (PÓŹNIEJ PODMIENISZ NA REALNE API)
# ---------------------------------------------------------
class XTBClientMock:
    def __init__(self):
        self.session_id = "FAKE"

    def login(self, login: str, password: str, mode: str = "demo"):
        # tutaj w realnym kliencie robisz logowanie do XTB
        pass

    def get_gpw_symbols(self):
        # TODO: podmień na realne pobieranie symboli z XTB (tylko akcje GPW/NewConnect)
        return ["CDPROJEKT", "PKOBP", "KGHM", "PEKAO", "ALLEGRO"]

    def get_ohlc(self, symbol: str, period: str = "D1", candles: int = 200) -> pd.DataFrame:
        # TODO: podmień na realne /chartLastRequest z XTB
        end = datetime.now()
        idx = [end - timedelta(days=i) for i in range(candles)][::-1]
        base = {
            "CDPROJEKT": 120,
            "PKOBP": 40,
            "KGHM": 150,
            "PEKAO": 100,
            "ALLEGRO": 30,
        }.get(symbol, 50)
        prices = np.linspace(base * 0.9, base * 1.1, candles) + np.random.randn(candles) * (base * 0.01)
        df = pd.DataFrame({
            "time": idx,
            "open": prices - np.random.rand(candles) * (base * 0.01),
            "high": prices + np.random.rand(candles) * (base * 0.01),
            "low": prices - np.random.rand(candles) * (base * 0.02),
            "close": prices,
            "volume": np.random.randint(1000, 10000, size=candles)
        })
        return df

# inicjalizacja klienta w session_state
if "xtb" not in st.session_state:
    st.session_state["xtb"] = XTBClientMock()

xtb = st.session_state["xtb"]

# ---------------------------------------------------------
# PANEL LOGOWANIA (NA RAZIE TYLKO UI, MOCK NIC Z TYM NIE ROBI)
# ---------------------------------------------------------
st.sidebar.header("🔐 Logowanie do XTB (mock)")

login = st.sidebar.text_input("Login XTB", "")
password = st.sidebar.text_input("Hasło XTB", "", type="password")
mode = st.sidebar.selectbox("Tryb:", ["Demo", "Real"])

if st.sidebar.button("Połącz"):
    xtb.login(login, password, mode.lower())
    st.sidebar.success("Połączono (mock) – dane są generowane lokalnie.")

# ---------------------------------------------------------
# WSKAŹNIKI
# ---------------------------------------------------------
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=14)
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    df["mom5"] = df["close"].pct_change(5)
    df["mom20"] = df["close"].pct_change(20)
    df["mom60"] = df["close"].pct_change(60)
    return df

# ---------------------------------------------------------
# SCORING – PROFIL SWING / DAY
# ---------------------------------------------------------
def compute_score_row_swing(row: pd.Series) -> float:
    score = 0.0

    if pd.notna(row.get("mom20")):
        score += float(row["mom20"]) * 0.6
    if pd.notna(row.get("mom60")):
        score += float(row["mom60"]) * 0.4

    if pd.notna(row.get("rsi")):
        rsi = float(row["rsi"])
        score += (1 - abs(rsi - 50) / 50) * 0.5

    price = float(row["price"])
    bonus = 0.0
    if pd.notna(row.get("sma20")) and price > float(row["sma20"]):
        bonus += 0.3
    if pd.notna(row.get("sma50")) and price > float(row["sma50"]):
        bonus += 0.2
    score += bonus

    return float(score)

def compute_score_row_day(row: pd.Series) -> float:
    score = 0.0

    if pd.notna(row.get("mom5")):
        score += float(row["mom5"]) * 0.5
    if pd.notna(row.get("mom20")):
        score += float(row["mom20"]) * 0.3

    if pd.notna(row.get("rsi")):
        rsi = float(row["rsi"])
        score += (1 - abs(rsi - 50) / 50) * 0.7

    price = float(row["price"])
    bonus = 0.0
    if pd.notna(row.get("sma20")) and price > float(row["sma20"]):
        bonus += 0.2
    score += bonus

    return float(score)

# ---------------------------------------------------------
# AI – LLM KOMENTARZ (OPENAI PRZEZ st.secrets)
# ---------------------------------------------------------
def generate_ai_comment(row: pd.Series, profile: str) -> str:
    """
    Tworzy komentarz LLM na podstawie danych wskaźników.
    Jeśli brak klucza → fallback rule-based.
    """

    # Fallback jeśli brak klucza
    if "OPENAI_API_KEY" not in st.secrets:
        return (
            f"(AI OFF) {row['symbol']}: "
            f"RSI {row['rsi']:.1f}, "
            f"mom20 {row['mom20']:.2%}, "
            f"cena {row['price']:.2f} vs SMA20 {row['sma20']:.2f}"
        )

    api_key = st.secrets["OPENAI_API_KEY"]
    model = st.secrets.get("OPENAI_MODEL", "gpt-4.1-mini")

    prompt = f"""
Jesteś analitykiem giełdowym. Oceniasz spółkę {row['symbol']}.

Dane:
- Cena: {row['price']:.2f}
- RSI(14): {row['rsi']:.1f}
- Momentum 5d: {row['mom5']:.2%}
- Momentum 20d: {row['mom20']:.2%}
- Momentum 60d: {row['mom60']:.2%}
- SMA20: {row['sma20']:.2f}
- SMA50: {row['sma50']:.2f}
- Profil: {profile}

Zadanie:
Napisz krótki komentarz (1–2 zdania), prosty, konkretny, bez lania wody.
Uwzględnij momentum, RSI i pozycję względem SMA.
"""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            data=json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": "Jesteś ekspertem giełdowym, piszesz krótko i konkretnie."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            })
        )

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"(AI ERROR) {str(e)}"

# ---------------------------------------------------------
# CACHE – POBIERANIE DANYCH
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def get_symbols():
    return xtb.get_gpw_symbols()

@st.cache_data(ttl=60)
def get_ohlc_with_indicators(symbol: str) -> pd.DataFrame:
    df = xtb.get_ohlc(symbol, period="D1", candles=200)
    df = compute_indicators(df)
    return df

@st.cache_data(ttl=60)
def get_rank(profile: str, limit: int) -> pd.DataFrame:
    symbols = get_symbols()
    rows = []

    for sym in symbols:
        df = get_ohlc_with_indicators(sym)
        last = df.iloc[-1]

        row = {
            "symbol": sym,
            "price": float(last["close"]),
            "rsi": float(last["rsi"]),
            "mom5": float(last["mom5"]),
            "mom20": float(last["mom20"]),
            "mom60": float(last["mom60"]),
            "sma20": float(last["sma20"]),
            "sma50": float(last["sma50"]),
        }

        if profile == "Swing":
            row["score"] = compute_score_row_swing(pd.Series(row))
        else:
            row["score"] = compute_score_row_day(pd.Series(row))

        row["comment"] = generate_ai_comment(pd.Series(row), profile)
        rows.append(row)

    df_rank = pd.DataFrame(rows)
    df_rank = df_rank.sort_values("score", ascending=False)
    return df_rank.head(limit)

# ---------------------------------------------------------
# UI – MENU
# ---------------------------------------------------------
menu = st.sidebar.radio(
    "Menu:",
    ["Ranking", "Szczegóły spółki", "Ustawienia scoringu"],
    index=0
)

profile = st.sidebar.selectbox(
    "Profil tradingowy:",
    ["Swing", "Day"],
    index=0
)

# ---------------------------------------------------------
# WIDOK: RANKING
# ---------------------------------------------------------
if menu == "Ranking":
    st.subheader(f"Ranking spółek – profil: {profile}")

    limit = st.slider("Ilość spółek w rankingu:", 5, 50, 20)

    df_rank = get_rank(profile, limit)

    st.dataframe(
        df_rank[["symbol", "price", "score", "rsi", "mom5", "mom20", "mom60"]],
        use_container_width=True
    )

    st.markdown("### Komentarze AI")
    for _, row in df_rank.iterrows():
        st.markdown(f"**{row['symbol']}** — {row['comment']}")

# ---------------------------------------------------------
# WIDOK: SZCZEGÓŁY SPÓŁKI
# ---------------------------------------------------------
if menu == "Szczegóły spółki":
    st.subheader("Szczegółowa analiza spółki")

    symbols = get_symbols()
    symbol = st.selectbox("Wybierz spółkę:", symbols)

    if symbol:
        df = get_ohlc_with_indicators(symbol)
        df_plot = df.tail(120).copy()
        df_plot["time"] = df_plot["time"].astype(str)

        col1, col2 = st.columns(2)

        with col1:
            fig_price = px.line(df_plot, x="time", y="close", title=f"Cena – {symbol}")
            fig_price.update_layout(height=350)
            st.plotly_chart(fig_price, use_container_width=True)

        with col2:
            fig_rsi = px.line(df_plot, x="time", y="rsi", title="RSI(14)")
            fig_rsi.update_layout(height=350)
            st.plotly_chart(fig_rsi, use_container_width=True)

        st.markdown("### Ostatnie dane")
        st.dataframe(df.tail(10), use_container_width=True)

# ---------------------------------------------------------
# WIDOK: USTAWIENIA SCORINGU
# ---------------------------------------------------------
if menu == "Ustawienia scoringu":
    st.subheader("Ustawienia scoringu (opis profili)")

    st.markdown("""
    ### 🔧 Profil Swing
    - Momentum 20d: 60%
    - Momentum 60d: 40%
    - RSI (preferowane okolice 50): +0.5
    - Cena > SMA20: +0.3
    - Cena > SMA50: +0.2

    ### ⚡ Profil Day
    - Momentum 5d: 50%
    - Momentum 20d: 30%
    - RSI (preferowane 45–55): +0.7
    - Cena > SMA20: +0.2

    AI‑komentarz korzysta z tych samych danych, ale opisuje je w języku naturalnym.
    """)

    st.info("Klucz LLM dodajesz w .streamlit/secrets.toml jako OPENAI_API_KEY i OPENAI_MODEL.")
