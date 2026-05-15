# ============================================================
#  FUNKCJA RYNKU
# ============================================================

def render_market(tab, market_name):
    with tab:
        st.header(f"Rynek: {market_name}")

        key = market_name.replace(" ", "_")

        if f"{key}_tickers" not in st.session_state:
            st.session_state[f"{key}_tickers"] = []

        if f"{key}_df" not in st.session_state:
            st.session_state[f"{key}_df"] = None

        if f"{key}_spark" not in st.session_state:
            st.session_state[f"{key}_spark"] = {}

        tickers_input = st.text_area(
            "Wpisz swoje tickery (oddzielone przecinkami):",
            value=",".join(st.session_state[f"{key}_tickers"]),
            key=f"{key}_input"
        )

        if st.button("💾 Zapisz listę", key=f"{key}_save"):
            st.session_state[f"{key}_tickers"] = [
                t.strip().upper() for t in tickers_input.split(",") if t.strip()
            ]
            st.success("Zapisano listę tickerów.")

        tickers = st.session_state[f"{key}_tickers"]

        mode = st.selectbox(
            "Tryb analizy:",
            ["Swing", "Day", "Long"],
            key=f"{key}_mode"
        )

        # ============================================================
        #  ANALIZA TECHNICZNA (AI #1)
        # ============================================================

        if st.button("🔍 Analiza techniczna (AI #1)", key=f"{key}_scan"):
            if not tickers:
                st.error("Najpierw dodaj spółki.")
                return

            with st.spinner("Analizuję..."):
                data = download(tickers)

                rows = []
                spark = {}

                for t, df in data.items():
                    if df is None or df.empty:
                        continue
                    if len(df) < 80:
                        continue

                    df = indicators(df, mode).dropna()
                    if df is None or df.empty:
                        continue
                    if len(df) < 5:
                        continue

                    last = df.iloc[-1]

                    trend_state, sigs = compute_signals(df)
                    news_text = news_flags(t)

                    score = 0
                    if "rośnie" in trend_state:
                        score += 2
                    if "spada" in trend_state:
                        score -= 2
                    if any("kupujących" in s for s in sigs):
                        score += 1
                    if any("sprzedających" in s for s in sigs):
                        score -= 1

                    color = "green" if "rośnie" in trend_state else "red" if "spada" in trend_state else "orange"

                    rows.append({
                        "Ticker": t,
                        "Kurs": round(last["Close"], 2),
                        "RSI": round(last["RSI"], 1),
                        "Vol x": round(last["Vol_ratio"], 2),
                        "Trend": trend_state,
                        "Sygnały": " | ".join(sigs),
                        "News": news_text,
                        "AI_score": score,
                        "Kolor": color,
                        "Komentarz AI": "",
                        "Sentiment AI": "",
                        "Fundamental AI": ""
                    })

                    spark[t] = df["Close"].tail(20).reset_index(drop=True)

                if not rows:
                    st.warning("Brak spółek z wystarczającą ilością danych.")
                    st.session_state[f"{key}_df"] = None
                    return

                df_out = pd.DataFrame(rows).sort_values("AI_score", ascending=False)
                st.session_state[f"{key}_df"] = df_out
                st.session_state[f"{key}_spark"] = spark

            play_beep()

        df_out = st.session_state.get(f"{key}_df", None)
        spark = st.session_state.get(f"{key}_spark", {})

        if df_out is not None:

            col_left, col_right = st.columns([1, 1])

            # ---------------- LEFT: TABELA ----------------

            with col_left:
                st.subheader("📊 Wyniki analizy technicznej")

                def highlight(row):
                    if row["Kolor"] == "green":
                        return ["background-color:#0f5132;color:white"] * len(row)
                    if row["Kolor"] == "red":
                        return ["background-color:#8b0000;color:white"] * len(row)
                    return ["background-color:#ff8c00;color:black"] * len(row)

                cols_order = [
                    "Ticker", "Kurs", "RSI", "Vol x", "Trend", "Sygnały", "News",
                    "AI_score", "Kolor",
                    "Komentarz AI", "Sentiment AI", "Fundamental AI"
                ]

                st.dataframe(
                    df_out[cols_order].style.apply(highlight, axis=1),
                    use_container_width=True
                )

                st.subheader("📉 Sparklines")
                cols = st.columns(4)
                for i, t in enumerate(df_out["Ticker"]):
                    with cols[i % 4]:
                        st.caption(t)
                        if t in spark:
                            st.line_chart(spark[t])

            # ---------------- RIGHT: AI + CHECKBOXY ----------------

            with col_right:
                st.subheader("🧠 Wybierz AI")

                ai_choice = st.radio(
                    "Wybierz AI:",
                    ["AI #2 — Komentarz LLM",
                     "AI #3 — Sentiment newsów",
                     "AI #4 — Fundamentalne ryzyka"],
                    key=f"{key}_ai_choice"
                )

                st.subheader("📌 Wybierz spółki do analizy AI")

                selected = []
                for t in df_out["Ticker"]:
                    if st.checkbox(t, key=f"{key}_{t}_chk"):
                        selected.append(t)

                if st.button("💬 Uruchom wybraną AI", key=f"{key}_ai_run"):
                    if not selected:
                        st.warning("Nie wybrano żadnych spółek.")
                    else:
                        with st.spinner("AI pracuje..."):
                            new_rows = []
                            for _, row in df_out.iterrows():
                                if row["Ticker"] in selected:
                                    if ai_choice.startswith("AI #2"):
                                        data_single = download([row["Ticker"]])
                                        df_single = list(data_single.values())[0]

                                        if df_single is None or df_single.empty:
                                            row["Komentarz AI"] = "Brak danych"
                                            new_rows.append(row)
                                            continue

                                        df_single = indicators(df_single, mode).dropna()
                                        if df_single is None or df_single.empty or len(df_single) < 5:
                                            row["Komentarz AI"] = "Za mało danych"
                                            new_rows.append(row)
                                            continue

                                        last = df_single.iloc[-1]
                                        trend_state, sigs = compute_signals(df_single)
                                        comment = ai2_comment(row["Ticker"], last, trend_state, sigs, row["News"])
                                        row["Komentarz AI"] = comment

                                    elif ai_choice.startswith("AI #3"):
                                        comment = ai3_sentiment(row["News"])
                                        row["Sentiment AI"] = comment

                                    else:  # AI #4
                                        comment = ai4_fundamental(row["News"])
                                        row["Fundamental AI"] = comment

                                new_rows.append(row)

                            df_out = pd.DataFrame(new_rows)
                            st.session_state[f"{key}_df"] = df_out

                        st.success("AI zakończyła analizę.")

                        st.dataframe(
                            df_out[cols_order].style.apply(highlight, axis=1),
                            use_container_width=True
                        )

        else:
            st.info("Wpisz tickery, wybierz tryb i uruchom 🔍 Analiza techniczna (AI #1).")

