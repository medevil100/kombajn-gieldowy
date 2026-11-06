"""Named combinations of three evidence families, with no ranking-point bonus."""
import hashlib
import json


def compose(snapshot, events, config):
    setups = []
    if not isinstance(snapshot.get('ticker'), str) or not snapshot['ticker'] or snapshot.get('interval') not in ('1h', '1d'):
        return setups
    # SMA/MACD/RSI are one momentum family; price patterns cannot supply two votes.
    for direction in ('UP', 'DOWN'):
        price = [e for e in events if e['direction'] == direction and e['code'] in
                 ('RESISTANCE_BREAKOUT', 'SUPPORT_BREAKDOWN', 'STRUCTURE_UP', 'STRUCTURE_DOWN')]
        momentum = [e for e in events if e['direction'] == direction and e['code'].startswith(
                    ('SMA_CROSS_', 'MACD_CROSS_', 'RSI_DIVERGENCE_'))]
        flow = [e for e in events if e['code'] == 'VOLUME_SURGE' or
                e['direction'] == direction and e['code'].startswith('OBV_DIVERGENCE_')]
        if not price or not momentum or not flow:
            continue
        chosen = [price[0], momentum[0], flow[0]]
        if len({e['candle_time'] for e in chosen}) != 1:
            continue
        opposite = [e for e in events if e['direction'] in ('UP', 'DOWN') and e['direction'] != direction]
        code = 'SETUP_' + ('BREAKOUT_' if price[0]['code'] in ('RESISTANCE_BREAKOUT', 'SUPPORT_BREAKDOWN') else 'STRUCTURE_') + direction
        identity = {k: snapshot.get(k) for k in ('ticker', 'interval')}
        identity.update(candle_time=chosen[0]['candle_time'], code=code, config_id=config.identifier)
        identifier = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        warning = bool(opposite)
        label = ('Układ wzrostowy' if direction == 'UP' else 'Układ spadkowy') + (' · sprzeczne przesłanki' if warning else ' · cena, momentum i aktywność')
        setups.append({'id': identifier, 'code': code, 'label': label, 'direction': direction,
                       'role': 'WARNING' if warning else 'CONFIRMING', 'kind': 'COMPOSITE',
                       'components': [e['code'] for e in chosen], 'families': ['PRICE', 'MOMENTUM', 'ACTIVITY'],
                       'conflicts': [e['code'] for e in opposite], 'score_effect': 0,
                       'candle_time': chosen[0]['candle_time'],
                       'evidence': 'Połączono: ' + '; '.join(e['label'] for e in chosen) +
                       '. Są to grupy przesłanek z tego samego OHLCV, nie niezależne prawdopodobieństwa. '
                       'Układ nie dodaje punktów ani nie potwierdza wykonalności transakcji.'})
        if len(setups) >= config.max_setups:
            break
    return setups
