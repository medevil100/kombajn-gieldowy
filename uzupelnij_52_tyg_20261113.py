"""Bounded automatic Yahoo history for all saved KI tickers; no GPT or keys."""
from datetime import timedelta
from pathlib import Path
import argparse
import json
import sqlite3
import sys


def replenish(api,store,ticker,now=None):
    at=api.parse_market_time(now or api.utc_now());key='history_52w_backfill:'+ticker
    with store.transaction() as db:
        global_row=db.execute("SELECT payload FROM runtime WHERE key='history52_global'").fetchone()
        global_state=api.load_payload(global_row[0]) if global_row else {}
        if global_state.get('next_attempt_at') and at<api.parse_market_time(global_state['next_attempt_at']):
            return {'ticker':ticker,'status':'SOURCE_BACKOFF','next_attempt_at':global_state['next_attempt_at']}
        first,last,count=db.execute('SELECT min(session_date),max(session_date),count(*) FROM daily_candles WHERE ticker=? AND session_date>=?',
            (ticker,(at-timedelta(weeks=52)).date().isoformat())).fetchone()
        required=api.required_daily_session(ticker,at,include_completed_today=True)
        if first and first<=(at-timedelta(weeks=52)+timedelta(days=7)).date().isoformat() and last>=required:
            return {'ticker':ticker,'status':'RANGE_ALREADY_COVERED','sessions':count,'first':first,'last':last}
        prior=db.execute('SELECT payload FROM runtime WHERE key=?',(key,)).fetchone()
        saved=api.load_payload(prior[0]) if prior else {}
        if saved.get('attempted_at') and at-api.parse_market_time(saved['attempted_at'])<timedelta(hours=24):
            return {'ticker':ticker,'status':'COOLDOWN','previous':saved}
        day=at.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        used=db.execute("SELECT count(*) FROM runtime WHERE key LIKE 'history_52w_backfill:%' AND json_extract(payload,'$.attempted_at')>=?",(day,)).fetchone()[0]
        if used>=48:return {'ticker':ticker,'status':'DAILY_LIMIT'}
        reservation={'attempted_at':at.isoformat(),'status':'RUNNING','requested_period':'1y'}
        db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',(key,api.json_text(reservation),at.isoformat()))
    try:
        snap=api.fetch_market(ticker,'1d')
        attempts=snap.get('history_attempts') or []
        if not any(a.get('period')=='1y' for a in attempts):raise ValueError('Pobranie nie potwierdza zakresu 1y.')
        rows=snap.get('daily_history') or []
        if not rows:raise ValueError('Źródło nie zwróciło zamkniętych sesji.')
        # Validate and save the complete source batch; never invent or adjust OHLC.
        api._save_daily_history(store,ticker,rows,snap['acquired_at'],snap.get('source','Yahoo Finance'),snap.get('rejected_source_rows'))
        with store.transaction() as db:
            db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',('market_intelligence:daily:'+ticker,
                api.json_text({'rows':rows,'corporate_actions':snap.get('corporate_actions',[]),'acquired_at':snap['acquired_at']}),snap['acquired_at']))
        first=min(api.parse_market_time(r['time']) for r in rows)
        result={**reservation,'status':'FETCHED','sessions':len(rows),'first':min(r['time'] for r in rows),
                'last':max(r['time'] for r in rows),'acquired_at':snap['acquired_at'],
                'coverage':'COVERS_START_OF_52W_WINDOW' if first<=api.parse_market_time(snap['acquired_at'])-timedelta(weeks=52)+timedelta(days=7) else 'SHORTER_SOURCE_HISTORY',
                'rejected_rows':len(snap.get('rejected_source_rows') or [])}
    except Exception as exc:
        result={**reservation,'status':'FAILED','error_type':type(exc).__name__}
    with store.transaction() as db:
        db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',(key,api.json_text(result),api.utc_now()))
        if result.get('error_type')=='MarketRateLimitError':
            db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',('history52_global',api.json_text({'next_attempt_at':(at+timedelta(hours=1)).isoformat(),'reason':'YAHOO_RATE_LIMIT'}),at.isoformat()))
    return result


def listed_tickers(db):
    raw=db.execute("SELECT payload FROM legacy_state WHERE section='tickers'").fetchone()
    tickers=json.loads(raw[0]) if raw else []
    if not isinstance(tickers,list) or not all(isinstance(t,str) for t in tickers):raise ValueError('Nietypowy zapis listy spółek.')
    attempts={r[0].split(':',1)[1]:json.loads(r[1]).get('attempted_at','') for r in db.execute("SELECT key,payload FROM runtime WHERE key LIKE 'history_52w_backfill:%'")}
    return sorted(set(tickers),key=lambda t:(attempts.get(t,''),t))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--limit',type=int,default=3)
    args=parser.parse_args()
    root=Path.home()/'ki2';path=root/'KI.matrix.sqlite3'
    if path.is_symlink() or not path.is_file():raise SystemExit('Brak zwykłego pliku bazy KI.')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        tickers=listed_tickers(db)
    print('Pełna lista KI:',len(tickers),'spółek.',flush=True)
    if not args.apply:
        print('Odczyt bez zmian. --apply: ograniczona partia Yahoo dla pełnej listy KI, bez GPT i wysyłki.');return
    sys.path.insert(0,str(root))
    import KI
    from ki2_ops_guard import provider_lease
    with provider_lease() as acquired:
        if not acquired:raise SystemExit('Trwa konserwacja; bez pobrań.')
        store=KI.Store(path)
        started=0
        for ticker in tickers:
            if not KI.valid_ticker(ticker):continue
            result=replenish(KI,store,ticker)
            if result['status'] not in ('COOLDOWN','RANGE_ALREADY_COVERED'):print(json.dumps(result,ensure_ascii=False),flush=True)
            if result['status'] in ('DAILY_LIMIT','SOURCE_BACKOFF'):break
            if result['status'] in ('FETCHED','FAILED'):started+=1
            if result.get('error_type') in ('MarketRateLimitError','MarketFetchCapacityError','MarketFetchTimeout'):break
            if started>=max(1,min(args.limit,6)):break
    print('Zapisane stare oceny AI nie zostały ponowione. Nowa historia jest dostępna dla kolejnych odczytów i ocen.')


if __name__=='__main__':main()
