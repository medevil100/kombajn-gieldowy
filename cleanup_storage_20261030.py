"""Remove only the identified failed copy and superseded pre-deployment DB.

Default is read-only. --apply requires two specific completed backups to pass
quick_check first. Live DB, current backups, keys and code are never removed.
"""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess


RETAIN = ('ki2-20261029T033003871502Z.sqlite3', 'ki2-20261030T033003932846Z.sqlite3')
REMOVE = (
    'backups/ki2-20261028T210011227927Z.partial',
    'backups/ki2-20261028T210011227927Z.partial-journal',
    'backup-before-a792e31-20261029T120310Z/KI.matrix.sqlite3',
)


def cleanup(root, apply=False, progress=print):
    root = Path(root).expanduser().resolve(strict=True)
    candidates = []
    for relative in REMOVE:
        path = root / relative
        expected_parent = root / Path(relative).parent
        if path.is_symlink() or path.resolve().parent != expected_parent:
            raise ValueError('Niedozwolony cel lub dowiązanie: ' + str(path))
        if path.exists():
            if not path.is_file():
                raise ValueError('Cel nie jest zwykłym plikiem: ' + str(path))
            candidates.append(path)
    total = sum(p.stat().st_size for p in candidates)
    for path in candidates:
        progress('Do usunięcia: ' + str(path), flush=True)
    progress(f'Łącznie: {total / 1024**3:.2f} GiB', flush=True)
    if not apply:
        progress('Tylko odczyt. Żaden plik nie został usunięty.', flush=True)
        return 0
    for name in RETAIN:
        path = root / 'backups' / name
        if path.is_symlink() or path.resolve().parent != root / 'backups' or not path.is_file():
            raise ValueError('Brak wymaganej bezpiecznej kopii: ' + name)
        progress('Sprawdzanie zachowywanej kopii: ' + name, flush=True)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise ValueError('Uszkodzona kopia; niczego nie usunięto.')
            if not db.execute('SELECT 1 FROM observations LIMIT 1').fetchone():
                raise ValueError('Kopia nie zawiera obserwacji; niczego nie usunięto.')
    # This list contains only explicitly identified stale files; no glob or recursion.
    for path in candidates:
        if path.is_symlink() or path.resolve().parent != root / path.relative_to(root).parent:
            raise ValueError('Cel zmienił się podczas kontroli; przerwano.')
        path.unlink()
        progress('Usunięto: ' + str(path), flush=True)
    progress(f'Odzyskano około {total / 1024**3:.2f} GiB. Dwie poprawne kopie zachowane.', flush=True)
    return total


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        state = subprocess.run(['systemctl', 'is-active', 'ki2-backup.service'],
                               capture_output=True, text=True, check=False).stdout.strip()
        if state not in ('inactive', 'failed'):
            raise SystemExit('Kopia działa lub nie ustalono jej stanu. Przerwano sprzątanie.')
    cleanup(Path.home() / 'ki2', args.apply)
