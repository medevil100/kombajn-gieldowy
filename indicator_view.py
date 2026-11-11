"""Read-only presentation of recorded indicators. No scoring, IO or API calls."""
from datetime import datetime, timezone
from html import escape
import math


CSS = '''<style>
.ki-indicators{width:100%;min-width:0;color:#edf2f7;font-size:14px}
.ki-indicators *{box-sizing:border-box}
.ki-indicators .ki-i-note{color:#b8c4d4;font-size:12px;overflow-wrap:anywhere}
.ki-indicators .ki-i-row{display:grid;grid-template-columns:minmax(120px,1fr) minmax(100px,.8fr) minmax(160px,1.6fr);gap:10px;padding:10px 12px;border-bottom:1px solid #354252;border-left:4px solid var(--ki-tone);background:#182330}
.ki-indicators .ki-i-row strong{font-variant-numeric:tabular-nums;color:var(--ki-tone);overflow-wrap:anywhere}
.ki-indicators .ki-i-status{color:var(--ki-tone);overflow-wrap:anywhere}
.ki-indicators .ki-i-meaning{display:block;color:#b8c4d4;font-size:12px;margin-top:4px}
.ki-indicators .ki-i-meter{position:relative;height:10px;background:#354252;border-radius:6px;margin:8px 8px 5px}
.ki-indicators .ki-i-dot{position:absolute;left:var(--ki-pos);top:-3px;width:4px;height:16px;background:#fff;border:1px solid #182330;transform:translateX(-50%)}
.ki-indicators .ki-i-scale{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#b8c4d4}
.ki-indicators .ki-i-bb{padding:12px;border:1px solid #526173;border-radius:8px;margin:10px 0;background:#182330}
.ki-indicators .ki-i-bb .ki-i-meter{background:linear-gradient(90deg,#344965 0%,#72859c 50%,#344965 100%)}
.ki-indicators .ki-i-middle{position:absolute;left:var(--ki-mid);height:10px;border-left:1px dashed #fff}
@media(max-width:600px){.ki-indicators .ki-i-row{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:5px;padding:9px 8px}.ki-indicators .ki-i-status{grid-column:1/-1}.ki-indicators .ki-i-row strong{text-align:right}.ki-indicators .ki-i-scale{flex-wrap:wrap}.ki-indicators{font-size:13px}}
</style>'''
TONES = {'up': ('#68dfaa', '↑'), 'down': ('#ff929b', '↓'),
         'attention': ('#ffd17b', '•'), 'neutral': ('#b8c4d4', '—')}
KEYS = {'RSI':'rsi','SMA 10':'ma_fast','SMA 30':'ma_slow','MACD':'last_macd',
        'Sygnał MACD':'last_macd_signal','Histogram MACD':'last_macd_hist','ADX':'adx',
        '+DI':'plus_di','−DI':'minus_di','Stochastic %K':'stoch_k','Stochastic %D':'stoch_d',
        'BB górne':'last_upper_bb','BB środek · SMA 20':'bb_sma','BB dolne':'last_lower_bb',
        'ATR':'atr','VWMA 20':'vwma','ROC':'roc','OBV':'obv','RVOL':'rvol',
        'VWAP sesji (ze świec)':'vwap','Stoch RSI %K':'stoch_rsi_k','Stoch RSI %D':'stoch_rsi_d'}
RATIOS = (0,23.6,38.2,50,61.8,78.6,100)


def number(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)


def fmt(value, digits=2):
    return f'{value:,.{digits}f}'.replace(',', ' ').replace('.', ',')


def recorded_age(snapshot, now):
    try:
        stamp=datetime.fromisoformat(str(snapshot.get('acquired_at')).replace('Z','+00:00'))
        return (now-stamp).total_seconds() if stamp.tzinfo is not None else None
    except (ValueError,TypeError,OverflowError):
        return None


