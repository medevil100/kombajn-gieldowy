"""An explicit preliminary lane into the existing single company-review digest.

No fabricated confirmations, new providers, queue replay or independent outbox.
The same fresh, coherent session evidence is required before any provider call.
"""
KIND='EARLY_COMPANY_REVIEW'
STAGE='PRELIMINARY'
LABEL='Wstępna ocena · przed trzema potwierdzeniami'


def is_event(evidence):
    return (evidence.get('kind')==KIND and evidence.get('review_stage')==STAGE
            and bool(evidence.get('company_review_batch')))


def gate(api,snapshot,current,settings,allow_confirmed=False,require_new_activity=True):
    def no(reason):return {'allowed':False,'reason':reason}
    matrix=snapshot.get('price_matrix') or {}
    threshold=settings.get('price_threshold_pct',2.)
    if not api.finite_number(threshold,True):return no('Niepoprawny próg ceny w ustawieniach.')
    if (not api.accepted_matrix_snapshot(snapshot) or not api.open_hour_fresh(snapshot,current)
        or not api.market_session_open(snapshot.get('ticker'),current)):
        return no('Brak świeżego, zaakceptowanego odczytu w regularnej sesji.')
    states=('CANDIDATE','CONFIRMED') if allow_confirmed else ('CANDIDATE',)
    if (matrix.get('state') not in states or matrix.get('activity_tracking_version')!='E05'
        or matrix.get('consecutive_reads') not in ((1,2,3) if allow_confirmed else (1,2))):
        return no('Brak wstępnego kandydata z zapisanym dowodem aktywności.')
    if snapshot.get('latest_price_origin')=='carried_previous_close':return no('Cena przeniesiona z wcześniejszej świecy.')
    change=matrix.get('change_pct')
    if not api.finite_number(change) or abs(change)<=threshold:
        return no('Ruch nie przekracza ustawionego progu ceny.')
    if api.material_issues(snapshot):return no('Niepełne lub niespójne dane ceny, techniki lub aktywności.')
    if snapshot.get('currency')!=('PLN' if str(snapshot.get('ticker')).endswith('.WA') else 'USD'):
        return no('Waluta nie odpowiada rynkowi instrumentu.')
    try:
        minimum_rvol=max(1.5,float(settings.get('min_rvol_for_opportunity',.5)),float(settings.get('min_rvol_absolute',.3)))
        minimum_volume=max(1000,float(settings.get('min_volume_for_opportunity',1000)))
    except (ValueError,TypeError):return no('Niepoprawne progi aktywności.')
    if (not api.finite_number(minimum_rvol,True) or not api.finite_number(minimum_volume,True)
        or not api.finite_number(snapshot.get('rvol'),True) or snapshot['rvol']<minimum_rvol
        or not api.finite_number(snapshot.get('volume'),True) or snapshot['volume']<minimum_volume):
        return no('Wstępna ocena wymaga RVOL co najmniej półtora i dodatniego obrotu ponad minimum.')
    if require_new_activity and (matrix.get('activity_evidence') not in ('VOLUME_INCREASE','NEW_CANDLE_VOLUME')
        or matrix.get('last_activity_at')!=snapshot.get('acquired_at')):
        return no('Ten odczyt nie zawiera nowego dowodu aktywności.')
    session=api.company_review.session_context.build(snapshot)
    if session.get('status')!='COMPLETE_TO_ASOF':return no('Niepełny zapis świec bieżącej sesji.')
    return {'allowed':True,'reason':'Istotny ruch z nową aktywnością; status nadal wstępny.',
            'confirmation_reads':matrix['consecutive_reads'],'required_confirmation_reads':3,
            'minimum_rvol':minimum_rvol,'minimum_volume':minimum_volume}


def movement_valid(api,evidence,current,settings,latest=False):
    if not is_event(evidence):return False
    snap=evidence.get('snapshot') or {}
    decision=gate(api,snap,current,settings,allow_confirmed=latest,require_new_activity=not latest)
    return decision['allowed']


def reserve(api,store,cycle_id,current):
    selected=[];pool=[];settings=store.load_section('settings',{})
    ticks=set(store.load_section('tickers',[]))
    with store.transaction() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM opportunities WHERE state='CANDIDATE' AND cycle_id=?",(cycle_id,))]
        for row in rows:
            rank=api.load_payload(row['payload']);snap=rank['snapshot']
            decision=gate(api,snap,current,settings)
            latest=c.execute("SELECT payload FROM observations WHERE ticker=? AND interval='1h' ORDER BY id DESC LIMIT 1",(row['ticker'],)).fetchone()
            actual=api.load_payload(latest[0]) if latest else {}
            if row['ticker'] not in ticks or actual.get('acquired_at')!=snap.get('acquired_at'):
                decision={'allowed':False,'reason':'Kandydat nie jest najnowszym odczytem aktywnej spółki.'}
            if not decision['allowed']:
                pool.append({'ticker':row['ticker'],'event_id':'early_gate_'+row['sequence_id'],
                    'state':'EARLY_DATA_GATE','review_stage':STAGE,'snapshot_at':snap.get('acquired_at'),
                    'assessed_at':current.isoformat(),'details':[decision['reason']]})
                continue
            c.execute("UPDATE opportunities SET state='RESERVED' WHERE sequence_id=? AND state='CANDIDATE'",(row['sequence_id'],))
            row.update(rank=rank,review_stage=STAGE)
            selected.append(row)
    return {'selected':selected,'pool':pool}
