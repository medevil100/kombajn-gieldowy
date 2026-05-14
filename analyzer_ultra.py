import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import plotly.express as px
from datetime import datetime, timedelta
import json
import time
import requests
from websocket import create_connection

# =========================================================
# KONFIGURACJA APLIKACJI
# =========================================================
st.set_page_config(page_title="Kombajn Giełdowy XTB REAL", layout="wide")
st.set_option("client.showErrorDetails", False)

st.title("📈 Kombajn Giełdowy – XTB REAL + GPT‑4.1 AI alerty")

# =========================================================
# KLIENT XTB (xAPI WebSocket – REAL/DEMO)
# =========================================================
class XTBClient:
    def __init__(self, user_id: str, password: str, mode: str = "real"):
        self.user_id = user_id
        self.password = password
        self.mode = mode  # "real" lub "demo"
        self.ws = None
        self.stream_ws = None
        self.session_id = None

    def _get_url(self):
        if self.mode == "demo":
            return "wss://ws.xtb.com/demo"
        return "wss://ws.xtb.com/real"

    def connect(self):
        if self.ws is None:
            self.ws = create_connection(self._get_url())

    def send(self, command: str, arguments: dict | None = None):
        if self.ws is None:
            self.connect()
        msg = {"command": command}
        if arguments is not None:
            msg["arguments"] = arguments
        self.ws.send(json.dumps(msg))
        raw = self.ws.recv()
        return json.loads(raw)

    def login(self):
        resp = self.send("login", {
            "userId": self.user_id,
            "password": self.password
        })
        if not resp.get("status"):
            raise RuntimeError(f"XTB login failed: {resp}")
        self.session_id = resp.get("streamSessionId")

    def get_all_symbols(self):
        resp = self.send("getAllSymbols")
        if not resp.get("status"):
            raise RuntimeError("getAllSymbols failed")
        return resp["returnData"]

    def get_gpw_stocks(self, limit: int | None = None):
        data = self.get_all_symbols()
        stocks = [
            s for s in data
            if s.get("categoryName") == "STOCK"
        ]
        if limit:
            stocks = stocks[:limit]
        return stocks

    def get_ohlc(self, symbol: str, period: int = 1440, candles: int = 200) -> pd.DataFrame:
        """
        period (minuty): 1, 5, 15, 30, 60, 240, 1440 (D1)
        """
        end = int(time.time())
        # przybliżony start – candles * period * 60
        start = end - candles * period * 60

        resp = self.send("getChartRangeRequest", {
            "info": {
                "period": period,
                "start": start,
                "end": end,
                "symbol": symbol
            }
        })
        if not resp.get("status"):
            raise RuntimeError(f"getChartRangeRequest failed for {symbol}")

        data = resp["returnData"]["rateInfos"]
        if not data:
            raise RuntimeError(f"No OHLC data for {symbol}")

        # XTB zwraca czas jako offset od startTime
        start_time = resp["returnData"]["info"]["start"]
        rows = []
        for r in data:
            t = (start_time + r["ctm"]) / 1000.0
            rows.append({
                "time": datetime.utcfromtimestamp(t),
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r.get("vol", 0)
            })
        df = pd.DataFrame(rows)
        return df.tail(candles)

# =========================================================
# AI – GPT‑4.1: KOMENTARZE I ALERTY
# =========================================================
def call_gpt(system_prompt: str, user_prompt: str) -> str:
    if "OPENAI_API_KEY" not in st.secrets:
        return "(AI OFF – brak OPENAI_API_KEY w secrets.toml)"

    api_key = st.secrets["OPENAI_API_KEY"]
    model = st.secrets.get("OPENAI_MODEL", "gpt-4.1")

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3
            }),
            timeout=20
        )
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(AI ERROR: {e})"

def generate_ai_comment(row: pd.Series, profile: str) -> str:
    user_prompt = f"""
Spółka: {row['symbol']}
Profil: {profile}

Dane:
Cena: {row['price']:.2f}
RSI(14): {row['rsi']:.1f}
Momentum 5d: {row['mom5']:.2%}
Momentum 20d: {row['mom20']:.2%}
Momentum 60d: {row['mom60']:.2%}
SMA20: {row['sma20']:.2f}
SMA50: {row['sma50']:.2f}
Score: {row['score']:.4f}

Napisz 1–2 zdania po polsku:
- konkretnie,
- bez lania wody,
- uwzględnij momentum, RSI i pozycję względem SMA.
"""
    return call_gpt(
        "Jesteś analitykiem giełdowym, piszesz krótko, konkretnie, bez marketingu.",
        user_prompt
    )

