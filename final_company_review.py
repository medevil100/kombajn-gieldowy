"""Independent final company reviews, bounded per-cycle work and one digest.

No cross-company model prompt. Existing issuer-isolated research/AI jobs retain
their complete evidence. This module only qualifies, schedules and groups them.
"""
from datetime import timedelta,timezone
import hashlib
import json
import re
import session_context
import early_company_review as early_review
import company_orchestrator as orchestrator

LIMIT=6
SETTING='final_company_review_enabled'
MIN_REVIEW_MINUTES=15
MIN_PRICE_CHANGE_PCT=1.0
UPDATE_REASONS={
    'PRICE_CHANGED':'Cena zmieniła się o co najmniej jeden procent od poprzedniej oceny.',
    'NEW_CLOSED_HOUR':'Dostępna jest kolejna pełna zamknięta świeca z obrotem.',
    'TECHNICAL_STATE_CHANGED':'Zmienił się układ wskazań technicznych.',
    'ACTIVITY_THRESHOLD_REACHED':'Nowy wolumen osiągnął średnią pełnej godziny.',
    'CONFIRMATION_COMPLETED':'Wstępny ruch uzyskał trzy potwierdzenia aktywności.',
    'ASSESSMENT_IN_PROGRESS':'Poprzednia ocena tej spółki jeszcze trwa.',
    'REVIEW_COOLDOWN':'Od danych poprzedniej oceny nie minęło piętnaście minut.',
    'NO_NEW_MARKET_DATA':'Brak nowszego odczytu rynku.',
    'NO_NEW_MARKET_ACTIVITY':'Nowszy odczyt nie zawiera nowego wolumenu.',
    'NO_MATERIAL_CHANGE':'Nie zmieniły się istotnie cena, technika ani aktywność; brak nowej pełnej świecy.',
    'PREVIOUS_ASSESSMENT_UNAVAILABLE':'Nie można potwierdzić poprzedniej oceny; wymagana kontrola.',
    'INCOMPARABLE_ASSESSMENT':'Odczyty nie są porównywalne z poprzednią oceną.'}


def intraday_gate(api,c,snapshot,previous_event_id,current):
    """A new market assessment, never a retry/reset of the previous provider job."""
    def result(allowed,reason,**facts):return {'allowed':allowed,'reason':reason,**facts}
    row=c.execute('''SELECT e.payload,j.state FROM events e
                     LEFT JOIN analysis_jobs j ON j.event_id=e.id WHERE e.id=?''',
                  (previous_event_id,)).fetchone()
    if not row:return result(False,'PREVIOUS_ASSESSMENT_UNAVAILABLE')
    if row['state'] not in ('DONE','FAILED','REVIEW_REQUIRED','FILTERED'):
        return result(False,'ASSESSMENT_IN_PROGRESS')
    old=(api.load_payload(row['payload']) or {}).get('snapshot') or {}
    if (snapshot.get('ticker')!=old.get('ticker') or snapshot.get('interval')!=old.get('interval')
        or snapshot.get('currency')!=old.get('currency')):
        return result(False,'INCOMPARABLE_ASSESSMENT')
    try:
        at,previous=(api.parse_market_time(s['acquired_at']) for s in (snapshot,old))
        start,old_start=(api.parse_market_time(s['candle_time']) for s in (snapshot,old))
    except (ValueError,TypeError,KeyError):return result(False,'INCOMPARABLE_ASSESSMENT')
    if at<=previous or at>current or start<old_start:return result(False,'NO_NEW_MARKET_DATA')
    if (at-previous).total_seconds()<MIN_REVIEW_MINUTES*60:
        return result(False,'REVIEW_COOLDOWN',previous_at=previous.isoformat())
    volume,old_volume=snapshot.get('volume'),old.get('volume')
    activity=(api.finite_number(volume,True) and
              (start>old_start or (start==old_start and api.finite_number(old_volume)
                                   and volume>old_volume)))
    if not activity:return result(False,'NO_NEW_MARKET_ACTIVITY')
    if not api.finite_number(snapshot.get('price'),True) or not api.finite_number(old.get('price'),True):
        return result(False,'INCOMPARABLE_ASSESSMENT')
    change=(snapshot['price']/old['price']-1)*100
    facts={'previous_event_id':previous_event_id,'previous_at':previous.isoformat(),
           'current_at':at.isoformat(),'price_change_since_assessment_pct':change}
    if early_review.is_event(api.load_payload(row['payload'])) and api.two_candle_confirmation(snapshot,current):
        return result(True,'CONFIRMATION_COMPLETED',**facts)
    if abs(change)>=MIN_PRICE_CHANGE_PCT-1e-10:
        return result(True,'PRICE_CHANGED',**facts)
    closed=snapshot.get('previous_closed') or {};old_closed=old.get('previous_closed') or {}
    try:
        end=api.parse_market_time(closed['end']);begin=api.parse_market_time(closed['time'])
        old_end=api.parse_market_time(old_closed['end']) if old_closed.get('end') else previous
        if (closed.get('status')=='CLOSED' and (end-begin).total_seconds()==3600
            and previous<end<=at and end>old_end and api.finite_number(closed.get('volume'),True)):
            return result(True,'NEW_CLOSED_HOUR',closed_hour=end.isoformat(),**facts)
    except (ValueError,TypeError,KeyError):pass
    def signature(s):
        indicators=s.get('indicators') or {};price=s.get('price')
        sign=lambda v:1 if v>0 else -1 if v<0 else 0
        values=(price-indicators['ma_fast'] if api.finite_number(indicators.get('ma_fast')) else None,
                indicators.get('last_macd_hist'),
                indicators['plus_di']-indicators['minus_di']
                if all(api.finite_number(indicators.get(k)) for k in ('plus_di','minus_di')) else None,
                indicators['rsi']-50 if api.finite_number(indicators.get('rsi')) else None)
        rsi=indicators.get('rsi')
        return tuple(sign(v) if api.finite_number(v) else None for v in values)+(
            'OVERBOUGHT' if api.finite_number(rsi) and rsi>70 else
            'OVERSOLD' if api.finite_number(rsi) and rsi<30 else
            'NEUTRAL' if api.finite_number(rsi) else 'MISSING',)
    if signature(snapshot)!=signature(old):return result(True,'TECHNICAL_STATE_CHANGED',**facts)
    rv,old_rv=snapshot.get('rvol'),old.get('rvol')
    if (start==old_start and api.finite_number(rv,True) and api.finite_number(old_rv,True)
        and old_rv<1<=rv):return result(True,'ACTIVITY_THRESHOLD_REACHED',**facts)
    return result(False,'NO_MATERIAL_CHANGE',**facts)


