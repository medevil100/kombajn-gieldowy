# Przegląd promptów KI 2 — 8 listopada 2026

Status: wdrożona na VPS 8 listopada 2026 około 17:38 UTC; potwierdzenie w wyniku
instalatora przekazanym przez użytkownika. Bieżący kod KI.py wymaga zarówno
ki2_paths.py, jak i nowego prompt_policy.py. Nie podmieniać samego KI.py.
Nie uruchamiano nowych zadań płatnych, wysyłek Telegram ani starych zadań błędów.

To zapis wersji v1 z 8 listopada. Aktualny kontrakt KI-PROMPT-20261109-v2
wdrożono na VPS 9 listopada około 16:26 UTC; przyczyny, zmiany oraz dowody
zawiera WALIDACJA_OCEN_20261109.md. Nie ponawiano dawnych błędnych zadań.

## Co oznacza samodzielność AI

Automat ocenia materiał zebrany przez KI. Model może krytykować jego wymowę,
ale nie otrzymuje przez prompt dostępu do nowych danych. Analiza pogłębiona
ma dostęp tylko do narzędzi faktycznie udostępnionych w jej grafie.

decision.verdict pozostaje obliczoną klasyfikacją programu, kontrolowaną przez
istniejący walidator. W końcowej ocenie model może wybrać PANEL_ONLY mimo
lokalnego ALIGNED. To zachowanie działało już w kodzie; prompt wyjaśnia je teraz
wprost. Nie zmieniono lokalnych kryteriów dopuszczenia do AI ani publikacji.

## Usunięte niespójności i nowe zasady

- Prompt końcowej oceny zawierał jednocześnie limit jednego zdania do 150 znaków
  oraz późniejsze polecenie kilku zdań do 600 znaków. Teraz wybiera jeden format:
  zwykła analiza — jedno zdanie do 150 znaków na oś; końcowa — 100–600 znaków
  i co najmniej dwa zdania. Zgodnie z istniejącymi walidatorami.
- Skróconego przedziału końca sesji nie potwierdza sama flaga partial_interval.
  Instrukcja wymaga activity.structurally_shortened. Zachowuje null godzinowego
  RVOL oraz rzeczywisty wolumen; nie przelicza krótszej świecy na fikcyjną godzinę.
- Suma wolumenu całej sesji nie może być porównywana ze średnią jednej godziny.
  Bez właściwego punktu odniesienia nie wolno oceniać całego dnia jako bardziej
  lub mniej aktywnego niż zwykle.
- Źródła, pytanie i zapisane komentarze nie mogą zmieniać reguł programu.
  Dawny opis AI nie stanowi niezależnego dowodu. Model rozdziela fakty,
  obliczenia programu i interpretację, wskazuje argumenty wspierające i przeciwne.
- Emitent, czas, interwał, waluta i okres sprawozdawczy muszą pasować do wniosku.
  Brak nie oznacza zera; historyczny raport nie dowodzi bieżącej kondycji.
- Kilka wskaźników z tych samych OHLCV nie jest zbiorem niezależnych dowodów
  ani podstawą do wymyślania prawdopodobieństwa.
- Tekst osi unika również negowanych słów odrzucanych przez obecny walidator,
  np. „nie gwarantuje”. Neutralne określenie: „Dalszy ruch pozostaje nieustalony”.

Reguły wspólne mają wersję KI-PROMPT-20261108-v1. Istniejący zapis przygotowanego
żądania zachowuje ją razem z promptem; bez migracji bazy i zmiany starych zadań.
Dawny kompaktowy pakiet zdarzenia otrzymuje krótszy wariant tych zasad,
z zachowaniem istniejącego limitu rozmiaru instrukcji.

Nie zmieniono modeli, limitów odpowiedzi, liczby wywołań, schematu JSON,
walidatorów, progu selekcji ani kwot płatnych analiz. Dodatkowe instrukcje
zwiększają wejście do modelu; nie oznacza to braku kosztu dodatkowych tokenów.

## Weryfikacja i granice

Nowe osiem testów sprawdza rzeczywiście budowane żądania, zgodność formatu
z walidatorem, zachowanie kompletu danych sesji, granicę źródło/instrukcja,
odrzucanie zabronionych twierdzeń i ścieżkę ALIGNED → PANEL_ONLY bez Telegrama.
Odpowiedzi dostawcy są atrapami; test nie dowodzi odporności modelu na każdą
instrukcję ukrytą w źródle ani jakości przyszłego języka naturalnego.

