import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 1. KONFIGURACJA ŚRODOWISKA I SESJI
# ==============================================================================
st.set_page_config(
    page_title="AI ALPHA MONSTER PRO v71",
    page_icon="🚜",
    layout="wide",
)

# Sesja HTTP z nagłówkiem przeglądarki (mniej banów z Yahoo)
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
})

DB_FILE = "moje_spolki.txt"
AI_KEY = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=AI_KEY) if AI_KEY else None

if "risk_cap" not in st.session_state:
    st.session_state.risk_cap = 10000.0
if "risk_pct" not in st.session_state:
    st.session_state.risk_pct = 1.0


def load_tickers():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                c = f.read().strip()
                return c if c else "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BDRX, BNOX, BOLT"
        except Exception:
            pass
    return "ADTX, ACRS, ALZN, ANIX, ATHE, BBI, BCTX, BDRX, BNOX, BOLT"


# ==============================================================================
# 2. CSS NEON DARK
# ==============================================================================
st.markdown(
    """
    <style>
    .stApp {
        background-color: #010101;
        color: #e0e0e0;
        font-family: 'Inter', sans-serif;
    }

    .top-mini-tile {
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        background: linear-gradient(145deg, #0d1117, #050505);
        border: 1px solid #30363d;
        margin-bottom: 15px;
        transition: 0.3s ease;
    }
    .tile-buy {
        border: 2px solid #00ff88 !important;
        box-shadow: 0 0 15px rgba(0,255,136,0.3);
    }
    .tile-sell {
        border: 2px solid #ff4b4b !important;
        box-shadow: 0 0 15px rgba(255,75,75,0.3);
    }
    .tile-neutral {
        border: 2px solid #8b949e !important;
        box-shadow: 0 0 15px rgba(139,148,158,0.3);
    }

    .main-card {
        background: linear-gradient(145deg, #0d1117, #020202);
        padding: 35px;
        border-radius: 25px;
        border: 1px solid #30363d;
        text-align: center;
        min-height: 1100px;
        width: 100%;
        transition: 0.3s ease-in-out;
        margin-bottom: 40px;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    }
    .main-card:hover {
        border-color: #58a6ff;
        box-shadow: 0 0 30px rgba(88, 166, 255, 0.15);
    }

    .sig-buy {
        color: #00ff88;
        font-weight: 900;
        font-size: 1.8rem;
        text-transform: uppercase;
        text-shadow: 0 0 12px #00ff88;
    }
    .sig-sell {
        color: #ff4b4b;
        font-weight: 900;
        font-size: 1.8rem;
        text-transform: uppercase;
        text-shadow: 0 0 12px #ff4b4b;
    }
    .sig-neutral {
        color: #8b949e;
        font-weight: 800;
        font-size: 1.5rem;
    }

    .pos-calc-box {
        background: rgba(88, 166, 255, 0.08);
        border-radius: 15px;
        padding: 25px;
        margin: 25px 0;
        border: 1px solid #58a6ff;
        color: #58a6ff;
    }
    .pos-val {
        font-size: 2.2rem;
        display: block;
        margin-bottom: 5px;
        font-weight: 900;
        text-shadow: 0 0 10px #58a6ff;
    }
    .pos-label {
        font-size: 0.85rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 2px;
    }

    .tech-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        background: rgba(255,255,255,0.02);
        padding: 20px;
        border-radius: 20px;
        text-align: left;
    }
    .tech-row {
        border-bottom: 1px solid #21262d;
        padding: 10px 0;
        font-size: 0.95rem;
        display: flex;
        justify-content: space-between;
    }
    .t-lab { color: #8b949e; }
    .t-val { color: #ffffff; font-weight: bold; }

    .ai-strategy-box {
        padding: 20px;
        border-radius: 15px;
        margin-top: 25px;
        font-size: 1rem;
        background: rgba(0, 255, 136, 0.05);
        border: 1px solid #00ff88;
        line-height: 1.6;
        text-align: left;
        color: #00ff88;
    }

    .news-link {
        color: #58a6ff;
        text-decoration: none;
        font-size: 0.85rem;
        display: block;
        margin-bottom: 12px;
        text-align: left;
    }

    .block-container {
        max-width: 98% !important;
        padding-top: 1.5rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# 3. SILNIK ANALITYCZNY (RSI, SMA, ATR, SL/TP, NEWS)
# ==============================================================================
def get_monster_analysis(symbol: str):
    try:
        time.sleep(np.random.uniform(0.1, 0.4))  # lekkie opóźnienie
        s = symbol.strip().upper()
        t = yf.Ticker(s, session=session)

        df_raw = t.history(period="2y", interval="1d", auto_adjust=False)
        if df_raw.empty or len(df_raw) < 200:
            return None

        # naprawa zerowych cen
        df_raw["Close"] = df_raw["Close"].replace(0, np.nan).ffill()
        c = df_raw["Close"]
        curr_price = float(c.iloc[-1])

        # SMA
        s20 = c.rolling(20).mean().iloc[-1]
        s50 = c.rolling(50).mean().iloc[-1]
        s100 = c.rolling(100).mean().iloc[-1]
        s200 = c.rolling(200).mean().iloc[-1]

        # RSI 14
        delta = c.diff()
        g = delta.where(delta > 0, 0).rolling(14).mean()
        l = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi_val = 100 - (100 / (1 + (g / (l + 1e-12)))).iloc[-1]

        # MACD
        e12 = c.ewm(span=12).mean()
        e26 = c.ewm(span=26).mean()
        macd_val = (e12 - e26).iloc[-1]

        # Pivot + 52T
        prev = df_raw.iloc[-2]
        pivot = (prev["High"] + prev["Low"] + prev["Close"]) / 3
        h52 = df_raw["High"].tail(252).max()
        l52 = df_raw["Low"].tail(252).min()

        # ATR
        high = df_raw["High"]
        low = df_raw["Low"]
        close = df_raw["Close"]
        tr = pd.concat(
            [
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # Pozycja, SL, TP
        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100.0)
        sh = int(risk_cash / (atr * 1.5)) if atr > 0 else 0
        sl = curr_price - (atr * 1.5)
        tp = curr_price + (atr * 3.5)

        # Werdykt
        if rsi_val < 33:
            v_text, v_class, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi_val > 67:
            v_text, v_class, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else:
            v_text, v_class, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        # Newsy
        news = []
        try:
            for n in t.news[:3]:
                news.append(
                    {
                        "title": str(n.get("title", ""))[:65],
                        "link": n.get("link", ""),
                    }
                )
        except Exception:
            pass

        return {
            "symbol": s,
            "price": curr_price,
            "rsi": float(rsi_val),
            "macd": float(macd_val),
            "pivot": float(pivot),
            "s20": float(s20),
            "s50": float(s50),
            "s100": float(s100),
            "s200": float(s200),
            "h52": float(h52),
            "l52": float(l52),
            "atr": float(atr),
            "sh": int(sh),
            "sl": float(sl),
            "tp": float(tp),
            "v_text": v_text,
            "v_class": v_class,
            "v_type": v_type,
            "news": news,
            "df": df_raw.tail(80),
        }
    except Exception:
        return None


# ==============================================================================
# 4. UI + WIELOWĄTKOWOŚĆ + ZERO BŁĘDÓW DOM
# ==============================================================================
st.sidebar.title("🚜 MONSTER v71 PRO")

st_autorefresh(interval=60000, key="global_monster_refresh")

t_area = st.sidebar.text_area("Lista Symboli (CSV):", load_tickers(), height=250)
st.session_state.risk_cap = st.sidebar.number_input(
    "Kapitał PLN:", value=st.session_state.risk_cap
)
st.session_state.risk_pct = st.sidebar.slider(
    "Ryzyko %:", 0.1, 5.0, st.session_state.risk_pct
)

if st.sidebar.button("💾 ZAPISZ I START"):
    with open(DB_FILE, "w") as f:
        f.write(t_area)
    st.rerun()

symbols = [s.strip().upper() for s in t_area.split(",") if s.strip()]

with ThreadPoolExecutor(max_workers=10) as executor:
    results = [r for r in executor.map(get_monster_analysis, symbols) if r]

if results:
    # TOP 10 po RSI
    st.subheader("🔥 TOP SYGNAŁY (Najniższe RSI)")
    top_cols = st.columns(5)
    for i, r in enumerate(sorted(results, key=lambda x: x["rsi"])[:10]):
        tile_class = (
            "tile-buy" if r["v_type"] == "buy"
            else "tile-sell" if r["v_type"] == "sell"
            else "tile-neutral"
        )
        with top_cols[i % 5]:
            st.markdown(
                f"""
                <div class="top-mini-tile {tile_class}">
                    <b>{r['symbol']}</b><br>
                    {r['price']:.4f}<br>
                    <small>{r['v_text']}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    cols = st.columns(3)
    for idx, r in enumerate(results):
        with cols[idx % 3]:
            with st.container():
                st.markdown(
                    f"""
                    <div class="main-card">
                        <div>
                            <h2 style="margin:0;">{r['symbol']}</h2>
                            <h1 style="color:#58a6ff; margin:10px 0;">{r['price']:.6f}</h1>
                            <div class="{r['v_class']}">{r['v_text']}</div>
                        </div>

                        <div class="pos-calc-box">
                            <span class="pos-label">WIELKOŚĆ POZYCJI</span>
                            <span class="pos-val">{r['sh']} SZT.</span>
                            <small>SL: {r['sl']:.6f} | TP: {r['tp']:.6f}</small>
                        </div>

                        <div class="tech-grid">
                            <div class="tech-row">
                                <span class="t-lab">RSI (14)</span>
                                <span class="t-val">{r['rsi']:.1f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">MACD</span>
                                <span class="t-val">{r['macd']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">SMA 20</span>
                                <span class="t-val">{r['s20']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">SMA 50</span>
                                <span class="t-val">{r['s50']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">SMA 100</span>
                                <span class="t-val">{r['s100']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">SMA 200</span>
                                <span class="t-val">{r['s200']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">Pivot</span>
                                <span class="t-val">{r['pivot']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">Max 52T</span>
                                <span class="t-val">{r['h52']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">Min 52T</span>
                                <span class="t-val">{r['l52']:.4f}</span>
                            </div>
                            <div class="tech-row">
                                <span class="t-lab">ATR (14)</span>
                                <span class="t-val">{r['atr']:.4f}</span>
                            </div>
                        </div>
                    """,
                    unsafe_allow_html=True,
                )

                fig = go.Figure(
                    data=[
                        go.Candlestick(
                            x=r["df"].index,
                            open=r["df"]["Open"],
                            high=r["df"]["High"],
                            low=r["df"]["Low"],
                            close=r["df"]["Close"],
                        )
                    ]
                )
                fig.update_layout(
                    template="plotly_dark",
                    height=400,
                    margin=dict(l=0, r=0, t=0, b=0),
                    xaxis_rangeslider_visible=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                # unikalny key -> brak błędów DOM
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    key=f"chart_{r['symbol']}_{idx}",
                    config={"displayModeBar": False},
                )

                if client and st.button(
                    f"🤖 STRATEGIA AI {r['symbol']}",
                    key=f"ai_{r['symbol']}_{idx}",
                ):
                    prompt = (
                        f"Analiza {r['symbol']}: "
                        f"cena {r['price']:.6f}, RSI {r['rsi']:.1f}, "
                        f"MACD {r['macd']:.4f}, Pivot {r['pivot']:.4f}, "
                        f"ATR {r['atr']:.4f}, SL {r['sl']:.6f}, TP {r['tp']:.6f}. "
                        "Podaj konkretny plan wejścia, wyjścia, zarządzania pozycją i ryzykiem "
                        "dla krótkoterminowego trade'u."
                    )
                ai_res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                    )
                    st.markdown(
                        f"<div class='ai-strategy-box'>{ai_res.choices[0].message.content}</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    "<div style='text-align:left; margin-top:20px;'>"
                    "<span class='t-lab'>OSTATNIE NEWSY:</span></div>",
                    unsafe_allow_html=True,
                )
                
                for n in res["news"]:
                    if n.get("link"):
                        st.markdown(
                            f"<a class='news-link' href='{n['link']}' target='_blank'>● {n['title']}</a>",
                            unsafe_allow_html=True,
                        )

                st.markdown("</div>", unsafe_allow_html=True)

# Stopka - musi być wyrównana do lewej (zero spacji na początku)
st.markdown(
    "<center><br><small style='color:#333;'>AI ALPHA MONSTER PRO v71 ULTRA © 2026 | "
    "Auto-refresh: 60s</small></center>",
    unsafe_allow_html=True,
)