class ScriptAPI:
    """Use the callback's own globals, including Streamlit fragment reruns.

    Streamlit may replace sys.modules['__main__'] independently of a retained
    callback. Its function globals still hold the correct KI functions.
    """
    def __init__(self,namespace):
        self._namespace=namespace

    def __getattr__(self,name):
        try:return self._namespace[name]
        except KeyError:raise AttributeError('Brak funkcji KI w przestrzeni widoku: '+name) from None


def script_api(namespace):
    return ScriptAPI(namespace)


def enabled(settings):
    return settings.get(SETTING) is True


def ensure(c):
    c.execute('''CREATE TABLE IF NOT EXISTS company_review_batches(
        id TEXT PRIMARY KEY, slot TEXT NOT NULL UNIQUE, cycle_id TEXT NOT NULL,
        state TEXT NOT NULL, created_at TEXT NOT NULL, deadline TEXT NOT NULL,
        payload TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS company_review_seen(
        ticker TEXT NOT NULL, session TEXT NOT NULL, direction TEXT NOT NULL,
        batch_id TEXT NOT NULL, event_id TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(ticker,session,direction))''')


def exists(c):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='company_review_batches'").fetchone() is not None


def slot_at(at):
    at=at.astimezone(timezone.utc)
    return at.replace(minute=at.minute//15*15,second=0,microsecond=0).isoformat()


def event_id_for(sequence_id,batch_id):
    return 'final_'+hashlib.sha256((sequence_id+'|'+batch_id).encode()).hexdigest()[:32]


def release_unstarted(api,c,current):
    """Release only reservations whose preparation failed BEFORE any batch event.

    Never reset analysis_jobs/research/outbox or replay a failed provider call.
    The next attempt, if any, must come from a newly validated scanner reading.
    """
    rows=c.execute('''SELECT s.*,b.payload FROM company_review_seen s
                      JOIN company_review_batches b ON b.id=s.batch_id WHERE b.state='EMPTY' ''').fetchall()
    for row in rows:
        day=current.astimezone(api.exchange_zone(row['ticker'])).date().isoformat()
        if row['session']!=day:continue
        payload=api.load_payload(row['payload'])
        failed=any(item.get('event_id')==row['event_id'] and item.get('status')=='PREPARATION_FAILED'
                   and item.get('error_type')=='IntegrityError' for item in payload.get('diagnostics',[]))
        if not failed:continue
        started=c.execute("SELECT 1 FROM events WHERE ticker=? AND json_extract(payload,'$.company_review_batch')=? LIMIT 1",
                          (row['ticker'],row['batch_id'])).fetchone()
        if started:continue
        c.execute('DELETE FROM company_review_seen WHERE ticker=? AND session=? AND direction=? AND batch_id=?',
                  (row['ticker'],row['session'],row['direction'],row['batch_id']))
        payload=api.load_payload(c.execute('SELECT payload FROM company_review_batches WHERE id=?',(row['batch_id'],)).fetchone()[0])
        payload.setdefault('recovery',[]).append({'ticker':row['ticker'],'at':current.isoformat(),
            'status':'UNSTARTED_RESERVATION_RELEASED','reason':'Brak zdarzenia i zadania tej partii; bez ponawiania dostawców.'})
        c.execute('UPDATE company_review_batches SET payload=? WHERE id=?',(api.json_text(payload),row['batch_id']))


def background(api,store,snapshot):
    """Read cached material for THIS issuer only, never fetch another provider."""
    ticker=snapshot['ticker'];at=api.parse_market_time(snapshot['acquired_at'])
    data={'ticker':ticker,'as_of':snapshot['acquired_at'],
          'scope':'Tło tej spółki; nie dowód przyczyny ruchu ani skuteczności sygnału.'}
    with store.connection() as c:
        row=c.execute('SELECT payload,updated_at FROM runtime WHERE key=?',('fundamentals_alpha:'+ticker,)).fetchone()
        if row and api.parse_market_time(row['updated_at'])<=at:
            raw=api.load_payload(row['payload'])
            data['fundamentals']={k:raw[k] for k in ('status','summary','fetched_at','updated_at') if k in raw}
            data['fundamentals']['cached_at']=row['updated_at']
        else:data['fundamentals']={'status':'UNAVAILABLE'}
        end=at.astimezone(api.exchange_zone(ticker)).date()
        daily=c.execute('''SELECT session_date,open,high,low,close,volume FROM daily_candles
                           WHERE ticker=? AND session_date>=? AND session_date<? ORDER BY session_date DESC LIMIT 260''',
                        (ticker,(end-timedelta(weeks=52)).isoformat(),end.isoformat())).fetchall()
        ordered=list(reversed(daily))
        history={'status':'AVAILABLE' if daily else 'UNAVAILABLE','sample_count':len(daily),
             'raw_location':'daily_candles; wszystkie świece zachowane w KI, do AI trafia wyliczone podsumowanie.',
             'note':'Zapisane zakończone sesje tej spółki; niekoniecznie komplet 52 tygodni.'}
        if ordered:
            last=ordered[-1]['close']
            history.update(period_from=ordered[0]['session_date'],period_to=ordered[-1]['session_date'],
                last_close=last,high=max(r['high'] for r in ordered),low=min(r['low'] for r in ordered),
                mean_volume_last_20=sum(r['volume'] for r in ordered[-20:])/len(ordered[-20:]),
                price_change_by_sessions={str(h):(last/ordered[-1-h]['close']-1)*100
                    for h in (1,5,20,60,252) if len(ordered)>h})
        data['daily_history']=history
        confirmations=c.execute('''SELECT confirmed_at,price,change_pct,currency FROM signal_confirmations
                                  WHERE ticker=? AND confirmed_at<? ORDER BY confirmed_at DESC LIMIT 20''',
                                (ticker,snapshot['acquired_at'])).fetchall()
        data['earlier_confirmations']=[dict(r) for r in confirmations]
        data['outcomes_note']='Same daty dawnych potwierdzeń nie dowodzą ich skuteczności; nie wyliczaj prawdopodobieństwa zysku.'
    outcomes=api.signal_session_outcomes(store,snapshot['acquired_at'],only_ticker=ticker)
    groups={}
    for row in outcomes:
        key=row['direction']+' · '+str(row['horizon'])+' sesji'
        group=groups.setdefault(key,{'computed':0,'missing':0,'waiting':0,'mean_price_change_pct':None})
        if row['status']=='Obliczono' and api.finite_number(row['change']):
            count=group['computed'];mean=group['mean_price_change_pct'] or 0.
            group['computed']+=1;group['mean_price_change_pct']=(mean*count+row['change'])/(count+1)
        elif row['status']=='Brak danych z sesji':group['missing']+=1
        else:group['waiting']+=1
    data['own_signal_outcomes']={'window_days':30,'groups':groups,
          'note':'Opisowe wyniki wyłącznie tej spółki; próby mogą się nakładać. To zmiana ceny, bez kosztów i bez dowodu rentowności lub prawdopodobieństwa kontynuacji.'}
    return data


def add_schema(schema,manifest):
    if manifest.get('purpose')!='FINAL_COMPANY_REVIEW':return
    schema['properties']['final_review']={
        'type':'object','additionalProperties':False,'required':['attention','explanation'],
        'properties':{'attention':{'type':'string','enum':['INFORM','PANEL_ONLY']},
                      'explanation':{'type':'string','minLength':30,'maxLength':320}}}
    schema['required'].append('final_review')


def validate_final(result,manifest,unsupported_story):
    final=result.get('final_review')
    if (not isinstance(final,dict) or set(final)!={'attention','explanation'}
            or final.get('attention') not in ('INFORM','PANEL_ONLY')):
        return ['Niepoprawna końcowa ocena spółki.']
    text=final.get('explanation')
    if (not isinstance(text,str) or not 30<=len(text.strip())<=320
            or re.search(r'\d|\b(?:buy|sell|kup|kupuj|sprzedaj|sprzedawaj)\b|gwarant|bezpieczn',text,re.I)
            or unsupported_story(text)):
        return ['Końcowy opis zawiera nieuprawnione twierdzenia lub ma niepoprawny zakres.']
    if final['attention']=='INFORM' and (manifest.get('local_review') or {}).get('verdict')!='ALIGNED':
        return ['Powiadomienie wymaga zgodnych wskazań tej spółki; sprzeczności pozostają w panelu.']
    if manifest.get('review_stage')==early_review.STAGE:
        movement=(result.get('assessment') or {}).get('movement','')
        if not re.search('wstępn',movement,re.I) or not re.search('nie.{0,30}zakończ|nie.{0,30}potwierdz|przed.{0,20}potwierdz',movement,re.I):
            return ['Wstępna ocena musi jawnie opisywać niezakończoną serię potwierdzeń.']
    return []


def release_reservations(c,rows):
    for row in rows:
        state='CANDIDATE' if row.get('review_stage')==early_review.STAGE else 'CONFIRMED'
        c.execute("UPDATE opportunities SET state=? WHERE sequence_id=? AND state='RESERVED'",(state,row['sequence_id']))


def prepare(api,store,cycle_id,selected,now=None,early_pool=None):
    """All local candidates remain stored; at most six NEW issuer jobs per slot."""
    current=api.parse_market_time(now or api.utc_now());slot=slot_at(current)
    batch_id='company_review_'+slot.replace(':','').replace('+','_')
    planned=[];pool=list(early_pool or [])
    with store.transaction() as c:
        ensure(c)
        release_unstarted(api,c,current)
        if c.execute('SELECT 1 FROM company_review_batches WHERE slot=?',(slot,)).fetchone():
            release_reservations(c,selected)
            return None
        for row in selected:
            snap=row['rank']['snapshot'];ticker=snap['ticker'];change=(snap.get('price_matrix') or {}).get('change_pct')
            preliminary=row.get('review_stage')==early_review.STAGE
            day=api.parse_market_time(snap['acquired_at']).astimezone(api.exchange_zone(ticker)).date().isoformat()
            direction='UP' if api.finite_number(change) and change>0 else 'DOWN'
            evidence={'snapshot':snap,'autonomous_assessment_version':1,'price_change_pct':change}
            manifest=api.build_analysis_manifest(evidence,{'sources':[]})
            local=manifest['local_review'];reason='SCHEDULED';details=api.material_issues(snap);update=None
            session=session_context.build(snap)
            control=orchestrator.assess(api,snap,manifest,store.load_section('settings',{}),current,
                early_review.STAGE if preliminary else 'CONFIRMED')
            if not control['review_allowed']:
                reason=control['reason'];details.extend(control['issues']);details.append(control['next_check'])
            else:
                update=orchestrator.previous_assessment(api,c,snap,current)
                if update:
                    if not update['allowed']:reason=update['reason']
                    details.append(UPDATE_REASONS[update['reason']])
                    control=orchestrator.assess(api,snap,manifest,store.load_section('settings',{}),current,
                        early_review.STAGE if preliminary else 'CONFIRMED',previous=update)
                if reason=='SCHEDULED' and len(planned)>=LIMIT:reason='CYCLE_LIMIT'
            if reason=='CYCLE_LIMIT':control.update(action='WAIT_FOR_CAPACITY',reason=reason,review_allowed=False,next_check='Następny cykl z nowym, nadal poprawnym materiałem.')
            orchestrator.save(api,c,control)
            new_event_id=event_id_for(row['sequence_id'],batch_id)
            pool.append({'ticker':ticker,'event_id':new_event_id,'sequence_id':row['sequence_id'],'local_verdict':local['verdict'],'state':reason,
                         'review_stage':early_review.STAGE if preliminary else 'CONFIRMED',
                         'orchestration':control,
                         'details':details,'snapshot_at':snap.get('acquired_at'),'assessed_at':current.isoformat(),
                         'session_status':session['status'],'review_update':update})
            if reason=='SCHEDULED':
                planned.append(row)
                c.execute('''INSERT INTO company_review_seen VALUES(?,?,?,?,?,?)
                             ON CONFLICT(ticker,session,direction) DO UPDATE SET
                             batch_id=excluded.batch_id,event_id=excluded.event_id,created_at=excluded.created_at''',
                          (ticker,day,direction,batch_id,new_event_id,current.isoformat()))
            else:
                release_reservations(c,[row])
        payload={'version':1,'scope':'INDEPENDENT_COMPANY_REVIEWS','pool':pool,'members':[],
                 'included':[],'diagnostics':[]}
        c.execute('INSERT INTO company_review_batches VALUES(?,?,?,?,?,?,?,?)',
                  (batch_id,slot,cycle_id,'PREPARING',current.isoformat(),
                   (current+timedelta(minutes=12)).isoformat(),api.json_text(payload),current.isoformat()))
    for row in planned:
        new_event_id=event_id_for(row['sequence_id'],batch_id)
        try:
            settings=store.load_section('settings',{})
            if not enabled(settings) or not api.service_config(settings)['pipeline_enabled']:
                payload['diagnostics'].append({'event_id':new_event_id,'status':'DISABLED_DURING_PREPARATION'})
                continue
            # The existing quote operation also verifies the issuer profile.
            quote=api.fetch_opportunity_spread(row['ticker'])
            extra={'review_stage':early_review.STAGE} if row.get('review_stage')==early_review.STAGE else {}
            if api.queue_opportunity(store,row['sequence_id'],quote,False,batch_id=batch_id,**extra):
                payload['members'].append(new_event_id)
            else:payload['diagnostics'].append({'event_id':new_event_id,'status':'NOT_QUEUED'})
        except Exception as exc:
            # No raw provider message, key or credential in diagnostics.
            payload['diagnostics'].append({'event_id':new_event_id,'status':'PREPARATION_FAILED','error_type':type(exc).__name__})
    with store.transaction() as c:
        c.execute('UPDATE company_review_batches SET state=?,payload=?,updated_at=? WHERE id=?',
                  ('OPEN' if payload['members'] else 'EMPTY',api.json_text(payload),api.utc_now(),batch_id))
        release_reservations(c,planned)
    return batch_id


def batch_live(api,store,evidence,now=None):
    batch=evidence.get('company_review_batch')
    if not batch:return True
    with store.connection() as c:
        if not exists(c):return False
        row=c.execute('SELECT state,deadline FROM company_review_batches WHERE id=?',(batch,)).fetchone()
    return bool(row and row['state'] in ('PREPARING','OPEN')
                and api.parse_market_time(now or api.utc_now())<api.parse_market_time(row['deadline']))


def due(store):
    with store.connection() as c:
        return exists(c) and c.execute("SELECT 1 FROM company_review_batches WHERE state IN ('PREPARING','OPEN') LIMIT 1").fetchone() is not None


def records(api,c,member_ids):
    result=[]
    for event_id in member_ids:
        row=c.execute('''SELECT e.id,e.ticker,e.payload,e.created_at,j.state,j.context,j.result,j.last_error,j.updated_at
                         FROM events e JOIN analysis_jobs j ON j.event_id=e.id WHERE e.id=?''',(event_id,)).fetchone()
        if row:result.append(dict(row))
    return result


def digest_message(api,items,slot):
    lines=['KI · KOŃCOWE OCENY SPÓŁEK · '+slot[:16].replace('T',' ')+' UTC',
           'Każda spółka oceniona osobno; brak porównania między spółkami.']
    for item in items:
        ev=api.load_payload(item['payload']);snap=ev['snapshot'];ctx=api.load_payload(item['context'])
        analysis=api.load_payload(item['result'])['analysis'];change=snap['price_matrix']['change_pct']
        control=item.get('orchestration') or orchestrator.report_decision(api,ev,ctx,analysis,{},api.parse_market_time(snap['acquired_at']))
        cut=lambda text,n:str(text)[:n].rsplit(' ',1)[0]+'…' if len(str(text))>n else str(text)
        lines.extend(['',('OSTRZEŻENIE SPADKOWE · ' if control['role']==orchestrator.WARNING else 'WZROST Z PLANEM · ' if control['role']==orchestrator.TOP else 'WZROST DO OBSERWACJI · ')+snap['ticker']+' '+api.pl_number(change,2,'%')
                      +' · '+api.pl_number(snap['price'],4,' '+snap['currency']),
                      'Ocena AI: '+cut(analysis['final_review']['explanation'],190),
                      'Ryzyko: '+cut(analysis['assessment']['risk'],110)])
        if early_review.is_event(ev):
            lines.insert(len(lines)-2,'Status: WSTĘPNA OCENA · '+str(snap['price_matrix']['consecutive_reads'])+'/3 potwierdzeń aktywności.')
        plan=ctx['analysis_manifest'].get('trade_plan') or {}
        if plan.get('status')=='INDICATIVE':
            lines.append('Technicznie: SL '+api.pl_number(plan['sl'],4)+' · TP '+api.pl_number(plan['tp1'],4)+' / '+api.pl_number(plan['tp2'],4))
        else:lines.append('SL/TP: '+cut(plan.get('reason') or 'brak kompletu danych',90))
    lines.append('\nPełny opis, wskaźniki, źródła i scenariusze każdej spółki: panel KI. Oferty sprawdź w XTB.')
    message='\n'.join(lines)
    if len(message)>3900:raise ValueError('Przekroczony limit zestawienia; bez obcinania raportu.')
    return message


def finalize(api,store,now=None):
    if not enabled(store.load_section('settings',{})):return False
    current=api.parse_market_time(now or api.utc_now());changed=False
    with store.connection() as c:
        if not exists(c):return False
        batches=[dict(r) for r in c.execute("SELECT * FROM company_review_batches WHERE state IN ('PREPARING','OPEN') ORDER BY created_at")]
    for batch in batches:
        if batch['state']=='PREPARING':
            if current>=api.parse_market_time(batch['deadline']):
                with store.transaction() as c:c.execute("UPDATE company_review_batches SET state='REVIEW_REQUIRED',updated_at=? WHERE id=? AND state='PREPARING'",(current.isoformat(),batch['id']))
            continue
        payload=api.load_payload(batch['payload'])
        with store.connection() as c:members=records(api,c,payload['members'])
        terminal={'DONE','FAILED','FILTERED','REVIEW_REQUIRED'}
        if any(r['state'] not in terminal for r in members) and current<api.parse_market_time(batch['deadline']):continue
        included=[];decisions=[]
        for row in members:
            status=row['state']
            if status=='DONE':
                try:
                    ev=api.load_payload(row['payload']);ctx=api.load_payload(row['context'])
                    analysis=api.validate_event_analysis(api.load_payload(row['result'])['analysis'],ev['snapshot'],ctx)
                    if api.analysis_publication_issues(analysis,True):status='INVALID_REVIEW'
                    elif (analysis.get('final_review') or {}).get('attention')!='INFORM':status='PANEL_ONLY'
                    elif not api.opportunity_delivery_valid(store,ev,current):status='STALE'
                    else:
                        with store.connection() as current_db:
                            latest_raw=current_db.execute("SELECT payload FROM observations WHERE ticker=? AND interval='1h' ORDER BY id DESC LIMIT 1",(row['ticker'],)).fetchone()
                        latest_snapshot=api.load_payload(latest_raw[0]) if latest_raw else ev['snapshot']
                        control=orchestrator.report_decision(api,ev,ctx,analysis,store.load_section('settings',{}),current,latest_snapshot)
                        if not control['notify']:status='ORCHESTRATOR_HOLD'
                        else:row['orchestration']=control;included.append(row);status='INFORM'
                except (ValueError,TypeError,KeyError):status='INVALID_REVIEW'
            if status in ('FAILED','REVIEW_REQUIRED','FILTERED','INVALID_REVIEW'):
                event=api.load_payload(row['payload']);context=api.load_payload(row.get('context') or '{}')
                before=(context.get('analysis_manifest') or {}).get('orchestration') or event.get('orchestration')
                if before:row['orchestration']=orchestrator.stopped(before,status,current)
            decisions.append({'event_id':row['id'],'ticker':row['ticker'],'status':status,
                              'orchestration':row.get('orchestration')})
        payload.update(included=[r['id'] for r in included],decisions=decisions)
        with store.transaction() as c:
            latest=c.execute('SELECT state FROM company_review_batches WHERE id=?',(batch['id'],)).fetchone()
            if not latest or latest['state']!='OPEN':continue
            state='READY' if included else 'EMPTY'
            if included:
                evidence={'kind':'FINAL_COMPANY_DIGEST','batch_id':batch['id'],'members':payload['included']}
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(batch['id'],'KI','1h',current.isoformat(),api.json_text(evidence)))
                c.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',
                          (batch['id'],batch['id'],'FINAL_COMPANY_DIGEST',digest_message(api,included,batch['slot']),
                           'PENDING' if api.telegram_delivery_active(store) else 'FILTERED',current.isoformat()))
            c.execute('UPDATE company_review_batches SET state=?,payload=?,updated_at=? WHERE id=?',
                      (state,api.json_text(payload),current.isoformat(),batch['id']))
            for item in members:
                if item.get('orchestration'):orchestrator.save(api,c,item['orchestration'])
        changed=True
    return changed


