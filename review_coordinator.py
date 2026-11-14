"""Grounded observation decisions: general uncertainty is not a rejection reason.

No providers, ranking overrides, minimum pick count or historical job changes.
The model selects evidence first and an explicit, source-bound decision last.
"""
CONTRACT='EVIDENCE_SELECTION_V2'
SCHEMA_NAME='ki_coordinated_company_review_v2'
CONTEXT_ONLY={'L_FUTURE','L_CAUSE','L_ACTIVITY_SCOPE','L_QUOTES','L_FUNDAMENTALS','L_RSI_EXTREME','L_PLAN','L_CONFIRMATION'}
FIELDS={'price_evidence','momentum_evidence','supporting_evidence','limiting_evidence','watch_condition','decision'}


def policy(book,snapshot):
    warnings=set(CONTEXT_ONLY)&set(book['limits'])
    warnings.update(k for k in book['limits'] if k.startswith('L_TREND_') and k.endswith('_UNKNOWN'))
    # A partial hour below a full-hour mean is not proof of weak full-hour activity.
    if snapshot.get('candle_status')!='CLOSED':warnings.add('L_ACTIVITY_LOW')
    # A missing long execution plan does not suppress an observation in XTB.
    # A measured POOR_RR/ADVERSE_RETRACE/WIDE_SPREAD remains a material limit.
    supports=[k for k in book['supports'] if k!='S_DETECTION'] or list(book['supports'])
    return {'version':1,'purpose':'OBSERVATION_IN_XTB',
            'inform_reasons':supports,
            'panel_reasons':[k for k in book['limits'] if k not in warnings],
            'context_only':[k for k in book['limits'] if k in warnings],
            'source_quote_ids':list(book['quotes']),
            'rule':'INFORM oznacza informację do obserwacji, nie prognozę ani zlecenie. '
                   'PANEL_ONLY wymaga konkretnego ograniczenia tej spółki albo faktu ze zweryfikowanego źródła. '
                   'Ogólna niepewność, brak ustalonej przyczyny, częściowa godzina, niepotwierdzony czas bid/ask, '
                   'brak fundamentów lub kompletnego planu SL/TP i sama skrajna strefa RSI pozostają jawnymi zastrzeżeniami.'}


def decision_schema(book):
    rules=book['coordination'];choices=[]
    def option(verdict,reasons,quotes):
        if not reasons:return
        props={'verdict':{'type':'string','enum':[verdict]},
               'primary_reason':{'type':'string','enum':reasons},
               'source_quote':{'type':'string','enum':quotes}}
        choices.append({'type':'object','properties':props,'required':list(props),'additionalProperties':False})
    if book['local_verdict']=='ALIGNED':
        option('INFORM',rules['inform_reasons'],['NONE',*rules['source_quote_ids']])
    option('PANEL_ONLY',rules['panel_reasons'],['NONE',*rules['source_quote_ids']])
    if rules['source_quote_ids']:
        if book['local_verdict']=='ALIGNED':option('INFORM',['SOURCE_EVENT'],rules['source_quote_ids'])
        option('PANEL_ONLY',['SOURCE_EVENT'],rules['source_quote_ids'])
    if not choices:raise ValueError('Brak udokumentowanej podstawy decyzji końcowej.')
    return {'anyOf':choices} if len(choices)>1 else choices[0]


