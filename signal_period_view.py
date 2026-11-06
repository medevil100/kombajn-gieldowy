"""One issuer over a chosen period, with a constant 52-week Yahoo context."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from statistics import mean, median

import daily_analogs as daily
from company_market_history import market_rows
from technical_events import finite
from tracking_view import number_text, time_text


def period_summary(rows):
    if not rows:
        return None
    if len({r['ticker'] for r in rows}) != 1:
        raise ValueError('Okres musi dotyczyć jednej spółki.')
    ordered = sorted(rows, key=lambda r: r['session'])
    first, last = ordered[0], ordered[-1]
    split = any(r.get('split') for r in ordered[1:])
    return {'ticker': first['ticker'], 'currency': first['currency'],
            'from': first['session'], 'to': last['session'], 'sessions': len(ordered),
            'start_close': first['close'], 'end_close': last['close'],
            'change': None if split else (last['close'] / first['close'] - 1) * 100,
            'split': split, 'low': min(r['low'] for r in ordered), 'high': max(r['high'] for r in ordered),
            'volume': sum(r['volume'] for r in ordered),
            'directions': dict(Counter(r['daily_movement'] for r in ordered))}


def event_review(rows, cases):
    """Describe events within the selected dates; outcomes stop at the period end."""
    if not rows:
        return []
    summary = period_summary(rows)
    dates = {r['session'] for r in rows}
    end = max(daily.stamp(r['end']) for r in rows)
    groups = {}
    for case in cases:
        if case['ticker'] != summary['ticker'] or case['session'] not in dates:
            continue
        for event in {e['code']: e for e in case['events']}.values():
            group = groups.setdefault(event['code'], {'label': event['label'], 'dates': [],
                                                       'outcomes': defaultdict(list)})
            group['dates'].append(case['session'])
            for horizon in daily.HORIZONS:
                result = case['outcomes'][horizon]
                if (result['status'] == 'Obliczono' and finite(result.get('change'))
                        and daily.stamp(result['session_close']) <= end):
                    group['outcomes'][horizon].append(result['change'])
    return [{'label': group['label'], 'count': len(group['dates']), 'dates': group['dates'],
             'outcomes': {h: {'n': len(group['outcomes'][h]),
                               'mean': mean(group['outcomes'][h]) if group['outcomes'][h] else None,
                               'median': median(group['outcomes'][h]) if group['outcomes'][h] else None}
                          for h in daily.HORIZONS}}
            for group in sorted(groups.values(), key=lambda g: (-len(g['dates']), g['label']))]


def month_summaries(rows, cases):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['session'][:7]].append(row)
    result = []
    for month, candles in sorted(grouped.items()):
        value = period_summary(candles)
        value.update(month=month, events=event_review(candles, cases))
        result.append(value)
    return result


def months_html(months):
    names = ('styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec',
             'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień')
    cards = []
    for value in months:
        year, month = value['month'].split('-')
        change = value['change']
        color = 'unknown' if change is None else 'up' if change > 0 else 'down' if change < 0 else 'flat'
        movement = 'Split w okresie — zmiana nieporównywalna' if change is None else daily.pct(change)
        directions = value['directions']
        event_text = '; '.join(e['label'] + ': ' + str(e['count']) for e in value['events'])
        fields = [('Zamknięcie pierwszej sesji', number_text(value['start_close'], value['currency'])),
                  ('Zamknięcie ostatniej sesji', number_text(value['end_close'], value['currency'])),
                  ('Minimum / maksimum', number_text(value['low']) + ' / ' + number_text(value['high']) + ' ' + value['currency']),
                  ('Sesje wzrost / spadek / bez zmian', str(directions.get('up', 0)) + ' / ' +
                   str(directions.get('down', 0)) + ' / ' + str(directions.get('flat', 0))),
                  ('Wolumen łącznie', number_text(value['volume'], digits=0))]
        detail = ''.join('<div><span>' + escape(k) + '</span><strong>' + escape(v) + '</strong></div>' for k, v in fields)
        cards.append('<article class="ki-period-month ' + color + '"><h4>' + names[int(month)-1].capitalize() +
                     ' ' + year + '</h4><p>' + escape(value['from'] + ' → ' + value['to']) + ' · ' +
                     str(value['sessions']) + ' sesji</p><p class="ki-period-change">' + escape(movement) +
                     '</p><div class="ki-period-values">' + detail + '</div><p><b>Zdarzenia techniczne</b><br>' +
                     escape(event_text or 'Bez rozpoznanych zdarzeń w dostępnym zakresie oceny.') + '</p></article>')
    return '''<style>
    .ki-period-months{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px}
    .ki-period-month{border:1px solid #61758b;border-radius:10px;background:#182330;color:#edf2f7;padding:14px;min-width:0;overflow-wrap:anywhere}
    .ki-period-month h4{color:inherit!important;margin:0;font-size:1.15rem}
    .ki-period-month p{font-size:.92rem;line-height:1.5;margin:8px 0}
    .ki-period-month.up{border-color:#4ade80;border-top-width:5px}
    .ki-period-month.down{border-color:#fb7185;border-top-width:5px}
    .ki-period-month.flat{border-color:#facc15;border-top-width:5px}
    .ki-period-change{font-size:1.25rem!important;font-weight:700}
    .ki-period-month.up .ki-period-change{color:#86efac}.ki-period-month.down .ki-period-change{color:#fda4af}
    .ki-period-month.flat .ki-period-change{color:#fde047}
    .ki-period-values>div{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid #43566c;font-size:.9rem}
    .ki-period-values span{color:#c6d0dc}.ki-period-values strong{text-align:right}
    @media(max-width:640px){.ki-period-months{grid-template-columns:minmax(0,1fr)}}
    </style><div class="ki-period-months">''' + ''.join(cards) + '</div>'


def render(store):
    import pandas as pd
    import plotly.graph_objects as go
    import streamlit as st
    st.subheader('Porównanie okresów tej samej spółki · 52 tygodnie')
    st.caption('Pełny rok notowań Yahoo w jednym widoku. Wybierz początek okresu; koniec to ostatnia zakończona sesja.')

    def clear():
        st.session_state['daily_analog_input'] = ''
        st.session_state.pop('daily_analog_active', None)
        st.session_state.pop('signal_period_from', None)

    with st.form('daily_analog_search'):
        symbol = st.text_input('Ticker spółki — historia dzienna', placeholder='Np. HUMA lub STX.WA',
                               max_chars=30, key='daily_analog_input')
        submitted = st.form_submit_button('Pokaż porównanie okresu')
        st.form_submit_button('Wyczyść', on_click=clear)
    if submitted:
        ticker = symbol.strip().upper()
        if not daily.valid_symbol(ticker):
            st.warning('Wpisz poprawny ticker, np. HUMA lub STX.WA.')
            return
        if ticker != st.session_state.get('daily_analog_active'):
            st.session_state.pop('signal_period_from', None)
        st.session_state['daily_analog_active'] = ticker
    ticker = st.session_state.get('daily_analog_active')
    if not ticker:
        st.info('Wpisz ticker. Wcześniejsze potwierdzenia KI nie są wymagane.')
        return
    refresh = st.button('Odśwież Yahoo', key='signal_period_refresh')
    if submitted or refresh:
        try:
            with st.spinner('Odczytuję historię Yahoo…'):
                state = daily.refresh(store, ticker)
            if state == 'WAIT':
                st.info('Następne pobranie jest chwilowo odroczone; pokazujemy dostępną kopię Yahoo.')
        except Exception as exc:
            st.warning(daily.sanitize_cli_diagnostic(str(exc)))
    cache = daily.read_cache(store, ticker)
    if cache.get('last_error'):
        st.warning('Ostatnie pobranie: ' + cache['last_error'])
    now = datetime.now(timezone.utc)
    rows = market_rows(cache, now) if cache.get('ticker') == ticker else []
    if not rows:
        st.info('Brak pobranych poprawnych sesji Yahoo z ostatnich 52 tygodni dla ' + ticker + '.')
        return
    if rows[-1]['session'] < daily.last_session(ticker, now):
        st.warning('Kopia nie obejmuje ostatniej zakończonej sesji. Widoczne wyniki dotyczą starszych danych.')
    first, last = date.fromisoformat(rows[0]['session']), date.fromisoformat(rows[-1]['session'])
    current = st.session_state.get('signal_period_from', first)
    if not isinstance(current, date) or current < first or current > last:
        st.session_state['signal_period_from'] = first
    start = st.date_input('Od dnia', value=first, min_value=first, max_value=last,
                          key='signal_period_from', format='DD.MM.YYYY')
    selected = [r for r in rows if r['session'] >= start.isoformat()]
    st.caption('Dostępne 52 tygodnie: ' + rows[0]['session'] + ' → ' + rows[-1]['session'] +
               ' · ' + str(len(rows)) + ' sesji · pobrano ' + time_text(cache.get('fetched_at')))
    st.caption('Wybrany okres: ' + start.isoformat() + ' → ' + rows[-1]['session'] +
               ' · ' + str(len(selected)) + ' sesji. Zmiana daty nie pobiera danych ponownie.')
    chart = go.Figure(go.Scatter(x=[r['session'] for r in rows], y=[r['close'] for r in rows],
                                mode='lines', name='Pełne 52 tygodnie', line={'color': '#8194ab', 'width': 1.5}))
    chart.add_trace(go.Scatter(x=[r['session'] for r in selected], y=[r['close'] for r in selected],
                              mode='lines', name='Wybrany okres', line={'color': '#60a5fa', 'width': 3}))
    chart.update_layout(height=300, margin=dict(l=8, r=8, t=16, b=8), yaxis_title=cache['currency'],
                        hovermode='x unified', dragmode=False, legend={'orientation': 'h'})
    st.plotly_chart(chart, width='stretch', config={'displayModeBar': False, 'scrollZoom': False})
    summary = period_summary(selected)
    if summary is None:
        st.info('Brak zakończonych sesji w wybranym okresie.')
        return
    st.markdown('**Cały wybrany okres · ' + ticker + '**')
    st.write('Zamknięcia: ' + number_text(summary['start_close'], summary['currency']) + ' → ' +
             number_text(summary['end_close'], summary['currency']) + ' · zmiana ' +
             ('nieporównywalna — split' if summary['split'] else daily.pct(summary['change'])))
    d = summary['directions']
    st.write('Sesje wzrostowe: ' + str(d.get('up', 0)) + ' · spadkowe: ' + str(d.get('down', 0)) +
             ' · bez zmiany: ' + str(d.get('flat', 0)) + ' · brak porównania: ' + str(d.get('unknown', 0)))
    cases = daily.build_cases(cache, now, require_features=False)
    st.subheader('Przebieg miesiąc po miesiącu')
    st.html(months_html(month_summaries(selected, cases)))
    st.caption('Zmiana okresu i miesiąca: od pierwszego do ostatniego zamknięcia w danym zakresie. '
               'Wzrosty i spadki sesji: względem poprzedniego zapisanego zamknięcia. '
               'Surowe ceny Yahoo, bez dywidend i kosztów; splity są oznaczone. Miesiące brzegowe mogą być częściowe.')
    with st.expander('Zdarzenia techniczne i późniejsze zmiany ceny w wybranym okresie'):
        review = event_review(selected, cases)
        if not review:
            st.info('Brak rozpoznanych zdarzeń z pełnymi danymi w wybranym okresie.')
        for event in review:
            st.markdown('**' + event['label'] + ' · ' + str(event['count']) + ' sesji**')
            st.caption('Daty: ' + ', '.join(event['dates']))
            st.write(' · '.join('Po ' + str(h) + ' sesjach: ' + daily.pct(event['outcomes'][h]['mean']) +
                               ' (n=' + str(event['outcomes'][h]['n']) + ')' for h in daily.HORIZONS))
        eligible = sum(c['ticker'] == ticker and c.get('features') is not None and c['session'] in {r['session'] for r in selected} for c in cases)
        st.caption('Sesje z pełnymi cechami: ' + str(eligible) + '/' + str(len(selected)) +
                   '. Odtworzenie dzienne z ówczesnych danych; braki i splity przerywają ocenę. '
                   'Wyniki ograniczamy końcem wybranego okresu. Zdarzenia mogą się nakładać; to opis historii, bez prognozy skuteczności.')
    with st.expander('Wszystkie sesje wybranego okresu'):
        st.dataframe(pd.DataFrame([{'Sesja': r['session'], 'Zamknięcie': r['close'],
                                   'Minimum': r['low'], 'Maksimum': r['high'], 'Wolumen': r['volume'],
                                   'Ruch': r['movement_label']} for r in selected]), hide_index=True, width='stretch')
