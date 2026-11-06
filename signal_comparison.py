"""Descriptive event statistics and causal, deterministic historical comparisons."""
from datetime import datetime, timezone
from html import escape
import math
from statistics import mean, median

from sl_tp import stamp
from technical_events import analyze, finite, valid_bar
from tracking_view import time_text


VERSION = 'KI_COMPARISON_1'
HORIZONS = (1, 2, 3, 5)


def features(snapshot, movement, event_context=None):
    """Only the original confirmation and fully closed reference bars, never live volume."""
    if not finite(movement) or movement == 0 or snapshot.get('interval') != '1h':
        return None
    context = event_context if event_context is not None else analyze(snapshot)
    moment = stamp(context.get('candle_time'))
    if not moment:
        return None
    rows = [r for r in snapshot.get('chart_history') or []
            if r.get('status') == 'CLOSED' and stamp(r.get('time'))
            and stamp(r['time']) <= moment]
    if len(rows) < 31 or not all(valid_bar(r) for r in rows[-31:]):
        return None
    last = rows[-1]
    baseline = mean(r['volume'] for r in rows[-21:-1])
    if baseline <= 0 or last['volume'] <= 0 or not finite(last.get('macd_hist')):
        return None
    fast = mean(r['close'] for r in rows[-10:])
    slow = mean(r['close'] for r in rows[-30:])
    value = {'version': VERSION, 'interval': '1h', 'candle_time': last['time'], 'candle_end': last['end'],
            'movement_pct': movement, 'closed_rvol': last['volume'] / baseline,
            'sma_gap_pct': (fast / slow - 1) * 100,
            'price_sma10_pct': (last['close'] / fast - 1) * 100,
            'macd_hist_pct': last['macd_hist'] / last['close'] * 100}
    return value if valid_features(value) else None


def valid_features(value):
    return (isinstance(value, dict) and value.get('version') == VERSION and value.get('interval') == '1h'
            and stamp(value.get('candle_time')) is not None
            and stamp(value.get('candle_end')) is not None
            and 0 < (stamp(value['candle_end']) - stamp(value['candle_time'])).total_seconds() <= 3720
            and all(finite(value.get(k)) for k in ('movement_pct', 'closed_rvol', 'sma_gap_pct', 'price_sma10_pct', 'macd_hist_pct'))
            and value['closed_rvol'] > 0 and value['movement_pct'] != 0)


def features_at(case):
    value = case.get('features')
    return valid_features(value) and stamp(value['candle_end']) <= stamp(case['confirmed_at'])


def cases_from_rows(rows):
    cases = {}
    for row in rows:
        key = (row['ticker'], row['confirmed_at'])
        if key not in cases:
            context = row.get('technical_events')
            context = context if isinstance(context, dict) else {}
            events = context.get('events')
            cases[key] = {k: row[k] for k in ('ticker', 'confirmed_at', 'direction', 'currency', 'price')}
            cases[key].update(events={e['code']: e['label'] for e in (events if isinstance(events, list) else [])
                                      if isinstance(e, dict) and isinstance(e.get('code'), str) and isinstance(e.get('label'), str)},
                              features=context.get('comparison'), outcomes={})
        cases[key]['outcomes'][row['horizon']] = row
    return sorted(cases.values(), key=lambda c: (c['confirmed_at'], c['ticker']), reverse=True)


def recover_original_features(store, cases):
    """Read the exact retained confirmation, without writes or later replacement data."""
    from observation_storage import loads
    with store.connection() as db:
        for case in cases:
            if features_at(case):
                continue
            at = stamp(case['confirmed_at'])
            times = (at.isoformat(), at.isoformat(timespec='microseconds'),
                     at.isoformat().replace('+00:00', 'Z'), at.isoformat(timespec='microseconds').replace('+00:00', 'Z'))
            row = db.execute("""
                SELECT payload FROM observations WHERE ticker=? AND interval='1h' AND acquired_at IN (?,?,?,?)
                AND json_valid(payload)
                AND json_extract(payload,'$.price_matrix.newly_confirmed')=1
                AND json_extract(payload,'$.price_matrix.activity_verified')=1
                ORDER BY id LIMIT 1
            """, (case['ticker'], *times)).fetchone()
            if not row:
                case['features'] = None
                continue
            snapshot = loads(row[0])
            matrix = snapshot.get('price_matrix') or {}
            movement = matrix.get('change_pct')
            if (snapshot.get('ticker') != case['ticker'] or stamp(snapshot.get('acquired_at')) != stamp(case['confirmed_at'])
                    or snapshot.get('currency') != case['currency'] or snapshot.get('price') != case['price']):
                case['features'] = None
                continue
            case['features'] = features(snapshot, movement)
    return cases