def delivery_valid(api,store,evidence,now):
    if not enabled(store.load_section('settings',{})) or evidence.get('kind')!='FINAL_COMPANY_DIGEST':return False
    with store.connection() as c:
        if not exists(c):return False
        row=c.execute('SELECT payload,state FROM company_review_batches WHERE id=?',(evidence.get('batch_id'),)).fetchone()
        if not row or row['state']!='READY':return False
        members=api.load_payload(row['payload']).get('included') or []
        if not 1<=len(members)<=LIMIT or members!=evidence.get('members'):return False
        items=records(api,c,members)
    return len(items)==len(members) and all(item['state']=='DONE' and api.opportunity_delivery_valid(store,api.load_payload(item['payload']),now) for item in items)


def claim(api,store,c,outbox_id,current):
    rows=c.execute("SELECT o.*,e.payload AS evidence_payload FROM outbox o JOIN events e ON e.id=o.event_id WHERE o.kind='FINAL_COMPANY_DIGEST' AND o.status='PENDING'"+
                   (' AND o.id=?' if outbox_id else '')+' ORDER BY o.created_at', (outbox_id,) if outbox_id else ()).fetchall()
    for row in rows:
        if not delivery_valid(api,store,api.load_payload(row['evidence_payload']),current):
            c.execute("UPDATE outbox SET status='FILTERED',last_error='Zestawienie nieaktualne przed wysyłką.',next_attempt_at=NULL WHERE id=?",(row['id'],))
        elif row['next_attempt_at'] is None or row['next_attempt_at']<=current.isoformat():
            item=dict(row);item['attempts']+=1
            c.execute("UPDATE outbox SET status='SENDING',attempts=? WHERE id=?",(item['attempts'],item['id']))
            return item
    return None


