"""Lossless observation history storage; ordinary JSON market fields stay queryable.

Readers must use loads(), not the standard json.loads(), for stored payloads.
Old uncompressed rows remain readable. No network or external dependencies.
"""
import base64
import hashlib
import json
import zlib
from datetime import datetime, timedelta, timezone


HISTORY_FIELDS = ('chart_history', 'carried_price_candles')
MARKER = '_ki_history_zlib_v1'
MAX_HISTORY_BYTES = 8 * 1024 * 1024


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _restore_fields(value):
    for field in HISTORY_FIELDS:
        packed = value.get(field)
        if not isinstance(packed, dict) or MARKER not in packed:
            continue
        if set(packed) != {MARKER, 'size', 'sha256'}:
            raise ValueError('Niepoprawny format zapisanej historii KI.')
        size = packed['size']
        if type(size) is not int or not 0 <= size <= MAX_HISTORY_BYTES:
            raise ValueError('Niepoprawny rozmiar zapisanej historii KI.')
        data = packed[MARKER]
        if not isinstance(data, str) or len(data) > 2 * MAX_HISTORY_BYTES:
            raise ValueError('Niepoprawna skompresowana historia KI.')
        decoder = zlib.decompressobj()
        raw = decoder.decompress(base64.b64decode(data, validate=True), size + 1)
        if (len(raw) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
                or hashlib.sha256(raw).hexdigest() != packed['sha256']):
            raise ValueError('Uszkodzona historia KI; nie zastąpiono danych.')
        rows = json.loads(raw)
        if not isinstance(rows, list):
            raise ValueError('Historia KI nie jest listą świec.')
        value[field] = rows
    return value


def loads(raw, **kwargs):
    # Most settings/results do not contain packed history: keep the ordinary fast path.
    marker = MARKER.encode() if isinstance(raw, (bytes, bytearray)) else MARKER
    if marker not in raw:
        return json.loads(raw, **kwargs)
    if kwargs:
        # Hook-based import validation retains the standard JSON contract.
        return json.loads(raw, **kwargs)
    return json.loads(raw, object_hook=_restore_fields)


def encode_observation(snapshot):
    """Encode only large list fields, without changing the caller's snapshot."""
    stored = dict(snapshot)
    for field in HISTORY_FIELDS:
        rows = stored.get(field)
        if not isinstance(rows, list):
            continue
        raw = _json(rows).encode('utf-8')
        if not 2048 <= len(raw) <= MAX_HISTORY_BYTES:
            continue
        packed = {MARKER: base64.b64encode(zlib.compress(raw, 6)).decode('ascii'),
                  'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if len(_json(packed).encode('utf-8')) < len(raw) * .8:
            stored[field] = packed
    return _json(stored)


def prune_observations(connection, days, now=None, batch_size=1000):
    """Apply configured age limit in bounded batches, preserving latest two per pair.

    Must run inside the caller's transaction. No event, job, alert or research rows
    are changed. A completed sweep is checked at most once per day.
    """
    if type(days) is not int or days < 1 or not 1 <= batch_size <= 10000:
        raise ValueError('Niepoprawny okres lub limit retencji obserwacji.')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Retencja wymaga czasu ze strefą.')
    now = now.astimezone(timezone.utc)
    state = connection.execute("SELECT payload FROM runtime WHERE key='observation_retention'").fetchone()
    if state:
        state = json.loads(state[0])
        if state.get('days') == days and state.get('next_check_at', '') > now.isoformat():
            return 0
    cutoff = (now - timedelta(days=days)).isoformat()
    rows = connection.execute("""
        SELECT o.id FROM observations o
        WHERE o.acquired_at < ? AND julianday(o.acquired_at) < julianday(?)
          AND o.id NOT IN (
            SELECT recent.id FROM observations recent
            WHERE recent.ticker=o.ticker AND recent.interval=o.interval
            ORDER BY recent.id DESC LIMIT 2)
        ORDER BY o.acquired_at, o.id LIMIT ?
        """, (cutoff, cutoff, batch_size)).fetchall()
    connection.executemany('DELETE FROM observations WHERE id=?', [(r[0],) for r in rows])
    state = {'days': days, 'deleted_last_batch': len(rows), 'cutoff': cutoff,
             'next_check_at': (now + (timedelta(minutes=15) if len(rows) == batch_size
                                     else timedelta(days=1))).isoformat()}
    connection.execute('INSERT OR REPLACE INTO runtime(key,payload,updated_at) VALUES(?,?,?)',
                       ('observation_retention', _json(state), now.isoformat()))
    return len(rows)