def market(case):
    return 'GPW' if case['ticker'].endswith('.WA') else 'USA'


def signal_day(case):
    from zoneinfo import ZoneInfo
    return stamp(case['confirmed_at']).astimezone(ZoneInfo('Europe/Warsaw' if market(case) == 'GPW' else 'America/New_York')).date()


def event_statistics(cases, horizon):
    # One earliest confirmation per issuer/session/type/direction, so polling and
    # repeated intraday confirmations do not inflate the number of examples.
    groups = {}
    for case in sorted(cases, key=lambda c: stamp(c['confirmed_at'])):
        for code, label in case['events'].items():
            key = (market(case), case['direction'], code)
            group = groups.setdefault(key, {'market': key[0], 'direction': key[1], 'code': code,
                                            'label': label, 'cases': {}})
            group['cases'].setdefault((case['ticker'], signal_day(case)), case)
    result = []
    for group in groups.values():
        selected = [case['outcomes'].get(horizon, {}) for case in group.pop('cases').values()]
        measured = [r['change'] for r in selected if r.get('status') == 'Obliczono' and finite(r.get('change'))]
        result.append({**group, 'total': len(selected), 'n': len(measured),
                       'mean': mean(measured) if measured else None, 'median': median(measured) if measured else None,
                       'continued': sum(v > 1e-9 if group['direction'] == 'Wzrost' else v < -1e-9 for v in measured),
                       'flat': sum(abs(v) <= 1e-9 for v in measured),
                       'missing': sum(r.get('status') == 'Brak danych z sesji' for r in selected),
                       'pending': sum(r.get('status') == 'Oczekuje na zamknięcie' for r in selected)})
    return sorted(result, key=lambda r: (-r['n'], r['label'], r['market'], r['direction']))


def sign(value):
    return 1 if value > 1e-9 else -1 if value < -1e-9 else 0


def feature_distance(ref, value):
    """Fixed geometry shared by separate daily and hourly comparisons."""
    if any(sign(value[k]) != sign(ref[k]) for k in ('sma_gap_pct', 'price_sma10_pct', 'macd_hist_pct')):
        return None
    movement_scale = max(2., abs(ref['movement_pct']) * .5)
    differences = (abs(value['movement_pct'] - ref['movement_pct']) / movement_scale,
                   abs(math.log2(value['closed_rvol']) - math.log2(ref['closed_rvol'])),
                   abs(value['sma_gap_pct'] - ref['sma_gap_pct']) / 3.,
                   abs(value['price_sma10_pct'] - ref['price_sma10_pct']) / 3.)
    return mean(differences) if max(differences) <= 1 else None


def similar_cases(reference, cases, limit=10):
    """No outcome is read during matching. Distances are fixed, not trained."""
    ref = reference.get('features')
    if not features_at(reference):
        return []
    at = stamp(reference['confirmed_at'])
    matched = []
    for case in cases:
        value = case.get('features')
        if (case['ticker'] != reference['ticker'] or case['direction'] != reference['direction'] or market(case) != market(reference)
                or not features_at(case) or stamp(case['confirmed_at']) >= at
                or (case['ticker'] == reference['ticker'] and signal_day(case) == signal_day(reference))):
            continue
        # Match the trend order and MACD sign, not an arbitrary later outcome.
        distance = feature_distance(ref, value)
        if distance is not None:
            matched.append({'case': case, 'distance': distance})
    matched.sort(key=lambda m: (m['distance'], -stamp(m['case']['confirmed_at']).timestamp(), m['case']['ticker']))
    # Also cap repeated historical issuer sessions independently of rank.
    selected, used = [], set()
    for item in matched:
        key = (item['case']['ticker'], signal_day(item['case']))
        if key not in used:
            selected.append(item)
            used.add(key)
        if len(selected) == limit:
            break
    return selected


