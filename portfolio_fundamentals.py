"""Fundamenty portfela USA z Alpha Vantage."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FUNCTIONS = ('INCOME_STATEMENT', 'BALANCE_SHEET', 'CASH_FLOW')
PREFIX = 'fundamentals_alpha:'
BUDGET = PREFIX + 'budget'
ANALYST = 'portfolio_analyst:'
ANALYST_PAUSE = ANALYST + 'pause'
DAY = timedelta(days=1)
REFRESH = timedelta(days=7)
LIMIT = 12
SOURCE = 'https://www.alphavantage.co/query'
STATUSES = {
    'waiting': 'Oczekuje na pobranie sprawozdań.',
    'key': 'Wymaga skonfigurowania klucza Alpha Vantage.',
    'market': 'Brak zweryfikowanego źródła sprawozdań dla tego rynku.',
    'provider': 'Alpha Vantage odmówiło dostępu lub nie odpowiedziało. Odczyt odłożony.',
    'incomplete': 'Sprawozdania nie przeszły kontroli okresów, waluty lub wartości.',
    'budget': 'Odczyt w kolejce do zwolnienia limitu zapytań.',
}


class ProviderUnavailable(RuntimeError):
    pass


def key_path():
    return Path.home() / '.config' / 'ki2' / 'alpha-vantage.key'


def valid_key(key):
    return key.lower() != 'demo' and re.fullmatch(r'[A-Za-z0-9_-]{8,100}', key) is not None


def read_key():
    path = key_path()
    try:
        if path.is_symlink() or (os.name == 'posix' and path.stat().st_mode & 0o077):
            return ''
        with path.open(encoding='ascii') as file:
            key = file.read(1024).strip()
    except (OSError, UnicodeError):
        return ''
    return key if valid_key(key) else ''


def save_key():
    if sys.stdin.isatty():
        raise SystemExit('Przekaż klucz przez potok SSH.')
    key = sys.stdin.readline(1024).strip()
    if not valid_key(key):
        raise SystemExit('Oczekiwano samego klucza Alpha Vantage.')
    target = key_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', dir=target.parent,
                                     delete=False) as file:
        temp = Path(file.name)
        try:
            file.write(key + '\n')
            file.flush()
            os.fsync(file.fileno())
            file.close()
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    print('Zapisano klucz Alpha Vantage dla KI.')


def supported(ticker):
    return isinstance(ticker, str) and re.fullmatch(r'[A-Z][A-Z0-9-]{0,14}(?:\.[AB])?', ticker) is not None


def amount(value):
    if isinstance(value, bool):
        raise ValueError('Niepoprawna kwota.')
    number = float(value)
    if not math.isfinite(number) or abs(number) > 1e16:
        raise ValueError('Niepoprawna kwota.')
    return number


def summarize(ticker, documents, today):
    quarters = []
    dates = None
    for function in FUNCTIONS:
        body = documents[function]
        if body.get('symbol') != ticker:
            raise ValueError('Niezgodny symbol.')
        rows = body['quarterlyReports'][:4]
        periods = [date.fromisoformat(row['fiscalDateEnding']) for row in rows]
        if (len(rows) != 4 or periods[0] > today
                or any(not 70 <= (a-b).days <= 110 for a, b in zip(periods, periods[1:]))
                or any(row.get('reportedCurrency') != 'USD' for row in rows)
                or (dates is not None and periods != dates)):
            raise ValueError('Niezgodne okresy lub waluty.')
        dates = periods
        quarters.append(rows)
    income, balances, flows = quarters
    for balance in balances:
        assets = amount(balance['totalAssets'])
        liabilities = amount(balance['totalLiabilities'])
        equity = amount(balance['totalShareholderEquity'])
        if assets < 0 or liabilities < 0 or abs(assets-liabilities-equity) > 1:
            raise ValueError('Niezgodny bilans.')
    cash = amount(balances[0]['cashAndCashEquivalentsAtCarryingValue'])
    if cash < 0:
        raise ValueError('Niepoprawne saldo gotówki.')
    return {
        'period_end': dates[0].isoformat(),
        'net_income': amount(income[0]['netIncome']),
        'cash': cash,
        'equity': amount(balances[0]['totalShareholderEquity']),
        'operating_cashflow': sum(amount(row['operatingCashflow']) for row in flows),
    }


def fetch(ticker, function, key):
    query = urlencode({'function': function, 'symbol': ticker, 'apikey': key})
    request = Request(SOURCE + '?' + query, headers={'User-Agent': 'KI2-portfolio/1.0'})
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError('Przekroczony limit odpowiedzi.')
        body = json.loads(raw)
    except (OSError, URLError, ValueError):
        raise ProviderUnavailable from None
    if not isinstance(body, dict) or any(body.get(k) for k in ('Information', 'Note', 'Error Message')):
        raise ProviderUnavailable
    return body


def load(connection, key):
    row = connection.execute('SELECT payload FROM runtime WHERE key=?', (key,)).fetchone()
    if not row:
        return {}
    payload = json.loads(row[0])
    if not isinstance(payload, dict):
        raise ValueError('Niepoprawny zapis fundamentów.')
    return payload


def save(connection, key, payload, now):
    connection.execute(
        'INSERT INTO runtime(key,payload,updated_at) VALUES(?,?,?) ON CONFLICT(key) '
        'DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at',
        (key, json.dumps(payload, ensure_ascii=False, allow_nan=False), now.isoformat()),
    )


def due(record, now):
    next_check = record.get('next_check')
    return not next_check or datetime.fromisoformat(next_check) <= now


def process_one(store, tickers, key, stop, now=None):
    now = now or datetime.now(timezone.utc)
    with store.transaction() as connection:
        budget = load(connection, BUDGET)
        if not due(budget, now):
            return False
        spent = [datetime.fromisoformat(at) for at in budget.get('reserved', [])]
        # Komplet obejmuje trzy kolejne połączenia. Zachowaj margines ich trwania.
        spent = [at for at in spent if at > now - DAY - timedelta(minutes=2)]
        if len(spent) + len(FUNCTIONS) > LIMIT:
            return False
        for ticker in tickers:
            if not supported(ticker):
                continue
            record = load(connection, PREFIX + ticker)
            if due(record, now):
                break
        else:
            return False
        # Rezerwacja całego kompletu przed pierwszym zapytaniem, również przy przerwaniu procesu.
        budget = {'reserved': [at.isoformat() for at in spent] + [now.isoformat()] * len(FUNCTIONS)}
        save(connection, BUDGET, budget, now)
        record.update(status='waiting', next_check=(now + DAY).isoformat())
        save(connection, PREFIX + ticker, record, now)

    documents = {}
    try:
        for function in FUNCTIONS:
            if stop.is_set():
                return False
            documents[function] = fetch(ticker, function, key)
            if function != FUNCTIONS[-1] and stop.wait(1.2):
                return False
        summary = summarize(ticker, documents, now.date())
    except ProviderUnavailable:
        record['status'] = 'provider'
        budget['next_check'] = (now + DAY).isoformat()
    except (KeyError, TypeError, ValueError, AttributeError):
        record['status'] = 'incomplete'
    else:
        record.update(status='ready', summary=summary, fetched_at=now.isoformat(),
                      next_check=(now + REFRESH).isoformat())
    with store.transaction() as connection:
        save(connection, PREFIX + ticker, record, now)
        if record['status'] == 'provider':
            save(connection, BUDGET, budget, now)
    return True


def process_analyst(store, tickers, quote, now=None):
    now = now or datetime.now(timezone.utc)
    with store.transaction() as connection:
        if not due(load(connection, ANALYST_PAUSE), now):
            return False
        for ticker in tickers:
            if not (supported(ticker) or (isinstance(ticker, str) and ticker.endswith('.WA') and supported(ticker[:-3]))):
                continue
            record = load(connection, ANALYST + ticker)
            if due(record, now):
                break
        else:
            return False
        record['next_check'] = (now + DAY).isoformat()
        save(connection, ANALYST + ticker, record, now)
    try:
        info = quote(ticker)
        if info.get('symbol') != ticker or info.get('currency') not in ('PLN', 'USD'):
            raise ValueError('Niezgodna tożsamość lub waluta.')
        count = info.get('numberOfAnalystOpinions')
        target = info.get('targetMeanPrice')
        if (isinstance(count, int) and not isinstance(count, bool) and count > 0
                and isinstance(target, (int, float)) and not isinstance(target, bool)
                and math.isfinite(target) and target > 0):
            record['target'] = {'price': target, 'count': count, 'currency': info['currency'],
                                'acquired_at': now.isoformat()}
        else:
            record.pop('target', None)
        record.update(checked=True, next_check=(now + REFRESH).isoformat())
        record.pop('error', None)
    except Exception as error:
        with store.transaction() as connection:
            record['error'] = True
            save(connection, ANALYST + ticker, record, now)
            if type(error).__name__ in ('YFRateLimitError', 'MarketRateLimitError'):
                save(connection, ANALYST_PAUSE, {'next_check': (now + DAY).isoformat()}, now)
        return False
    with store.transaction() as connection:
        save(connection, ANALYST + ticker, record, now)
    return True


def worker(store, stop, portfolio_tickers, quote):
    from ki2_ops_guard import MaintenanceUnavailable, provider_lease

    if stop.wait(15):
        return
    while not stop.is_set():
        key = read_key()
        try:
            with provider_lease() as acquired:
                if acquired:
                    tickers = portfolio_tickers(store)
                    worked = key and process_one(store, tickers, key, stop)
                    if not worked and not stop.is_set():
                        process_analyst(store, tickers, quote)
        except (OSError, sqlite3.Error, MaintenanceUnavailable, ValueError, TypeError) as error:
            print('Fundamenty portfela: odczyt odłożony (' + type(error).__name__ + ').', flush=True)
        stop.wait(30)


def views(store, tickers):
    configured = key_path().is_file()
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)
    result = {}
    with store.connection() as connection:
        try:
            budget = load(connection, BUDGET)
            reserved = sum(datetime.fromisoformat(at) > now - DAY - timedelta(minutes=2)
                           for at in budget.get('reserved', []))
            pending = 'provider' if not due(budget, now) else 'budget' if reserved + len(FUNCTIONS) > LIMIT else 'waiting'
        except (TypeError, ValueError):
            pending = 'waiting'
        for ticker in tickers:
            if not supported(ticker):
                result[ticker] = {'notice': STATUSES['market']}
                continue
            try:
                record = load(connection, PREFIX + ticker)
                summary = record.get('summary')
                if summary:
                    period = date.fromisoformat(summary['period_end'])
                    summary = {k: amount(summary[k]) for k in ('net_income', 'cash', 'equity', 'operating_cashflow')}
                    summary['period_end'] = period.strftime('%d.%m.%Y')
                    summary['older'] = today - period > timedelta(days=180)
                status = record.get('status', pending)
                if not configured:
                    status = 'key'
                elif status == 'waiting' or (status == 'provider' and due(record, now)):
                    status = pending
                result[ticker] = {'summary': summary, 'notice': STATUSES.get(status, '')}
            except (KeyError, TypeError, ValueError, AttributeError):
                result[ticker] = {'notice': 'Zapis fundamentów wymaga ponownego odczytu.'}
    return result


def analyst_views(store, tickers):
    result = {}
    now = datetime.now(timezone.utc)
    with store.connection() as connection:
        for ticker in tickers:
            try:
                record = load(connection, ANALYST + ticker)
                target = record.get('target')
                if target and timedelta(0) <= now - datetime.fromisoformat(target['acquired_at']) <= REFRESH + DAY:
                    result[ticker] = target
                elif record.get('error'):
                    result[ticker] = {'unavailable': True}
                elif record.get('checked'):
                    result[ticker] = {}
            except (ValueError, KeyError, TypeError):
                continue
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Konfiguracja źródła fundamentów KI')
    parser.add_argument('--save-key', action='store_true', required=True)
    parser.parse_args()
    save_key()
