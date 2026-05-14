import streamlit as st
import pandas as pd
import numpy as np
import pandas_ta as ta
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import time
import requests
from websocket import create_connection

# =========================================================
# KONFIGURACJA
# =========================================================
st.set_page_config(page_title="Kombajn Giełdowy XTB ULTRA", layout="wide")
st.title("📈 Kombajn Giełdowy – XTB REAL + GPT‑4.1 (ULTRA)")

# =========================================================
# KLIENT XTB
# =========================================================
class XTBClient:
    def __init__(self, user_id: str, password: str, mode: str = "real"):
        self.user_id = user_id
        self.password = password
        self.mode = mode
        self.ws = None
        self.session_id = None

    def _get_url(self):
        # NOWE, DZIAŁAJĄCE ENDPOINTY XTB
        if self.mode == "demo":
            return "wss://ws.xtb.com/demoStream"
        return "wss://ws.xtb.com/realStream"

    def connect(self):
        if self.ws is None:
            self.ws = create_connection(self._get_url())

    def send(self, command: str, arguments: dict | None = None):
        if self.ws is None:
            self.connect()

        msg = {"command": command}
        if arguments:
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

    def get_gpw_stocks(self):
        data = self.get_all_symbols()
        return [
            s for s in data
            if s.get("categoryName") == "STOCK" and s.get("currency") == "PLN"
        ]

    def get_ohlc(self, symbol: str, period: int = 1440, candles: int = 200):
        end = int(time.time())
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

        return pd.DataFrame(rows)

# =========================================================
# AI
# =========================================================

def call_gpt(system_prompt: str, user_prompt: str) -> str:
    if "OPENAI_API_KEY" not in st.secrets:
        return "(AI OFF – brak OPENAI_API_KEY)"
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {st.secrets['OPENAI_API_KEY']}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": st.secrets.get("OPENAI_MODEL", "gpt-4.1"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3
            }),
            timeout=20
        )
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(AI ERROR: {e})"

# =========================================================
# WSKAŹNIKI
# =========================================================
def compute_indicators(df):
    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=14)
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    df["mom20"] = df["close"].pct_change(20)
    return df

# =========================================================
# CACHE
# =========================================================
@st.cache_data(ttl=300)
def cached_symbols(user_id, mode):
    client = get_client(user_id, mode)
    return pd.DataFrame(client.get_gpw_stocks())

@st.cache_data(ttl=300)
def cached_ohlc(user_id, mode, symbol, period, candles):
    client = get_client(user_id, mode)
    df = client.get_ohlc(symbol, period, candles)
    return compute_indicators(df)

# =========================================================
# SESSION CLIENT
# =========================================================
def get_client(user_id, mode):
    key = f"xtb_{mode}_{user_id}"
    if key not in st.session_state:
        raise RuntimeError("Brak zalogowanego klienta XTB")
    return st.session_state[key]

def set_client(user_id, password, mode):
    client = XTBClient(user_id, password, mode)
    client.login()
    st.session_state[f"xtb_{mode}_{user_id}"] = client

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.header("🔐 XTB REAL / DEMO")
xtb_login = st.sidebar.text_input("Login XTB")
xtb_password = st.sidebar.text_input("Hasło XTB", type="password")
xtb_mode = st.sidebar.selectbox("Tryb XTB", ["real", "demo"])

if st.sidebar.button("Połącz z XTB"):
    try:
        set_client(xtb_login, xtb_password, xtb_mode)
        st.sidebar.success("Zalogowano.")
    except Exception as e:
        st.sidebar.error(f"Błąd logowania: {e}")

menu = st.sidebar.radio("Menu", ["Ranking", "Szczegóły", "AI alerty"])

# =========================================================
# GUARD
# =========================================================
if xtb_login == "" or f"xtb_{xtb_mode}_{xtb_login}" not in st.session_state:
    st.warning("Zaloguj się do XTB.")
    st.stop()

# =========================================================
# RANKING
# =========================================================
if menu == "Ranking":
    st.subheader("Ranking spółek GPW")

    symbols_df = cached_symbols(xtb_login, xtb_mode)

    # 🔥 FILTROWANIE SEKTORÓW
    sectors = sorted(symbols_df["groupName"].dropna().unique())
    selected_sector = st.selectbox("Filtr sektorów", ["Wszystkie"] + sectors)

    if selected_sector != "Wszystkie":
        symbols_df = symbols_df[symbols_df["groupName"] == selected_sector]

    limit = st.slider("Ilość spółek", 10, 150, 50)

    rows = []
    for _, s in symbols_df.head(limit).iterrows():
        try:
            df = cached_ohlc(xtb_login, xtb_mode, s["symbol"], 1440, 200)
            last = df.iloc[-1]
            rows.append({
                "symbol": s["symbol"],
                "price": last["close"],
                "rsi": last["rsi"],
                "mom20": last["mom20"],
                "sma20": last["sma20"],
                "sma50": last["sma50"],
            })
        except:
            continue

    rank_df = pd.DataFrame(rows).sort_values("mom20", ascending=False)
    st.dataframe(rank_df, use_container_width=True)

# =========================================================
# SZCZEGÓŁY — WYKRES ŚWIECOWY
# =========================================================
if menu == "Szczegóły":
    st.subheader("Szczegóły spółki – wykres świecowy")

    symbols_df = cached_symbols(xtb_login, xtb_mode)
    symbol = st.selectbox("Wybierz spółkę", symbols_df["symbol"].tolist())

    df = cached_ohlc(xtb_login, xtb_mode, symbol, 1440, 200)

    fig = go.Figure(data=[
        go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"]
        )
    ])
    fig.update_layout(title=f"Wykres świecowy – {symbol}", height=600)

    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df.tail(20), use_container_width=True)

# =========================================================
# AI ALERTY
# =========================================================
if menu == "AI alerty":
    st.subheader("AI alerty – GPT‑4.1")

    symbols_df = cached_symbols(xtb_login, xtb_mode).head(50)

    rows = []
    for _, s in symbols_df.iterrows():
        try:
            df = cached_ohlc(xtb_login, xtb_mode, s["symbol"], 1440, 200)
            last = df.iloc[-1]
            rows.append({
                "symbol": s["symbol"],
                "price": last["close"],
                "rsi": last["rsi"],
                "mom20": last["mom20"],
            })
        except:
            continue

    text = "Wygeneruj alerty tradingowe dla spółek:\n\n"
    for r in rows:
        text += f"- {r['symbol']}: cena {r['price']:.2f}, RSI {r['rsi']:.1f}, mom20 {r['mom20']:.2%}\n"

    st.write(call_gpt("Jesteś systemem alertów tradingowych.", text))
