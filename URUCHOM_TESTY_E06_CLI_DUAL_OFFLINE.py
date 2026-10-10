"""Offline validation KI E06 REST + CLI; no calls to paid services."""
from pathlib import Path
import hashlib
import os
import re
import subprocess
import sys

root=Path(__file__).resolve().parent
EXPECTED={
    'KI.py':'39CBF235078BC202C0B5C776EFF2D60B4DB4A3A9984A84FD110F83932719E9E5',
    'tavily_cli_adapter.py':'80E71B70140782AADD663762571614D99E8EA10A8BD26E5B86FCA64142F6952B',
    'test_e06_cli_dual_contract.py':'FA83BE197BFC32E0CCF240E8B9085698CC1D8AD5F7E6C7DD14BD4184BE7B4860',
}
for name,digest in EXPECTED.items():
    p=root/name
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest().upper()!=digest:
        sys.exit('STOP: brak lub inna zawartosc pliku '+name)
for path in root.iterdir():
    if path.is_file() and (path.suffix.lower() in ('.db','.sqlite','.sqlite3') or path.name.endswith(('.sqlite3-wal','.sqlite3-shm'))):
        sys.exit('STOP: baza danych w katalogu testowym: '+path.name)
if (root/'.streamlit/secrets.toml').exists():
    sys.exit('STOP: wykryto sekrety w katalogu testowym.')

cases=[
    ('Wbudowana regresja KI',['KI.py','--self-test']),
    ('A+B - kontrakt GPT',['test_ab_contract.py']),
    ('C - kontrakt Tavily REST',['test_c_tavily_contract.py']),
    ('D - raport',['test_d_report_contract.py']),
    ('E01-E03 - SQLite i przelaczniki',['test_e_integracja_contract.py']),
    ('E04 - kwalifikacja bez limitu',['test_e04_kwalifikacja_contract.py']),
    ('E05 - dowody aktywnosci rynku',['test_e05_aktywnosc.py']),
    ('E06 - kwalifikacja REST',['test_e06_tavily_issuer.py']),
    ('E06 CLI - kontrakt offline',['test_e06_cli_dual_contract.py']),
    ('GPW - alert/wskazniki',['test_gpw_alert_indicator_contract.py']),
    ('GPW - cena bazowa',['test_price_matrix.py']),
    ('GPW - daty zrodel',['test_tavily_page_dates.py']),
    ('GPW - wyszukiwanie',['test_tavily_search_contract.py']),
    ('GPW - dane liczbowe',['test_manual_numeric_contract.py']),
    ('GPW - walidator reczny',['test_manual_validation_20261008.py']),
    ('GPW - reguly numeryczne',['test_numeric_rules.py']),
    ('GPW - raport reczny',['test_research_v3.py']),
    ('GPW - bid/ask',['test_bid_ask.py']),
    ('Panel Streamlit',['KI.py','--panel-test']),
    ('Uruchamianie diagnostyczne',['KI.py','--launch-test']),
    ('Dodatkowy panel Tavily',['test_tavily_panel.py']),
]
print('E06 DWA WARIANTY: sprawdzono kontrolne SHA256',flush=True)
env=dict(os.environ)
env['PYTHONDONTWRITEBYTECODE']='1'
total=0
for n,(name,command) in enumerate(cases,1):
    print('\nTEST '+str(n)+'/'+str(len(cases))+': '+name,flush=True)
    p=subprocess.run([sys.executable,'-B',*command],cwd=root,env=env,
                     text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                     encoding='utf-8',errors='replace')
    if p.returncode:
        print(p.stdout[-14000:],flush=True)
        sys.exit('STOP: FAIL — '+name)
    count=sum(map(int,re.findall(r'Ran (\d+) tests?',p.stdout)))
    total+=count
    print('PASS: '+str(count)+' testow',flush=True)
if total!=319:
    sys.exit('STOP: niezgodna liczba testow '+str(total)+' (wymagane 319).')
print('\nKI E06 DWA WARIANTY: 319/319 TESTOW OFFLINE PASS',flush=True)
print('Realny Tavily CLI, GPT i Telegram wymagaja odrebnej weryfikacji.',flush=True)
