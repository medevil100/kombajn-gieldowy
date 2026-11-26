"""Deterministic technical state and durable watchlist. No model/provider calls.

Score is rule strength, never a calibrated probability. One independent family
each: trend 40, momentum 20, activity 20, structure 20. Unknowns score zero.
Stored observation timestamps, not wall-clock refreshes, drive state changes.
"""
import json
import math
import sqlite3
from html import escape
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo
from technical_core import valid_bar
from sl_tp import stamp

VERSION=1
LABELS={'TRACKING':'Aktywna obserwacja techniczna','LARGE':'Duży potencjał techniczny',
        'WEAKENED':'Układ osłabiony','INVALIDATED':'Scenariusz zanegowany',
        'DATA_WAIT':'Oczekiwanie na poprawne dane','CLOSED':'Obserwacja zakończona ręcznie',
        'BASIS_REVIEW':'Zmiana jednostki ceny — poziomy do sprawdzenia'}
TERMINAL=('INVALIDATED','BASIS_REVIEW','CLOSED')


def ranking_cards_html(states, ai_by_ticker):
    """Visible summary; rule score and AI assessment have separate labels."""
    cards=[]
    for state in states:
        ticker=escape(str(state['ticker']))
        score=escape(str(state['growth_score']))
        price=escape(fmt(state.get('price')))
        currency=escape(str(state.get('currency') or ''))
        reason=escape(str((state.get('reasons') or ['Brak zapisanego uzasadnienia technicznego.'])[0]))
        ai=ai_by_ticker.get(state['ticker'])
        if not ai:
            ai_text='Ocena AI: jeszcze nie zaplanowana'
        elif ai['state'] in ('DONE','PARTIAL'):
            try:result=json.loads(ai['result'] or '{}')
            except (TypeError,ValueError):result={}
            verdict={'STRONG_SETUP':'mocny układ','WATCH':'obserwować','WEAKENED':'osłabienie','INSUFFICIENT':'niewystarczające dane'}.get(result.get('verdict'),'brak poprawnego werdyktu')
            ai_text='Ocena AI: '+verdict+' · '+str(ai['market_at'])
        else:
            ai_text='Ocena AI: '+str(ai['state'])
        cards.append('<article style="background:#172334;border:1px solid #3b526d;border-radius:12px;padding:16px;margin:10px 0;color:#edf4ff">'
                     '<div style="font-size:1.15rem;font-weight:700">'+ticker+' · '+score+'/100 technicznie</div>'
                     '<div>Cena: '+price+' '+currency+'</div><div>'+reason+'</div>'
                     '<div style="margin-top:8px;color:#a8d8ff">'+escape(ai_text)+'</div></article>')
    return ''.join(cards)


def enabled(settings):
    # Retired mode: legacy opportunity, portfolio and TOP 5 flows own the UI.
    return False


def monitored_tickers(store):
    """Durable observations survive a change of current ranking/watchlist."""
    with store.connection() as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        names=[]
        if 'technical_watch' in tables:
            names.extend(r[0] for r in c.execute("SELECT ticker FROM technical_watch WHERE status NOT IN ('INVALIDATED','BASIS_REVIEW','CLOSED')"))
        if 'ki_top5_follow' in tables:
            names.extend(r[0] for r in c.execute("SELECT ticker FROM ki_top5_follow WHERE status='FOLLOWING'"))
        if 'large_movement_cases' in tables:
            names.extend(r[0] for r in c.execute("SELECT ticker FROM large_movement_cases WHERE status IN ('ACTIVE','WATCHING','WAIT','REVIEW_DUE','REVIEW_FAILED','BASIS_REVIEW')"))
    positions=store.load_section('settings',{}).get('portfolio_config',[])
    portfolio=[e['ticker'] for e in positions if isinstance(e,dict) and e.get('ticker')]
    return list(dict.fromkeys(names+portfolio))


def number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def fmt(v):
    return format(v,'.4f').replace('.',',') if number(v) else 'brak danych'


@lru_cache(maxsize=32)
def session_dates(market,first,last):
    from exchange_calendars import get_calendar
    return frozenset(day.date().isoformat() for day in get_calendar(market).sessions_in_range(first,last))


