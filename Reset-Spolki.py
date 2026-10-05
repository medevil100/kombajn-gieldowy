"""Reset pamięci spółek KI; uruchamiany ręcznie po zatrzymaniu programu."""
import argparse
from contextlib import ExitStack, closing
from datetime import datetime
from pathlib import Path
import sqlite3
import KI

TABLES = ('delivery_receipts','analysis_rejections','analysis_jobs','outbox','events',
          'observations','baselines','opportunities','analysis_budgets','deep_reports',
          'gpt_chat_turns','cycles','watchlist','portfolio','alerts','runtime','dismissed_errors')


def reset_company_data(db):
    primary = Path(db).expanduser().resolve()
    if not primary.is_file():
        raise ValueError('Nie znaleziono bazy. Niczego nie wyczyszczono.')
    paths = [primary]
    manual = KI.manual_store_path(primary)
    if manual.is_file():
        paths.append(manual)
    with ExitStack() as locks:
        for path in paths:
            for suffix in ('','.launcher','.analysis','.telegram','.gpt_chat'):
                locks.enter_context(KI.ScannerLock(str(path)+suffix))
        stores = [KI.Store(path) for path in paths]
        for store in stores:
            with store.connection() as c:
                if c.execute("SELECT 1 FROM deep_reports WHERE state IN ('QUEUED','RUNNING')").fetchone():
                    raise ValueError('Analiza pogłębiona nadal oczekuje lub pracuje. Niczego nie wyczyszczono.')
                if c.execute("SELECT 1 FROM gpt_chat_turns WHERE state='REQUESTED'").fetchone():
                    raise ValueError('Pytanie GPT nie jest zakończone. Niczego nie wyczyszczono.')
        backup_dir = primary.parent / ('kopia_SQLite_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup_dir.mkdir()
        for store in stores:
            with store.connection() as source, closing(sqlite3.connect(backup_dir / store.path.name)) as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Kopia bazy nie przeszła weryfikacji. Niczego nie wyczyszczono.')
        for store in stores:
            with store.transaction() as c:
                for table in TABLES:
                    c.execute('DELETE FROM '+table)
                c.execute("DELETE FROM legacy_state WHERE section!='settings'")
                KI.Store._write_section(store,c,'tickers',[])
                KI.Store._write_section(store,c,'portfolio',[])
                KI.Store._write_section(store,c,'alerts',{})
        return backup_dir


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        primary=Path(temp)/'test.sqlite3'
        stores=[KI.Store(primary),KI.Store(KI.manual_store_path(primary))]
        for store in stores:
            store.save_section('tickers',['AAA'])
            store.save_section('settings',{'auto_scan_interval':15})
        with KI.ScannerLock(primary):
            try:reset_company_data(primary)
            except RuntimeError:pass
            else:raise AssertionError('Reset nie blokuje aktywnego skanera.')
        assert stores[0].load_section('tickers',[])==['AAA']
        backup=reset_company_data(primary)
        for store in stores:
            assert store.load_section('tickers',[])==[]
            assert store.load_section('settings',{})=={'auto_scan_interval':15}
            assert KI.Store(backup/store.path.name).load_section('tickers',[])==['AAA']
        print('Test resetu: obie bazy, kopie, ustawienia i blokada aktywnego skanera — OK.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=str(KI.DEFAULT_DB))
    parser.add_argument('--confirm')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        raise SystemExit(0)
    if args.confirm != 'WYCZYSC DANE SPOLEK':
        parser.error('Wymagane potwierdzenie: WYCZYSC DANE SPOLEK')
    try:
        backup = reset_company_data(args.db)
        print('Wyczyszczono listę spółek, odczyty, zdarzenia, analizy, rozmowy, kolejki, portfolio i alerty.')
        print('Zachowano ustawienia, klucze, metadane migracji i kopię bazy:', backup)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        print('Reset przerwany:', str(exc))
        raise SystemExit(2)
