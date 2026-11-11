"""Calendar-based end-of-session report window; no network or delivery actions."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from session_context import bounds, stamp


def report_window(market, now=None):
    current=stamp(now) if now is not None else datetime.now(timezone.utc)
    if not current:raise ValueError('Brak poprawnego czasu raportu.')
    calendar,zone={'GPW':('XWAR','Europe/Warsaw'),'USA':('XNYS','America/New_York')}[market]
    day=current.astimezone(ZoneInfo(zone)).date().isoformat()
    session=bounds(calendar,day)
    if not session:return None
    opening,closing=session
    due=closing+timedelta(minutes=5)
    # A fifteen-minute scan cadence may finish after the exact due minute.
    # Allow delayed completion, but never send before the actual session end.
    if not due<=current<=closing+timedelta(minutes=90):return None
    return {'market':market,'session_date':day,'session_open':opening.isoformat(),
            'session_close':closing.isoformat(),'due_at':due.isoformat()}
