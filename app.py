# ============================================================
# 7. LICZENIE WYNIKÓW
# ============================================================

results = []
for t in tickers:
    data = ultra(t)
    if data:
        results.append(data)

if not results:
    st.warning("Brak danych — sprawdź tickery.")
    st.stop()

# ============================================================
# 8. DATAFRAME, TOP10, AI PORTFEL / AI TOP10
# ============================================================

df_res = pd.DataFrame([
    {
        "symbol": r["symbol"],
        "price": r["price"],
        "score": r["score"],
        "signal": r["signal"],
        "rsi": r["rsi"],
        "macd": r["macd"],
        "vol": r["vol"],
    }
    for r in results
])

df_sorted = df_res.sort_values(by=["score", "macd"], ascending=[False, False])
top10_symbols = df_sorted.head(10)["symbol"].tolist()

st.subheader("🧠 AI – portfel i TOP 10")

colp1, colp2 = st.columns([3, 1])

with colp1:
    if client:

        # -----------------------------
        # AI PODSUMOWANIE PORTFELA
        # -----------------------------
        if st.button("🤖 AI podsumowanie portfela"):
            with st.spinner("AI analizuje portfel..."):

                opis = "\n".join(
                    f"{r['symbol']}: cena {r['price']:.2f}, score {r['score']}, RSI {r['rsi']:.1f}, MACD {r['macd']:.2f}"
                    for r in results
                )

                prompt = f"""
Analiza techniczna portfela.

Dane wejściowe:
{opis}

TOP 10 według score + MACD:
{", ".join(top10_symbols)}

Zasady:
- Zero lania wody.
- Zero ogólników.
- Zero porad.
- Zero ostrzeżeń.
- Tylko fakty techniczne.
- Styl: zimny, bezemocjonalny, precyzyjny.

Wygeneruj:
1. Ranking siły trendu w portfelu (od najmocniejszego).
2. 3 najlepsze okazje do wejścia — krótko, konkretnie, dlaczego.
3. 3 najsłabsze pozycje — krótko, konkretnie, dlaczego.
4. Werdykt końcowy — jedno zdanie, bez porad.
"""

                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.05
                )
                st.session_state["ai_portfolio"] = resp.choices[0].message.content

        # -----------------------------
        # AI ANALIZA TOP 10
        # -----------------------------
        if st.button("🤖 AI analiza TOP 10"):
            with st.spinner("AI analizuje TOP 10..."):

                prompt = f"""
Analiza techniczna TOP 10 (score + MACD):

{chr(10).join(top10_symbols)}

Zasady:
- Zero lania wody.
- Zero ogólników.
- Zero porad.
- Zero ostrzeżeń.
- Tylko fakty techniczne.
- Styl: zimny, bezemocjonalny, precyzyjny.

Wygeneruj:
1. Ranking siły trendu.
2. 3 najlepsze okazje do wejścia — krótko i konkretnie.
3. 3 ostrzeżenia (przegrzanie / słabość).
4. Werdykt końcowy — jedno zdanie.
"""

                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.05
                )
                st.session_state["ai_top10"] = resp.choices[0].message.content

    # -----------------------------
    # WYŚWIETLANIE AI
    # -----------------------------
    if st.session_state["ai_portfolio"]:
        st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
        st.write(st.session_state["ai_portfolio"])
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state["ai_top10"]:
        st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
        st.write(st.session_state["ai_top10"])
        st.markdown("</div>", unsafe_allow_html=True)

with colp2:
    st.markdown("### 🏆 TOP 10 (score + MACD)")
    st.dataframe(df_sorted.head(10), use_container_width=True)

st.divider()

# ============================================================
# 9. RADAR WYBIĆ (WOLUMEN RELATYWNY)
# ============================================================

st.subheader("🔥 RADAR WYBIĆ (wolumen relatywny)")

top_vol = df_res.sort_values(by="vol", ascending=False).head(10)

for i in range(0, len(top_vol), 5):
    cols = st.columns(5)
    for j, (_, row) in enumerate(top_vol.iloc[i:i+5].iterrows()):
        with cols[j]:
            r = next(x for x in results if x["symbol"] == row["symbol"])
            st.markdown(f"""
            <div class="top-card">
                <div style="color:#39FF14; font-weight:bold; font-size:1.4rem;">{r['symbol']}</div>
                <div style="font-size:1.6rem; font-weight:bold;">{r['price']:.2f}</div>
                <span class="neon-bid">B: {r['bid']}</span> | <span class="neon-ask">A: {r['ask']}</span><hr>
                <b>TP: <span class="tp-val">{r['tp']:.2f}</span></b><br>
                <b>SL: <span class="sl-val">{r['sl']:.2f}</span></b><hr>
                <b>Score:</b> {r['score']} | <b>RSI:</b> {r['rsi']:.1f}<br>
                <div class="signal-{r['signal']}" style="margin-top:10px; font-size:1rem;">{r['signal']}</div>
            </div>
            """, unsafe_allow_html=True)

