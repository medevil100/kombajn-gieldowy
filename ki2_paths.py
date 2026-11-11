"""Runtime paths and service keys; no filesystem writes or provider imports."""
import argparse
import json
import os
from pathlib import Path
import tomllib

PROFILE = '.ki2-local-paths.json'


def _absolute(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Niepoprawna konfiguracja ścieżek KI 2.')
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('Ścieżki konfiguracji KI 2 muszą być bezwzględne.')
    return path.resolve()


def runtime_paths(project, environ=None, platform=None):
    project = Path(project).resolve()
    env = os.environ if environ is None else environ
    platform = os.name if platform is None else platform
    local = {}
    profile = project / PROFILE
    # Local Windows routing must never silently change production Linux paths.
    if platform == 'nt' and profile.exists():
        try:
            local = json.loads(profile.read_text(encoding='utf-8-sig'))
            if not isinstance(local, dict) or local.get('version') != 1:
                raise ValueError()
            if set(local) != {'version', 'data_dir', 'log_dir', 'secrets_file'}:
                raise ValueError()
        except (OSError, ValueError):
            raise ValueError('Nie można odczytać lokalnych ścieżek KI 2.') from None
    data = env.get('KI2_DATA_DIR') or local.get('data_dir')
    logs = env.get('KI2_LOG_DIR') or local.get('log_dir')
    secrets = env.get('KI2_SECRETS_FILE') or local.get('secrets_file')
    return {'database': (_absolute(data) if data else project) / 'KI.matrix.sqlite3',
            'log_dir': _absolute(logs) if logs else None,
            'secrets_file': _absolute(secrets) if secrets else project / '.streamlit' / 'secrets.toml',
            'secrets_required': bool(secrets)}


def default_database(project, environ=None, platform=None):
    return runtime_paths(project, environ, platform)['database']


def process_log_paths(database, project, environ=None, platform=None):
    db = Path(database).expanduser().resolve()
    folder = runtime_paths(project, environ, platform)['log_dir']
    base = folder / db.name if folder else db
    return [base.with_suffix('.scanner.log'), base.with_suffix('.panel.log')]


def load_keys(keys, project, home=None, environ=None, platform=None):
    env = os.environ if environ is None else environ
    paths = runtime_paths(project, env, platform)
    home = Path(home) if home is not None else Path.home()
    values = {}
    for path, required in ((home / '.streamlit' / 'secrets.toml', False),
                           (paths['secrets_file'], paths['secrets_required'])):
        if required or path.exists():
            try:
                values.update(tomllib.loads(path.read_text(encoding='utf-8-sig')))
            except (OSError, ValueError):
                raise ValueError('Nie można odczytać konfiguracji usług z secrets.toml.') from None
    return {key: str(env.get(key) or values.get(key) or '').strip() for key in keys}


def main():
    parser = argparse.ArgumentParser(description='Ścieżki KI 2, bez wartości kluczy.')
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    paths = runtime_paths(args.project)
    if paths['log_dir'] is None:
        paths['log_dir'] = paths['database'].parent
    print(json.dumps({key: str(value) if isinstance(value, Path) else value
                      for key, value in paths.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
