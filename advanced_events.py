"""Confirmed-pivot RSI/OBV divergences and closed-bar trend-structure transitions."""
from technical_core import decimal, finite, oscillator_series, pivots, valid_tail, volume_ratio


def detect(rows, interval, config):
    rows = valid_tail(rows)
    events = []
    if len(rows) < config.rsi_period + 2*config.pivot_width + config.pivot_min_separation + 1:
        return events
    rsi, obv = oscillator_series(rows, config.rsi_period)
    width = config.pivot_width
    low = [i for i in pivots(rows, 'low', width, 'low') if i >= len(rows)-config.pivot_lookback]
    high = [i for i in pivots(rows, 'high', width, 'high') if i >= len(rows)-config.pivot_lookback]

    def add(code, label, direction, role, evidence, data=None):
        events.append({'code': code, 'label': label, 'direction': direction, 'role': role,
                       'evidence': evidence, 'data': data or {}, 'candle_time': rows[-1]['time'],
                       'known_at': rows[-1]['end']})

    for indices, field, side in ((low, 'low', 'UP'), (high, 'high', 'DOWN')):
        if len(indices) < 2 or indices[-1] + width != len(rows)-1:
            continue
        new = indices[-1]
        earlier = [i for i in indices[:-1] if new-i >= config.pivot_min_separation]
        if not earlier:
            continue
        old = earlier[-1]
        a, b = rows[old][field], rows[new][field]
        price_diverges = b <= a*(1-config.divergence_price_fraction) if side == 'UP' else b >= a*(1+config.divergence_price_fraction)
        if not price_diverges:
            continue
        data = {'first_pivot': rows[old]['time'], 'second_pivot': rows[new]['time'],
                'first_price': a, 'second_price': b, 'right_confirmation_bars': width}
        base = ('Potwierdzone ' + ('dołki' if side == 'UP' else 'szczyty') + ': ' + decimal(a) + ' → ' + decimal(b) +
                '. Daty punktów: ' + rows[old]['time'] + ' → ' + rows[new]['time'] +
                '. Drugi punkt potwierdzono dopiero po ' + str(width) + ' kolejnych zamkniętych świecach.')
        if finite(rsi[old]) and finite(rsi[new]):
            delta = rsi[new]-rsi[old]
            if (delta >= config.rsi_divergence_points if side == 'UP' else delta <= -config.rsi_divergence_points):
                add('RSI_DIVERGENCE_' + side, 'Dywergencja RSI · ' + ('wzrostowa' if side == 'UP' else 'spadkowa'),
                    side, 'WARNING', base + ' RSI: ' + decimal(rsi[old], 2) + ' → ' + decimal(rsi[new], 2) +
                    '. Ostrzeżenie o rozbieżności, bez potwierdzenia odwrócenia.',
                    {**data, 'first_rsi': rsi[old], 'second_rsi': rsi[new]})
        reference = rows[max(0, new-config.reference_bars):new]
        threshold = sum(r['volume'] for r in reference)/len(reference)*config.obv_divergence_volume if reference else float('inf')
        delta = obv[new]-obv[old]
        if all(finite(v) for v in (obv[old], obv[new], delta, threshold)) and (delta >= threshold if side == 'UP' else delta <= -threshold):
            add('OBV_DIVERGENCE_' + side, 'Dywergencja OBV · ' + ('wzrostowa' if side == 'UP' else 'spadkowa'),
                side, 'WARNING', base + ' Zmiana OBV między punktami w zachowanym oknie: ' + decimal(delta, 0) +
                '. Cena i skumulowany wolumen są rozbieżne; to nie dowód napływu kapitału.',
                {**data, 'first_obv': obv[old], 'second_obv': obv[new], 'delta_obv': delta, 'basis': 'closed_window'})

    def structure(lows, highs):
        if len(lows) < 2 or len(highs) < 2:
            return 'UNKNOWN'
        low1, low2 = [rows[i]['low'] for i in lows[-2:]]
        high1, high2 = [rows[i]['high'] for i in highs[-2:]]
        fraction = config.divergence_price_fraction
        if low2 > low1*(1+fraction) and high2 > high1*(1+fraction):
            return 'UP'
        if low2 < low1*(1-fraction) and high2 < high1*(1-fraction):
            return 'DOWN'
        return 'MIXED'

    current = structure(low, high)
    before = structure([i for i in low if i+width < len(rows)-1], [i for i in high if i+width < len(rows)-1])
    if current in ('UP', 'DOWN') and before not in ('UNKNOWN', current):
        add('STRUCTURE_' + current, 'Zmiana struktury · ' + ('wyższe szczyty i dołki' if current == 'UP' else 'niższe szczyty i dołki'),
            current, 'CONFIRMING', 'Nowy układ dwóch ostatnich potwierdzonych szczytów i dołków. '
            'Punkty wymagają po ' + str(width) + ' świec z prawej strony; zdarzenie jest opóźnionym opisem struktury.',
            {'lows': [{'time': rows[i]['time'], 'price': rows[i]['low']} for i in low[-2:]],
             'highs': [{'time': rows[i]['time'], 'price': rows[i]['high']} for i in high[-2:]], 'previous': before})
    return events


def activity_event(rows, interval, config):
    ratio = volume_ratio(rows, interval, config.reference_bars)
    if ratio is None or ratio < config.closed_volume_ratio:
        return []
    return [{'code': 'VOLUME_SURGE', 'label': 'Podwyższony wolumen zamkniętej świecy', 'direction': 'NEUTRAL',
             'role': 'CONFIRMING', 'evidence': 'Wolumen zamkniętej świecy: ' + decimal(ratio, 2) +
             '× średniej ' + str(config.reference_bars) + ' poprzednich pełnych świec. Sam wolumen nie określa kierunku.',
             'data': {'closed_rvol': ratio}, 'candle_time': rows[-1]['time'], 'known_at': rows[-1]['end']}]
