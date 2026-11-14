"""AI selects evidence IDs; KI renders checked Polish statements, never invented prose."""
import copy
import hashlib
import json

from ai_assessment import source_quote_catalog
from sl_tp import stamp
import prompt_policy
import review_coordinator
import company_narrative

CONTRACT='EVIDENCE_SELECTION_V1'
SCHEMA_NAME='ki_grounded_company_review'
CURRENT_CONTRACT=review_coordinator.CONTRACT
CURRENT_SCHEMA_NAME=review_coordinator.SCHEMA_NAME


def active(context):
    return (context.get('analysis_manifest') or {}).get('review_contract') in (CONTRACT,CURRENT_CONTRACT)


def is_request(request):
    return contract_for_request(request) is not None


def contract_for_request(request):
    name=(request.get('response_format') or {}).get('json_schema',{}).get('name')
    return {SCHEMA_NAME:CONTRACT,CURRENT_SCHEMA_NAME:CURRENT_CONTRACT}.get(name)


def catalogue(api,snapshot,context):
    m=context['analysis_manifest'];local=m.get('local_review') or {}
    if m.get('purpose')!='FINAL_COMPANY_REVIEW':raise ValueError('Kontrakt dowodów wymaga końcowej oceny spółki.')
    identity=m.get('identity') or {}
    if any(identity.get(k)!=snapshot.get(k) for k in ('ticker','currency','interval','acquired_at','candle_time','candle_end')):
        raise ValueError('Tożsamość lub czas katalogu nie odpowiada migawce spółki.')
    if context.get('ticker',snapshot.get('ticker'))!=snapshot.get('ticker'):
        raise ValueError('Kontekst katalogu należy do innej spółki.')
    session=m.get('session_context') or {};summary=session.get('summary') or {}
    if session.get('status')!='COMPLETE_TO_ASOF':raise ValueError('Brak pełnego zapisanego przebiegu sesji.')
    n=api.finite_number;i=snapshot.get('indicators') or {};price=snapshot.get('price')
    change=(snapshot.get('price_matrix') or {}).get('change_pct')
    if not n(change) or not change or not n(price,True):raise ValueError('Brak kierunku lub ceny do oceny dowodów.')
    up=change>0;direction='wzrostowy' if up else 'spadkowy'
    prices={};momentum={}
    if n(i.get('ma_fast')):
        above=price>i['ma_fast'];below=price<i['ma_fast']
        code='P_ABOVE_FAST' if above else 'P_BELOW_FAST' if below else 'P_AT_FAST'
        prices[code]={'metric':'ma_fast','text':'Cena znajduje się '+('powyżej' if above else 'poniżej' if below else 'na poziomie')+' szybkiej średniej.'}
    if n(i.get('last_macd_hist')):
        v=i['last_macd_hist'];code='M_MACD_POSITIVE' if v>0 else 'M_MACD_NEGATIVE' if v<0 else 'M_MACD_ZERO'
        momentum[code]={'metric':'last_macd_hist','text':('Dodatni histogram MACD wspiera bieżące momentum wzrostowe.' if v>0 else
            'Ujemny histogram MACD wspiera bieżące momentum spadkowe.' if v<0 else 'Histogram MACD znajduje się na poziomie zerowym.')}
    if n(i.get('rsi')):
        r=i['rsi'];code='M_RSI_HIGH' if r>70 else 'M_RSI_LOW' if r<30 else 'M_RSI_ABOVE' if r>50 else 'M_RSI_BELOW' if r<50 else 'M_RSI_NEUTRAL'
        text=('RSI jest w strefie wykupienia; nie jest to wycena spółki.' if r>70 else
              'RSI jest w strefie wyprzedania; nie jest to wycena spółki.' if r<30 else
              'RSI jest poza strefami skrajnymi; momentum jest '+('powyżej' if r>50 else 'poniżej')+' poziomu neutralnego.' if r!=50 else
              'RSI jest poza strefami skrajnymi; momentum jest neutralne.')
        momentum[code]={'metric':'rsi','text':text}
    if n(i.get('plus_di')) and n(i.get('minus_di')):
        d=i['plus_di']-i['minus_di'];code='M_DI_UP' if d>0 else 'M_DI_DOWN' if d<0 else 'M_DI_NEUTRAL'
        momentum[code]={'metric':'plus_di','text':('Układ DI wspiera bieżący kierunek wzrostowy.' if d>0 else
            'Układ DI wspiera bieżący kierunek spadkowy.' if d<0 else 'Wskaźniki kierunku DI są równe; nie rozstrzygają kierunku.')}
    if not prices or not momentum:raise ValueError('Brak odrębnych dowodów ceny i momentum.')
    preliminary=m.get('review_stage')=='PRELIMINARY'
    supports={'S_DETECTION':('Wstępny ruch od stałej bazy jest zapisany; seria potwierdzeń jeszcze trwa.' if preliminary else
                            'Ruch od stałej bazy ma potwierdzenie w zapisanych odczytach.')}
    limits={'L_FUTURE':'Dalszy kierunek pozostaje nieustalony.',
            'L_CAUSE':'Związek informacji o emitencie z ruchem nie jest potwierdzony.'}
    if n(i.get('rsi')) and (i['rsi']>70 or i['rsi']<30):
        limits['L_RSI_EXTREME']='RSI jest w strefie skrajnej; sam ten stan nie przesądza odwrócenia ruchu.'
    technical_aligned=local.get('verdict')=='ALIGNED'
    if m.get('review_contract')==CURRENT_CONTRACT:
        technical=m.get('technical') or {}
        technical_aligned=bool(technical.get('supports')) and not technical.get('contradicts') and technical.get('status')=='READY'
    if technical_aligned:supports['S_ALIGNMENT']='Bieżące wskazania techniczne są zgodne z ruchem od bazy.'
    else:limits['L_ALIGNMENT']='Bieżące wskazania nie są w pełni zgodne z ruchem od bazy.'
    session_change=summary.get('change_from_session_open_pct')
    if not n(session_change):raise ValueError('Brak porównania ceny z otwarciem sesji.')
    session_text='W zapisanej bieżącej sesji cena jest '+('powyżej otwarcia.' if session_change>0 else 'poniżej otwarcia.' if session_change<0 else 'na poziomie otwarcia.')
    if session_change*change>0:supports['S_SESSION']='Ruch od otwarcia sesji jest zgodny z ruchem od stałej bazy.'
    elif session_change*change<0:limits['L_SESSION']='Kierunek ruchu od otwarcia sesji różni się od ruchu od stałej bazy.'
    movement=('Zaobserwowano wstępny ruch ' if preliminary else 'Potwierdzono ruch ')+direction+' od stałej bazy. '+session_text+' '+(
        'Bieżące wskazania techniczne są zgodne z tym ruchem.' if technical_aligned else
        'Bieżące wskazania techniczne pozostają mieszane lub sprzeczne z ruchem.')
    if preliminary:
        movement+=' Seria trzech potwierdzeń aktywności nie została zakończona.'
        limits['L_CONFIRMATION']='Wstępny ruch nie uzyskał jeszcze trzech potwierdzeń aktywności.'
    shortened=api.shortened_activity_ready(snapshot)
    rv=snapshot.get('rvol');closed=snapshot.get('previous_closed') or {};old_rv=closed.get('rvol')
    if shortened:
        activity='Bieżąca świeca jest skróconym przedziałem końca sesji; godzinowy RVOL nie jest dla niej wyznaczany. '
        if n(old_rv):
            activity+='Wolumen ostatniej pełnej godziny jest '+('powyżej' if old_rv>1 else 'poniżej' if old_rv<1 else 'na poziomie')+' średniej godzinowej. '
            if old_rv>=1:supports['S_ACTIVITY']='Wolumen ostatniej pełnej godziny osiągnął lub przekroczył średnią.'
        else:activity+='Brak pełnego porównania wolumenu ostatniej zakończonej godziny. '
        activity+='Opis obejmuje zapisany przebieg aktywności całej sesji.'
        limits['L_ACTIVITY_SCOPE']='Końcowy przedział jest skrócony; jego wolumen nie jest pełną godziną.'
    elif n(rv):
        relation='powyżej' if rv>1 else 'poniżej' if rv<1 else 'na poziomie'
        opened=snapshot.get('candle_status')=='OPEN'
        activity=('Dotychczasowy wolumen otwartej świecy jest ' if opened else 'Wolumen zamkniętej świecy jest ')+relation+' średniej godzinowej. '
        activity+=('To pomiar częściowy; nie określa wolumenu całej godziny. ' if opened else 'Jest to porównanie pełnych przedziałów godzinowych. ')
        activity+='Wolumen całej zapisanej sesji jest odrębny od wolumenu tej świecy.'
        if rv>=1:supports['S_ACTIVITY']='Wolumen badanej świecy osiągnął średnią pełnych godzin.'
        else:limits['L_ACTIVITY_LOW']='Wolumen badanej świecy dotąd nie osiągnął średniej pełnych godzin.'
        if opened:limits['L_ACTIVITY_SCOPE']='Wolumen otwartej świecy jest częściowy; pełna godzina nie została oceniona.'
    else:
        activity='Brak pełnego porównania wolumenu godzinowego. Dostępne dane sesji nie zastępują tego pomiaru.'
        limits['L_ACTIVITY_SCOPE']='Brak pełnego porównania wolumenu godzinowego.'
    status=api.quote_status(snapshot)
    if status=='VALID':
        quote=('Oferty bid/ask są dostępne, ale ich czas aktualizacji nie jest potwierdzony.' if local.get('execution')!='TIMESTAMP_CONFIRMED' else
               'Oferty bid/ask mają potwierdzony czas aktualizacji w zapisanym odczycie.')
    elif status=='INVERTED':quote='Oferty bid/ask są niespójne; bid przewyższa ask i spread nie jest oceniony.'
    elif status=='INCOMPLETE':quote='Oferty bid/ask są niepełne; warunki wykonania nie są w pełni ocenione.'
    else:quote='Brak bid/ask; warunki wykonania nie są ocenione.'
    if local.get('execution')!='TIMESTAMP_CONFIRMED':limits['L_QUOTES']=quote
    plan=m.get('trade_plan') or {};rr=plan.get('rr1')
    if plan.get('status')=='INDICATIVE' and n(rr):
        plan_text='Dostępny jest orientacyjny plan techniczny; nie potwierdza on warunków wykonania.'
        if rr>=1:supports['S_PLAN']='Potencjał do pierwszego celu nie jest mniejszy od odległości do SL.'
        else:limits['L_PLAN']='Potencjał do pierwszego celu jest mniejszy niż odległość do SL.'
    else:
        plan_text='Brak kompletnego technicznego planu SL/TP.';limits['L_PLAN']=plan_text
    dominant=[]
    for code in local.get('required_reason_codes') or []:
        if code in ('WIDE_SPREAD','ADVERSE_RETRACE','POOR_RR'):
            text=local['evidence'][code]['text']
            limits['L_'+code]=text;dominant.append(text.rstrip('.'))
    risk=quote+' '+plan_text+(' '+'; '.join(dominant)+'.' if dominant else '')+' Dalszy kierunek pozostaje nieustalony.'
    fund=(m.get('company_background') or {}).get('fundamentals') or {};fin=fund.get('summary') or {}
    if fund.get('status')=='ready' and fin:
        if n(fin.get('net_income')):
            if fin['net_income']>0:supports['S_PROFIT']='Zapisany kwartał zakończył się zyskiem netto.'
            elif fin['net_income']<0:limits['L_LOSS']='Zapisany kwartał zakończył się stratą netto.'
        if n(fin.get('operating_cashflow')):
            if fin['operating_cashflow']>0:supports['S_CASHFLOW']='Zapisane przepływy operacyjne z czterech kwartałów są dodatnie.'
            elif fin['operating_cashflow']<0:limits['L_CASHFLOW']='Zapisane przepływy operacyjne z czterech kwartałów są ujemne.'
    else:limits['L_FUNDAMENTALS']='Brak kompletnego zapisanego pakietu finansowego.'
    scenario=m.get('scenario_plan') or {};until=stamp(scenario.get('valid_until'));at=stamp(snapshot.get('acquired_at'))
    conditions={}
    if scenario.get('status')=='CONDITIONAL' and until and at and at<until:
        for key,field in (('C_SUPPORT','base'),('C_INVALIDATION','alternative')):
            if scenario.get(field):conditions[key]=scenario[field]
    if not conditions:conditions['C_UNAVAILABLE']='Brak bieżącego zapisanego warunku scenariusza.'
    aliases=(context.get('issuer_identity') or api.issuer_search_identity(snapshot)).get('aliases',[])
    quotes={q['quote_id']:q for q in source_quote_catalog(context.get('sources',[]),aliases)}
    book={'contract':m.get('review_contract',CONTRACT),'price':prices,'momentum':momentum,'supports':supports,'limits':limits,
            'conditions':conditions,'quotes':quotes,'axes':{'movement':movement,'activity':activity,'risk':risk},
            'local_verdict':local.get('verdict'),'identity':m.get('identity'),
            'missing':(['Nie ustalono przyczyny ruchu.']+([quote] if local.get('execution')!='TIMESTAMP_CONFIRMED' else []))}
    intelligence=m.get('market_intelligence') or {}
    horizons=(intelligence.get('trend_context') or {}).get('horizons') or {}
    for key,horizon in horizons.items():
        text=horizon.get('label','')+': '+{'UP':'wzrostowy','DOWN':'spadkowy','MIXED':'mieszany','UNKNOWN':'brak danych'}.get(horizon.get('direction'),'brak danych')+'.'
        expected='UP' if change>0 else 'DOWN'
        observed=horizon.get('direction')
        if observed==expected:
            supports['S_TREND_'+key.upper()]=text
        else:
            code='L_TREND_'+key.upper()+('_CONFLICT' if observed in ('UP','DOWN') else '_UNKNOWN')
            limits[code]=text
    if any(value is not None for value in intelligence.values()):
        book['market_intelligence']=intelligence
    if horizons:
        book['axes']['movement']+=' '+intelligence['trend_context']['relationship']
    if book['contract']==CURRENT_CONTRACT:
        book['coordination']=review_coordinator.policy(book,snapshot)
    if preliminary:
        book['review_stage']='PRELIMINARY'
        book['missing'].append(limits['L_CONFIRMATION'])
    if book['contract']==CURRENT_CONTRACT and (m.get('orchestration') or {}).get('version')==1:
        control=m['orchestration']
        book['orchestration']={k:control.get(k) for k in ('version','direction','role','role_label','plan_complete','connections','scenario','limitations')}
    return book


