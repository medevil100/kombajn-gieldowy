"""Local event descriptions adapted from Alchemik's technical detector."""
from html import escape
from zoneinfo import ZoneInfo

from sl_tp import number, stamp
from technical_config import DEFAULT_CONFIG
from technical_core import finite, decimal, valid_bar
from advanced_events import detect as advanced_events, activity_event
from signal_setups import compose
from scenario_plan import build as build_scenarios, cards_html as scenario_cards_html


METHOD = 'KI_TECHNICAL_EVENTS_2'
ROLES = {'EARLY': 'Wczesna obserwacja', 'CONFIRMING': 'Potwierdzenie układu',
         'WARNING': 'Ostrzeżenie', 'CONTEXT': 'Kontekst'}


def analyze(snapshot, config=DEFAULT_CONFIG):
    """Evaluate completed bars only, using the snapshot's own acquisition time."""
    result = {'method': METHOD, 'config_version': config.version, 'config_id': config.identifier,
              'events': [], 'setups': [], 'missing': [], 'candle_time': None, 'known_at': None,
              'interval': snapshot.get('interval'), 'acquired_at': snapshot.get('acquired_at')}
    acquired = stamp(snapshot.get('acquired_at'))
    if not acquired:
        result['missing'].append('Brak wiarygodnego czasu odczytu.')
        return result
    rows = []
    previous = None
    for row in snapshot.get('chart_history') or []:
        start, end = stamp(row.get('time')), stamp(row.get('end'))
        if not start or not end or end <= start or (previous is not None and start <= previous):
            result['missing'].append('Niepoprawna kolejność lub czas świec.')
            return result
        previous = start
        if row.get('status') == 'CLOSED' and end <= acquired:
            rows.append(row)
    if not rows or not valid_bar(rows[-1]) or rows[-1]['volume'] <= 0:
        result['missing'].append('Brak poprawnej zamkniętej świecy z obrotem.')
        return result
    last = rows[-1]
    result['candle_time'] = last['time']
    result['known_at'] = last['end']

    def add(code, label, direction, role, evidence):
        result['events'].append({'code': code, 'label': label, 'direction': direction,
                                 'role': role, 'evidence': evidence, 'candle_time': last['time'], 'known_at': last['end']})

    reference = rows[-config.reference_bars-1:-1]
    if len(reference) == config.reference_bars and all(valid_bar(row) for row in reference):
        high = max(row['high'] for row in reference)
        low = min(row['low'] for row in reference)
        if last['close'] >= high * (1+config.breakout_fraction):
            add('RESISTANCE_BREAKOUT', 'Wybicie oporu', 'UP', 'EARLY',
                f'Zamknięcie {decimal(last["close"])} co najmniej {decimal(config.breakout_fraction*100, 2)}% ponad maksimum {decimal(high)} z {config.reference_bars} poprzednich świec.')
        if last['close'] <= low * (1-config.breakout_fraction):
            add('SUPPORT_BREAKDOWN', 'Przebicie wsparcia', 'DOWN', 'EARLY',
                f'Zamknięcie {decimal(last["close"])} co najmniej {decimal(config.breakout_fraction*100, 2)}% poniżej minimum {decimal(low)} z {config.reference_bars} poprzednich świec.')
    else:
        result['missing'].append(f'Wybicie wymaga {config.reference_bars} poprawnych świec odniesienia.')

    if len(rows) >= config.sma_slow+1 and all(valid_bar(row) for row in rows[-config.sma_slow-1:]):
        closes = [row['close'] for row in rows[-config.sma_slow-1:]]
        old_fast, old_slow = sum(closes[-config.sma_fast-1:-1]) / config.sma_fast, sum(closes[-config.sma_slow-1:-1]) / config.sma_slow
        fast, slow = sum(closes[-config.sma_fast:]) / config.sma_fast, sum(closes[-config.sma_slow:]) / config.sma_slow
        evidence = (f'SMA {config.sma_fast} / {config.sma_slow} poprzednio {decimal(old_fast)} / {decimal(old_slow)}, '
                    f'obecnie {decimal(fast)} / {decimal(slow)}.')
        if old_fast <= old_slow and fast > slow:
            add('SMA_CROSS_UP', 'Przecięcie SMA w górę', 'UP', 'EARLY', evidence)
        if old_fast >= old_slow and fast < slow:
            add('SMA_CROSS_DOWN', 'Przecięcie SMA w dół', 'DOWN', 'EARLY', evidence)
    else:
        result['missing'].append(f'Przecięcie SMA {config.sma_fast} / {config.sma_slow} wymaga {config.sma_slow+1} poprawnych świec.')

    pair = rows[-2:]
    if len(pair) == 2 and all(valid_bar(row) for row in pair):
        before = pair[0]
        if all(finite(row.get(key)) for row in pair for key in ('macd', 'macd_signal')):
            old_delta = before['macd'] - before['macd_signal']
            delta = last['macd'] - last['macd_signal']
            evidence = f'MACD minus linia sygnału poprzednio {decimal(old_delta)}, obecnie {decimal(delta)}.'
            if old_delta <= 0 < delta:
                add('MACD_CROSS_UP', 'Przecięcie MACD w górę', 'UP', 'EARLY', evidence)
            if old_delta >= 0 > delta:
                add('MACD_CROSS_DOWN', 'Przecięcie MACD w dół', 'DOWN', 'EARLY', evidence)
        else:
            result['missing'].append('Brak dwóch kolejnych wartości MACD i linii sygnału.')
        if (before['close'] < before['open'] and last['close'] > last['open']
                and last['open'] <= before['close'] and last['close'] >= before['open']
                and last['close'] - last['open'] > before['open'] - before['close']):
            add('BULLISH_ENGULFING', 'Objęcie wzrostowe', 'UP', 'CONFIRMING',
                'Korpus wzrostowej świecy obejmuje większym zakresem poprzedni korpus spadkowy.')
        if (before['close'] > before['open'] and last['close'] < last['open']
                and last['open'] >= before['close'] and last['close'] <= before['open']
                and last['open'] - last['close'] > before['close'] - before['open']):
            add('BEARISH_ENGULFING', 'Objęcie spadkowe', 'DOWN', 'CONFIRMING',
                'Korpus spadkowej świecy obejmuje większym zakresem poprzedni korpus wzrostowy.')
    else:
        result['missing'].append('Brak dwóch poprawnych świec do porównania.')

    window = rows[-config.reference_bars-1:]
    if len(window) == config.reference_bars+1 and all(valid_bar(row) and number(row.get('bb_middle'))
            and finite(row.get('bb_upper')) and finite(row.get('bb_lower'))
            and row['bb_upper'] >= row['bb_lower'] for row in window):
        widths = [(row['bb_upper'] - row['bb_lower']) / row['bb_middle'] for row in window]
        average = sum(widths[:-1]) / config.reference_bars
        if average > 0:
            ratio = widths[-1] / average
            evidence = f'Szerokość pasma {decimal(ratio, 2)}× średniej z {config.reference_bars} poprzednich zamkniętych świec.'
            if ratio <= config.bb_squeeze_ratio:
                add('BB_SQUEEZE', 'Zwężenie Bollingera', 'NEUTRAL', 'CONTEXT', evidence)
            if ratio >= config.bb_expansion_ratio:
                add('BB_EXPANSION', 'Rozszerzenie Bollingera', 'NEUTRAL', 'EARLY', evidence)
        else:
            result['missing'].append('Zerowa średnia szerokości pasma Bollingera.')
    else:
        result['missing'].append(f'Brak {config.reference_bars+1} poprawnych wartości pasma Bollingera.')
    candle_range = last['high'] - last['low']
    if candle_range > 0 and abs(last['close'] - last['open']) / candle_range <= config.doji_fraction:
        add('DOJI', 'Doji', 'NEUTRAL', 'WARNING', f'Korpus zajmuje najwyżej {decimal(config.doji_fraction*100, 2)}% zakresu świecy.')
    result['events'].extend(advanced_events(rows, snapshot.get('interval'), config))
    result['events'].extend(activity_event(rows, snapshot.get('interval'), config))
    result['setups'] = compose(snapshot, result['events'], config)
    result['events'].extend(result['setups'])
    result['scenario'] = build_scenarios(snapshot, rows, result['events'], config)
    return result


