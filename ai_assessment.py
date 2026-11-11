"""Local contract for the three AI assessment axes. No model calls or repairs."""
import math
import re
import json
from session_context import shortened_activity_ready

AXES=('movement','activity','risk')


def quote_candidates(source,aliases=None):
    import unicodedata
    def normalized(value):
        value=unicodedata.normalize('NFKD',value.casefold().replace('ł','l'))
        return ' '.join(re.findall(r'[^\W_]+',''.join(c for c in value if not unicodedata.combining(c))))
    identities=[normalized(a) for a in aliases or [] if isinstance(a,str) and a.strip()]
    candidates=[]
    for match in re.finditer(r'(?:[^.!?\n]|(?<=\d)\.(?=\d))+(?:[.!?]|$)',source.get('content') or ''):
        sentence=match.group().strip()
        if not 5<=len(sentence.split())<=25 or len(sentence)>180:continue
        if re.search(r'\bImage\s+\d+|https?://|\]\(|###',sentence,re.I):continue
        if re.search(r'\b(?:S|Sp|Inc|Ltd)\.$',sentence):continue
        if aliases is not None and not any(' '+alias+' ' in ' '+normalized(sentence)+' ' for alias in identities):continue
        if re.search(r'cookie|copyright|privacy|disclaimer|forward.looking|subscribe|register|log.?in|polityk\w*\s+prywatno|wszelkie prawa|\b(?:buy|sell|kup|kupuj|sprzedaj|sprzedawaj)\b',sentence,re.I):continue
        if sentence not in candidates:candidates.append(sentence)
        if len(candidates)==5:break
    return candidates


def source_quote_catalog(sources, aliases):
    """Only verified literal fragments; short ASCII IDs are the wire format."""
    catalog=[]
    for source in sources:
        for fact in quote_candidates(source,aliases):
            catalog.append({'quote_id':'Q'+str(len(catalog)+1),
                            'source_id':source['id'],'fact':fact})
    return catalog


def prepared_quote_catalog(context):
    """Frozen mapping from the saved request, not a provider-created citation."""
    request=context.get('prepared_ai_request') or {}
    for message in request.get('messages',[]):
        if message.get('role')!='user':continue
        try:source_context=json.loads(message['content']).get('source_context') or {}
        except (ValueError,TypeError,KeyError,AttributeError):continue
        if source_context.get('quote_reference_version')!=1:continue
        catalog=source_context.get('quote_catalog')
        if not isinstance(catalog,list):return {}
        result={}
        for item in catalog:
            if (not isinstance(item,dict) or set(item)!={'quote_id','source_id','fact'}
                or not all(isinstance(v,str) for v in item.values())
                or not re.fullmatch(r'Q[1-9][0-9]*',item['quote_id'])
                or item['quote_id'] in result):return {}
            result[item['quote_id']]=item
        return result
    return {}


def unsupported_story(value):
    """Conservative guard for selected investor-behaviour narratives, not an NLP proof."""
    for sentence in re.split(r'[.!?;]',value):
        # "Ryzyko dla inwestorów" identifies who bears risk, not their behaviour.
        story_sentence=(re.sub(r'\bdla\s+inwestorów\b','',sentence,flags=re.I)
                        if re.search(r'ryzyk',sentence,re.I) else sentence)
        narrative=re.search(r'sentyment|realizacj\w*\s+zysk|panik|eufori|inwestor(?:zy|ów)|napływ\w*\s+kapita|odpływ\w*\s+kapita|reakcj\w*\s+rynku',story_sentence,re.I)
        causal=re.search(r'(?:wzrost\w*|wzrosł\w*|wzrósł\w*|wzrast\w*|spad\w*|ruch\w*|zmian\w*\s+ceny).{0,35}(?:wynika|wynik|spowodowan|wywoła|reakcj|efekt|dzięki)|(?:spowodował|wywołał).{0,25}(?:ruch|wzrost|spad)',sentence,re.I)
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
        limit=600 if manifest.get('purpose')=='FINAL_COMPANY_REVIEW' else 150
        if not isinstance(text,str) or not text.strip() or len(text)>limit:
            errors.append(key+': wymagany tekst do '+str(limit)+' znaków');continue
        text=text.strip()
        if manifest.get('purpose')=='FINAL_COMPANY_REVIEW':
            sentences=[s.strip() for s in re.split(r'[.!?]+(?:\s|$)',text) if s.strip()]
            modern=manifest.get('assessment_contract')=='SENTENCES_V1'
            if modern:
                words=re.findall(r'[^\W\d_]+',text.casefold())
                repeated=any(words[i:i+1]*4==words[i:i+4] for i in range(len(words)-3))
                phrases=[' '.join(words[i:i+4]) for i in range(len(words)-3)]
                if repeated or any(phrases.count(phrase)>=3 for phrase in set(phrases)):
                    errors.append(key+': zapętlony lub powtarzany tekst zamiast uzasadnienia');continue
                if not 2<=len(sentences)<=4 or not re.search(r'[.!?]$',text):
                    errors.append(key+': wymagane od dwóch do czterech pełnych zdań');continue
                if len(set(s.casefold() for s in sentences))!=len(sentences):
                    errors.append(key+': powtórzone zdanie zamiast osobnego uzasadnienia');continue
            elif len(text)<100 or len(sentences)<2:
                errors.append(key+': końcowa ocena wymaga pełniejszego uzasadnienia w co najmniej dwóch zdaniach');continue
        if re.search(r'\d',text):errors.append(key+': niedozwolone cyfry w opisie; liczby pozostają w danych raportu')
        if re.search(r'\b(?:buy|sell|kup|kupuj|sprzedaj|sprzedawaj)\b',text,re.I):errors.append(key+': niedozwolone polecenie transakcyjne')
        if re.search(r'gwarant|bezpieczn|potwierdz\w*.{0,45}kontynuacj',text,re.I):errors.append(key+': nieuprawniona pewność')
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
    partial_caveat=bool(re.search(r'częściow|niepełn|skrócon|krótsz|pół\s*godzin|trzydziestominut|nieporównywal|za wcześnie|nie rozstrzyg|brak.{0,25}danych|nie.{0,25}ocen',activity,re.I))
    if shortened_activity_ready(snapshot) and not re.search(r'skrócon|krótsz|pół\s*godzin|trzydziestominut',activity,re.I):
        errors.append('activity: pominięto skrócony przedział końca sesji')
    if manifest.get('purpose')=='FINAL_COMPANY_REVIEW' and (manifest.get('session_context') or {}).get('status')=='COMPLETE_TO_ASOF' and not re.search(r'sesj|otwar|przebieg.{0,15}dnia',movement,re.I):
        errors.append('movement: końcowa ocena pomija przebieg bieżącej sesji')
    if (manifest.get('activity') or {}).get('status')=='PARTIAL' and not partial_caveat:errors.append('activity: niepełne dane wymagają jawnego ograniczenia oceny')
    if snapshot.get('candle_status')=='OPEN' and re.search(r'nisk|słab|poniżej',activity,re.I) and not partial_caveat:errors.append('activity: pominięto częściowy wolumen godziny')
    plan=manifest.get('trade_plan') or {}
    if plan.get('status')=='INDICATIVE' and plan.get('rr1',1)<1 and not re.search(r'potencjał|zysk|relacj',risk,re.I):errors.append('risk: pominięto słabą relację potencjału do ryzyka')
    return (empty if errors else clean),errors
