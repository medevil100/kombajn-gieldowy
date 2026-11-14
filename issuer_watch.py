"""Bounded independent issuer research. No GPT; reservations survive crashes.

At most 24 independent Search calls/day (UTC), one attempt per reservation;
existing research/AI queues stay separate. Source rejection is not 'no news'.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import market_intelligence as facts

SCHEMA = '''CREATE TABLE IF NOT EXISTS issuer_watch_jobs(
 id TEXT PRIMARY KEY, ticker TEXT NOT NULL, state TEXT NOT NULL,
 reason TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
 started_at TEXT, finished_at TEXT, result TEXT, error_type TEXT);
 CREATE INDEX IF NOT EXISTS issuer_watch_pending ON issuer_watch_jobs(state,created_at);
 CREATE INDEX IF NOT EXISTS issuer_watch_ticker ON issuer_watch_jobs(ticker,created_at);
 CREATE TABLE IF NOT EXISTS issuer_watch_notices(id TEXT PRIMARY KEY,created_at TEXT NOT NULL);'''

LABELS = {'QUEUED': 'W kolejce niezależnego sprawdzenia informacji',
          'RUNNING': 'Sprawdzanie informacji w toku', 'COMPLETED': 'Znaleziono zweryfikowane źródła',
          'NO_ACCEPTED_SOURCES': 'Nie przyjęto źródeł; nie oznacza to braku informacji',
          'LIMIT_REACHED': 'Osiągnięto dzienny limit niezależnych wyszukiwań',
          'KEY_MISSING': 'Brak klucza Tavily; nie wykonano wyszukiwania',
          'FAILED': 'Nie udało się sprawdzić informacji; bez automatycznego ponowienia',
          'DISABLED': 'Niezależne sprawdzanie informacji wyłączone'}


def state(api, c, ticker, status, now, **extra):
    data = {'status': status, 'label': LABELS.get(status, status), 'checked_at': now, **extra}
    c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',
              ('market_intelligence:news:'+ticker, api.json_text(data), now))
    return data


def enqueue(api, store, snapshot, now=None, reason_override=None):
    current = facts.stamp(now or snapshot['acquired_at']).astimezone(timezone.utc)
    cfg = store.load_section('settings', {})
    if not api.service_config(cfg)['pipeline_enabled'] or cfg.get('issuer_watch_enabled', True) is False:
        return None
    ticker = snapshot['ticker']; matrix = snapshot.get('price_matrix') or {}
    held = ticker in api.portfolio_tickers(store)
    score = (snapshot.get('scoring') or {}).get('score', 0)
    move = matrix.get('change_pct')
    action = (snapshot.get('price_basis') or {}).get('blocked') or (snapshot.get('price_basis') or {}).get('events')
    scores={'market_score':score}
    # Automat also displays a separate directional 0–100 score. It must trigger
    # research even when the generic bullish score is lower or the move is <2%.
    if not held and not action and api.finite_number(move) and abs(move)<cfg.get('price_threshold_pct',2.) and not (api.finite_number(score) and score>=80):
        with store.connection() as c:
            row=c.execute("SELECT payload FROM observations WHERE ticker=? AND interval='1h' AND acquired_at<? ORDER BY acquired_at DESC LIMIT 1",
                          (ticker,snapshot['acquired_at'])).fetchone()
        try:
            directional=api.opportunity_local_rank(snapshot,api.load_payload(row[0]) if row else None)
            scores['directional_score']=directional.get('score')
            if api.finite_number(directional.get('score')):score=max(score if api.finite_number(score) else 0,directional['score'])
        except (ValueError,KeyError,TypeError):
            scores['directional_score']=None
    reason = ('CORPORATE_ACTION' if action else 'PORTFOLIO' if held else 'HIGH_SCORE' if isinstance(score, (float, int)) and score >= 80
              else 'SIGNIFICANT_MOVE' if api.finite_number(move) and abs(move) >= cfg.get('price_threshold_pct', 2.) else None)
    if reason_override=='LARGE_POTENTIAL' and not action and not held:reason=reason_override
    if not reason:
        return None
    ttl = timedelta(hours=1 if reason in ('SIGNIFICANT_MOVE', 'CORPORATE_ACTION') else 6)
    with store.transaction() as c:
        c.execute("DELETE FROM issuer_watch_jobs WHERE created_at<? AND state NOT IN ('QUEUED','RUNNING')",
                  ((current-timedelta(days=14)).isoformat(),))
        old = c.execute('SELECT * FROM issuer_watch_jobs WHERE ticker=? ORDER BY created_at DESC LIMIT 1', (ticker,)).fetchone()
        if old and (old['state'] in ('QUEUED', 'RUNNING') or current - facts.stamp(old['created_at']) < ttl):
            return None
        day=current.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        used=c.execute('SELECT count(*) FROM issuer_watch_jobs WHERE started_at>=?',(day,)).fetchone()[0]
        if used>=24:
            snapshot['news_watch']=state(api,c,ticker,'LIMIT_REACHED',current.isoformat())
            return None
        # A missing key and the quota are checked by worker; queueing never makes provider calls.
        count = c.execute("SELECT count(*) FROM issuer_watch_jobs WHERE state='QUEUED'").fetchone()[0]
        if count >= 100:
            return None
        key = hashlib.sha256((ticker+current.isoformat()).encode()).hexdigest()[:24]
        c.execute('INSERT INTO issuer_watch_jobs(id,ticker,state,reason,snapshot,created_at) VALUES(?,?,?,?,?,?)',
                  (key, ticker, 'QUEUED', reason, api.json_text({k:snapshot.get(k) for k in
                      ('ticker','company_name','company_website','currency','acquired_at','candle_time','candle_end','interval')}), current.isoformat()))
        snapshot['news_watch'] = state(api, c, ticker, 'QUEUED', current.isoformat(), reason=reason,trigger_scores=scores)
    return key


def notice(api, c, ticker, identity, text, now, enabled):
    """Unique structured event + standard outbox; no independent sender or bypass."""
    key = 'issuer_'+hashlib.sha256((ticker+identity).encode()).hexdigest()[:32]
    if not enabled:
        return False
    if c.execute('SELECT 1 FROM issuer_watch_notices WHERE id=?', (key,)).fetchone():
        return False
    c.execute('INSERT INTO events VALUES(?,?,?,?,?)',
              (key, ticker, '1h', now, api.json_text({'issuer_notice': True, 'identity': identity})))
    c.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',
              (key, key, 'ISSUER_NOTICE', text[:3500], 'PENDING', now))
    c.execute('INSERT INTO issuer_watch_notices VALUES(?,?)', (key, now))
    return True


def action_notice(api, store, snapshot):
    basis = snapshot.get('price_basis') or {}
    cfg = api.service_config(store.load_section('settings', {}))
    with store.transaction() as c:
        for action in basis.get('events', []):
            ratio = action['new_per_old']
            desc = ('Scalenie: 1 nowa akcja za '+format(1/ratio, '.6g')+' starych.' if ratio < 1 else
                    'Split: '+format(ratio, '.6g')+' nowych akcji za 1 starą.')
            text = ('OPERACJA NA AKCJACH · '+snapshot['ticker']+'\n'+desc+'\nData dostawcy: '+action['effective_at']+
                    '\nŹródło: Yahoo Finance actions · odczyt '+action['observed_at']+'\n'+basis['reason']+
                    '\nHistoryczne poziomy, SL/TP i wielkość pozycji wymagają ponownej oceny. Sprawdź komunikat emitenta i dane w XTB.')
            notice(api, c, snapshot['ticker'], action['effective_at']+str(ratio), text,
                   snapshot['acquired_at'], cfg['pipeline_enabled'] and cfg['telegram_enabled'])


def pending(store):
    with store.connection() as c:
        return c.execute("SELECT 1 FROM issuer_watch_jobs WHERE state='QUEUED' LIMIT 1").fetchone() is not None


def recover(api,store):
    with store.transaction() as c:
        rows=c.execute("SELECT id,ticker FROM issuer_watch_jobs WHERE state='RUNNING'").fetchall()
        for row in rows:
            c.execute("UPDATE issuer_watch_jobs SET state='FAILED',error_type='InterruptedUnknownOutcome',finished_at=? WHERE id=?",(api.utc_now(),row['id']))
            state(api,c,row['ticker'],'FAILED',api.utc_now(),error_type='InterruptedUnknownOutcome',job_id=row['id'])
        feed=c.execute("SELECT payload FROM runtime WHERE key='market_intelligence:nasdaq_feed'").fetchone()
        if feed and api.load_payload(feed[0]).get('state')=='RUNNING':
            c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',('market_intelligence:nasdaq_feed',
                      api.json_text({'state':'FAILED','error_type':'InterruptedUnknownOutcome','checked_at':api.utc_now()}),api.utc_now()))


def process_once(api, store, keys, now=None):
    """Caller holds provider lease; no automatic retry after an uncertain Search."""
    current = facts.stamp(now or api.utc_now()).astimezone(timezone.utc); iso = current.isoformat()
    cfg = store.load_section('settings', {})
    if not api.service_config(cfg)['pipeline_enabled'] or cfg.get('issuer_watch_enabled', True) is False:
        return False
    with store.transaction() as c:
        row = c.execute("SELECT * FROM issuer_watch_jobs WHERE state='QUEUED' ORDER BY CASE reason WHEN 'CORPORATE_ACTION' THEN 0 WHEN 'PORTFOLIO' THEN 1 WHEN 'LARGE_POTENTIAL' THEN 2 WHEN 'HIGH_SCORE' THEN 3 ELSE 4 END,created_at LIMIT 1").fetchone()
        if not row:
            return False
        # A delayed job cannot research yesterday's market as if it were current.
        if current - facts.stamp(row['created_at']) > timedelta(hours=2):
            c.execute("UPDATE issuer_watch_jobs SET state='EXPIRED',finished_at=? WHERE id=?", (iso, row['id']))
            state(api, c, row['ticker'], 'FAILED', iso, reason='Wygasło oczekiwanie na sprawdzenie informacji.')
            return True
        start = current.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        used = c.execute('SELECT count(*) FROM issuer_watch_jobs WHERE started_at>=?', (start,)).fetchone()[0]
        status = 'KEY_MISSING' if not keys.get('TAVILY_API_KEY') else 'LIMIT_REACHED' if used >= 24 else None
        if status:
            c.execute('UPDATE issuer_watch_jobs SET state=?,finished_at=? WHERE id=?', (status, iso, row['id']))
            state(api, c, row['ticker'], status, iso)
            return True
        c.execute("UPDATE issuer_watch_jobs SET state='RUNNING',started_at=? WHERE id=?", (iso, row['id']))
        state(api, c, row['ticker'], 'RUNNING', iso, job_id=row['id'])
    snapshot = api.load_payload(row['snapshot'])
    snapshot['acquired_at']=iso  # Research is current; the old market trigger is not a news cutoff.
    try:
        from tavily_cli_adapter import search_sync
        cutoff = api.event_context_cutoff(snapshot).isoformat()
        # Always request business events too, not just narratives about a price movement.
        query = api.research_query(snapshot, cutoff)+(' reverse stock split corporate action' if row['reason']=='CORPORATE_ACTION' else ' latest company announcements earnings offering clinical trial stock split')
        response = search_sync(query, keys['TAVILY_API_KEY'], max_results=8, **api.event_search_arguments(snapshot, cutoff))
        context = api.normalize_tavily_context(response, snapshot, window_days=30, allow_external_domains=False)
        if row['reason']=='LARGE_POTENTIAL' and context.get('sources'):
            from tavily_cli_adapter import enrich_search_response
            enrich_search_response(response,keys['TAVILY_API_KEY'],{s['url'] for s in context['sources'][:3]})
            context=api.normalize_tavily_context(response,snapshot,window_days=30,allow_external_domains=False)
        sources = context.get('sources', [])
        status = 'COMPLETED' if sources else 'NO_ACCEPTED_SOURCES'
        # Search snippets are kept as dated leads. Full-content acceptance for AI remains separate.
        leads = [{k: s.get(k) for k in ('id', 'title', 'url', 'published_at', 'content_complete')} for s in sources]
        result = {'sources': leads, 'rejected_count': context.get('excluded', 0), 'query': query,
                  'cutoff': cutoff, 'reason': row['reason'], 'job_id': row['id'],
                  'scope': 'Wyszukiwanie informacji; brak dowodu związku wiadomości z ruchem ceny.'}
        finished=now or api.utc_now()
        with store.transaction() as c:
            c.execute('UPDATE issuer_watch_jobs SET state=?,finished_at=?,result=? WHERE id=?',
                      (status, finished, api.json_text({**result,'raw_response':response}), row['id']))
            state(api, c, row['ticker'], status, finished, **result)
            # Only publish a dated, validated issuer lead about capital restructuring; do not assert a ratio from a snippet.
            for lead in leads:
                title = (lead.get('title') or '').casefold()
                published=facts.stamp(lead.get('published_at'))
                if published and timedelta(0)<=current-published<=timedelta(days=7) and any(term in title for term in ('reverse split', 'reverse stock split', 'scalenie akcji', 'stock split', 'podział akcji')):
                    notice(api, c, row['ticker'], lead['url'],
                           'WAŻNA INFORMACJA EMITENTA · '+row['ticker']+'\n'+str(lead['title'])+'\n'+str(lead['published_at'])+
                           '\n'+lead['url']+'\nŹródło wymaga przeczytania; sprawdź datę wejścia w życie i jednostkę ceny. Brak potwierdzenia wpływu na kurs.',
                           iso, api.service_config(cfg)['telegram_enabled'])
    except Exception as exc:
        with store.transaction() as c:
            c.execute("UPDATE issuer_watch_jobs SET state='FAILED',finished_at=?,error_type=? WHERE id=?", (iso, type(exc).__name__, row['id']))
            state(api, c, row['ticker'], 'FAILED', iso, error_type=type(exc).__name__, job_id=row['id'])
    return True


def cached_search(api, store, snapshot, cutoff):
    """Reuse a prior issuer search only within one hour and never beyond the report's cutoff."""
    at=facts.stamp(cutoff)
    with store.connection() as c:
        row=c.execute("SELECT result FROM issuer_watch_jobs WHERE ticker=? AND state IN ('COMPLETED','NO_ACCEPTED_SOURCES') AND finished_at<=? ORDER BY finished_at DESC LIMIT 1",
                      (snapshot['ticker'],cutoff)).fetchone()
    data=api.load_payload(row[0]) if row else {}
    previous=facts.stamp(data.get('cutoff'))
    if previous and timedelta(0)<=at-previous<=timedelta(hours=1):
        response=data.get('raw_response')
        if isinstance(response,dict) and isinstance(response.get('results'),list):
            response['ki_cached_issuer_search']=data['job_id']
            # This is a new local reservation, not a second provider request ID.
            response['request_id']=None
            return response
    return None


