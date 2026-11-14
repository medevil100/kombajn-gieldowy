"""One per-company policy shared by selection, AI, publication and read-only UI.

No model/provider calls. Evidence times and missing dependencies remain explicit;
an aligned decline is a warning, never an implied long opportunity.
"""
import copy
import hashlib
import math
from datetime import timedelta

import early_company_review as early
import session_context
from sl_tp import stamp

VERSION=1
TOP='TOP5_RISE_WITH_PLAN'
WATCH='RISING_WATCH'
WARNING='FALLING_WARNING'
PANEL='PANEL_ONLY'
LABELS={TOP:'Wzrost · kompletny plan techniczny',WATCH:'Wzrost do obserwacji · bez pełnego planu',
        WARNING:'Ostrzeżenie spadkowe',PANEL:'Tylko panel'}


def coordinate_large_movement(api,store,snapshot,cycle,now):
    """Central orchestration branch; independent of the short intraday rank."""
    import large_movement
    try:status=large_movement.consider(api,store,snapshot,cycle,now)
    except Exception as exc:
        large_movement.save_diagnostic(api,store,snapshot['ticker'],snapshot['acquired_at'],'PREPARATION_FAILED',error_type=type(exc).__name__)
        status='PREPARATION_FAILED'
    if status=='QUEUED':
        api.issuer_watch.enqueue(api,store,snapshot,now,reason_override='LARGE_POTENTIAL')
    return {'status':status,'contract':large_movement.CONTRACT,
            'scope':'Pełna ocena dużego potencjału; osobny czas, cel, ryzyko i trwała obserwacja.'}


def plan_ready(api,snapshot,plan,now):
    at=stamp(snapshot.get('acquired_at'));until=stamp(plan.get('valid_until'))
    if (plan.get('status')!='INDICATIVE' or plan.get('side')!='LONG'
        or plan.get('currency')!=snapshot.get('currency') or not at or stamp(plan.get('as_of'))!=at
        or not until or not at<=now<until<=at+timedelta(minutes=15)):
        return False
    values=[plan.get(k) for k in ('entry','sl','tp1','tp2','rr1','rr2','atr')]
    supporting=plan.get('support') or {};targets=plan.get('resistances') or []
    if not isinstance(supporting,dict) or not isinstance(targets,list) or any(not isinstance(x,dict) for x in targets):return False
    support=supporting.get('price')
    if not all(api.finite_number(v,True) for v in (*values,support)) or len(targets)<2:return False
    entry,sl,tp1,tp2,rr1,rr2,atr=values
    if not (sl<support<entry<tp1<tp2 and api.finite_number(snapshot.get('price'),True)
            and math.isclose(entry,snapshot['price'],rel_tol=1e-9,abs_tol=1e-10)
            and rr1>=1 and rr2>rr1):return False
    if not all(api.finite_number(r.get('price'),True) and stamp(r.get('time')) and stamp(r['time'])<=at for r in targets[:2]):return False
    return (math.isclose(targets[0]['price'],tp1) and math.isclose(targets[1]['price'],tp2)
            and math.isclose(rr1,(tp1-entry)/(entry-sl),rel_tol=1e-7)
            and math.isclose(rr2,(tp2-entry)/(entry-sl),rel_tol=1e-7))