def history_coverage(ticker,at,rows):
    from session_context import bounds
    market='XWAR' if ticker.endswith('.WA') else 'XNYS'
    zone=ZoneInfo('Europe/Warsaw' if market=='XWAR' else 'America/New_York')
    today=at.astimezone(zone).date();first=today-timedelta(days=364)
    limits=bounds(market,today.isoformat())
    last=today if limits and at>=limits[1] else today-timedelta(days=1)
    expected=session_dates(market,first.isoformat(),last.isoformat())
    observed={r['time'][:10] for r in rows}
    return {'complete':bool(expected and expected<=observed),'expected_sessions':len(expected),
            'available_sessions':len(expected&observed),'missing_sessions':len(expected-observed),
            'from':first.isoformat(),'to':last.isoformat()}


def evaluate(snapshot, daily, reference=None):
    at=stamp(snapshot.get('acquired_at'));price=snapshot.get('price')
    if not at or not number(price) or price<=0:raise ValueError('Brak poprawnego czasu lub ceny')
    rows=[r for r in daily if valid_bar(r) and stamp(r.get('end')) and stamp(r['end'])<=at and r.get('status')=='CLOSED']
    rows=sorted({r['time']:r for r in rows}.values(),key=lambda r:stamp(r['time']))
    ind=snapshot.get('indicators') or {};horizons=(snapshot.get('trend_context') or {}).get('horizons') or {}
    directions={k:(horizons.get(k) or {}).get('direction','UNKNOWN') for k in ('session','short','medium','long')}
    # Recompute no trend label here: use the same shared classifier as KI.
    up=sum(v=='UP' for v in directions.values());down=sum(v=='DOWN' for v in directions.values())
    fast=ind.get('ma_fast');slow=ind.get('ma_slow');hist=ind.get('last_macd_hist')
    trend_up=10*up;trend_down=10*down
    momentum_up=(10 if number(hist) and hist>0 else 0)+(10 if number(fast) and number(slow) and price>fast>slow else 0)
    momentum_down=(10 if number(hist) and hist<0 else 0)+(10 if number(fast) and number(slow) and price<fast<slow else 0)
    closed=snapshot.get('previous_closed') or {};rv=closed.get('rvol')
    closed_at=stamp(closed.get('end'))
    hour_activity=bool(closed.get('status')=='CLOSED' and closed_at and timedelta(0)<=at-closed_at<=timedelta(hours=1)
                       and number(rv) and rv>=1.5)
    avg=sum(r['volume'] for r in rows[-21:-1])/20 if len(rows)>=21 else None
    daily_ratio=rows[-1]['volume']/avg if avg and avg>0 else None
    activity=(10 if hour_activity else 0)+(10 if number(daily_ratio) and daily_ratio>=1.5 else 0)
    high=max(r['high'] for r in rows[-20:]) if len(rows)>=20 else None
    low=min(r['low'] for r in rows[-20:]) if len(rows)>=20 else None
    rolling_high=high
    if reference and number(reference.get('breakout_level')):high=reference['breakout_level']
    breakout=bool(high and price>high);breakdown=bool(low and price<low)
    coverage=history_coverage(snapshot['ticker'],at,rows)
    complete_52=coverage['complete']
    high52=max((r['high'] for r in rows if stamp(r['time'])>=at-timedelta(days=364)),default=None)
    new_high=bool(high52 and price>high52)
    blocked=bool((snapshot.get('price_basis') or {}).get('blocked'))
    carried=snapshot.get('latest_price_origin')=='carried_previous_close'
    ohlc=snapshot.get('ohlc') or {}
    coherent=(not ohlc or all(number(ohlc.get(k)) for k in ('open','high','low','close')) and
              ohlc['low']<=min(ohlc['open'],ohlc['close'],price)<=max(ohlc['open'],ohlc['close'],price)<=ohlc['high'])
    valid=not blocked and not carried and coherent and number(snapshot.get('volume')) and snapshot['volume']>0
    growth=min(100,trend_up+momentum_up+(activity if trend_up or momentum_up or breakout else 0)+(20 if breakout else 0)) if valid else 0
    decline=min(100,trend_down+momentum_down+(activity if trend_down or momentum_down or breakdown else 0)+(20 if breakdown else 0)) if valid else 0
    position=('powyżej obu średnich' if number(fast) and number(slow) and price>max(fast,slow) else
              'poniżej obu średnich' if number(fast) and number(slow) and price<min(fast,slow) else
              'między średnimi lub na jednej z nich' if number(fast) and number(slow) else 'bez kompletu średnich')
    reasons=[f'Cena {fmt(price)} {snapshot.get("currency","")} jest {position}; SMA 10 {fmt(fast)}, SMA 30 {fmt(slow)}. '
             +('Układ ceny i średnich wspiera wzrost.' if momentum_up>=10 and number(fast) and number(slow) and price>fast>slow else
              'Układ ceny i średnich wspiera spadek.' if number(fast) and number(slow) and price<fast<slow else 'Średnie nie potwierdzają uporządkowanego kierunku.'),
             f'Histogram MACD {fmt(hist)}: '+('dodatni, wspiera momentum wzrostowe.' if number(hist) and hist>0 else 'ujemny, wspiera momentum spadkowe.' if number(hist) and hist<0 else 'brak kierunkowego potwierdzenia.'),
             'Trendy: '+', '.join({'session':'śród sesji','short':'krótki','medium':'średni','long':'długi'}[k]+' '+{'UP':'wzrostowy','DOWN':'spadkowy','MIXED':'mieszany','UNKNOWN':'brak danych'}.get(v,'brak danych') for k,v in directions.items())+'. Zgodność horyzontów wzmacnia ocenę kierunku.']
    if hour_activity:reasons.append(f'Ostatnia pełna godzina: RVOL {fmt(rv)}×; aktywność przekracza 1,5 średniej pełnych godzin.')
    if number(daily_ratio):reasons.append(f'Ostatnia sesja: {fmt(rows[-1]["volume"])} akcji; średnia 20 wcześniejszych {fmt(avg)}; relacja {fmt(daily_ratio)}×.')
    if not hour_activity:reasons.append('Nie potwierdzono RVOL co najmniej 1,5× ostatniej pełnej godziny. Otwartej lub skróconej świecy nie porównano z pełną godziną.')
    if rolling_high:reasons.append(f'Zakres 20 zamkniętych sesji: {fmt(low)}–{fmt(rolling_high)}.')
    if high:reasons.append('Poziom obserwowanego wybicia '+fmt(high)+'. '+('Cena pozostaje ponad poziomem; brak wyższego oporu nie usuwa spółki.' if breakout else 'Cena pozostaje na lub pod poziomem.' ))
    if new_high:reasons.append('Nowe maksimum '+('52 tygodni.' if complete_52 else 'dostępnej historii; pełne 52 tygodnie niepotwierdzone.'))
    risks=[]
    if number(ind.get('rsi')) and ind['rsi']>=70:risks.append(f'RSI {fmt(ind["rsi"])}: podwyższony poziom oscylatora; kontroluj cofnięcie, samo wskazanie nie neguje wzrostu.')
    if number(ind.get('rsi')) and ind['rsi']<=30:risks.append(f'RSI {fmt(ind["rsi"])}: wyprzedanie; możliwe odbicie wymaga potwierdzenia ceną.')
    if directions['long']=='DOWN' and growth:risks.append('Długi trend spadkowy: bieżący wzrost nie potwierdza jeszcze jego odwrócenia.')
    if not complete_52:risks.append(f'Historia: {len(rows)} zamkniętych sesji; maksimum 52 tygodni nie jest potwierdzone pełnym zakresem.')
    if blocked:risks.append('Operacja na akcjach lub niespójna baza: stare poziomy wymagają weryfikacji.')
    if number(ind.get('adx')) and ind['adx']<20:risks.append('ADX '+fmt(ind['adx'])+' poniżej 20: słaba siła kierunkowego trendu według tej reguły; samo wybicie wymaga kontroli utrzymania poziomu.')
    return {'version':VERSION,'ticker':snapshot['ticker'],'as_of':snapshot['acquired_at'],'price':price,
            'currency':snapshot.get('currency'),'valid':bool(valid),'blocked':blocked,'growth_score':growth,'decline_score':decline,
            'directions':directions,'breakout':breakout,'breakdown':breakdown,'first_resistance':high,'support':low,
            'new_high':new_high,'full_52w':complete_52,'history_coverage':coverage,'activity':activity,'reasons':reasons,'risks':risks,
            'score_components':{'trend':{'up':trend_up,'down':trend_down},'momentum':{'up':momentum_up,'down':momentum_down},
                                'activity':{'up':activity if trend_up or momentum_up or breakout else 0,'down':activity if trend_down or momentum_down or breakdown else 0},
                                'structure':{'up':20 if breakout else 0,'down':20 if breakdown else 0}},
            'large_eligible':bool(valid and len(rows)>=60 and at-stamp(rows[-1]['end'])<=timedelta(days=7)
                                  and growth>=70 and directions['medium']=='UP' and directions['long']!='DOWN' and activity>=10 and breakout),
            'score_meaning':'Siła reguł technicznych /100; nie prawdopodobieństwo zysku.',
            'next_condition':('Utrzymanie przebitego poziomu '+fmt(high)+'; potwierdzenie przez późniejsze zamknięcie sesji.' if breakout else
                              'Wybicie i zamknięcie ponad '+fmt(high) if high else 'Uzupełnienie zamkniętej historii do oceny poziomów.')}


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS technical_radar(ticker TEXT PRIMARY KEY,as_of TEXT NOT NULL,payload TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS technical_watch(ticker TEXT PRIMARY KEY,opened_at TEXT NOT NULL,updated_at TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL)')


def confirmation(saved,state,rows):
    """Frozen resistance survives rolling history; daily close confirms it.

    The closing 30-minute US bar is never called a full one-hour bar. Daily
    confirmation uses the exchange's stored daily closed_at instead.
    """
    level=saved.get('breakout_level')
    if not level and state['breakout']:
        level=state['first_resistance'];saved['breakout_level']=level
        saved['breakout_detected_at']=state['as_of']
    if not level:return {'status':'WAITING','reason':state['next_condition']}
    start=stamp(saved.get('breakout_detected_at') or saved['entry_at'])
    later=[r for r in rows if number(r.get('close')) and stamp(r.get('closed_at'))
           and start<stamp(r['closed_at'])<=stamp(state['as_of'])]
    if state['price']<=level:
        return {'status':'PULLBACK','level':level,'reason':'Cena '+fmt(state['price'])+' wróciła na lub pod przebity poziom '+fmt(level)+'. Wcześniejsze potwierdzenie nie oznacza utrzymania poziomu w bieżącym odczycie.'}
    if later:
        latest=max(later,key=lambda r:stamp(r['closed_at']))
        if latest['close']>level:
            return {'status':'CONFIRMED','level':level,'closed_at':latest['closed_at'],
                    'reason':'Sesja '+str(latest.get('session_date',''))+' zamknięta na '+fmt(latest['close'])+' ponad zapisanym poziomem '+fmt(level)+'.'}
    return {'status':'DETECTED','level':level,'reason':'Cena '+fmt(state['price'])+' ponad '+fmt(level)+'. Oczekiwanie na późniejsze zamknięcie sesji ponad tym poziomem.'}


def record(api,store,snapshot):
    import large_movement
    with store.connection() as c:
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='technical_watch'").fetchone()
        previous=c.execute('SELECT payload FROM technical_watch WHERE ticker=?',(snapshot['ticker'],)).fetchone() if exists else None
    reference=api.load_payload(previous[0]) if previous else None
    result=evaluate(snapshot,large_movement.daily_rows(api,store,snapshot),reference)
    portfolio=next((e for e in api.portfolio_get(store) if e['ticker']==snapshot['ticker']),None)
    if reference:
        changed=any(stamp(action.get('effective_at')) and stamp(reference['entry_at'])<stamp(action['effective_at'])<=stamp(result['as_of'])
                    for action in snapshot.get('corporate_actions',[]))
        currency=(reference.get('latest') or {}).get('currency')
        if changed or currency and currency!=result['currency']:
            result.update(valid=False,blocked=True,growth_score=0,decline_score=0,large_eligible=False)
            result['risks'].append('Od początku obserwacji zmieniła się jednostka ceny lub waluta. Porównanie ze starymi poziomami wstrzymane.')
    with store.transaction() as c:
        schema(c)
        old=c.execute('SELECT as_of FROM technical_radar WHERE ticker=?',(result['ticker'],)).fetchone()
        if old and stamp(old[0])>=stamp(result['as_of']):return None
        c.execute('INSERT INTO technical_radar VALUES(?,?,?) ON CONFLICT(ticker) DO UPDATE SET as_of=excluded.as_of,payload=excluded.payload',
                  (result['ticker'],result['as_of'],api.json_text(result)))
        legacy=c.execute('SELECT * FROM large_movement_cases WHERE ticker=?', (result['ticker'],)).fetchone()
        if legacy and legacy['status'] in ('ACTIVE','WATCHING','WAIT','REVIEW_DUE','REVIEW_FAILED'):
            old=api.load_payload(legacy['result']) or {}
            entry={'entry_price':result['price'],'entry_at':result['as_of'],
                   'breakout_level':None,'invalidation':result['support'],
                   'latest':result,'last_score':result['growth_score'],
                   'legacy':{'status':legacy['status'],'opened_at':legacy['opened_at'],'assessment_at':old.get('as_of'),
                             'reference_price':old.get('reference_price')},
                   'origin':'Przeniesiona obserwacja; bieżące poziomy techniczne ustalono od nowa. Historyczna ocena AI zachowana oddzielnie.'}
            c.execute('INSERT OR IGNORE INTO technical_watch VALUES(?,?,?,?,?)',
                      (result['ticker'],result['as_of'],result['as_of'],'TRACKING',api.json_text(entry)))
        if portfolio:
            entry={'entry_price':result['price'],'entry_at':result['as_of'],'breakout_level':None,
                   'invalidation':result['support'],'latest':result,'last_score':result['growth_score'],'origin':'PORTFOLIO'}
            c.execute('INSERT OR IGNORE INTO technical_watch VALUES(?,?,?,?,?)',
                      (result['ticker'],result['as_of'],result['as_of'],'TRACKING',api.json_text(entry)))
    return result


def finish_cycle(api,store,now):
    """Persist TOP entries, then monitor all existing entries, independently of rank."""
    ticks=set(store.load_section('tickers',[]))|set(monitored_tickers(store));at=stamp(now)
    changes=[]
    with store.transaction() as c:
        schema(c)
        states=[json.loads(r[0]) for r in c.execute('SELECT payload FROM technical_radar')]
        stopped={r[0] for r in c.execute("SELECT ticker FROM technical_watch WHERE status IN ('INVALIDATED','BASIS_REVIEW','CLOSED')")}
        fresh=[s for s in states if s['ticker'] in ticks and s['ticker'] not in stopped and s['valid'] and timedelta(0)<=at-stamp(s['as_of'])<=timedelta(minutes=30)
               and api.market_session_open(s['ticker'],at)]
        top=sorted((s for s in fresh if s['growth_score']>=50 and s['growth_score']>s['decline_score']),key=lambda s:(-s['growth_score'],s['ticker']))[:5]
        for s in top:
            entry={'entry_price':s['price'],'entry_at':s['as_of'],'breakout_level':s['first_resistance'] if s['breakout'] else None,
                   'invalidation':s['support'],'latest':s,'last_score':s['growth_score']}
            inserted=c.execute('INSERT OR IGNORE INTO technical_watch VALUES(?,?,?,?,?)',(s['ticker'],s['as_of'],s['as_of'],'TRACKING',api.json_text(entry))).rowcount
            if inserted:changes.append((s,'TOP 5 — rozpoczęto trwałą obserwację'))
        for s in states:
            old=c.execute('SELECT * FROM technical_watch WHERE ticker=?',(s['ticker'],)).fetchone()
            if not old or stamp(s['as_of'])<stamp(old['updated_at']):continue
            saved=json.loads(old['payload']);before=old['status'];state=before
            if before in TERMINAL:continue
            if saved.get('evaluated_at')==s['as_of']:continue
            rows=api.load_daily_candles(store,s['ticker'])
            saved['confirmation']=confirmation(saved,s,rows)
            if s['blocked']:state='BASIS_REVIEW'
            elif not s['valid']:state='DATA_WAIT'
            else:
                # Frozen daily support is invalidated only by a later closed daily bar.
                later=[r for r in rows if r.get('closed_at') and stamp(r['closed_at']) and stamp(saved['entry_at'])<stamp(r['closed_at'])<=stamp(s['as_of'])]
                latest=max(later,key=lambda r:stamp(r['closed_at'])) if later else None
                if saved.get('invalidation') and latest and latest['close']<saved['invalidation']:state='INVALIDATED'
                elif s['valid']:
                    weakened=s['growth_score']<40 or s['decline_score']>s['growth_score'] or saved['confirmation']['status']=='PULLBACK'
                    qualified=s['large_eligible'] and saved['confirmation']['status']=='CONFIRMED'
                    retained=bool(saved.get('large_since') and s['growth_score']>=50 and s['directions']['medium']!='DOWN'
                                  and saved['confirmation']['status']=='CONFIRMED')
                    state='WEAKENED' if weakened else 'LARGE' if qualified or retained else 'TRACKING'
                    if state=='LARGE' and not saved.get('large_since'):saved['large_since']=s['as_of']
            saved.update(latest=s,previous_score=saved.get('last_score'),last_score=s['growth_score'],evaluated_at=s['as_of'])
            c.execute('UPDATE technical_watch SET updated_at=?,status=?,payload=? WHERE ticker=?',(s['as_of'],state,api.json_text(saved),s['ticker']))
            if state!=before:changes.append((s,LABELS[state]))
        # One digest; no notification for merely dropping out of the live rank.
        settings=store.load_section('settings',{})
        notify_changes=[(s,label) for s,label in changes
                        if (label.startswith('TOP 5') or label==LABELS['LARGE'])
                        and timedelta(0)<=at-stamp(s['as_of'])<=timedelta(minutes=30)]
        if notify_changes and settings.get('telegram_enabled'):
            import hashlib
            notify_changes=list({(s['ticker'],label):(s,label) for s,label in notify_changes}.values())
            members=[(s['ticker'],label,s['as_of']) for s,label in notify_changes[:5]]
            identifier='technical_'+hashlib.sha256(api.json_text(members).encode()).hexdigest()[:24]
            message='KI · ZMIANY TECHNICZNE\n'+'\n\n'.join(s['ticker']+' · '+label+'\nOcena '+str(s['growth_score'])+'/100 · '+fmt(s['price'])+' '+str(s['currency'])+'\n'+s['next_condition'] for s,label in notify_changes[:5])
            if len(notify_changes)>5:message+='\n\nPozostałe zmiany: '+str(len(notify_changes)-5)+' — pełna lista w panelu.'
            c.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)',(identifier,'TECHNICAL','1h',now,api.json_text({'members':members})))
            c.execute('INSERT OR IGNORE INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',
                      (identifier,identifier,'TECHNICAL_DIGEST',message,'PENDING',now))
    return changes


