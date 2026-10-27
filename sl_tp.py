"""Deterministic long-side scenario from completed hourly candles; no network."""
import math
from datetime import datetime, timedelta, timezone


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0


def stamp(value):
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return dt if dt.tzinfo else None
    except (ValueError,TypeError):return None


def build_plan(snapshot,change,now=None):
    now=now or datetime.now(timezone.utc)
    at=stamp(snapshot.get('acquired_at'))
    plan={'version':1,'status':'UNAVAILABLE','side':'LONG','as_of':snapshot.get('acquired_at'),
          'currency':snapshot.get('currency'),'reason':'','method':'60 zamkniętych świec 1h; pivots 2+2; SL poniżej wsparcia o 0,25 ATR, co najmniej 1 ATR od wejścia; TP: dwa najbliższe opory.',
          'execution_confirmed':False}
    def missing(reason):
        plan['reason']=reason
        return plan
    if not at or not -60<=(now-at).total_seconds()<=900:return missing('Brak świeżego odczytu ceny (limit 15 minut).')
    if snapshot.get('interval')!='1h':return missing('Plan wymaga świec 1h.')
    if snapshot.get('currency') not in ('PLN','USD'):return missing('Brak obsługiwanej waluty PLN/USD.')
    if snapshot.get('latest_price_origin')=='carried_previous_close':return missing('Cena pochodzi z przeniesionego zamknięcia.')
    price=snapshot.get('price');atr=(snapshot.get('indicators') or {}).get('atr')
    if not number(price):return missing('Brak poprawnej ceny.')
    rows=[];seen=set()
    for row in snapshot.get('chart_history') or []:
        start=stamp(row.get('time'));end=stamp(row.get('end'))
        if row.get('status')!='CLOSED' or not start or not end or not start<end<=at:continue
        if (end-start).total_seconds()!=3600:continue
        if row.get('price_origin')=='carried_previous_close' or not number(row.get('volume')):continue
        if not all(number(row.get(k)) for k in ('open','high','low','close')):continue
        if not row['low']<=min(row['open'],row['close'])<=max(row['open'],row['close'])<=row['high']:continue
        if start in seen:continue
        rows.append(row);seen.add(start)
    rows=sorted(rows,key=lambda r:stamp(r['time']))[-60:]
    if len(rows)<20:return missing('Za mało pełnych świec z obrotem: wymagane co najmniej 20.')
    q=snapshot.get('spread') or {}
    valid_quotes=number(q.get('bid')) and number(q.get('ask')) and q['ask']>=q['bid']
    # Timestamp evidence, not a boolean alone, is needed to use an ask as entry.
    qt=stamp(q.get('acquired_at') or q.get('updated_at') or q.get('timestamp'))
    fresh=valid_quotes and q.get('freshness_confirmed') is True and qt and 0<=(at-qt).total_seconds()<=60
    entry=q['ask'] if fresh else price
    supports=[];resistances=[]
    for idx in range(2,len(rows)-2):
        r=rows[idx];neighbours=rows[idx-2:idx]+rows[idx+1:idx+3]
        if r['low']<price and all(r['low']<n['low'] for n in neighbours):supports.append(r)
        if r['high']>price and all(r['high']>n['high'] for n in neighbours):resistances.append(r)
    if not supports:return missing('Brak potwierdzonego lokalnego wsparcia poniżej ceny.')
    support=max(supports,key=lambda r:r['low'])
    targets=[]
    for r in sorted(resistances,key=lambda r:r['high']):
        if not targets or (r['high']>targets[-1]['high'] and r['high']-targets[-1]['high']>=(.25*atr if number(atr) else 0)):targets.append(r)
        if len(targets)==2:break
    plan.update(reference_price=price,support={'price':support['low'],'time':support['time']},
                resistances=[{'price':r['high'],'time':r['time']} for r in targets],
                support_distance_pct=(price-support['low'])/price*100)
    if targets:plan.update(resistance=targets[0]['high'],resistance_distance_pct=(targets[0]['high']-price)/price*100)
    if not number(change):
        plan['side']='NONE'
        return missing('Ruch nie jest wzrostowy: poziomy techniczne bez planu kupna ani założenia krótkiej sprzedaży.')
    if not number(atr):return missing('Brak poprawnego ATR do planu SL/TP.')
    if len(targets)<2:return missing('Brak dwóch odrębnych potwierdzonych oporów powyżej ceny.')
    sl=min(support['low']-.25*atr,entry-atr)
    if sl<=0:return missing('SL wynikający ze wsparcia i ATR jest niepoprawny.')
    spread=q['ask']-q['bid'] if valid_quotes and not fresh else 0.
    risk=entry-sl+spread
    rewards=[r['high']-entry-spread for r in targets]
    if min(rewards)<=0:return missing('Spread pochłania potencjał do pierwszego oporu.')
    ratios=[v/risk for v in rewards]
    plan.update(status='INDICATIVE',entry=entry,entry_basis='ask z potwierdzonym czasem' if fresh else 'ostatnia cena; orientacyjnie',
                sl=sl,tp1=targets[0]['high'],tp2=targets[1]['high'],rr1=ratios[0],rr2=ratios[1],
                reference_price=price,support_distance_pct=(price-support['low'])/price*100,
                resistance_distance_pct=(targets[0]['high']-price)/price*100,
                support={'price':support['low'],'time':support['time']},
                resistances=[{'price':r['high'],'time':r['time']} for r in targets],atr=atr,
                candle_count=len(rows),spread_cost=spread,quote_freshness_confirmed=bool(fresh),
                spread_basis='wejście po ask; spread zawarty w odległościach' if fresh else 'doliczony ostatni spread; czas ofert niepotwierdzony' if valid_quotes else 'brak ofert: spread nieujęty w relacji zysku do ryzyka',
                valid_until=(at+timedelta(minutes=15)).isoformat(),
                reason='Poziomy orientacyjne; wykonalność niepotwierdzona. Prowizje i poślizg nieujęte. '+('Potencjał TP1 mniejszy od ryzyka.' if ratios[0]<1 else ''))
    return plan


