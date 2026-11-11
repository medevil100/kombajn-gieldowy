"""Run KI regression in an isolated code copy, without production DBs or keys.

Python tests use their own fixtures/mocked providers. No scanner in market mode,
paid probes, historical job retries or Telegram previews are started here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


def snapshot(source, destination):
    files = []
    suffixes = {'.py', '.md', '.cjs', '.ps1', '.conf', '.service', '.timer'}
    for path in sorted(source.iterdir()):
        if not path.is_file() or path.name.startswith(('_', 'Alchemik-', 'audit_', 'verify_', 'edit_')):
            continue
        if path.suffix not in suffixes and path.name not in ('requirements.txt', 'odpowiedz_AAT.json', 'odpowiedz_3RG.json'):
            continue
        shutil.copy2(path, destination / path.name)
        files.append({'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New report directory outside the project.')
    parser.add_argument('--list', action='store_true', help='List current root-level Python test modules only.')
    parser.add_argument('--node', help='Optional path to Node.js for the fullscreen JavaScript test.')
    parser.add_argument('--phase', action='append', choices=(
        'self-test', 'all-python-modules', 'panel', 'launch-diagnostic', 'fullscreen-javascript'),
        help='Run only named phases; omit for the full regression.')
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent
    modules = sorted(p.stem for p in source.glob('test_*.py'))
    if args.list:
        print('\n'.join(modules))
        print(f'Moduly: {len(modules)}')
        return 0
    if args.output:
        output = args.output.expanduser().resolve()
        if output == source or source in output.parents:
            parser.error('Report directory must be outside the project.')
        output.mkdir(parents=True, exist_ok=False)
    else:
        output = Path(tempfile.mkdtemp(prefix='ki2-regression-'))
    code = output / 'code'
    code.mkdir()
    home = output / 'empty-home'
    home.mkdir()
    files = snapshot(source, code)
    if not (code / 'KI.py').is_file():
        raise ValueError('Missing KI.py in isolated snapshot.')
    env = dict(os.environ)
    for key in tuple(env):
        if key.upper().startswith('KI2_') or any(token in key.upper() for token in ('API_KEY', 'BOT_TOKEN', 'CHAT_ID', 'SECRET', 'ACCESS_TOKEN')):
            env.pop(key, None)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', PYTHONUNBUFFERED='1',
               PYTHONPATH=str(code), USERPROFILE=str(home))
    # Path.home uses HOME on POSIX. This is the child environment, not a shell variable.
    if os.name != 'nt':
        env['HOME'] = str(home)
    python = [sys.executable, '-B', '-X', 'utf8']
    phases = [
        ('self-test', python + ['KI.py', '--self-test']),
        ('all-python-modules', python + ['-m', 'unittest', 'discover', '-s', '.', '-p', 'test_*.py', '-v']),
        ('panel', python + ['KI.py', '--panel-test']),
        ('launch-diagnostic', python + ['KI.py', '--launch-test']),
    ]
    node = args.node or shutil.which('node')
    if args.node and not Path(args.node).is_file():
        parser.error('The specified Node.js executable does not exist.')
    if node:
        phases.append(('fullscreen-javascript', [node, 'test_fullscreen_20261105.cjs']))
    if args.phase:
        if 'fullscreen-javascript' in args.phase and not node:
            parser.error('The JavaScript phase requires Node.js.')
        phases = [(name, command) for name, command in phases if name in args.phase]
    report = {'source': str(source), 'code': str(code), 'python': sys.version,
              'modules': modules, 'files': files, 'phases': [],
              'javascript': ('scheduled' if any(name == 'fullscreen-javascript' for name, _ in phases)
                             else 'NOT_SELECTED' if node else 'NOT_RUN_NODE_UNAVAILABLE'),
              'selected_phases': args.phase or 'ALL', 'production_access': False}
    print(f'Raport: {output}', flush=True)
    for name, command in phases:
        started = time.monotonic()
        log = output / (name + '.log')
        print(f'START {name}', flush=True)
        with log.open('w', encoding='utf-8') as stream:
            try:
                process = subprocess.run(command, cwd=code, env=env, stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=600, check=False)
                result = {'name': name, 'returncode': process.returncode}
            except subprocess.TimeoutExpired:
                result = {'name': name, 'returncode': None, 'error': 'TIMEOUT'}
        result['seconds'] = round(time.monotonic() - started, 2)
        content = log.read_text(encoding='utf-8', errors='replace')
        if name != 'fullscreen-javascript':
            result['tests'] = sum(map(int, re.findall(r'Ran (\d+) tests?', content)))
            if result['returncode'] == 0 and result['tests'] == 0:
                result.update(returncode=1, error='NO_TESTS_EXECUTED')
        else:
            report['javascript'] = 'PASS' if result['returncode'] == 0 else 'FAILED'
        report['phases'].append(result)
        report['status'] = 'RUNNING'
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'WYNIK {name}: {result["returncode"]} ({result["seconds"]} s)', flush=True)
    passed = all(item['returncode'] == 0 for item in report['phases'])
    if not passed:
        report['status'] = 'FAILED'
    elif args.phase:
        report['status'] = 'SELECTED_PHASES_PASS'
    else:
        report['status'] = 'PASS' if node else 'PYTHON_PASS_JAVASCRIPT_NOT_RUN'
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(report['status'], flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
