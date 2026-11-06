"""Yahoo daily market history for one issuer, independent of the KI audit log."""
from datetime import datetime, timedelta, timezone

import daily_analogs as yahoo
from technical_events import valid_bar
from tracking_view import number_text, time_text


def market_rows(cache, now=None):
    """Return closed daily sessions within 52 weeks, with the preceding close."""
    from company_history import daily_movement
    now = now or datetime.now(timezone.utc)
    ticker = cache.get('ticker', '')
    if not yahoo.valid_symbol(ticker) or cache.get('version') != yahoo.VERSION:
        return []
    cutoff = (now.astimezone(yahoo.zone(ticker)).date() - timedelta(weeks=52)).isoformat()
    result, previous = [], None
    for bar in sorted(cache.get('rows') or [], key=lambda r: r.get('session', '')):
        end = yahoo.stamp(bar.get('end'))
        if not end or end > now or not valid_bar(bar):
            continue
        day = bar['session']
        if day >= cutoff:
            movement = daily_movement(bar['close'], previous['close'] if previous else None)
            result.append({**bar, 'ticker': ticker, 'currency': cache.get('currency', ''),
                           'daily_movement': movement['direction'], 'movement_label': movement['label'],
                           'previous_session': previous['session'] if previous else None,
                           'previous_close': previous['close'] if previous else None,
                           'split': day in (cache.get('splits') or [])})
        previous = bar
    return result


def cards(rows):
    from company_history import cards_html
    records = []
    for row in rows:
        fields = [('Otwarcie', number_text(row['open'], row['currency'])),
                  ('Maksimum', number_text(row['high'], row['currency'])),
                  ('Minimum', number_text(row['low'], row['currency'])),
                  ('Wolumen', number_text(row['volume'], digits=0)),
                  ('Poprzednia zapisana sesja Yahoo', row['previous_session'] or 'Brak danych'),
                  ('Poprzednie zamknięcie', number_text(row['previous_close'], row['currency'])),
                  ('Źródło', 'Yahoo Finance · świeca dzienna')]
        if row['split']:
            fields.append(('Zmiana kapitałowa', 'Split w tej sesji; zmiana surowej ceny nie jest stopą zwrotu inwestora.'))
        records.append({**row, 'source': 'daily', 'id': row['session'], 'at': row['end'],
                        'state': 'CLOSED', 'category': 'Yahoo · 1 dzień',
                        'title': row['session'] + (' · split' if row['split'] else ''),
                        'summary': 'Zamknięcie ' + number_text(row['close'], row['currency']), 'fields': fields})
    return cards_html(records)


def render(store):
    import pandas as pd
    import plotly.graph_objects as go
    import streamlit as st
    st.subheader('Historia spółki · Yahoo · 52 tygodnie')
    st.caption('Przebieg ceny i dzienne świece wybranej spółki. Dostępność nie zależy od daty dodania do KI.')

    def clear():
        st.session_state['market_history_input'] = ''
        st.session_state.pop('market_history_active', None)
        st.session_state['market_history_page'] = 1

    with st.form('market_history_search'):
        symbol = st.text_input('Ticker spółki', placeholder='Np. HUMA lub STX.WA',
                               key='market_history_input', max_chars=30)
        submitted = st.form_submit_button('Pokaż historię 52 tygodni')
        st.form_submit_button('Wyczyść', on_click=clear)
    if submitted:
        ticker = symbol.strip().upper()
        if not yahoo.valid_symbol(ticker):
            st.warning('Wpisz poprawny ticker, np. HUMA lub STX.WA.')
            return
        st.session_state['market_history_active'] = ticker
        st.session_state['market_history_page'] = 1
    ticker = st.session_state.get('market_history_active')
    if not ticker:
        st.info('Wpisz ticker. Historia zostanie pobrana z Yahoo; nie wymaga zapisów skanera KI.')
        return
    refresh = st.button('Odśwież Yahoo', key='market_history_refresh')
    if submitted or refresh:
        try:
            with st.spinner('Pobieram dzienne dane Yahoo lub odczytuję aktualną kopię…'):
                state = yahoo.refresh(store, ticker)
            if state == 'WAIT':
                st.info('Następne pobranie jest chwilowo odroczone. Poniżej dostępna zapisana historia Yahoo.')
        except Exception as exc:
            st.warning(yahoo.sanitize_cli_diagnostic(str(exc)))
    cache = yahoo.read_cache(store, ticker)
    if cache.get('last_error'):
        st.warning('Ostatnie pobranie nie powiodło się: ' + cache['last_error'])
        st.caption('Kolejna próba najwcześniej: ' + time_text(cache.get('next_attempt_at')))
    now = datetime.now(timezone.utc)
    rows = market_rows(cache, now) if cache.get('ticker') == ticker else []
    if not rows:
        st.info('Brak pobranych poprawnych sesji Yahoo z ostatnich 52 tygodni dla ' + ticker + '.')
        return
    st.caption(ticker + ' · Yahoo Finance · pobrano ' + time_text(cache.get('fetched_at')) +
               ' · ' + str(len(rows)) + ' sesji · ' + rows[0]['session'] + ' → ' + rows[-1]['session'])
    if rows[-1]['session'] < yahoo.last_session(ticker, now):
        st.warning('Brakuje ostatniej zakończonej sesji. Pokazujemy starszą historię Yahoo.')
    st.caption('Zielony: wzrost zamknięcia; czerwony: spadek; żółty: bez zmian względem poprzedniej zapisanej sesji. '
               'Widok obejmuje dostępne poprawne sesje w okresie 52 tygodni; odrzucono rekordów źródłowych: ' +
               str(cache.get('rejected_count', 0)) + '.')
    chart = go.Figure(go.Scatter(x=[r['session'] for r in rows], y=[r['close'] for r in rows],
                                mode='lines', name='Zamknięcie', line={'color': '#60a5fa'}))
    chart.update_layout(height=320, margin=dict(l=8, r=8, t=16, b=8),
                        yaxis_title=cache.get('currency', ''), xaxis_title='Sesja',
                        dragmode=False, hovermode='x unified')
    st.plotly_chart(chart, width="stretch", config={'displayModeBar': False, 'scrollZoom': False})
    st.caption('Surowe ceny Yahoo; wykres i zmiany nie uwzględniają dywidend ani kosztów. '
               'Splity mogą powodować skoki ceny; są oznaczone w kaflach.')
    pages = max(1, (len(rows) + 19) // 20)
    st.session_state['market_history_page'] = max(1, min(int(st.session_state.get('market_history_page', 1)), pages))
    index = st.number_input('Strona sesji dziennych', min_value=1, max_value=pages,
                            step=1, key='market_history_page')
    st.caption(f'{ticker} · strona {index} z {pages} · 20 sesji na stronie · najnowsze na początku')
    newest = list(reversed(rows))
    st.html(cards(newest[(index-1)*20:index*20]))
    with st.expander('Wszystkie sesje Yahoo w tabeli'):
        st.dataframe(pd.DataFrame([{'Sesja': r['session'], 'Otwarcie': r['open'], 'Maksimum': r['high'],
                                   'Minimum': r['low'], 'Zamknięcie': r['close'], 'Wolumen': r['volume']}
                                  for r in newest]), hide_index=True, width="stretch")
