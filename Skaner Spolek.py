
import streamlit as st
from openai import OpenAI
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================== KONFIG ==================
st.set_page_config(page_title="3× AI — Multi-Skaner Groszówek", layout="wide")

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
.box { padding: 12px; border-radius: 8px; font-size: 13px; margin-top: 10px; color: white; line-height: 1.4; }
.swing  { background-color: #064e3b; border-left: 5px solid #10b981; }
.day    { background-color: #1e3a8a; border-left: 5px solid #3b82f6; }
.long   { background-color: #4c1d95; border-left: 5px solid #8b5cf6; }
</style>
""", unsafe_allow_html=True)

st.title("📊 3× AI — Multi-Skaner i Ranking Groszówek (PL + USA)")

# ================== SILNIK ANALIZY TECHNICZNEJ ==================
def calculate_indicators(ticker: str, interval: str):
    try:
        stock = yf.Ticker(ticker)
        period = "730d" if interval == "1h" else "1y"
        df = stock.history(period=period, interval=interval)
        
        if df.empty or len(df) < 15:
            return None, None
        
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
        if body / candle_range < 0.2:
            candle_type = "Doji"
        elif lower_shadow / candle_range > 0.6:
            candle_type = "Młot"
        elif upper_shadow / candle_range > 0.6:
            candle_type = "Spadająca Gwiazda"
        df['Candle_Analysis'] = candle_type
        
        # 10. Geometria Fibonacciego
        max_p = df['High'].max()
        min_p = df['Low'].min()
        diff = max_p - min_p if (max_p - min_p) > 0 else 0.0001
        fibo = {
            "100.0%": max_p,
            "61.8%": max_p - 0.382 * diff,
            "50.0%": max_p - 0.5 * diff,
            "38.2%": max_p - 0.618 * diff,
            "23.6%": max_p - 0.764 * diff,
            "0.0%": min_p
        }
        
        return df, fibo
    except Exception:
        return None, None

# ================== SILNIK MASOWYCH ZAPYTAŃ AI (3× STRATEGIE) ==================
def ask_ai_batch(ticker: str, text: str):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[{
                "role": "user",
                "content": (
                    f"Przeanalizuj groszówkę {ticker} na podstawie tych danych technicznych:\n{text}\n\n"
                    "Zwróć odpowiedź dokładnie w poniższym formacie (użyj znaczników [STRATEGIA]):\n"
                    "[SWING] Werdykt (KUP/CZEKAJ/SPRZEDAJ) oraz 2 krótkie zdania strategii z poziomami ST i TP.\n"
                    "[DAY] Werdykt (KUP/CZEKAJ/SPRZEDAJ) oraz 2 krótkie zdania na bazie świec i VWAP z poziomami ST i TP.\n"
                    "[LONG] Werdykt (KUP/CZEKAJ/SPRZEDAJ) oraz 2 krótkie zdania na bazie OBV i Fibo z poziomami ST i TP."
                )
            }],
        )
        res = r.choices[0].message.content.strip()
        
        swing_part = res.split("[DAY]")[0].replace("[SWING]", "").strip()
        if "[DAY]" in res:
            day_block = res.split("[DAY]")[1]
            day_part = day_block.split("[LONG]")[0].strip() if "[LONG]" in day_block else day_block.strip()
        else:
            day_part = "CZEKAJ — brak danych"
        long_part = res.split("[LONG]")[1].strip() if "[LONG]" in res else "CZEKAJ — brak danych"
        
        v_swing = "KUP" if "KUP" in swing_part[:25].upper() else ("SPRZEDAJ" if "SPRZED" in swing_part[:25].upper() else "CZEKAJ")
        v_day = "KUP" if "KUP" in day_part[:25].upper() else ("SPRZEDAJ" if "SPRZED" in day_part[:25].upper() else "CZEKAJ")
        v_long = "KUP" if "KUP" in long_part[:25].upper() else ("SPRZEDAJ" if "SPRZED" in long_part[:25].upper() else "CZEKAJ")
        
        return {
            "swing_txt": swing_part, "day_txt": day_part, "long_txt": long_part,
            "v_swing": v_swing, "v_day": v_day, "v_long": v_long
        }
    except Exception as e:
        err_msg = f"Błąd analizy AI: {str(e)}"
        return {
            "swing_txt": err_msg,
            "day_txt": err_msg,
            "long_txt": err_msg,
            "v_swing": "CZEKAJ",
            "v_day": "CZEKAJ",
            "v_long": "CZEKAJ"
        }

# ================== AI MARKET REGIME DETECTOR ==================
def ai_market_regime(summary_text: str):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.25,
            messages=[{
                "role": "user",
                "content": (
                    "Jesteś analitykiem rynku groszówek. "
                    "Na podstawie poniższego zbiorczego raportu z wielu spółek oceń:\n"
                    "- sentyment rynku (BULL / NEUTRAL / BEAR)\n"
                    "- poziom ryzyka systemowego (0–100)\n"
                    "- poziom spekulacji (0–100)\n"
                    "- czy rynek jest w fazie: ACCUMULATION / DISTRIBUTION / EXPLOSION / PANIC\n"
                    "- krótka rekomendacja stylu gry (agresywny / defensywny / neutralny)\n\n"
                    f"Raport:\n{summary_text}\n\n"
                    "Zwróć odpowiedź w formacie:\n"
                    "[SENTYMENT] ...\n"
                    "[RYZYKO] ...\n"
                    "[SPEKULACJA] ...\n"
                    "[FAZA] ...\n"
                    "[REKOMENDACJA] ..."
                )
            }]
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI-MRD: {e}"

# ================== AI PATTERN DETECTOR ==================
def ai_pattern_detector(ticker: str, text: str):
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.35,
            messages=[{
                "role": "user",
                "content": (
                    f"Analizujesz spółkę {ticker}. Dane techniczne:\n{text}\n\n"
                    "Wykryj formacje:\n"
                    "- świecowe (np. młot, objęcie, harami, pinbar)\n"
                    "- wolumenowe (climax, dry-up, breakout)\n"
                    "- trendowe (kanał, wybicie, odwrócenie)\n"
                    "- anomalie (short squeeze setup, liquidity trap, exhaustion)\n\n"
                    "Zwróć odpowiedź w formacie:\n"
                    "[FORMACJE] ...\n"
                    "[ANOMALIE] ...\n"
                    "[OCENA] (0–100 siła sygnału)"
                )
            }]
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI-PD: {e}"

# ================== DODATKOWE 3× AI: RISK / OPPORTUNITY / SIGNAL ==================
def ai_risk_score(text: str) -> int:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": (
                    "Oceń poziom ryzyka inwestycyjnego w skali 0–100. "
                    "0 = brak ryzyka, 100 = ekstremalne ryzyko spekulacyjne. "
                    f"Dane: {text}. Zwróć tylko liczbę."
                )
            }],
        )
        raw = r.choices[0].message.content
        digits = "".join(c for c in raw if c.isdigit())
        return max(0, min(100, int(digits))) if digits else 50
    except Exception:
        return 50


def ai_opportunity_score(text: str) -> int:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": (
                    "Oceń potencjał spekulacyjny (szansa na ciekawy ruch) w skali 0–100. "
                    "0 = brak sensu, 100 = ogromny potencjał. "
                    f"Dane: {text}. Zwróć tylko liczbę."
                )
            }],
        )
        raw = r.choices[0].message.content
        digits = "".join(c for c in raw if c.isdigit())
        return max(0, min(100, int(digits))) if digits else 50
    except Exception:
        return 50


def ai_signal(text: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": (
                    f"Na podstawie tych danych: {text}. "
                    "Zwróć jeden sygnał: BUY, WATCH lub AVOID. Bez komentarza."
                )
            }],
        )
        out = r.choices[0].message.content.upper()
        if "BUY" in out:
            return "BUY"
        if "AVOID" in out:
            return "AVOID"
        return "WATCH"
    except Exception:
        return "WATCH"

# ================== INTERFEJS UŻYTKOWNIKA ==================
col_in1, col_in2 = st.columns([3, 1])
with col_in1:
    tickers_input = st.text_input(
        "Wklej listę Tickerów rozdzielonych przecinkami (np. TNON, BML.WA, GRN.WA, BCX.WA):", 
        value="TNON, BML.WA"
    )
with col_in2:
    interval_input = st.selectbox("Interwał świecy:", options=["1h", "1d"], index=1)

if "calculated_dfs" not in st.session_state:
    st.session_state.calculated_dfs = {}
if "calculated_fibos" not in st.session_state:
    st.session_state.calculated_fibos = {}

if tickers_input:
    ticker_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    
    if st.button("🚀 URUCHOM MASOWY SKANER I RANKING"):
        ranking_data = []
        st.session_state.calculated_dfs = {}
        st.session_state.calculated_fibos = {}
        
        progress_bar = st.progress(0)
        
        for idx, t in enumerate(ticker_list):
            st.write(f"🔍 Przetwarzanie i analiza techniczna: **{t}**...")
            df, fibo_data = calculate_indicators(t, interval_input)
            
            if df is not None:
                st.session_state.calculated_dfs[t] = df
                st.session_state.calculated_fibos[t] = fibo_data
                
                last = df.iloc[-1]
                prev = df.iloc[-2]
                cena = last['Close']
                zmiana_proc = ((cena - prev['Close']) / prev['Close']) * 100
                vol_ratio = last['Volume'] / last['Vol_Avg10'] if last['Vol_Avg10'] > 0 else 1
                
                fibo_summary = ", ".join([f"{k}: {v:.4f}" for k, v in fibo_data.items()])
                raport_tekst = (
                    f"Cena: {cena:.4f}, Zmiana: {zmiana_proc:+.2f}%, RSI14: {last['RSI14']:.1f}, "
                    f"StochRSI_K: {last['StochRSI_K']:.1f}, VWAP: {last['VWAP']:.4f}, "
                    f"OBV_Slope: {last['OBV_Slope']:.0f}, EMA9: {last['EMA9']:.4f}, "
                    f"SMA50: {last['SMA50']:.4f}, SMA200: {last['SMA200']:.4f}, "
                    f"ATR: {last['ATR']:.4f}, Wolumen: {vol_ratio:.1f}x normy, "
                    f"Świeca: {last['Candle_Analysis']}, Fibo: {fibo_summary}, "
                    f"Bollinger: Góra={last['BB_Upper']:.4f}, Dół={last['BB_Lower']:.4f}"
                )
                
                ai_res = ask_ai_batch(t, raport_tekst)
                risk = ai_risk_score(raport_tekst)
                opp = ai_opportunity_score(raport_tekst)
                sig = ai_signal(raport_tekst)
                
                ranking_data.append({
                    "Ticker": t,
                    "Cena": f"{cena:.4f}",
                    "Zmiana %": round(zmiana_proc, 2),
                    "Skok Wolumenu": round(vol_ratio, 2),
                    "RSI (14)": round(last['RSI14'], 1),
                    "Świeca": last['Candle_Analysis'],
                    "SWING STRATEGIA": ai_res["v_swing"],
                    "DAY STRATEGIA": ai_res["v_day"],
                    "LONG STRATEGIA": ai_res["v_long"],
                    "RISK": risk,
                    "OPPORTUNITY": opp,
                    "SIGNAL": sig,
                    "swing_txt": ai_res["swing_txt"],
                    "day_txt": ai_res["day_txt"],
                    "long_txt": ai_res["long_txt"],
                    "raport_tekst": raport_tekst
                })
            else:
                st.warning(f"⚠️ Pominięto {t} — brak danych w yfinance lub zbyt niska płynność.")
                
            progress_bar.progress((idx + 1) / len(ticker_list))
            
        if ranking_data:
            df_ranking = pd.DataFrame(ranking_data)
            df_ranking = df_ranking.sort_values(by="Skok Wolumenu", ascending=False).reset_index(drop=True)
            st.session_state.df_ranking = df_ranking
            st.success("Skanowanie zakończone sukcesem!")
            
    if "df_ranking" in st.session_state and not st.session_state.df_ranking.empty:
        st.subheader("🏆 Główny Ranking Groszówek (Sortowanie: Skok Wolumenu)")
        
        # === AI MARKET REGIME DETECTOR ===
        st.subheader("🌐 AI Market Regime — Ocena całego rynku groszówek")
        market_summary = "\n".join([
            f"{row['Ticker']}: zmiana {row['Zmiana %']}%, wolumen x{row['Skok Wolumenu']}, RSI {row['RSI (14)']}"
            for _, row in st.session_state.df_ranking.iterrows()
        ])
        mrd = ai_market_regime(market_summary)
        st.markdown(f"<div class='box long'>{mrd}</div>", unsafe_allow_html=True)
        
        st.subheader("🤖 3× AI — Werdykty + Risk/Opportunity/Signal")
        display_cols = [
            "Ticker", "Cena", "Zmiana %", "Skok Wolumenu",
            "RSI (14)", "Świeca",
            "SWING STRATEGIA", "DAY STRATEGIA", "LONG STRATEGIA",
            "RISK", "OPPORTUNITY", "SIGNAL"
        ]
        st.dataframe(st.session_state.df_ranking[display_cols], use_container_width=True)
        
        st.markdown("<hr>", unsafe_allow_html=True)
        st.subheader("🔍 Szczegółowy Profil i Analiza Wybranej Spółki z Rankingu")
        
        selected_ticker = st.selectbox(
            "Wybierz spółkę, aby załadować jej pełne opisy AI oraz wykres techniczny:", 
            options=st.session_state.df_ranking["Ticker"].tolist()
        )
        
        if selected_ticker:
            row = st.session_state.df_ranking[st.session_state.df_ranking["Ticker"] == selected_ticker].iloc[0]
            
            st.markdown(f"### 🤖 Raport Strategiczny dla **{selected_ticker}**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("### ⚡ SWING TRADER")
                st.markdown(f'<div class="box swing">{row["swing_txt"]}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown("### ⏱️ DAY TRADER")
                st.markdown(f'<div class="box day">{row["day_txt"]}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown("### 💎 LONG TERM")
                st.markdown(f'<div class="box long">{row["long_txt"]}</div>', unsafe_allow_html=True)
            
            # AI PATTERN DETECTOR dla wybranego waloru
            st.subheader("🧠 AI Pattern Detector — Formacje i anomalie")
            pattern_text = ai_pattern_detector(selected_ticker, row["raport_tekst"])
            st.markdown(f'<div class="box day">{pattern_text}</div>', unsafe_allow_html=True)
            
            if selected_ticker in st.session_state.calculated_dfs:
                df_plot = st.session_state.calculated_dfs[selected_ticker]
                fibo_plot = st.session_state.calculated_fibos[selected_ticker]
                
                st.subheader(f"📈 Wykres Świecowy oraz Geometria dla {selected_ticker} ({interval_input})")
                fig = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.03,
                    row_heights=[0.7, 0.3]
                )
                
                fig.add_trace(go.Candlestick(
                    x=df_plot.index,
                    open=df_plot['Open'],
                    high=df_plot['High'],
                    low=df_plot['Low'],
                    close=df_plot['Close'],
                    name='Świece'
                ), row=1, col=1)
                
                fig.add_trace(go.Scatter(
                    x=df_plot.index,
                    y=df_plot['EMA9'],
                    line=dict(color='#ec4899', width=1.5),
                    name='EMA 9'
                ), row=1, col=1)
                
                fig.add_trace(go.Scatter(
                    x=df_plot.index,
                    y=df_plot['VWAP'],
                    line=dict(color='#10b981', width=1.5, dash='dash'),
                    name='VWAP'
                ), row=1, col=1)
                
                fig.add_trace(go.Scatter(
                    x=df_plot.index,
                    y=df_plot['BB_Upper'],
                    line=dict(color='rgba(173,216,230,0.4)', width=1),
                    name='BB Góra'
                ), row=1, col=1)
                
                fig.add_trace(go.Scatter(
                    x=df_plot.index,
                    y=df_plot['BB_Lower'],
                    line=dict(color='rgba(173,216,230,0.4)', width=1),
                    fill='tonexty',
                    fillcolor='rgba(173,216,230,0.02)',
                    name='BB Dół'
                ), row=1, col=1)
                
                for lvl, val in fibo_plot.items():
                    fig.add_hline(
                        y=val,
                        line_dash="dot",
                        line_color="#f59e0b",
                        line_width=1,
                        annotation_text=lvl,
                        row=1, col=1
                    )
                    
                fig.add_trace(go.Bar(
                    x=df_plot.index,
                    y=df_plot['Volume'],
                    name='Wolumen',
                    marker_color='#475569'
                ), row=2, col=1)
                
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#020617",
                    plot_bgcolor="#020617",
                    xaxis_rangeslider_visible=False,
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=500
                )
                st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Skaner czeka na uruchomienie. Wklej wybrane tickery giełdowe powyżej i naciśnij przycisk, aby wygenerować ranking.")
