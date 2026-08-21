# =====================================================================
# WYŚWIETLANIE WYNIKÓW Z KOLOROWANIEM (poprawione .map z dynamicznym subset)
# =====================================================================
if st.session_state.last_scanned_tickers:
    st.subheader("📊 Podgląd aktualnego cyklu skanowania (Posortowany)")

    df_wyniki = pd.DataFrame(st.session_state.last_scanned_tickers)

    # Jeśli brak kolumny "Status", dodaj domyślną
    if "Status" not in df_wyniki.columns:
        df_wyniki["Status"] = "Brak danych"

    # Sortowanie po score (jeśli istnieje)
    if "score" in df_wyniki.columns:
        df_wyniki = df_wyniki.sort_values(by="score", ascending=False)
        df_wyniki = df_wyniki.drop(columns=["score"])

    # Bezpieczne usuwanie kolumn – sprawdzamy, czy istnieją
    for col in ["Sygnał", "_df", "_cena_akt", "_waluta"]:
        if col in df_wyniki.columns:
            df_wyniki = df_wyniki.drop(columns=[col])

    # Skracanie długich tekstów
    if "Analiza AI" in df_wyniki.columns:
        df_wyniki["Analiza AI"] = df_wyniki["Analiza AI"].apply(
            lambda x: x[:150] + "..." if isinstance(x, str) and len(x) > 150 else x
        )

    # Funkcje kolorowania
    def koloruj_zmiane(val):
        try:
            if isinstance(val, (int, float)):
                if val > 0:
                    return 'color: green; font-weight: bold;'
                elif val < 0:
                    return 'color: red; font-weight: bold;'
            return ''
        except:
            return ''

    def koloruj_wolumen(val):
        try:
            if isinstance(val, str) and 'x' in val:
                liczba = float(val.replace('x', '').strip())
                if liczba >= 3:
                    return 'background-color: #d4edda;'
                elif liczba >= 1.5:
                    return 'background-color: #fff3cd;'
                else:
                    return 'background-color: #f8d7da;'
            return ''
        except:
            return ''

    def koloruj_rsi(val):
        try:
            if isinstance(val, (int, float)):
                if 30 <= val <= 70:
                    return 'color: green;'
                elif val < 30:
                    return 'color: orange; font-weight: bold;'
                else:
                    return 'color: red; font-weight: bold;'
            return ''
        except:
            return ''

    def koloruj_status(val):
        if isinstance(val, str):
            if 'Kupuj' in val:
                return 'background-color: #d4edda; color: #155724; font-weight: bold;'
            elif 'Trzymaj' in val:
                return 'background-color: #fff3cd; color: #856404;'
            elif 'Unikaj' in val:
                return 'background-color: #f8d7da; color: #721c24;'
            elif '❌' in val or '⛔' in val:
                return 'background-color: #f5c6cb; color: #721c24;'
        return ''

    # Rozpocznij stylizację – tylko dla istniejących kolumn
    styled = df_wyniki.style

    # Stosuj map tylko jeśli kolumna istnieje
    if "Zmiana %" in df_wyniki.columns:
        styled = styled.map(koloruj_zmiane, subset=['Zmiana %'])
    if "Wolumen (x śr.)" in df_wyniki.columns:
        styled = styled.map(koloruj_wolumen, subset=['Wolumen (x śr.)'])
    if "RSI" in df_wyniki.columns:
        styled = styled.map(koloruj_rsi, subset=['RSI'])
    if "Status" in df_wyniki.columns:
        styled = styled.map(koloruj_status, subset=['Status'])

    styled = styled.set_properties(**{'text-align': 'center'}) \
                     .set_table_styles([{'selector': 'thead th', 'props': [('text-align', 'center')]}])

    st.dataframe(styled, use_container_width=True)