def render(api,store):
    import streamlit as st
    st.subheader('Końcowe oceny spółek')
    orchestrator.render_status(api,store)
    settings=store.load_section('settings',{})
    if not enabled(settings):
        st.info('Tryb końcowych ocen jest wyłączony. W pasku bocznym zaznacz „Końcowa ocena każdej spółki · jedno zestawienie Telegram” i zapisz ustawienia. Zapisane raporty pozostają dostępne.')
    elif not api.service_config(settings)['pipeline_enabled']:
        st.info('Końcowe oceny są włączone, ale Tavily + AI jest wyłączone. Włącz analizę w pasku bocznym i zapisz ustawienia, aby oceniać nowe potwierdzone ruchy.')
    waiting='Oczekuje na pierwsze nowe zestawienie po cyklu skanera. Raport pojawi się po zakwalifikowaniu nowej spółki i zakończeniu jej oceny AI. Dawne analizy nie są automatycznie ponawiane.'
    with store.connection() as c:
        if not exists(c):
            st.info(waiting)
            return
        batch=c.execute('SELECT * FROM company_review_batches ORDER BY created_at DESC LIMIT 1').fetchone()
        if not batch:
            st.info(waiting)
            return
        newest_state=batch['state']
        newest_payload=api.load_payload(batch['payload']);showing_previous=False
        if not api.load_payload(batch['payload']).get('members'):
            previous=c.execute("SELECT * FROM company_review_batches WHERE json_array_length(json_extract(payload,'$.members'))>0 ORDER BY created_at DESC LIMIT 1").fetchone()
            if previous:
                showing_previous=previous['id']!=batch['id'];batch=previous
        payload=api.load_payload(batch['payload']);members=records(api,c,payload['members'])
    st.caption('Każda spółka oceniana niezależnie. Pełne opisy pozostają w KI; Telegram otrzymuje jedno zestawienie do sześciu spółek po cyklu z nowym istotnym materiałem. Zapis zestawienia: '+batch['created_at'])
    st.caption('Ta sama spółka może otrzymać nową ocenę w trakcie sesji po zmianie ceny, wskazań lub aktywności albo po kolejnej pełnej świecy z obrotem. Niezmieniony odczyt nie uruchamia ponownie AI.')
    st.caption('Nowe powiadomienia dotyczą obserwacji w XTB. Nieznana przyszłość, częściowa godzina i brak kompletnego planu SL/TP pozostają zastrzeżeniami; odmowa wymaga konkretnej przesłanki tej spółki.')
    st.caption('Istotne wczesne ruchy mogą otrzymać ocenę przed trzema potwierdzeniami. Mają jawny status „wstępna ocena” i wspólny limit zestawienia.')
    labels={'PREPARING':'Zbieranie materiału','OPEN':'Analizy w toku','READY':'Zestawienie zapisane','EMPTY':'Brak nowych spółek do powiadomienia','REVIEW_REQUIRED':'Wymaga sprawdzenia'}
    st.write(labels.get(batch['state'],batch['state']))
    preparation_failed=any(item.get('status')=='PREPARATION_FAILED' for item in newest_payload.get('diagnostics',[]))
    if preparation_failed:st.warning('Przygotowanie części ocen zakończyło się błędem. Sprawdź powody poniżej; sam wybór spółki nie oznacza uruchomienia AI.')
    if newest_state=='EMPTY' and showing_previous:st.caption('W ostatnim cyklu nie było nowego zestawienia. Poniżej pozostaje poprzedni zapis z własną datą.')
    for row in members:
        with st.expander(row['ticker']+' · '+('pełna ocena AI' if row['state']=='DONE' else 'Błąd — zadanie zatrzymane' if row['state']=='FAILED' else api.polish_status(row['state'])),expanded=False):
            if row['state']!='DONE':
                from tavily_cli_adapter import sanitize_cli_diagnostic
                st.caption('Zdarzenie: '+row['created_at']+' · ostatnia aktualizacja: '+row['updated_at'])
                st.caption('Ocena nie została zakończona poprawną odpowiedzią AI. Zadanie nie jest ponawiane automatycznie.')
                if row.get('last_error'):st.warning(sanitize_cli_diagnostic(row['last_error']))
                analysis=api.load_payload(row.get('result') or '{}').get('analysis') or {}
                for issue in analysis.get('quality_issues',[]):st.write('• '+sanitize_cli_diagnostic(issue))
                continue
            ev=api.load_payload(row['payload']);s=ev['snapshot'];ctx=api.load_payload(row['context'])
            if early_review.is_event(ev):st.warning(early_review.LABEL+' · '+str(s['price_matrix']['consecutive_reads'])+'/3. To zapis stanu w chwili oceny.')
            analysis=api.load_payload(row['result'])['analysis'];final=analysis.get('final_review') or {}
            control=next((d.get('orchestration') for d in payload.get('decisions',[]) if d.get('event_id')==row['id']),None)
            if control:st.info(control['role_label'])
            selection=(api.load_payload(row['result']).get('provider') or {}).get('evidence_review') or {}
            if selection:
                st.caption('AI wybrało werdykt i dowody; pełny opis złożyło KI ze zweryfikowanych danych. To nie jest swobodny komentarz modelu.')
                st.markdown('**Warunek obserwacji wybrany przez AI**');st.write(selection.get('condition_text','Brak zapisanego warunku.'))
            st.write('Ocena końcowa: '+('do powiadomienia' if final.get('attention')=='INFORM' else 'tylko panel'))
            st.write(final.get('explanation','Brak poprawnego końcowego opisu.'))
            st.caption('Dane ceny: '+s['acquired_at']+' · raport jest zapisem tej chwili.')
            for axis,title in (('movement','Ruch i technika'),('activity','Wolumen i aktywność'),('risk','Ryzyko i ograniczenia')):
                st.markdown('**'+title+'**');st.write((analysis.get('assessment') or {}).get(axis,'Brak poprawnej oceny.'))
            session=ctx['analysis_manifest'].get('session_context') or {}
            st.markdown('**Przebieg bieżącej sesji**')
            st.caption('Dane do '+str(session.get('as_of') or s['acquired_at'])+' · świece: '
                       +str(len(session.get('candles',[])))+' · odczyty kontrolne: '+str(len(session.get('observations',[])))
                       +'. Każda świeca liczona raz; odczyty jej wolumenu są narastające.')
            summary=session.get('summary') or {}
            for key,label,unit in (('session_open_price','Otwarcie sesji',s['currency']),
                    ('observed_low','Minimum zapisanej sesji',s['currency']),('observed_high','Maksimum zapisanej sesji',s['currency']),
                    ('change_from_session_open_pct','Zmiana od otwarcia','%'),('observed_volume','Wolumen zapisanych świec','szt.')):
                if api.finite_number(summary.get(key)):st.write(label+': '+api.pl_number(summary[key],2,' '+unit))
            for bar in session.get('candles',[]):
                st.caption(bar['time']+' → '+bar['end']+' · '+('skrócona świeca' if bar['partial_interval'] else 'pełny przedział')
                           +' · O '+api.pl_number(bar['open'],4)+' · H '+api.pl_number(bar['high'],4)
                           +' · L '+api.pl_number(bar['low'],4)+' · C '+api.pl_number(bar['close'],4)
                           +' · wolumen '+api.pl_number(bar['volume'],0))
            for detail in session.get('missing',[]):st.caption(detail)
            st.markdown('**Wskaźniki — uzasadnienie AI**')
            for item in analysis.get('technical',[]):st.write(item['metric']+': '+item['interpretation'])
            st.markdown('**Źródła i kontekst**')
            sources={item['id']:item for item in ctx.get('sources',[])}
            for item in analysis.get('context',[]):
                source=sources[item['source_id']];st.write(item['fact']);st.caption(str(source.get('published_at') or '')+' · '+source['url'])
            if not analysis.get('context'):st.caption('Przyczyna ruchu nieustalona; brak przyjętego faktu źródłowego.')
            for key,title in (('hypotheses','Hipotezy'),('risks','Co osłabia sygnał'),('missing','Brakujące dane')):
                if analysis.get(key):
                    st.markdown('**'+title+'**')
                    for value in analysis[key]:st.write('• '+value)
            for line in api.trade_plan_lines(ctx['analysis_manifest'].get('trade_plan') or {},details=True):st.write(line)
            api.render_technical_events(s)
            bg=ctx['analysis_manifest'].get('company_background') or {}
            st.markdown('**Zapisane tło tej spółki**')
            history=bg.get('daily_history') or {}
            st.caption('Historia dzienna: '+str(history.get('sample_count',0))+' sesji · '
                       +str(history.get('period_from') or '—')+' → '+str(history.get('period_to') or '—')
                       +'. Podsumowanie dostępnych danych; nie gwarancja pełnego pokrycia 52 tygodni.')
            fundamental=bg.get('fundamentals') or {};summary=fundamental.get('summary') or {}
            if fundamental.get('status')=='ready' and summary:
                st.caption('Alpha Vantage · okres sprawozdawczy: '+str(summary.get('period_end') or '—')
                           +' · zapis: '+str(fundamental.get('cached_at') or '—'))
                labels_fin={'net_income':'Wynik netto kwartału','cash':'Gotówka','equity':'Kapitał własny','operating_cashflow':'Operacyjne przepływy z czterech kwartałów'}
                for key,label in labels_fin.items():
                    if api.finite_number(summary.get(key)):st.write(label+': '+api.pl_number(summary[key],2,' USD'))
            else:st.caption('Brak kompletnego zapisanego pakietu finansowego. Nie oznacza to dobrej ani złej kondycji spółki.')
            for horizon,stats in (bg.get('own_signal_outcomes') or {}).get('groups',{}).items():
                if stats['computed']:
                    st.caption(horizon+': '+str(stats['computed'])+' obliczonych przypadków; średnia zmiana ceny '
                               +api.pl_number(stats['mean_price_change_pct'],2,'%')+'. Próby mogą się nakładać; bez kosztów.')
            st.markdown('**Wszystkie wskaźniki**')
            api.render_indicator_table(s)
    with st.expander('Dlaczego pozostałe spółki nie weszły do zestawienia'):
        reasons={'SCHEDULED':'Wybrano do przygotowania oceny; zapis zadania jeszcze niepotwierdzony','CYCLE_LIMIT':'Poza limitem sześciu nowych ocen tego cyklu',
            'EARLY_DATA_GATE':'Wstępny kandydat nie spełnia bramki danych lub aktywności',
            'MISSING_REFERENCE':'Czeka na poprawną bazę poprzedniej sesji','SESSION_CLOSED':'Czeka na regularną sesję',
            'INVALID_OR_STALE_DATA':'Czeka na świeże i spójne dane','INCOMPLETE_SESSION':'Czeka na komplet świec sesji',
            'BELOW_PRICE_THRESHOLD':'Ruch nie przekracza progu ceny','MOVEMENT_NOT_READY':'Czeka na wymagany dowód aktywności',
            'MIXED':'Wskazania mieszane — materiał pozostaje w KI','ALREADY_REVIEWED':'Ten kierunek oceniono już w tej sesji',
            'RISK_DOMINANT':'Ryzyko przeważa w ocenie sygnału','CONTRADICTED':'Wskazania przeczą ruchowi',
            'INSUFFICIENT':'Za mało spójnych danych','INCOMPLETE_OR_STALE':'Dane niepełne lub odczyt nieaktualny',
            'QUEUED':'Zadanie niezależnej oceny AI zostało zapisane',
            'PREPARATION_FAILED':'Błąd przygotowania — nie utworzono zadania tej oceny',
            'NOT_QUEUED':'Nie zapisano nowego zadania: odczyt wygasł albo zadanie już istniało',
            'SESSION_HISTORY_INCOMPLETE':'Niepełny przebieg bieżącej sesji w pakiecie',
            'DISABLED_DURING_PREPARATION':'Wyłączono analizę podczas przygotowania'}
        reasons.update(UPDATE_REASONS)
        diagnostics={d['event_id']:d for d in payload.get('diagnostics',[]) if d.get('event_id')}
        for item in payload.get('pool',[]):
            diagnostic=diagnostics.get(item['event_id']) or {}
            state=diagnostic.get('status') or ('QUEUED' if item['event_id'] in payload.get('members',[]) else item['state'])
            st.write(item['ticker']+' · '+reasons.get(state,state)+(' ('+diagnostic['error_type']+')' if diagnostic.get('error_type') else ''))
            for detail in item.get('details',[]):st.caption(detail)
            if item.get('details'):st.caption('Odczyt: '+str(item.get('snapshot_at') or '—')+' · selekcja: '+str(item.get('assessed_at') or '—'))
