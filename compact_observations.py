"""Offline, lossless rewrite into a NEW database; never modifies the source.

Stop KI before --apply. Deploy the matching reader before using the resulting DB.
No paid providers, settings changes, history deletion, or automatic file replacement.
"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
from observation_storage import encode_observation, loads


def compact(source, destination, apply=False, progress=print):
    source = Path(source).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser().resolve()
    if source == destination or destination.exists():
        raise ValueError('Cel musi być nowym plikiem, innym niż baza źródłowa.')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        count = src.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        progress(f'Obserwacje: {count}; źródło: {source.stat().st_size} bajtów', flush=True)
        if not apply:
            progress('Tylko odczyt; --apply tworzy osobną, skompresowaną bazę.', flush=True)
            return
        if shutil.disk_usage(destination.parent).free < source.stat().st_size * 2 + 1024**3:
            raise ValueError('Za mało miejsca na bezpieczne utworzenie i weryfikację osobnej bazy.')
        # Reject accidentally running against a live production scanner on Linux.
        if os.name != 'nt':
            import fcntl
            with open(str(source) + '.scanner.lock', 'a+b') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Skaner działa. Najpierw zatrzymaj usługę KI.') from None
                return _copy_and_compact(src, destination, count, progress)
        raise ValueError('Operacja --apply jest przeznaczona dla zatrzymanego KI na VPS Linux.')


def _copy_and_compact(source, destination, expected_count, progress):
    # Exclusive creation prevents overwriting an unrelated file, even after a race.
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(destination)) as target:
        source.backup(target, pages=2048)
        target.execute('PRAGMA journal_mode=DELETE')
        target.execute('PRAGMA synchronous=FULL')
        target.execute('PRAGMA cache_size=-8192')
        target.execute('PRAGMA foreign_keys=ON')
        cursor = 0
        processed = changed = 0
        while True:
            batch = target.execute('SELECT id,payload FROM observations WHERE id>? ORDER BY id LIMIT 100',
                                   (cursor,)).fetchall()
            if not batch:
                break
            with target:
                for row_id, raw in batch:
                    snapshot = loads(raw)
                    encoded = encode_observation(snapshot)
                    if loads(encoded) != snapshot:
                        raise ValueError(f'Niezgodność danych obserwacji {row_id}; źródło pozostaje bez zmian.')
                    if encoded != raw and len(encoded.encode('utf-8')) < len(raw.encode('utf-8')):
                        target.execute('UPDATE observations SET payload=? WHERE id=?', (encoded, row_id))
                        changed += 1
                    cursor = row_id
                    processed += 1
            if processed % 1000 == 0:
                progress(f'Przetworzono {processed}/{expected_count}; zmniejszono {changed}', flush=True)
        if target.execute('SELECT COUNT(*) FROM observations').fetchone()[0] != expected_count:
            raise ValueError('Niezgodna liczba obserwacji.')
        progress('Zmniejszanie osobnej bazy i kontrola integralności…', flush=True)
        target.execute('VACUUM')
        if target.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('Kontrola integralności nie powiodła się.')
        if target.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Kontrola powiązań nie powiodła się.')
        # Every non-observation table, including messages and paid-call identities,
        # must be byte-for-byte unchanged in both directions.
        target.execute('ATTACH DATABASE ? AS original', (source.execute('PRAGMA database_list').fetchone()[2],))
        tables = [r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'observations'")]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            for left, right in (('main', 'original'), ('original', 'main')):
                if target.execute(f'SELECT * FROM {left}.{quoted} EXCEPT SELECT * FROM {right}.{quoted} LIMIT 1').fetchone():
                    raise ValueError(f'Zmieniono niepowiązaną tabelę {table}.')
    progress(f'Gotowe: {destination}; {destination.stat().st_size} bajtów. Źródło bez zmian.', flush=True)
    return changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    compact(args.source, args.destination, args.apply)
