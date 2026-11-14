"""Shared, as-of facts: corporate actions, price basis and trend horizons.

No provider calls, price rewriting, portfolio changes or investment forecasts.
Yahoo OHLC are already split adjusted; never apply the split a second time.
"""
import html
import math
from datetime import datetime, timedelta, timezone

VERSION = 1


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def positive(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def yahoo_actions(frame, observed_at):
    """Read the actions columns returned with the SAME OHLC request (no new call)."""
    observed = stamp(observed_at)
    result = []
    if observed is None or 'Stock Splits' not in frame.columns:
        return result
    for index, value in frame['Stock Splits'].items():
        at = stamp(index.isoformat())
        if positive(value) and value != 1 and at and at <= observed:
            result.append({'kind': 'REVERSE_SPLIT' if value < 1 else 'SPLIT',
                           'effective_at': at.isoformat(), 'new_per_old': float(value),
                           'observed_at': observed_at, 'source': 'Yahoo Finance actions',
                           'status': 'PROVIDER_REPORTED'})
    return sorted(result, key=lambda item: item['effective_at'])[-20:]


def price_basis(snapshot, reference, now=None):
    """Quarantine mismatched scales. A large gap alone never proves a split."""
    at = stamp(now or snapshot.get('acquired_at'))
    anchor = (reference or {}).get('close')
    price = snapshot.get('price')
    recent = [a for a in snapshot.get('corporate_actions', [])
              if stamp(a.get('effective_at')) and stamp(a.get('observed_at')) and at
              and stamp(a['effective_at']) <= at and stamp(a['observed_at']) <= at
              and at - stamp(a['effective_at']) <= timedelta(days=10)
              and positive(a.get('new_per_old'))]
    result = {'version': VERSION, 'as_of': snapshot.get('acquired_at'), 'status': 'NO_ACTION_REPORTED',
              'blocked': False, 'events': recent, 'reason': 'Brak zgłoszonej operacji w ostatnich 10 dniach; to nie dowodzi jej braku.'}
    if not positive(anchor) or not positive(price):
        return {**result, 'status': 'REFERENCE_UNAVAILABLE', 'blocked': True,
                'reason': 'Brak poprawnej ceny lub bazy do kontroli jednostki akcji.'}
    # Compare a closed previous-session candle from today's fetch, not an old cached snapshot.
    day = (reference or {}).get('session_date')
    comparable = [r for r in snapshot.get('chart_history', [])
                  if str(r.get('time', ''))[:10] == day and r.get('status') == 'CLOSED'
                  and stamp(r.get('end')) and stamp(r['end']) <= at and positive(r.get('close'))]
    provider_close = comparable[-1]['close'] if comparable else None
    result['cached_reference'] = anchor
    result['same_fetch_previous_close'] = provider_close
    for action in recent:
        # A cache collected before the action may be in the OLD share unit.
        if day and day < action['effective_at'][:10]:
            if provider_close is None:
                return {**result, 'status': 'ACTION_BASIS_UNVERIFIED', 'blocked': True,
                        'reason': 'Operacja na akcjach: brak porównywalnej świecy poprzedniej sesji; poziomy wymagają kontroli.'}
            ratio = provider_close / anchor
            factor = 1 / action['new_per_old']
            if math.isclose(ratio, factor, rel_tol=.12) and not math.isclose(ratio, 1, rel_tol=.12):
                return {**result, 'status': 'ACTION_SCALE_MISMATCH', 'blocked': True,
                        'reason': 'Potwierdzona przez dostawcę operacja na akcjach i różne jednostki ceny oraz starej bazy. Bez procentowego sygnału i SL/TP.'}
            if not math.isclose(ratio, 1, rel_tol=.12):
                return {**result, 'status': 'ACTION_BASIS_UNVERIFIED', 'blocked': True,
                        'reason': 'Po operacji na akcjach nie potwierdzono zgodności bazy z nowym szeregiem cen.'}
    # Guard even when the provider failed to report an action (do NOT infer its ratio).
    if max(price / anchor, anchor / price) >= 4:
        return {**result, 'status': 'UNEXPLAINED_PRICE_DISCONTINUITY', 'blocked': True,
                'reason': 'Skok jednostki ceny co najmniej 4×; przyczyna wymaga sprawdzenia. Nie przypisano splitu na podstawie samej ceny.'}
    if recent:
        result.update(status='ACTION_BASIS_VERIFIED', reason='Operacja zgłoszona przez Yahoo; baza zgodna z historią z tego odczytu. Nie przeliczano cen ponownie.')
    return result


def classify(rows, fast, slow, slope_bars, label):
    closes = [r['close'] for r in rows]
    required = slow + slope_bars
    base = {'label': label, 'bars': len(rows), 'required_bars': required,
            'first': rows[0]['time'] if rows else None, 'last': rows[-1]['time'] if rows else None,
            'status': 'INSUFFICIENT', 'direction': 'UNKNOWN'}
    if len(closes) < required:
        return {**base, 'reason': 'Za mało zamkniętych świec dla tego horyzontu.'}
    short = sum(closes[-fast:]) / fast
    long = sum(closes[-slow:]) / slow
    old_long = sum(closes[-slow-slope_bars:-slope_bars]) / slow
    slope = (long / old_long - 1) * 100
    direction = ('UP' if closes[-1] > short > long and slope > .1 else
                 'DOWN' if closes[-1] < short < long and slope < -.1 else 'MIXED')
    return {**base, 'status': 'READY', 'direction': direction, 'fast_ma': short, 'slow_ma': long,
            'slow_slope_pct': slope, 'last_close': closes[-1],
            'reason': 'Cena względem średnich '+str(fast)+'/'+str(slow)+' i nachylenie wolniejszej średniej; układ mieszany nie potwierdza kierunku.'}


def closed_rows(rows, at):
    """Reject duplicate times and invalid/future/incomplete candles, never fill gaps."""
    seen = set(); result = []
    for row in rows:
        start, end = stamp(row.get('time')), stamp(row.get('end'))
        if (not start or not end or end > at or start >= end or start in seen
                or row.get('status') != 'CLOSED' or not positive(row.get('close'))):
            continue
        seen.add(start); result.append(row)
    return sorted(result, key=lambda row: stamp(row['time']))


def trends(snapshot, daily_rows, basis):
    at = stamp(snapshot.get('acquired_at'))
    blocked = basis.get('blocked', False)
    hourly = closed_rows(snapshot.get('chart_history', []), at) if at and not blocked else []
    hourly = [r for r in hourly if stamp(r['end'])-stamp(r['time'])==timedelta(hours=1)]
    daily = closed_rows(daily_rows, at) if at and not blocked else []
    # OHLC across cached fetches may use different units after a split: suppress until a full new daily fetch.
    # Intraday uses only this regular session, never yesterday's bars disguised as today's trend.
    session_day = str(snapshot.get('candle_time', ''))[:10]
    hourly = [r for r in hourly if r['time'][:10] == session_day]
    groups = {'session': classify(hourly, 2, 3, 1, 'Śródsesyjny · zamknięte 1h'),
              'short': classify(daily, 5, 20, 5, 'Krótki · około 1–4 tygodni'),
              'medium': classify(daily, 20, 50, 10, 'Średni · około 1–3 miesięcy'),
              'long': classify(daily, 50, 200, 10, 'Długi · około 3–12 miesięcy')}
    short, long = groups['short']['direction'], groups['long']['direction']
    relation = ('Wzrost krótkoterminowy wewnątrz trendu spadkowego; odwrócenie długiego trendu niepotwierdzone.'
                if short == 'UP' and long == 'DOWN' else
                'Korekta krótkoterminowa wewnątrz trendu wzrostowego.' if short == 'DOWN' and long == 'UP' else
                'Zgodny kierunek krótkiego i długiego trendu.' if short == long and short in ('UP', 'DOWN') else
                'Horyzonty mieszane lub niepełne; brak podstaw do wspólnego kierunku.')
    return {'version': VERSION, 'as_of': snapshot.get('acquired_at'), 'horizons': groups,
            'relationship': basis['reason'] if blocked else relation,
            'method': 'Zamknięte świece 1h i 1d; średnie oraz ich nachylenie. To klasyfikacja historyczna, bez prognozy.'}


def select_daily_history(api, stored, fresh, snapshot, reference=None):
    """Select compatible saved history; a partial fetch must not erase a year."""
    at = stamp(snapshot['acquired_at'])
    actions = snapshot.get('corporate_actions') or []
    cutovers = [stamp(a.get('effective_at')) for a in actions
                if stamp(a.get('effective_at')) and stamp(a.get('effective_at')) <= at]
    cutover = max(cutovers) if cutovers else None
    def valid(rows):
        return [r for r in closed_rows(rows, at)
                if all(positive(r.get(k)) for k in ('open','high','low','close'))
                and r['low'] <= min(r['open'],r['close']) <= max(r['open'],r['close']) <= r['high']
                and stamp(r['end']) >= at-timedelta(weeks=52)]
    database = []
    for raw in stored:
        r = dict(raw)
        metadata = api.load_payload(r.get('metadata') or '{}')
        acquired = stamp(metadata.get('acquired_at'))
        if acquired and acquired > at or cutover and (not acquired or acquired < cutover):
            continue
        database.append({'time':r['session_date']+'T00:00:00+00:00',
                         'end':r['closed_at'],'status':'CLOSED',
                         **{k:r.get(k) for k in ('open','high','low','close','volume')}})
    database = valid(database)
    cache_at = stamp(fresh.get('acquired_at'))
    cache = valid(fresh.get('rows') or []) if cache_at and cache_at <= at and (not cutover or cache_at >= cutover) else []
    by_day = {r['time'][:10]:r for r in database}
    conflict = any(r['time'][:10] in by_day and any(
        not math.isclose(r[k],by_day[r['time'][:10]][k],rel_tol=.02)
        for k in ('open','high','low','close')) for r in cache)
    rows = cache if conflict else list({**by_day,**{r['time'][:10]:r for r in cache}}.values())
    rows.sort(key=lambda r:stamp(r['time']))
    matrix = snapshot.get('price_matrix') or {}
    day = (reference or {}).get('session_date') or matrix.get('reference_session')
    anchor = (reference or {}).get('close') or matrix.get('anchor_price')
    cached_reference = [r for r in fresh.get('rows',[]) if str(r.get('time',''))[:10] == day]
    if cache_at and cache_at <= at and cached_reference and positive(anchor) and (
            not positive(cached_reference[-1].get('close')) or
            not math.isclose(cached_reference[-1]['close'],anchor,rel_tol=.02)):
        return []
    match = [r for r in rows if r['time'][:10] == day]
    if ((snapshot.get('price_basis') or {}).get('blocked') or
            match and positive(anchor) and not math.isclose(match[-1]['close'],anchor,rel_tol=.02) or
            rows and at-stamp(rows[-1]['end']) > timedelta(days=7)):
        rows = []
    return rows[-260:]


def attach(api, store, snapshot):
    """One bounded, local package used by detector, AI, ranking and readers."""
    with store.connection() as c:
        at = api.parse_market_time(snapshot['acquired_at'])
        ref = api._daily_reference(c, snapshot['ticker'], at)
        rows = c.execute('SELECT * FROM daily_candles WHERE ticker=? ORDER BY session_date DESC LIMIT 270',
                         (snapshot['ticker'],)).fetchall()
        cached = c.execute('SELECT payload FROM runtime WHERE key=?', ('market_intelligence:daily:'+snapshot['ticker'],)).fetchone()
        news = c.execute('SELECT payload FROM runtime WHERE key=?', ('market_intelligence:news:'+snapshot['ticker'],)).fetchone()
        official = c.execute('SELECT payload FROM runtime WHERE key=?', ('market_intelligence:official:'+snapshot['ticker'],)).fetchone()
    fresh = api.load_payload(cached[0]) if cached else {}
    if stamp(fresh.get('acquired_at')) and stamp(fresh['acquired_at']) <= at:
        actions = { (a['effective_at'], a['new_per_old']): a for a in
                   list(fresh.get('corporate_actions', []))+list(snapshot.get('corporate_actions', [])) }
        snapshot['corporate_actions'] = list(actions.values())
    else:
        fresh = {}
    basis = price_basis(snapshot, ref, snapshot['acquired_at'])
    snapshot['price_basis'] = basis
    daily = select_daily_history(api, rows, fresh, snapshot, ref)
    snapshot['daily_history_selection'] = {'sessions':len(daily),
        'first':daily[0]['time'][:10] if daily else None,
        'last':daily[-1]['time'][:10] if daily else None}
    if basis.get('events') or basis.get('blocked'):
        snapshot['historical_52w']=None  # Old cached price-based statistics may use pre-action units.
    snapshot['trend_context'] = trends(snapshot, daily, basis)
    saved_news=api.load_payload(news[0]) if news else {}
    snapshot['news_watch'] = (saved_news if stamp(saved_news.get('checked_at')) and stamp(saved_news['checked_at'])<=at
                              else {'status': 'NOT_CHECKED', 'reason': 'Brak niezależnego sprawdzenia informacji dostępnego w chwili tego odczytu.'})
    notices=api.load_payload(official[0]) if official else {}
    snapshot['official_notices'] = {'sources':[lead for lead in notices.get('sources',[]) if stamp(lead.get('observed_at'))
                                              and stamp(lead['observed_at'])<=at and stamp(lead.get('published_at')) and stamp(lead['published_at'])<=at]}
    return snapshot


def refresh_blocked_reference(api, store, snapshot):
    """Re-fetch raw daily data, at most once/30 min per ticker. Never synthesize prices."""
    if not (snapshot.get('price_basis') or {}).get('blocked'):
        return snapshot
    at = stamp(snapshot['acquired_at']); key = 'market_intelligence:basis_retry:'+snapshot['ticker']
    with store.transaction() as c:
        row = c.execute('SELECT updated_at FROM runtime WHERE key=?', (key,)).fetchone()
        if row and at-stamp(row[0]) < timedelta(minutes=30):
            return snapshot
        c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)', (key, '{}', at.isoformat()))
    try:
        daily = api.fetch_market(snapshot['ticker'], '1d')
        if not daily.get('daily_history'):
            return snapshot
        api._save_daily_history(store, snapshot['ticker'], daily['daily_history'], daily['acquired_at'],
                                daily.get('source', 'Yahoo Finance'), daily.get('rejected_source_rows'))
        with store.transaction() as c:
            c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',
                      ('market_intelligence:daily:'+snapshot['ticker'],
                       api.json_text({'rows':daily['daily_history'], 'corporate_actions':daily.get('corporate_actions', []),
                                      'acquired_at':daily['acquired_at']}),daily['acquired_at']))
        # Its acquisition is newer than the 1h snapshot: use only for basis verification,
        # and keep trend/as-of evidence from the next 1h acquisition, never use future data.
        snapshot['price_basis']['refresh_status'] = 'Nowa historia zapisana; kontrola w kolejnym odczycie 1h.'
        return snapshot
    except (api.MarketRateLimitError, api.MarketFetchCapacityError):
        raise
    except Exception as exc:
        snapshot['price_basis']['refresh_error_type'] = type(exc).__name__
        return snapshot