Po pierwszej regresji skrócono reguły dawnego pakietu zamiast podnosić limit
testu kompaktowości. Kontrola realnego grafu TradingAgents ujawniła też końcowy
znak nowej linii usuwany przez framework; kontrakt normalizuje go przed
przekazaniem. Ponowna kompilacja grafu: READY_OFFLINE, bez modeli i narzędzi.

Końcowa regresja na Windows: 648 testów głównych modułów OK (dwa testy blokad
Linux pominięte), testy wbudowane OK, panel 25 OK, diagnostyka uruchamiania 5 OK,
pełny ekran JavaScript OK. Zestawy częściowo się pokrywają; nie sumować liczb.
Wyniki zapisano poza projektem:
`ki2-prompt-20261108/regression-final/report.json` w katalogu artefaktów Codex.
Nie stanowią potwierdzenia działania nowej wersji na VPS.

Dodatkowo tę samą wersję kodu sprawdzono w lokalnym Ubuntu WSL2 (Python 3.12.3):
648 testów OK, rzeczywiste testy blokad POSIX OK, dwa testy migracji Windows
pominięte; testy wbudowane, panel i uruchamianie OK. Raport `ki2-linux-20261108`
poza projektem. To osobna kontrola Linuksa, nie wdrożenie na VPS z Pythonem 3.14.

## Potwierdzone wdrożenie na VPS

Użytkownik przekazał kompletny wynik przygotowania i instalacji:
- suma paczki: 93deb7251d04a215ac232ef18f83474802b4eb12d5b240cf6206b879752c10c5, OK;
- osiem testów instalatora OK; komunikaty o /tmp pochodzą z testów, nie produkcji;
- pełna regresja na Pythonie VPS: self-test, wszystkie moduły, panel,
  uruchamianie i JavaScript — wszystkie fazy 0, wynik PASS;
- rzeczywisty graf analizy pogłębionej skompilowany bez modeli i narzędzi;
- jednostka ki2-prompts-install-20261108.service: success, status 0, około 4,9 s;
- panel oraz świeże heartbeaty scanner, worker_analysis i worker_telegram
  potwierdzone przez instalator po restarcie;
- kopia kodu: /home/ubuntu/ki2/backup-prompts-20261108T173849719593Z.

Zmieniono tylko KI.py, ki2_paths.py i prompt_policy.py. Instalator nie podmieniał
bazy ani kluczy i nie ponawiał historycznych zadań. Pozostałe pliki paczki służyły
do izolowanych testów. Repozytorium nie zostało w tym kroku commitowane/pushowane.
Nowe zasady dotyczą nowo przygotowywanych żądań; dawne zapisy zachowują własny prompt.
Jakość nowych odpowiedzi zostanie sprawdzona na naturalnej pracy sesji.

## Ostrzeżenie o dysku po wdrożeniu — usunięte

Nadzór zgłosił DISK_LOW: około 11,59 GiB wolnego przy progu około 11,73 GiB.
Panel, skaner i oba workery działały prawidłowo. Usunięto odtwarzalny cache pip
(301,4 MB); nadzór następnie zgłosił powrót prawidłowego stanu.

Sprawdzono dwie zachowywane kopie z 7 i 8 listopada: quick_check = ok,
obserwacje obecne. Po kontroli ścieżki, braku dowiązań, rozmiaru starej bazy
6 541 127 680 bajtów, pustego WAL i nieaktywnego zadania backupu użytkownik
usunął wyłącznie KI.matrix.sqlite3 oraz jej SHM/WAL z katalogu
`/home/ubuntu/ki2/backup-db-storage-20261030T201503937265Z`, a następnie pusty katalog.
To nie jest kopia bieżącego kodu promptów — ta pozostaje zachowana.

Końcowy wynik użytkownika: dysk 38G, zajęte 20G, wolne 18G, 53%;
ki2, ki2-guardian.timer i ki2-backup.timer — active. Dwie zweryfikowane nocne
kopie i baza produkcyjna pozostają na VPS. Próg nadzoru nie był obniżany.

Żaden prompt nie gwarantuje braku luk. Nadal obowiązują walidatory i odrębna
kontrola kilku naturalnych raportów z sesji. Nie ponawiać historycznych zadań
w celu uzyskania ładniejszego wyniku i nie luzować bramek dla większej liczby ocen.

Oficjalne wskazówki: [projektowanie promptów](https://developers.openai.com/api/docs/guides/prompt-engineering)
i [przypadki typowe, brzegowe oraz przeciwstawne w ewaluacji](https://developers.openai.com/api/docs/guides/evaluation-best-practices).
