"""
_ai_review.py - offline analiza decyzji should_alert.
Czyta alert_decisions (lub opportunities jako fallback), grupuje po reason,
pyta GPT o kalibracje progów, zapisuje raport MD.

Uruchomienie:
    python _ai_review.py --days 7 --min-samples 10
    python _ai_review.py --dry-run          # bez GPT, tylko statystyki
    python _ai_review.py --no-opportunities # tylko alert_decisions, bez fallbacku

Koszt: 1 wywolanie GPT-4o-mini (~$0.001-0.005 w zaleznosci od liczby probek).
"""
import argparse, io, json, os, sqlite3, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_DEFAULT = "KI.matrix.sqlite3"
OUT_DEFAULT = "AI_REVIEW_{date}.md"


def load_alert_decisions(db, days):
    """Zwraca liste dict z alert_decisions z ostatnich N dni."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    c = sqlite3.connect(db)
    try:
        rows = c.execute(
            "SELECT seq, ts, stage, should_alert, reason, payload_json "
            "FROM alert_decisions WHERE ts >= ? ORDER BY ts DESC",
            (cutoff,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {'seq': r[0], 'ts': r[1], 'stage': r[2], 'should_alert': bool(r[3]),
         'reason': r[4], 'payload': json.loads(r[5]) if r[5] else None}
        for r in rows
    ]


def load_opportunities(db, days):
    """Fallback: opportunities z ostatnich N dni, zmapowane na te same pola."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    c = sqlite3.connect(db)
    try:
        rows = c.execute(
            "SELECT sequence_id, updated_at, state, payload FROM opportunities "
            "WHERE updated_at >= ? ORDER BY updated_at DESC",
            (cutoff,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for seq, ts, state, payload in rows:
        try:
            p = json.loads(payload) if payload else {}
        except Exception:
            p = {}
        # payload w opportunities JEST rankiem: score, rvol, snapshot, change_pct na najwyzszym poziomie
        snap = p.get('snapshot') or {}
        out.append({
            'seq': seq, 'ts': ts, 'stage': f'opportunity/{state}',
            'should_alert': state in ('RESERVED', 'SELECTED'),
            'reason': f'state={state}',
            'payload': {
                'ticker': snap.get('ticker'),
                'acquired_at': snap.get('acquired_at'),
                'rvol': p.get('rvol'),
                'score': p.get('score'),
                'change_pct': p.get('change_pct'),
            },
        })
    return out


def stats(decisions):
    """Rozklad reasonow, stagey, alert/nie-alert."""
    total = len(decisions)
    if not total:
        return {'total': 0}
    by_reason = {}
    by_stage = {}
    alert_yes = sum(1 for d in decisions if d['should_alert'])
    for d in decisions:
        by_reason[d['reason']] = by_reason.get(d['reason'], 0) + 1
        by_stage[d['stage']] = by_stage.get(d['stage'], 0) + 1
    return {
        'total': total,
        'alert_yes': alert_yes,
        'alert_no': total - alert_yes,
        'pct_alert': round(100 * alert_yes / total, 1) if total else 0,
        'by_reason': dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
        'by_stage': by_stage,
    }


def build_prompt(decisions, st, days):
    """Buduje prompt dla GPT: rozklad decyzji + prosba o kalibracje."""
    # Probka: max 200 decyzji z alert=False, z roznymi reasonami
    false_sample = [d for d in decisions if not d['should_alert']][:100]
    true_sample = [d for d in decisions if d['should_alert']][:50]

    lines = [
        f"Jestes analitykiem systemu alertow gieldowych. Przeanalizuj decyzje should_alert z ostatnich {days} dni.",
        f"Lacznie decyzji: {st['total']} (alert=True: {st['alert_yes']}, alert=False: {st['alert_no']}, {st['pct_alert']}% alertow).",
        "",
        "Rozklad reasonow (odrzucenia):",
    ]
    for reason, cnt in st['by_reason'].items():
        lines.append(f"  - {reason}: {cnt}")

    lines.append("")
    lines.append("Przyklady ODRZUCONYCH (should_alert=False, max 100):")
    for d in false_sample[:50]:
        p = d.get('payload') or {}
        lines.append(f"  [{d['stage']}] {p.get('ticker') or '?'} rvol={p.get('rvol')} score={p.get('score')} reason={d['reason']}")

    if true_sample:
        lines.append("")
        lines.append("Przyklady PRZEPUSZCZONYCH (should_alert=True, max 50):")
        for d in true_sample[:30]:
            p = d.get('payload') or {}
            lines.append(f"  [{d['stage']}] {p.get('ticker') or '?'} rvol={p.get('rvol')} score={p.get('score')}")

    lines.append("")
    lines.append("Zadanie:")
    lines.append("1. Ktore progi (rvol_min, spread_risk_pct, matryca 3 odczytow) sa zle skalibrowane?")
    lines.append("2. Ktore odrzucenia wygladaja na bledne (powinny przejsc)?")
    lines.append("3. Ktore przepuszczenia wygladaja na bledne (powinny byc odrzucone)?")
    lines.append("4. Konkretne sugestie zmian (np. 'rvol_min 1.0 -> 0.8') z uzasadnieniem.")
    lines.append("")
    lines.append("Odpowiedz po polsku, w formacie markdown, zwiezle (max 800 slow).")
    return "\n".join(lines)


def call_gpt(prompt, keys):
    """Wywoluje GPT-4o-mini z promptem. Zwraca tekst odpowiedzi."""
    import urllib.request
    import urllib.error
    api_key = keys.get('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("Brak OPENAI_API_KEY w secrets.toml")
    body = json.dumps({
        'model': 'gpt-4o-mini',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.2,
        'max_tokens': 2000,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=body,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content']


def load_api_key():
    """Probuje wczytac OPENAI_API_KEY z secrets.toml (projekt lub home)."""
    import tomllib
    for base in (Path.home(), Path(__file__).resolve().parent):
        p = base / '.streamlit' / 'secrets.toml'
        if p.is_file():
            try:
                with io.open(p, 'rb') as f:
                    d = tomllib.load(f)
                if d.get('OPENAI_API_KEY'):
                    return {'OPENAI_API_KEY': d['OPENAI_API_KEY']}
            except Exception:
                pass
    if os.environ.get('OPENAI_API_KEY'):
        return {'OPENAI_API_KEY': os.environ['OPENAI_API_KEY']}
    return {}


def main():
    ap = argparse.ArgumentParser(description='Offline AI review decyzji should_alert')
    ap.add_argument('--db', default=DB_DEFAULT)
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--min-samples', type=int, default=10)
    ap.add_argument('--dry-run', action='store_true', help='Bez GPT, tylko statystyki')
    ap.add_argument('--no-opportunities', action='store_true', help='Bez fallbacku na opportunities')
    ap.add_argument('--out', default=None, help='Plik wyjsciowy MD (default: AI_REVIEW_<data>.md)')
    args = ap.parse_args()

    decisions = load_alert_decisions(args.db, args.days)
    source = 'alert_decisions'
    if not decisions and not args.no_opportunities:
        decisions = load_opportunities(args.db, args.days)
        source = 'opportunities (fallback)'

    st = stats(decisions)
    print(f"Zrodlo: {source}")
    print(f"Decyzji w ostatnich {args.days} dniach: {st['total']}")
    if st['total']:
        print(f"  alert=True: {st['alert_yes']} ({st['pct_alert']}%)")
        print(f"  alert=False: {st['alert_no']}")
        print("\nRozklad reasonow:")
        for r, c in st['by_reason'].items():
            print(f"  {r}: {c}")

    if st['total'] < args.min_samples:
        print(f"\nZa malo probek ({st['total']} < {args.min_samples}). Zbierz wiecej danych albo obniz --min-samples.")
        if args.dry_run:
            return 0
        print("Kontynuuje mimo to (dry-run nie ustawiony)...")

    if args.dry_run:
        print("\n[dry-run] Pomijam GPT. Prompt by byl:")
        print(build_prompt(decisions, st, args.days)[:2000])
        return 0

    if st['total'] == 0:
        print("\nBrak danych do analizy. Uruchom skaner zeby zebrac decyzje.")
        return 1

    keys = load_api_key()
    if not keys.get('OPENAI_API_KEY'):
        print("\nBrak OPENAI_API_KEY - nie mozna wywolac GPT.")
        return 1

    print("\nWolam GPT-4o-mini...")
    prompt = build_prompt(decisions, st, args.days)
    try:
        answer = call_gpt(prompt, keys)
    except Exception as e:
        print(f"Blad GPT: {e}")
        return 1

    out = args.out or OUT_DEFAULT.format(date=datetime.now().strftime('%Y-%m-%d'))
    out_path = Path(out)
    header = f"""# AI Review decyzji should_alert

**Data:** {datetime.now().isoformat()}
**Zrodlo:** {source}
**Okres:** ostatnie {args.days} dni
**Probek:** {st['total']} (alert=True: {st['alert_yes']}, alert=False: {st['alert_no']})

## Rozklad reasonow

"""
    for r, c in st['by_reason'].items():
        header += f"- **{r}**: {c}\n"
    header += "\n## Rekomendacje GPT\n\n"
    io.open(out_path, 'w', encoding='utf-8').write(header + answer + "\n")
    print(f"\nZapisano: {out_path}")
    print(f"\n--- Pierwsze 500 znakow odpowiedzi ---")
    print(answer[:500])
    return 0


if __name__ == '__main__':
    sys.exit(main())