def generate_ai_alerts(rows: list[dict]) -> str:
    """
    rows: lista słowników z danymi spółek (top N)
    """
    text = "Masz wygenerować krótkie alerty tradingowe dla poniższych spółek.\n\n"
    for r in rows:
        text += (
            f"- {r['symbol']}: cena {r['price']:.2f}, RSI {r['rsi']:.1f}, "
            f"mom20 {r['mom20']:.2%}, score {r['score']:.4f}\n"
        )
    text += "\nZwróć 3–6 najciekawszych alertów (po polsku, krótko)."

    return call_gpt(
        "Jesteś systemem alertów tradingowych. Wybierasz tylko najciekawsze setupy.",
        text
    )

# =========================================================
# WSKAŹNIKI I SCORING
# =========================================================
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=14)
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    df["mom5"] = df["close"].pct_change(5)
    df["mom20"] = df["close"].pct_change(20)
    df["mom60"] = df["close"].pct_change(60)
    return df

def score_swing(row: pd.Series) -> float:
    score = 0.0
    if pd.notna(row["mom20"]):
        score += float(row["mom20"]) * 0.6
    if pd.notna(row["mom60"]):
        score += float(row["mom60"]) * 0.4
    if pd.notna(row["rsi"]):
        score += (1 - abs(float(row["rsi"]) - 50) / 50) * 0.5
    if row["price"] > row["sma20"]:
        score += 0.3
    if row["price"] > row["sma50"]:
        score += 0.2
    return score

def score_day(row: pd.Series) -> float:
    score = 0.0
    if pd.notna(row["mom5"]):
        score += float(row["mom5"]) * 0.5
    if pd.notna(row["mom20"]):
        score += float(row["mom20"]) * 0.3
    if pd.notna(row["rsi"]):
        score += (1 - abs(float(row["rsi"]) - 50) / 50) * 0.7
    if row["price"] > row["sma20"]:
        score += 0.2
    return score

# =========================================================
# CACHE – POD CLOUD
# =========================================================
@st.cache_data(ttl=300)
def cached_symbols(user_id: str, mode: str) -> pd.DataFrame:
    client = get_client(user_id, mode)
    data = client.get_gpw_stocks()
    return pd.DataFrame(data)

@st.cache_data(ttl=300)
def cached_ohlc(user_id: str, mode: str, symbol: str, period: int, candles: int) -> pd.DataFrame:
    client = get_client(user_id, mode)
    df = client.get_ohlc(symbol, period=period, candles=candles)
    return compute_indicators(df)

# =========================================================
# KLIENT XTB W SESSION_STATE
# =========================================================
def get_client(user_id: str, mode: str) -> XTBClient:
    key = f"xtb_{mode}_{user_id}"
    if key not in st.session_state:
        # hasło nie jest trzymane w session_state – logowanie niżej
        raise RuntimeError("Brak zalogowanego klienta XTB w session_state")
    return st.session_state[key]

def set_client(user_id: str, password: str, mode: str):
    key = f"xtb_{mode}_{user_id}"
    client = XTBClient(user_id=user_id, password=password, mode=mode)
    client.login()
    st.session_state[key] = client

# =========================================================
# SIDEBAR – LOGOWANIE + USTAWIENIA
# =========================================================
st.sidebar.header("🔐 XTB REAL / DEMO")

xtb_login = st.sidebar.text_input("Login XTB", value="", type="default")
xtb_password = st.sidebar.text_input("Hasło XTB", value="", type="password")
xtb_mode = st.sidebar.selectbox("Tryb XTB", ["real", "demo"], index=0)

login_btn = st.sidebar.button("Połącz z XTB")

if login_btn:
    try:
        set_client(xtb_login, xtb_password, xtb_mode)
        st.sidebar.success("Zalogowano do XTB.")
    except Exception as e:
        st.sidebar.error(f"Błąd logowania: {e}")

menu = st.sidebar.radio("Menu", ["Ranking", "Szczegóły", "AI alerty"])
profile = st.sidebar.selectbox("Profil tradingowy", ["Swing", "Day"], index=0)

# =========================================================
# GUARD – WYMAGANE LOGOWANIE
# =========================================================
if xtb_login == "" or f"xtb_{xtb_mode}_{xtb_login}" not in st.session_state:
    st.warning("Zaloguj się do XTB (login + hasło) po lewej, potem wybierz menu.")
    st.stop()

