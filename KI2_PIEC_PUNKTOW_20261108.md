# Pięć obszarów KI 2 — stan końcowy prac lokalnych z 8 listopada 2026

Projekt: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`.
Produkcja OVH: `/home/ubuntu/ki2`. 8 listopada około 17:38 UTC wdrożono KI.py,
ki2_paths.py i prompt_policy.py, z testami na VPS i kopią kodu. Lokalne narzędzia
migracji/archiwizacji oraz profil Windows nie były przenoszone do produkcji.
Osobno naprawiono brak środowiska TradingAgents: instalacja na VPS potwierdzona
8 listopada o 16:40 UTC, bez zmiany KI.py, bazy i PID usługi oraz bez restartu.
Szczegóły i granice kontroli offline: `ANALIZA_POGLEBIONA_VPS_20261108.md`.

## 1. Git — zmiany przygotowane w indeksie, commit/push czekają

Gałąź `ki-stage1-test`, HEAD nadal `ca706ba`. Jawnie wybrane pliki kodu,
testów i dokumentacji przygotowano w stagingu, bez baz, kluczy i archiwów.
Nie używano `git add .`. Oddzielna wcześniejsza zmiana użytkownika w
`_ai_review.py` pozostaje poza stagingiem i bez modyfikacji.
SHA-256: `0306397d6ac55fdada6a5afcd1edd5c62caa484a62d5ff3e2fc34e0d71415a72`.

Dokładny zakres i sumy plików: `release-plan.json` w katalogu artefaktów.
Brak dopasowań sprawdzanych wzorców sekretów w wybranych plikach; nie zastępuje
to przeglądu diffu. Commit/push pozostają po ocenie naturalnych raportów
w poniedziałek 9 listopada, zgodnie z wcześniejszym ustaleniem.

## 2. Lokalne dane i archiwa — wykonane

Aktywna lokalna konfiguracja i zweryfikowana kopia bazy są w
`C:\Users\szela\KI2-local`, poza OneDrive i pamięcią aplikacji Codex.
Klucze usług zachowano bez zmiany wartości. Lokalna baza pochodzi z
28 października i nie jest aktualną bazą VPS. Oryginał pozostał do powrotu.

Przeniesiono 35 historycznych katalogów oraz 134 luźne kopie kodu do
`C:\Users\szela\KI2-local\archives\20261108`. Łącznie 412 plików, około
84,38 GiB. Wszystkie przeszły porównanie SHA-256 przed przeniesieniem i po nim,
łącznie z plikami SQLite WAL/SHM. Nie kasowano danych ani katalogów Alchemika.
Nie dodano automatycznej retencji kasującej historyczne archiwa.
Archiwa nadal zajmują miejsce na tym samym dysku C; zmniejszono zakres danych
w OneDrive, a nie fizyczną zajętość dysku.

Szczegóły i mapa nowych lokalizacji: `LOKALNE_SCIEZKI_20261108.md`,
`ARCHIWA_LOKALNE_20261108.md`. Rotacja logów i retencja obserwacji już istniały.
Na PC nadal korzystamy ze skrótu KI - VPS; lokalnego skanera nie uruchamiano.

## 3. Testy — wykonane

`run_regression.py` uruchamia izolowaną kopię bez baz, kluczy i lokalnego profilu.
Izoluje także odziedziczone zmienne ścieżek KI2_. Jawnie kopiuje dwa pliki fixture.
Wszystkie 61 głównych modułów: 648 testów OK, dwa testy blokad Linux pominięte
na Windows. Testy wbudowane OK; panel 25 OK; uruchamianie 5 OK; pełny ekran JS OK.
Regresja przeszła także z celowo ustawioną zewnętrzną ścieżką KI2_DATA_DIR,
której testy nie użyły ani nie utworzyły.

Wyniki zestawów częściowo się pokrywają; nie sumować ich jako niezależnych
przypadków. W lokalnym Ubuntu WSL2 wykonano dodatkowo pełną regresję Python:
648 testów OK, oba testy blokad POSIX OK, pominięto dwa testy migracji Windows.
Panel i uruchamianie również OK. To Python 3.12.3. Następnie wykonano pełne
przygotowanie w środowisku VPS: wszystkie fazy regresji, w tym JavaScript, PASS;
kompilacja grafu analizy pogłębionej bez modeli i narzędzi również poprawna.
Bieżące polecenie i zakres: `TESTY_KI.md`.

## 4. Naturalne analizy AI — przygotowane, ocena po sesji

Samodzielny `ki2_readonly_audit.py` otwiera istniejącą bazę przez mode=ro i
query_only=ON. Nie importuje KI, nie wykonuje migracji, zapytań dostawców ani
wysyłek. Pokazuje liczniki pracy, pokrycie sesji, selekcję i zapisane tokeny;
nie wypisuje surowych odpowiedzi, promptów ani sekretów.
Nie został jeszcze uruchomiony na VPS. Liczniki nie dowodzą jakości odpowiedzi.

Gotowe komendy i kryteria przeglądu: `KONTROLA_PRODUKCJI_20261109.md`.
Ocenimy raporty po naturalnej sesji, bez ponawiania starych FAILED,
REVIEW_REQUIRED i UNCERTAIN oraz bez wymuszania minimum trzech spółek.
Do 16:00 nie będzie jeszcze dowodu działania na końcowej świecy sesji USA.

Potwierdzona kontrola z 8 listopada: poprawna nocna kopia 4,4 GB,
Result=success/0. Później sprawdzono obie zachowane kopie z 7 i 8 listopada
(quick_check ok, obserwacje obecne). Po usunięciu cache pip i starego oryginału
bazy sprzed optymalizacji z 30 października: 18 GB wolnego, dysk zajęty w 53%;
KI i oba timery active. Próg nadzoru zachowany. Szczegóły: PROMPTY_KI_20261108.md.
To zapis wyników użytkownika, nie nowy bezpośredni odczyt serwera.

## 5. Modularność — pierwszy zaplanowany etap wykonany

Wydzielono `ki2_paths.py`: baza, logi i ładowanie kluczy; dostosowano
`Start-KI2.ps1`. Zachowano kolejność źródeł kluczy i jawny wybór --db.
Windows używa ignorowanego profilu lokalnego; Linux zachowuje dotychczasowe
ścieżki domyślne. Brak wymaganego zewnętrznego pliku kluczy jest jawnym błędem.

Testy konfiguracji i migracji obejmują zgodność ścieżek, zachowanie kluczy,
kopiowanie SQLite bez nadpisania i powrót po błędzie.
Pozostałych części KI.py nie przebudowywano. Dalszy podział będzie wykonywany
przy konkretnych zmianach; nie jest warunkiem poniedziałkowej obserwacji.
KI.py na VPS wdrożono razem z ki2_paths.py i prompt_policy.py. Nie wysyłać tam
profilu Windows ani lokalnych kluczy. Przegląd promptów opisano w
PROMPTY_KI_20261108.md: jeden format osi,
krytyczna ocena publikacji i wspólne zasady interpretowania dowodów.

## Artefakty i pozostałe działania

Raporty poza OneDrive w katalogu:
`C:\Users\szela\.codex\visualizations\2026\10\24\01a16d6f-31ac-7bf2-86e3-26fcecc5967f`:
- `ki2-piec-punktow-20261108`: inwentarz, plan wydania, początkowa regresja;
- `ki2-przeniesienie-lokalne-20261108`: kopia kodu, testy migracji i regresja;
- `ki2-archiwa-20261108`: plan archiwizacji i kontrola izolacji testów.

Do zamknięcia pozostają: naturalna kontrola AI po poniedziałkowej sesji,
przegląd stagingu i commit/push. Wdrożenie trzech plików na VPS zostało potwierdzone
wynikiem użytkownika: success/0, panel i trzy heartbeaty świeże; kopia kodu
`/home/ubuntu/ki2/backup-prompts-20261108T173849719593Z`.

Aktualizacja 9 listopada: przegląd sześciu nowych ocen wykazał błędy schematu
i odpowiedzi. Poprawkę walidacji wdrożono na VPS około 16:26 UTC, po pełnym
PASS jego regresji i kontroli grafu offline; instalacja success/0, panel i
trzy heartbeaty potwierdzone. Kopia: backup-validation-20261109T162641451779Z.
Szczegóły: WALIDACJA_OCEN_20261109.md. Pozostaje ocena nowych odpowiedzi v2;
starych zadań nie ponawiano. Commit/push nadal nie wykonano.
