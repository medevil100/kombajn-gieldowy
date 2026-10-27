"""Archiwizacja osieroconej diagnostyki bez utraty treści. Bez automatycznego VACUUM."""
import argparse
from pathlib import Path
import sqlite3
from contextlib import closing
import KI


def archive_orphan_rejections(store):
    with store.transaction() as c:
        rows=c.execute('SELECT r.* FROM analysis_rejections r LEFT JOIN events e ON e.id=r.event_id WHERE e.id IS NULL').fetchall()
        for row in rows:
            values=tuple(row[key] for key in ('id','event_id','reason','payload','created_at'))
            old=c.execute('SELECT id,event_id,reason,payload,created_at FROM archived_analysis_rejections WHERE id=?',(row['id'],)).fetchone()
            if old and tuple(old)!=values:raise ValueError('Niezgodna istniejąca kopia archiwalna; nie zmieniono danych.')
            c.execute('INSERT OR IGNORE INTO archived_analysis_rejections VALUES(?,?,?,?,?,?,?)',
                      (*values,KI.utc_now(),'Historyczny brak nadrzędnego zdarzenia; zachowano oryginalne ID i treść.'))
        for row in rows:
            c.execute('DELETE FROM analysis_rejections WHERE id=?',(row['id'],))
        return len(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    path=Path(args.db).resolve()
    if not path.is_file():raise ValueError('Brak istniejącej bazy.')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
        count=c.execute('SELECT COUNT(*) FROM analysis_rejections r LEFT JOIN events e ON e.id=r.event_id WHERE e.id IS NULL').fetchone()[0]
    print('Osierocone rekordy:',count)
    if args.apply:
        store=KI.Store(path);print('Zarchiwizowano:',archive_orphan_rejections(store))
        with store.connection() as c:print('Pozostałe naruszenia FK:',len(c.execute('PRAGMA foreign_key_check').fetchall()))


if __name__=='__main__':main()
