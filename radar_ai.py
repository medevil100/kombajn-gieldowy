"""Bounded automatic AI reviews of technical TOP 5, large cases and portfolio.

No AI calls per tick: first admission, changed thesis/trend, new daily session
or a material price/score/momentum change, with a 30-minute cooldown.
Uses the existing model, token ceiling and conservative shared daily ceiling.
"""
import hashlib
import json
from datetime import datetime,timedelta,timezone
import company_narrative
import ai_model_policy
import large_movement
import technical_radar
from sl_tp import stamp


def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS radar_ai_jobs(
        id TEXT PRIMARY KEY,ticker TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL,
        market_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,packet TEXT NOT NULL,
        request TEXT,response TEXT,result TEXT,error_type TEXT,input_tokens INTEGER,output_tokens INTEGER)''')
    c.execute('CREATE INDEX IF NOT EXISTS radar_ai_latest ON radar_ai_jobs(ticker,created_at)')


def legacy_candidates(api,store,at):
    portfolio={r['ticker']:r for r in api.portfolio_get(store)}
    roles={t:{'PORTFOLIO'} for t in portfolio};watches={}
    with store.connection() as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'ki_top5_follow' in tables:
            for row in c.execute("SELECT ticker FROM ki_top5_follow WHERE status='FOLLOWING'"):
                roles.setdefault(row['ticker'],set()).add('TOP5')
        if 'large_movement_cases' in tables:
            for row in c.execute("SELECT * FROM large_movement_cases WHERE status IN ('ACTIVE','WATCHING','WAIT','REVIEW_DUE','REVIEW_FAILED')"):
                roles.setdefault(row['ticker'],set()).add('LARGE');watches[row['ticker']]=dict(row)
        snapshots={}
        for ticker in roles:
            row=c.execute("SELECT payload FROM observations WHERE ticker=? AND interval='1h' ORDER BY id DESC LIMIT 1",(ticker,)).fetchone()
            if row:snapshots[ticker]=api.load_payload(row[0])
    result=[]
    for ticker,snap in snapshots.items():
        observed=stamp(snap.get('acquired_at'))
        if observed is None or not timedelta(0)<=at-observed<=timedelta(minutes=30):continue
        rows=large_movement.daily_rows(api,store,snap)
        if len(rows)<20:continue
        state=technical_radar.evaluate(snap,rows)
        if not state['valid']:continue
        watch=watches.get(ticker,{})
        result.append({'ticker':ticker,'roles':sorted(roles[ticker]),'technical':state,
                       'watch':api.load_payload(watch.get('result') or '{}'),
                       'watch_status':watch.get('status'),'portfolio':portfolio.get(ticker)})
    return sorted(result,key=lambda r:('PORTFOLIO' not in r['roles'],'LARGE' not in r['roles'],r['ticker']))


def candidates(api,store,at):
    if not technical_radar.enabled(store.load_section('settings',{})):
        return legacy_candidates(api,store,at)
    with store.connection() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='technical_radar'").fetchone():return []
        states=[json.loads(r[0]) for r in c.execute('SELECT payload FROM technical_radar')]
        watches={r['ticker']:dict(r) for r in c.execute('SELECT * FROM technical_watch')}
    fresh={s['ticker']:s for s in states if s['valid'] and timedelta(0)<=at-stamp(s['as_of'])<=timedelta(minutes=30)}
    portfolio={r['ticker']:r for r in api.portfolio_get(store)}
    eligible=[s for s in fresh.values() if s['growth_score']>=50 and s['growth_score']>s['decline_score']
              and watches.get(s['ticker'],{}).get('status') not in technical_radar.TERMINAL]
    top={s['ticker'] for s in sorted(eligible,key=lambda s:(-s['growth_score'],s['ticker']))[:5]}
    result=[]
    for ticker,s in fresh.items():
        roles=[];watch=watches.get(ticker);saved=json.loads(watch['payload']) if watch else {}
        if ticker in top:roles.append('TOP5')
        if watch and (watch['status']=='LARGE' or saved.get('large_since') and watch['status'] in ('TRACKING','WEAKENED','DATA_WAIT')):roles.append('LARGE')
        if ticker in portfolio:roles.append('PORTFOLIO')
        if roles:result.append({'ticker':ticker,'roles':roles,'technical':s,'watch':saved,
                                'watch_status':watch['status'] if watch else None,'portfolio':portfolio.get(ticker)})
    # Portfolio risk and existing long theses precede new ranking admissions.
    return sorted(result,key=lambda r:('PORTFOLIO' not in r['roles'],'LARGE' not in r['roles'],-r['technical']['growth_score'],r['ticker']))


def significant(old,new,now):
    if old is None:return True
    if now-stamp(old['created_at'])<timedelta(minutes=30):return False
    previous=json.loads(old['packet']);a=previous['selection'];b=new['selection']
    pa=a['technical']['price'];pb=b['technical']['price']
    old_technical=a.get('technical') or {};new_technical=b.get('technical') or {}
    old_ind=((previous.get('material') or {}).get('snapshot') or {}).get('indicators') or {}
    new_ind=((new.get('material') or {}).get('snapshot') or {}).get('indicators') or {}
    def changed_number(key,threshold):
        x=old_ind.get(key);y=new_ind.get(key)
        return isinstance(x,(int,float)) and isinstance(y,(int,float)) and abs(y-x)>=threshold
    return (set(a['roles'])!=set(b['roles']) or a.get('watch_status')!=b.get('watch_status')
            or a.get('portfolio')!=b.get('portfolio')
            or ((a.get('watch') or {}).get('monitoring') or {}).get('confirmation_status',{}).get('code')
               !=((b.get('watch') or {}).get('monitoring') or {}).get('confirmation_status',{}).get('code')
            or old_technical.get('directions')!=new_technical.get('directions')
            or abs((new_technical.get('growth_score') or 0)-(old_technical.get('growth_score') or 0))>=10
            or abs((new_technical.get('decline_score') or 0)-(old_technical.get('decline_score') or 0))>=10
            or changed_number('rsi',7) or changed_number('adx',5) or changed_number('rvol',.5)
            or ((old_ind.get('last_macd_hist') or 0)>=0)!=((new_ind.get('last_macd_hist') or 0)>=0)
            or abs(pb/pa-1)>=.03 or previous.get('daily_last')!=new.get('daily_last'))


def portfolio_context(api,store,snapshot,entry):
    """Complete saved position facts used by automatic and manual portfolio AI."""
    if not isinstance(entry,dict):return None
    with store.connection() as c:
        row=c.execute("SELECT payload FROM runtime WHERE key='portfolio_usd_pln'").fetchone()
    fx=api.load_payload(row[0]) if row else {}
    enriched={**entry,'valuation_fx_pln':fx.get('rate'),
              'valuation_fx_date':fx.get('effective_date')}
    metrics=api.portfolio_position_metrics(enriched,snapshot.get('price'),snapshot.get('currency'))
    return {**enriched,'metrics':metrics}


def schedule(api,store,now=None):
    at=stamp(now or api.utc_now());settings=store.load_section('settings',{})
    if not api.service_config(settings)['pipeline_enabled']:return 0
    count=0
    for chosen in candidates(api,store,at):
        # No new paid review outside the regular market session.
        if not api.market_session_open(chosen['ticker'],at):continue
        with store.connection() as c:
            raw=c.execute("SELECT payload FROM observations WHERE ticker=? AND interval='1h' ORDER BY id DESC LIMIT 1",(chosen['ticker'],)).fetchone()
        if not raw:continue
        snap=api.load_payload(raw[0])
        if stamp(snap.get('acquired_at'))!=stamp(chosen['technical']['as_of']):continue
        if chosen.get('portfolio'):
            chosen={**chosen,'portfolio':portfolio_context(api,store,snap,chosen['portfolio'])}
        rows=large_movement.daily_rows(api,store,snap)
        material=large_movement.packet(api,store,snap,rows,large_movement.setup(snap,rows))
        packet={'selection':chosen,'material':material,'daily_last':rows[-1]['time'] if rows else None}
        requeued=False
        with store.transaction() as c:
            schema(c)
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'large_movement_jobs' in tables and c.execute("SELECT 1 FROM large_movement_jobs WHERE ticker=? AND state IN ('QUEUED','RUNNING')",(chosen['ticker'],)).fetchone():continue
            if c.execute("SELECT 1 FROM analysis_jobs j JOIN events e ON e.id=j.event_id WHERE e.ticker=? AND j.state IN ('PENDING_CONTEXT','PENDING_AI','RUNNING')",(chosen['ticker'],)).fetchone():continue
            if c.execute("SELECT 1 FROM radar_ai_jobs WHERE ticker=? AND state IN ('QUEUED','RUNNING')",(chosen['ticker'],)).fetchone():continue
            old=c.execute('SELECT * FROM radar_ai_jobs WHERE ticker=? ORDER BY created_at DESC LIMIT 1',(chosen['ticker'],)).fetchone()
            if old and old['state']=='DEFERRED_BUDGET':
                old_day=stamp(old['created_at']).astimezone(timezone.utc).date()
                current_day=at.astimezone(timezone.utc).date()
                if current_day>old_day:
                    c.execute("""UPDATE radar_ai_jobs SET state='QUEUED',created_at=?,market_at=?,started_at=NULL,
                              finished_at=NULL,packet=?,request=NULL,response=NULL,result=NULL,error_type=NULL,
                              input_tokens=NULL,output_tokens=NULL WHERE id=?""",
                              (at.isoformat(),snap['acquired_at'],api.json_text(packet),old['id']))
                    count+=1
                    requeued=True
                else:
                    c.execute('UPDATE radar_ai_jobs SET market_at=?,packet=? WHERE id=?',
                              (snap['acquired_at'],api.json_text(packet),old['id']))
                    continue
            if not requeued:
                if not significant(old,packet,at):continue
                identifier=hashlib.sha256((chosen['ticker']+snap['acquired_at']).encode()).hexdigest()[:32]
                c.execute('INSERT OR IGNORE INTO radar_ai_jobs(id,ticker,state,created_at,market_at,packet) VALUES(?,?,?,?,?,?)',
                          (identifier,chosen['ticker'],'QUEUED',at.isoformat(),snap['acquired_at'],api.json_text(packet)))
                count+=1
        # Existing Tavily queue, TTL and quota; research is limited to the same
        # three selected groups, never to every market tick.
        api.issuer_watch.enqueue(api,store,snap,at.isoformat(),reason_override='LARGE_POTENTIAL')
    return count


def _schedule_manual(api,store,ticker,origin,now=None):
    """Build current full KI data and queue one explicit operator-paid review."""
    at=stamp(now or api.utc_now());ticker=str(ticker or '').strip().upper()
    if not api.valid_ticker(ticker):return 'INVALID_TICKER'
    with store.connection() as c:
        schema(c)
        active=c.execute("SELECT * FROM large_movement_cases WHERE ticker=? AND status IN ('ACTIVE','REVIEW_DUE','WATCHING','WAIT')",(ticker,)).fetchone()
        portfolio=next((row for row in api.portfolio_get(store) if row['ticker']==ticker),None)
        if origin=='LARGE' and not active:return 'NO_FRESH_ACTIVE_CASE'
        if origin=='PORTFOLIO' and not portfolio:return 'NOT_IN_PORTFOLIO'
        existing=c.execute("SELECT id,state,packet FROM radar_ai_jobs WHERE ticker=? AND state IN ('QUEUED','RUNNING') ORDER BY created_at DESC LIMIT 1",(ticker,)).fetchone()
        if existing and existing['state']=='RUNNING':return 'IN_PROGRESS'
        if existing and api.load_payload(existing['packet']).get('manual_requested') is True:return 'IN_PROGRESS'
        deferred=c.execute("SELECT * FROM radar_ai_jobs WHERE ticker=? AND state='DEFERRED_BUDGET' ORDER BY created_at DESC LIMIT 1",(ticker,)).fetchone()
        raw=c.execute("SELECT payload FROM observations WHERE ticker=? AND interval='1h' ORDER BY id DESC LIMIT 1",(ticker,)).fetchone()
    if not raw:return 'NO_FRESH_ACTIVE_CASE'
    snap=api.load_payload(raw[0])
    rows=large_movement.daily_rows(api,store,snap)
    technical=technical_radar.evaluate(snap,rows)
    roles=[]
    if active:roles.append('LARGE')
    if portfolio:roles.append('PORTFOLIO')
    chosen={'ticker':ticker,'roles':roles,'technical':technical,
            'watch':api.load_payload(active['result'] or '{}') if active else {},
            'watch_status':active['status'] if active else None,
            'portfolio':portfolio_context(api,store,snap,portfolio)}
    material=large_movement.packet(api,store,snap,rows,large_movement.setup(snap,rows))
    packet={'selection':chosen,'material':material,'daily_last':rows[-1]['time'] if rows else None,
            'manual_requested':True,'manual_origin':origin,'manual_requested_at':at.isoformat()}
    with store.transaction() as c:
        schema(c)
        existing=c.execute("SELECT id,state,packet FROM radar_ai_jobs WHERE ticker=? AND state IN ('QUEUED','RUNNING') ORDER BY created_at DESC LIMIT 1",(ticker,)).fetchone()
        if existing and existing['state']=='RUNNING':return 'IN_PROGRESS'
        if existing and api.load_payload(existing['packet']).get('manual_requested') is True:return 'IN_PROGRESS'
        if existing:
            c.execute("""UPDATE radar_ai_jobs SET created_at=?,market_at=?,packet=?,request=NULL,response=NULL,result=NULL,
                      error_type=NULL,started_at=NULL,finished_at=NULL,input_tokens=NULL,output_tokens=NULL WHERE id=?""",
                      (at.isoformat(),snap['acquired_at'],api.json_text(packet),existing['id']))
            return 'QUEUED'
        if deferred and c.execute("SELECT 1 FROM radar_ai_jobs WHERE id=? AND state='DEFERRED_BUDGET'",(deferred['id'],)).fetchone():
            c.execute("""UPDATE radar_ai_jobs SET state='QUEUED',created_at=?,market_at=?,started_at=NULL,finished_at=NULL,
                      packet=?,request=NULL,response=NULL,result=NULL,error_type=NULL,input_tokens=NULL,output_tokens=NULL
                      WHERE id=?""",(at.isoformat(),snap['acquired_at'],api.json_text(packet),deferred['id']))
            return 'QUEUED'
        identifier=hashlib.sha256(('manual:'+ticker+':'+at.isoformat()).encode()).hexdigest()[:32]
        c.execute('INSERT INTO radar_ai_jobs(id,ticker,state,created_at,market_at,packet) VALUES(?,?,?,?,?,?)',
                  (identifier,ticker,'QUEUED',at.isoformat(),snap['acquired_at'],api.json_text(packet)))
    return 'QUEUED'


def schedule_manual(api,store,ticker,now=None):
    return _schedule_manual(api,store,ticker,'LARGE',now)


def schedule_manual_portfolio(api,store,ticker,now=None):
    return _schedule_manual(api,store,ticker,'PORTFOLIO',now)


def pending(store):
    with store.connection() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='radar_ai_jobs'").fetchone():return False
        return c.execute("SELECT 1 FROM radar_ai_jobs WHERE state='QUEUED' LIMIT 1").fetchone() is not None


def manual_pending(store):
    with store.connection() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='radar_ai_jobs'").fetchone():return False
        return c.execute("""SELECT 1 FROM radar_ai_jobs WHERE state='QUEUED'
            AND json_extract(packet,'$.manual_requested')=1 LIMIT 1""").fetchone() is not None


def recover(api,store):
    with store.transaction() as c:
        schema(c)
        c.execute("UPDATE radar_ai_jobs SET state='FAILED',error_type='InterruptedUnknownOutcome',finished_at=? WHERE state='RUNNING'",(api.utc_now(),))


def analyst_instructions():
    """One stable investment-analysis contract shared by all three KI groups."""
    return (
        'Jesteś analitykiem akcji publicznych w systemie KI. Oceniasz dokładnie jedną spółkę na podstawie '
        'zamrożonego pakietu danych. Nie podejmujesz decyzji za użytkownika i nie wydajesz polecenia kupna ani sprzedaży. '
        'Twoim zadaniem jest pełna synteza wszystkich dostępnych danych oraz ocena jakości i etapu scenariusza, nie skrót kilku pól. '
        'To ma być analiza konkretnej spółki, a nie uniwersalny komentarz rynkowy. Zanim napiszesz odpowiedź, zestaw ze sobą '
        'wszystkie dostępne grupy dowodów: strukturę 52 tygodni, trendy, momentum, aktywność, poziomy, źródła, fundamenty '
        'oraz — jeśli dotyczy — stan portfela. Nie pomijaj grupy tylko dlatego, że osłabia wybrany werdykt. '
        '\n\nHIERARCHIA DOWODÓW. Najpierw oceń cenę i strukturę zamkniętych sesji, potem zgodność trendów, momentum i wolumen, '
        'następnie poziomy potwierdzenia oraz zanegowania, a na końcu źródła i fundamenty. Pojedynczy wskaźnik nie rozstrzyga werdyktu. '
        'Punktacja techniczna /100 jest wynikiem reguł selekcji, a nie prawdopodobieństwem wzrostu. Otwarta świeca nie potwierdza '
        'tego, co wymaga zamknięcia godziny lub sesji. Brak wiadomości nie unieważnia zmierzonego układu technicznego, ale oznacza, '
        'że przyczyna ruchu pozostaje niepotwierdzona. Brak pełnych fundamentów ogranicza ocenę fundamentalną, nie techniczną. '
        'Zmiana dzienna istnieje wyłącznie jako daily.change_pct i musi mieć daily.previous_close, daily.reference_session oraz '
        'quality.daily_reference_status=READY. tracking.change_pct jest ruchem matrycy technicznej i nie wolno nazywać go zmianą '
        'dzienną. Jeżeli te dwa ruchy mają różny znak, opisz konflikt wprost i nie przedstawiaj wzrostu od bazy jako wzrostu sesyjnego. '
        '\n\nZNACZENIE WERDYKTÓW. STRONG_SETUP wybierz tylko wtedy, gdy istnieje spójny kierunek, mierzalny warunek utrzymania lub '
        'potwierdzenia, sensowna przestrzeń względem zanegowania i brak dominującego dowodu przeciwnego. WATCH oznacza, że teza '
        'jest możliwa, lecz oczekuje na konkretny warunek albo zawiera istotny konflikt. WEAKENED oznacza, że wcześniejsza teza '
        'straciła potwierdzenie, poziom został oddany albo ryzyko przeważa nad dostępną przestrzenią. INSUFFICIENT wybierz wyłącznie, '
        'gdy brak danych uniemożliwia wiarygodną ocenę; nie używaj go tylko dlatego, że nie ma wyższego oporu, wiadomości lub celu. '
        '\n\nROLA SPÓŁKI. selection.roles może zawierać kilka ról; wykonaj jedną spójną analizę i uwzględnij wszystkie. '
        'Dla TOP5 wyjaśnij, dlaczego spółka znalazła się wśród najsilniejszych wzrostowych kandydatów, czy ruch jest wczesny czy '
        'już rozciągnięty oraz jaki warunek pozwala przejść od rankingu do trwałej tezy. Dla LARGE oceń, czy potwierdzony scenariusz '
        'nadal obowiązuje, ile ruchu wykonano od punktu odniesienia, czy wybicie jest utrzymane i co zakończy scenariusz. '
        'Dla PORTFOLIO uwzględnij liczbę akcji, cenę zakupu, bieżący wynik w walucie instrumentu i PLN, ryzyko dla istniejącej '
        'pozycji oraz relację przestrzeni do celu względem zanegowania. Nie sugeruj zwiększenia ani zamknięcia pozycji. '
        '\n\nWYBICIA I POZIOMY. Przekroczenie ostatniego oporu nie usuwa spółki. Jeżeli cena jest nad najwyższym oporem dostępnej '
        'historii, oceń wysokość wybicia, zamknięcie względem poziomu i możliwość zamiany oporu we wsparcie. Brak kolejnego oporu '
        'oznacza otwartą przestrzeń bez potwierdzonego celu, a nie brak potencjału. Analogicznie brak niższego wsparcia nie kasuje '
        'scenariusza spadkowego, lecz ogranicza możliwość wyznaczenia celu. Historyczne maksimum nie jest samo w sobie prognozą. '
        '\n\nWYMAGANA SYNTEZA. Zidentyfikuj etap ruchu: baza/akumulacja, próba wybicia, wybicie niepotwierdzone, wybicie utrzymane, '
        'kontynuacja, ruch dojrzały/rozciągnięty, osłabienie albo zanegowanie. Porównaj krótki, średni i długi horyzont; konflikt '
        'nazwij wprost i wyjaśnij jego praktyczny skutek. Wolumen przedstaw jako relację liczbową do porównywalnej średniej i oceń, '
        'czy potwierdza kierunek. RSI, MACD, ADX, średnie, ATR, Bollinger i pozostałe wskaźniki łącz w argument — nie twórz katalogu. '
        'Jeśli dostępne są derived.target_distance_pct, derived.invalidation_distance_pct i derived.reward_risk, użyj ich do oceny '
        'asymetrii. Jeśli ich nie ma, nazwij brak poziomu, ale nie wymyślaj wartości. '
        '\n\nTREŚĆ SEKCJI. summary: werdykt, etap ruchu i jeden dominujący powód. data_quality: osobno oceń kompletność i świeżość '
        'techniki, historii, aktywności, źródeł i fundamentów oraz napisz, jakie wnioski nadal są uprawnione. technical: struktura ceny, '
        'średnie, Bollinger, VWAP, Fibo i konflikt horyzontów. momentum: wspólny sens RSI, ROC, MACD/histogramu, ADX/DI i Stochastic. '
        'activity: liczbowe porównanie wolumenu i znaczenie dla jakości ruchu. levels: '
        'najbliższy warunek potwierdzenia, obowiązujące wsparcie/opór, zanegowanie i asymetria; przy nowym szczycie opisz utrzymanie '
        'wybicia. horizon: osobno opisz krótki, średni i długi horyzont oraz ich konflikt, bez obietnicy terminu. fundamentals: '
        'gotówka, zadłużenie, przychody, wynik i przepływy, jeżeli istnieją; nie utożsamiaj straty netto z burn rate. scenarios: '
        'wariant wzrostowy, neutralny i spadkowy wraz z warunkami. risks: dwa najważniejsze '
        'scenariuszowe ryzyka i mechanizm ich wpływu, nie lista zastrzeżeń. context: tylko przyjęte fakty źródłowe/fundamentalne '
        'oraz dokładny wpływ braków danych. Każda sekcja ma wnosić nową informację i zwykle zawierać dwa do czterech pełnych zdań. '
        'Każda sekcja musi użyć co najmniej jednego identyfikatora istniejącego w narrative_facts. Nie twórz skrótowych '
        'identyfikatorów activity, levels, risks ani context — używaj wyłącznie dokładnych nazw przekazanych przez KI. '
        '\n\nJĘZYK I KONTROLA. Pisz konkretnie po polsku. Każda konkluzja odpowiada na: co się dzieje, na jakim dowodzie, dlaczego '
        'to ważne i co zmieni ocenę. Nie używaj samodzielnych ogólników „istotne ryzyka”, „wymaga obserwacji”, „dalszy kierunek '
        'nieustalony”, „może wpłynąć” ani „układ uzasadnia obserwację”. Nie powtarzaj tej samej informacji w kilku sekcjach. '
        'Nie pisz, że sam wzrost wolumenu oznacza zainteresowanie inwestorów; wolumen opisuje aktywność i uczestnictwo, '
        'nie motywację. Nie wymyślaj wiadomości, zachowania inwestorów, celów, prawdopodobieństw ani danych finansowych. '
        '\n\nODWOŁANIA. Każdą liczbę, datę, cenę i mierzalne twierdzenie zapisuj znacznikiem [id] z narrative_facts. '
        'Przykład: „Cena [price] utrzymuje się nad średnimi [indicator.ma_fast] i [indicator.ma_slow], lecz RSI '
        '[indicator.rsi] pokazuje rozciągnięcie ruchu; utrata [invalidation.support] zaneguje tę strukturę.” '
        'Pole references każdej sekcji zawiera dokładnie unikalne identyfikatory faktycznie użyte w jej tekście. '
        'Jeżeli faktu nie ma w narrative_facts, nie podawaj odpowiadającej mu liczby ani twierdzenia. '
    )


def request(api,packet,full_input=False):
    material=packet['material'];snap=material['snapshot']
    facts=company_narrative.facts_for(snap,material)
    for key in ('shares','entry_price','entry_fx_pln','sl','tp'):
        value=(packet['selection'].get('portfolio') or {}).get(key)
        if api.finite_number(value,True):facts['portfolio.'+key]={'label':'Portfel: '+key,'value':value,
            'unit':'szt.' if key=='shares' else 'PLN/USD' if key=='entry_fx_pln' else str((packet['selection']['portfolio'] or {}).get('entry_currency') or ''),
            'scope':'Ręcznie zapisane dane pozycji użytkownika','as_of':snap['acquired_at']}
    metrics=(packet['selection'].get('portfolio') or {}).get('metrics') or {}
    metric_units={'cost_native':metrics.get('currency'),'value_native':metrics.get('currency'),
                  'pnl_native':metrics.get('currency'),'pnl_pct':'%',
                  'cost_pln':'PLN','value_pln':'PLN','pnl_pln':'PLN'}
    for key,unit in metric_units.items():
        value=metrics.get(key)
        if api.finite_number(value):facts['portfolio.'+key]={'label':'Portfel: '+key,'value':value,
            'unit':unit or '','scope':'Wyliczenie z zapisanej pozycji i ostatniej ceny KI','as_of':snap['acquired_at']}
    price=snap.get('price')
    targets=[item.get('price') for item in (material.get('targets') or {}).values()
             if api.finite_number(item.get('price'),True) and api.finite_number(price,True) and item['price']>price]
    invalidations=[item.get('price') for item in (material.get('invalidation_levels') or {}).values()
                   if api.finite_number(item.get('price'),True) and api.finite_number(price,True) and item['price']<price]
    if targets:
        target=min(targets);facts['derived.target_distance_pct']={'label':'Odległość do najbliższego celu lub oporu','value':(target/price-1)*100,'unit':'%','scope':'Wyliczenie KI z zapisanych poziomów','as_of':snap['acquired_at']}
    if invalidations:
        invalidation=max(invalidations);facts['derived.invalidation_distance_pct']={'label':'Odległość do zanegowania','value':(1-invalidation/price)*100,'unit':'%','scope':'Wyliczenie KI z zapisanych poziomów','as_of':snap['acquired_at']}
    if targets and invalidations and price>invalidation:
        facts['derived.reward_risk']={'label':'Relacja przestrzeni do celu względem zanegowania','value':(target-price)/(price-invalidation),'unit':'×','scope':'Odległości cenowe, bez gwarancji wykonania','as_of':snap['acquired_at']}
    rows=material.get('daily_candles') or []
    if rows and api.finite_number(price,True):
        highs=[r.get('high') for r in rows if api.finite_number(r.get('high'),True)]
        lows=[r.get('low') for r in rows if api.finite_number(r.get('low'),True)]
        if highs and lows and max(highs)>min(lows):
            facts['derived.history_position_pct']={'label':'Położenie ceny w zakresie dostępnej historii','value':(price-min(lows))/(max(highs)-min(lows))*100,'unit':'%','scope':'Zakres dostępnych zamkniętych sesji','as_of':snap['acquired_at']}
        volumes=[r.get('volume') for r in rows[-20:-1] if api.finite_number(r.get('volume'),True)]
        if volumes and api.finite_number(rows[-1].get('volume'),True) and sum(volumes)>0:
            facts['derived.daily_volume_ratio']={'label':'Wolumen ostatniej sesji względem średniej wcześniejszych','value':rows[-1]['volume']/(sum(volumes)/len(volumes)),'unit':'×','scope':'Zamknięte sesje dzienne','as_of':snap['acquired_at']}
    indicators=snap.get('indicators') or {}
    fast=indicators.get('ma_fast');slow=indicators.get('ma_slow')
    if all(api.finite_number(value,True) for value in (price,fast,slow)):
        facts['derived.price_vs_ma_fast_pct']={'label':'Cena względem SMA 10','value':(price/fast-1)*100,'unit':'%',
            'scope':'Dodatnia wartość oznacza cenę nad średnią','as_of':snap['acquired_at']}
        facts['derived.price_vs_ma_slow_pct']={'label':'Cena względem SMA 30','value':(price/slow-1)*100,'unit':'%',
            'scope':'Dodatnia wartość oznacza cenę nad średnią','as_of':snap['acquired_at']}
        tolerance=max(abs(price),abs(fast),abs(slow))*1e-9
        position=('ABOVE_BOTH' if price>max(fast,slow)+tolerance else
                  'BELOW_BOTH' if price<min(fast,slow)-tolerance else 'BETWEEN_OR_EQUAL')
        structure='BULLISH' if fast>slow+tolerance else 'BEARISH' if fast<slow-tolerance else 'FLAT'
        facts['derived.price_vs_mas']={'label':'Jednoznaczna relacja ceny do obu średnich','value':position,'unit':'',
            'scope':'Wyliczenie KI zapobiegające błędnej interpretacji średnich','as_of':snap['acquired_at']}
        facts['derived.ma_structure']={'label':'Układ SMA 10 względem SMA 30','value':structure,'unit':'',
            'scope':'Wyliczenie KI; nie jest samodzielnym werdyktem','as_of':snap['acquired_at']}
    for key in ('growth_score','decline_score'):
        facts['radar.'+key]={'label':'Ocena techniczna '+key,'value':packet['selection']['technical'][key],
                            'unit':'/100','scope':'Siła reguł, nie prawdopodobieństwo','as_of':snap['acquired_at']}
    shape={'type':'object','properties':{
        'verdict':{'type':'string','enum':['STRONG_SETUP','WATCH','WEAKENED','INSUFFICIENT']},
        'narrative':company_narrative.schema(sections=company_narrative.FULL_SECTIONS)},'required':['verdict','narrative'],'additionalProperties':False}
    instructions=analyst_instructions()+company_narrative.instructions(full=True)
    data={'selection':packet['selection'],'material':material,'narrative_facts':facts}
    model_input=data if full_input else company_narrative.compact_input(data)
    prepared={**ai_model_policy.chat_parameters(),'temperature':.1,'max_completion_tokens':company_narrative.FULL_MAX_TOKENS,'store':False,
        'messages':[{'role':'system','content':instructions},{'role':'user','content':api.json_text(model_input)}],
        'response_format':{'type':'json_schema','json_schema':{'name':'ki_radar_review','strict':True,'schema':shape}}}
    return prepared,facts


def manual_raw_result(wire,error,market_at,roles):
    return {'verdict':wire.get('verdict') if isinstance(wire,dict) else None,
            'raw_narrative':wire.get('narrative') if isinstance(wire,dict) else None,
            'validation_error':str(error) or 'Odpowiedź nie przeszła lokalnej kontroli jakości.',
            'market_at':market_at,'roles':roles,
            'notice':'Ręcznie zamówiona odpowiedź AI została zachowana w całości; program jej nie zatwierdza ani nie ukrywa.'}


def process_once(api,store,keys,now=None,transport=None,job_id=None):
    at=stamp(now or api.utc_now());iso=at.isoformat()
    if not job_id and not api.service_config(store.load_section('settings',{}))['pipeline_enabled']:return False
    with store.transaction() as c:
        schema(c)
        if job_id:
            row=c.execute("SELECT * FROM radar_ai_jobs WHERE id=? AND state='QUEUED'",(job_id,)).fetchone()
        else:
            row=c.execute("""SELECT * FROM radar_ai_jobs WHERE state='QUEUED'
                ORDER BY CASE WHEN json_extract(packet,'$.manual_requested')=1 THEN 0 ELSE 1 END,created_at LIMIT 1""").fetchone()
        if not row:return False
        row=dict(row);packet=api.load_payload(row['packet'])
        manual=packet.get('manual_requested') is True
        if not manual and c.execute("SELECT 1 FROM large_movement_jobs WHERE ticker=? AND state IN ('QUEUED','RUNNING')",(row['ticker'],)).fetchone():return False
        if c.execute("SELECT 1 FROM analysis_jobs j JOIN events e ON e.id=j.event_id WHERE e.ticker=? AND j.state IN ('PENDING_CONTEXT','PENDING_AI','RUNNING')",(row['ticker'],)).fetchone():return False
        news=c.execute('SELECT state FROM issuer_watch_jobs WHERE ticker=? ORDER BY created_at DESC LIMIT 1',(row['ticker'],)).fetchone()
        if news and news['state'] in ('QUEUED','RUNNING') and at-stamp(row['created_at'])<timedelta(minutes=3):return False
        start=at.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        used=c.execute("SELECT count(*) FROM radar_ai_jobs WHERE started_at>=? AND COALESCE(json_extract(packet,'$.manual_requested'),0)<>1",(start,)).fetchone()[0]
        used+=c.execute('SELECT count(*) FROM large_movement_jobs WHERE started_at>=?',(start,)).fetchone()[0]
        # Count all legacy automated jobs created today conservatively; no extra
        # daily budget is introduced when switching from the former pipeline.
        used+=c.execute('SELECT count(*) FROM analysis_jobs j JOIN events e ON e.id=j.event_id WHERE e.created_at>=?',(start,)).fetchone()[0]
        ticker_used=c.execute("SELECT count(*) FROM radar_ai_jobs WHERE ticker=? AND started_at>=? AND COALESCE(json_extract(packet,'$.manual_requested'),0)<>1",(row['ticker'],start)).fetchone()[0]
        ticker_used+=c.execute('SELECT count(*) FROM large_movement_jobs WHERE ticker=? AND started_at>=?',(row['ticker'],start)).fetchone()[0]
        reason=('EXPIRED' if not manual and (at-stamp(row['market_at'])>timedelta(minutes=30) or not api.market_session_open(row['ticker'],at))
                else 'DEFERRED_BUDGET' if not manual and (used>=large_movement.MAX_CALLS_DAY or ticker_used>=large_movement.MAX_CALLS_TICKER_DAY)
                else 'KEY_MISSING' if not keys.get('OPENAI_API_KEY') else None)
        if reason:
            c.execute('UPDATE radar_ai_jobs SET state=?,finished_at=? WHERE id=?',
                      (reason,None if reason=='DEFERRED_BUDGET' else iso,row['id']));return True
        try:
            large_movement.attach_sources(api,packet['material'],large_movement.source_material(api,store,packet['material']['snapshot']))
            prepared,facts=request(api,packet,full_input=manual)
        except (ValueError,KeyError,TypeError):
            c.execute("UPDATE radar_ai_jobs SET state='INVALID_PACKET',finished_at=? WHERE id=?",(iso,row['id']));return True
        if not manual and len(api.json_text(prepared).encode('utf-8'))>160000:
            c.execute("UPDATE radar_ai_jobs SET state='PACKET_TOO_LARGE',finished_at=? WHERE id=?",(iso,row['id']));return True
        c.execute("UPDATE radar_ai_jobs SET state='RUNNING',started_at=?,request=?,packet=? WHERE id=?",(iso,api.json_text(prepared),api.json_text(packet),row['id']))
    body=None;error=None;result=None;wire=None
    try:
        body=(transport or api.service_http)('OpenAI','https://api.openai.com/v1/chat/completions',keys['OPENAI_API_KEY'],prepared,uncertain=True)
        choice=body['choices'][0]
        if choice.get('finish_reason')!='stop':raise ValueError('Niepełna odpowiedź AI')
        wire=json.loads(choice['message']['content'])
        if set(wire)!={'verdict','narrative'} or wire['verdict'] not in ('STRONG_SETUP','WATCH','WEAKENED','INSUFFICIENT'):raise ValueError('Niepoprawny werdykt')
        narrative=company_narrative.checked(wire['narrative'],facts,company_narrative.FULL_SECTIONS)
        result={'verdict':wire['verdict'],'narrative':narrative,'market_at':row['market_at'],'roles':packet['selection']['roles']}
        if not narrative['sections']:
            if manual:
                state='MANUAL_RAW';result=manual_raw_result(wire,'Brak sekcji zaakceptowanych przez kontrolę odwołań.',row['market_at'],packet['selection']['roles'])
            else:raise ValueError('Brak poprawnego opisu')
        else:state='DONE' if narrative['status']=='COMPLETE' else 'PARTIAL'
    except Exception as exc:
        if manual and isinstance(wire,dict) and isinstance(wire.get('narrative'),dict):
            state='MANUAL_RAW';error=type(exc).__name__;result=manual_raw_result(wire,exc,row['market_at'],packet['selection']['roles'])
        else:
            state='FAILED';error=type(exc).__name__
            from tavily_cli_adapter import sanitize_cli_diagnostic
            result={'error':sanitize_cli_diagnostic(str(exc)) or 'Nie zapisano opisu błędu.'}
    usage=(body.get('usage') or {}) if isinstance(body,dict) else {}
    with store.transaction() as c:
        c.execute('UPDATE radar_ai_jobs SET state=?,finished_at=?,response=?,result=?,error_type=?,input_tokens=?,output_tokens=? WHERE id=?',
            (state,iso,api.json_text(body) if body else None,api.json_text(result) if result else None,error,
             usage.get('prompt_tokens'),usage.get('completion_tokens'),row['id']))
        if 'LARGE' in packet['selection']['roles'] and state in ('DONE','PARTIAL'):
            case=c.execute("SELECT status,result FROM large_movement_cases WHERE ticker=?",(row['ticker'],)).fetchone()
            if case and case['status']=='REVIEW_DUE':
                saved=api.load_payload(case['result']);saved['post_confirmation_ai']={
                    'finished_at':iso,'market_at':row['market_at'],'verdict':result['verdict'],
                    'job_id':row['id'],'state':state}
                next_state='ACTIVE' if result['verdict']=='STRONG_SETUP' else 'WATCHING'
                saved.setdefault('monitoring',{})['reason']=(
                    'Świeża ocena AI po potwierdzeniu podtrzymała aktywny duży potencjał.' if next_state=='ACTIVE'
                    else 'Świeża ocena AI po potwierdzeniu nie uznała układu za mocny; scenariusz pozostaje obserwowany poza aktywnymi dużymi okazjami.')
                c.execute("UPDATE large_movement_cases SET status=?,result=?,updated_at=?,notice_cycle=? WHERE ticker=?",
                          (next_state,api.json_text(saved),iso,row['id'] if next_state=='ACTIVE' else None,row['ticker']))
    return True


def run_manual_portfolio(api,store,keys,ticker,now=None,transport=None):
    """Run the explicitly selected portfolio ticker now, outside the automatic queue budget."""
    state=schedule_manual_portfolio(api,store,ticker,now)
    if state not in ('QUEUED','IN_PROGRESS'):
        return state
    with store.connection() as c:
        row=c.execute("""SELECT id,state FROM radar_ai_jobs
            WHERE ticker=? AND json_extract(packet,'$.manual_requested')=1
            ORDER BY created_at DESC LIMIT 1""",(str(ticker).strip().upper(),)).fetchone()
    if not row:return 'NOT_FOUND'
    if row['state']=='RUNNING':return 'IN_PROGRESS'
    if row['state']!='QUEUED':return row['state']
    process_once(api,store,keys,now=now,transport=transport,job_id=row['id'])
    with store.connection() as c:
        finished=c.execute('SELECT state FROM radar_ai_jobs WHERE id=?',(row['id'],)).fetchone()
    return finished['state'] if finished else 'NOT_FOUND'


def render_latest(store,ticker):
    import streamlit as st
    with store.connection() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='radar_ai_jobs'").fetchone():
            st.caption('Ocena AI: oczekuje na kwalifikację TOP 5, Duży potencjał lub portfel.');return
        row=c.execute('SELECT * FROM radar_ai_jobs WHERE ticker=? ORDER BY created_at DESC LIMIT 1',(ticker,)).fetchone()
        completed=c.execute("SELECT * FROM radar_ai_jobs WHERE ticker=? AND state IN ('DONE','PARTIAL') ORDER BY finished_at DESC LIMIT 1",(ticker,)).fetchone()
    if not row:st.caption('Ocena AI: nie zaplanowano jeszcze oceny tej spółki.');return
    st.write('Dane techniczne przekazane do AI: '+row['market_at']+' · stan '+row['state'])
    if row['state']=='DEFERRED_BUDGET':
        st.warning('AI oczekuje — dzienny limit został wykorzystany. Monitoring techniczny trwa, a pakiet jest aktualizowany najnowszymi danymi. Zadanie wróci automatycznie po odnowieniu limitu.')
        if completed:
            st.caption('Ostatnia zakończona ocena AI: '+str(completed['finished_at'])+' · dane z '+completed['market_at']+'. Poniższy opis jest historyczny, nie bieżący.')
            value=json.loads(completed['result']);st.write('Poprzedni werdykt AI: '+{'STRONG_SETUP':'mocny układ','WATCH':'obserwować','WEAKENED':'osłabienie','INSUFFICIENT':'niewystarczające dane'}[value['verdict']])
            st.markdown(company_narrative.html(value['narrative']),unsafe_allow_html=True)
        return
    if row['state'] in ('DONE','PARTIAL'):
        value=json.loads(row['result']);st.write('Werdykt AI: '+{'STRONG_SETUP':'mocny układ','WATCH':'obserwować','WEAKENED':'osłabienie','INSUFFICIENT':'niewystarczające dane'}[value['verdict']])
        st.markdown(company_narrative.html(value['narrative']),unsafe_allow_html=True)
    elif row['state']=='MANUAL_RAW':
        value=json.loads(row['result']);st.warning('Ręcznie zamówiona odpowiedź AI została pokazana w całości, mimo że nie przeszła lokalnej kontroli odwołań. Zweryfikuj liczby z danymi KI.')
        st.write('Werdykt AI: '+{'STRONG_SETUP':'mocny układ','WATCH':'obserwować','WEAKENED':'osłabienie','INSUFFICIENT':'niewystarczające dane'}.get(value.get('verdict'),str(value.get('verdict') or 'brak')))
        st.caption('Kontrola jakości: '+str(value.get('validation_error') or 'nie podano'))
        labels={'summary':'Podsumowanie','technical':'Technika','activity':'Aktywność','levels':'Poziomy','horizon':'Horyzont','risks':'Ryzyka','context':'Kontekst'}
        for key,section in (value.get('raw_narrative') or {}).items():
            if not isinstance(section,dict):continue
            st.markdown('**'+labels.get(key,key)+'**')
            st.write(str(section.get('text') or 'Brak tekstu.'))
            refs=section.get('references') or []
            if refs:st.caption('Odwołania podane przez AI: '+', '.join(map(str,refs)))
    else:st.caption({'QUEUED':'Oczekuje w kolejce.','RUNNING':'Ocena w toku.','FAILED':'Odpowiedź nie zakończyła się poprawnie; techniczne śledzenie trwa.','EXPIRED':'Materiał wygasł przed wywołaniem.','KEY_MISSING':'Brak klucza OpenAI.','PACKET_TOO_LARGE':'Pakiet przekroczył limit; nie wykonano wywołania.'}.get(row['state'],row['state']))
