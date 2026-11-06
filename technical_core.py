"""Shared pure calculations over completed source candles; no provider calls."""
import math
from sl_tp import number, stamp


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def decimal(value, digits=4):
    return format(value, '.' + str(digits) + 'f').replace('.', ',')


def valid_bar(row):
    prices = [row.get(key) for key in ('open', 'high', 'low', 'close')]
    return (all(number(value) for value in prices) and finite(row.get('volume')) and row['volume'] >= 0
            and row.get('price_origin') != 'carried_previous_close'
            and row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high'])


def valid_tail(rows):
    start = 0
    for i, row in enumerate(rows):
        if not valid_bar(row) or row['volume'] <= 0:
            start = i + 1
    return rows[start:]


def pivots(rows, key, width, kind):
    found = []
    for i in range(width, len(rows)-width):
        value = rows[i][key]
        neighbours = rows[i-width:i] + rows[i+1:i+width+1]
        if all(value < row[key] if kind == 'low' else value > row[key] for row in neighbours):
            found.append(i)
    return found


def oscillator_series(rows, period):
    rsi = [None]*len(rows)
    obv = [0.]*len(rows)
    gain = loss = None
    changes = [rows[i]['close'] - rows[i-1]['close'] for i in range(1, len(rows))]
    for i, change in enumerate(changes, 1):
        obv[i] = obv[i-1] + (rows[i]['volume'] if change > 0 else -rows[i]['volume'] if change < 0 else 0.)
        if i < period:
            continue
        if i == period:
            gain = sum(max(x, 0.) for x in changes[:period])/period
            loss = sum(max(-x, 0.) for x in changes[:period])/period
        else:
            gain = (gain*(period-1) + max(change, 0.))/period
            loss = (loss*(period-1) + max(-change, 0.))/period
        rsi[i] = 50. if gain == loss == 0 else 100. if loss == 0 else 100 - 100/(1 + gain/loss)
    return rsi, obv


def volume_ratio(rows, interval, reference):
    selected = rows[-reference-1:]
    if len(selected) != reference+1 or not all(valid_bar(r) and r['volume'] > 0 for r in selected):
        return None
    seconds = {'5m': 300, '15m': 900, '30m': 1800, '1h': 3600}.get(interval)
    if seconds and any(not stamp(r.get('time')) or not stamp(r.get('end')) or
                       (stamp(r['end'])-stamp(r['time'])).total_seconds() != seconds for r in selected):
        return None
    average = sum(r['volume'] for r in selected[:-1])/reference
    ratio = selected[-1]['volume']/average if average > 0 else None
    return ratio if finite(ratio) and ratio > 0 else None
