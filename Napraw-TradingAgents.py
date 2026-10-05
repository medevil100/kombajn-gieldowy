"""Jawna, kontrolowana poprawka TradingAgents 0.6.0: agent wiadomości tylko Yahoo."""
import hashlib
from importlib import metadata
from pathlib import Path

ORIGINAL_SHA256 = 'fbc22552cd6ae0306ef66a891fb7f7ca5de4f528f12402ebab3c68d2c8c58cba'
PATCHED_SHA256 = '2dc14d54f26b5627e66e6abe8f288fc756189ca93a71cde3b0ef82aec477d554'


def patched_source(source):
    for name in ('get_macro_indicators', 'get_prediction_markets'):
        source = source.replace('    '+name+',\n', '')
    start = source.index(', get_macro_indicators(indicator, curr_date, look_back_days)')
    end = source.index(' Provide specific, actionable insights', start)
    source = source[:start] + '. Do not call macroeconomic or prediction-market tools; they are unavailable in this Yahoo-only integration.' + source[end:]
    return source


def main():
    dist = metadata.distribution('tradingagents')
    if dist.version != '0.6.0':
        raise ValueError('Wymagana wersja TradingAgents 0.6.0. Niczego nie zmieniono.')
    target = Path(dist.locate_file('tradingagents/agents/analysts/news_analyst.py'))
    original = target.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest == PATCHED_SHA256:
        print('Poprawka Yahoo jest już zainstalowana.')
    elif digest == ORIGINAL_SHA256:
        changed = patched_source(original.decode('utf-8')).encode('utf-8')
        if hashlib.sha256(changed).hexdigest() != PATCHED_SHA256:
            raise ValueError('Niepoprawny wynik poprawki. Niczego nie zmieniono.')
        compile(changed, str(target), 'exec')
        backup = target.with_name('news_analyst.py.ki-original')
        if not backup.exists():
            backup.write_bytes(original)
        temporary = target.with_name('news_analyst.py.ki-new')
        temporary.write_bytes(changed)
        temporary.replace(target)
        print('Usunięto narzędzia makro i rynków prognostycznych oraz ich instrukcje.')
    else:
        raise ValueError('Nieznana zawartość agenta wiadomości. Niczego nie zmieniono.')
    from tradingagents.agents.analysts.news_analyst import TOOLS
    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
    expected = {'get_news', 'get_global_news'}
    assert {tool.name for tool in TOOLS} == expected
    assert {tool.name for tool in ANALYST_NODE_SPECS['news'].tools} == expected
    print('Zweryfikowano rzeczywiste narzędzia modelu i węzła grafu. Bez wywołań API.')


if __name__ == '__main__':
    main()