def cards_html(view):
    """Compact, wrapping labels and touch-sized details for any KI card."""
    events = sorted(view.get('events') or [], key=lambda e: (e.get('kind') != 'COMPOSITE', e.get('role') != 'WARNING'))
    chips = []
    for event in events[:3]:
        color = 'warning' if event['role'] == 'WARNING' else event['direction'].lower()
        chips.append('<span class="ki-event-chip ' + color + '">' + escape(event['label']) + '</span>')
    if not events:
        message = ('Brak danych do oceny zdarzeń.' if not view.get('candle_time')
                   else 'Brak zdarzeń w sprawdzonym zakresie.')
        chips.append('<span class="ki-event-empty">' + message + '</span>')
    details = ''.join('<p><strong>' + escape(event['label']) + '</strong> · '
                      + escape(ROLES[event['role']]) + '<br>' + escape(event['evidence']) + '</p>'
                      for event in events)
    if (view.get('scenario') or {}).get('status') == 'UNAVAILABLE':
        details += '<p>Scenariusze: ' + escape(view['scenario'].get('reason', 'Brak danych.')) + '</p>'
    details += ''.join('<p>' + escape(message) + '</p>' for message in view.get('missing', []))
    if len(events) > 3:
        chips.append('<span class="ki-event-empty">+' + str(len(events) - 3) + ' w szczegółach</span>')
    at = stamp(view.get('candle_time'))
    date = at.astimezone(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y %H:%M %Z') if at else 'brak czasu świecy'
    return '''<style>
    .ki-event-box{margin:10px 0;min-width:0;overflow-wrap:anywhere;color:#edf2f7}
    .ki-event-chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
    .ki-event-chip{font-size:.9rem;border:1px solid #738497;border-radius:6px;padding:6px 8px}
    .ki-event-chip.up{background:#143b2c;color:#dcfce7;border-color:#4ade80}
    .ki-event-chip.down{background:#4c1d24;color:#ffe4e6;border-color:#fb7185}
    .ki-event-chip.neutral{background:#142b45;color:#bfdbfe;border-color:#60a5fa}
    .ki-event-chip.warning{background:#443713;color:#fef9c3;border-color:#facc15}
    .ki-event-empty,.ki-event-time{font-size:.85rem;color:#c6d0dc}
    .ki-event-box summary{min-height:44px;cursor:pointer;padding:10px 0;box-sizing:border-box}
    .ki-event-box details p{font-size:.85rem;color:#c6d0dc}
    </style><section class="ki-event-box"><strong>Zdarzenia techniczne</strong>
    <div class="ki-event-chips">''' + ''.join(chips) + '</div><div class="ki-event-time">' + escape(
        'Ostatnia zamknięta świeca ' + str(view.get('interval') or '') + ' · ' + date
    ) + '</div><details><summary>Dowody i zakres oceny</summary>' + details + '</details></section>' + (scenario_cards_html(view['scenario']) if (view.get('scenario') or {}).get('status') in ('CONDITIONAL', 'HISTORICAL') else '')