# =========================================================
# RANKING
# =========================================================
if menu == "Ranking":
    st.subheader(f"Ranking spółek – XTB {xtb_mode.upper()} – profil {profile}")

    limit = st.slider("Ilość spółek w rankingu", 10, 150, 50, step=10)
    period = 1440  # D1
    candles = 200

    if st.button("🔄 Odśwież ranking"):
        st.cache_data.clear()

    symbols_df = cached_symbols(xtb_login, xtb_mode)
    # bierzemy tylko pierwsze N, żeby nie zabić Cloud
    symbols_df = symbols_df.head(limit)

    rows = []
    for _, s in symbols_df.iterrows():
        symbol = s["symbol"]
        try:
            df = cached_ohlc(xtb_login, xtb_mode, symbol, period, candles)
            last = df.iloc[-1]
            row = {
                "symbol": symbol,
                "price": float(last["close"]),
                "rsi": float(last["rsi"]),
                "mom5": float(last["mom5"]),
                "mom20": float(last["mom20"]),
                "mom60": float(last["mom60"]),
                "sma20": float(last["sma20"]),
                "sma50": float(last["sma50"]),
            }
            if profile == "Swing":
                row["score"] = score_swing(pd.Series(row))
            else:
                row["score"] = score_day(pd.Series(row))
            rows.append(row)
        except Exception:
            continue

    if not rows:
        st.error("Brak danych OHLC z XTB dla wybranych spółek.")
        st.stop()

    rank_df = pd.DataFrame(rows).sort_values("score", ascending=False)
    st.dataframe(rank_df, use_container_width=True)

    st.markdown("### AI‑komentarze (GPT‑4.1) – top 10")
    top10 = rank_df.head(10)
    for _, r in top10.iterrows():
        comment = generate_ai_comment(r, profile)
        st.markdown(f"**{r['symbol']}** — {comment}")

# =========================================================
# SZCZEGÓŁY SPÓŁKI
# =========================================================
if menu == "Szczegóły":
    st.subheader("Szczegóły spółki – XTB")

    symbols_df = cached_symbols(xtb_login, xtb_mode)
    symbol = st.selectbox("Wybierz spółkę", symbols_df["symbol"].tolist())

    period = st.selectbox("Interwał", ["D1", "H4", "H1"], index=0)
    period_map = {"D1": 1440, "H4": 240, "H1": 60}
    candles = st.slider("Liczba świec", 50, 400, 200, step=50)

    if st.button("🔄 Odśwież dane spółki"):
        st.cache_data.clear()

    df = cached_ohlc(xtb_login, xtb_mode, symbol, period_map[period], candles)
    df_plot = df.copy()
    df_plot["time"] = df_plot["time"].astype(str)

    col1, col2 = st.columns(2)

    with col1:
        fig_price = px.line(df_plot, x="time", y="close", title=f"Cena – {symbol}")
        st.plotly_chart(fig_price, use_container_width=True)

    with col2:
        fig_rsi = px.line(df_plot, x="time", y="rsi", title="RSI(14)")
        st.plotly_chart(fig_rsi, use_container_width=True)

    st.markdown("### Ostatnie świece")
    st.dataframe(df.tail(20), use_container_width=True)

# =========================================================
# AI ALERTY
# =========================================================
if menu == "AI alerty":
    st.subheader("AI alerty – GPT‑4.1 na podstawie rankingu")

    limit = st.slider("Ilość spółek do analizy alertów", 10, 150, 50, step=10)
    period = 1440
    candles = 200

    if st.button("🔄 Odśwież dane do alertów"):
        st.cache_data.clear()

    symbols_df = cached_symbols(xtb_login, xtb_mode)
    symbols_df = symbols_df.head(limit)

    rows = []
    for _, s in symbols_df.iterrows():
        symbol = s["symbol"]
        try:
            df = cached_ohlc(xtb_login, xtb_mode, symbol, period, candles)
            last = df.iloc[-1]
            row = {
                "symbol": symbol,
                "price": float(last["close"]),
                "rsi": float(last["rsi"]),
                "mom5": float(last["mom5"]),
                "mom20": float(last["mom20"]),
                "mom60": float(last["mom60"]),
                "sma20": float(last["sma20"]),
                "sma50": float(last["sma50"]),
            }
            row["score"] = score_swing(pd.Series(row))
            rows.append(row)
        except Exception:
            continue

    if not rows:
        st.error("Brak danych do alertów.")
        st.stop()

    alerts_text = generate_ai_alerts(rows)
    st.markdown("### 🔔 AI‑alerty (GPT‑4.1)")
    st.write(alerts_text)