def delivery_valid(c,payload):
    """A newer technical observation invalidates the frozen pending message."""
    members=json.loads(payload).get('members') or []
    if not members:return False
    try:
        for ticker,label,at in members:
            current=c.execute('SELECT as_of FROM technical_radar WHERE ticker=?',(ticker,)).fetchone()
            if not current or stamp(current[0])!=stamp(at):return False
        return True
    except (ValueError,TypeError,sqlite3.Error):return False


def close_watch(store,ticker,now=None):
    at=(now or datetime.now(timezone.utc)).isoformat()
    with store.transaction() as c:
        row=c.execute('SELECT payload FROM technical_watch WHERE ticker=?',(ticker,)).fetchone()
        if not row:return False
        saved=json.loads(row[0]);saved['closed_at']=at
        c.execute("UPDATE technical_watch SET status='CLOSED',payload=? WHERE ticker=?",(json.dumps(saved,ensure_ascii=False),ticker))
    return True


def render(store,large=False,tickers=None):
    import streamlit as st
    st.subheader('Duży potencjał · technika' if large else 'Radar techniczny · TOP 5 i trwała obserwacja')
    st.caption('Ocena reguł /100. Trend 40, momentum 20, aktywność 20, struktura 20. Brakujące dane nie dostają punktów. Awans techniczny nie oznacza prognozy wzrostu o 50–100%.')
    with store.connection() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='technical_watch'").fetchone():
            st.info('Oczekiwanie na pierwszy cykl radaru.');return
        watches=[dict(r) for r in c.execute('SELECT * FROM technical_watch ORDER BY updated_at DESC')]
        states=[json.loads(r[0]) for r in c.execute('SELECT payload FROM technical_radar')]
        ai_by_ticker={}
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='radar_ai_jobs'").fetchone():
            for r in c.execute('SELECT ticker,state,market_at,result FROM radar_ai_jobs ORDER BY created_at DESC'):
                ai_by_ticker.setdefault(r['ticker'],dict(r))
    if tickers is not None:
        watches=[r for r in watches if r['ticker'] in tickers]
        states=[s for s in states if s['ticker'] in tickers]
    if not large:
        now=datetime.now(timezone.utc)
        stopped={r['ticker'] for r in watches if r['status'] in TERMINAL}
        ranked=sorted((s for s in states if s['ticker'] not in stopped and s['valid'] and s['growth_score']>=50 and s['growth_score']>s['decline_score'] and timedelta(0)<=now-stamp(s['as_of'])<=timedelta(minutes=30)),key=lambda s:(-s['growth_score'],s['ticker']))[:5]
        st.write('Bieżący zapis rankingu: '+(', '.join(s['ticker']+' '+str(s['growth_score'])+'/100' for s in ranked) or 'brak kwalifikujących się spółek'))
        if ranked:st.html(ranking_cards_html(ranked,ai_by_ticker))
        falling=sorted((s for s in states if s['valid'] and s['decline_score']>=50 and timedelta(0)<=now-stamp(s['as_of'])<=timedelta(minutes=30)),key=lambda s:(-s['decline_score'],s['ticker']))[:5]
        st.write('Ostrzeżenia spadkowe: '+(', '.join(s['ticker']+' '+str(s['decline_score'])+'/100' for s in falling) or 'brak świeżych kwalifikacji'))
    else:
        large_states=[]
        by_ticker={s['ticker']:s for s in states}
        for row in watches:
            if row['status']=='LARGE' or json.loads(row['payload']).get('large_since'):
                if row['ticker'] in by_ticker:large_states.append(by_ticker[row['ticker']])
        if large_states:st.html(ranking_cards_html(large_states,ai_by_ticker))
    for row in watches:
        data=json.loads(row['payload']);s=data['latest']
        if large and row['status']!='LARGE' and not data.get('large_since'):continue
        with st.expander(row['ticker']+' · '+LABELS[row['status']]):
            st.write('Ostatni odczyt: '+s['as_of']+' · '+fmt(s['price'])+' '+str(s['currency']))
            if datetime.now(timezone.utc)-stamp(s['as_of'])>timedelta(minutes=30):
                st.caption('Zapis historyczny. Poza sesją cena może pozostać z ostatniego dnia notowań; w trakcie sesji sprawdź stan pobierania, jeśli nie pojawiają się kolejne odczyty.')
            st.write('Obserwacja od: '+row['opened_at']+' · cena '+fmt(data['entry_price']))
            if data.get('legacy'):
                legacy=data['legacy']
                st.caption('Poprzednia ocena AI: '+str(legacy.get('assessment_at') or 'brak daty')+' · dawny stan '+str(legacy.get('status'))+'. Bieżąca ocena poniżej jest techniczna.')
            if data.get('large_since'):st.write('Kwalifikacja do Dużego potencjału od: '+data['large_since'])
            st.write('Ocena wzrostowa '+str(s['growth_score'])+'/100; spadkowa '+str(s['decline_score'])+'/100.')
            previous=data.get('previous_score')
            if number(previous):st.write('Zmiana oceny wzrostowej: '+str(previous)+' → '+str(s['growth_score'])+'.')
            for reason in s['reasons']:st.write(reason)
            if row['status'] in TERMINAL:st.write('Scenariusz zakończony lub wstrzymany; historyczne poziomy nie stanowią bieżącej kwalifikacji.')
            elif row['status']=='LARGE':st.write('Utrzymanie: cena ponad zapisanym poziomem wybicia, brak przewagi spadkowej i brak zanegowania dziennego wsparcia.')
            else:st.write('Następny warunek: '+s['next_condition'])
            if data.get('confirmation'):st.write('Potwierdzenie wybicia: '+data['confirmation']['reason'])
            st.write('Zanegowanie: późniejsza zamknięta sesja poniżej '+fmt(data.get('invalidation')) if data.get('invalidation') else 'Brak potwierdzonego dziennego poziomu zanegowania.')
            for risk in s['risks']:st.caption(risk)
            import radar_ai
            radar_ai.render_latest(store,row['ticker'])
            st.caption('Data dotyczy zapisanych danych. Aktywna obserwacja pozostaje na liście pobierania także poza bieżącym rankingiem. Dane rynkowe zmieniają się w czasie sesji.')
            if row['status'] not in TERMINAL and st.button('Zakończ obserwację '+row['ticker'],key='radar_close_'+row['ticker']):
                close_watch(store,row['ticker']);st.rerun()
