"""Separate, cached Yahoo daily analogies; no fabricated scanner confirmations."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html import escape
import json
import re
from statistics import mean, median
from zoneinfo import ZoneInfo

from ki2_ops_guard import guard_operation
from signal_comparison import HORIZONS, STYLE, feature_distance, pct, sign
from sl_tp import stamp
from tavily_cli_adapter import sanitize_cli_diagnostic
from technical_events import analyze, finite, valid_bar
from tracking_view import time_text


VERSION = 'YAHOO_DAILY_ANALOG_1'
WARMUP = 60
DOWNLOAD_GATE = 'daily_analog:download_gate'


class YahooRateLimited(RuntimeError):
    pass


def valid_symbol(ticker):
    return isinstance(ticker, str) and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,29}', ticker) is not None


@lru_cache(maxsize=2)
def calendar_for(gpw):
    from exchange_calendars import get_calendar
    return get_calendar('XWAR' if gpw else 'XNYS')


def zone(ticker):
    return ZoneInfo('Europe/Warsaw' if ticker.endswith('.WA') else 'America/New_York')


def last_session(ticker, now):
    calendar = calendar_for(ticker.endswith('.WA'))
    day = now.astimezone(zone(ticker)).date().isoformat()
    session = calendar.date_to_session(day, direction='previous')
    if calendar.session_close(session) > now:
        session = calendar.previous_session(session)
    return session.date().isoformat()


def parse_response(body, ticker, now):
    """Validate identity, exchange sessions and complete OHLCV before caching."""
    chart = body.get('chart') or {}
    results = chart.get('result')
    if chart.get('error') or not isinstance(results, list) or len(results) != 1:
        raise ValueError('Yahoo nie zwróciło historii dla tego tickera.')
    source = results[0]
    meta = source.get('meta') or {}
    currency = 'PLN' if ticker.endswith('.WA') else 'USD'
    if (meta.get('symbol') != ticker or meta.get('currency') != currency
            or meta.get('exchangeTimezoneName') != str(zone(ticker))):
        raise ValueError('Nie potwierdzono zgodności tickera, waluty i rynku w odpowiedzi Yahoo.')
    timestamps = source.get('timestamp') or []
    quote = ((source.get('indicators') or {}).get('quote') or [{}])[0]
    if not timestamps or len(timestamps) > 2000:
        raise ValueError('Brak historii dziennej lub nieoczekiwany rozmiar odpowiedzi Yahoo.')
    if any(not isinstance(quote.get(k), list) or len(quote[k]) != len(timestamps)
           for k in ('open', 'high', 'low', 'close', 'volume')):
        raise ValueError('Niespójne kolumny dziennych danych Yahoo.')
    calendar = calendar_for(ticker.endswith('.WA'))
    rows, rejected, seen = [], [], set()
    for i, timestamp in enumerate(timestamps):
        day = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(zone(ticker)).date().isoformat()
        if day in seen:
            raise ValueError('Yahoo zwróciło powtórzoną sesję; nie zapisano nowej historii.')
        seen.add(day)
        if not calendar.is_session(day):
            rejected.append({'session': day, 'reason': 'Data poza kalendarzem sesji.'})
            continue
        end = calendar.session_close(day).to_pydatetime()
        if end > now:
            continue
        row = {key: quote[key][i] for key in ('open', 'high', 'low', 'close', 'volume')}
        row.update(session=day, time=calendar.session_open(day).isoformat(),
                   end=end.isoformat(), status='CLOSED')
        if not valid_bar(row):
            rejected.append({'session': day, 'reason': 'Niepełne lub sprzeczne OHLCV.'})
            continue
        rows.append(row)
    if not rows:
        raise ValueError('Brak poprawnych zamkniętych sesji dziennych Yahoo.')
    if [row['session'] for row in rows] != sorted(row['session'] for row in rows):
        raise ValueError('Historia Yahoo nie ma poprawnej kolejności sesji.')
    splits = sorted({datetime.fromtimestamp(item['date'], timezone.utc).astimezone(zone(ticker)).date().isoformat()
                     for item in ((source.get('events') or {}).get('splits') or {}).values()})
    return {'version': VERSION, 'ticker': ticker, 'currency': currency, 'rows': rows,
            'splits': splits, 'rejected_count': len(rejected), 'rejected': rejected[:30],
            'source': 'Yahoo Finance', 'source_interval': '1d', 'requested_range': '2y',
            'fetched_at': now.isoformat()}


def download(ticker, now):
    from curl_cffi import requests
    with requests.Session(impersonate='chrome') as session:
        response = session.get('https://query1.finance.yahoo.com/v8/finance/chart/' + ticker,
                               params={'range': '2y', 'interval': '1d', 'includePrePost': 'false',
                                       'events': 'div,splits'}, timeout=20)
        if response.status_code == 429:
            raise YahooRateLimited('Yahoo ograniczyło liczbę zapytań. Następna próba najwcześniej za godzinę.')
        if response.status_code != 200:
            raise ValueError('Pobranie historii Yahoo nie powiodło się (HTTP ' + str(response.status_code) + ').')
        return parse_response(response.json(), ticker, now)


def read_value(connection, key):
    row = connection.execute('SELECT payload FROM runtime WHERE key=?', (key,)).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def read_cache(store, ticker):
    with store.connection() as connection:
        return read_value(connection, 'daily_analog:' + ticker)


def write_value(connection, key, value, now):
    connection.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',
                       (key, json.dumps(value, ensure_ascii=False, allow_nan=False), now.isoformat()))


@guard_operation()
def refresh(store, ticker, now=None):
    """One explicit request, with durable reservations and no retries or fan-out."""
    from KI import bounded_market_operation
    now = now or datetime.now(timezone.utc)
    if not valid_symbol(ticker):
        raise ValueError('Wpisz poprawny ticker, np. STX.WA lub MREO.')
    required = last_session(ticker, now)
    key = 'daily_analog:' + ticker
    with store.transaction() as connection:
        current = read_value(connection, key)
        rows = current.get('rows') or []
        if (current.get('version') == VERSION and current.get('checked_for_session') == required
                and rows and rows[-1].get('session') == required):
            return 'CACHED'
        gate = read_value(connection, DOWNLOAD_GATE)
        deadlines = [stamp(value.get('next_attempt_at')) for value in (current, gate)]
        if any(deadline and deadline > now for deadline in deadlines):
            return 'WAIT'
        current.update(status='FETCHING', attempted_at=now.isoformat(), next_attempt_at=(now + timedelta(minutes=15)).isoformat())
        write_value(connection, key, current, now)
        write_value(connection, DOWNLOAD_GATE, {'next_attempt_at': (now + timedelta(seconds=30)).isoformat()}, now)
    try:
        data = bounded_market_operation(lambda: download(ticker, now), ('DAILY_ANALOG', ticker), 30)
    except Exception as exc:
        rate_limited = isinstance(exc, YahooRateLimited)
        deadline = now + timedelta(hours=1) if rate_limited else now + timedelta(minutes=15)
        current.update(status='FAILED', last_error=sanitize_cli_diagnostic(str(exc))[:500], next_attempt_at=deadline.isoformat())
        with store.transaction() as connection:
            write_value(connection, key, current, now)
            if rate_limited:
                write_value(connection, DOWNLOAD_GATE, {'next_attempt_at': deadline.isoformat()}, now)
        return 'FAILED'
    data.update(status='READY', checked_for_session=required, attempted_at=now.isoformat(),
                next_attempt_at=(now + timedelta(minutes=15)).isoformat(), last_error=None)
    with store.transaction() as connection:
        write_value(connection, key, data, now)
    return 'UPDATED'


def daily_features(chart):
    if len(chart) < WARMUP or not all(valid_bar(row) for row in chart[-WARMUP:]):
        return None
    last, prior = chart[-1], chart[-2]
    average = mean(row['volume'] for row in chart[-21:-1])
    if average <= 0 or last['volume'] <= 0 or not finite(last.get('macd_hist')):
        return None
    fast, slow = mean(row['close'] for row in chart[-10:]), mean(row['close'] for row in chart[-30:])
    f = {'movement_pct': (last['close'] / prior['close'] - 1) * 100,
         'closed_rvol': last['volume'] / average, 'sma_gap_pct': (fast / slow - 1) * 100,
         'price_sma10_pct': (last['close'] / fast - 1) * 100,
         'macd_hist_pct': last['macd_hist'] / last['close'] * 100}
    return f if all(finite(v) for v in f.values()) and f['movement_pct'] != 0 else None


def build_cases(cache, now=None, require_features=True):
    """Walk forward only. A missing session or split restarts indicator warm-up."""
    from KI import build_chart_history
    now = now or datetime.now(timezone.utc)
    ticker = cache['ticker']
    calendar = calendar_for(ticker.endswith('.WA'))
    cutoff = (now.astimezone(zone(ticker)).date() - timedelta(weeks=52)).isoformat()
    source_rows = cache.get('rows') or []
    rows = [row for row in source_rows if stamp(row.get('end')) and stamp(row['end']) <= now]
    by_day = {row['session']: row for row in rows}
    splits = set(cache.get('splits') or [])
    segments, segment, previous = [], [], None
    for row in rows:
        day = row['session']
        continuous = previous is not None and calendar.next_session(previous).date().isoformat() == day
        if not continuous or day in splits or not valid_bar(row):
            if segment:
                segments.append(segment)
            segment = []
        if day not in splits and valid_bar(row):
            segment.append(row)
        previous = day
    if segment:
        segments.append(segment)
    cases = []
    for segment in segments:
        chart = build_chart_history(segment, limit=len(segment))
        for i in range(WARMUP - 1, len(chart)):
            day = segment[i]['session']
            if day < cutoff:
                continue
            prefix = chart[:i + 1]
            f = daily_features(prefix)
            if f is None and require_features:
                continue
            at = stamp(chart[i]['end'])
            events = analyze({'interval': '1d', 'acquired_at': at.isoformat(), 'chart_history': prefix})
            outcomes = {}
            sessions = calendar.sessions_window(day, max(HORIZONS) + 1)
            for horizon in HORIZONS:
                target = sessions[horizon].date().isoformat()
                end = calendar.session_close(sessions[horizon]).to_pydatetime()
                candle = by_day.get(target)
                intervening = {s.date().isoformat() for s in sessions[1:horizon + 1]}
                if end > now:
                    status, change = 'Oczekuje na zamknięcie', None
                elif intervening & splits:
                    status, change = 'Split w okresie — pominięto', None
                elif candle is None or not valid_bar(candle):
                    status, change = 'Brak danych z sesji', None
                else:
                    status, change = 'Obliczono', (candle['close'] / chart[i]['close'] - 1) * 100
                outcomes[horizon] = {'session': target, 'session_close': end.isoformat(), 'status': status, 'change': change}
            cases.append({'ticker': ticker, 'session': day, 'at': at.isoformat(), 'price': chart[i]['close'],
                          'features': f, 'events': events['events'], 'outcomes': outcomes,
                          'technical_method': events['method'], 'config_id': events.get('config_id')})
    return cases


def find_matches(reference, cases, limit=10):
    found = []
    f = reference['features']
    for case in cases:
        if (case['ticker'] != reference['ticker'] or case['session'] >= reference['session']
                or sign(case['features']['movement_pct']) != sign(f['movement_pct'])):
            continue
        distance = feature_distance(f, case['features'])
        if distance is not None:
            found.append({'case': case, 'distance': distance})
    return sorted(found, key=lambda m: (m['distance'], -stamp(m['case']['at']).timestamp()))[:limit]


def visible_result(case, horizon, reference):
    row = case['outcomes'][horizon]
    if stamp(row['session_close']) > stamp(reference['at']):
        return {'status': 'Sesja późniejsza od odniesienia', 'change': None}
    return row


def matches_html(reference, matches):
    cards = []
    for item in matches:
        case = item['case']
        f = case['features']
        results = []
        for horizon in HORIZONS:
            row = visible_result(case, horizon, reference)
            label = 'Po 1 sesji' if horizon == 1 else 'Po ' + str(horizon) + ' sesjach'
            value = pct(row['change']) if row['change'] is not None else escape(row['status'])
            results.append(label + ': <b>' + value + '</b>')
        event_text = ', '.join(event['label'] for event in case['events']) or 'Bez zdarzeń w sprawdzonym zakresie'
        cards.append('<article class="ki-compare-card"><strong>Sesja ' + escape(case['session'])
                     + '</strong><p class="muted">Analogia dzienna z Yahoo · ' + escape(case['ticker'])
                     + '</p><p>Zmiana dzienna: ' + pct(f['movement_pct'])
                     + '<br>RVOL pełnej sesji: ' + format(f['closed_rvol'], '.2f').replace('.', ',')
                     + '×</p><p>' + '<br>'.join(results) + '</p><details><summary>Układ techniczny</summary><p>'
                     + escape(event_text) + '</p><p>SMA 10/30: ' + pct(f['sma_gap_pct'])
                     + '<br>Cena względem SMA 10: ' + pct(f['price_sma10_pct'])
                     + '<br>MACD / cena: ' + pct(f['macd_hist_pct']) + '</p></details></article>')
    return STYLE + '<div class="ki-compare-grid">' + ''.join(cards) + '</div>'


def render(store):
    from signal_period_view import render as render_period
    render_period(store)
