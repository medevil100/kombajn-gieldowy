# ================== konfig ==================
st.set_page_config(page_title="3× ai — terminal groszówek", layout="wide")

# Opcja awaryjna: Wklej swój klucz bezpośrednio tutaj, jeśli st.secrets nie działa lokalnie
MOJ_KLUCZ_AWARYJNY = "sk-proj-TUTAJ_WKLEJ_SWÓJ_PRAWDZIWY_KLUCZ"

if "openai_api_key" in st.secrets:
    client = OpenAI(api_key=st.secrets["openai_api_key"])
elif MOJ_KLUCZ_AWARYJNY != "sk-proj-TUTAJ_WKLEJ_SWÓJ_PRAWDZIWY_KLUCZ":
    client = OpenAI(api_key=MOJ_KLUCZ_AWARYJNY)
else:
    st.error("brak klucza openai_api_key! Wklej go w kodzie w zmiennej MOJ_KLUCZ_AWARYJNY lub dodaj do secrets.toml")
    st.stop()

    st.stop()

# ================== STYLE CSS ==================
st.markdown("""
<style>
body { background-color: #020617; color: #e5e7eb; font-family: system-ui, sans-serif; }
.metric-container { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.metric-card { width: 180px; padding: 12px; border-radius: 8px; color: white; font-size: 13px; font-weight: bold; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
.status-bull { background-color: #15803d; border: 2px solid #22c55e; }
.status-side { background-color: #a16207; border: 2px solid #eab308; }
.status-bear { background-color: #b91c1c; border: 2px solid #ef4444; }
.ai-box { padding: 15px; border-radius: 10px; margin-top: 10px; color: white; min-height: 150px; font-size: 14px; line-height: 1.5; }
.ai-swing { background-color: #064e3b; border-left: 5px solid #10b981; }
.ai-day { background-color: #1e3a8a; border-left: 5px solid #3b82f6; }
.ai-long { background-color: #4c1d95; border-left: 5px solid #8b5cf6; }
.fibo-container { background-color: #1e293b; padding: 15px; border-radius: 10px; margin-top: 15px; border: 1px solid #475569; }
h3 { margin-bottom: 5px; }
</style>
""", unsafe_allow_html=True)

st.title("📈 3× AI — Zaawansowany Terminal Groszówek")

# ================== SILNIK ANALIZY TECHNICZNEJ ==================
def get_advanced_data(ticker: str, interval: str):
    try:
        stock = yf.Ticker(ticker)
        # 1h wymaga max 60 dni wstecz w yfinance, 1d pobieramy z 6 miesięcy
        period = "60d" if interval == "1h" else "6mo"
        df = stock.history(period=period, interval=interval)
        
        if df.empty or len(df) < 20:
            return None, "Za mało danych historycznych do obliczenia wskaźników."
        
        # 1. Klasyczne wskaźniki (RSI, MACD)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Vol_Avg10'] = df['Volume'].rolling(window=10).mean()
        
        # 2. Wstęgi Bollingera (20, 2)
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        df['BB_Std'] = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
        df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * 2)
        
        # 3. ATR (14) - Zmienność w ujęciu bezwzględnym
        high_low = df['High'] - df['Low']
        high_cp = (df['High'] - df['Close'].shift()).abs()
        low_cp = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(window=14).mean()
        
        # 4. Formacje Świecowe (Prosta analiza OCHL z ostatniej świecy)
        last_s = df.iloc[-1]
        body = abs(last_s['Close'] - last_s['Open'])
        candle_range = last_s['High'] - last_s['Low'] if (last_s['High'] - last_s['Low']) > 0 else 0.0001
        
        upper_shadow = last_s['High'] - max(last_s['Open'], last_s['Close'])
        lower_shadow = min(last_s['Open'], last_s['Close']) - last_s['Low']
        
        candle_type = "Neutralna"
        if body / candle_range < 0.2:
            candle_type = "Doji (Niezdecydowanie rynku)"
        elif lower_shadow / candle_range > 0.6:
            candle_type = "Młot / Pinbar (Sygnał popytowy)"
        elif upper_shadow / candle_range > 0.6:
            candle_type = "Spadająca Gwiazda (Sygnał podażowy)"
        elif last_s['Close'] > last_s['Open'] and body / candle_range > 0.7:
            candle_type = "Silna Świeca Marubozu Popytowa"
        elif last_s['Close'] < last_s['Open'] and body / candle_range > 0.7:
            candle_type = "Silna Świeca Marubozu Podażowa"
            
        df['Candle_Analysis'] = candle_type
        
        # 5. Zniesienia Fibonacciego (Na podstawie ekstremów z całego okresu)
        max_p = df['High'].max()
        min_p = df['Low'].min()
        diff = max_p - min_p
        
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

