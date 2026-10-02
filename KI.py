"""KI.py — etap 1: procesy, SQLite, jawna migracja i diagnostyka.

Interfejs: python -m streamlit run KI.py -- --ui --db KI.stage1.sqlite3
Diagnostyka: python KI.py --scanner --diagnostic --db KI.stage1.sqlite3
Testy: python KI.py --self-test
Raport migracji: python KI.py --migration-report state.json
Import: python KI.py --migrate state.json --approve-sha <SHA256_Z_RAPORTU>

Etap 1 nie podłącza automatycznego pobierania danych ani usług zewnętrznych.
Istniejące ręczne moduły UI zostają zachowane do kolejnych etapów naprawy.
"""
from pathlib import Path
from contextlib import contextmanager
import argparse
import hashlib
import json
import math
import os
import signal
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

STAGE = 1
SCHEMA_VERSION = 1
DEFAULT_DB = Path(__file__).resolve().with_name('KI.stage1.sqlite3')
_STORE = None


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS legacy_state(
 section TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watchlist(ticker TEXT PRIMARY KEY, position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS portfolio(
 ticker TEXT PRIMARY KEY, shares REAL NOT NULL CHECK(shares>0),
 avg_price REAL NOT NULL CHECK(avg_price>0), currency TEXT, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts(
 id TEXT PRIMARY KEY, ticker TEXT NOT NULL, direction TEXT NOT NULL,
 target_price REAL NOT NULL CHECK(target_price>0), status TEXT NOT NULL,
 previous_price REAL, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations(
 id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, interval TEXT NOT NULL,
 candle_time TEXT NOT NULL, acquired_at TEXT NOT NULL, candle_status TEXT NOT NULL,
 payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS observation_lookup ON observations(ticker,interval,acquired_at);
CREATE TABLE IF NOT EXISTS baselines(
 ticker TEXT NOT NULL, interval TEXT NOT NULL, payload TEXT NOT NULL,
 updated_at TEXT NOT NULL, PRIMARY KEY(ticker,interval));
CREATE TABLE IF NOT EXISTS events(
 id TEXT PRIMARY KEY, ticker TEXT NOT NULL, interval TEXT NOT NULL,
 created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(
 id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id),
 kind TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
 next_attempt_at TEXT, last_error TEXT, delivered_at TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS outbox_pending ON outbox(status,next_attempt_at);
CREATE TABLE IF NOT EXISTS cycles(
 id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
 status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime(
 key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS migrations(
 source_sha256 TEXT PRIMARY KEY, source_path TEXT NOT NULL, imported_at TEXT NOT NULL,
 warning_payload TEXT NOT NULL);
"""


class Store:
    """Short connections; every write is one real SQLite transaction."""
    def __init__(self, db):
        self.path = Path(db).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as c:
            c.execute('PRAGMA journal_mode=WAL')
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone()
            if exists:
                row = c.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
                if row and int(row[0]) != SCHEMA_VERSION:
                    raise ValueError('Nieobsługiwana wersja bazy; nie zmieniono schematu.')
            c.executescript(SCHEMA)
            c.execute("INSERT OR IGNORE INTO metadata VALUES('schema_version',?)", (str(SCHEMA_VERSION),))

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=15000')
        c.execute('PRAGMA synchronous=FULL')
        try:
            yield c
        finally:
            c.close()

    @contextmanager
    def transaction(self):
        with self.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                yield c
                c.execute('COMMIT')
            except BaseException:
                c.execute('ROLLBACK')
                raise

    def load_state(self):
        with self.connection() as c:
            return {r['section']: json.loads(r['payload']) for r in c.execute('SELECT section,payload FROM legacy_state')}

    def load_section(self, section, default):
        with self.connection() as c:
            r = c.execute('SELECT payload FROM legacy_state WHERE section=?', (section,)).fetchone()
            return json.loads(r[0]) if r else default

    def _write_section(self, c, section, data):
        payload = json_text(data)
        c.execute('INSERT INTO legacy_state VALUES(?,?,?) ON CONFLICT(section) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                  (section, payload, utc_now()))
        # Stage-one adapters preserve all legacy fields while preparing typed data.
        if section == 'settings':
            c.execute('DELETE FROM settings')
            c.executemany('INSERT INTO settings VALUES(?,?)', [(k, json_text(v)) for k,v in data.items()])
        elif section == 'tickers':
            c.execute('DELETE FROM watchlist')
            c.executemany('INSERT INTO watchlist VALUES(?,?)', [(t,i) for i,t in enumerate(data)])
        elif section == 'portfolio':
            c.execute('DELETE FROM portfolio')
            c.executemany('INSERT INTO portfolio VALUES(?,?,?,?,?)',
                          [(p['ticker'],p['shares'],p['avg_price'],p.get('currency'),json_text(p)) for p in data])
        elif section == 'alerts':
            # Only legacy IDs are synchronized. Future independently identified alerts survive.
            c.execute("DELETE FROM alerts WHERE id LIKE 'legacy:%'")
            for ticker,a in data.items():
                direction = 'UP' if a['type'] == 'SELL_TARGET' else 'DOWN'
                status = 'ARMED' if a.get('active',True) else 'TRIGGERED_LEGACY'
                c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?)',
                          ('legacy:'+ticker,ticker,direction,a['price'],status,None,json_text(a),utc_now()))

    def save_section(self, section, data):
        if section in ('settings','tickers','portfolio','alerts'):
            errors = validate_state({section:data})
            if errors:
                raise ValueError('; '.join(errors))
        with self.transaction() as c:
            self._write_section(c, section, data)

    def update_settings(self, changes):
        """Merge under the write lock: independent updates cannot erase each other."""
        with self.transaction() as c:
            row = c.execute("SELECT payload FROM legacy_state WHERE section='settings'").fetchone()
            current = json.loads(row[0]) if row else {}
            current.update(changes)
            errors = validate_state({'settings': current})
            if errors:
                raise ValueError('; '.join(errors))
            self._write_section(c, 'settings', current)

    def set_baseline(self, ticker, interval, payload):
        encoded = json_text(payload)
        with self.transaction() as c:
            c.execute('INSERT INTO baselines VALUES(?,?,?,?) ON CONFLICT(ticker,interval) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                      (ticker,interval,encoded,utc_now()))

    def get_baseline(self, ticker, interval):
        with self.connection() as c:
            row = c.execute('SELECT payload FROM baselines WHERE ticker=? AND interval=?', (ticker,interval)).fetchone()
            return json.loads(row[0]) if row else None

    def record_event(self, ticker, interval, evidence, message=None):
        event_id = uuid.uuid4().hex
        now = utc_now()
        with self.transaction() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)', (event_id,ticker,interval,now,json_text(evidence)))
            if message is not None:
                c.execute('INSERT INTO outbox(id,event_id,kind,message,created_at) VALUES(?,?,?,?,?)',
                          (uuid.uuid4().hex,event_id,'MOVEMENT',message,now))
        return event_id

    def runtime_status(self, payload):
        with self.transaction() as c:
            c.execute("INSERT INTO runtime VALUES('scanner',?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                      (json_text(payload),utc_now()))


def finite_number(value, positive=False):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and (not positive or value>0)


def valid_ticker(value):
    return isinstance(value,str) and bool(value.strip()) and value == value.strip().upper()


def validate_state(data):
    errors = []
    if not isinstance(data,dict):
        return ['Korzeń JSON musi być obiektem.']
    if 'tickers' in data:
        ticks = data['tickers']
        if not isinstance(ticks,list) or any(not valid_ticker(t) for t in ticks):
            errors.append('tickers: wymagana lista niepustych tickerów zapisanych wielkimi literami.')
        elif len(set(ticks)) != len(ticks):
            errors.append('tickers: powtarzające się tickery.')
    if 'settings' in data:
        settings = data['settings']
        if not isinstance(settings,dict):
            errors.append('settings: wymagany obiekt.')
        else:
            if 'telegram' in settings and not isinstance(settings['telegram'],bool):
                errors.append('settings.telegram: wymagana wartość logiczna.')
            v = settings.get('auto_scan_interval',0)
            if isinstance(v,bool) or not isinstance(v,int) or v not in (0,15,30,60):
                errors.append('settings.auto_scan_interval: dozwolone 0,15,30,60.')
    if 'portfolio' in data:
        items = data['portfolio']
        if not isinstance(items,list):
            errors.append('portfolio: wymagana lista.')
        else:
            seen = set()
            for i,p in enumerate(items):
                if not isinstance(p,dict) or not valid_ticker(p.get('ticker')) or not finite_number(p.get('shares'),True) or not finite_number(p.get('avg_price'),True):
                    errors.append(f'portfolio[{i}]: błędny ticker, liczba akcji lub cena.')
                elif p['ticker'] in seen:
                    errors.append(f'portfolio[{i}]: powtórzona pozycja tickera.')
                else:
                    seen.add(p['ticker'])
                    currency = p.get('currency')
                    if currency is not None and (not isinstance(currency,str) or len(currency)!=3 or not currency.isalpha() or currency!=currency.upper()):
                        errors.append(f'portfolio[{i}].currency: wymagany trzyliterowy kod.')
    if 'alerts' in data:
        alerts = data['alerts']
        if not isinstance(alerts,dict):
            errors.append('alerts: wymagany obiekt.')
        else:
            for t,a in alerts.items():
                if not valid_ticker(t) or not isinstance(a,dict) or a.get('type') not in ('BUY_TARGET','SELL_TARGET','STOP_LOSS') or not finite_number(a.get('price'),True) or not isinstance(a.get('active',True),bool):
                    errors.append(f'alerts[{t}]: błędny ticker, typ, cena lub aktywność.')
    for section in ('last_scan','backtest'):
        if section in data and not isinstance(data[section],dict):
            errors.append(f'{section}: wymagany obiekt.')
    if isinstance(data.get('last_scan'),dict):
        for ticker,item in data['last_scan'].items():
            if not valid_ticker(ticker) or not isinstance(item,dict):
                errors.append(f'last_scan[{ticker}]: błędna struktura.')
            elif item.get('price') is not None and not finite_number(item['price'],True):
                errors.append(f'last_scan[{ticker}].price: błędna cena.')
            elif item.get('rvol') is not None and (not finite_number(item['rvol']) or item['rvol']<0):
                errors.append(f'last_scan[{ticker}].rvol: błędny RVOL.')
    return errors


def reject_duplicate_keys(pairs):
    data = {}
    for key,value in pairs:
        if key in data:
            raise ValueError('Powtórzony klucz JSON: '+key)
        data[key] = value
    return data


def normalize_legacy(value, warnings, errors, path='state'):
    if isinstance(value,float) and not math.isfinite(value):
        # Historical market calculations used NaN. Do not silently use it as a baseline.
        if path.startswith(('state.last_scan.','state.backtest.')):
            warnings.append(path+': NaN/Infinity zastąpiono brakiem danych (null).')
            return None
        errors.append(path+': niedozwolone NaN/Infinity.')
        return None
    if isinstance(value,dict):
        return {k:normalize_legacy(v,warnings,errors,path+'.'+k) for k,v in value.items()}
    if isinstance(value,list):
        return [normalize_legacy(v,warnings,errors,f'{path}[{i}]') for i,v in enumerate(value)]
    return value


def prepare_migration(source):
    path = Path(source).expanduser().resolve()
    errors, warnings = [], []
    sha, data = None, None
    try:
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw.decode('utf-8-sig'),object_pairs_hook=reject_duplicate_keys)
        data = normalize_legacy(data,warnings,errors)
        errors.extend(validate_state(data))
    except (OSError,UnicodeError,ValueError) as exc:
        errors.append(f'Nie można zatwierdzić źródła: {exc}')
    if isinstance(data,dict) and not errors:
        if data.get('last_scan'):
            warnings.append('last_scan zachowano jako historię legacy; brak czasu i interwału wyklucza użycie jako nowego punktu odniesienia.')
        if any(p.get('currency') is None for p in data.get('portfolio',[])):
            warnings.append('Portfel zawiera pozycje bez waluty; nie przypisano jej na podstawie domysłu.')
        if any(not a.get('active',True) for a in data.get('alerts',{}).values()):
            warnings.append('Nieaktywne alerty zachowano; historyczne dostarczenie Telegrama jest niepotwierdzone.')
    return {'source':str(path),'sha256':sha,'errors':errors,'warnings':warnings,'data':data}


def public_migration_report(plan):
    data = plan['data'] if isinstance(plan['data'],dict) else {}
    return {k:plan[k] for k in ('source','sha256','errors','warnings')} | {
        'valid': not plan['errors'],
        'sections':list(data),
        'counts':{k:len(v) for k,v in data.items() if isinstance(v,(dict,list))},
        'note':'Raport nie zmienia źródła ani bazy. Import wymaga --approve-sha z tego raportu.'}


def import_migration(store, plan, expected_sha):
    if plan['errors'] or not plan['sha256'] or expected_sha != plan['sha256']:
        raise ValueError('Import zablokowany: błędy walidacji lub niezgodny zatwierdzony SHA256.')
    if hashlib.sha256(Path(plan['source']).read_bytes()).hexdigest() != expected_sha:
        raise ValueError('Źródło zmieniło się po raporcie; przygotuj nowy raport.')
    with store.transaction() as c:
        if c.execute('SELECT 1 FROM migrations WHERE source_sha256=?',(expected_sha,)).fetchone():
            return {'status':'ALREADY_IMPORTED','sha256':expected_sha}
        for table in ('legacy_state','settings','watchlist','portfolio','alerts','observations','baselines','events','outbox','cycles','runtime','migrations'):
            if c.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                raise ValueError('Import wymaga pustej bazy; nie nadpisano istniejących danych.')
        for section,data in plan['data'].items():
            store._write_section(c,section,data)
        c.execute('INSERT INTO migrations VALUES(?,?,?,?)',
                  (expected_sha,plan['source'],utc_now(),json_text(plan['warnings'])))
    return {'status':'IMPORTED','sha256':expected_sha,'warnings':plan['warnings']}


class ScannerLock:
    """OS lock is held for the full scanner lifetime and released even after a crash."""
    def __init__(self, db):
        self.path = Path(str(Path(db).expanduser().resolve())+'.scanner.lock')
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0,os.SEEK_END)
                if self.file.tell()==0:
                    self.file.write(b'0')
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError('Drugi skaner zablokowany: baza ma już aktywny proces skanera.') from exc
        return self

    def __exit__(self,*args):
        if self.file:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            self.file.close()
            self.file = None


def next_slot(now, seconds):
    return (math.floor(now/seconds)+1)*seconds


def scanner_main(db, diagnostic=False, cycles=None):
    if not diagnostic:
        raise ValueError('Etap 1: dostępny tylko --scanner --diagnostic. Pobieranie i detekcja nie są jeszcze podłączone.')
    stop = threading.Event()
    previous_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT,signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig,lambda *_:stop.set())
    try:
        with ScannerLock(db):
            store = Store(db)
            count = 0
            status = {'pid':os.getpid(),'mode':'DIAGNOSTIC','stage':STAGE,'status':'RUNNING'}
            print('DIAGNOSTYKA: cykle bez danych rynku i bez wywołań usług.',flush=True)
            store.runtime_status(status)
            while not stop.is_set() and (cycles is None or count<cycles):
                cycle_id, started = uuid.uuid4().hex, utc_now()
                with store.transaction() as c:
                    c.execute('INSERT INTO cycles VALUES(?,?,?,?,?)',
                              (cycle_id,started,utc_now(),'DIAGNOSTIC',json_text({'market_scan':False,'pid':os.getpid()})))
                count += 1
                status['cycles_this_run'] = count
                store.runtime_status(status)
                print(json_text({'cycle':count,'id':cycle_id,'status':'DIAGNOSTIC'}),flush=True)
                if cycles is not None and count>=cycles:
                    break
                settings = store.load_section('settings',{})
                minutes = settings.get('auto_scan_interval',15)
                target = next_slot(time.time(),max(15,minutes)*60)
                heartbeat = time.monotonic()
                while time.time()<target and not stop.is_set():
                    stop.wait(min(1,max(0,target-time.time())))
                    if time.monotonic()-heartbeat>=5:
                        store.runtime_status(status)
                        heartbeat = time.monotonic()
                # No catch-up: overruns skip past slots, never overlap another cycle.
            status['status'] = 'STOPPED'
            store.runtime_status(status)
    finally:
        for sig,handler in previous_handlers.items():
            signal.signal(sig,handler)
    return 0


def _load_state():
    return _STORE.load_state()


def _load_user_tickers():
    return _STORE.load_section('tickers',[])


def _save_user_tickers(data):
    _STORE.save_section('tickers',data)


def _load_last_scan():
    return _STORE.load_section('last_scan',{})


def _save_last_scan(data):
    warnings,errors = [],[]
    clean = normalize_legacy(data,warnings,errors,'state.last_scan')
    if errors:
        raise ValueError('; '.join(errors))
    _STORE.save_section('last_scan',clean)


def _load_settings():
    return _STORE.load_section('settings',{})


def _save_settings(data):
    _STORE.update_settings(data)


def _load_alerts():
    return _STORE.load_section('alerts',{})


def _save_alerts(data):
    _STORE.save_section('alerts',data)


def _load_backtest_results():
    return _STORE.load_section('backtest',{})


def _save_backtest_results(data):
    _STORE.save_section('backtest',data)


def _load_portfolio():
    return _STORE.load_section('portfolio',[])


def _save_portfolio(data):
    _STORE.save_section('portfolio',data)

def _has_changed(ticker: str, price_now: float, rvol_now: float) -> bool:
    """Sprawdza czy cena zmieniła się >1% lub wolumen >2% od ostatniego skanu."""
    last_scan = _load_last_scan()
    old = last_scan.get(ticker, {})
    old_price = old.get("price", None)
    old_vol = old.get("rvol", None)
    price_changed = old_price is None or (
        old_price != 0 and abs(price_now - old_price) / max(abs(old_price), 0.0001) > 0.01
    )
    vol_changed = old_vol is None or (
        old_vol != 0 and abs(rvol_now - old_vol) / max(abs(rvol_now), 0.0001) > 0.02
    )
    return price_changed or vol_changed


def run_streamlit(db):
    global _STORE
    try:
        import re
        import requests
        import numpy as np
        import pandas as pd
        import yfinance as yf
        import plotly.graph_objects as go
        import streamlit as st
        from streamlit_autorefresh import st_autorefresh
    except ImportError as exc:
        raise ValueError("Brak zależności interfejsu: " + str(exc) + ". SQLite i --self-test działają bez tych pakietów.") from exc
    _STORE = Store(db)
    # ------------------ KONFIGURACJA ------------------
    st.set_page_config(page_title="CYBER DESK PRO", page_icon="💠", layout="wide")
    st.warning("ETAP 1 — wersja robocza. SQLite i diagnostyka procesów; moduły rynku są wyłączone do kolejnych etapów naprawy.")
    st.caption(f"Baza robocza: {_STORE.path}")

    st.markdown(
        """
        <style>
        body, .stApp { background-color: #050816; color: #E0E0FF; }
        .stSidebar, section[data-testid="stSidebar"] { background: radial-gradient(circle at top, #111827 0, #020617 60%); color: #E0E0FF; }
        .stButton>button { background: linear-gradient(90deg, #0ea5e9, #6366f1); color: white; border-radius: 8px; border: none; }
        .stButton>button:hover { background: linear-gradient(90deg, #22c55e, #6366f1); color: #e5e7eb; }
        .stTextInput>div>div>input { background-color: #020617; color: #e5e7eb; }
        .stSelectbox>div>div>div { background-color: #020617; color: #e5e7eb; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### 💠 CYBER DESK PRO")
        st.caption("Czat + Trading + Skaner · GPT-4.1 + Tavily + yfinance")
        _saved_settings = _load_settings()
        _saved_tickers = _load_user_tickers()

        mode = st.radio(
            "Tryb pracy:",
            [
                "🏠 Dashboard portfela",
                "🤖 Czat AI (internet + trading)",
                "📈 Kombajn tradingowy",
                "🧪 Skaner spółek (wpisz własne tickery)",
                "🔔 Alerty cenowe",
                "📊 Backtesting sygnałów",
            ],
        )
        st.divider()
        tg_enabled = st.checkbox("📲 Telegram – wysyłaj wyniki",
                                 value=_saved_settings.get("telegram", True),
                                 help="Wysyła sygnały BUY/SELL, skany i odpowiedzi AI na Telegram")
        st.caption("Token i chat ID z secrets.toml")
        st.session_state["telegram_enabled"] = tg_enabled
        if tg_enabled != _saved_settings.get("telegram", True):
            _save_settings({"telegram": tg_enabled})

        st.divider()
        st.markdown("⏰ **Auto-skaner**")
        _auto_interval_options = [0, 15, 30, 60]
        _saved_auto_val = _saved_settings.get("auto_scan_interval", 0)
        _auto_index = _auto_interval_options.index(_saved_auto_val) if _saved_auto_val in _auto_interval_options else 0
        auto_interval = st.selectbox(
            "Skanuj co:",
            options=_auto_interval_options,
            format_func=lambda x: "Wyłączony" if x == 0 else f"Co {x} min",
            index=_auto_index,
            key="auto_interval"
        )
        st.caption("Etap 1: zapis ustawienia. Diagnostyka nie pobiera danych rynku.")
        st.session_state["auto_scan_interval"] = 0  # Etap 1: brak skanowania w UI
        if auto_interval != _saved_settings.get("auto_scan_interval", 0):
            _save_settings({"auto_scan_interval": auto_interval})

    # ------------------ FUNKCJE POMOCNICZE ------------------
    def detect_ticker_from_text(text: str):
        pattern = r"\b[A-Z0-9]{2,5}\.[A-Z]{2,3}\b|\b[A-Z]{1,5}\b"
        matches = re.findall(pattern, text)
        stop_words = {'I', 'A', 'THE', 'TO', 'FOR', 'OF', 'WITH', 'ON', 'AT', 'BY', 'IN', 'IS', 'IT', 'AS', 'OR', 'AND', 'BUT'}
        for m in matches:
            if m not in stop_words and len(m) >= 2:
                return m
        return None

    def to_scalar(x):
        if isinstance(x, (pd.Series, np.ndarray, list)):
            if len(x) == 0:
                return np.nan
            try:
                return float(np.asarray(x).ravel()[-1])
            except Exception:
                return np.nan
        try:
            return float(x)
        except Exception:
            return np.nan

    def fmt_price(price: float) -> str:
        """Formatuje cenę – dla groszówek więcej miejsc po przecinku."""
        if np.isnan(price) or price == 0:
            return "Brak"
        if price < 0.01:
            return f"{price:.6f}"
        elif price < 1:
            return f"{price:.4f}"
        elif price < 10:
            return f"{price:.3f}"
        else:
            return f"{price:.2f}"

    def fmt_price_short(price: float) -> str:
        """Krótki format ceny dla metryk."""
        if np.isnan(price) or price == 0:
            return "Brak"
        if price < 0.01:
            return f"{price:.4f}"
        elif price < 1:
            return f"{price:.3f}"
        else:
            return f"{price:.2f}"

    # ------------------ TELEGRAM ------------------
    def send_telegram(message: str, parse_mode: str = "HTML"):
        """Wysyła wiadomość przez Telegram Bot API.
           Token i chat ID czyta z st.secrets – nie hardcoduje."""
        try:
            token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                return False
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": parse_mode}
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------ WSKAŹNIKI TECHNICZNE ------------------
    def compute_indicators(close, volume):
        close = close.copy()
        volume = volume.copy()
        if len(close) < 30:
            return {"rsi": np.nan, "ma_fast": np.nan, "ma_slow": np.nan,
                    "upper_bb": pd.Series([np.nan]), "lower_bb": pd.Series([np.nan]),
                    "last_upper_bb": np.nan, "last_lower_bb": np.nan,
                    "macd": pd.Series([np.nan]), "macd_signal": pd.Series([np.nan]),
                    "macd_hist": pd.Series([np.nan]),
                    "last_macd": np.nan, "last_macd_signal": np.nan, "last_macd_hist": np.nan,
                    "vol": np.nan, "volume": np.nan,
                    "sl": np.nan, "tp": np.nan,
                    "trend": "Unknown", "atr": np.nan, "adx": np.nan,
                    "obv": np.nan, "vwap": np.nan, "roc": np.nan,
                    "stoch_k": np.nan, "stoch_d": np.nan, "rvol": np.nan}

        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs)).dropna()
        last_rsi = to_scalar(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

        # MA
        ma_fast = close.rolling(10).mean()
        ma_slow = close.rolling(30).mean()
        last_ma_fast = to_scalar(ma_fast.iloc[-1]) if not ma_fast.dropna().empty else np.nan
        last_ma_slow = to_scalar(ma_slow.iloc[-1]) if not ma_slow.dropna().empty else np.nan

        # BB
        ma_bb = close.rolling(20).mean()
        std_bb = close.rolling(20).std()
        upper_bb = ma_bb + 2 * std_bb
        lower_bb = ma_bb - 2 * std_bb
        last_upper_bb = to_scalar(upper_bb.iloc[-1]) if not upper_bb.dropna().empty else np.nan
        last_lower_bb = to_scalar(lower_bb.iloc[-1]) if not lower_bb.dropna().empty else np.nan

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_series = ema12 - ema26
        macd_signal_series = macd_series.ewm(span=9, adjust=False).mean()
        macd_hist_series = macd_series - macd_signal_series
        last_macd = to_scalar(macd_series.iloc[-1]) if not macd_series.empty else np.nan
        last_macd_signal = to_scalar(macd_signal_series.iloc[-1]) if not macd_signal_series.empty else np.nan
        last_macd_hist = to_scalar(macd_hist_series.iloc[-1]) if not macd_hist_series.empty else np.nan

        # Volatility
        vol_series = close.pct_change().rolling(20).std().dropna()
        last_vol = to_scalar(vol_series.iloc[-1]) if not vol_series.empty else np.nan

        # Volume
        last_volume = to_scalar(volume.iloc[-1]) if not volume.empty else np.nan

        # ATR
        high = close.rolling(1).max()
        low = close.rolling(1).min()
        tr = pd.concat([(high - low).abs(),
                        (high - close.shift(1)).abs(),
                        (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr_series = tr.rolling(14).mean()
        last_atr = to_scalar(atr_series.iloc[-1]) if not atr_series.dropna().empty else np.nan

        # ADX (uproszczony)
        try:
            plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0.0)
            minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0.0)
            atr_adx = tr.rolling(14).mean()
            plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_adx + 1e-9))
            minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_adx + 1e-9))
            dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
            adx_series = dx.rolling(14).mean()
            last_adx = to_scalar(adx_series.iloc[-1]) if not adx_series.dropna().empty else np.nan
        except:
            last_adx = np.nan

        # OBV
        try:
            obv = volume.where(close == close.shift(1), np.where(close > close.shift(1), volume, -volume)).cumsum()
            last_obv = to_scalar(obv.iloc[-1]) if not obv.empty else np.nan
        except:
            last_obv = np.nan

        # VWAP
        try:
            vwap_series = (close * volume).rolling(20).sum() / (volume.rolling(20).sum() + 1e-9)
            last_vwap = to_scalar(vwap_series.iloc[-1]) if not vwap_series.dropna().empty else np.nan
        except:
            last_vwap = np.nan

        # ROC
        try:
            roc_series = close.pct_change(10) * 100
            last_roc = to_scalar(roc_series.iloc[-1]) if not roc_series.dropna().empty else np.nan
        except:
            last_roc = np.nan

        # Stochastic
        try:
            low14 = close.rolling(14).min()
            high14 = close.rolling(14).max()
            stoch_k = (close - low14) / (high14 - low14 + 1e-9) * 100
            stoch_d = stoch_k.rolling(3).mean()
            last_stoch_k = to_scalar(stoch_k.iloc[-1]) if not stoch_k.dropna().empty else np.nan
            last_stoch_d = to_scalar(stoch_d.iloc[-1]) if not stoch_d.dropna().empty else np.nan
        except:
            last_stoch_k = np.nan
            last_stoch_d = np.nan

        # RVOL
        try:
            avg_vol_20 = volume.rolling(20).mean()
            rvol_series = volume / (avg_vol_20 + 1e-9)
            last_rvol = to_scalar(rvol_series.iloc[-1]) if not rvol_series.dropna().empty else np.nan
        except:
            last_rvol = np.nan

        # SL/TP
        sl_level = last_lower_bb if not np.isnan(last_lower_bb) else np.nan
        tp_level = last_upper_bb if not np.isnan(last_upper_bb) else np.nan

        # Trend
        if not np.isnan(last_ma_fast) and not np.isnan(last_ma_slow):
            if last_ma_fast > last_ma_slow * 1.01:
                trend = "Uptrend"
            elif last_ma_fast < last_ma_slow * 0.99:
                trend = "Downtrend"
            else:
                trend = "Sideways"
        else:
            trend = "Unknown"

        return {
            "rsi": last_rsi, "ma_fast": last_ma_fast, "ma_slow": last_ma_slow,
            "upper_bb": upper_bb, "lower_bb": lower_bb,
            "last_upper_bb": last_upper_bb, "last_lower_bb": last_lower_bb,
            "macd": macd_series, "macd_signal": macd_signal_series, "macd_hist": macd_hist_series,
            "last_macd": last_macd, "last_macd_signal": last_macd_signal, "last_macd_hist": last_macd_hist,
            "vol": last_vol, "volume": last_volume,
            "sl": sl_level, "tp": tp_level,
            "trend": trend,
            "atr": last_atr, "adx": last_adx,
            "obv": last_obv, "vwap": last_vwap, "roc": last_roc,
            "stoch_k": last_stoch_k, "stoch_d": last_stoch_d, "rvol": last_rvol,
        }

    def compute_scoring_pro(ind, sentiment=None):
        score = 0
        if ind["trend"] == "Uptrend": score += 20
        elif ind["trend"] == "Sideways": score += 10

        adx = ind.get("adx", np.nan)
        if not np.isnan(adx):
            if adx > 40: score += 20
            elif adx > 25: score += 15
            elif adx > 20: score += 10

        rsi = ind.get("rsi", np.nan)
        if not np.isnan(rsi):
            if 30 <= rsi <= 50: score += 15
            elif rsi < 30: score += 10
            elif 50 < rsi <= 70: score += 5

        k, d = ind.get("stoch_k", np.nan), ind.get("stoch_d", np.nan)
        if not np.isnan(k) and not np.isnan(d):
            if k < 20 and d < 20: score += 10
            elif k > 80 and d > 80: score += 0
            else: score += 5

        rvol = ind.get("rvol", np.nan)
        if not np.isnan(rvol):
            if rvol > 1.5: score += 15
            elif rvol > 1.0: score += 10
            elif rvol > 0.7: score += 5

        if not np.isnan(ind.get("last_macd", np.nan)) and not np.isnan(ind.get("last_macd_signal", np.nan)):
            if ind["last_macd"] > ind["last_macd_signal"]: score += 10

        if not np.isnan(ind.get("last_lower_bb", np.nan)): score += 5
        if not np.isnan(ind.get("last_upper_bb", np.nan)): score += 5

        if not np.isnan(ind.get("atr", np.nan)): score += 5

        if sentiment == "Bullish": score += 10
        elif sentiment == "Bearish": score -= 10

        return max(0, min(score, 100))

    def generate_signal(price, ind):
        rsi, ma_fast, ma_slow, trend = ind["rsi"], ind["ma_fast"], ind["ma_slow"], ind["trend"]
        adx, rvol, stoch_k, stoch_d = ind.get("adx", np.nan), ind.get("rvol", np.nan), ind.get("stoch_k", np.nan), ind.get("stoch_d", np.nan)
        sl, tp = ind["sl"], ind["tp"]

        if any(np.isnan(x) for x in [rsi, ma_fast, ma_slow]):
            return "HOLD", "Za mało danych."

        reasons = []
        signal = "HOLD"

        if trend == "Uptrend": reasons.append("📈 Trend wzrostowy (MA10 > MA30)")
        elif trend == "Downtrend": reasons.append("📉 Trend spadkowy (MA10 < MA30)")
        else: reasons.append("➡️ Trend boczny")

        if not np.isnan(adx):
            if adx < 20: reasons.append(f"🔹 ADX {adx:.1f} → słaby trend")
            elif adx < 40: reasons.append(f"🔸 ADX {adx:.1f} → umiarkowany")
            else: reasons.append(f"🔺 ADX {adx:.1f} → silny")

        if rsi < 30: reasons.append(f"📊 RSI {rsi:.1f} → wyprzedanie")
        elif rsi > 70: reasons.append(f"📊 RSI {rsi:.1f} → wykupienie")
        else: reasons.append(f"📊 RSI {rsi:.1f} → neutralny")

        if not np.isnan(stoch_k) and not np.isnan(stoch_d):
            if stoch_k < 20 and stoch_d < 20: reasons.append(f"🔻 Stochastic → wyprzedanie")
            elif stoch_k > 80 and stoch_d > 80: reasons.append(f"🔺 Stochastic → wykupienie")

        if not np.isnan(rvol):
            if rvol > 1.5: reasons.append(f"📊 RVOL {rvol:.2f} → wysoki wolumen")
            elif rvol < 0.7: reasons.append(f"📊 RVOL {rvol:.2f} → niski wolumen")

        if trend == "Uptrend" and rsi < 40:
            signal = "BUY"
            reasons.append("✅ Sygnał BUY: trend wzrostowy + RSI < 40")
        elif trend == "Downtrend" and rsi > 60:
            signal = "SELL"
            reasons.append("⛔ Sygnał SELL: trend spadkowy + RSI > 60")
        elif trend == "Uptrend" and 30 < rsi < 50:
            signal = "BUY"
            reasons.append("✅ Sygnał BUY: trend wzrostowy + RSI w strefie akumulacji")
        elif trend == "Downtrend" and rsi < 30:
            signal = "BUY"
            reasons.append("✅ Sygnał BUY: wyprzedanie w trendzie spadkowym")
        else:
            signal = "HOLD"
            reasons.append("⏸️ HOLD: brak jednoznacznego sygnału")

        if not np.isnan(sl): reasons.append(f"🛑 SL: {sl:.2f}")
        if not np.isnan(tp): reasons.append(f"🎯 TP: {tp:.2f}")

        return signal, "\n".join(f"- {r}" for r in reasons)

    def fetch_news_sentiment(ticker):
        try:
            t = yf.Ticker(ticker)
            news = t.news if hasattr(t, "news") else []
        except:
            news = []
        titles = [n.get("title", "") for n in news if isinstance(n.get("title", ""), str)][:5]
        if not titles:
            return "Mixed", [], "Brak newsów."
        score = 0
        pos = ["beat","strong","growth","upgrade","profit","record","surge","rally","positive"]
        neg = ["miss","weak","downgrade","fall","loss","cut","crash","negative","concern"]
        for title in titles:
            tl = title.lower()
            if any(w in tl for w in pos): score += 1
            if any(w in tl for w in neg): score -= 1
        sentiment = "Bullish" if score > 0 else "Bearish" if score < 0 else "Mixed"
        return sentiment, titles, ""

    # ------------------ KLASYFIKACJA TYPÓW RUCHU ------------------
    def classify_movement(close: pd.Series, price: float, ind: dict) -> tuple:
        """Rozpoznaje typ ruchu cenowego (breakout, pullback, konsolidacja itd.).
        Zwraca (etykieta_z_emoją, opis, ranking_wagowy)."""
        trend = ind.get("trend", "Unknown")
        adx = ind.get("adx", np.nan)
        rvol = ind.get("rvol", np.nan)
        roc = ind.get("roc", np.nan)
        rsi = ind.get("rsi", np.nan)
        obv = ind.get("obv", np.nan)
        last_upper = ind.get("last_upper_bb", np.nan)
        last_lower = ind.get("last_lower_bb", np.nan)
        ma_fast = ind.get("ma_fast", np.nan)
        ma_slow = ind.get("ma_slow", np.nan)
        vol = ind.get("vol", np.nan)

        has_all = not any(np.isnan(x) for x in [price, ma_fast, ma_slow])
        candidates = []

        # --- Gwałtowny ruch (Pump / Dump) ---
        if not np.isnan(roc) and not np.isnan(rvol):
            if roc > 4 and rvol > 2.0:
                candidates.append(("⚡ Gwałtowny wzrost (pump)", 40))
            elif roc < -4 and rvol > 2.0:
                candidates.append(("⚡ Gwałtowny spadek (dump)", 40))

        # --- Breakout / Breakdown ---
        if has_all and not np.isnan(last_upper) and not np.isnan(last_lower):
            if price > last_upper and trend == "Uptrend" and not np.isnan(rvol) and rvol > 1.3:
                candidates.append(("🚀 Breakout (przebicie górnego BB)", 50))
            elif price < last_lower and trend == "Downtrend" and not np.isnan(rvol) and rvol > 1.3:
                candidates.append(("💥 Breakdown (przebicie dolnego BB)", 50))

        # --- Reversal warning (dywergencja RSI) ---
        if len(close) >= 10 and not np.isnan(rsi):
            try:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / (loss + 1e-9)
                rsi_vals = 100 - (100 / (1 + rs))
                last5_rsi = rsi_vals.iloc[-5:]
                last5_price = close.iloc[-5:]
                if not last5_rsi.dropna().empty and not last5_price.dropna().empty:
                    if (last5_price.iloc[-1] > last5_price.max() - 1e-9 and
                        last5_rsi.iloc[-1] < last5_rsi.max() - 1e-9 and
                        last5_rsi.iloc[-1] < last5_rsi.iloc[0]):
                        candidates.append(("⚠️ Reversal (dywergencja RSI – niedźwiedzia)", 30))
                    if (last5_price.iloc[-1] < last5_price.min() + 1e-9 and
                        last5_rsi.iloc[-1] > last5_rsi.min() + 1e-9 and
                        last5_rsi.iloc[-1] > last5_rsi.iloc[0]):
                        candidates.append(("⚠️ Reversal (dywergencja RSI – bycza)", 30))
            except Exception:
                pass

        # --- Kontynuacja trendu ---
        if has_all and not np.isnan(adx) and adx > 22:
            if trend == "Uptrend" and price > ma_fast:
                candidates.append(("📈 Kontynuacja wzrostu", 25))
            elif trend == "Downtrend" and price < ma_fast:
                candidates.append(("📉 Kontynuacja spadku", 25))

        # --- Pullback ---
        if has_all and not np.isnan(adx) and adx > 22:
            if trend == "Uptrend" and ma_slow < price < ma_fast * 1.02:
                candidates.append(("🔄 Pullback (cofnięcie do MA w trendzie wzrostowym)", 20))
            elif trend == "Downtrend" and ma_fast * 0.98 < price < ma_slow:
                candidates.append(("🔄 Pullback (cofnięcie do MA w trendzie spadkowym)", 20))

        # --- Konsolidacja ---
        if trend == "Sideways" or (not np.isnan(adx) and adx < 18):
            if not np.isnan(vol) and vol < 0.015:
                candidates.append(("⏸️ Konsolidacja / brak kierunku", 10))

        # --- Domyślny ---
        if not has_all:
            candidates.append(("❓ Nieznany (brak danych)", 0))
        elif not candidates:
            if trend == "Uptrend":
                candidates.append(("📈 Ruch wzrostowy (bez sygnału specjalnego)", 15))
            elif trend == "Downtrend":
                candidates.append(("📉 Ruch spadkowy (bez sygnału specjalnego)", 15))
            else:
                candidates.append(("➡️ Ruch boczny (bez sygnału specjalnego)", 5))

        candidates.sort(key=lambda x: -x[1])
        best_label, best_weight = candidates[0]
        short_desc = best_label.split("(")[0].strip() if "(" in best_label else best_label
        return best_label, short_desc, best_weight

    # ------------------ DASHBOARD PORFELA ------------------
    def render_dashboard():
        st.title("🏠 Dashboard portfela")
        portfolio = _load_portfolio()
        last_scan = _load_last_scan()
        user_tickers = _load_user_tickers()

        # --- Sekcja zarządzania portfelem ---
        with st.expander("💼 **Mój portfel – dodaj/edytuj akcje**", expanded=True):
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            new_ticker = col1.text_input("Ticker", placeholder="np. STX.WA", key="pf_ticker", label_visibility="collapsed")
            new_shares = col2.number_input("Liczba akcji", min_value=0.0, step=1.0, format="%g", key="pf_shares", label_visibility="collapsed")
            new_price = col3.number_input("Średnia cena zakupu", min_value=0.0, step=0.01, format="%f", key="pf_price", label_visibility="collapsed")
            if col4.button("➕ Dodaj", use_container_width=True):
                if new_ticker and new_shares > 0 and new_price > 0:
                    t = new_ticker.strip().upper()
                    found = False
                    for item in portfolio:
                        if item["ticker"] == t:
                            item["shares"] += new_shares
                            item["avg_price"] = new_price
                            found = True
                            break
                    if not found:
                        portfolio.append({"ticker": t, "shares": new_shares, "avg_price": new_price})
                    _save_portfolio(portfolio)
                    st.rerun()

        # --- Tabela portfela ---
            if portfolio:
                st.divider()
                st.markdown("**📋 Twoje pozycje:**")

                # Nagłówek tabeli
                st.markdown("""
                <div style="display:flex; align-items:center; gap:10px; padding:6px 0; font-size:13px; color:#94a3b8; border-bottom:2px solid #334155;">
                    <div style="flex:3;"><b>Spółka</b></div>
                    <div style="flex:2;"><b>Akcje</b></div>
                    <div style="flex:2;"><b>Śr. cena</b></div>
                    <div style="flex:2;"><b>Kurs</b></div>
                    <div style="flex:2;"><b>Wartość</b></div>
                    <div style="flex:2;"><b>Zysk/Strata</b></div>
                    <div style="flex:1;"></div>
                </div>
                """, unsafe_allow_html=True)

                total_value = 0
                total_cost = 0
                for item in portfolio[:25]:
                    t = item["ticker"]; shares = item["shares"]; avg_price = item["avg_price"]
                    price_live = None; change_pct = 0

                    # Pobierz aktualną cenę z yfinance (próbuj różne okresy)
                    for period_try in ["1mo", "3mo", "6mo"]:
                        try:
                            d = yf.download(t, period=period_try, interval="1d", progress=False)
                            if not d.empty:
                                c = d["Close"].iloc[:, 0] if isinstance(d.columns, pd.MultiIndex) else d["Close"]
                                price_live = to_scalar(c.iloc[-1])
                                if len(c) > 1:
                                    change_pct = (price_live - to_scalar(c.iloc[-2])) / (to_scalar(c.iloc[-2]) + 1e-9) * 100
                                break
                        except: continue

                    # Fallback: last_scan → avg_price
                    if price_live is None or np.isnan(price_live):
                        cached_price = last_scan.get(t, {}).get("price", None)
                        if cached_price is not None and not np.isnan(cached_price):
                            price_live = cached_price
                        else:
                            price_live = avg_price
                        change_pct = 0

                    cur_val = price_live * shares
                    cost_val = avg_price * shares
                    pnl = cur_val - cost_val
                    pnl_pct = (pnl / cost_val) * 100 if cost_val > 0 else 0
                    total_value += cur_val; total_cost += cost_val

                    # Kolory
                    pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
                    pnl_arrow = "📈" if pnl >= 0 else "📉"
                    change_arrow = ("<span style='color:#22c55e'>▲</span>" if change_pct > 0
                                   else "<span style='color:#ef4444'>▼</span>" if change_pct < 0
                                   else "")

                    # HTML dla każdego wiersza
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px solid #1e293b; font-size:14px;">
                        <div style="flex:3;"><b>{t}</b></div>
                        <div style="flex:2;">{int(shares) if shares == int(shares) else f'{shares:.1f}'} szt.</div>
                        <div style="flex:2;">{fmt_price_short(avg_price)}</div>
                        <div style="flex:2;">{fmt_price_short(price_live)} {change_arrow}</div>
                        <div style="flex:2;">{fmt_price_short(cur_val)}</div>
                        <div style="flex:2;color:{pnl_color};font-weight:bold;">{pnl_arrow} {fmt_price_short(abs(pnl))} ({pnl_pct:+.1f}%)</div>
                        {"<div style='flex:1;'><span style='cursor:pointer;' onclick=''>🗑️</span></div>"}
                    </div>
                    """, unsafe_allow_html=True)

                    # Przycisk usuwania (potrzebuje osobnego wiersza by działał)
                    if st.button("🗑️ Usuń " + t, key="del_" + t):
                        portfolio = [p for p in portfolio if p["ticker"] != t]
                        _save_portfolio(portfolio)
                        st.rerun()

                st.divider()
                total_pnl = total_value - total_cost
                tpc = "#22c55e" if total_pnl >= 0 else "#ef4444"
                st.markdown(f"""
                <div style="background:#1e293b; padding:14px; border-radius:10px; border:1px solid #334155;">
                    <b>💰 Podsumowanie</b><br>
                    Wartość: <b>{fmt_price_short(total_value)}</b> •
                    Koszt: <b>{fmt_price_short(total_cost)}</b> •
                    <span style="color:{tpc};font-size:17px;">{total_pnl:+.2f} ({total_pnl/total_cost*100:+.1f}%)</span>
                </div>
                """, unsafe_allow_html=True)

        # --- Obserwowane ---
        if user_tickers:
            st.divider()
            st.markdown("**👀 Obserwowane (" + str(len(user_tickers)) + " spółek):**")
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=60 * 1000, key="dash_refresh")
            ch = st.columns([2, 1, 1, 1, 1, 1])
            ch[0].markdown("**Ticker**"); ch[1].markdown("**Cena**"); ch[2].markdown("**Zmiana**"); ch[3].markdown("**Score**"); ch[4].markdown("**Trend**"); ch[5].markdown("**Ruch**")
            for t in user_tickers:
                c = last_scan.get(t, {}); pl = None; cp = 0
                try:
                    d = yf.download(t, period="1mo", interval="1d", progress=False)
                    if not d.empty:
                        cl = d["Close"].iloc[:, 0] if isinstance(d.columns, pd.MultiIndex) else d["Close"]
                        pl = to_scalar(cl.iloc[-1])
                        if len(cl) > 1: cp = (pl - to_scalar(cl.iloc[-2])) / (to_scalar(cl.iloc[-2]) + 1e-9) * 100
                except: pass
                if pl is None or np.isnan(pl): pl = c.get("price", None); cp = 0
                ps = fmt_price_short(pl) if pl is not None and not np.isnan(pl) else "?"
                cs = f"{cp:+.2f}%" if cp != 0 else "0.00%"
                cc = "#22c55e" if cp > 0 else "#ef4444" if cp < 0 else "#888"
                sc = c.get("scoring"); tr = c.get("trend", "?"); ru = c.get("ruch", "?")
                bg = "🟢" if sc is not None and sc >= 70 else "🟡" if sc is not None and sc >= 40 else "🔴"
                cr = st.columns([2, 1, 1, 1, 1, 1])
                cr[0].write("**" + bg + " " + t + "**")
                cr[1].write(ps)
                cr[2].write(f"<span style='color:{cc}'>{cs}</span>", unsafe_allow_html=True)
                cr[3].write(f"{sc if sc is not None else '?'}/100")
                cr[4].write(tr); cr[5].write(ru)

            if last_scan:
                st.divider()
                st.markdown("**📋 Podsumowanie dla Telegram:**")
                tg = [f"<b>🏠 Dashboard – {len(user_tickers)} spółek</b>"]
                for t in user_tickers:
                    d = last_scan.get(t, {}); p = d.get("price", "?")
                    tg.append(f"• {t} – {fmt_price(p) if p != '?' else '?'} | {d.get('scoring','?')}/100 | {d.get('trend','?')} | {d.get('ruch','?')}")
                st.code("\n".join(tg), language="text")
        elif not portfolio:
            st.info("📌 Dodaj spółki do portfela powyżej lub zapisz tickery w skanerze.")

    # ------------------ ANALIZA MULTI-INTERWAŁ ------------------
    def analyze_multi_tf(ticker: str):
        """Pobiera dane dla 1d, 1h, 15m i zwraca DataFrame z wskaźnikami."""
        configs = [
            ("1d (długi)", "3mo", "1d"),
            ("1h (średni)", "1mo", "1h"),
            ("15m (krótki)", "5d", "15m"),
        ]
        rows = []
        for label, period, interval in configs:
            try:
                d = yf.download(ticker, period=period, interval=interval, progress=False)
                if d.empty or len(d) < 30:
                    rows.append({"Interwał": label, "Okres": period, "Cena": None, "Trend": "Brak danych",
                                 "RSI": None, "ADX": None, "RVOL": None, "Sygnał": "N/A", "Scoring": None,
                                 "Ruch": "?"})
                    continue
                if isinstance(d.columns, pd.MultiIndex):
                    close = d["Close"].iloc[:, 0]
                    volume = d["Volume"].iloc[:, 0]
                else:
                    close = d["Close"]
                    volume = d["Volume"]
                price = to_scalar(close.iloc[-1])
                ind = compute_indicators(close, volume)
                sentiment, _, _ = fetch_news_sentiment(ticker)
                signal, _ = generate_signal(price, ind)
                scoring = compute_scoring_pro(ind, sentiment)
                _, movement_short, _ = classify_movement(close, price, ind)
                rows.append({
                    "Interwał": label,
                    "Okres": period,
                    "Cena": price,
                    "Trend": ind["trend"],
                    "RSI": ind["rsi"],
                    "ADX": ind["adx"],
                    "RVOL": ind["rvol"],
                    "Sygnał": signal,
                    "Scoring": scoring,
                    "Ruch": movement_short
                })
            except:
                rows.append({"Interwał": label, "Okres": period, "Cena": None, "Trend": "Błąd",
                             "RSI": None, "ADX": None, "RVOL": None, "Sygnał": "N/A",
                             "Scoring": None, "Ruch": "?"})
        return pd.DataFrame(rows)

    # ------------------ MODUŁ: TRADING ------------------
    def render_trading():
        st.title("📈 Kombajn tradingowy – pełny panel")
        ticker = st.text_input("Ticker (np. AAPL, MSFT, STX.WA):", "",
                               placeholder="Wpisz ticker, np. STX.WA")
        col1, col2, col3 = st.columns([2, 2, 1])
        period = col1.selectbox("Okres:", ["5d", "1mo", "3mo", "6mo", "1y"], index=1)
        interval = col2.selectbox("Interwał:", ["15m", "30m", "1h", "1d"], index=3)
        multi_tf = col3.checkbox("🔬 Multi-TF", value=False,
                                 help="Analiza 1d + 1h + 15m jednocześnie")

        if st.button("Pobierz dane i policz sygnały", use_container_width=True):
            try:
                with st.spinner(f"Pobieram dane dla {ticker}..."):
                    data = yf.download(ticker, period=period, interval=interval, progress=False)
                    if data.empty:
                        st.error("Brak danych.")
                        return
                    if len(data) < 60:
                        st.info("Za mało danych, używam 6mo/1d")
                        data = yf.download(ticker, period="6mo", interval="1d", progress=False)
                        if data.empty:
                            st.error("Brak danych.")
                            return

                    if isinstance(data.columns, pd.MultiIndex):
                        close = data["Close"].iloc[:, 0]
                        open_ = data["Open"].iloc[:, 0]
                        high = data["High"].iloc[:, 0]
                        low = data["Low"].iloc[:, 0]
                        volume = data["Volume"].iloc[:, 0]
                    else:
                        close, open_, high, low, volume = data["Close"], data["Open"], data["High"], data["Low"], data["Volume"]

                    ind = compute_indicators(close, volume)
                    price = to_scalar(close.iloc[-1])

                    # Wykres
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(x=data.index, open=open_, high=high, low=low, close=close, name="Świece"))
                    if not ind["upper_bb"].isna().all():
                        fig.add_trace(go.Scatter(x=data.index, y=ind["upper_bb"], line=dict(color="rgba(34,197,94,0.5)", width=1), name="BB górna"))
                        fig.add_trace(go.Scatter(x=data.index, y=ind["lower_bb"], line=dict(color="rgba(239,68,68,0.5)", width=1), name="BB dolna"))
                    fig.update_layout(height=500, title=f"{ticker} - {period} ({interval})", paper_bgcolor="#020617", plot_bgcolor="#020617", font=dict(color="#E5E7EB"))
                    st.plotly_chart(fig, use_container_width=True)

                    sentiment, titles, _ = fetch_news_sentiment(ticker)
                    signal, explanation = generate_signal(price, ind)
                    scoring = compute_scoring_pro(ind, sentiment)
                    movement_label, movement_short, movement_weight = classify_movement(close, price, ind)

                    st.subheader("🤖 Analiza")
                    c1, c2 = st.columns(2)
                    c1.metric("Cena", fmt_price_short(price))
                    c1.metric("RSI", f"{ind['rsi']:.1f}" if not np.isnan(ind['rsi']) else "Brak")
                    c1.metric("Trend", ind['trend'])
                    c1.metric("Sygnał", signal)
                    c2.metric("Scoring", f"{scoring}/100")
                    c2.metric("ADX", f"{ind['adx']:.1f}" if not np.isnan(ind['adx']) else "Brak")
                    c2.metric("RVOL", f"{ind['rvol']:.2f}" if not np.isnan(ind['rvol']) else "Brak")
                    c2.metric("Sentyment", sentiment)

                    st.info(f"🧠 **Typ ruchu:** {movement_label} (waga: {movement_weight}/50)")

                    with st.expander("📊 Wszystkie wskaźniki"):
                        for k, v in ind.items():
                            if isinstance(v, pd.Series):
                                continue
                            try:
                                if not np.isnan(v):
                                    val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
                                    st.write(f"**{k}:** {val_str}")
                            except TypeError:
                                st.write(f"**{k}:** {v}")

                    st.markdown("**Uzasadnienie:**")
                    st.markdown(explanation)
                    st.subheader("📰 News")
                    st.write(f"Sentyment: {sentiment}")
                    for t in titles:
                        st.write(f"- {t}")

                    st.session_state["last_analysis"] = {
                        "ticker": ticker, "price": price, "indicators": ind,
                        "signal": signal, "explanation": explanation,
                        "sentiment": sentiment, "news_titles": titles,
                        "scoring": scoring, "period": period, "interval": interval,
                        "movement_label": movement_label, "movement_short": movement_short
                    }
                    st.success("✅ Analiza zapisana.")

                    # --- Analiza multi-interwał ---
                    if multi_tf:
                        st.divider()
                        st.subheader("🔬 Analiza multi-interwał (1d + 1h + 15m)")
                        with st.spinner("Pobieram dane dla 1d, 1h, 15m..."):
                            df_multi = analyze_multi_tf(ticker)
                        if df_multi is not None and not df_multi.empty:
                            # Tabela
                            cols_m = st.columns([2, 1, 1, 1, 1, 1, 1, 1, 1])
                            cols_m[0].markdown("**Interwał**")
                            cols_m[1].markdown("**Cena**")
                            cols_m[2].markdown("**Trend**")
                            cols_m[3].markdown("**RSI**")
                            cols_m[4].markdown("**ADX**")
                            cols_m[5].markdown("**RVOL**")
                            cols_m[6].markdown("**Ruch**")
                            cols_m[7].markdown("**Sygnał**")
                            cols_m[8].markdown("**Score**")

                            trends = []
                            signals = []
                            for _, r in df_multi.iterrows():
                                color_row = ""
                                if r["Sygnał"] == "BUY": color_row = "rgba(34,197,94,0.15)"
                                elif r["Sygnał"] == "SELL": color_row = "rgba(239,68,68,0.15)"
                                c = st.columns([2, 1, 1, 1, 1, 1, 1, 1, 1])
                                c[0].write(f"**{r['Interwał']}**")
                                c[1].write(fmt_price_short(r["Cena"]) if r["Cena"] is not None and not np.isnan(r["Cena"]) else "?")
                                tr = r["Trend"]
                                em = "🟢" if tr == "Uptrend" else ("🔴" if tr == "Downtrend" else "⚪")
                                c[2].write(f"{em} {tr}")
                                c[3].write(f"{r['RSI']:.1f}" if r["RSI"] is not None and not np.isnan(r["RSI"]) else "?")
                                c[4].write(f"{r['ADX']:.1f}" if r["ADX"] is not None and not np.isnan(r["ADX"]) else "?")
                                c[5].write(f"{r['RVOL']:.2f}" if r["RVOL"] is not None and not np.isnan(r["RVOL"]) else "?")
                                c[6].write(r["Ruch"])
                                c[7].write(f"**{r['Sygnał']}**" if r["Sygnał"] in ("BUY", "SELL") else r["Sygnał"])
                                c[8].write(f"{int(r['Scoring'])}/100" if r["Scoring"] is not None and not np.isnan(r["Scoring"]) else "?")
                                trends.append(tr)
                                signals.append(r["Sygnał"])

                            # Konsensus
                            st.divider()
                            buy_count = signals.count("BUY")
                            sell_count = signals.count("SELL")
                            hold_count = signals.count("HOLD")
                            uptrends = trends.count("Uptrend")
                            downtrends = trends.count("Downtrend")

                            verdict_parts = []
                            if uptrends >= 2:
                                verdict_parts.append("📈 Trend zgodny: **WZROSTOWY**")
                            elif downtrends >= 2:
                                verdict_parts.append("📉 Trend zgodny: **SPADKOWY**")
                            else:
                                verdict_parts.append("➡️ Trend mieszany")

                            if buy_count >= 2:
                                verdict_parts.append(f"🟢 Sygnały: **{buy_count}/3 BUY** 🔥")
                            elif sell_count >= 2:
                                verdict_parts.append(f"🔴 Sygnały: **{sell_count}/3 SELL** ⚠️")
                            else:
                                verdict_parts.append(f"⏸️ Sygnały: BUY {buy_count} / SELL {sell_count} / HOLD {hold_count}")

                            st.info(" | ".join(verdict_parts))

                            # Telegram z multi-TF
                            if st.session_state.get("telegram_enabled", True) and (buy_count >= 2 or sell_count >= 2):
                                tg_tf_lines = [
                                    f"<b>🔬 Multi-TF {ticker}</b>",
                                    f"📊 {' | '.join(verdict_parts)}"
                                ]
                                for _, r in df_multi.iterrows():
                                    tg_tf_lines.append(f"• {r['Interwał']}: {r['Trend']} | RSI:{r['RSI']:.1f if r['RSI'] is not None and not np.isnan(r['RSI']) else '?'} | {r['Sygnał']}")
                                send_telegram("\n".join(tg_tf_lines))

                    if st.session_state.get("telegram_enabled", True) and signal in ("BUY", "SELL"):
                        tg_msg = (
                            f"🚀 <b>{ticker}</b> – sygnał: <b>{signal}</b>\n"
                            f"{movement_label}\n"
                            f"💰 Cena: {fmt_price(price)} | Scoring: {scoring}/100\n"
                            f"📈 Trend: {ind['trend']} | RSI: {ind['rsi']:.1f}\n"
                            f"📊 ADX: {ind['adx']:.1f} | RVOL: {ind['rvol']:.2f}\n"
                            f"📰 Sentyment: {sentiment}\n"
                            f"📅 {period} ({interval})"
                        )
                        if send_telegram(tg_msg):
                            st.toast("📲 Telegram wysłany", icon="✅")
                        else:
                            st.toast("📲 Telegram: brak tokena lub błąd", icon="⚠️")
            except Exception as e:
                st.error(f"❌ Błąd: {str(e)}")

    # ------------------ MODUŁ: SKANER ------------------
    def render_scanner():
        st.title("🧪 Skaner spółek – własne tickery → TOP N")

        # --- Auto-refresh ---
        auto_interval = st.session_state.get("auto_scan_interval", 0)
        is_auto_scan = False
        if auto_interval > 0:
            # odśwież stronę co N minut (st_autorefresh w ms)
            st_autorefresh(interval=auto_interval * 60 * 1000, key="autoscan")
            # sprawdź czy to auto-odświeżenie (brak kliknięcia przycisku)
            last_auto = st.session_state.get("last_auto_scan_time", 0)
            now = time.time()
            if now - last_auto > auto_interval * 60 - 5 and st.session_state.get("auto_scan_trigger", False):
                is_auto_scan = True
            st.session_state["auto_scan_trigger"] = True

        _saved_tickers_list = _load_user_tickers()
        _default_tickers_str = " ".join(_saved_tickers_list)
        tickers_text = st.text_area("Tickery (oddzielone spacją, przecinkiem lub nową linią):",
                                    _default_tickers_str, height=120,
                                    placeholder="Wpisz tickery, np. STX.WA, ACP.WA, TUP.WA")
        max_to_show = st.slider("TOP N:", 5, 20, 10)

        if is_auto_scan and _saved_tickers_list:
            st.info(f"⏰ Auto-skaner aktywny (co {auto_interval} min) – automatycznie skanuję: {' '.join(_saved_tickers_list[:8])}" +
                    ("..." if len(_saved_tickers_list) > 8 else ""))

        # --- Decyzja: czy uruchomić skanowanie ---
        _should_scan = False
        _auto_mode = False
        if st.button("🔍 Skanuj", use_container_width=True):
            _should_scan = True
        elif is_auto_scan and _saved_tickers_list:
            # auto-skan: użyj zapisanych tickerów
            _should_scan = True
            _auto_mode = True
            tickers_text = _default_tickers_str

        if _should_scan:
            raw = re.split(r'[,\s\n]+', tickers_text)
            tickers = list(dict.fromkeys([t.strip().upper() for t in raw if t.strip()]))
            if not tickers:
                st.error("Brak tickerów.")
                if not _auto_mode:
                    return

            results = []
            progress_bar = st.progress(0) if not _auto_mode else st.empty()
            status = st.empty()
            for i, ticker in enumerate(tickers):
                if not _auto_mode:
                    status.text(f"Skanuję: {ticker} ({i+1}/{len(tickers)})")
                    progress_bar.progress((i+1)/len(tickers))
                try:
                    data = yf.download(ticker, period="6mo", interval="1d", progress=False)
                    if data.empty or len(data) < 30:
                        continue
                    if isinstance(data.columns, pd.MultiIndex):
                        close = data["Close"].iloc[:, 0]
                        volume = data["Volume"].iloc[:, 0]
                    else:
                        close, volume = data["Close"], data["Volume"]
                    ind = compute_indicators(close, volume)
                    price = to_scalar(close.iloc[-1])
                    sentiment, _, _ = fetch_news_sentiment(ticker)
                    scoring = compute_scoring_pro(ind, sentiment)
                    _, movement_short, _ = classify_movement(close, price, ind)
                    results.append({
                        "Ticker": ticker, "Cena": price, "Trend": ind["trend"],
                        "RSI": ind["rsi"], "ADX": ind["adx"], "RVOL": ind["rvol"],
                        "Sentyment": sentiment, "Scoring": scoring,
                        "Ruch": movement_short
                    })
                except:
                    continue
            if not _auto_mode:
                progress_bar.empty()
            status.empty()

            # --- Zapisz tickery do state.json ---
            _save_user_tickers(tickers)

            # --- Sprawdź alerty cenowe ---
            try:
                alert_price_data = {}
                for r in results:
                    alert_price_data[r["Ticker"]] = {"price": r["Cena"]}
                check_alerts(results, alert_price_data)
            except Exception:
                pass

            if not results:
                st.error("Brak wyników.")
                return

            df = pd.DataFrame(results).sort_values("Scoring", ascending=False).head(max_to_show)
            st.subheader(f"🏆 TOP {len(df)} spółek")

            for _, row in df.iterrows():
                score = row["Scoring"]
                if score >= 70:
                    color, border, label = "rgba(34,197,94,0.25)", "2px solid #22c55e", "🔥 Mocny sygnał"
                elif score >= 40:
                    color, border, label = "rgba(251,146,60,0.25)", "2px solid #fb923c", "📊 Obserwacja"
                else:
                    color, border, label = "rgba(239,68,68,0.25)", "2px solid #ef4444", "⚠️ Słaby sygnał"
                st.markdown(f"""
                <div style="background-color:{color}; padding:15px; border-radius:10px; margin-bottom:10px; border:{border};">
                    <b style="font-size:18px;">{row['Ticker']}</b><br>
                    Cena: {fmt_price(row['Cena'])} | Trend: {row['Trend']} | RSI: {row['RSI']:.1f}<br>
                    ADX: {row['ADX']:.1f} | RVOL: {row['RVOL']:.2f} | Sentyment: {row['Sentyment']}<br>
                    🧠 Ruch: {row['Ruch']}<br>
                    <b>Scoring: {score}/100</b> — {label}
                </div>
                """, unsafe_allow_html=True)

            if st.button("💾 Zapisz CSV"):
                st.download_button("Pobierz", df.to_csv(index=False), "skaner.csv", "text/csv")

            # --- Telegram z detekcją zmian ---
            if st.session_state.get("telegram_enabled", True):
                last_scan = _load_last_scan()
                changes = []
                for _, r in df.iterrows():
                    ticker = r["Ticker"]
                    price_now = float(r["Cena"])
                    vol_now = float(r["RVOL"])
                    old = last_scan.get(ticker, {})
                    old_price = old.get("price", None)
                    old_vol = old.get("rvol", None)
                    # porównaj z progiem (1% zmiany ceny lub 2% zmiany RVOL)
                    price_changed = old_price is None or (
                        old_price != 0 and abs(price_now - old_price) / max(abs(old_price), 0.0001) > 0.01
                    )
                    vol_changed = old_vol is None or (
                        old_vol != 0 and abs(vol_now - old_vol) / max(abs(vol_now), 0.0001) > 0.02
                    )
                    if price_changed or vol_changed:
                        changes.append(ticker)

                if changes:
                    top3 = df.head(3)
                    tg_lines = [f"<b>📊 SKANER – TOP {len(df)} spółek (zmiana: {', '.join(changes[:5])})</b>"]
                    for _, r in top3.iterrows():
                        tg_lines.append(
                            f"• {r['Ticker']} – {fmt_price(r['Cena'])} | {r['Scoring']}/100 | {r['Trend']} | {r['Ruch']}"
                        )
                    tg_lines.append(f"📅 Pełna lista: {len(df)} spółek")
                    if send_telegram("\n".join(tg_lines)):
                        st.toast("📲 Telegram wysłany (wykryto zmiany)", icon="✅")
                else:
                    st.toast("📲 Telegram: brak zmian – pominięto", icon="ℹ️")

                # Zapisz bieżące wyniki jako last_scan
                scan_data = {}
                for _, r in df.iterrows():
                    scan_data[r["Ticker"]] = {
                        "price": float(r["Cena"]),
                        "rvol": float(r["RVOL"]),
                        "scoring": int(r["Scoring"]),
                        "trend": str(r["Trend"]),
                        "ruch": str(r["Ruch"]),
                        "rsi": float(r["RSI"]) if not np.isnan(r["RSI"]) else None
                    }
                _save_last_scan(scan_data)

            # --- Aktualizuj znacznik czasu auto-skanu ---
            if not _auto_mode:
                st.session_state["last_auto_scan_time"] = time.time()
                st.session_state["auto_scan_trigger"] = False
            else:
                st.session_state["last_auto_scan_time"] = time.time()
                st.rerun()  # wymuś odświeżenie by zaktualizować widok

    # ------------------ ALERTY CENOWE ------------------
    def check_alerts(tickers_data: list, price_data: dict):
        """Sprawdza alerty i wysyła Telegram dla trafionych."""
        alerts = _load_alerts()
        if not alerts:
            return
        triggered = []
        for t in alerts:
            a = alerts[t]
            target_type = a.get("type", "BUY")
            target_price = a.get("price", 0)
            active = a.get("active", True)
            if not active:
                continue
            price_now = price_data.get(t, {}).get("price", None)
            if price_now is None or np.isnan(price_now):
                continue
            hit = False
            if target_type == "BUY_TARGET" and price_now <= target_price:
                hit = True
            elif target_type == "SELL_TARGET" and price_now >= target_price:
                hit = True
            elif target_type == "STOP_LOSS" and price_now <= target_price:
                hit = True
            if hit:
                triggered.append((t, target_type, target_price, price_now))
                alerts[t]["active"] = False  # deaktywuj po trafieniu
        if triggered:
            _save_alerts(alerts)
            lines = [f"<b>🔔 ALERTY – trafione:</b>"]
            for t, typ, tp, pn in triggered:
                emoji = "🟢" if "BUY" in typ else ("🔴" if "STOP" in typ else "🟡")
                lines.append(f"{emoji} {t}: {typ} @ {fmt_price(tp)} → teraz {fmt_price(pn)}")
            msg = "\n".join(lines)
            if st.session_state.get("telegram_enabled", True):
                send_telegram(msg)

    def render_alerts():
        st.title("🔔 Alerty cenowe")
        st.caption("Ustaw cele cenowe – gdy cena osiągnie target, dostaniesz powiadomienie Telegram")
        tickers = _load_user_tickers()
        if not tickers:
            st.info("📌 Najpierw dodaj tickery w skanerze.")
            return

        alerts = _load_alerts()
        col_ticker, col_type, col_price, col_btn = st.columns([2, 2, 2, 1])
        ticker_sel = col_ticker.selectbox("Spółka", tickers, key="alert_ticker")
        type_sel = col_type.selectbox("Typ", ["BUY_TARGET", "SELL_TARGET", "STOP_LOSS"], key="alert_type")
        price_inp = col_price.number_input("Cena docelowa", min_value=0.0, step=0.01, format="%f", key="alert_price")
        if col_btn.button("➕ Dodaj", use_container_width=True):
            if ticker_sel and price_inp > 0:
                alerts[ticker_sel] = {"type": type_sel, "price": price_inp, "active": True}
                _save_alerts(alerts)
                st.toast(f"✅ Alert {type_sel} dla {ticker_sel} @ {fmt_price(price_inp)}", icon="🔔")

        st.divider()
        st.markdown("**Aktywne alerty:**")
        if not alerts:
            st.info("Brak alertów. Dodaj nowy powyżej.")
        else:
            to_delete = []
            for t, a in alerts.items():
                active = a.get("active", True)
                typ = a.get("type", "?")
                price = a.get("price", 0)
                if not active:
                    continue
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                c1.write(f"**{t}**")
                c2.write(typ)
                c3.write(fmt_price(price))
                if c4.button("🗑️", key=f"del_{t}_{typ}_{price}"):
                    to_delete.append(t)
            for t in to_delete:
                if t in alerts:
                    del alerts[t]
                    _save_alerts(alerts)
                    st.rerun()

        st.divider()
        st.markdown("**Historia trafionych alertów:**")
        hit_any = False
        for t, a in alerts.items():
            if not a.get("active", True):
                hit_any = True
                typ = a.get("type", "?")
                price = a.get("price", 0)
                st.write(f"✅ {t} – {typ} @ {fmt_price(price)} (trafiony)")
        if not hit_any:
            st.caption("Brak trafionych alertów.")

    # ------------------ BACKTESTING SYGNAŁÓW ------------------
    def render_backtest():
        st.title("📊 Backtesting sygnałów")
        st.caption("Sprawdź, jak nasze sygnały sprawdziłyby się na historycznych danych")

        tickers = _load_user_tickers()
        if not tickers:
            st.info("📌 Najpierw dodaj tickery w skanerze.")
            return

        period_map = {"3 miesiące": "3mo", "6 miesięcy": "6mo", "1 rok": "1y"}
        period_sel = st.selectbox("Okres testu:", list(period_map.keys()), index=1)
        period = period_map[period_sel]

        if st.button("🔍 Uruchom backtest", use_container_width=True):
            results = []
            progress_bar = st.progress(0)
            status = st.empty()

            for i, ticker in enumerate(tickers):
                status.text(f"Testuję: {ticker} ({i+1}/{len(tickers)})")
                progress_bar.progress((i + 1) / len(tickers))

                try:
                    data = yf.download(ticker, period=period, interval="1d", progress=False)
                    if data.empty or len(data) < 30:
                        continue
                    if isinstance(data.columns, pd.MultiIndex):
                        close = data["Close"].iloc[:, 0]
                    else:
                        close = data["Close"]

                    # Symulacja sygnałów na historycznych danych
                    # Dzielimy dane na segmenty co 10 dni
                    window = 30
                    buy_hold_start = to_scalar(close.iloc[0])
                    buy_hold_end = to_scalar(close.iloc[-1])
                    buy_hold_return = (buy_hold_end - buy_hold_start) / (buy_hold_start + 1e-9) * 100

                    signal_trades = []
                    for start_idx in range(0, len(close) - window, window):
                        seg = close.iloc[start_idx:start_idx + window]
                        if len(seg) < window:
                            continue
                        price_now_sim = to_scalar(seg.iloc[-1])
                        # Oblicz wskaźniki dla tego okna
                        vol_seg = volume.iloc[start_idx:start_idx + window] if not isinstance(data.columns, pd.MultiIndex) else data["Volume"].iloc[:, 0].iloc[start_idx:start_idx + window]
                        ind_sim = compute_indicators(seg, vol_seg)
                        sig_sim, _ = generate_signal(price_now_sim, ind_sim)
                        if sig_sim == "BUY":
                            # kup na początku następnego okna, sprzedaj na końcu
                            next_start = start_idx + window
                            next_end = min(next_start + window, len(close))
                            if next_end > next_start:
                                buy_p = to_scalar(close.iloc[next_start])
                                sell_p = to_scalar(close.iloc[next_end - 1])
                                ret = (sell_p - buy_p) / (buy_p + 1e-9) * 100
                                signal_trades.append(ret)

                    if signal_trades:
                        avg_trade = sum(signal_trades) / len(signal_trades)
                        total_trades = len(signal_trades)
                        win_rate = sum(1 for r in signal_trades if r > 0) / total_trades * 100
                    else:
                        avg_trade = 0
                        total_trades = 0
                        win_rate = 0

                    results.append({
                        "Ticker": ticker,
                        "BH_Return": buy_hold_return,
                        "Signal_Return": avg_trade * max(1, total_trades // 2),  # approx cumulative
                        "Avg_Trade%": avg_trade,
                        "Win_Rate%": win_rate,
                        "Total_Trades": total_trades,
                        "BH_vs_Signal": avg_trade * max(1, total_trades // 2) - buy_hold_return
                    })
                except:
                    continue

            progress_bar.empty()
            status.empty()

            if not results:
                st.error("Brak wyników.")
                return

            df = pd.DataFrame(results)
            df = df.sort_values("Avg_Trade%", ascending=False)

            st.subheader(f"📊 Wyniki backtestu ({period_sel})")

            for _, r in df.iterrows():
                color = "rgba(34,197,94,0.2)" if r["Avg_Trade%"] > 0 else "rgba(239,68,68,0.2)"
                border = "2px solid #22c55e" if r["Avg_Trade%"] > 0 else "2px solid #ef4444"
                st.markdown(f"""
                <div style="background:{color}; padding:12px; border-radius:10px; margin-bottom:8px; border:{border};">
                    <b style="font-size:16px;">{r['Ticker']}</b><br>
                    📈 Kup i trzymaj: <b>{r['BH_Return']:+.2f}%</b><br>
                    🎯 Sygnały: <b>{r['Avg_Trade%']:+.2f}% średnio</b> ({"+" if r["Avg_Trade%"] > 0 else ""}{r['Avg_Trade%']:.2f}%)<br>
                    ✅ Win rate: {r['Win_Rate%']:.0f}% | Liczba transakcji: {r['Total_Trades']}<br>
                    <span style="color:{"#22c55e" if r["BH_vs_Signal"] > 0 else "#ef4444"}">
                    📊 Sygnały vs Kup-Trzymaj: <b>{r['BH_vs_Signal']:+.2f}%</b></span>
                </div>
                """, unsafe_allow_html=True)

            # Zapis do state.json
            backtest_data = {}
            for _, r in df.iterrows():
                backtest_data[r["Ticker"]] = {
                    "bh": round(r["BH_Return"], 2),
                    "signal": round(r["Avg_Trade%"], 2),
                    "winrate": round(r["Win_Rate%"], 1),
                    "trades": int(r["Total_Trades"])
                }
            _save_backtest_results(backtest_data)

            if st.button("💾 Zapisz CSV"):
                st.download_button("Pobierz CSV", df.to_csv(index=False), f"backtest_{period}.csv", "text/csv")

            # Podsumowanie
            avg_bh = df["BH_Return"].mean()
            avg_sig = df["Avg_Trade%"].mean()
            st.divider()
            if avg_sig > avg_bh:
                st.success(f"🏆 **Sygnały średnio lepsze od Kup-Trzymaj o {avg_sig - avg_bh:+.2f}%**")
            else:
                st.info(f"📊 Kup-Trzymaj lepsze o {avg_bh - avg_sig:+.2f}% – sygnały wymagają optymalizacji")

    # ------------------ MODUŁ: CZAT AI ------------------
    def tavily_research(tavily_key, ticker, question):
        if not tavily_key:
            return "Brak klucza Tavily.", False
        queries = [question]
        if ticker:
            queries.extend([f"{ticker} company profile", f"{ticker} stock news", f"{ticker} analyst ratings"])
        all_answers, all_results = [], []
        for q in queries[:3]:
            try:
                resp = requests.post("https://api.tavily.com/search",
                                     headers={"Authorization": f"Bearer {tavily_key}"},
                                     json={"query": q, "topic": "finance", "max_results": 3,
                                           "include_answer": True, "include_raw_content": False},
                                     timeout=15)
                if resp.status_code == 200:
                    j = resp.json()
                    if j.get("answer"): all_answers.append(j["answer"])
                    all_results.extend(j.get("results", []))
            except:
                continue
        bullets = []
        for item in all_results[:5]:
            title, url = item.get("title", ""), item.get("url", "")
            if title or url:
                bullets.append(f"- {title} ({url})")
        merged = "\n\n".join(all_answers)
        research = ""
        if merged: research += f"Podsumowanie Tavily:\n{merged}\n\n"
        if bullets: research += "Źródła:\n" + "\n".join(bullets)
        return research if research else "Brak danych z Tavily.", bool(research)

    def render_ai_chat():
        st.title("🤖 Czat AI – Analityk finansowy")
        st.caption("Zero zgadywania – tylko dane z Trading Engine + Tavily.")

        if "OPENAI_API_KEY" not in st.secrets:
            st.error("❌ Brak OPENAI_API_KEY w secrets.toml")
            return
        if "TAVILY_API_KEY" not in st.secrets:
            st.error("❌ Brak TAVILY_API_KEY w secrets.toml")
            return

        openai_key = st.secrets["OPENAI_API_KEY"]
        tavily_key = st.secrets["TAVILY_API_KEY"]

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        st.markdown("### Historia rozmowy")
        for sender, msg in st.session_state.chat_history:
            st.markdown(f"**{sender}:** {msg}")

        user_input = st.text_input("Twoja wiadomość:")
        col_send, col_clear = st.columns([3,1])
        send = col_send.button("Wyślij")
        clear = col_clear.button("Wyczyść")

        if clear:
            st.session_state.chat_history = []
            st.rerun()

        if not send or not user_input.strip():
            return

        question = user_input.strip()
        st.session_state.chat_history.append(("Ty", question))

        ticker = detect_ticker_from_text(question)
        if not ticker and "last_analysis" in st.session_state:
            ticker = st.session_state["last_analysis"].get("ticker")

        trading_data = st.session_state.get("last_analysis", None)
        trading_summary = "Brak danych z Trading Engine."
        if trading_data:
            ind = trading_data["indicators"]
            scoring = trading_data.get("scoring", compute_scoring_pro(ind, trading_data.get("sentiment")))
            lines = [f"Ticker: {trading_data['ticker']}"]
            if not np.isnan(trading_data["price"]): lines.append(f"Cena: {fmt_price(trading_data['price'])}")
            lines.append(f"Sygnał: {trading_data['signal']}")
            lines.append(f"Scoring: {scoring}")
            if not np.isnan(ind["rsi"]): lines.append(f"RSI: {ind['rsi']:.1f}")
            if not np.isnan(ind["ma_fast"]) and not np.isnan(ind["ma_slow"]):
                lines.append(f"MA10: {fmt_price(ind['ma_fast'])}, MA30: {fmt_price(ind['ma_slow'])}")
            lines.append(f"Trend: {ind['trend']}")
            if not np.isnan(ind["adx"]): lines.append(f"ADX: {ind['adx']:.1f}")
            if not np.isnan(ind["atr"]): lines.append(f"ATR: {ind['atr']:.2f}")
            if not np.isnan(ind["vol"]): lines.append(f"Volatility: {ind['vol']:.4f}")
            if not np.isnan(ind["volume"]): lines.append(f"Volume: {ind['volume']:.0f}")
            if not np.isnan(ind["rvol"]): lines.append(f"RVOL: {ind['rvol']:.2f}")
            if not np.isnan(ind["vwap"]): lines.append(f"VWAP: {ind['vwap']:.2f}")
            if not np.isnan(ind["roc"]): lines.append(f"ROC: {ind['roc']:.2f}%")
            if not np.isnan(ind["stoch_k"]) and not np.isnan(ind["stoch_d"]):
                lines.append(f"Stochastic: {ind['stoch_k']:.1f}/{ind['stoch_d']:.1f}")
            if not np.isnan(ind["sl"]): lines.append(f"SL: {ind['sl']:.2f}")
            if not np.isnan(ind["tp"]): lines.append(f"TP: {ind['tp']:.2f}")
            lines.append(f"Sentyment newsów: {trading_data['sentiment']}")
            if "movement_label" in trading_data:
                lines.append(f"Typ ruchu: {trading_data['movement_label']}")
            trading_summary = "\n".join(lines)

        # Sprawdź czy dane się zmieniły od ostatniego skanu – jeśli nie, pomiń Tavily i GPT
        skip_ai = False
        if ticker and trading_data is not None:
            try:
                price_val = float(trading_data["price"])
                rvol_val = float(trading_data["indicators"]["rvol"])
                if not _has_changed(ticker, price_val, rvol_val):
                    skip_ai = True
            except:
                pass

        if skip_ai:
            ai_msg = (
                f"📊 **{ticker} – brak znaczących zmian od ostatniego skanu.**\n\n"
                f"{trading_summary}\n\n"
                f"⚠️ Oszczędność: nie wysyłano zapytania do GPT/Tavily (brak zmian >1% ceny lub >2% wolumenu)."
            )
        else:
            research_text, has_fund = tavily_research(tavily_key, ticker, question)

            try:
                system_prompt = (
                    "Jesteś analitykiem finansowym. Masz dwa źródła: "
                    "1) Trading Engine (dane techniczne/wskaźniki) - zawsze dostępne, "
                    "2) Tavily (fundamenty/newsy/ratingi) - może być puste.\n\n"
                    "ZASADY:\n"
                    "- Jeśli Tavily zwrócił 'Brak danych' - analizuj WYŁĄCZNIE na podstawie Trading Engine.\n"
                    "- Nie mów 'brak danych' ani 'nie mam informacji' - po prostu analizuj technicznie.\n"
                    "- Podaj konkretne wartości: trend, RSI, ADX, typ ruchu, scoring i co oznaczają.\n"
                    "- Odpowiadaj po polsku, konkretnie, bez ogólników."
                )
                def ask_gpt():
                    return requests.post("https://api.openai.com/v1/chat/completions",
                                         headers={"Authorization": f"Bearer {openai_key}"},
                                         json={"model": "gpt-4.1", "messages": [
                                             {"role": "system", "content": system_prompt},
                                             {"role": "system", "content": f"Dane z Trading Engine:\n{trading_summary}"},
                                             {"role": "system", "content": f"Research Tavily:\n{research_text}"}
                                         ] + [{"role": "user" if s=="Ty" else "assistant", "content": c}
                                              for s,c in st.session_state.chat_history],
                                              "temperature": 0.1}, timeout=60)
                resp = ask_gpt()
                if resp.status_code != 200:
                    resp = ask_gpt()
                resp.raise_for_status()
                ai_msg = resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                ai_msg = f"[Błąd GPT] {e}"

        st.session_state.chat_history.append(("AI", ai_msg))

        if st.session_state.get("telegram_enabled", True):
            tg_text = f"🤖 <b>AI – {ticker or 'bez tickera'}</b>\n{question[:200]}\n\n{ai_msg[:500]}"
            send_telegram(tg_text)

        st.rerun()

    # ------------------ PANEL DIAGNOSTYCZNY ETAPU 1 ------------------
    st.title("Etap 1 — zapis i proces skanera")
    with _STORE.connection() as _connection:
        _runtime = _connection.execute("SELECT payload,updated_at FROM runtime WHERE key='scanner'").fetchone()
        _counts = {name: _connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                   for name in ("watchlist", "portfolio", "alerts", "observations", "events", "outbox", "cycles")}
        _recent = [dict(row) for row in _connection.execute("SELECT started_at,finished_at,status FROM cycles ORDER BY started_at DESC LIMIT 10")]
    if _runtime:
        st.json({"ostatni_stan_procesu": json.loads(_runtime[0]), "czas_zapisu_UTC": _runtime[1]})
        if (datetime.now(timezone.utc)-datetime.fromisoformat(_runtime[1])).total_seconds()>15:
            st.warning("Brak świeżego heartbeat. Zapisany stan nie potwierdza, że proces nadal działa.")
    else:
        st.info("Brak zapisanej diagnostyki skanera.")
    st.write("Liczba zapisanych rekordów", _counts)
    st.dataframe(_recent, use_container_width=True)
    st.button("Odśwież diagnostykę")
    st.info("Widoki rynku, AI i wysyłka Telegrama nie są aktywne w etapie 1. Wybrane ustawienia zapisują się w SQLite.")
    st.stop()
    # ------------------ ROUTING LEGACY: DO NAPRAWY W KOLEJNYCH ETAPACH ------------------
    if mode == "🏠 Dashboard portfela":
        render_dashboard()
    elif mode == "🤖 Czat AI (internet + trading)":
        render_ai_chat()
    elif mode == "📈 Kombajn tradingowy":
        render_trading()
    elif mode == "🔔 Alerty cenowe":
        render_alerts()
    elif mode == "📊 Backtesting sygnałów":
        render_backtest()
    else:
        render_scanner()

def run_self_tests():
    import unittest
    import tempfile
    import subprocess
    # Exercise real children with a Windows-style legacy pipe encoding.
    child_env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING='cp1252')
    import io
    from contextlib import redirect_stdout

    class StageOneTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.root = Path(self.temp.name)
            self.db = self.root / 'test.sqlite3'
            self.store = Store(self.db)

        def tearDown(self):
            self.temp.cleanup()

        def fixture(self):
            return {'tickers': ['AAA', 'BBB.WA'],
                    'settings': {'telegram': False, 'auto_scan_interval': 15},
                    'portfolio': [{'ticker': 'AAA', 'shares': 100, 'avg_price': 1.5}],
                    'alerts': {'AAA': {'type': 'SELL_TARGET', 'price': 2, 'active': True}},
                    'last_scan': {'AAA': {'price': 1.6, 'rvol': 1.2}},
                    'backtest': {'AAA': {'bh': 3, 'signal': 2}},
                    'custom': {'preserved': True}}

        def source(self, data=None):
            p = self.root / 'state.json'
            p.write_text(json.dumps(data if data is not None else self.fixture()), encoding='utf-8')
            return p

        def test_01_migration_preserves_source_and_all_sections(self):
            p = self.source()
            before = p.read_bytes()
            plan = prepare_migration(p)
            import_migration(self.store, plan, plan['sha256'])
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(self.store.load_state(), self.fixture())
            with self.store.connection() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM alerts').fetchone()[0], 1)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM portfolio').fetchone()[0], 1)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM baselines').fetchone()[0], 0)

        def test_02_validation_is_read_only(self):
            p = self.source()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--migration-report', str(p), '--db', str(self.root / 'absent.db')]), 0)
            self.assertFalse((self.root / 'absent.db').exists())
            self.assertFalse((self.root / 'absent.db.scanner.lock').exists())

        def test_03_repeat_import_does_not_duplicate(self):
            plan = prepare_migration(self.source())
            self.assertEqual(import_migration(self.store, plan, plan['sha256'])['status'], 'IMPORTED')
            self.assertEqual(import_migration(self.store, plan, plan['sha256'])['status'], 'ALREADY_IMPORTED')
            with self.store.connection() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM migrations').fetchone()[0], 1)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM alerts').fetchone()[0], 1)

        def test_04_bad_data_and_duplicate_json_do_not_import(self):
            data = self.fixture()
            data['portfolio'][0]['shares'] = -1
            plan = prepare_migration(self.source(data))
            self.assertTrue(plan['errors'])
            with self.assertRaises(ValueError):
                import_migration(self.store, plan, plan['sha256'])
            self.assertEqual(self.store.load_state(), {})
            p = self.root / 'duplicate.json'
            p.write_text('{"tickers": [], "tickers": ["AAA"]}')
            self.assertTrue(prepare_migration(p)['errors'])

        def test_05_source_change_invalidates_approval(self):
            p = self.source()
            plan = prepare_migration(p)
            p.write_text('{}')
            with self.assertRaises(ValueError):
                import_migration(self.store, plan, plan['sha256'])
            self.assertEqual(self.store.load_state(), {})

        def test_06_nonempty_database_is_protected(self):
            self.store.save_section('settings', {'existing': True})
            plan = prepare_migration(self.source())
            with self.assertRaises(ValueError):
                import_migration(self.store, plan, plan['sha256'])
            self.assertEqual(self.store.load_state(), {'settings': {'existing': True}})

        def test_07_transaction_rolls_back_all_import_tables(self):
            with self.store.connection() as c:
                c.execute("CREATE TRIGGER fail_import BEFORE INSERT ON portfolio BEGIN SELECT RAISE(ABORT, 'test integrity constraint'); END")
            plan = prepare_migration(self.source())
            with self.assertRaises(sqlite3.IntegrityError):
                import_migration(self.store, plan, plan['sha256'])
            self.assertEqual(self.store.load_state(), {})
            with self.store.connection() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM watchlist').fetchone()[0], 0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM migrations').fetchone()[0], 0)

        def test_08_concurrent_processes_keep_independent_settings(self):
            processes = [subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                         '--storage-probe', '--db', str(self.db), '--probe-key', k],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=child_env)
                         for k in ('scanner_probe', 'ui_probe')]
            for p in processes:
                stdout, stderr = p.communicate(timeout=30)
                self.assertEqual(p.returncode, 0, stdout + stderr)
            settings = self.store.load_section('settings', {})
            self.assertEqual(settings, {'scanner_probe': 39, 'ui_probe': 39})

        def test_09_scanner_lock_blocks_another_process(self):
            with ScannerLock(self.db):
                p = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                     '--scanner', '--diagnostic', '--cycles', '1', '--db', str(self.db)],
                     capture_output=True, text=True, encoding='utf-8', env=child_env, timeout=15)
                self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
            p = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                 '--scanner', '--diagnostic', '--cycles', '1', '--db', str(self.db)],
                 capture_output=True, text=True, encoding='utf-8', env=child_env, timeout=15)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

        def test_10_restart_preserves_baselines_and_outbox(self):
            baseline = {'price': 1.25, 'rvol': 1.0, 'candle_time': '2026-10-02T09:00:00Z'}
            self.store.set_baseline('AAA', '1h', baseline)
            event_id = self.store.record_event('AAA', '1h', {'reason': 'PRICE'}, 'alert evidence')
            restarted = Store(self.db)
            self.assertEqual(restarted.get_baseline('AAA', '1h'), baseline)
            with restarted.connection() as c:
                row = c.execute('SELECT event_id, status, attempts FROM outbox').fetchone()
                self.assertEqual(tuple(row), (event_id, 'PENDING', 0))
            self.assertIsNone(restarted.get_baseline('AAA', '1d'))

        def test_11_diagnostic_cycle_is_not_a_market_scan(self):
            scanner_main(self.db, diagnostic=True, cycles=1)
            with self.store.connection() as c:
                self.assertEqual(c.execute('SELECT status FROM cycles').fetchone()[0], 'DIAGNOSTIC')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 0)

        def test_12_schedule_uses_fixed_slots(self):
            self.assertEqual(next_slot(1001, 900), 1800)
            self.assertEqual(next_slot(1800, 900), 2700)
            self.assertEqual(next_slot(3601, 900), 4500)

        def test_13_nonfinite_legacy_values_are_explicitly_reported(self):
            data = self.fixture()
            data['last_scan']['AAA']['rvol'] = float('nan')
            plan = prepare_migration(self.source(data))
            self.assertFalse(plan['errors'])
            self.assertTrue(plan['warnings'])
            import_migration(self.store, plan, plan['sha256'])
            self.assertIsNone(self.store.load_section('last_scan', {})['AAA']['rvol'])
            data['portfolio'][0]['avg_price'] = float('inf')
            self.assertTrue(prepare_migration(self.source(data))['errors'])

        def test_14_event_and_outbox_are_atomic(self):
            with self.store.connection() as c:
                c.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT, 'test integrity constraint'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                self.store.record_event('AAA', '1h', {'reason': 'PRICE'}, 'evidence')
            with self.store.connection() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)

        def test_15_crash_releases_os_lock(self):
            p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                 '--scanner', '--diagnostic', '--db', str(self.db)],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=child_env)
            try:
                self.assertIn('DIAGNOSTYKA', p.stdout.readline())
                blocked = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                          '--scanner', '--diagnostic', '--cycles', '1', '--db', str(self.db)],
                          capture_output=True, text=True, encoding='utf-8', env=child_env, timeout=15)
                self.assertEqual(blocked.returncode, 3, blocked.stdout + blocked.stderr)
            finally:
                p.kill()
                p.communicate(timeout=15)
            restarted = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                         '--scanner', '--diagnostic', '--cycles', '1', '--db', str(self.db)],
                         capture_output=True, text=True, encoding='utf-8', env=child_env, timeout=15)
            self.assertEqual(restarted.returncode, 0, restarted.stdout + restarted.stderr)

        def test_16_normal_scanner_is_not_silently_simulated(self):
            with self.assertRaises(ValueError):
                scanner_main(self.root / 'unused.db', diagnostic=False, cycles=1)
            self.assertFalse((self.root / 'unused.db').exists())

        def test_17_cli_outputs_utf8_with_legacy_environment(self):
            p = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                 '--scanner', '--db', str(self.db)], capture_output=True,
                 text=True, encoding='utf-8', env=child_env, timeout=15)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn('Błąd:', p.stderr)
            self.assertIn('Pobieranie i detekcja', p.stderr)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StageOneTests)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

def configure_cli_output():
    """Use UTF-8 for terminal and pipe output, independent of Windows locale."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            reconfigure(encoding='utf-8')


def main(argv=None):
    configure_cli_output()
    parser = argparse.ArgumentParser(description='KI.py — etap 1: SQLite i diagnostyka procesów')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--ui',action='store_true')
    modes.add_argument('--scanner',action='store_true')
    modes.add_argument('--migration-report',metavar='JSON')
    modes.add_argument('--migrate',metavar='JSON')
    modes.add_argument('--self-test',action='store_true')
    modes.add_argument('--storage-probe',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--approve-sha')
    parser.add_argument('--diagnostic',action='store_true')
    parser.add_argument('--cycles',type=int)
    parser.add_argument('--probe-key',help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.cycles is not None and args.cycles<1:
        parser.error('--cycles musi być dodatnie.')
    if args.diagnostic and not args.scanner:
        parser.error('--diagnostic wymaga --scanner.')
    if args.cycles is not None and not args.scanner:
        parser.error('--cycles wymaga --scanner.')
    try:
        if args.self_test:
            return run_self_tests()
        if args.migration_report:
            plan = prepare_migration(args.migration_report)
            print(json.dumps(public_migration_report(plan),ensure_ascii=False,indent=2))
            return 2 if plan['errors'] else 0
        if args.migrate:
            plan = prepare_migration(args.migrate)
            if plan['errors'] or not args.approve_sha or args.approve_sha!=plan['sha256']:
                print(json.dumps(public_migration_report(plan),ensure_ascii=False,indent=2))
                raise ValueError('Import niezatwierdzony; użyj --approve-sha zgodnego z raportem.')
            print(json.dumps(import_migration(Store(args.db),plan,args.approve_sha),ensure_ascii=False,indent=2))
            return 0
        if args.scanner:
            return scanner_main(args.db,args.diagnostic,args.cycles)
        if args.storage_probe:
            if not args.probe_key:
                raise ValueError('Brak klucza testowego.')
            store = Store(args.db)
            for i in range(40):
                store.update_settings({args.probe_key:i})
            return 0
        run_streamlit(args.db)
        return 0
    except RuntimeError as exc:
        print(str(exc),file=sys.stderr)
        return 3
    except (ValueError,OSError,sqlite3.Error) as exc:
        print(f'Błąd: {exc}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    _exit_code = main()
    if _exit_code:
        raise SystemExit(_exit_code)