def values(snapshot):
    result=dict(snapshot.get('indicators') or {})
    extra=snapshot.get('supplemental_indicators') or {}
    for key in ('vwap','stoch_rsi_k','stoch_rsi_d'):
        result[key]=extra.get(key)
    levels=extra.get('fibonacci') or []
    if len(levels)==len(RATIOS):
        result.update({f'fib_{r:g}':v for r,v in zip(RATIOS,levels)})
    return result


def relation(price, level):
    if not number(price) or price<=0 or not number(level) or level<=0:
        return 'neutral','Brak ceny lub poprawnego poziomu',None
    delta=(price/level-1)*100
    if abs(delta)<1e-9:return 'attention','Cena na poziomie · 0,00%',None
    return ('up' if delta>0 else 'down',
            'Cena '+('powyżej' if delta>0 else 'poniżej')+' · '+fmt(delta)+'%',None)


def describe(key, data, snapshot):
    value=data.get(key);price=snapshot.get('price')
    if not number(value):return 'neutral','Brak danych',None
    if key in ('ma_fast','ma_slow','vwma','vwap','last_upper_bb','last_lower_bb','bb_sma') or key.startswith('fib_'):
        return relation(price,value)
    if key in ('rsi','stoch_k','stoch_d','stoch_rsi_k','stoch_rsi_d'):
        if not 0<=value<=100:return 'neutral','Wartość poza skalą 0–100',None
        low,high=(30,70) if key=='rsi' else (20,80)
        if value<low:label='Dolna strefa · nie potwierdza odbicia'
        elif value>high:label='Górna strefa · nie potwierdza spadku'
        else:label='Środkowa strefa skali'
        return ('attention' if value<low or value>high else 'neutral'),label,value
    if key in ('last_macd','last_macd_signal','last_macd_hist'):
        macd,signal=data.get('last_macd'),data.get('last_macd_signal')
        diff=value if key=='last_macd_hist' else macd-signal if number(macd) and number(signal) else None
        if diff is None:return 'neutral','Brak drugiej linii do porównania',None
        return ('up' if diff>0 else 'down' if diff<0 else 'attention',
                'MACD '+('powyżej' if diff>0 else 'poniżej' if diff<0 else 'na')+' linii sygnału · bez oceny przecięcia',None)
    if key in ('plus_di','minus_di'):
        plus,minus=data.get('plus_di'),data.get('minus_di')
        if not number(plus) or not number(minus):return 'neutral','Brak pary +DI / −DI',None
        return ('up' if plus>minus else 'down' if plus<minus else 'attention',
                '+DI > −DI' if plus>minus else '−DI > +DI' if plus<minus else '+DI = −DI',None)
    if key=='adx':return 'neutral',('Niska siła trendu' if value<20 else 'Siła trendu: ADX ≥ 20')+' · bez kierunku',None
    if key=='atr':return 'neutral',('Zmienność · '+fmt(value/price*100)+'% ceny' if value>=0 and number(price) and price>0 else 'Brak poprawnej ceny lub ATR')+' · bez kierunku',None
    if key=='obv':return 'neutral','Poziom skumulowany · brak porównania z poprzednią świecą',None
    if key=='roc':return ('up' if value>0 else 'down' if value<0 else 'attention'),'Zmiana w oknie ROC · nie zmiana dzienna',None
    if key=='rvol':
        if value<0:return 'neutral','Niepoprawny RVOL',None
        if snapshot.get('partial_interval'):return 'neutral','Skrócona świeca · bez porównania z pełną godziną',None
        label='Wolumen '+('powyżej' if value>1 else 'poniżej' if value<1 else 'równy')+' średniej'
        if snapshot.get('candle_status')!='CLOSED' or snapshot.get('rvol_incomplete'):
            label+=' · pomiar częściowy'
        return 'attention' if value>1 else 'neutral',label,None
    return 'neutral','Brak porównania dla tego pola',None


