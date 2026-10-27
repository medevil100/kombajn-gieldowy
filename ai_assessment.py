"""Local contract for the three AI assessment axes. No model calls or repairs."""
import math
import re

AXES=('movement','activity','risk')


def quote_candidates(source):
    candidates=[]
    for match in re.finditer(r'[^.!?\n]+(?:[.!?]|$)',source.get('content') or ''):
        sentence=match.group().strip()
        if not 5<=len(sentence.split())<=25 or len(sentence)>180:continue
        if re.search(r'cookie|copyright|privacy|disclaimer|forward.looking|subscribe|register|log.?in|polityk\w*\s+prywatno|wszelkie prawa|\b(?:buy|sell|kupuj|sprzedaj)\b',sentence,re.I):continue
        if sentence not in candidates:candidates.append(sentence)
        if len(candidates)==5:break
    return candidates


def unsupported_story(value):
    """Conservative guard for selected investor-behaviour narratives, not an NLP proof."""
    for sentence in re.split(r'[.!?;]',value):
        narrative=re.search(r'sentyment|realizacj\w*\s+zysk|panik|eufori|inwestor(?:zy|ów)|napływ\w*\s+kapita|odpływ\w*\s+kapita|reakcj\w*\s+rynku',sentence,re.I)
        causal=re.search(r'(?:wzrost|spadek|ruch|zmian\w*\s+ceny).{0,35}(?:wynika|wynik|spowodowan|wywoła|reakcj|efekt|dzięki)|(?:spowodował|wywołał).{0,25}(?:ruch|wzrost|spad)',sentence,re.I)
        if not narrative and not causal:continue
        if re.search(r'brak\s+(?:dowod|podstaw|danych)|nie\s+(?:można|ustalono|potwierdzono|dowodzi|oznacza|przypis)|nieustalon',sentence,re.I):continue
        return True
    return False


def summary_text(result):
    value=result.get('assessment')
    if isinstance(value,str):return value.strip()
    if isinstance(value,dict) and set(value)==set(AXES) and all(isinstance(value[k],str) and value[k].strip() for k in AXES):
        return ' '.join(value[k].strip() for k in AXES)
    return ''


def validate_axes(value,snapshot,manifest):
    empty=dict.fromkeys(AXES,'');errors=[]
    if not isinstance(value,dict) or set(value)!=set(AXES):return empty,['wymagane osobne pola movement, activity i risk']
    patterns={'movement':r'ruch|wzrost|spad|kierunk|momentum|trend|sygnał|wskaza',
              'activity':r'aktywno|wolumen|obrót|świec|godzin',
              'risk':r'ryzyk|ofert|bid|ask|spread|wykon|ogranicz|płynno|plan|potencjał'}
    clean={}
    for key in AXES:
        text=value[key]
        if not isinstance(text,str) or not text.strip() or len(text)>150:
            errors.append(key+': wymagany tekst do 150 znaków');continue
        text=text.strip()
        if re.search(r'\d|\b(?:buy|sell|kup|kupuj|sprzedaj|sprzedawaj)\b|gwarant|bezpieczn|potwierdz\w*.{0,45}kontynuacj',text,re.I):errors.append(key+': liczby, polecenie lub nieuprawniona pewność')
        if unsupported_story(text):errors.append(key+': nieudokumentowana narracja o inwestorach lub przyczynie')
        if not re.search(patterns[key],text,re.I):errors.append(key+': tekst nie dotyczy wymaganej osi')
        clean[key]=text
    if errors:return empty,errors
    movement=clean['movement'];activity=clean['activity'];risk=clean['risk']
    local=(manifest.get('technical') or {}).get('assessment','')
    if local=='Wskazania mieszane' and not re.search(r'mieszan|sprzecz|niejednoznacz|rozbież|częściow|nie.{0,30}potwierdz',movement,re.I):
        errors.append('movement: pominięto mieszane wskazania')
    if local=='Bieżące wskazania przeczą ruchowi od bazy' and not re.search(r'przecz|sprzecz|rozbież|cofnię|niezgod',movement,re.I):errors.append('movement: pominięto wskazania przeczące ruchowi')
    q=snapshot.get('spread') or {}
    valid=lambda v:isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) and v>0
    quotes=valid(q.get('bid')) and valid(q.get('ask')) and q['ask']>=q['bid']
    if not quotes and not re.search(r'brak|nie.{0,25}(?:ocen|potwierdz|znan)|nieocen|niepotwierdz|ogranicz',risk,re.I):errors.append('risk: brak ofert wymaga ograniczenia oceny')
    if not q.get('freshness_confirmed') and re.search(r'nisk\w*\s+ryzyk|ryzyk\w*.{0,12}nisk|wąsk\w*\s+spread|dobr\w*\s+płynno|wysok\w*\s+płynno|płynno\w*.{0,12}wysok',risk,re.I):
        errors.append('risk: brak podstaw do zapewnień o bezpieczeństwie lub płynności')
    rv=snapshot.get('rvol')
    partial_caveat=bool(re.search(r'częściow|niepełn|za wcześnie|nie rozstrzyg|brak.{0,25}danych|nie.{0,25}ocen',activity,re.I))
    if (manifest.get('activity') or {}).get('status')=='PARTIAL' and not partial_caveat:errors.append('activity: niepełne dane wymagają jawnego ograniczenia oceny')
    if snapshot.get('candle_status')=='OPEN' and re.search(r'nisk|słab|poniżej',activity,re.I) and not partial_caveat:errors.append('activity: pominięto częściowy wolumen godziny')
    plan=manifest.get('trade_plan') or {}
    if plan.get('status')=='INDICATIVE' and plan.get('rr1',1)<1 and not re.search(r'potencjał|zysk|relacj',risk,re.I):errors.append('risk: pominięto słabą relację potencjału do ryzyka')
    return (empty if errors else clean),errors