def render(api, store):
    import streamlit as st
    with st.expander('Niezależne informacje emitentów · kolejka i źródła',expanded=False):
        st.caption('Portfel co 6 godzin, wynik ≥80/100 co 6 godzin, ruch ponad próg i operacje na akcjach co godzinę. Maksymalnie 24 dodatkowe Search na dobę UTC; jedno podejście, bez GPT. Otwarcie widoku nie wywołuje API.')
        with store.connection() as c:
            rows=c.execute("SELECT key,payload FROM runtime WHERE key LIKE 'market_intelligence:news:%' ORDER BY updated_at DESC LIMIT 20").fetchall()
            today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
            used=c.execute('SELECT count(*) FROM issuer_watch_jobs WHERE started_at>=?',(today,)).fetchone()[0]
        st.caption('Rezerwacje Search dzisiaj: '+str(used)+'/24. To lokalny licznik tej kolejki; pozostałe wyszukiwania KI są rozliczane osobno.')
        with store.connection() as c:
            feed=c.execute("SELECT payload FROM runtime WHERE key='market_intelligence:nasdaq_feed'").fetchone()
        if feed:
            value=api.load_payload(feed[0]);st.caption('Oficjalny kanał Nasdaq: '+str(value.get('state'))+' · '+str(value.get('checked_at',''))+' · ostatnie komunikaty, nie kompletna baza zdarzeń.')
        if not rows:st.info('Brak zarejestrowanych sprawdzeń; kolejka powstaje podczas pracy skanera.')
        for row in rows:
            data=api.load_payload(row['payload']);ticker=row['key'].rsplit(':',1)[-1]
            st.write(ticker+' · '+data.get('label',data.get('status','—')))
            st.caption(str(data.get('checked_at',''))+' · '+str(data.get('reason','')))
            for source in data.get('sources',[])[:4]:
                st.markdown('['+str(source.get('title','Źródło')).replace('[','').replace(']','')+']('+source['url']+')')
                st.caption(str(source.get('published_at') or 'Data niepotwierdzona')+' · trop informacyjny, bez potwierdzenia przyczyny ruchu')