def assess(api,snapshot,manifest,settings,now,stage=None,previous=None,revalidation=False):
    """Use one coherent, as-of evidence package. Do not mutate a frozen report."""
    matrix=snapshot.get('price_matrix') or {};change=matrix.get('change_pct')
    direction='UP' if api.finite_number(change) and change>0 else 'DOWN' if api.finite_number(change) and change<0 else 'UNKNOWN'
    stage=stage or (early.STAGE if matrix.get('state')=='CANDIDATE' else 'CONFIRMED')
    session=manifest.get('session_context') or session_context.build(snapshot)
    summary=session.get('summary') or {};local=manifest.get('local_review') or {}
    plan=manifest.get('trade_plan') or {};technical=manifest.get('technical') or {}
    issues=api.material_issues(snapshot)
    reason=None;action='ANALYZE_PRELIMINARY' if stage==early.STAGE else 'ANALYZE_CONFIRMED'
    next_check='Nowy zaakceptowany odczyt; ponowna ocena tylko po istotnej zmianie dowodów.'
    if (snapshot.get('price_basis') or {}).get('blocked'):
        reason='PRICE_BASIS_BLOCKED';action='WAIT_FOR_PRICE_BASIS';next_check=snapshot['price_basis']['reason']
    elif not api.daily_matrix_reference_ready(snapshot):
        reason='MISSING_REFERENCE';action='WAIT_FOR_REFERENCE';next_check='Poprawne zamknięcie wymaganej poprzedniej sesji.'
    elif not api.market_session_open(snapshot.get('ticker'),now):
        reason='SESSION_CLOSED';action='WAIT_FOR_SESSION';next_check='Nowy odczyt podczas następnej regularnej sesji.'
    elif not api.accepted_matrix_snapshot(snapshot) or not api.open_hour_fresh(snapshot,now) or issues:
        reason='INVALID_OR_STALE_DATA';action='WAIT_FOR_DATA';next_check='Świeża, spójna cena, OHLCV i wskaźniki z tego samego odczytu.'
    elif session.get('status')!='COMPLETE_TO_ASOF':
        reason='INCOMPLETE_SESSION';action='WAIT_FOR_SESSION_DATA';next_check='Komplet rzeczywistych świec sesji do chwili odczytu.'
    elif not api.finite_number(settings.get('price_threshold_pct',2.),True) or not api.finite_number(change) or abs(change)<=settings.get('price_threshold_pct',2.):
        reason='BELOW_PRICE_THRESHOLD';action='WAIT_FOR_MOVEMENT';next_check='Nowy ruch przekraczający zapisany próg ceny.'
    else:
        if stage==early.STAGE:
            gate=early.gate(api,snapshot,now,settings,allow_confirmed=revalidation,require_new_activity=not revalidation)
            qualified=gate['allowed']
            if not qualified:issues.append(gate['reason'])
        else:
            qualified=api.two_candle_confirmation(snapshot,now)
            try:
                rv=max(float(settings.get('min_rvol_for_opportunity',.5)),float(settings.get('min_rvol_absolute',.3)))
                volume=float(settings.get('min_volume_for_opportunity',1000))
                qualified=qualified and (api.shortened_activity_ready(snapshot) or
                    api.finite_number(snapshot.get('rvol')) and snapshot['rvol']>=rv) and snapshot.get('volume',0)>=volume
            except (TypeError,ValueError):qualified=False
        if not qualified:
            reason='MOVEMENT_NOT_READY';action='WAIT_FOR_ACTIVITY';next_check='Nowy dowód aktywności przy zachowanym ruchu od poprawnej bazy.'
        elif local.get('verdict')!='ALIGNED':
            reason=local.get('verdict') or 'INSUFFICIENT';action='KEEP_IN_PANEL';next_check='Zmiana konkretnej sprzeczności lub dominującego ryzyka.'
    ready=reason is None
    complete=direction=='UP' and plan_ready(api,snapshot,plan,now)
    role=(WARNING if direction=='DOWN' else TOP if complete else WATCH) if ready else PANEL
    scenario=manifest.get('scenario_plan') or {}
    data={'version':VERSION,'ticker':snapshot.get('ticker'),'as_of':snapshot.get('acquired_at'),
          'evaluated_at':now.isoformat(),'direction':direction,'confirmation_stage':stage,
          'confirmation_reads':matrix.get('consecutive_reads'),'action':action,'reason':reason or 'READY_FOR_AI',
          'review_allowed':ready,'role':role,'role_label':LABELS[role],'plan_complete':complete,
          'next_check':next_check,'issues':list(dict.fromkeys(issues)),
          'explanation':local.get('summary') if action=='KEEP_IN_PANEL' else issues[0] if issues else next_check,
          'connections':{
              'market_intelligence':manifest.get('market_intelligence') or {},
              'price':{'change_from_base_pct':change,'reference_session':matrix.get('reference_session'),
                       'change_from_open_pct':summary.get('change_from_session_open_pct')},
              'activity':{'proof':matrix.get('activity_evidence'),'volume':snapshot.get('volume'),
                          'rvol':snapshot.get('rvol'),'partial_hour':snapshot.get('candle_status')=='OPEN'},
              'technical':{'supports':technical.get('supports',[]),'contradicts':technical.get('contradicts',[]),
                           'verdict':local.get('verdict'),'decisive_reasons':local.get('required_reason_codes',[])},
              'session':{'status':session.get('status'),'candles':len(session.get('candles',[])),
                         'missing':session.get('missing',[])},
              'plan':{'status':plan.get('status'),'complete':complete,'reason':plan.get('reason'),
                      'rr1':plan.get('rr1'),'as_of':plan.get('as_of')},
              'quotes':{'status':local.get('quote_status'),'execution':local.get('execution'),
                        'spread_pct':local.get('spread_pct')},
              'sources':{'status':(manifest.get('sources') or {}).get('status'),'count':(manifest.get('sources') or {}).get('count',0)},
              'background':{'fundamentals_status':((manifest.get('company_background') or {}).get('fundamentals') or {}).get('status','NOT_LOADED'),
                            'own_history_available':bool((manifest.get('company_background') or {}).get('daily_history'))}},
          'scenario':{'base':scenario.get('base'),'invalidation':scenario.get('alternative'),
                      'valid_until':scenario.get('valid_until')},
          'limitations':list(local.get('limitations') or [])}
    if previous:
        data['previous_assessment']={k:previous.get(k) for k in ('allowed','reason','previous_event_id','previous_at')}
        if ready and not previous.get('allowed'):
            data.update(review_allowed=False,action='WAIT_FOR_AI' if previous.get('reason')=='ASSESSMENT_IN_PROGRESS' else 'WAIT_FOR_CHANGE',
                reason=previous.get('reason'),
                explanation=previous.get('message') or api.company_review.UPDATE_REASONS.get(previous.get('reason'),previous.get('reason')))
    if stage==early.STAGE:data['limitations'].append('Seria trzech potwierdzeń aktywności nie została zakończona.')
    fingerprint={k:snapshot.get(k) for k in ('ticker','currency','acquired_at','candle_time','price','volume','price_matrix','indicators')}
    data['evidence_sha256']=hashlib.sha256(api.json_text(fingerprint).encode('utf-8')).hexdigest()
    return data