def render_metric(title: str, value: str, status: str):
    return f"""
    <div class="metric-card status-{status}">
        <div style="font-size: 11px; opacity: 0.8; text-transform: uppercase;">{title}</div>
        <div style="font-size: 16px; margin-top: 5px;">{value}</div>
    </div>
    """

# ================== AGENT AI ==================
def ask_ai(role_prompt: str, ticker: str, data_summary: str) -> str:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": role_prompt},
                {"role": "user", "content": f"Spółka: {ticker}\nKompletny zestaw danych rynkowych:\n{data_summary}\n\nWyznacz bezwzględną strategię wejścia, wyjścia, poziomy stop-loss (ST) i take-profit (TP)."}
            ]
        )
        return r.choices.message.content
    except Exception as e:
        return f"Błąd AI: {str(e)}"

# ================== PANEL KONTROLNY UŻYTKOWNIKA ==================
col_inp1, col_inp2 = st.columns([2, 1])
with col_inp1:
    ticker_input = st.text_input("Wpisz Ticker ręcznie (np. BML.WA dla GPW lub TNON dla USA):", value="").upper().strip()
with col_inp2:
    interval_input = st.selectbox("Wybierz interwał czasowy wykresu:", options=["1h", "1d"], index=1)

if ticker_input:
    with st.spinner(f"Analiza techniczo-algorytmiczna dla {ticker_input} ({interval_input})..."):
        df, fibo_or_err = get_advanced_data(ticker_input, interval_input)
        
        if df is None:
            st.error(f"Problem z pobraniem danych: {fibo_or_err}")
        else:
            fibo = fibo_or_err
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            
            cena = last_row['Close']
            zmiana_proc = ((cena - prev_row['Close']) / prev_row['Close']) * 100
            
            # --- LOGIKA KOLORÓW DLA NOWYCH WSKAŹNIKÓW ---
            # Bollinger Bands
            bb_upper = last_row['BB_Upper']
            bb_lower = last_row['BB_Lower']
            if cena >= bb_upper * 0.98: bb_stat = "bear"   # Wykupienie, blisko górnej wstęgi
            elif cena <= bb_lower * 1.02: bb_stat = "bull" # Wyprzedanie, blisko dolnej wstęgi
            else: bb_stat = "side"
            
            # RSI
            rsi_val = last_row['RSI']
            rsi_stat = "side"
            if rsi_val < 32: rsi_stat = "bull"
            elif rsi_val > 68: rsi_stat = "bear"
            
            # Wolumen
            vol_ratio = last_row['Volume'] / last_row['Vol_Avg10'] if last_row['Vol_Avg10'] > 0 else 1
            vol_stat = "bull" if vol_ratio > 1.8 else ("bear" if vol_ratio < 0.4 else "side")
            
            # Świeca
            candle_name = last_row['Candle_Analysis']
            candle_stat = "bull" if "popyt" in candle_name.lower() or "młot" in candle_name.lower() else ("bear" if "podaż" in candle_name.lower() or "gwiazda" in candle_name.lower() else "side")

            # --- WYŚWIETLENIE KAFELKÓW STANÓW ---
            st.subheader("📊 Diagnostyka Sygnałów Rynkowych")
            metrics_html = f"""
            <div class="heatmap-container" style="display: flex; flex-wrap: wrap; gap: 10px;">
                {render_metric("Cena Zamknięcia", f"{cena:.4f}", "bull" if zmiana_proc >= 0 else "bear")}
                {render_metric("Zmiana %", f"{zmiana_proc:+.2f}%", "bull" if zmiana_proc >= 0 else "bear")}
                {render_metric("RSI (14)", f"{rsi_val:.1f}" if not pd.isna(rsi_val) else "Brak", rsi_stat)}
                {render_metric("Wstęgi Bollingera", "Ekstremum Górne" if bb_stat=="bear" else ("Ekstremum Dolne" if bb_stat=="bull" else "Wstęgi Środek"), bb_stat)}
                {render_metric("ATR (Zmienność)", f"{last_row['ATR']:.4f}" if not pd.isna(last_row['ATR']) else "Brak", "side")}
                {render_metric("Skok Wolumenu", f"{vol_ratio:.1f}x normy", vol_stat)}
                {render_metric("Analiza Świecy", candle_name.split(' (')[0], candle_stat)}
            </div>
            """
            st.markdown(metrics_html, unsafe_allow_html=True)

            # --- POZIOMY FIBONACCIEGO ---
            st.subheader("📐 Wyznaczone Poziomy Zniesień Fibonacciego (Cały Zakres)")
            fibo_cols = st.columns(6)
            for i, (level, val) in enumerate(fibo.items()):
                with fibo_cols[i]:
                    # Kolorowanie najbliższych wsparć lub oporów
                    st.metric(label=level, value=f"{val:.4f}")

            # --- PRZYGOTOWANIE RAPORTU TEKSTOWEGO DLA MODELI AI ---
            fibo_summary = ", ".join([f"{k}: {v:.4f}" for k, v in fibo.items()])
            raport_tekst = f"""
            - Interwał danych: {interval_input}
            - Aktualna Cena: {cena:.4f} (Zmiana sesji: {zmiana_proc:+.2f}%)
            - Geometria Fibo: {fibo_summary}
            - Formacja świecy (ostatni słupek): {candle_name}
            - RSI(14): {rsi_val:.1f}
            - Wstęgi Bollingera: Góra={bb_upper:.4f}, Środek={last_row['BB_Mid']:.4f}, Dół={bb_lower:.4f}
            - Średni zasięg ruchu ATR(14): {last_row['ATR']:.4f}
            - Aktywność wolumenu: {vol_ratio:.1f}x powyżej średniej z 10 barów.
            """

            # --- GENEROWANIE ANALIZY PRZEZ 3 AGENTÓW AI ---
            st.subheader(f"🤖 Rezultat Konsultacji Strategicznych 3× AI")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("### ⚡ AGRESYWNY SWING TRADER")
                p1 = "Jesteś agresywnym swing traderem szukającym gwałtownych pomp i breakoutów. Wykorzystaj geometrię poziomów Fibonacci oraz dotknięcia Wstęg Bollingera do podania precyzyjnych, agresywnych poziomów ST i TP."
                st.markdown(f'<div class="ai-box ai-swing">{ask_ai(p1, ticker_input, raport_tekst)}</div>', unsafe_allow_html=True)
                
            with col2:
                st.markdown("### ⏱️ SCALPER / DAY TRADER")
                p2 = "Jesteś precyzyjnym day traderem. Interesuje Cię wyłącznie analiza ostatniej świecy rynkowej (jej kształt i wolumen) oraz zmienność mierzona wskaźnikiem ATR. Podaj bardzo ciasne, matematyczne poziomy docelowe na najbliższe godziny."
                st.markdown(f'<div class="ai-box ai-day">{ask_ai(p2, ticker_input, raport_tekst)}</div>', unsafe_allow_html=True)
                
            with col3:
                st.markdown("### 💎 LONG-TERM SPECULATOR")
                p3 = "Jesteś długoterminowym spekulantem. Szukasz wejścia blisko długoterminowych zniesień Fibo (0.0%, 23.6%, 38.2%) jako bazy pod głębokie odwrócenie trendu. Wyznacz szerokie poziomy obronne i docelowe z perspektywą tygodniową."
                st.markdown(f'<div class="ai-box ai-long">{ask_ai(p3, ticker_input, raport_tekst)}</div>', unsafe_allow_html=True)

            # --- ZAAWANSOWANY WYKRES PLOTLY ---
            st.subheader("📈 Interaktywny Wykres Techniczny")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # Świece japońskie (OHLC)
            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name='Cena (OHLC)'
            ), row=1, col=1)
            
            # Wstęgi Bollingera na wykresie ceny
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173, 216, 230, 0.5)', width=1), name='BB Upper'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173, 216, 230, 0.5)', width=1), fill='tonexty', fillcolor='rgba(173, 216, 230, 0.05)', name='BB Lower'), row=1, col=1)
            
            # Poziomy Fibonacciego jako poziome linie
            for level, val in fibo.items():
                fig.add_hline(y=val, line_dash="dot", line_color="orange", line_width=1, annotation_text=level, row=1, col=1)
            
            # Wolumen obrotu na dolnym panelu
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Wolumen', marker_color='#475569'), row=2, col=1)
            
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#020617",
                plot_bgcolor="#020617",
                xaxis_rangeslider_visible=False,
                margin=dict(l=10, r=10, t=10, b=10),
                height=550,
                showlegend=True
            )
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Terminal gotowy. Wpisz ticker giełdowy w polu powyżej (np. `TNON` lub `ALE.WA`), aby rozpocząć pobieranie danych i analizę 3× AI.")
