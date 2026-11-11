"""As-of intraday session evidence from already collected data. No providers."""
from datetime import datetime,timedelta,timezone
from functools import lru_cache
import math
from zoneinfo import ZoneInfo


def number(value,positive=False):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and (not positive or value>0)


def stamp(value):
    try:
        value=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return value if value.utcoffset() is not None else None
    except (ValueError,TypeError):return None


@lru_cache(maxsize=512)
def bounds(ticker_market,day):
    from exchange_calendars import get_calendar
    calendar=get_calendar(ticker_market)
    if not calendar.is_session(day):return None
    return (calendar.session_open(day).to_pydatetime(),calendar.session_close(day).to_pydatetime())


def valid_bar(row,at):
    start,end=stamp(row.get('time')),stamp(row.get('end'))
    if not start or not end or not start<end or start>at:return False
    if row.get('status') not in ('OPEN','CLOSED'):return False
    if (row['status']=='CLOSED' and end>at) or (row['status']=='OPEN' and not start<=at<end):return False
    if row.get('price_origin')=='carried_previous_close':return False
    if not all(number(row.get(k),True) for k in ('open','high','low','close')):return False
    if not number(row.get('volume')) or row['volume']<0:return False
    return row['low']<=min(row['open'],row['close'])<=max(row['open'],row['close'])<=row['high']


def build(snapshot):
    """One OHLCV row per candle, including the actual unfinished tail.

    A timestamp grid from the exchange calendar exposes gaps. We never fill
    them with a carried close, a daily candle or a future observation.
    """
    at=stamp(snapshot.get('acquired_at'));ticker=snapshot.get('ticker')
    result={'version':1,'status':'UNAVAILABLE','ticker':ticker,'as_of':snapshot.get('acquired_at'),
            'candles':[],'missing':[],'observations':[],
            'note':'Cała dostępna sesja do chwili odczytu, bez danych z przyszłości. Wolumen odczytów tej samej świecy jest narastający; nie sumować go wielokrotnie.'}
    if not at or not isinstance(ticker,str) or snapshot.get('interval')!='1h':
        result['missing']=['Brak tożsamości, czasu lub interwału 1h.'];return result
    zone=ZoneInfo('Europe/Warsaw' if ticker.endswith('.WA') else 'America/New_York')
    day=at.astimezone(zone).date().isoformat();result['session_date']=day
    try:limits=bounds('XWAR' if ticker.endswith('.WA') else 'XNYS',day)
    except (ValueError,KeyError):limits=None
    if not limits:
        result['missing']=['Brak potwierdzonych granic sesji.'];return result
    opening,closing=limits
    result.update(session_open=opening.isoformat(),session_close=closing.isoformat())
    if not opening<=at<=closing:
        result['missing']=['Odczyt poza regularną sesją.'];return result
    expected={};start=opening
    while start<closing and start<=at:
        expected[start]=min(start+timedelta(hours=1),closing);start+=timedelta(hours=1)
    source=list(snapshot.get('chart_history') or [])
    current={**(snapshot.get('ohlc') or {}),'time':snapshot.get('candle_time'),'end':snapshot.get('candle_end'),
             'status':snapshot.get('candle_status'),'volume':snapshot.get('volume'),
             'price_origin':snapshot.get('latest_price_origin')}
    # Current OHLCV is itself collected evidence, not a synthesized history row.
    source.append(current)
    accepted={};invalid=set()
    for raw in source:
        if not isinstance(raw,dict):continue
        start,end=stamp(raw.get('time')),stamp(raw.get('end'))
        if start not in expected:continue
        if end!=expected[start] or not valid_bar(raw,at):
            invalid.add(start);continue
        row={k:raw.get(k) for k in ('time','end','status','open','high','low','close','volume')}
        row.update(time=start.isoformat(),end=end.isoformat(),partial_interval=(end-start).total_seconds()<3600)
        if start in accepted and any(accepted[start][k]!=row[k] for k in ('open','high','low','close','volume','status')):
            invalid.add(start);continue
        accepted[start]=row
    for start in invalid:accepted.pop(start,None)
    result['candles']=[accepted[start] for start in sorted(accepted)]
    result['missing']=['Brak poprawnej świecy '+start.isoformat() for start in expected if start not in accepted]
    result['expected_candles']=len(expected)
    result['closed_full_candles']=sum(r['status']=='CLOSED' and not r['partial_interval'] for r in result['candles'])
    result['status']='COMPLETE_TO_ASOF' if accepted and not result['missing'] else 'PARTIAL' if accepted else 'UNAVAILABLE'
    if accepted:
        rows=result['candles'];first=accepted.get(opening)
        result['summary']={'observed_high':max(r['high'] for r in rows),'observed_low':min(r['low'] for r in rows),
            'observed_volume':sum(r['volume'] for r in rows),'session_open_price':first['open'] if first else None,
            'last_price':snapshot.get('price'),'change_from_previous_close_pct':(snapshot.get('price_matrix') or {}).get('change_pct'),
            'change_from_session_open_pct':(snapshot['price']/first['open']-1)*100 if first and number(snapshot.get('price'),True) else None,
            'closed_up_candles':sum(r['status']=='CLOSED' and r['close']>r['open'] for r in rows),
            'closed_down_candles':sum(r['status']=='CLOSED' and r['close']<r['open'] for r in rows)}
    return result


def gather(store,snapshot):
    result=build(snapshot)
    if not result.get('session_open'):return result
    at=stamp(snapshot['acquired_at']);opening=stamp(result['session_open'])
    with store.connection() as c:
        rows=c.execute('''SELECT acquired_at,candle_time,candle_status,
            json_extract(payload,'$.price') AS price,json_extract(payload,'$.volume') AS volume,
            json_extract(payload,'$.latest_price_origin') AS price_origin,
            json_extract(payload,'$.price_matrix.activity_evidence') AS activity_evidence,
            json_extract(payload,'$.price_matrix.consecutive_reads') AS proofs
            FROM observations WHERE ticker=? AND interval='1h' AND acquired_at>=? AND acquired_at<=?
            ORDER BY acquired_at,id''',(snapshot['ticker'],opening.isoformat(),snapshot['acquired_at'])).fetchall()
    seen=set()
    for row in rows:
        acquired=stamp(row['acquired_at']);start=stamp(row['candle_time'])
        if not acquired or not start or not opening<=start<=acquired<=at:continue
        if row['price_origin']=='carried_previous_close':
            result.setdefault('excluded_observations',[]).append({'acquired_at':row['acquired_at'],'reason':'CARRIED_PRICE'})
            continue
        if not number(row['price'],True) or not number(row['volume']) or row['volume']<0:continue
        key=(acquired,start,row['price'],row['volume'])
        if key in seen:continue
        seen.add(key)
        result['observations'].append({'acquired_at':row['acquired_at'],'candle_time':row['candle_time'],
            'price':row['price'],'volume_in_candle':row['volume'],'activity_evidence':row['activity_evidence'],'proofs':row['proofs']})
    return result


def shortened_activity_ready(snapshot):
    """Only an expected RVOL omission with a verified whole-session context."""
    if (snapshot.get('partial_interval') is not True or snapshot.get('status_basis')!='session_end'
            or snapshot.get('rvol') is not None or not number(snapshot.get('volume'),True)
            or not number(snapshot.get('average_volume'),True)):return False
    start,end=stamp(snapshot.get('candle_time')),stamp(snapshot.get('candle_end'))
    if not start or not end or not 0<(end-start).total_seconds()<3600:return False
    context=build(snapshot)
    return context['status']=='COMPLETE_TO_ASOF' and context['closed_full_candles']>=1
