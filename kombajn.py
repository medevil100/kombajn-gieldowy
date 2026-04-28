Masz słowo. Poniżej masz **NEON SENTINEL PRO v97** z:

- **AI scoring 0–100**
- **heatmapą portfela**
- **alertami cenowymi**
- **pełnym modułem portfolio**
- dalej **single-file, neon, bez śmieci**.

```python
import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import os
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime

# ---------------------------------------------------------
# 1. SESSION STATE & CONFIG
# ---------------------------------------------------------
DEFAULTS = {
    "risk_cap": 10000.0,
    "risk_pct": 2.0,
    "ai_results": {},
    "alerts": {},          # {symbol: {"above": float|None, "below": float|None}}
    "portfolio": None      # lazy load
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

DB_FILE = "moje_spolki.txt"
PORTFOLIO_FILE = "portfolio.json"

st.set_page_config(
    page_title="NEON SENTINEL PRO v97",
    page_icon="⚡",
    layout="wide"
)

# ---------------------------------------------------------
# 2. HELPERS: TICKERS & PORTFOLIO
# ---------------------------------------------------------
def load_tickers():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "NVDA, TSLA, BTC-USD, PKO.WA"

def load_portfolio():
    if st.session_state.portfolio is not None:
        return st.session_state.portfolio
    if not os.path.exists(PORTFOLIO_FILE):
        st.session_state.portfolio = {"positions": [], "history": []}
        return st.session_state.portfolio
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            st.session_state.portfolio = json.load(f)
    except:
        st.session_state.portfolio = {"positions": [], "history": []}
    return st.session_state.portfolio

def save_portfolio(p):
    st.session_state.portfolio = p
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=4)

# ---------------------------------------------------------
# 3. CSS — NEON STYLE
# ---------------------------------------------------------
st.markdown("""
<style>
.stApp { background-color: #020202; color: #ffffff; font-family: 'Courier New', monospace; }
.neon-card { background: #0d0d0d; border: 1px solid #1f1f1f; padding: 25px; border-radius: 20px; margin-bottom: 30px; }
.status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; border: 2px solid #00ff88; padding: 5px 15px; border-radius: 10px; }
.status-sell { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; border: 2px solid #ff0055; padding: 5px 15px; border-radius: 10px; }
.status-hold { color: #58a6ff; text-shadow: 0 0 10px #58a6ff; font-weight: bold; border: 2px solid #58a6ff; padding: 5px 15px; border-radius: 10px; }
.tp-box { border: 1px solid #00ff88; padding: 12px; border-radius: 10px; color: #00ff88; text-align: center; background: rgba(0,255,136,0.1); font-weight: bold; }
.sl-box { border: 1px solid #ff0055; padding: 12px; border-radius: 10px; color: #ff0055; text-align: center; background: rgba(255,0,85,0.1); font-weight: bold; }
.top-tile { background: #111; border: 1px solid #333; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #58a6ff; }
.score-badge { margin-top:6px; display:inline-block; padding:4px 10px; border-radius:999px; font-size:0.8rem; border:1px solid #58a6ff; color:#58a6ff; }
.alert-badge { display:inline-block; margin-top:6px; font-size:0.75rem; color:#ffcc00; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 4. TECHNICAL ENGINE
# ---------------------------------------------------------
def fix_col(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")

        if df.empty or len(df) < 50:
            return None

        df = fix_col(df)

        price = float(df["Close"].iloc[-1])
        ma50 = df["Close"].rolling(50).mean().iloc[-1]
        ma200 = df["Close"].rolling(200).mean().iloc[-1]

        high = float(df["High"].iloc[-1])
        low = float(df["Low"].iloc[-1])

        prev_h = df["High"].iloc[-2]
        prev_l = df["Low"].iloc[-2]
        prev_c = df["Close"].iloc[-2]

        pivot = (prev_h + prev_l + prev_c) / 3

        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = float(100 - (100 / (1 + gain / (loss + 1e-9))).iloc[-1])

        if rsi < 1.0:
            return None

        return {
            "symbol": symbol.upper(),
            "price": price,
            "rsi": rsi,
            "ma50": ma50,
            "ma200": ma200,
            "pp": pivot,
            "high": high,
            "low": low,
            "df": df.tail(45),
            "change": ((price - prev_c) / prev_c * 100)
        }

    except:
        return None

# ---------------------------------------------------------
# 5. AI ENGINE (WITH SCORING 0–100)
# ---------------------------------------------------------
def run_ai(d, key):
    if d["symbol"] in st.session_state.ai_results:
        return st.session_state.ai_results[d["symbol"]]

    try:
        client = OpenAI(api_key=key)

        prompt = (
            f"Analiza {d['symbol']} @ {d['price']}.\n"
            f"DATA: RSI {d['rsi']:.1f}, High {d['high']}, Low {d['low']}, "
            f"Pivot {d['pp']:.2f}, MA50 {d['ma50']:.2f}, MA200 {d['ma200']:.2f}.\n"
            f"Zwróć werdykt w formacie JSON:\n"
            f"{{"
            f"\"w\": \"KUP\"|\"SPRZEDAJ\"|\"TRZYMAJ\", "
            f"\"sl\": cena_sl, "
            f"\"tp\": cena_tp, "
            f"\"score\": liczba_od_0_do_100, "
            f"\"uzas\": \"max 10 slow uzasadnienia technicznego\""
            f"}}"
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        res = json.loads(resp.choices[0].message.content)

        # fallback jeśli model nie zwróci score
        if "score" not in res:
            # prosty heurystyczny scoring z RSI
            base = max(0, min(100, 100 - abs(d["rsi"] - 50) * 2))
            res["score"] = int(base)

        st.session_state.ai_results[d["symbol"]] = res
        return res

    except:
        return None

# ---------------------------------------------------------
# 6. SIDEBAR: SETTINGS, TICKERS, PORTFOLIO, ALERTS
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚡ SENTINEL PRO v97")

    key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")

    st.session_state.risk_cap = st.number_input("💵 Kapitał portfela:", value=st.session_state.risk_cap)
    st.session_state.risk_pct = st.slider("Ryzyko % na trade", 0.5, 5.0, st.session_state.risk_pct)

    t_in = st.text_area("Lista Symboli:", value=load_tickers(), height=150)

    if st.button("🚀 SKANUJ I ZAPISZ"):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            f.write(t_in)
        st.session_state.ai_results = {}
        st.rerun()

    st.markdown("---")
    st.subheader("📦 Portfolio")

    p = load_portfolio()

    with st.expander("Dodaj / edytuj pozycję", expanded=False):
        colp1, colp2 = st.columns(2)
        with colp1:
            new_sym = st.text_input("Symbol", value="")
            qty = st.number_input("Ilość", value=0.0, step=1.0)
        with colp2:
            buy_price = st.number_input("Cena zakupu", value=0.0, step=0.01)
            add_btn = st.button("➕ Zapisz pozycję")

        if add_btn and new_sym and qty > 0 and buy_price > 0:
            # nadpisujemy jeśli istnieje
            updated = False
            for pos in p["positions"]:
                if pos["symbol"].upper() == new_sym.upper():
                    pos["qty"] = qty
                    pos["buy_price"] = buy_price
                    updated = True
                    break
            if not updated:
                p["positions"].append({
                    "symbol": new_sym.upper(),
                    "qty": qty,
                    "buy_price": buy_price
                })
            save_portfolio(p)
            st.success("Pozycja zapisana.")
            st.rerun()

    if p["positions"]:
        st.write("Aktualne pozycje:")
        st.table(pd.DataFrame(p["positions"]))

    st.markdown("---")
    st.subheader("⏰ Alerty cenowe")

    alert_sym = st.text_input("Symbol alertu", value="")
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        above = st.text_input("Alert powyżej ceny", value="")
    with col_a2:
        below = st.text_input("Alert poniżej ceny", value="")
    if st.button("💾 Zapisz alert"):
        if alert_sym:
            st.session_state.alerts[alert_sym.upper()] = {
                "above": float(above) if above.strip() else None,
                "below": float(below) if below.strip() else None
            }
            st.success("Alert zapisany.")
    if st.session_state.alerts:
        st.write("Aktywne alerty:")
        st.json(st.session_state.alerts)

    st_autorefresh(interval=60000, key="v97_ref")

# ---------------------------------------------------------
# 7. MAIN DATA FETCH
# ---------------------------------------------------------
tickers = [x.strip().upper() for x in t_in.split(",") if x.strip()]

with ThreadPoolExecutor(max_workers=10) as executor:
    data_list = [d for d in executor.map(get_data, tickers) if d is not None]

# ---------------------------------------------------------
# 8. PORTFOLIO HEATMAP (BASED ON VALUE & SCORE)
# ---------------------------------------------------------
def build_portfolio_heatmap(data_list, portfolio):
    if not portfolio["positions"]:
        return None

    df_prices = {d["symbol"]: d for d in data_list}
    rows = []
    for pos in portfolio["positions"]:
        sym = pos["symbol"].upper()
        if sym not in df_prices:
            continue
        d = df_prices[sym]
        ai = st.session_state.ai_results.get(sym)
        score = ai["score"] if ai else None
        value = pos["qty"] * d["price"]
        rows.append({
            "symbol": sym,
            "value": value,
            "score": score if score is not None else 50
        })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df = df.sort_values("value", ascending=False)

    fig = go.Figure(
        data=go.Heatmap(
            z=df["score"],
            x=df["symbol"],
            y=["AI score"],
            colorscale="RdYlGn",
            zmin=0,
            zmax=100,
            text=[f"{s}<br>{v:,.0f} ({sc})" for s, v, sc in zip(df["symbol"], df["value"], df["score"])],
            hoverinfo="text"
        )
    )
    fig.update_layout(
        title="Heatmapa portfela (AI score 0–100)",
        template="plotly_dark",
        height=260,
        margin=dict(l=0, r=0, t=40, b=0)
    )
    return fig

# ---------------------------------------------------------
# 9. DASHBOARD
# ---------------------------------------------------------
if data_list:

    # TOP 10
    st.subheader("🔥 TOP 10 SYGNAŁÓW (Techniczny + AI Scoring)")
    t_cols = st.columns(5)

    ranked = []
    for r in data_list:
        ai_brief = run_ai(r, key) if key else None
        score = ai_brief["score"] if ai_brief else 0
        ranked.append((r, ai_brief, score))

    ranked = sorted(ranked, key=lambda x: x[2], reverse=True)[:10]

    for i, (r, ai_brief, score) in enumerate(ranked):
        tag = ai_brief["w"] if ai_brief else "---"
        color = "#00ff88" if tag == "KUP" else "#ff4b4b" if tag == "SPRZEDAJ" else "#58a6ff"
        with t_cols[i % 5]:
            st.markdown(
                f"<div class='top-tile'><b>{r['symbol']}</b><br>"
                f"<span style='color:{color}; font-weight:bold;'>{tag}</span><br>"
                f"<small>RSI: {r['rsi']:.1f}</small><br>"
                f"<span class='score-badge'>AI score: {score}</span></div>",
                unsafe_allow_html=True
            )

    st.divider()

    # HEATMAP PORTFOLIO
    p = load_portfolio()
    heatmap_fig = build_portfolio_heatmap(data_list, p)
    if heatmap_fig:
        st.plotly_chart(heatmap_fig, use_container_width=True)

    st.divider()

    # FULL CARDS
    for d in data_list:
        ai = run_ai(d, key) if key else None

        st.markdown('<div class="neon-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 2.5, 1.5])

        # LEFT PANEL
        with c1:
            st.markdown(f"### {d['symbol']}")

            if ai:
                cls = (
                    "status-buy" if ai["w"] == "KUP"
                    else "status-sell" if ai["w"] == "SPRZEDAJ"
                    else "status-hold"
                )
                st.markdown(f'<span class="{cls}">{ai["w"]}</span>', unsafe_allow_html=True)
                st.markdown(f"<div class='score-badge'>AI score: {ai['score']}</div>", unsafe_allow_html=True)

            st.markdown(f"<br>Cena: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.write(f"Szczyt: {d['high']:.2f} | Dołek: {d['low']:.2f}")
            st.write(f"Pivot: {d['pp']:.2f} | RSI: {d['rsi']:.1f}")

            # ALERT CHECK
            alerts = st.session_state.alerts.get(d["symbol"], {})
            alert_msgs = []
            if alerts:
                if alerts.get("above") is not None and d["price"] >= alerts["above"]:
                    alert_msgs.append(f"⚠ Cena >= {alerts['above']}")
                if alerts.get("below") is not None and d["price"] <= alerts["below"]:
                    alert_msgs.append(f"⚠ Cena <= {alerts['below']}")
            if alert_msgs:
                st.markdown(
                    "<div class='alert-badge'>" + "<br>".join(alert_msgs) + "</div>",
                    unsafe_allow_html=True
                )

        # CHART
        with c2:
            fig = go.Figure(
                data=[go.Candlestick(
                    x=d["df"].index,
                    open=d["df"]["Open"],
                    high=d["df"]["High"],
                    low=d["df"]["Low"],
                    close=d["df"]["Close"]
                )]
            )
            fig.add_hline(y=d["pp"], line_dash="dot", line_color="#58a6ff", annotation_text="Pivot")
            fig.update_layout(
                template="plotly_dark",
                height=280,
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis_rangeslider_visible=False
            )
            st.plotly_chart(fig, use_container_width=True, key=f"f_{d['symbol']}")

        # RIGHT PANEL
        with c3:
            if ai:
                st.markdown(f'<div class="tp-box"><small>TAKE PROFIT</small><br><b>{ai["tp"]}</b></div>', unsafe_allow_html=True)
                st.markdown(f'<div class="sl-box" style="margin-top:10px;"><small>STOP LOSS</small><br><b>{ai["sl"]}</b></div>', unsafe_allow_html=True)

                try:
                    diff = abs(d["price"] - float(ai["sl"]))
                    risk_val = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
                    shares = int(risk_val / diff) if diff > 0 else 0

                    st.markdown(
                        f"<div style='background:#111; padding:15px; border-radius:10px; "
                        f"border:1px solid #333; margin-top:15px; text-align:center;'>"
                        f"KUP: <b style='color:#00ff88; font-size:1.3rem;'>{shares} szt.</b>"
                        f"<br><small><i>{ai['uzas']}</i></small></div>",
                        unsafe_allow_html=True
                    )
                except:
                    pass

        st.markdown("</div>", unsafe_allow_html=True)

else:
    st.info("System gotowy. Wpisz symbole i klucz OpenAI (PRO v97).")
```