def previous_assessment(api,connection,snapshot,current):
    if api.rebase_research_already_reserved(connection,snapshot):
        return {'allowed':False,'reason':'REFERENCE_RESEARCH_RESERVED',
                'message':'Po zmianie bazy research tej spółki jest już zarezerwowany w tej sesji; bez ponawiania dostawcy.'}
    if not api.company_review.exists(connection):return None
    change=(snapshot.get('price_matrix') or {}).get('change_pct')
    if not api.finite_number(change) or not change:return None
    day=api.parse_market_time(snapshot['acquired_at']).astimezone(api.exchange_zone(snapshot['ticker'])).date().isoformat()
    row=connection.execute('SELECT event_id FROM company_review_seen WHERE ticker=? AND session=? AND direction=?',
        (snapshot['ticker'],day,'UP' if change>0 else 'DOWN')).fetchone()
    if not row:return None
    return api.company_review.intraday_gate(api,connection,snapshot,row['event_id'],current)


def publish(decision,analysis):
    result=copy.deepcopy(decision)
    if not decision['review_allowed'] or (analysis.get('final_review') or {}).get('attention')!='INFORM':
        result.update(action='KEEP_IN_PANEL',reason='AI_PANEL_ONLY' if decision['review_allowed'] else decision['reason'],
                      role=PANEL,role_label=LABELS[PANEL],notify=False)
    else:
        result.update(action={TOP:'PUBLISH_RISE_WITH_PLAN',WATCH:'PUBLISH_RISING_WATCH',WARNING:'PUBLISH_FALLING_WARNING'}[result['role']],notify=True)
    return result


def stopped(decision,status,now):
    result=copy.deepcopy(decision)
    result.update(evaluated_at=now.isoformat(),review_allowed=False,notify=False,role=PANEL,role_label=LABELS[PANEL],
        reason='AI_'+status,action='WAIT_FOR_REVIEW' if status in ('FAILED','REVIEW_REQUIRED','INVALID_REVIEW') else 'KEEP_IN_PANEL',
        explanation='Ocena nie zakończyła się wynikiem dopuszczonym do publikacji. Szczegóły są w raporcie tej spółki.',
        next_check='Nowy istotny materiał lub kontrola zapisanego błędu; bez automatycznego ponawiania zadania.')
    return result


def save(api,connection,decision):
    if not stamp(decision.get('as_of')):return False
    connection.execute('INSERT INTO runtime VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at '
        "WHERE julianday(json_extract(excluded.payload,'$.as_of'))>=coalesce(julianday(json_extract(runtime.payload,'$.as_of')),0)",
        ('orchestrator:'+decision['ticker'],api.json_text(decision),decision['evaluated_at']))
    return True


