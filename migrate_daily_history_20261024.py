"""Addytywna migracja istniejących baz; nie pobiera danych ani nie uruchamia usług."""
import json
import re
import sqlite3
from pathlib import Path

import KI


def migrate(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    connection=sqlite3.connect(path.resolve().as_uri()+'?mode=rw',uri=True)
    try:
        connection.execute('PRAGMA busy_timeout=15000')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('BEGIN IMMEDIATE')
        schema=connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        tables=[row[1] for row in schema if row[0]=='table' and row[1]!='daily_candles']
        def counts():
            return {name:connection.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in tables}
        before=counts()
        statement=re.search(r'CREATE TABLE IF NOT EXISTS daily_candles\(.*?;',KI.SCHEMA,re.S).group()
        connection.execute(statement)
        after=counts()
        after_schema=connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND name<>'daily_candles' ORDER BY type,name").fetchall()
        original_schema=[row for row in schema if row[1]!='daily_candles']
        if before!=after or original_schema!=after_schema:
            raise RuntimeError('Zmiana dotychczasowych danych lub schematu; wycofano transakcję.')
        connection.commit()
        print(path.name+': migracja zatwierdzona; istniejące tabele i liczby rekordów zachowane.',flush=True)
        check=connection.execute('PRAGMA quick_check').fetchall()
        if check!=[('ok',)]:
            raise RuntimeError(str(check))
        return {'database':str(path.resolve()),'before':before,'after':after,
                'existing_schema_preserved':True,'quick_check':check,
                'daily_candles':connection.execute('SELECT COUNT(*) FROM daily_candles').fetchone()[0],
                'size':path.stat().st_size}
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__=='__main__':
    root=Path(__file__).resolve().parent
    report=[]
    for name in ('KI.matrix.sqlite3','KI.matrix.manual.sqlite3'):
        report.append(migrate(root/name))
        (root/'repair_database_migration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Kontrola obu baz: ok.',flush=True)