def outcome_asof(case, horizon, at):
    row = case['outcomes'].get(horizon, {})
    close = stamp(row.get('session_close'))
    if not close or close > at:
        return {'status': 'Oczekuje na zamknięcie', 'change': None}
    candle_close = stamp((row.get('candle') or {}).get('closed_at'))
    if (row.get('status') == 'Obliczono' and finite(row.get('change'))
            and candle_close and candle_close <= at):
        return {'status': 'Obliczono', 'change': row['change']}
    return {'status': 'Brak danych z sesji', 'change': None}


def pct(value):
    return f'{value:+.2f}%'.replace('.', ',') if finite(value) else '—'


STYLE = '''<style>
.ki-compare-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px}
.ki-compare-card{background:#182330;color:#edf2f7;border:1px solid #61758b;border-radius:10px;padding:14px;min-width:0;overflow-wrap:anywhere}
.ki-compare-card p{font-size:.92rem;line-height:1.5}.ki-compare-card .muted{color:#c6d0dc}
.ki-compare-card .up{color:#6ee7a0}.ki-compare-card .down{color:#ff9292}
.ki-compare-card summary{min-height:44px;padding:10px 0;cursor:pointer;box-sizing:border-box}
@media(max-width:640px){.ki-compare-grid{grid-template-columns:minmax(0,1fr)}}
</style>'''


def statistics_html(rows):
    cards = []
    for r in rows:
        color = 'up' if r['direction'] == 'Wzrost' else 'down'
        note = 'Mało danych — wynik opisowy.' if r['n'] < 20 else 'Opis zapisanej próby, bez prognozy.'
        cards.append('<article class="ki-compare-card"><strong>' + escape(r['label']) + '</strong><p class="' + color + '">'
                     + escape(r['market'] + ' · ' + r['direction']) + '</p><p>Obliczono <b>' + str(r['n']) + '</b> z '
                     + str(r['total']) + '<br>Średnia zmiana ceny: <b>' + pct(r['mean'])
                     + '</b><br>Mediana: <b>' + pct(r['median']) + '</b></p><p>Zgodne z kierunkiem: '
                     + str(r['continued']) + ' z ' + str(r['n']) + '<br>Bez zmiany: ' + str(r['flat'])
                     + '<br>Brak danych: ' + str(r['missing']) + ' · oczekuje: ' + str(r['pending'])
                     + '</p><p class="muted">' + note + '</p></article>')
    return STYLE + '<div class="ki-compare-grid">' + ''.join(cards) + '</div>'


def similar_html(reference, matches):
    cards = []
    at = stamp(reference['confirmed_at'])
    for item in matches:
        case, f = item['case'], item['case']['features']
        results = []
        for horizon in HORIZONS:
            row = outcome_asof(case, horizon, at)
            label = 'Po 1 sesji' if horizon == 1 else 'Po ' + str(horizon) + ' sesjach'
            results.append(label + ': <b>' + (pct(row['change']) if row['change'] is not None else escape(row['status'])) + '</b>')
        cards.append('<article class="ki-compare-card"><strong>' + escape(case['ticker']) + '</strong><p>'
                     + escape(time_text(case['confirmed_at'])) + '</p><p>Ruch od bazy: ' + pct(f['movement_pct'])
                     + '<br>RVOL zamkniętej 1h: ' + format(f['closed_rvol'], '.2f').replace('.', ',') + '×</p><p>'
                     + '<br>'.join(results) + '</p><details><summary>Dlaczego ten przypadek</summary><p>'
                     + 'Ta sama spółka i kierunek. Zgodne znaki układu SMA i MACD.<br>Rozstęp SMA 10/30: '
                     + pct(f['sma_gap_pct']) + '<br>Cena względem SMA 10: ' + pct(f['price_sma10_pct'])
                     + '<br>Histogram MACD / cena: ' + pct(f['macd_hist_pct'])
                     + '</p><p class="muted">Kolejność wynika z różnic cech. Nie jest oceną szans transakcji.</p></details></article>')
    return STYLE + '<div class="ki-compare-grid">' + ''.join(cards) + '</div>'


def render(store):
    # Compare the selected issuer only; no pooled-market defaults or foreign issuers.
    from daily_analogs import render as render_daily
    render_daily(store)
