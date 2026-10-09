"""Testy offline E01–E06: izolowany ZIP KI, bez kluczy/API/produkcyjnej SQLite."""
from pathlib import Path
import hashlib
import os
import re
import subprocess
import sys

root=Path(__file__).resolve().parent
sha='6CAF50D72D259E123C9C3F400CE501B72AE69CEC2B124499D6150B33BD8C3B72'
file=root/'KI.py'
if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest().upper()!=sha:
    sys.exit('STOP: niezgodny KI.py lub brak pliku.')
for path in root.iterdir():
    if path.is_file() and (path.suffix.lower() in ('.db','.sqlite','.sqlite3') or path.name.endswith(('.sqlite3-wal','.sqlite3-shm'))):
        sys.exit('STOP: znaleziono baze danych w katalogu testowym: '+path.name)
if (root/'.streamlit/secrets.toml').exists():
    sys.exit('STOP: znaleziono sekrety w katalogu testowym.')

cases=[
    ('Wbudowana regresja KI', ['KI.py','--self-test']),
    ('A+B - kontrakt GPT', ['test_ab_contract.py']),
    ('C - kontrakt Tavily', ['test_c_tavily_contract.py']),
    ('D - raport', ['test_d_report_contract.py']),
    ('E01-E03 - SQLite i przelaczniki', ['test_e_integracja_contract.py']),
    ('E04 - kwalifikacja bez limitu', ['test_e04_kwalifikacja_contract.py']),
    ('E05 - dowody aktywnosci rynku', ['test_e05_aktywnosc.py']),
    ('E06 - kwalifikacja zrodel Tavily', ['test_e06_tavily_issuer.py']),
    ('GPW - alert/wskazniki', ['test_gpw_alert_indicator_contract.py']),
    ('GPW - cena bazowa', ['test_price_matrix.py']),
    ('GPW - daty zrodel', ['test_tavily_page_dates.py']),
    ('GPW - wyszukiwanie', ['test_tavily_search_contract.py']),
    ('GPW - dane liczbowe', ['test_manual_numeric_contract.py']),
    ('GPW - walidator reczny', ['test_manual_validation_20261008.py']),
    ('GPW - reguly numeryczne', ['test_numeric_rules.py']),
    ('GPW - raport reczny', ['test_research_v3.py']),
    ('GPW - bid/ask', ['test_bid_ask.py']),
    ('Panel Streamlit', ['KI.py','--panel-test']),
    ('Uruchamianie diagnostyczne', ['KI.py','--launch-test']),
    ('Dodatkowy panel Tavily', ['test_tavily_panel.py']),
]
print('KI E01-E06 - SHA256 POTWIERDZONE',flush=True)
env=dict(os.environ)
env['PYTHONDONTWRITEBYTECODE']='1'
total=0
for n,(title,args) in enumerate(cases,1):
    print(f'\nTEST {n}/{len(cases)}: {title}',flush=True)
    p=subprocess.run([sys.executable,'-B',*args],cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if p.returncode:
        print(p.stdout[-10000:],flush=True)
        sys.exit(f'TEST FAILED: {title}. Zatrzymano, pozostale testy nie zostaly uruchomione.')
    counted=sum(map(int,re.findall(r'Ran (\d+) tests?',p.stdout)))
    total+=counted
    print(f'PASS ({counted} testow)',flush=True)
print('\n========================================',flush=True)
print(f'KI E01-E06: WSZYSTKIE TESTY OFFLINE PASS ({total})',flush=True)
print('Nie testowano platnych API ani rzeczywistej wysylki Telegrama.',flush=True)
print('========================================',flush=True)