def normalize(wire,book):
    if not isinstance(wire,dict) or set(wire)!=FIELDS:
        raise ValueError('Końcowa decyzja wymaga kontraktu koordynatora.')
    decision=wire.get('decision')
    if not isinstance(decision,dict) or set(decision)!={'verdict','primary_reason','source_quote'}:
        raise ValueError('Niepoprawna struktura końcowej decyzji.')
    verdict=decision['verdict'];reason=decision['primary_reason'];quote=decision['source_quote'];rules=book['coordination']
    if (verdict not in ('INFORM','PANEL_ONLY') or not isinstance(reason,str) or not isinstance(quote,str)
        or quote not in ('NONE',*rules['source_quote_ids'])):
        raise ValueError('Niepoprawny werdykt lub odwołanie do dowodu.')
    if verdict=='INFORM' and book['local_verdict']!='ALIGNED':
        raise ValueError('Werdykt AI nie może omijać lokalnego ryzyka lub niespójności.')
    if reason=='SOURCE_EVENT':
        if quote=='NONE':raise ValueError('Przesłanka źródłowa wymaga zweryfikowanego cytatu.')
    else:
        allowed=rules['inform_reasons'] if verdict=='INFORM' else rules['panel_reasons']
        selected=wire.get('supporting_evidence') if verdict=='INFORM' else wire.get('limiting_evidence')
        if reason not in allowed or not isinstance(selected,list) or reason not in selected:
            raise ValueError('Werdykt wymaga konkretnej wybranej przesłanki; ogólne zastrzeżenie nie jest wetem.')
    normalized={k:v for k,v in wire.items() if k!='decision'}
    normalized.update(verdict=verdict,source_quote=quote)
    return normalized


def explanation(wire,book):
    decision=wire['decision'];attention=decision['verdict'];reason=decision['primary_reason']
    if reason=='SOURCE_EVENT':
        main='Fakt z datowanego źródła jest główną przesłanką oceny AI; cytat znajduje się w kontekście.'
    else:main=(book['supports'] if attention=='INFORM' else book['limits'])[reason]
    opposite=(book['limits'][wire['limiting_evidence'][0]] if attention=='INFORM'
              else book['supports'][wire['supporting_evidence'][0]])
    return ('Do obserwacji: ' if attention=='INFORM' else 'Tylko panel: ')+main+' '+(
        'Ograniczenie: ' if attention=='INFORM' else 'Argument za: ')+opposite


def instructions():
    return (
        'Cel to informacja o spółce wartej obserwacji w XTB, a nie zgoda na transakcję ani gwarancja dalszego ruchu. '
        'Najpierw wybierz konkretne dowody ceny, momentum, zalet i ograniczeń; decyzję podaj na końcu. '
        'decision.primary_reason musi wskazywać główną wybraną przesłankę decyzji zgodną z coordination. '
        'Nie używaj context_only jako powodu PANEL_ONLY. Dalszy kierunek jest nieznany dla każdej spółki; '
        'brak potwierdzonej przyczyny ani brak świeżego bid/ask nie jest samodzielnym powodem milczenia. '
        'Otwarta godzina i samo RSI w strefie skrajnej są ograniczeniami interpretacji, a nie dowodem odwrócenia. '
        'Brak kompletnego planu SL/TP pozostaje jawny; nie utożsamiaj informacji do obserwacji z gotowym zleceniem. '
        'PANEL_ONLY wybierz dla konkretnego, obserwowanego ograniczenia z panel_reasons, które uznajesz za przeważające. '
        'SOURCE_EVENT jest dozwolone tylko gdy wybrany datowany cytat opisuje konkretny istotny fakt o emitencie; '
        'dla PANEL_ONLY ma to być konkretne niekorzystne zdarzenie, a nie sam brak wiadomości. '
        'Przy SOURCE_EVENT wybierz istniejący source_quote; nie dopowiadaj przyczyn ani skutków spoza źródła. '
        'Gdy nie ma konkretnej podstawy odmowy, pozytywnie zakwalifikowany sygnał pozostaje informacją do obserwacji. '
        'Nie ma obowiązku wypełnienia listy ani minimalnej liczby spółek. '
        'Przykład: zgodna technika i potwierdzony ruch, ale nieznana przyszłość i otwarta godzina: '
        'INFORM z primary_reason S_ALIGNMENT, o ile katalog zawiera tę przesłankę. '
        'Przykład: katalog zawiera L_POOR_RR i ryzyko przeważa: PANEL_ONLY z primary_reason L_POOR_RR. ')