def legacy_schema(book):
    def obj(fields):return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
    def enum(keys):return {'type':'string','enum':list(keys)}
    def many(keys,minimum,maximum):return {'type':'array','items':enum(keys),'minItems':minimum,'maxItems':min(maximum,len(keys))}
    return obj({'verdict':enum(['INFORM','PANEL_ONLY'] if book['local_verdict']=='ALIGNED' else ['PANEL_ONLY']),'price_evidence':enum(book['price']),
        'momentum_evidence':many(book['momentum'],1,2),'supporting_evidence':many(book['supports'],1,3),
        'limiting_evidence':many(book['limits'],1,3),'watch_condition':enum(book['conditions']),
        'source_quote':enum(['NONE',*book['quotes']])})


def schema(book):
    result=legacy_schema(book)
    if book.get('contract')==CURRENT_CONTRACT:
        props=result['properties']
        props.pop('verdict');props.pop('source_quote')
        props['narrative']=company_narrative.schema()
        props['decision']=review_coordinator.decision_schema(book)
        result['required']=list(props)
    return result


def narrative_material(snapshot,context,book):
    manifest=context.get('analysis_manifest') or {}
    background=manifest.get('company_background') or {}
    return {'analysis_manifest':manifest,'company_background':background,
            'daily_candles':background.get('daily_candles') or [],
            'quote_catalog':list(book.get('quotes',{}).values()),'sources':context.get('sources') or []}


