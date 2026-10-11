"""KI R1: Tavily CLI Research Mini only. No Search/Extract transport."""
from __future__ import annotations
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

class CLITransportError(RuntimeError):
    """A Tavily CLI subprocess did not return a verified complete result."""
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response if isinstance(response, dict) else None
        self.request_id = None
        if self.response:
            value = self.response.get('request_id')
            if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,255}', value):
                self.request_id = value


def sanitize_cli_diagnostic(value, secrets=()):
    """Bound CLI errors and remove credentials before SQLite/UI diagnostics."""
    text = str(value or '')
    for secret in sorted((v for v in secrets if isinstance(v, str) and v), key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'(?i)Bearer\s+[^\s"\']+', 'Bearer [REDACTED]', text)
    text = re.sub(r'(?i)(?:tvly-|sk-)[A-Za-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization)["\']?\s*[:=]\s*["\']?)[^\s"\',}]+', r'\1[REDACTED]', text)
    text = ''.join(c if c >= ' ' or c in '\n\t' else ' ' for c in text)
    return text.strip()[:3000]


def parse_cli_result(returncode, stdout, stderr, secrets=()):
    """Parse a real process result; retain a valid task ID even on CLI failure."""
    if len(stdout) > 12_000_000:
        raise CLITransportError('Tavily CLI: przekroczony rozmiar danych; bez ponowienia.')
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError):
        data = None
    detail = sanitize_cli_diagnostic(stderr or (data.get('error') if isinstance(data, dict) else stdout), secrets)
    if returncode != 0:
        raise CLITransportError('Tavily CLI: kod '+str(returncode)+'. '+detail, data)
    if not isinstance(data, dict):
        raise CLITransportError('Tavily CLI: niepoprawny JSON. '+detail)
    if data.get('error'):
        raise CLITransportError('Tavily CLI: '+sanitize_cli_diagnostic(data['error'], secrets), data)
    return data


def _safe_url(url):
    """Validate a public HTTPS citation without opening the URL."""
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        part = urlsplit(url)
        if part.scheme != "https" or not part.hostname or part.username or part.password:
            return False
        hostname = part.hostname.lower().strip(".")
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            return False
        if "." not in hostname:
            return False
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            return True
        return ip.is_global
    except (ValueError, TypeError):
        return False


def _launch(args, api_key):
    """Do not interpret a web result as shell syntax. No API call without a key."""
    if not api_key or not isinstance(api_key, str):
        raise CLITransportError("Tavily CLI: brak zatwierdzonego klucza API.")
    executable = shutil.which("tvly")
    if not executable:
        raise CLITransportError("Tavily CLI: nie znaleziono polecenia tvly w PATH. Nie wykonano zapytania.")
    env = dict(os.environ)
    env["TAVILY_API_KEY"] = api_key
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        done = subprocess.run([executable, *args, "--json"], check=False,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=env, shell=False, timeout=110)
    except subprocess.TimeoutExpired:
        raise CLITransportError("Tavily CLI: limit czasu. Koszt zapytania nieznany; nie ponawiać automatycznie.") from None
    except OSError as exc:
        raise CLITransportError("Tavily CLI: proces nie wystartowal; "+type(exc).__name__+
                                "; errno="+str(exc.errno)+"; winerror="+str(getattr(exc, 'winerror', None))) from None
    secrets = [api_key] + [value for name, value in env.items()
                           if any(word in name.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD'))]
    return parse_cli_result(done.returncode, done.stdout, done.stderr, secrets)



RESEARCH_OUTPUT_SCHEMA={
    'properties':{'materials':{'type':'array','description':'Materiały dotyczące wskazanego emitenta; bez własnych ocen.',
        'items':{'type':'object','properties':{
            'url':{'type':'string','description':'Dokładny URL obecny w cytowaniach sources.'},
            'title':{'type':'string','description':'Dokladny tytul materialu zrodlowego.'},
            'published_at':{'type':'string','description':'Data publikacji ISO 8601 ze strefą czasową; pusty tekst jeśli nieznana.'},
            'content':{'type':'string','description':'Dosłowny fragment źródła, bez parafrazy; pusty tekst jeśli niedostępny.'}},
            'required':['url','title','published_at','content']}}},
    'required':['materials']}


def research_start_arguments(query):
    if not isinstance(query,str) or not query.strip():raise CLITransportError('Research: puste zapytanie.')
    return ['research','run',query.strip(),'--model','mini','--no-wait']


def research_status_arguments(request_id):
    if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,255}',request_id):
        raise CLITransportError('Research: niepoprawny request_id.')
    return ['research','status',request_id]


def _normalize_research_response(raw,expected_request_id=None):
    if not isinstance(raw,dict):raise ValueError('Research: odpowiedź nie jest obiektem.')
    request_id=raw.get('request_id') or expected_request_id
    research_status_arguments(request_id)
    if expected_request_id and request_id!=expected_request_id:raise ValueError('Research: niezgodny request_id.')
    status=raw.get('status')
    allowed=('pending','queued','running','in_progress','processing','submitted','completed','failed','error','cancelled','canceled')
    if not isinstance(status,str) or status.lower() not in allowed:raise ValueError('Research: nieznany status.')
    status=status.lower()
    sources=raw.get('sources')
    if status=='completed' and not isinstance(sources,list):raise ValueError('Research: niepoprawne sources.')
    if sources is not None and not isinstance(sources,list):raise ValueError('Research: niepoprawne sources.')
    return {**raw,'request_id':request_id,'status':status,'sources':sources or [],
            'raw_response':raw.get('raw_response') if isinstance(raw.get('raw_response'),dict) else raw}


def start_research(query,api_key):
    if not isinstance(api_key,str) or not api_key.strip():raise CLITransportError('Research: brak klucza API.')
    args=research_start_arguments(query)
    # A closed temporary schema file works on Windows; it contains no credentials.
    fd,path=tempfile.mkstemp(prefix='ki_research_schema_',suffix='.json')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as handle:json.dump(RESEARCH_OUTPUT_SCHEMA,handle,ensure_ascii=False)
        raw=_launch([*args,'--output-schema',path],api_key)
        try:
            return _normalize_research_response(raw)
        except (ValueError, CLITransportError) as exc:
            raise CLITransportError('Research: odpowiedz startowa: '+str(exc), raw) from None
    except OSError as exc:
        raise CLITransportError('Research: plik schematu: '+type(exc).__name__+'; errno='+str(exc.errno)) from None
    finally:
        try:Path(path).unlink(missing_ok=True)
        except OSError:pass  # Cleanup must never hide a received request_id.


def check_research(request_id,api_key):
    args=research_status_arguments(request_id)
    raw=_launch(args,api_key)
    try:return _normalize_research_response(raw,request_id)
    except ValueError:
        raise CLITransportError('Research: niepoprawna odpowiedź statusu. ID zachowano.') from None