def cards(snapshot):
    """Small wrapping cards suitable for phone/tablet; text carries the meaning too."""
    trend = snapshot.get('trend_context') or {}; basis = snapshot.get('price_basis') or {}
    if not trend and not basis:
        return ''
    esc = lambda value: html.escape(str(value))
    result = '<div class="ki-context" style="display:flex;flex-wrap:wrap;gap:8px;margin:10px 0">'
    labels = {'UP': ('↑ Wzrostowy', '#164d36'), 'DOWN': ('↓ Spadkowy', '#622f35'),
              'MIXED': ('↔ Mieszany', '#615020'), 'UNKNOWN': ('— Brak danych', '#39434f')}
    for h in trend.get('horizons', {}).values():
        text, color = labels[h['direction']]
        result += '<div style="flex:1 1 160px;padding:9px;border-radius:7px;background:'+color+';color:#fff">'+esc(h['label'])+'<br><b>'+esc(text)+'</b><br>'+esc('Dane: '+str(h['bars'])+' · minimum: '+str(h['required_bars']))+'</div>'
    result += '</div><p>'+esc(trend.get('relationship', ''))+'</p>'
    if basis.get('blocked') or basis.get('events'):
        result += '<p><b>Jednostka akcji:</b> '+esc(basis.get('reason', ''))+'</p>'
    news = snapshot.get('news_watch') or {}
    result += '<p><b>Informacje emitenta:</b> '+esc(news.get('label') or news.get('reason') or news.get('status', 'Brak sprawdzenia'))+'</p>'
    for source in ((snapshot.get('official_notices') or {}).get('sources') or [])[-3:]:
        result += '<p><b>Komunikat giełdy:</b> <a href="'+esc(source['url'])+'">'+esc(source['title'])+'</a> · '+esc(source['published_at'])+'</p>'
    return result
