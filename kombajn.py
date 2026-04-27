        # --- 6. NAPRAWIONY KALKULATOR RYZYKA (POSITION SIZING) ---
        tr = pd.concat([
            df['High']-df['Low'], 
            (df['High']-df['Close'].shift()).abs(), 
            (df['Low']-df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]
        
        # Ryzyko kwotowe (np. 1% z 10000 = 100 PLN)
        risk_cash = st.session_state.risk_cap * (st.session_state.risk_pct / 100)
        
        # Stop Loss: Cena - (1.6 * ATR)
        sl_dist = atr * 1.6
        
        if sl_dist > 0:
            # ILOŚĆ AKCJI = Ryzyko Gotówkowe / Dystans do SL
            shares = int(risk_cash / sl_dist)
            
            # Zabezpieczenie: Wartość pozycji nie może przekroczyć całego kapitału
            max_shares_by_cap = int(st.session_state.risk_cap / price)
            if shares > max_shares_by_cap:
                shares = max_shares_by_cap
                
            position_val = shares * price
        else:
            shares, position_val = 0, 0
            
        # 7. Pobieranie Newsów rynkowych
        market_news = []
        try:
            raw_news = ticker.news
            if raw_news:
                for n in raw_news[:2]:
                    market_news.append({
                        "t": n.get('title', '')[:65] + "...", 
                        "l": n.get('link', '#')
                    })
        except Exception:
            pass
        if not market_news:
            market_news = [{"t": "Info rynkowe czasowo niedostępne", "l": "#"}]

        # 8. Logika Decyzyjna (System Expert)
        v_type = "neutral"
        # Warunek KUP: RSI nisko + cena nad SMA200 (trend wzrostowy) lub MACD rośnie
        if rsi < 35 and price < bb_low: 
            verd, vcl, v_type = "KUP 🔥", "sig-buy", "buy"
        elif rsi > 65 or price > bb_up: 
            verd, vcl, v_type = "SPRZEDAJ ⚠️", "sig-sell", "sell"
        else: 
            verd, vcl, v_type = "CZEKAJ ⏳", "sig-neutral", "neutral"

        return {
            "s": s, "p": price, "rsi": rsi, "sma50": sma50, "sma100": sma100, 
            "sma200": sma200, "ema20": ema20, "pivot": pivot, "r1": r1, "s1": s1,
            "macd": curr_macd, "verd": verd, "vcl": vcl, "v_type": v_type, 
            "shares": shares, "sl": price - sl_dist, "tp": price + (atr * 3.8), 
            "news": market_news, "df": df.tail(65), "val": position_val
        }
    except Exception:
        return None

# --- SEKCJA 4: INTERFEJS UŻYTKOWNIKA (SIDEBAR) ---
with st.sidebar:
    st.title("🚜 GOLDEN v62 PRO")
    st.markdown("---")
    
    st.subheader("💰 KONFIGURACJA PORTFELA")
    st.session_state.risk_cap = st.number_input("Twój Kapitał (PLN)", value=st.session_state.risk_cap, step=1000.0)
    st.session_state.risk_pct = st.slider("Ryzyko na pozycję (%)", 0.1, 5.0, st.session_state.risk_pct)
    
    st.subheader("📝 LISTA OBSERWOWANYCH")
    ticker_area = st.text_area("Symbole (BBI, EVOK, BTC-USD...):", value=load_tickers(), height=250)
    
    if st.button("💾 ZAPISZ I ANALIZUJ"):
        with open(DB_FILE, "w") as f:
            f.write(ticker_area)
        st.cache_data.clear()
        st.success("Baza zaktualizowana!")
        st.rerun()
    
    refresh_rate = st.select_slider("Auto-odświeżanie (s)", options=[30, 60, 120, 300], value=60)

st_autorefresh(interval=refresh_rate * 1000, key="v62_fsh_global")

# --- SEKCJA 5: LOGIKA WYŚWIETLANIA ---
tickers_list = [x.strip().upper() for x in ticker_area.replace('\n', ',').split(',') if x.strip()]

@st.cache_data(ttl=refresh_rate)
def fetch_all_data(s_list):
    results = []
    pbar = st.progress(0)
    for i, symbol in enumerate(s_list):
        data = get_analysis(symbol)
        if data:
            results.append(data)
        pbar.progress((i + 1) / len(s_list))
    pbar.empty()
    return results

data_ready = fetch_all_data(tickers_list)

if data_ready:
    # --- TERMINAL TOP 10 ---
    st.subheader("🏆 TOP 10 SIGNAL TERMINAL (RANKING RSI)")
    top_10 = sorted(data_ready, key=lambda x: x['rsi'])[:10]
    t_cols = st.columns(5)
    for idx, d in enumerate(top_10):
        with t_cols[idx % 5]:
            t_cls = "tile-buy" if d['v_type'] == "buy" else "tile-sell" if d['v_type'] == "sell" else ""
            st.markdown(f"""
                <div class="top-mini-tile {t_cls}">
                    <b style="font-size:1.1rem;">{d['s']}</b> | {d['p']:.2f}<br>
                    <small>RSI: {d['rsi']:.0f}</small><br>
                    <span class="{d['vcl']}">{d['verd']}</span>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- KAFELKI GŁÓWNE ---
    for i in range(0, len(data_ready), 5):
        row_cols = st.columns(5)
        for idx, d in enumerate(data_ready[i:i+5]):
            with row_cols[idx]:
                border = "#00ff88" if d['v_type'] == "buy" else "#ff4b4b" if d['v_type'] == "sell" else "#30363d"
                st.markdown(f"""
                <div class="main-card" style="border: 2px solid {border};">
                    <div>
                        <div style="font-size:2rem; font-weight:bold; letter-spacing:-1px;">{d['s']}</div>
                        <div style="color:#58a6ff; font-size:1.3rem; margin-bottom:10px;">{d['p']:.2f} PLN</div>
                        <div style="margin: 15px 0;"><span class="{d['vcl']}">{d['verd']}</span></div>
                    </div>
                    
                    <div class="pos-calc">
                        <span class="pos-label">Ilość do kupna:</span><br>
                        <span class="pos-val">{d['shares']} szt.</span>
                        <small>Wartość: {d['val']:.0f} PLN</small>
                    </div>
                    
                    <div class="tech-grid">
                        <div class="tech-row"><span class="t-label">SMA 200:</span><span class="t-value">{d['sma200']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">SMA 100:</span><span class="t-value">{d['sma100']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">SMA 50:</span><span class="t-value">{d['sma50']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">MACD:</span><span class="t-value">{d['macd']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">PIVOT:</span><span class="t-value">{d['pivot']:.2f}</span></div>
                        <div class="tech-row"><span class="t-label">RSI (14):</span><span class="t-value">{d['rsi']:.0f}</span></div>
                    </div>
                """, unsafe_allow_html=True)
                
                # SEKCJA AI
                if st.button(f"🤖 ANALIZA AI: {d['s']}", key=f"btn_{d['s']}"):
                    if AI_KEY:
                        try:
                            with st.spinner(f"AI Analizuje..."):
                                client = OpenAI(api_key=AI_KEY)
                                prompt = (f"Jesteś analitykiem. Przeanalizuj {d['s']}. Cena {d['p']}, RSI {d['rsi']:.0f}, MACD {d['macd']:.2f}. "
                                          f"Sugerowany SL: {d['sl']:.2f}, Sugerowany TP: {d['tp']:.2f}. Podaj 3 konkretne punkty strategii.")
                                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                                st.session_state.ai_results[d['s']] = resp.choices[0].message.content
                        except: st.error("AI Busy")
                    else: st.warning("Brak klucza w skrytce!")

                if d['s'] in st.session_state.ai_results:
                    st.markdown(f"""<div class="ai-display">{st.session_state.ai_results[d['s']]}</div>""", unsafe_allow_html=True)
                    if st.button("❌ Zamknij", key=f"cls_{d['s']}"):
                        del st.session_state.ai_results[d['s']]
                        st.rerun()

                st.markdown(f"""
                    <div class="news-box">
                        <b>📢 NEWSY:</b>
                        {"".join([f'<a class="news-link" href="{n["l"]}" target="_blank">• {n["t"]}</a>' for n in d['news']])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("🔍 WYKRES"):
                    fig = go.Figure(data=[go.Candlestick(x=d['df'].index, open=d['df']['Open'], high=d['df']['High'], low=d['df']['Low'], close=d['df']['Close'])])
                    fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("❌ Błąd pobierania danych. Sprawdź symbole.")

st.markdown(f"<div style='text-align:center; color:#8b949e; margin-top:50px;'>v62.0 ULTIMATE MAXI | {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