def request(api,base,snapshot,context):
    result=copy.deepcopy(base);book=catalogue(api,snapshot,context)
    payload=json.loads(result['messages'][-1]['content']);payload['evidence_review']=book
    result['messages'][-1]['content']=api.json_text(payload)
    result['messages'][0]['content']=prompt_policy.evidence_policy('event')+(
        'Oceń niezależnie tę jedną spółkę na podstawie pełnego pakietu. Nie porównuj jej z innymi emitentami. '
        'Zwróć wyłącznie identyfikatory z evidence_review, bez własnych opisów, liczb i nowych faktów. '
        'verdict to Twoja krytyczna ocena: INFORM gdy dowody uzasadniają obserwację; PANEL_ONLY gdy ograniczenia przeważają. '
        'Lokalne ALIGNED nie wymusza INFORM. Nie typuj spółki tylko dlatego, że jest wybrana do analizy. '
        'price_evidence i momentum_evidence wybierają konkretne dowody techniczne. '
        'supporting_evidence i limiting_evidence wybierają argumenty, które rzeczywiście zważyłeś. '
        'Uporządkuj wybrane dowody od najważniejszego. Pierwszy supporting_evidence jest głównym uzasadnieniem INFORM, '
        'a pierwszy limiting_evidence głównym uzasadnieniem PANEL_ONLY. Nie powtarzaj identyfikatora w liście. '
        'watch_condition wybierz z istniejącego scenariusza; przy braku danych wybierz C_UNAVAILABLE. '
        'source_quote to jeden zweryfikowany cytat Q albo NONE. Cytat nie dowodzi przyczyny ruchu. '
        'Nie utożsamiaj potwierdzonego ruchu z przyszłą kontynuacją, wolumenu z płynnością ani momentum z wyceną. '
        'Wolumen sesji i godzin są odrębne; końcowy przedział może być skrócony. '
        'Nie zakładaj sentymentu, spekulacji ani zachowania inwestorów. '
        'KI składa pełny polski opis z wybranych dowodów oraz obowiązkowych faktów i ograniczeń pakietu. '
        'Nie ma gwarancji zysku, poleceń transakcji ani obowiązku wyboru minimalnej liczby spółek.')
    if book['contract']==CURRENT_CONTRACT:
        result['messages'][0]['content']=prompt_policy.evidence_policy('event')+(
            'Oceń niezależnie tę jedną spółkę na podstawie pełnego pakietu i evidence_review. '
            'Nie porównuj jej z innymi emitentami. Zwróć wyłącznie identyfikatory ze schematu, '
            'bez własnych opisów, liczb i nowych faktów. '
            'price_evidence i momentum_evidence wskazują fakty techniczne; supporting_evidence i limiting_evidence '
            'zawierają rozważone zalety i ograniczenia. Nie powtarzaj identyfikatora w liście. '
            'watch_condition wybierz z istniejącego scenariusza; przy braku danych C_UNAVAILABLE. '
            'decision.source_quote wskazuje zweryfikowany cytat Q albo NONE. Cytat nie dowodzi przyczyny ruchu. '
            'Nie utożsamiaj wolumenu z płynnością ani momentum z wyceną. Nie zakładaj sentymentu ani zachowania inwestorów. '
            'Wolumen sesji i godzin jest odrębny, a ostatni przedział sesji może być skrócony. '
            'KI składa pełny polski opis z wybranych dowodów oraz obowiązkowych ograniczeń pakietu. '
            +review_coordinator.instructions())
        if book.get('review_stage')=='PRELIMINARY':
            result['messages'][0]['content']+=' To wstępna ocena przed trzema potwierdzeniami. Nie określaj ruchu jako potwierdzony; uwzględnij L_CONFIRMATION jako jawne ograniczenie.'
        if book.get('orchestration'):
            result['messages'][0]['content']+=' Orkiestrator wiąże kierunek, aktywność, technikę, poziomy i ograniczenia tej spółki. Spadek opisuj jako ostrzeżenie spadkowe, bez planu kupna lub domniemania krótkiej sprzedaży. TOP 5 dotyczy wyłącznie wzrostów z kompletnym planem technicznym; wzrost bez planu może nadal uzasadniać obserwację. Oceń konkretne wspierające i sprzeczne przesłanki całego pakietu; rola nie wymusza powiadomienia.'
    result['response_format']={'type':'json_schema','json_schema':{
        'name':CURRENT_SCHEMA_NAME if book['contract']==CURRENT_CONTRACT else SCHEMA_NAME,
        'strict':True,'schema':schema(book)}}
    if book['contract']==CURRENT_CONTRACT:
        payload['narrative_facts']=company_narrative.facts_for(snapshot,narrative_material(snapshot,context,book))
        result['messages'][-1]['content']=api.json_text(company_narrative.compact_input(payload))
        instruction=result['messages'][0]['content']
        instruction=instruction.replace('Zwróć wyłącznie identyfikatory ze schematu, bez własnych opisów, liczb i nowych faktów.',
            'W polach decyzyjnych wybieraj identyfikatory ze schematu; w narrative napisz własne uzasadnienie na podstawie danych.')
        instruction=instruction.replace('KI składa pełny polski opis z wybranych dowodów oraz obowiązkowych ograniczeń pakietu.',
            'Własne pełne uzasadnienie piszesz w narrative; KI zachowuje sprawdzone dane i warunki lokalne.')
        result['messages'][0]['content']=instruction+company_narrative.instructions()
    return result