def meter(position, left='0', right='100'):
    pos=min(100,max(0,position))
    return ('<div class="ki-i-meter"><span class="ki-i-dot" style="--ki-pos:'+f'{pos:.4f}%'
            +'"></span></div><div class="ki-i-scale"><span>'+escape(left)+'</span><span>'+escape(right)+'</span></div>')


def bollinger(snapshot, data):
    price=snapshot.get('price');low=data.get('last_lower_bb');mid=data.get('bb_sma');high=data.get('last_upper_bb')
    if not all(number(v) and v>0 for v in (price,low,mid,high)) or not low<mid<high:
        return '<div class="ki-i-bb">Bollinger: brak kompletu spójnych danych ceny i pasma.</div>'
    label=('poniżej dolnej wstęgi' if price<low else 'na dolnej wstędze' if price==low else
           'między dolną wstęgą a środkiem' if price<mid else 'na środku pasma' if price==mid else
           'między środkiem a górną wstęgą' if price<high else 'na górnej wstędze' if price==high else 'powyżej górnej wstęgi')
    unit=str(snapshot.get('currency') or '')
    pos=(price-low)/(high-low)*100;middle=(mid-low)/(high-low)*100
    bar=meter(pos,'Dolna '+fmt(low,4),'Górna '+fmt(high,4))
    bar=bar.replace('<span class="ki-i-dot"','<span class="ki-i-middle" style="--ki-mid:'+f'{middle:.4f}%'
                    +'"></span><span class="ki-i-dot"')
    return ('<div class="ki-i-bb"><strong>Bollinger · cena '+fmt(price,4)+' '+escape(unit)+'</strong>'
            +'<div>Cena '+label+'</div>'+bar+'<div class="ki-i-note">Środek '+fmt(mid,4)
            +' · Pozycja w paśmie: '+fmt(pos)+'%. Poza pasmem znacznik jest na brzegu skali.</div></div>')


def render_html(snapshot, rows, now=None):
    """Render existing values without modifying snapshot, rows, scoring or AI data."""
    now=now or datetime.now(timezone.utc);data=values(snapshot);age=recorded_age(snapshot,now)
    dated=age is not None and age>=0
    result=CSS+'<div class="ki-indicators notranslate" lang="pl" translate="no">'
    result+='<div class="ki-i-note">↑ zielony: relacja wzrostowa · ↓ czerwony: spadkowa · • bursztynowy: uwaga · — szary: neutralne lub brak danych.</div>'
    result+='<div class="ki-i-note">Zapis: '+escape(str(snapshot.get('acquired_at') or 'brak czasu'))+' · '
    result+=('Zapis historyczny — kolory opisują sytuację w chwili tego odczytu, nie aktualny rynek.' if dated and age>1200
             else 'Kolory dotyczą tej migawki.' if dated
             else 'Czas odczytu niepotwierdzony — oznaczenia neutralne; opisy dotyczą zapisanych wartości.')+'</div>'
    result+=bollinger(snapshot,data)
    for row in rows:
        label=str(row.get('Wskaźnik',''));key=KEYS.get(label,'')
        if label.startswith('Fibonacci '):key='fib_'+label.split(' ',1)[1].replace('%','').replace(',','.')
        tone,text,position=describe(key,data,snapshot)
        if not dated:tone='neutral'
        color,symbol=TONES[tone]
        meaning=str(row.get('Znaczenie') or '')
        result+='<div class="ki-i-row" style="--ki-tone:'+color+'"><span>'+escape(label)+'</span><strong>'+escape(str(row.get('Wartość','Brak danych')))+'</strong><div class="ki-i-status">'+symbol+' '+escape(text)
        if position is not None:result+=meter(position)
        if meaning:result+='<span class="ki-i-meaning">'+escape(meaning)+'</span>'
        result+='</div></div>'
    return result+'<div class="ki-i-note">Relacje wskaźników nie zastępują końcowej oceny. Przecięcia i zmiany w czasie są w zdarzeniach technicznych.</div></div>'
