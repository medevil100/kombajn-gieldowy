"""Run as database owner. Atomically change one preference, preserve all others."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import runpy
import sqlite3

ROOT=Path('/home/ubuntu/ki2')
KEY='final_company_review_enabled'


def change(path,mode,previous=None):
    db=sqlite3.connect(path.as_uri()+('?mode=ro' if mode=='read' else '?mode=rw'),uri=True,timeout=20)
    try:
        row=db.execute("SELECT payload FROM legacy_state WHERE section='settings'").fetchone()
        if not row:raise ValueError('Brak zapisanych ustawień KI.')
        settings=json.loads(row[0])
        if not isinstance(settings,dict):raise ValueError('Niepoprawne ustawienia KI.')
        before={'present':KEY in settings,'value':settings.get(KEY)}
        if mode=='read':return before
        db.execute('BEGIN IMMEDIATE')
        # Re-read under the write lock, so unrelated preferences are never lost.
        settings=json.loads(db.execute("SELECT payload FROM legacy_state WHERE section='settings'").fetchone()[0])
        if mode=='enable':
            runpy.run_path(str(ROOT/'final_company_review.py'),run_name='ki2_review_config')['ensure'](db)
            settings[KEY]=True
        else:
            if not isinstance(previous,dict) or set(previous)!={'present','value'} or type(previous['present']) is not bool:
                raise ValueError('Niepoprawna kopia preferencji.')
            if previous['present']:settings[KEY]=previous['value']
            else:settings.pop(KEY,None)
        stamp=datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE legacy_state SET payload=?,updated_at=? WHERE section='settings'",
                   (json.dumps(settings,ensure_ascii=False,allow_nan=False),stamp))
        if KEY in settings:
            db.execute('INSERT OR REPLACE INTO settings(key,payload) VALUES(?,?)',(KEY,json.dumps(settings[KEY],allow_nan=False)))
        else:db.execute('DELETE FROM settings WHERE key=?',(KEY,))
        db.commit()
        return before
    except BaseException:
        db.rollback();raise
    finally:db.close()


def main():
    parser=argparse.ArgumentParser()
    options=parser.add_mutually_exclusive_group(required=True)
    options.add_argument('--read',action='store_true')
    options.add_argument('--enable',action='store_true')
    options.add_argument('--restore',type=Path)
    args=parser.parse_args()
    mode='read' if args.read else 'enable' if args.enable else 'restore'
    previous=json.loads(args.restore.read_text(encoding='utf-8')) if args.restore else None
    print(json.dumps(change(ROOT/'KI.matrix.sqlite3',mode,previous)))


if __name__=='__main__':main()
