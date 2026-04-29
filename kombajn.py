import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

# --- 1. KONFIGURACJA ---
st.set_page_config(page_title="NEON COMMANDER v102", page_icon="⚡", layout="wide")

# Ustawienia E-mail
EMAIL_RECEIVER = "szelag-adam@t-online.de"
EMAIL_SENDER = "szelag-adam@t-online.de" 
SMTP_SERVER = "securesmtp.t-online.de"
SMTP_PORT = 465

if "ai_results" not in st.session_state: st.session_state.ai_results = {}
if "full_analysis" not in st.session_state: st.session_state.full_analysis = {}
if "risk_cap" not in st.session_state: st.session_state.risk_cap = 10000.0
if "previous_trends" not in st.session_state: st.session_state.previous_trends = {}

DB_FILE = "moje_spolki.txt"

# --- 2. STYLE NEONOWE ---
st.markdown("""
<style>
    .stApp { background-color: #020202; color: #e0e0e0; font-family: 'Courier New', monospace; }
    .neon-card { background: #0d1117; border: 1px solid #30363d; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .neon-card-buy { border: 2px solid #00ff88 !important; box-shadow: 0 0 15px rgba(0,255,136,0.2); }
    .top-tile { background: #161b22; border-radius: 12px; padding: 12px; text-align: center; border-bottom: 4px solid #58a6ff; }
    .status-buy { color: #00ff88; text-shadow: 0 0 10px #00ff88; font-weight: bold; }
    .status-sell { color: #ff4b4b; text-shadow: 0 0 10px #ff4b4b; font-weight: bold; }
    .tp-box { color: #00ff88; font-weight: bold; }
    .sl-box { color: #ff4b4b; font-weight: bold; }
    .trend-tag { padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; border: 1px solid #30363d; }
    .bid-style { color: #00ff88; font-weight: bold; }
    .ask-style { color: #ff4b4b; font-weight: bold; }
    .ai-full-box { background: rgba(88, 166, 255, 0.1); border-left: 4px solid #58a6ff; padding: 15px; margin-top: 10px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNKCJE POMOCNICZE ---
def send_email(subject, body, password):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_SENDER, password)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Błąd e-mail: {e}")
        return False

def get_data(symbol):
    try:
        t = yf.Ticker(symbol.strip().upper())
        df = t.history(period="1y", interval="1d")
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        info = t.info
        p = float(df['Close'].iloc[-1])
        bid = info.get('bid') or p * 0.999
        ask = info.get('ask') or p * 1.001
        
        # Obliczanie trendów (SMA 20, 50, 200)
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        trends = {
            "K": "UP" if p > sma20 else "DOWN",
            "S": "UP" if p > sma50 else "DOWN",
            "D": "UP" if p > sma200 else "DOWN"
        }
        
        delta = df['Close'].diff()
        rsi = float(100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (delta.where(delta < 0, 0).abs().rolling(14).mean() + 1e-9)))).iloc[-1])
        
        return {
            "symbol": symbol.upper(), "price": p, "bid": bid, "ask": ask, 
            "rsi": rsi, "pp": (df['High'].iloc[-2] + df['Low'].iloc[-2] + df['Close'].iloc[-2]) / 3,
            "high": float(df['High'].iloc[-1]), "low": float(df['Low'].iloc[-1]),
            "change": ((p - df['Close'].iloc[-2])/df['Close'].iloc[-2]*100),
            "trends": trends, "df": df.tail(45)
        }
    except: return None

def run_ai_short(d, key):
    if d['symbol'] in st.session_state.ai_results: return st.session_state.ai_results[d['symbol']]
    try:
        client = OpenAI(api_key=key)
        prompt = f"Analiza {d['symbol']} @ {d['price']}. RSI:{d['rsi']:.1f}. Zwróć JSON: {{\"w\": \"KUP/SPRZEDAJ/TRZYMAJ\", \"sl\": cena, \"tp\": cena}}"
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        res = json.loads(resp.choices[0].message.content)
        st.session_state.ai_results[d['symbol']] = res
        return res
    except: return None

def run_ai_full(d, key):
    try:
        client = OpenAI(api_key=key)
        prompt = f"Analiza techniczna {d['symbol']} @ {d['price']}. Podaj konkretne powody wejścia/wyjścia (żołnierskie punkty)."
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        res = resp.choices[0].message.content
        st.session_state.full_analysis[d['symbol']] = res
        return res
    except: return "Błąd analizy."

# --- 4. PANEL STEROWANIA ---
with st.sidebar:
    st.title("🚜 MONSTER v102")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI Key", type="password")
    email_pass = st.text_input("T-Online App Password", type="password")
    
    st.session_state.risk_cap = st.number_input("💵 Kapitał:", value=st.session_state.risk_cap)
    risk_pct = st.slider("🎯 Ryzyko na transakcję (%)", 0.1, 5.0, 1.0)
    
    refresh_min = st.slider("⏱️ Odświeżanie (min)", 1, 10, 2)
    st_autorefresh(interval=refresh_min * 60 * 1000, key="auto_ref")

    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: default_tickers = f.read()
    else: default_tickers = "NVDA, TSLA, BTC-USD"
    
    t_in = st.text_area("Lista Tickerów:", value=default_tickers, height=150)
    if st.button("🚀 SKANUJ"):
        with open(DB_FILE, "w") as f: f.write(t_in)
        st.session_state.ai_results = {}; st.session_state.full_analysis = {}
        st.rerun()

# --- 5. LOGIKA GŁÓWNA ---
symbols = [s.strip().upper() for s in t_in.split(",") if s.strip()]
data_list = []
email_updates = []

with st.spinner("Pobieranie danych..."):
    for sym in symbols:
        res = get_data(sym)
        if res:
            if api_key: res['ai'] = run_ai_short(res, api_key)
            data_list.append(res)
            
            # Detekcja zmiany trendu "Tylko Raz"
            current_trends = str(res['trends'])
            if sym in st.session_state.previous_trends and st.session_state.previous_trends[sym] != current_trends:
                email_updates.append(f"ZMIANA TRENDU: {sym} -> {res['trends']} (Cena: {res['price']})")
            st.session_state.previous_trends[sym] = current_trends

# Automatyczna wysyłka e-mail przy zmianie
if email_updates and email_pass:
    send_email(f"MONSTER: Alert Zmiany Trendu {datetime.now().strftime('%H:%M')}", "\n".join(email_updates), email_pass)
    st.toast("Wysłano powiadomienie e-mail!", icon="📧")

# --- 6. INTERFEJS ---
if data_list:
    # Radar Top 10
    st.subheader("🔥 RADAR TRENDÓW")
    cols = st.columns(min(len(data_list), 5))
    for i, r in enumerate(data_list[:10]):
        with cols[i % 5]:
            st.markdown(f"""<div class="top-tile"><b>{r['symbol']}</b><br>{r['price']:.2f}<br><small>{r['trends']['K']}/{r['trends']['S']}/{r['trends']['D']}</small></div>""", unsafe_allow_html=True)

    st.divider()

    for d in data_list:
        ai = d.get('ai')
        card_class = "neon-card-buy" if ai and "KUP" in ai['w'].upper() else ""
        
        st.markdown(f'<div class="neon-card {card_class}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 3, 1.8])
        
        with c1:
            st.markdown(f"## {d['symbol']}")
            # Wyświetlanie trendów w kolorach
            t_html = ""
            for k, v in d['trends'].items():
                clr = "#00ff88" if v == "UP" else "#ff4b4b"
                t_html += f'<span class="trend-tag" style="color:{clr}; border-color:{clr}">{k}:{v}</span> '
            st.markdown(t_html, unsafe_allow_html=True)
            
            if ai:
                v_clr = "status-buy" if "KUP" in ai['w'].upper() else "status-sell" if "SPRZEDAJ" in ai['w'].upper() else ""
                st.markdown(f'<span class="{v_clr}" style="font-size:1.3rem;">{ai["w"]}</span>', unsafe_allow_html=True)
            
            st.write(f"CENA: **{d['price']:.2f}** ({d['change']:.2f}%)")
            st.markdown(f"B: <span class='bid-style'>{d['bid']:.2f}</span> | A: <span class='ask-style'>{d['ask']:.2f}</span>", unsafe_allow_html=True)
            st.write(f"RSI: {d['rsi']:.1f} | PP: {d['pp']:.2f}")

        with c2:
            fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
            fig.update_layout(template="plotly_dark", height=220, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{d['symbol']}")

        with c3:
            if ai:
                st.markdown(f"<span class='tp-box'>TP: {ai['tp']}</span> | <span class='sl-box'>SL: {ai['sl']}</span>", unsafe_allow_html=True)
                
                # Kalkulator pozycji
                try:
                    diff = abs(d['price'] - float(ai['sl']))
                    risk_val = st.session_state.risk_cap * (risk_pct / 100)
                    if diff > 0:
                        shares = int(risk_val / diff)
                        st.success(f"POZYCJA: {shares} szt.")
                        st.caption(f"Wartość: {shares * d['price']:.2f} USD")
                except: pass

                if st.button("🧠 ANALIZA", key=f"btn_{d['symbol']}"):
                    run_ai_full(d, api_key)
                
                if d['symbol'] in st.session_state.full_analysis:
                    st.markdown(f'<div class="ai-full-box">{st.session_state.full_analysis[d["symbol"]]}</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