def decode(api,wire,snapshot,context):
    prepared=context.get('prepared_ai_request') or {}
    if not is_request(prepared):raise ValueError('Brak zapisanego kontraktu oceny opartej na dowodach.')
    payload=json.loads(prepared['messages'][-1]['content']);frozen=payload.get('evidence_review')
    book=catalogue(api,snapshot,context)
    if frozen!=book:raise ValueError('Katalog dowodów nie odpowiada zapisanym danym tej spółki.')
    original_wire=copy.deepcopy(wire)
    coordinated=book['contract']==CURRENT_CONTRACT
    narrative=None
    if 'narrative_facts' in payload:
        expected=company_narrative.facts_for(snapshot,narrative_material(snapshot,context,book))
        if payload['narrative_facts']!=expected:raise ValueError('Katalog liczb uzasadnienia nie odpowiada zapisanym danym.')
        if not isinstance(wire,dict) or 'narrative' not in wire:raise ValueError('Brak pełnego uzasadnienia AI wymaganego przez zapisany kontrakt.')
        narrative=company_narrative.checked(wire['narrative'],expected)
        if not all(key in narrative['sections'] for key in ('summary','risks')):raise ValueError('Brak poprawnego autorskiego uzasadnienia werdyktu i ryzyka.')
        wire={k:v for k,v in wire.items() if k!='narrative'}
    if coordinated:wire=review_coordinator.normalize(wire,book)
    # The wire contract contains only scalar enums and bounded lists of enums.
    # Keep runtime validation dependency-free, including the separate deep env.
    properties=legacy_schema(book)['properties']
    if not isinstance(wire,dict) or set(wire)!=set(properties):
        raise ValueError('AI zwróciło pola spoza kontraktu identyfikatorów dowodów.')
    for name,rule in properties.items():
        value=wire[name]
        if rule['type']=='string':valid=isinstance(value,str) and value in rule['enum']
        else:valid=(isinstance(value,list) and rule['minItems']<=len(value)<=rule['maxItems']
                    and all(isinstance(item,str) and item in rule['items']['enum'] for item in value))
        if not valid:raise ValueError('AI zwróciło niepoprawne odwołanie do dowodu: '+name+'.')
    for name in ('momentum_evidence','supporting_evidence','limiting_evidence'):
        if len(wire[name])!=len(set(wire[name])):raise ValueError('AI powtórzyło identyfikator dowodu.')
    attention=wire['verdict']
    selected=wire['supporting_evidence'] if attention=='INFORM' else wire['limiting_evidence']
    key=selected[0]
    main=(book['supports'] if attention=='INFORM' else book['limits'])[key]
    opposite=(book['limits'][wire['limiting_evidence'][0]] if attention=='INFORM' else book['supports'][wire['supporting_evidence'][0]])
    explanation=('Do obserwacji: ' if attention=='INFORM' else 'Tylko panel: ')+main+' '+('Ograniczenie: ' if attention=='INFORM' else 'Argument za: ')+opposite
    if coordinated:explanation=review_coordinator.explanation(original_wire,book)
    if len(explanation)>320:raise ValueError('Opis z wybranych dowodów przekracza limit raportu.')
    quote=book['quotes'].get(wire['source_quote'])
    canonical={'technical':[{'metric':book['price'][wire['price_evidence']]['metric'],
                            'interpretation':book['price'][wire['price_evidence']]['text']}]
        +[{'metric':book['momentum'][code]['metric'],'interpretation':book['momentum'][code]['text']} for code in wire['momentum_evidence']],
        'context':([{'source_id':quote['source_id'],'fact':quote['quote_id']}] if quote else []),
        'hypotheses':[],'risks':[book['limits'][code] for code in wire['limiting_evidence']],
        'missing':book['missing'],'assessment':book['axes'],
        'decision':{'verdict':book['local_verdict'],
                    'reason_codes':context['analysis_manifest']['local_review']['required_reason_codes'][:3]},
        'final_review':{'attention':attention,'explanation':explanation}}
    provenance={'contract':book['contract'],'selected':original_wire,
        'catalogue_sha256':hashlib.sha256(api.json_text(book).encode('utf-8')).hexdigest(),
        'condition_text':book['conditions'][wire['watch_condition']],
        'description_origin':'KI composed verified statements; AI selected verdict and evidence.'}
    if narrative:
        provenance['narrative']=narrative
        provenance['description_origin']='AI authored the Polish explanation; KI checked numeric references and kept canonical decision constraints.'
    return canonical,provenance
