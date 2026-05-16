import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
st.set_page_config(page_title="3× AI — Multi-Terminal", layout="wide")

if "openai_api_key" in st.secrets:
    client = OpenAI(api_key=st.secrets["openai_api_key"])
elif "OPENAI_API_KEY" in st.secrets:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
else:
    st.error("Brak klucza OPENAI_API_KEY / openai_api_key w st.secrets! Dodaj go w konfiguracji Streamlit.")
    st.stop()

# ================== STYLE ==================
st.markdown("""
<style>
body { background-color: #020617; color: #e5e7eb; font-family: system-ui, sans-serif; }
.box { padding: 15px; border-radius: 10px; font-size: 14px; margin-top: 15px; color: white; line-height: 1.5; }
.swing  { background-color: #064e3b; border-left: 5px solid #10b981; }
.day    { background-color: #1e3a8a; border-left: 5px solid #3b82f6; }
.long   { background-color: #4c1d95; border-left: 5px solid #8b5cf6; }
.heatmap-container { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; margin-bottom: 15px; }
.heatmap-tile { width: 140px; height: 85px; border-radius: 8px; padding: 10px; font-size: 12px; color: white; display: flex; flex-direction: column; justify-content: space-between; font-weight: bold; text-align: center; }
.status-bull { background-color: #15803d; border: 2px solid #22c55e; }
.status-side { background-color: #a16207; border: 2px solid #eab308; }
.status-bear { background-color: #b91c1c; border: 2px solid #ef4444; }
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Terminal Groszówek (PL + USA)")

# ================== SILNIK ANALIZY TECHNICZNEJ ==================
def calculate_indicators(ticker: str, interval: str):
    try:
        stock = yf.Ticker(ticker)
        # 730 dni dla 1h zapewnia potężną bazę danych dla spółek o niskiej płynności
        period = "730d" if interval == "1h" else "1y"
        df = stock.history(period=period, interval=interval)
        
        if df.empty or len(df) < 15:
            return None, "Brak wystarczających danych handlowych dla tej spółki w systemie yfinance."
        
        d_len = len(df)
        w_rsi = min(14, max(5, d_len // 3))
        w_ma = min(20, max(5, d_len // 2))
        
        # 1. Klasyczne RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=w_rsi).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=w_rsi).mean()
        df['RSI14'] = 100 - (100 / (1 + (gain / (loss + 0.00001))))
        
        # 2. Stochastyczne RSI
        rsi_min = df['RSI14'].rolling(window=w_rsi).min()
        rsi_max = df['RSI14'].rolling(window=w_rsi).max()
        df['StochRSI'] = (df['RSI14'] - rsi_min) / (rsi_max - rsi_min + 0.00001) * 100
        df['StochRSI_K'] = df['StochRSI'].rolling(window=min(3, max(1, d_len // 10))).mean()
        
        # 3. Dynamiczne Średnie Kroczące
        df['EMA9'] = df['Close'].ewm(span=min(9, d_len // 2), adjust=False).mean()
        df['SMA20'] = df['Close'].rolling(window=w_ma).mean()
        df['SMA50'] = df['Close'].rolling(window=min(50, d_len // 2)).mean().bfill().ffill()
        df['SMA200'] = df['Close'].rolling(window=min(200, d_len // 2)).mean().bfill().ffill()
        
        # 4. MACD
        exp1 = df['Close'].ewm(span=min(12, d_len // 3), adjust=False).mean()
        exp2 = df['Close'].ewm(span=min(26, d_len // 2), adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=min(9, d_len // 3), adjust=False).mean()
        df['Vol_Avg10'] = df['Volume'].rolling(window=min(10, d_len // 2)).mean()
        
        # 5. Wstęgi Bollingera
        df['BB_Mid'] = df['SMA20']
        df['BB_Std'] = df['Close'].rolling(window=w_ma).std()
        df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
        df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * 2)
        
        # 6. ATR
        high_low = df['High'] - df['Low']
        high_cp = (df['High'] - df['Close'].shift()).abs()
        low_cp = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(window=w_rsi).mean()
        
        # 7. VWAP
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (typical_price * df['Volume']).cumsum() / (df['Volume'].cumsum() + 0.00001)
        
        # 8. OBV (On-Balance Volume)
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        df['OBV_Slope'] = df['OBV'].diff()
        
        # 9. Analiza Formacji Świecowej
        last_s = df.iloc[-1]
        body = abs(last_s['Close'] - last_s['Open'])
        candle_range = last_s['High'] - last_s['Low'] if (last_s['High'] - last_s['Low']) > 0 else 0.0001
        upper_shadow = last_s['High'] - max(last_s['Open'], last_s['Close'])
        lower_shadow = min(last_s['Open'], last_s['Close']) - last_s['Low']
        
        candle_type = "Neutralna"
        if body / candle_range < 0.2: candle_type = "Doji (Niezdecydowanie)"
        elif lower_shadow / candle_range > 0.6: candle_type = "Młot (Popyt)"
        elif upper_shadow / candle_range > 0.6: candle_type = "Spadająca Gwiazda (Podaż)"
        df['Candle_Analysis'] = candle_type
        
        # 10. Geometria Fibonacciego
        max_p = df['High'].max()
        min_p = df['Low'].min()
        diff = max_p - min_p if (max_p - min_p) > 0 else 0.0001
        fibo = {
            "100.0% (Szczyt)": max_p,
            "61.8%": max_p - 0.382 * diff,
            "50.0%": max_p - 0.5 * diff,
            "38.2%": max_p - 0.618 * diff,
            "23.6%": max_p - 0.764 * diff,
            "0.0% (Dołek)": min_p
        }
        
        return df, fibo
    except Exception as e:
        return None, str(e)

# ================== SEKCIJA KOMUNIKACJI Z AI ==================
def ai_swing(ticker: str, text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.4,
            messages=[{"role": "user", "content": f"Jesteś agresywnym swing traderem na groszówkach. Analizujesz spółkę {ticker}. Dane techniczne: {text}. Napisz 2–3 krótkie zdania po polsku, skupione na ruchu na kilka dni, punktach zwrotnych na bazie VWAP oraz podaj sugerowane agresywne poziomy ST i TP."}],
        )
        return r.choices[0].message.content.strip()
    except Exception as e: return f"(SWING AI – błąd: {e})"

def ai_day(ticker: str, text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.2,
            messages=[{"role": "user", "content": f"Jesteś precyzyjnym daytraderem (scalperem). Analizujesz spółkę {ticker}. Dane techniczne: {text}. Skup się na StochRSI, pozycji ceny względem VWAP oraz EMA9 i formacji świecy. Napisz 2–3 konkretne zdania z ciasnymi prognozami ST/TP na najbliższe godziny."}],
        )
        return r.choices[0].message.content.strip()
    except Exception as e: return f"(DAY AI – błąd: {e})"

def ai_long(ticker: str, text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.2,
            messages=[{"role": "user", "content": f"Jesteś analitykiem długoterminowym. Analizujesz spółkę {ticker} (spekulacja/groszówka). Dane techniczne: {text}. Zwróć szczególną uwagę na wskaźnik akumulacji wolumenu OBV oraz siatkę zniesień Fibonacci. Napisz 2–3 zdania o potencjale i szerokim poziomie ryzyka."}],
        )
        return r.choices[0].message.content.strip()
    except Exception as e: return f"(LONG AI – błąd: {e})"

def ai_verdict(role: str, ticker: str, text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.1,
            messages=[{"role": "user", "content": f"Jesteś {role}. Dane o {ticker}: {text}. Zwróć wyłącznie jedno słowo: KUP, CZEKAJ lub SPRZEDAJ."}],
        )
        out = r.choices[0].message.content.upper()
        if "KUP" in out: return "KUP"
        if "SPRZED" in out: return "SPRZEDAJ"
        return "CZEKAJ"
    except Exception: return "CZEKAJ"

def ai_score(metric_type: str, text: str) -> int:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.1,
            messages=[{"role": "user", "content": f"Oceń poziom {metric_type} w skali 0–100 na podstawie danych: {text}. Zwróć tylko i wyłącznie samą liczbę."}],
        )
        digits = "".join(c for c in r.choices[0].message.content if c.isdigit())
        return max(0, min(100, int(digits))) if digits else 50
    except Exception: return 50

# ================== INTERFEJS UŻYTKOWNIKA ==================
col_in1, col_in2 = st.columns(2)
with col_in1:
    ticker_input = st.text_input("Wpisz Ticker ręcznie (np. TNON dla USA, BML.WA dla GPW):", value="").upper().strip()
with col_in2:
    interval_input = st.selectbox("Wybierz interwał świecy:", options=["1h", "1d"], index=1)

if ticker_input:
    with st.spinner("Pobieranie i algorytmiczne przetwarzanie zaawansowanych wskaźników giełdowych..."):
        df, fibo_data = calculate_indicators(ticker_input, interval_input)
        
        if df is None:
            st.error(f"Błąd danych: {fibo_data}")
        else:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            cena = last['Close']
            zmiana_proc = ((cena - prev['Close']) / prev['Close']) * 100
            
            # --- MAPOWANIE STATUSÓW I KOLORÓW KAFELKÓW ---
            rsi_stat = "bull" if last['RSI14'] < 30 else ("bear" if last['RSI14'] > 70 else "side")
            stoch_stat = "bull" if last['StochRSI_K'] < 20 else ("bear" if last['StochRSI_K'] > 80 else "side")
            vwap_stat = "bull" if cena > last['VWAP'] else "bear"
            obv_stat = "bull" if last['OBV_Slope'] > 0 else "bear"
            
            vol_ratio = last['Volume'] / last['Vol_Avg10'] if last['Vol_Avg10'] > 0 else 1
            vol_stat = "bull" if vol_ratio > 1.8 else ("bear" if vol_ratio < 0.5 else "side")
            bb_stat = "bear" if cena >= last['BB_Upper'] * 0.98 else ("bull" if cena <= last['BB_Lower'] * 1.02 else "side")
            candle_stat = "bull" if "popyt" in last['Candle_Analysis'].lower() or "młot" in last['Candle_Analysis'].lower() else ("bear" if "podaż" in last['Candle_Analysis'].lower() or "gwiazda" in last['Candle_Analysis'].lower() else "side")
            
            trend_val = "Wzrostowy" if cena > last['SMA50'] else "Spadkowy"
            trend_score = 100 if cena > last['SMA50'] and cena > last['SMA200'] else (0 if cena < last['SMA50'] and cena < last['SMA200'] else 50)

            # Budowa paczki tekstowej dla LLM
            fibo_summary = ", ".join([f"{k}: {v:.4f}" for k, v in fibo_data.items()])
            raport_tekst = (
                f"Cena: {cena:.4f}, Zmiana: {zmiana_proc:+.2f}%, RSI14: {last['RSI14']:.1f}, StochRSI_K: {last['StochRSI_K']:.1f}, "
                f"VWAP: {last['VWAP']:.4f}, OBV_Slope: {last['OBV_Slope']:.0f}, EMA9: {last['EMA9']:.4f}, "
                f"SMA50: {last['SMA50']:.4f}, SMA200: {last['SMA200']:.4f}, Trend: {trend_val}, TrendScore: {trend_score}, "
                f"ATR: {last['ATR']:.4f}, Wolumen: {vol_ratio:.1f}x normy, Formacja świecy: {last['Candle_Analysis']}, "
                f"Poziomy Fibo: {fibo_summary}, Bollinger: Góra={last['BB_Upper']:.4f}, Dół={last['BB_Lower']:.4f}"
            )
            
            # Pobieranie ocen skumulowanych i werdyktów
            risk_score = ai_score("ryzyka inwestycyjnego (0=bezpiecznie, 100=skrajna spekulacja)", raport_tekst)
            opp_score = ai_score("potencjału zysku / szansy na wybicie (0=brak ruchu, 100=rakieta)", raport_tekst)
            
            v_swing = ai_verdict("agresywnym swing traderem", ticker_input, raport_tekst)
            v_day = ai_verdict("daytraderem szukającym momentum", ticker_input, raport_tekst)
            v_long = ai_verdict("analitykiem długoterminowym", ticker_input, raport_tekst)

            # --- PANEL KAFELKÓW (HEATMAP DIAGNOSTYCZNA) ---
            st.subheader("📊 Rozszerzona Diagnostyka Sygnałów Giełdowych")
            st.markdown(f"""
            <div class="heatmap-container">
                <div class="heatmap-tile status-{'bull' if zmiana_proc >= 0 else 'bear'}"><div>CENA</div><div>{cena:.4f} ({zmiana_proc:+.2f}%)</div></div>
                <div class="heatmap-tile status-{rsi_stat}"><div>RSI (14)</div><div>{last['RSI14']:.1f}</div></div>
                <div class="heatmap-tile status-{stoch_stat}"><div>STOCH RSI</div><div>{last['StochRSI_K']:.1f}</div></div>
                <div class="heatmap-tile status-{vwap_stat}"><div>VWAP</div><div>{ 'Nad VWAP' if vwap_stat=='bull' else 'Pod VWAP' }</div></div>
                <div class="heatmap-tile status-{obv_stat}"><div>OBV (KAPITAŁ)</div><div>{ 'Napływ' if obv_stat=='bull' else 'Odpływ' }</div></div>
                <div class="heatmap-tile status-{vol_stat}"><div>WOLUMEN</div><div>{vol_ratio:.1f}x</div></div>
                <div class="heatmap-tile status-{bb_stat}"><div>BOLLINGER</div><div>{ 'Góra' if bb_stat=='bear' else ('Dół' if bb_stat=='bull' else 'Środek') }</div></div>
                <div class="heatmap-tile status-{candle_stat}"><div>ŚWIECA</div><div>{last['Candle_Analysis'].replace(' (Niezdecydowanie)', '').replace(' (Popyt)', '').replace(' (Podaż)', '')}</div></div>
                <div class="heatmap-tile status-{'bear' if risk_score > 60 else 'bull'}"><div>RYZYKO (AI)</div><div>{risk_score}/100</div></div>
                <div class="heatmap-tile status-{'bull' if opp_score > 60 else 'side'}"><div>SZANSA (AI)</div><div>{opp_score}/100</div></div>
            </div>
            """, unsafe_allow_html=True)

            # --- SIZATKA POZIOMÓW FIBONACCIEGO ---
            st.subheader("📐 Kluczowe Zniesienia Fibonacciego")
            f_cols = st.columns(6)
            for idx, (lvl, val) in enumerate(fibo_data.items()):
                f_cols[idx].metric(label=lvl, value=f"{val:.4f}")

            # --- STRATEGIE I OPISY 3× AI ---
            st.subheader("🤖 Decyzje i Strategie 3× AI (Sugerowane ST / TP)")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"### ⚡ SWING TRADER — **{v_swing}**")
                st.markdown(f'<div class="box swing">{ai_swing(ticker_input, raport_tekst)}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f"### ⏱️ DAY TRADER — **{v_day}**")
                st.markdown(f'<div class="box day">{ai_day(ticker_input, raport_tekst)}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f"### 💎 LONG TERM — **{v_long}**")
                st.markdown(f'<div class="box long">{ai_long(ticker_input, raport_tekst)}</div>', unsafe_allow_html=True)

            # --- INTERAKTYWNY WYKRES PLOTLY ---
            st.subheader("📈 Wykres Świecowy i Panele Techniczne")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # Panel Główny: Świece, Bollinger, EMA9 i VWAP
            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Świece'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA9'], line=dict(color='#ec4899', width=1.5), name='EMA 9'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], line=dict(color='#10b981', width=1.5, dash='dash'), name='VWAP'), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173,216,230,0.4)', width=1), name='BB Góra'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173,216,230,0.4)', width=1), fill='tonexty', fillcolor='rgba(173,216,230,0.02)', name='BB Dół'), row=1, col=1)
            
            # Linie Fibo
            for lvl, val in fibo_data.items():
                fig.add_hline(y=val, line_dash="dot", line_color="#f59e0b", line_width=1, annotation_text=lvl, row=1, col=1)
                
            # Panel Dolny: Wolumen obrotu
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Wolumen', marker_color='#475569'), row=2, col=1)
            
            fig.update_layout(
                template="plotly_dark", paper_bgcolor="#020617", plot_bgcolor="#020617",
                xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), height=550
            )
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("System gotowy do pracy. Wprowadź ticker giełdowy (np. `TNON` dla USA lub `BML.WA` dla GPW), aby uruchomić pełną machinerię analityczną.")
