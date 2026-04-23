# --- SILNIK ANALITYCZNY (Zaktualizowany o Trend i Zmianę Ceny) ---
def get_analysis(symbol):
    try:
        d15 = yf.download(symbol, period="5d", interval="15m", progress=False)
        d1d = yf.download(symbol, period="250d", interval="1d", progress=False)
        if d15.empty: return None
        for df in [d15, d1d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        price = float(d15['Close'].iloc[-1])
        prev_close = float(d1d['Close'].iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100
        
        # Wskaźniki Trendu
        sma200 = d1d['Close'].rolling(200).mean().iloc[-1]
        trend_label = "HOSSA 🚀" if price > sma200 else "BESSA 📉"
        trend_color = "#00ff88" if price > sma200 else "#ff4b4b"
        
        atr = (d1d['High'] - d1d['Low']).rolling(14).mean().iloc[-1]
        
        # RSI
        delta = d15['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = delta.where(delta < 0, 0).abs().rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        
        # Poziomy
        pivot = (d1d['High'].iloc[-2] + d1d['Low'].iloc[-2] + d1d['Close'].iloc[-2]) / 3
        tp = price + (atr * 1.5)
        sl = price - (atr * 1.2)
        
        # Logika Rekomendacji
        if rsi < 32: rec, rec_col = "KUPUJ", "#238636"
        elif rsi > 68: rec, rec_col = "SPRZEDAJ", "#da3633"
        else: rec, rec_col = "CZEKAJ", "#8b949e"

        return {
            "symbol": symbol, "price": price, "change": change_pct, "rsi": rsi, 
            "rec": rec, "rec_col": rec_col, "trend": trend_label, "trend_col": trend_color,
            "pivot": pivot, "tp": tp, "sl": sl, "df": d15
        }
    except: return None

# --- TOP 10 DASHBOARD (Z TRENDEM I CENĄ) ---
st.subheader("📊 MONITORING RYNKU (TOP 10)")
top_cols = st.columns(5)
sorted_top = sorted(data_list, key=lambda x: x['rsi'])[:10]

for i, d in enumerate(sorted_top):
    with top_cols[i % 5]:
        change_col = "#00ff88" if d['change'] >= 0 else "#ff4b4b"
        st.markdown(f"""
            <div class="top-rank-card" style="border-top: 3px solid {d['trend_col']};">
                <b style="font-size:1.2rem;">{d['symbol']}</b><br>
                <span style="color:{change_col}; font-size:1.1rem; font-weight:bold;">{d['price']:.2f}</span> 
                <small style="color:{change_col};">({d['change']:.21f}%)</small><br>
                <div style="margin: 5px 0;">
                    <span class="stat-label">Trend:</span> <b style="color:{d['trend_col']}; font-size:0.8rem;">{d['trend']}</b>
                </div>
                <div class="verdict-badge" style="background:{d['rec_col']}; color:white; padding:2px 6px; border-radius:4px; font-size:0.7rem;">{d['rec']}</div>
                <div style="margin-top:5px;">
                    <span class="stat-label">RSI:</span> <span style="color:#58a6ff">{d['rsi']:.1f}</span> | 
                    <span class="stat-label">P:</span> <span style="color:white">{d['pivot']:.1f}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
