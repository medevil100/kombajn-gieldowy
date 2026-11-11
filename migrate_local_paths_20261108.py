"""Move active local configuration outside OneDrive; preserve the original DB.

Windows only. Default is a plan. --apply prepares and checks a new SQLite copy,
then activates a nonsecret local profile. It never starts KI or contacts a provider.
"""
import argparse
from contextlib import closing
import csv
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

import ki2_paths


def private_directory(target):
    system = Path(os.environ['SystemRoot']) / 'System32'
    raw = subprocess.check_output([str(system / 'whoami.exe'), '/user', '/fo', 'csv', '/nh'], text=True)
    sid = next(csv.reader(io.StringIO(raw)))[1]
    if not sid.startswith('S-1-'):
        raise ValueError('Nie potwierdzono użytkownika Windows.')
    subprocess.run([str(system / 'icacls.exe'), str(target), '/inheritance:r', '/grant:r',
                    '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def table_counts(db):
    names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {name: db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in names}


def copy_database(source, target):
    source = Path(source).resolve(strict=True)
    target = Path(target).resolve()
    if source == target or target.exists():
        raise ValueError('Kopia wymaga nowego pliku docelowego.')
    with target.open('xb'):
        pass
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=3)) as src:
        src.execute('PRAGMA query_only=ON')
        src.execute('BEGIN')
        counts = table_counts(src)
        with closing(sqlite3.connect(target)) as dst:
            dst.execute('PRAGMA cache_size=-8192')
            src.backup(dst, pages=4096, sleep=.01)
            dst.execute('PRAGMA journal_mode=DELETE')
            checks = [row[0] for row in dst.execute('PRAGMA quick_check')]
            if checks != ['ok'] or table_counts(dst) != counts:
                raise ValueError('Kopia bazy nie przeszła weryfikacji.')
    return counts


def migrate(project, target, apply=False):
    project = Path(project).resolve(strict=True)
    target = Path(target).resolve()
    if target == project or project in target.parents or target in project.parents:
        raise ValueError('Nowy katalog musi leżeć poza projektem.')
    profile = project / ki2_paths.PROFILE
    if profile.exists() or target.exists():
        raise ValueError('Profil lub katalog docelowy już istnieje; niczego nie nadpisano.')
    source = project / 'KI.matrix.sqlite3'
    if not source.is_file():
        raise ValueError('Nie znaleziono źródłowej bazy lokalnej.')
    plan = {'status': 'PLAN', 'project': str(project), 'target': str(target),
            'database_bytes': source.stat().st_size, 'original_database_preserved': True,
            'starts_scanner': False, 'changes_vps': False}
    if not apply:
        return plan
    if os.name != 'nt':
        raise ValueError('Migracja jest przeznaczona wyłącznie dla lokalnego Windows.')
    if any(os.environ.get(key) for key in ('KI2_DATA_DIR', 'KI2_SECRETS_FILE', 'KI2_LOG_DIR')):
        raise ValueError('Najpierw uzgodnij istniejące zmienne ścieżek KI 2.')
    if shutil.disk_usage(target.parent).free < source.stat().st_size * 2 + 1024**3:
        raise ValueError('Za mało miejsca na zweryfikowaną kopię.')
    import KI
    keys_before = KI.load_service_keys(project=project)
    target.mkdir(mode=0o700)
    if target.resolve() != target:
        target.rmdir()
        raise ValueError('Windows przekierował katalog docelowy; wybierz stabilną ścieżkę poza AppData.')
    try:
        private_directory(target)
    except Exception:
        target.rmdir()  # Only our just-created, empty directory; never recursive.
        raise
    for name in ('data', 'logs', 'config', 'backups'):
        (target / name).mkdir(mode=0o700)
    secrets_source = project / '.streamlit' / 'secrets.toml'
    if not secrets_source.is_file():
        raise ValueError('Brak lokalnego pliku konfiguracji; profil nie został zmieniony.')
    active_secrets = target / 'config' / 'secrets.toml'
    shutil.copyfile(secrets_source, active_secrets)
    files = [(secrets_source, target / 'config' / 'previous-project-secrets.toml')]
    if (project / '.env').is_file():
        files.append((project / '.env', target / 'config' / 'previous-project.env'))
    for original, saved in files:
        shutil.copyfile(original, saved)
        if original.read_bytes() != saved.read_bytes():
            raise ValueError('Nie potwierdzono kopii konfiguracji.')
    keys_after = KI.load_service_keys(project=project, environ={**os.environ, 'KI2_SECRETS_FILE': str(active_secrets)})
    if keys_before != keys_after:
        raise ValueError('Konfiguracja usług po przeniesieniu jest inna.')
    with KI.ScannerLock(str(source) + '.launcher'), KI.ScannerLock(source):
        stamp = (source.stat().st_size, source.stat().st_mtime_ns)
        counts = copy_database(source, target / 'data' / source.name)
        if stamp != (source.stat().st_size, source.stat().st_mtime_ns):
            raise ValueError('Źródło zmieniło się podczas kopiowania; profil nie został zmieniony.')
        data = {'version': 1, 'data_dir': str(target / 'data'), 'log_dir': str(target / 'logs'),
                'secrets_file': str(active_secrets)}
        removed = []
        try:
            with profile.open('x', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            if KI.load_service_keys(project=project) != keys_before:
                raise ValueError('Nie potwierdzono odczytu nowej konfiguracji.')
            for original, saved in files:
                if original.read_bytes() != saved.read_bytes():
                    raise ValueError('Konfiguracja źródłowa zmieniła się podczas migracji.')
                original.unlink()
                removed.append((original, saved))
        except Exception:
            profile.unlink(missing_ok=True)
            for original, saved in removed:
                shutil.copyfile(saved, original)
            raise
    result = {**plan, 'status': 'ACTIVATED_LOCAL_ONLY', 'tables': counts,
              'database': str(target / 'data' / source.name), 'profile': str(profile),
              'service_keys_unchanged': True, 'configuration_files_moved': len(files)}
    (target / 'migration-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        result = migrate(args.project, args.target, args.apply)
    except Exception as error:
        print(json.dumps({'status': 'FAILED', 'error_type': type(error).__name__,
                          'message': 'Migracja przerwana; sprawdź stan profilu i raport. Bez uruchamiania KI.'}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
