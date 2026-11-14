"""Measurable local base/alternative scenarios, separate from SL/TP and orders."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from html import escape

from sl_tp import stamp
from technical_config import DEFAULT_CONFIG
from technical_core import decimal, finite, pivots, valid_tail


def build(snapshot, rows, events, config=DEFAULT_CONFIG):
    plan = {'version': 1, 'status': 'UNAVAILABLE', 'ticker': snapshot.get('ticker'),
            'interval': snapshot.get('interval'), 'config_id': config.identifier,
            'reason': 'Za mało pełnych zamkniętych świec z obrotem do scenariuszy.',
            'execution_confirmed': False, 'is_trade_plan': False}
    if (snapshot.get('price_basis') or {}).get('blocked'):
        plan['reason']=snapshot['price_basis'].get('reason','Niepotwierdzona jednostka ceny po operacji na akcjach.')
        return plan
    acquired = stamp(snapshot.get('acquired_at'))
    if not acquired:
        return plan
    completed = []
    previous = None
    for row in rows:
        start, end = stamp(row.get('time')), stamp(row.get('end'))
        if not start or not end or end <= start or previous is not None and start < previous:
            plan['reason'] = 'Niespójne czasy świec; scenariusza nie obliczono.'
            return plan
        previous = end
        if row.get('status') == 'CLOSED' and end <= acquired:
            completed.append(row)
    rows = valid_tail(completed)[-config.pivot_lookback:]
    if len(rows) < max(config.sma_slow+1, config.reference_bars+1):
        return plan
    last = rows[-1]
    reference = rows[-config.reference_bars-1:-1]
    low, high = min(r['low'] for r in reference), max(r['high'] for r in reference)
    price = last['close']
    fast = sum(r['close'] for r in rows[-config.sma_fast:])/config.sma_fast
    slow = sum(r['close'] for r in rows[-config.sma_slow:])/config.sma_slow
    histogram = last.get('macd_hist')
    if not all(finite(v) for v in (low, high, price, fast, slow, histogram)) or not low < high:
        plan['reason'] = 'Brak pełnych, rozróżnialnych poziomów lub wskaźników zamkniętej świecy.'
        return plan
    direction = 'UP' if price > fast > slow and histogram > 0 else 'DOWN' if price < fast < slow and histogram < 0 else 'RANGE'
    width = config.pivot_width
    lows = [rows[i] for i in pivots(rows, 'low', width, 'low') if rows[i]['low'] < price]
    highs = [rows[i] for i in pivots(rows, 'high', width, 'high') if rows[i]['high'] > price]
    support = max((r['low'] for r in lows), default=low)
    resistance = min((r['high'] for r in highs), default=high)
    # Re-entering the old range negates the continuation branch of a breakout.
    guard = high if direction == 'UP' and price > high else low if direction == 'DOWN' and price < low else support if direction == 'UP' else resistance
    interval = str(snapshot.get('interval') or '')
    basis = 'Zamknięcie kolejnej pełnej świecy ' + interval
    if direction == 'UP':
        condition = {'field': 'closed_close', 'operator': 'GT', 'level': guard, 'interval': interval}
        invalidation = {**condition, 'operator': 'LE'}
        base = basis + ' powyżej ' + decimal(guard) + ' podtrzymuje warunkowy scenariusz wzrostowy.'
        alternative = basis + ' na lub poniżej ' + decimal(guard) + ' neguje ten wariant; możliwe cofnięcie lub konsolidacja.'
    elif direction == 'DOWN':
        condition = {'field': 'closed_close', 'operator': 'LT', 'level': guard, 'interval': interval}
        invalidation = {**condition, 'operator': 'GE'}
        base = basis + ' poniżej ' + decimal(guard) + ' podtrzymuje warunkowy scenariusz spadkowy.'
        alternative = basis + ' na lub powyżej ' + decimal(guard) + ' neguje ten wariant; możliwe odbicie lub konsolidacja.'
    else:
        condition = {'field': 'closed_close', 'operator': 'BETWEEN', 'lower': low, 'upper': high, 'interval': interval}
        invalidation = {**condition, 'operator': 'OUTSIDE'}
        base = 'Warunek scenariusza ruchu w przedziale: ' + basis.lower() + ' w zakresie ' + decimal(low) + '–' + decimal(high) + '.'
        alternative = basis + ' poza zakresem ' + decimal(low) + '–' + decimal(high) + ' neguje wariant przedziału; kierunek wymaga ponownej oceny.'
    at, acquired = stamp(last['end']), stamp(snapshot.get('acquired_at'))
    duration = (at-stamp(last['time'])).total_seconds() if stamp(last.get('time')) else 0
    historical = not acquired or not 0 <= (acquired-at).total_seconds() < duration
    warnings = [e['label'] for e in events if e['role'] == 'WARNING']
    plan.update(status='HISTORICAL' if historical else 'CONDITIONAL', direction=direction,
                candle_time=last['time'], known_at=last['end'], reference_close=price,
                evaluated_at=snapshot.get('acquired_at'), valid_until=(at+timedelta(seconds=duration)).isoformat(),
                base=base, alternative=alternative, condition=condition, invalidation=invalidation,
                warnings=warnings[:3], reason='Scenariusze opisują warunki techniczne, bez prognozy zysku i bez zlecenia.',
                levels={'range_low': low, 'range_high': high, 'guard': guard if direction != 'RANGE' else None},
                quote_limitation='Warunki wykonania wymagają osobnej oceny bid/ask; scenariusz nie potwierdza płynności.')
    plan['id'] = hashlib.sha256(json.dumps({k: plan[k] for k in ('ticker', 'interval', 'candle_time', 'config_id', 'condition')},
                                          sort_keys=True).encode()).hexdigest()[:24]
    return plan


def cards_html(plan):
    if plan.get('status') == 'UNAVAILABLE':
        return '<div class="ki-scenario-note">Scenariusze: ' + escape(plan.get('reason', 'Brak danych.')) + '</div>'
    condition = plan['invalidation']
    operator = condition['operator']
    trigger = ('Zamknięcie ' + str(plan.get('interval') or '') +
               (' ≤ ' if operator == 'LE' else ' ≥ ') + decimal(condition['level'])
               if operator in ('LE', 'GE') else 'Zamknięcie poza ' + decimal(condition['lower']) + '–' + decimal(condition['upper']))
    deadline = stamp(plan.get('valid_until'))
    historical = ' · zapis historyczny' if plan.get('status') == 'HISTORICAL' or deadline and datetime.now(timezone.utc) >= deadline else ''
    return '''<style>
    .ki-scenario{border:1px solid #64748b;border-radius:8px;padding:10px 12px;margin-top:10px;color:#edf2f7;overflow-wrap:anywhere;min-width:0}
    .ki-scenario p{font-size:.9rem;line-height:1.5;margin:8px 0}.ki-scenario summary{min-height:44px;cursor:pointer;padding:10px 0;box-sizing:border-box}
    .ki-scenario-note{font-size:.85rem;color:#c6d0dc;margin:8px 0}
    </style><section class="ki-scenario"><strong>Scenariusze warunkowe''' + historical + '</strong><p>' + escape(plan['base']) + \
        '</p><details><summary>Alternatywa i warunek zanegowania</summary><p>' + escape(plan['alternative']) + \
        '</p><p><b>Warunek zanegowania: ' + escape(trigger) + '</b></p>' + \
        ''.join('<p>Uwaga: ' + escape(x) + '</p>' for x in plan.get('warnings', [])) + \
        '<p class="ki-scenario-note">Podstawa: zamknięta świeca ' + escape(str(plan.get('candle_time'))) + \
        '. ' + escape(plan['reason']) + ' ' + escape(plan['quote_limitation']) + '</p></details></section>'