def report_decision(api,event,context,analysis,settings,now,latest=None):
    stage=early.STAGE if early.is_event(event) else 'CONFIRMED'
    original=assess(api,event['snapshot'],context['analysis_manifest'],settings,now,stage)
    if latest is not None:
        material=api.build_analysis_manifest({'snapshot':latest,'autonomous_assessment_version':1},{'sources':[]})
        current=assess(api,latest,material,settings,now,stage,revalidation=True)
        if original['direction']!=current['direction'] or not api.same_opportunity_basis(event['snapshot'],latest):
            original.update(review_allowed=False,reason='DIRECTION_OR_BASIS_CHANGED',action='WAIT_FOR_DATA',role=PANEL,role_label=LABELS[PANEL])
        elif not current['review_allowed']:
            original.update(review_allowed=False,reason=current['reason'],action=current['action'],role=PANEL,role_label=LABELS[PANEL])
        elif original['role']==TOP and current['role']!=TOP:
            original.update(role=WATCH,role_label=LABELS[WATCH],plan_complete=False)
        original['latest_as_of']=latest.get('acquired_at')
    return publish(original,analysis)


def render_status(api,store):
    """Read-only per-company control state, including cases never sent to AI."""
    import streamlit as st
    ticks=set(store.load_section('tickers',[]))
    labels={'WAIT_FOR_REFERENCE':'Czeka na bazę','WAIT_FOR_SESSION':'Czeka na sesję',
        'WAIT_FOR_PRICE_BASIS':'Operacja na akcjach · wymagana kontrola jednostki ceny',
        'WAIT_FOR_DATA':'Czeka na spójne dane','WAIT_FOR_SESSION_DATA':'Czeka na świece sesji',
        'WAIT_FOR_MOVEMENT':'Obserwuje cenę','WAIT_FOR_ACTIVITY':'Czeka na aktywność',
        'WAIT_FOR_CHANGE':'Czeka na istotną zmianę','WAIT_FOR_CAPACITY':'Czeka na kolejny cykl',
        'WAIT_FOR_AI':'Poprzednia ocena jeszcze trwa',
        'WAIT_FOR_REVIEW':'Ocena wymaga sprawdzenia',
        'KEEP_IN_PANEL':'Tylko panel','ANALYZE_PRELIMINARY':'Wstępny materiał do AI',
        'ANALYZE_CONFIRMED':'Potwierdzony materiał do AI','PUBLISH_RISE_WITH_PLAN':'Wzrost z planem',
        'PUBLISH_RISING_WATCH':'Wzrost do obserwacji','PUBLISH_FALLING_WARNING':'Ostrzeżenie spadkowe'}
    with st.expander('Orkiestrator · decyzje i powiązania spółki',expanded=False):
        st.caption('Zapis ostatniej oceny danych, również gdy nie uruchomiono AI. Otwarcie nie pobiera danych ani nie ponawia zadań.')
        ticker=st.text_input('Ticker — decyzja orkiestratora',value='',
            placeholder='Wpisz ticker, np. HUMA lub STX.WA',key='orchestrator_ticker_text').strip().upper()
        if ticker:
            if not api.valid_ticker(ticker):
                st.info('Wpisz poprawny ticker, np. HUMA lub STX.WA.');return
            with store.connection() as c:
                row=c.execute('SELECT payload FROM runtime WHERE key=?',('orchestrator:'+ticker,)).fetchone()
            if not row:
                st.info('Brak zapisanej decyzji orkiestratora dla '+ticker+'. Spółka musi być obserwowana i przetworzona przez skaner. Samo wpisanie tickera nie uruchamia pobierania ani AI.');return
            state=api.load_payload(row[0])
            if ticker not in ticks:st.caption('Spółka jest poza aktywną listą. Poniżej ostatni zapis z własną datą.')
            st.write(labels.get(state['action'],state['action'])+' · '+state['role_label'])
            st.caption('Dane: '+state['as_of']+' · decyzja: '+state['evaluated_at'])
            st.write(state.get('explanation') or state['next_check'])
            st.write('Następny warunek: '+state['next_check'])
            for item in state.get('issues',[]):st.write('• '+item)
            links=state['connections']
            value=lambda x:api.pl_number(x,2,'%') if api.finite_number(x) else 'brak danych'
            st.write('Cena od bazy: '+value(links['price'].get('change_from_base_pct'))+' · od otwarcia: '+value(links['price'].get('change_from_open_pct')))
            st.write('Wspiera: '+('; '.join(links['technical']['supports']) or 'brak'))
            st.write('Przeczy: '+('; '.join(links['technical']['contradicts']) or 'brak'))
            st.write('Plan SL/TP: '+('kompletny' if links['plan']['complete'] else str(links['plan'].get('reason') or 'brak kompletu danych')))
            st.write('Przebieg sesji: '+links['session']['status']+' · świece: '+str(links['session']['candles']))
            for item in state.get('limitations',[]):st.caption(item)