# ============================================================
#  RENDERUJEMY RYNKI
# ============================================================

render_market(tab_gpw, "GPW")
render_market(tab_usa, "USA")
# ============================================================
#  FUNKCJA RYNKU
# ============================================================

def render_market(tab, market_name):
    with tab:
        st.header(f"Rynek: {market_name}")

        key = market_name.replace(" ", "_")

        if f"{key}_tickers" not in st.session_state:
            st.session_state[f"{key}_tickers"] = []

        if f"{key}_df" not in st.session_state:
            st.session_state[f"{key}_df"] = None

        if f"{key}_spark" not in st.session_state:
            st.session_state[f"{key}_spark"] = {}

        tickers_input = st.text_area(
            "Wpisz swoje tickery (oddzielone przecinkami):",
            value=",".join(st.session_state[f"{key}_tickers"]),
            key=f"{key}_input"
        )

        if st.button("💾 Zapisz listę", key=f"{key}_save"):
            st.session_state[f"{key}_tickers"] = [
                t.strip().upper() for t in tickers_input.split(",") if t.strip()
            ]
            st.success("Zapisano listę tickerów.")

        tickers = st.session_state[f"{key}_tickers"]

        mode = st.selectbox(
            "Tryb analizy:",
            ["Swing", "Day", "Long"],
            key=f"{key}_mode"
        )

        # ============================================================
        #  ANALIZA TECHNICZNA (AI #1)
        # ============================================================

        if st.button("🔍 Analiza techniczna (AI #1)", key=f"{key}_scan"):
            if not tickers:
                st.error("Najpierw dodaj spółki.")
                return

            with st.spinner("Analizuję..."):
                data = download(tickers)

                rows = []
                spark = {}

                for t, df in data.items():
                    if df is None or df.empty:
                        continue
                    if len(df) < 80:
                        continue

                    df = indicators(df, mode).dropna()
                    if df is None or df.empty:
                        continue
                    if len(df) < 5:
                        continue

                    last = df.iloc[-1]

                    trend_state, sigs = compute_signals(df)
                    news_text = news_flags(t)

                    score = 0
                    if "rośnie" in trend_state:
                        score += 2
                    if "spada" in trend_state:
                        score -= 2
                    if any("kupujących" in s for s in sigs):
                        score += 1
                    if any("sprzedających" in s for s in sigs):
                        score -= 1

                    color = "green" if "rośnie" in trend_state else "red" if "spada" in trend_state else "orange"

                    rows.append({
                        "Ticker": t,
                        "Kurs": round(last["Close"], 2),
                        "RSI": round(last["RSI"], 1),
                        "Vol x": round(last["Vol_ratio"], 2),
                        "Trend": trend_state,
                        "Sygnały": " | ".join(sigs),
                        "News": news_text,
                        "AI_score": score,
                        "Kolor": color,
                        "Komentarz AI": "",
                        "Sentiment AI": "",
                        "Fundamental AI": ""
                    })

                    spark[t] = df["Close"].tail(20).reset_index(drop=True)

                if not rows:
                    st.warning("Brak spółek z wystarczającą ilością danych.")
                    st.session_state[f"{key}_df"] = None
                    return

                df_out = pd.DataFrame(rows).sort_values("AI_score", ascending=False)
                st.session_state[f"{key}_df"] = df_out
                st.session_state[f"{key}_spark"] = spark

            play_beep()

        df_out = st.session_state.get(f"{key}_df", None)
        spark = st.session_state.get(f"{key}_spark", {})

        if df_out is not None:

            col_left, col_right = st.columns([1, 1])

            # ---------------- LEFT: TABELA ----------------

            with col_left:
                st.subheader("📊 Wyniki analizy technicznej")

                def highlight(row):
                    if row["Kolor"] == "green":
                        return ["background-color:#0f5132;color:white"] * len(row)
                    if row["Kolor"] == "red":
                        return ["background-color:#8b0000;color:white"] * len(row)
                    return ["background-color:#ff8c00;color:black"] * len(row)

                cols_order = [
                    "Ticker", "Kurs", "RSI", "Vol x", "Trend", "Sygnały", "News",
                    "AI_score", "Kolor",
                    "Komentarz AI", "Sentiment AI", "Fundamental AI"
                ]

                st.dataframe(
                    df_out[cols_order].style.apply(highlight, axis=1),
                    use_container_width=True
                )

                st.subheader("📉 Sparklines")
                cols = st.columns(4)
                for i, t in enumerate(df_out["Ticker"]):
                    with cols[i % 4]:
                        st.caption(t)
                        if t in spark:
                            st.line_chart(spark[t])

            # ---------------- RIGHT: AI + CHECKBOXY ----------------

            with col_right:
                st.subheader("🧠 Wybierz AI")

                ai_choice = st.radio(
                    "Wybierz AI:",
                    ["AI #2 — Komentarz LLM",
                     "AI #3 — Sentiment newsów",
                     "AI #4 — Fundamentalne ryzyka"],
                    key=f"{key}_ai_choice"
                )

                st.subheader("📌 Wybierz spółki do analizy AI")

                selected = []
                for t in df_out["Ticker"]:
                    if st.checkbox(t, key=f"{key}_{t}_chk"):
                        selected.append(t)

                if st.button("💬 Uruchom wybraną AI", key=f"{key}_ai_run"):
                    if not selected:
                        st.warning("Nie wybrano żadnych spółek.")
                    else:
                        with st.spinner("AI pracuje..."):
                            new_rows = []
                            for _, row in df_out.iterrows():
                                if row["Ticker"] in selected:
                                    if ai_choice.startswith("AI #2"):
                                        data_single = download([row["Ticker"]])
                                        df_single = list(data_single.values())[0]

                                        if df_single is None or df_single.empty:
                                            row["Komentarz AI"] = "Brak danych"
                                            new_rows.append(row)
                                            continue

                                        df_single = indicators(df_single, mode).dropna()
                                        if df_single is None or df_single.empty or len(df_single) < 5:
                                            row["Komentarz AI"] = "Za mało danych"
                                            new_rows.append(row)
                                            continue

                                        last = df_single.iloc[-1]
                                        trend_state, sigs = compute_signals(df_single)
                                        comment = ai2_comment(row["Ticker"], last, trend_state, sigs, row["News"])
                                        row["Komentarz AI"] = comment

                                    elif ai_choice.startswith("AI #3"):
                                        comment = ai3_sentiment(row["News"])
                                        row["Sentiment AI"] = comment

                                    else:  # AI #4
                                        comment = ai4_fundamental(row["News"])
                                        row["Fundamental AI"] = comment

                                new_rows.append(row)

                            df_out = pd.DataFrame(new_rows)
                            st.session_state[f"{key}_df"] = df_out

                        st.success("AI zakończyła analizę.")

                        st.dataframe(
                            df_out[cols_order].style.apply(highlight, axis=1),
                            use_container_width=True
                        )

        else:
            st.info("Wpisz tickery, wybierz tryb i uruchom 🔍 Analiza techniczna (AI #1).")

# ============================================================
#  RENDERUJEMY RYNKI
# ============================================================

render_market(tab_gpw, "GPW")
render_market(tab_usa, "USA")
