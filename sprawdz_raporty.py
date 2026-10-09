"""Odczyt zapisanych raportów i ich pól liczbowych. Bez API i zapisu bazy."""
import argparse
import json
from pathlib import Path
import sqlite3
import KI


def inspect_reports(database, limit=3):
    con = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA query_only=ON')
        rows = con.execute(
            "SELECT id,state,context,metadata FROM gpt_chat_turns "
            "WHERE state='REVIEW_REQUIRED' ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        con.close()
    results = []
    for row in rows:
        ctx = json.loads(row['context'])
        metrics = KI.manual_research_metrics(ctx)
        values = {key: metrics[key]['value'] if key in metrics else None for key in (
            'rvol', 'previous_snapshot_volume', 'previous_candle_volume', 'carried_price_candles_count')}
        previous = KI.manual_previous_snapshot(ctx)
        result = {'report':row['id'], 'ticker':ctx.get('ticker'), 'state':row['state'],
                  'values':values, 'previous_acquired_at':(previous or {}).get('acquired_at')}
        metadata = json.loads(row['metadata'] or '{}')
        choices = metadata.get('raw_response')
        if not choices:
            result['validation'] = 'Brak zachowanej odpowiedzi GPT.'
        else:
            try:
                KI.parse_gpt_chat_response({'choices':choices}, ctx)
                result['validation'] = 'Format zgodny; nie jest to potwierdzenie wnioskow modelu.'
            except (KI.ServiceError, ValueError, TypeError, KeyError) as exc:
                result['validation'] = str(exc)
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args()
    print('HISTORYCZNE RAPORTY - TYLKO ODCZYT, BEZ API')
    for result in inspect_reports(args.db):
        if args.summary:
            print(str(result['ticker'])+' | '+result['report'])
            print('Zweryfikowane pola kontekstu: '+json.dumps(result['values'],ensure_ascii=False))
            print('Czas poprzedniego odczytu: '+str(result['previous_acquired_at']))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    print('Statusy i odpowiedzi w bazie pozostaly bez zmian.')


if __name__ == '__main__': main()
