"""Deterministic review of market evidence. No network, orders or model calls."""
import math
import re
from datetime import datetime

VERSION = 1
LABELS = {
    'ALIGNED': 'Wskazania zgodne z ruchem',
    'MIXED': 'Ruch potwierdzony, wskazania mieszane',
    'CONTRADICTED': 'Bieżące wskazania przeczą ruchowi',
    'RISK_DOMINANT': 'Ryzyko przeważa w ocenie sygnału',
    'INSUFFICIENT': 'Za mało spójnych danych do oceny',
}


def number(value, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (not positive or value > 0))


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def quote_status(snapshot):
    q = snapshot.get('spread') or {}
    bid, ask = number(q.get('bid'), True), number(q.get('ask'), True)
    if bid and ask: return 'INVERTED' if q['bid'] > q['ask'] else 'VALID'
    return 'INCOMPLETE' if bid or ask else 'MISSING'


def activity_summary(snapshot, previous=None):
    """Describe measured volume, never extrapolate an unfinished hourly candle."""
    def ratio(value): return format(value, '.2f').replace('.', ',') + '×'
    def count(value): return format(value, ',.0f').replace(',', ' ')
    rv = snapshot.get('rvol')
    valid_rv = number(rv) and rv >= 0
    closed = snapshot.get('candle_status') == 'CLOSED'
    start, acquired = timestamp(snapshot.get('candle_time')), timestamp(snapshot.get('acquired_at'))
    full = snapshot.get('previous_closed') or {}
    full_start, full_end = timestamp(full.get('time')), timestamp(full.get('end'))
    previous_hour = (not closed and start and full_start and full_end == start
                     and (full_end - full_start).total_seconds() == 3600
                     and full.get('status') == 'CLOSED' and number(full.get('rvol')) and full['rvol'] >= 0)
    if closed and valid_rv:
        text = 'wolumen zakończonej świecy ' + ('powyżej' if rv > 1 else 'równy' if rv == 1 else 'poniżej') + ' średniej (' + ratio(rv) + ').'
    elif valid_rv:
        text = ('ostatnia zamknięta 1h: ' + ratio(full['rvol']) + ' średniej; bieżąca dotąd: ' + ratio(rv)
                if previous_hour else 'wolumen dotąd: ' + ratio(rv) + ' średniej pełnej godziny')
        if start and acquired and 0 <= (acquired - start).total_seconds() < 3600:
            seconds = (acquired - start).total_seconds()
            text += ' po ' + (str(int(seconds // 60)) + ' min' if seconds >= 60 else str(int(seconds)) + ' s')
        text += '.'
    else:
        text = 'brak poprawnego pomiaru RVOL.'
    previous = previous or {}
    old_at = timestamp(previous.get('acquired_at'))
    old_start = timestamp(previous.get('candle_time'))
    old_volume, volume = previous.get('volume'), snapshot.get('volume')
    if (start and old_start == start and acquired and old_at and 0 < (acquired - old_at).total_seconds() <= 3600
        and previous.get('ticker') == snapshot.get('ticker') and previous.get('interval') == snapshot.get('interval') == '1h'
        and number(old_volume) and number(volume) and 0 <= old_volume <= volume):
        seconds = (acquired - old_at).total_seconds()
        duration = (format(seconds / 60, '.1f').replace('.', ',').removesuffix(',0') + ' min'
                    if seconds >= 60 else str(int(seconds)) + ' s')
        text += ' Od poprzedniego odczytu +' + count(volume - old_volume) + ' szt. w ' + duration + '.'
    return text


def material_issues(snapshot):
    """Minimum coherent material before either research or AI; quotes optional."""
    issues = []
    price = snapshot.get('price')
    ohlc = snapshot.get('ohlc') or {}
    if not snapshot.get('ticker') or snapshot.get('interval') != '1h':
        issues.append('Brak tożsamości lub interwału jednej godziny.')
    if not number(price, True) or not all(number(ohlc.get(k), True) for k in ('open', 'high', 'low', 'close')):
        issues.append('Niepełna cena lub OHLC.')
    elif not (ohlc['low'] <= min(ohlc['open'], ohlc['close'], price)
              <= max(ohlc['open'], ohlc['close'], price) <= ohlc['high']):
        issues.append('Cena i zakres OHLC są niespójne.')
    acquired, start, end = (timestamp(snapshot.get(k)) for k in ('acquired_at', 'candle_time', 'candle_end'))
    status = snapshot.get('candle_status')
    if not all((acquired, start, end)) or not start < end or acquired < start:
        issues.append('Niepełne lub sprzeczne czasy świecy i odczytu.')
    elif status not in ('OPEN', 'CLOSED') or (status == 'OPEN' and acquired >= end) or (status == 'CLOSED' and acquired < end):
        issues.append('Status świecy jest sprzeczny z czasem odczytu.')
    if not all(number(snapshot.get(k), True) for k in ('volume', 'average_volume', 'rvol')):
        issues.append('Brak pełnego pomiaru wolumenu, jego średniej lub RVOL.')
    matrix = snapshot.get('price_matrix') or {}
    change, anchor = matrix.get('change_pct'), matrix.get('anchor_price')
    if not number(change) or not change or not number(anchor, True):
        issues.append('Brak zmierzonego ruchu względem poprawnej bazy.')
    elif number(price, True) and abs((price / anchor - 1) * 100 - change) > .02:
        issues.append('Zmiana procentowa nie odpowiada cenie i bazie.')
    indicators = snapshot.get('indicators') or {}
    for key in ('rsi', 'stoch_k', 'stoch_d', 'adx', 'plus_di', 'minus_di'):
        if number(indicators.get(key)) and not 0 <= indicators[key] <= 100:
            issues.append('Wskaźnik poza dopuszczalnym zakresem: ' + key + '.')
    groups = set()
    if number(price, True) and number(indicators.get('ma_fast'), True): groups.add('price')
    if number(indicators.get('last_macd_hist')) or number(indicators.get('rsi')): groups.add('momentum')
    if all(number(indicators.get(k)) for k in ('plus_di', 'minus_di')): groups.add('direction')
    if len(groups) < 2:
        issues.append('Za mało niezależnych obszarów technicznych do interpretacji.')
    return issues


def review(snapshot, manifest):
    """Independent technical verdict and execution limitations, never a buy score."""
    issues = material_issues(snapshot)
    comparisons = (manifest.get('technical') or {}).get('comparisons') or []
    supports = [x for x in comparisons if x['status'] == 'SUPPORTS']
    against = [x for x in comparisons if x['status'] == 'CONTRADICTS']
    evidence = {}
    for code, items in (('TECH_SUPPORT', supports), ('TECH_AGAINST', against)):
        if items:
            evidence[code] = {'text': '; '.join(x['name'] for x in items),
                              'metrics': list(dict.fromkeys(k for x in items for k in x['metrics']))}
    verdict = 'MIXED' if supports and against else 'ALIGNED' if supports else 'CONTRADICTED' if against else 'INSUFFICIENT'
    if verdict == 'MIXED':
        evidence['TECH_MIXED'] = {'text': 'Część wskazań wspiera ruch, część mu przeczy.', 'metrics': []}
    q = snapshot.get('spread') or {}
    quotes = all(number(q.get(k), True) for k in ('bid', 'ask')) and q['ask'] >= q['bid']
    spread = (q['ask'] - q['bid']) / ((q['ask'] + q['bid']) / 2) * 100 if quotes else None
    quote_at, acquired = timestamp(q.get('quote_time') or q.get('updated_at') or q.get('timestamp')), timestamp(snapshot.get('acquired_at'))
    fresh = bool(quotes and q.get('freshness_confirmed') is True and quote_at and acquired
                 and 0 <= (acquired - quote_at).total_seconds() <= 60)
    execution = 'TIMESTAMP_CONFIRMED' if fresh else 'UNVERIFIED' if quotes else 'MISSING'
    status = quote_status(snapshot)
    limitations = ([] if fresh else ['Czas aktualizacji bid/ask niepotwierdzony.' if quotes else
                   'Niespójne bid/ask: bid przewyższa ask; spread nieoceniony.' if status == 'INVERTED' else
                   'Niepełne bid/ask; spread nieoceniony.' if status == 'INCOMPLETE' else
                   'Brak bid/ask; warunki wykonania nieocenione.'])
    dominant = []
    if quotes and spread >= 2 - 1e-10:
        evidence['WIDE_SPREAD'] = {'text': 'Szeroki spread zwiększa ryzyko wykonania' + ('.' if fresh else '; świeżość ofert niepotwierdzona.'), 'metrics': []}
        # Unverified quotes are a warning, not proof of the live execution cost.
        if fresh: dominant.append('WIDE_SPREAD')
    matrix = snapshot.get('price_matrix') or {}
    change = matrix.get('change_pct')
    ohlc = snapshot.get('ohlc') or {}
    price = snapshot.get('price')
    adverse = None
    if number(price, True) and number(change):
        if change > 0 and number(ohlc.get('high'), True): adverse = (ohlc['high'] - price) / ohlc['high'] * 100
        elif change < 0 and number(ohlc.get('low'), True): adverse = (price / ohlc['low'] - 1) * 100
    if number(adverse) and adverse >= 2 - 1e-10:
        evidence['ADVERSE_RETRACE'] = {'text': 'Cofnięcie od maksimum osłabia wzrost.' if change > 0 else 'Odbicie od minimum osłabia spadek.', 'metrics': []}
        dominant.append('ADVERSE_RETRACE')
    plan = manifest.get('trade_plan') or {}
    if plan.get('status') == 'INDICATIVE' and number(plan.get('rr1')) and plan['rr1'] < 1:
        evidence['POOR_RR'] = {'text': 'Potencjał do pierwszego celu jest mniejszy niż odległość do SL.', 'metrics': []}
        dominant.append('POOR_RR')
    if snapshot.get('candle_status') == 'OPEN':
        limitations.append('Świeca trwa; wolumen całej godziny pozostaje nieznany.')
        activity = 'PARTIAL_ABOVE' if number(snapshot.get('rvol')) and snapshot['rvol'] >= 1 else 'PARTIAL'
    else:
        activity = 'ABOVE' if number(snapshot.get('rvol')) and snapshot['rvol'] >= 1 else 'BELOW'
    if dominant: verdict = 'RISK_DOMINANT'
    if issues or not supports and not against: verdict = 'INSUFFICIENT'
    required = (dominant if verdict == 'RISK_DOMINANT' else
                ['TECH_MIXED'] if verdict == 'MIXED' else
                ['TECH_SUPPORT'] if verdict == 'ALIGNED' else
                ['TECH_AGAINST'] if verdict == 'CONTRADICTED' else [])
    coverage = 'PARTIAL' if issues or limitations or (manifest.get('technical') or {}).get('status') == 'PARTIAL' else 'FULL'
    return {'version': VERSION, 'verdict': verdict, 'label': LABELS[verdict], 'coverage': coverage,
            'execution': execution, 'quote_status': status, 'activity': activity, 'spread_pct': spread,
            'adverse_retrace_pct': adverse, 'evidence': evidence, 'required_reason_codes': required,
            'material_issues': issues, 'limitations': limitations,
            'summary': LABELS[verdict] + ('. ' + evidence[required[0]]['text'] if required else '. ' + issues[0] if issues else '.')}


def decision_errors(decision, local, technical, assessment, snapshot):
    """Check typed evidence references and selected contradictions; not an NLP proof."""
    errors = []
    if not isinstance(decision, dict) or set(decision) != {'verdict', 'reason_codes'}:
        return ['Brak decyzji z odwołaniami do dowodów.']
    reasons = decision.get('reason_codes')
    if decision.get('verdict') != local['verdict'] or local['verdict'] == 'INSUFFICIENT':
        errors.append('Werdykt jest sprzeczny z oceną materiału.')
    if (not isinstance(reasons, list) or not 1 <= len(reasons) <= 3
        or any(not isinstance(x, str) or x not in local['evidence'] for x in reasons)
        or len(reasons) != len(set(reasons))):
        errors.append('Niepoprawne odwołania do dowodów.')
        return errors
    elif not set(reasons).intersection(local['required_reason_codes']):
        errors.append('Pominięto decydującą przesłankę oceny.')
    metrics = {x['metric'] for x in technical}
    for item in technical:
        text = item['interpretation']
        if item['metric'] == 'last_macd_hist':
            value = (snapshot.get('indicators') or {}).get('last_macd_hist')
            if number(value):
                if (value > 0 and re.search(r'ujemn\w*\s+histogram|histogram.{0,15}(?:jest|pozostaje)\s+ujemn', text, re.I)
                    or value < 0 and re.search(r'dodatni\w*\s+histogram|histogram.{0,15}(?:jest|pozostaje)\s+dodatni', text, re.I)):
                    errors.append('Interpretacja histogramu przeczy wartości wskaźnika.')
    for code in ('TECH_SUPPORT', 'TECH_AGAINST'):
        if code in local['evidence'] and (code in (reasons or []) or local['verdict'] == 'MIXED'):
            if not metrics.intersection(local['evidence'][code]['metrics']):
                errors.append('Wniosek wymaga interpretacji wskaźnika: ' + code + '.')
    if isinstance(assessment, dict):
        activity, risk = str(assessment.get('activity', '')), str(assessment.get('risk', ''))
        if local['activity'] == 'BELOW' and re.search(r'powyżej|podwyższon|wysok\w*\s+(?:aktywno|wolumen)', activity, re.I):
            errors.append('Wniosek o aktywności przeczy zakończonej świecy.')
        if local['activity'] in ('ABOVE', 'PARTIAL_ABOVE') and re.search(r'poniżej|nisk\w*\s+aktywno|słab\w*\s+aktywno', activity, re.I):
            errors.append('Wniosek o aktywności przeczy zmierzonemu wolumenowi.')
        if local['verdict'] == 'RISK_DOMINANT':
            patterns = {'WIDE_SPREAD': r'spread', 'ADVERSE_RETRACE': r'cofnię|odbici', 'POOR_RR': r'potencjał|relacj|zysk'}
            if not any(re.search(patterns[x], risk, re.I) for x in local['required_reason_codes']):
                errors.append('Wniosek pomija dominujące ryzyko.')
        if local['spread_pct'] is not None and local['spread_pct'] >= 2 and re.search(r'nisk\w*\s+ryzyk|wąsk\w*\s+spread|dobr\w*\s+płynno', risk, re.I):
            errors.append('Wniosek pomija szeroki spread.')
    return errors


def narrative_errors(result, snapshot, manifest):
    """Selected factual contradictions in prose, independently of copied enums."""
    errors = []
    assessment = result.get('assessment') or {}
    texts = list(assessment.values()) if isinstance(assessment, dict) else [assessment]
    texts += [x.get('interpretation', '') for x in result.get('technical', [])]
    texts += [x for key in ('hypotheses', 'risks', 'missing') for x in result.get(key, [])]
    plan = manifest.get('trade_plan') or {}
    rr = plan.get('rr1')
    measured_rr = plan.get('status') == 'INDICATIVE' and number(rr) and rr >= 0
    poor = r'\b(?:słab\w*|niekorzystn\w*|nisk\w*)\s+(?:relacj\w*|stosun\w*)|(?:relacj\w*|stosun\w*).{0,65}(?:jest|pozostaje)\s+(?:słab\w*|niekorzystn\w*|nisk\w*)'
    good = r'\b(?:korzystn\w*|dobr\w*|wysok\w*)\s+(?:relacj\w*|stosun\w*)|(?:relacj\w*|stosun\w*).{0,65}(?:jest|pozostaje)\s+(?:korzystn\w*|dobr\w*|wysok\w*)'
    rr_subject = r'zysk|potencjał|ryzyk|\bR\s*[/:-]\s*R\b'
    missing_quotes = r'brak\w*\s+(?:(?:poprawnych|potwierdzonych|wiarygodnych|aktualnych)\s+)?(?:danych\s+)?(?:bid\s*[/\-]\s*ask|ofert\b)'
    for text in texts:
        if not isinstance(text, str): continue
        for sentence in re.split(r'[.!?;]', text):
            for pattern, is_poor in ((poor, True), (good, False)):
                match = re.search(pattern, sentence, re.I)
                if not match or not re.search(rr_subject, sentence, re.I): continue
                prefix = sentence[max(0, match.start() - 40):match.start()]
                if re.search(r'nie potwierdzono\s*$|brak dowodów na\s*$', prefix, re.I): continue
                if not measured_rr or (is_poor and rr >= 1) or (not is_poor and rr < 1):
                    errors.append('Ocena relacji potencjału do ryzyka bez potwierdzenia w wyliczonym planie.')
            status = quote_status(snapshot)
            if re.search(missing_quotes, sentence, re.I):
                if status == 'VALID':
                    errors.append('Oferty są dostępne: niepotwierdzona świeżość nie oznacza braku bid/ask.')
                elif status == 'INVERTED' and not re.search(r'niespójn|odwrócon|powyżej|przewyższa', sentence, re.I):
                    errors.append('Niespójne bid/ask należy odróżnić od braku ofert.')
    return list(dict.fromkeys(errors))