st.divider()

# ============================================================
# 10. KAFLE GŁÓWNE – SPÓŁKI + SZCZEGÓŁY PRO + AI PER SPÓŁKA
# ============================================================

st.subheader("📊 Analiza główna – spółki")

for r in results:
    with st.container():
        st.markdown("<div class='mega-card'>", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns([1.8, 1.5, 1.3, 2.4])

        with c1:
            st.markdown(
                f"<div class='neon-title' style='font-size:3rem;'>{r['symbol']}</div>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"<div class='price-tag'>{r['price']:.2f}</div>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"Bid: <span class='neon-bid'>{r['bid']}</span> | "
                f"Ask: <span class='neon-ask'>{r['ask']}</span>",
                unsafe_allow_html=True
            )
            st.write(f"Wolumen relatywny: {r['vol']:.2f}x")

        with c2:
            st.write(f"Score trendu: **{r['score']}**")
            st.write(f"RSI: **{r['rsi']:.1f}**")
            st.write(f"ATR: **{r['atr']:.2f}**")
            st.write(f"Swing High: {r['swing_high']:.2f}")
            st.write(f"Swing Low: {r['swing_low']:.2f}")

        with c3:
            st.markdown(
                f"**TP: <span class='tp-val'>{r['tp']:.2f}</span>**",
                unsafe_allow_html=True
            )
            st.markdown(
                f"**SL: <span class='sl-val'>{r['sl']:.2f}</span>**",
                unsafe_allow_html=True
            )
            st.write(f"Pivot: {r['pivot']:.2f}")
            st.write(f"R1: {r['r1']:.2f}")
            st.write(f"S1: {r['s1']:.2f}")

        with c4:
            st.markdown(
                f"<div class='signal-{r['signal']}'>{r['signal']}</div>",
                unsafe_allow_html=True
            )

            # -----------------------------
            # AI PER SPÓŁKA
            # -----------------------------
            if client and st.button(f"🤖 DIAGNOZA AI – {r['symbol']}", key=f"ai_{r['symbol']}"):
                with st.spinner("AI analizuje tę spółkę..."):

                    prompt = f"""
Analiza techniczna spółki {r['symbol']}:

Cena: {r['price']:.2f}
Score: {r['score']}
RSI: {r['rsi']:.1f}
MACD: {r['macd']:.2f}, sygnał: {r['macd_sig']:.2f}, histogram: {r['macd_hist']:.2f}
ATR: {r['atr']:.2f}
Swing High / Low: {r['swing_high']:.2f} / {r['swing_low']:.2f}
Pivot / R1 / S1: {r['pivot']:.2f} / {r['r1']:.2f} / {r['s1']:.2f}
TP / SL: {r['tp']:.2f} / {r['sl']:.2f}
Formacje świecowe: {r['candle_comment']}

Zasady:
- Zero lania wody.
- Zero ogólników.
- Zero porad.
- Tylko fakty techniczne.
- Styl: zimny, bezemocjonalny, precyzyjny.

Wygeneruj:
1. Ocena wejścia — krótko i konkretnie.
2. Ryzyko — zmienność, poziomy obrony.
3. Werdykt (KUP / TRZYMAJ / SPRZEDAJ) — jedno zdanie uzasadnienia.
"""

                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": "Jesteś bezdusznym modułem analizy technicznej. Zero emocji, zero lania wody."
                            },
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.05
                    )
                    st.session_state["ai_single"][r["symbol"]] = resp.choices[0].message.content

            if r["symbol"] in st.session_state["ai_single"]:
                st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
                st.write(st.session_state["ai_single"][r["symbol"]])
                st.markdown("</div>", unsafe_allow_html=True)

            with st.expander("📊 Szczegóły PRO"):
                st.markdown("<div class='pro-box'>", unsafe_allow_html=True)
                st.write(f"MA20: {r['ma20']:.2f}")
                st.write(f"MA50: {r['ma50']:.2f}")
                st.write(f"MA100: {r['ma100']:.2f}")
                st.write(f"MA200: {r['ma200']:.2f}")
                st.write(f"EMA200: {r['ema200']:.2f}")
                st.write(f"MACD: {r['macd']:.2f}")
                st.write(f"MACD sygnał: {r['macd_sig']:.2f}")
                st.write(f"MACD histogram: {r['macd_hist']:.2f}")
                st.write(f"Formacje świecowe: {r['candle_comment']}")
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