def movement_space_line(plan):
    if not plan.get('support') or not plan.get('resistances'):return 'Przestrzeń ruchu: brak kompletu potwierdzonych poziomów.'
    reference=plan.get('reference_price') or plan.get('entry')
    support=plan['support']['price'];resistance=plan['resistances'][0]['price']
    down=(reference-support)/reference*100;up=(resistance-reference)/reference*100
    fmt=lambda v,n:format(v,'.'+str(n)+'f').replace('.',',')
    return ('Wsparcie '+fmt(support,4)+' · opór '+fmt(resistance,4)+' '+str(plan.get('currency') or '')+
            ' · od ceny '+fmt(reference,4)+': do wsparcia −'+fmt(down,2)+'%, do oporu +'+fmt(up,2)+'%.'+
            ' Poziomy orientacyjne.')


def plan_lines(plan,details=False,now=None):
    if plan.get('status')!='INDICATIVE':
        lines=['SL/TP: brak podstaw do planu — '+plan.get('reason','brak danych')]
        if details:lines.append(movement_space_line(plan))
        return lines
    until=stamp(plan.get('valid_until'))
    expired=not until or (now or datetime.now(timezone.utc))>until
    fmt=lambda v:format(v,'.4f').replace('.',',')
    lines=[('SL/TP — zapis historyczny' if expired else 'SL/TP orientacyjnie')+': SL '+fmt(plan['sl'])+' · TP1 '+fmt(plan['tp1'])+' · TP2 '+fmt(plan['tp2'])+' '+str(plan.get('currency') or '')+
           ' · zysk/ryzyko '+format(plan['rr1'],'.2f')+'/'+format(plan['rr2'],'.2f')+'.'+(' TP1: potencjał mniejszy od ryzyka.' if plan['rr1']<1 else '')]
    if details:
        lines.append(movement_space_line(plan))
        lines.extend(['Wejście odniesienia: '+fmt(plan['entry'])+' · '+plan['entry_basis'],
                      'Odczyt: '+str(plan['as_of'])+' · ważność do: '+str(plan['valid_until']),
                      plan['method'],'Wsparcie: '+str(plan['support'])+' · opory: '+str(plan['resistances']),
                      'ATR: '+fmt(plan['atr'])+' · '+plan['spread_basis'],plan['reason']])
    return lines
