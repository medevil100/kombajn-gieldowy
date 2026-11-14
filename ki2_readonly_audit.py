"""Read-only operational/final-review counters; no KI import or provider calls."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def timestamp(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('Czas wymaga strefy, np. +00:00.')
    return at.astimezone(timezone.utc)


def read_audit(path, since, until=None):
    path = Path(path).expanduser().resolve(strict=True)
    start = timestamp(since)
    end = timestamp(until) if until else datetime.now(timezone.utc)
    if start > end:
        raise ValueError('Początek zakresu jest późniejszy niż koniec.')
    report = {'database': str(path), 'since': start.isoformat(), 'asof': end.isoformat(),
              'db_bytes': path.stat().st_size, 'read_only': True, 'warnings': []}
    params = (start.isoformat(), end.isoformat())
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        report['runtime'] = {}
        if 'runtime' in tables:
            for key, updated, raw in db.execute("SELECT key,updated_at,payload FROM runtime WHERE key IN ('scanner','worker_analysis','worker_telegram')"):
                try:
                    data = json.loads(raw)
                    age = round((end - timestamp(updated)).total_seconds(), 1)
                    report['runtime'][key] = {'updated_at': updated, 'age_seconds': age,
                                              'status': data.get('status'), 'pid': data.get('pid')}
                except (ValueError, TypeError, AttributeError):
                    report['runtime'][key] = {'status': 'INVALID_RECORD'}
            actions=Counter();roles=Counter();states=0
            for (raw,) in db.execute("SELECT payload FROM runtime WHERE key LIKE 'orchestrator:%'"):
                try:
                    value=json.loads(raw)
                    if start<=timestamp(value['evaluated_at'])<=end:
                        states+=1;actions[str(value['action'])]+=1;roles[str(value['role'])]+=1
                except (ValueError,TypeError,KeyError,AttributeError):continue
            report['orchestration']={'latest_company_states':states,'actions':dict(actions),'roles':dict(roles),
                'scope':'Ostatni zapis każdej spółki w badanym czasie; nie historia wszystkich przejść.'}
        if 'cycles' in tables:
            report['cycles'] = dict(db.execute('SELECT status,count(*) FROM cycles WHERE started_at>=? AND started_at<=? GROUP BY status', params))
        if 'large_movement_jobs' in tables:
            usage=db.execute('SELECT count(started_at),coalesce(sum(input_tokens),0),coalesce(sum(output_tokens),0) FROM large_movement_jobs WHERE created_at>=? AND created_at<=?',params).fetchone()
            report['large_movement']={'jobs':dict(db.execute('SELECT state,count(*) FROM large_movement_jobs WHERE created_at>=? AND created_at<=? GROUP BY state',params)),
                'reserved_model_calls':usage[0],'input_tokens':usage[1],'output_tokens':usage[2],
                'scope':'Osobna gałąź orkiestratora dla dużego potencjału; zużycie także z zapisanych błędnych odpowiedzi.'}
            if 'large_movement_cases' in tables:
                report['large_movement']['current_cases']=dict(db.execute('SELECT status,count(*) FROM large_movement_cases GROUP BY status'))
        if {'events', 'analysis_jobs'} <= tables:
            jobs = Counter()
            coverage = Counter()
            final_attention = Counter()
            review_stages = Counter()
            quality = Counter()
            token_total = 0
            usage_records = 0
            final_records = 0
            # Extract only the fields needed for counters, not source documents,
            # provider errors, prompts, raw answers or any credentials.
            sql = '''SELECT j.state,
                     CASE WHEN json_valid(e.payload) THEN json_extract(e.payload,'$.company_review_batch') END,
                     CASE WHEN json_valid(j.context) THEN json_extract(j.context,'$.analysis_manifest.session_context.status') END,
                     CASE WHEN json_valid(j.result) THEN json_extract(j.result,'$.analysis.final_review.attention') END,
                     CASE WHEN json_valid(j.result) THEN json_array_length(json_extract(j.result,'$.analysis.quality_issues')) END,
                     CASE WHEN json_valid(j.result) THEN json_extract(j.result,'$.provider.usage.total_tokens') END,
                     CASE WHEN json_valid(e.payload) THEN json_extract(e.payload,'$.review_stage') END
                     FROM analysis_jobs j JOIN events e ON e.id=j.event_id
                     WHERE e.created_at>=? AND e.created_at<=?'''
            for state, batch, session, attention, omissions, tokens, review_stage in db.execute(sql, params):
                jobs[state] += 1
                if batch:
                    final_records += 1
                    review_stages[review_stage or 'CONFIRMED_LEGACY'] += 1
                    coverage[session or 'NOT_RECORDED'] += 1
                    final_attention[attention or 'NOT_RECORDED'] += 1
                    quality['WITH_OMISSIONS' if omissions else 'NONE_RECORDED'] += 1
                if isinstance(tokens, int) and tokens >= 0:
                    token_total += tokens
                    usage_records += 1
            report['analysis_jobs'] = dict(jobs)
            report['final_reviews'] = {'jobs': final_records, 'session_coverage': dict(coverage),
                                       'attention': dict(final_attention), 'quality': dict(quality),
                                       'review_stages':dict(review_stages)}
            report['openai_recorded_usage'] = {'records': usage_records, 'total_tokens': token_total}
        if 'company_review_batches' in tables:
            batches = Counter()
            pool_reasons = Counter()
            preparation = Counter()
            for state, raw in db.execute('SELECT state,payload FROM company_review_batches WHERE created_at>=? AND created_at<=?', params):
                batches[state] += 1
                try:
                    data = json.loads(raw)
                    for item in data.get('pool', []):
                        reason = item.get('state')
                        if reason:
                            pool_reasons[str(reason)] += 1
                    for item in data.get('diagnostics', []):
                        if item.get('status'):
                            preparation[str(item['status'])] += 1
                except (ValueError, AttributeError, TypeError):
                    preparation['INVALID_RECORD'] += 1
            report['batches'] = dict(batches)
            report['selection_reasons'] = dict(pool_reasons)
            report['preparation'] = dict(preparation)
        if 'outbox' in tables:
            report['delivery'] = [dict(kind=kind, status=status, count=count) for kind, status, count in db.execute(
                'SELECT kind,status,count(*) FROM outbox WHERE created_at>=? AND created_at<=? GROUP BY kind,status', params)]
        required = {'runtime', 'cycles', 'events', 'analysis_jobs', 'company_review_batches', 'outbox'}
        report['warnings'].extend('MISSING_TABLE:' + table for table in sorted(required - tables))
    report['limitations'] = [
        'Liczniki nie potwierdzają prawdziwości wniosków AI ani skuteczności inwestycyjnej.',
        'Zakres zadań według utworzenia zdarzenia; nie jest to rozliczenie faktury dostawcy.',
        'Brak wiadomości nie dowodzi awarii: selekcja może nie znaleźć kwalifikujących się spółek.',
        'Stan i plik bazy mogą zmieniać się po odczycie; audyt nie zatrzymuje skanera.',
    ]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--since', required=True, help='ISO timestamp including timezone.')
    parser.add_argument('--until', help='Optional ISO timestamp including timezone.')
    args = parser.parse_args(argv)
    try:
        report = read_audit(args.db, args.since, args.until)
    except (ValueError, OSError, sqlite3.Error) as error:
        # Do not emit arbitrary DB contents or exception messages.
        print(json.dumps({'status': 'AUDIT_FAILED', 'error_type': type(error).__name__}))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
