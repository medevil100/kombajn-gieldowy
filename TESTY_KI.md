# KI E05 — TESTY

Czytaj najpierw STAN_KI.md.

Jest to wersja uruchomiona 9.10.2026.
SHA-256 KI.py:
C6C045D37389B040117C0BB74D420B3BE2B895CE8B9D96D154FA9B9ED92AD74D

W czystym katalogu repozytorium uruchom:

python -B .\URUCHOM_TESTY_E05_OFFLINE.py

Skrypt sprawdza SHA-256 KI.py i uruchamia 19 grup testowych.
Wynik na Windows wlasciciela: 302 PASS.

Testy nie wywoluja platnych API ani nie wysylaja Telegrama.
Dane SQLite i klucze API musza pozostac poza repozytorium.

Po kazdej poprawce wymagane sa:
- testy poprawianej funkcji,
- pelna regresja,
- kontrola kontraktow i integracji,
- audyt Git staged/unstaged/untracked,
- sprawdzenie braku sekretow i artefaktow.

Dotychczasowy filtr dwoch swiec i limit 3 analiz
nie obowiazuja w E05. Nie przywracac ich.

## E06 - REGRESJA KANDYDATA

Polecenie:
python -B .\URUCHOM_TESTY_E06_OFFLINE.py

Potwierdzony wynik Windows:
311 testow PASS, 20 grup PASS.

SHA256 KI.py E06:
6CAF50D72D259E123C9C3F400CE501B72AE69CEC2B124499D6150B33BD8C3B72

Nowe testy:
test_e06_tavily_issuer.py - 9 PASS.

Historyczny test E05 pozostaje przeznaczony dla wersji E05.
Regresja offline nie potwierdza rzeczywistego API Tavily.

## E06 REST + CLI - REGRESJA 319

Wynik Windows: 319/319 testow offline PASS.
Polecenie:
python -B .\URUCHOM_TESTY_E06_CLI_DUAL_OFFLINE.py

Obejmuje dwa warianty Tavily, dotychczasowe
kontrakty KI i pole recznego tickera.
Testy uruchomiono bez platnego API i Telegrama.
Rzeczywisty CLI, GPT i Telegram nie zostaly
zweryfikowane w tym etapie.
