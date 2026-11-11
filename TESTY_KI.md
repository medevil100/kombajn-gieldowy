# Aktualna regresja KI 2 — 11 listopada 2026

Aktualne źródła: pełna regresja Windows i Ubuntu WSL po poprawce kolorów
historycznych — 522 testy wbudowane, 780 testów modułów, 26 testów panelu
i 5 testów uruchamiania PASS. JavaScript PASS na Windows. Testy instalatora:
12 PASS na obu platformach. Działający Streamlit w Chromium: świeże i
historyczne raporty przy 360/768/1440 px zachowują cztery kolory, 29 wierszy,
bez przepełnienia poziomego. Bez produkcyjnej bazy i zapytań dostawców.

Pierwsze kolory wskaźników wdrożono na VPS 11.11 o 16:43 UTC, pełna regresja
VPS PASS, panel i trzy heartbeaty potwierdzone. Właściciel następnie potwierdził
działanie. Dodatkowa lokalna poprawka zachowania kolorów raportu historycznego
jest przetestowana, ale nie ma potwierdzonego wdrożenia VPS; patrz
KOLORY_HISTORII_POPRAWKA_20261111.md.

Naturalny audyt VPS do 11.11 16:03 UTC potwierdza 41 zakończonych ocen,
14 zbiorczych wiadomości DELIVERED i 2 alerty portfela DELIVERED; guardian
HEALTHY. To potwierdzenie pracy przepływu, nie jakości inwestycyjnej wyborów.
Szczegóły i ograniczenia: PUNKT_WZNOWIENIA_20261111.md.

## Poprzednie etapy — wyniki historyczne

Wpisywanie tickera w orkiestratorze — wdrożono, ORKIESTRATOR_TICKER_20261110.md.
Pole tekstowe zamiast listy, pusty początek, normalizacja symbolu i komunikat
braku zapisu; odczyt nie uruchamia API. Pełna regresja Windows/Ubuntu WSL:
769 testów modułów, wbudowane 522, panel 26 i uruchamianie 5 OK; JavaScript
OK na Windows. Dwanaście testów instalatora OK na obu systemach. Polityka
TOP 5 i główny plik KI.py pozostają bez zmian. VPS 17:28 UTC: pełne testy
PASS, graf offline, panel i trzy świeże heartbeaty; instalacja success/0.
Rzeczywiste wpisywanie na urządzeniu pozostaje do potwierdzenia.

Orkiestrator decyzji — wdrożono, ORKIESTRATOR_KI_PROJEKT_20261110.md.
Windows i Ubuntu WSL: 769 testów modułów, wbudowane 522, panel 26
i uruchamianie 5 OK (pominięcia zależne od platformy). JavaScript pełnego
ekranu OK na Windows; Linux bez Node nie uruchamia tej fazy. Siedemnaście
nowych testów orkiestratora obejmuje role wzrost/spadek, pełny rzeczywisty
plan z pivotów i ATR, brak planu, braki danych, ryzyko, poprzednią ocenę,
monotoniczny zapis stanu, prompt, jedną zbiorczą publikację, widok mobilny
i zatrzymaną ocenę bez ponowienia. Dwanaście testów instalatora na obu
systemach OK, w tym dokładne wersje opcjonalnych plików testowych.
VPS 17:04 UTC: dwanaście testów instalatora i wszystkie fazy regresji PASS,
graf offline, panel i trzy świeże heartbeaty potwierdzone; success/0.
Nie wykonano rzeczywistych testowych wywołań dostawców ani Telegrama.
Naturalne nowe decyzje i ich doręczenia nadal wymagają potwierdzenia.

Wstępne oceny AI — wdrożono, WSTEPNE_OCENY_AI_20261110.md.
Pełna regresja Windows i Ubuntu WSL: 751 testów modułów, wbudowane 522,
panel 26 i uruchamianie 5 OK (pominięcia zależne od platformy); JavaScript
OK na Windows. Po tej regresji dodano jeden test maksymalnej wiadomości
z sześcioma wstępnymi ocenami; cały nowy moduł 17 testów przeszedł ponownie
na obu systemach. Kod wykonawczy nie zmienił się między tymi kontrolami.
Dziewięć testów instalatora na Windows i Linux OK. Sprawdzono przejście
skaner → wstępna ocena → TOP 5 → jeden Telegram na atrapach, blokady danych,
ryzyko, deduplikację i wspólny limit z potwierdzonymi sygnałami. VPS:
pełna regresja PASS, graf offline, panel i trzy świeże heartbeaty potwierdzone.
Wdrożenie 16:17 UTC po bezpiecznym ponowieniu zajętej blokady. Rzeczywiste
nowe oceny i doręczenia pozostają niepotwierdzone. Bez testów dostawców.

Koordynator końcowej oceny — wdrożono, KOORDYNATOR_OCEN_20261110.md.
Windows i Ubuntu WSL: 735 testów modułów, wbudowane 522, panel 26
i uruchamianie 5 zakończone poprawnie (pominięcia zależne od platformy).
JavaScript pełnego ekranu OK na Windows; Linux bez Node pomija tę fazę.
Windowsowy test uruchomienia wymagał wyjścia poza piaskownicę po odmowie
połączenia lokalnego; pozostałe fazy przeszły w piaskownicy.
Nowe 24 testy obejmują konkretne przesłanki decyzji, stare kontrakty,
przepływ do TOP 5 i pojedynczej wysyłki na atrapie, ponawianie brakującej
bazy dziennej, kalendarze świąt i skrócone sesje. Bez rzeczywistych API,
produkcyjnej bazy i wiadomości testowych. VPS 14:56 UTC: dziewięć testów
instalatora i wszystkie pięć faz regresji PASS, graf offline, panel i trzy
świeże heartbeaty potwierdzone. Jakość naturalnych nowych ocen i doręczenie
Telegrama pozostają do potwierdzenia.

Harmonogram raportów — wdrożono, RAPORTY_SESJI_20261109.md.
Osiem testów kalendarzy XWAR/XNYS oraz kolejki SQLite: zima/lato,
różne terminy zmian czasu, święta i weekendy, skrócona sesja USA,
ograniczone opóźnienie, brak podwójnej wysyłki i zachowanie starych znaczników.
Dziewięć testów instalatora na Windows i Linux OK. Pełna regresja obu
systemów: 711 testów modułów (pominięcia zależne od platformy), wbudowane
522, panel 26 i uruchamianie 5 OK; JavaScript OK na Windows.
VPS 22:02 UTC: pełna regresja PASS, graf offline, panel i trzy heartbeaty
potwierdzone. Rzeczywista godzina kolejnego raportu wymaga potwierdzenia.
Odczyt VPS potwierdził działające wyszukiwania Tavily i przyjęte źródła;
nie wykonywano nowego zapytania ani zmiany filtrów do tej diagnostyki.

Oceny oparte na dowodach — wdrożono, OCENY_AI_DOWODY_20261109.md.
703 testy modułów Windows/Linux OK; wbudowane 522, panel 26, uruchamianie 5.
Dwanaście nowych testów kontraktu, katalogu, pełnej/skróconej sesji, stanów
RSI i ofert, zachowania starych żądań, surowej odpowiedzi, TOP 5 oraz pełnego
przepływu Telegrama na atrapie. Nowy model ani drugie wywołanie nie zostały
dodane. VPS 21:34 UTC: pełna regresja PASS, panel i trzy heartbeaty potwierdzone.
Rzeczywista ocena kolejnej otwartej sesji i doręczenie czekają na potwierdzenie.

Wybrane okazje TOP 5 — wdrożono, WYBRANE_OKAZJE_TOP5_20261109.md.
691 testów modułów Windows/Linux OK; wbudowane 522, panel 26, uruchamianie 5.
Jedenaście testów nowego widoku, dziewięć testów instalatora na obu systemach,
graf READY_OFFLINE. Układ telefonu i tabletu sprawdzony w odizolowanej
przeglądarce na danych testowych. Bez rzeczywistych wywołań AI/Tavily/Yahoo
i testowych wiadomości. VPS 19:21 UTC: panel i trzy heartbeaty potwierdzone.
Rzeczywisty widok na urządzeniach i nowa poprawna ocena pozostają do sprawdzenia.

Końcowe oceny po zapętleniu FBIO — wdrożono v3, OCENY_KONTRAKT_V3_20261109.md.
680 testów modułów Windows/Linux OK; wbudowane 522, panel 25, uruchamianie 5.
Liczba pełnych zdań w schemacie, brak sztucznego minimum znaków, blokada
powtórzeń i puste hipotezy w nowych końcowych ocenach. Historyczne zadania
pozostają bez zmian. Wdrożenie VPS 18:29 UTC: pełna regresja PASS, panel i trzy
heartbeaty potwierdzone. Bez rzeczywistych wywołań testowych; naturalna ocena v3
i doręczenie pozostają do potwierdzenia.

Ręczna Analiza GPT — kontrakt cyfr Unicode i progów: 672 testy modułów Windows
i Linux OK, testy wbudowane 522, panel 25, uruchamianie 5 OK. JavaScript
i wszystkie alfabety cyfr sprawdzone na Windows; Linux bez Node.js pomija ten
jeden test. Osiem testów instalatora na obu systemach OK; graf READY_OFFLINE.
Wdrożono na VPS 17:54 UTC: ANALIZA_GPT_CYFRY_20261109.md. Pełna regresja VPS
PASS, panel i trzy heartbeaty potwierdzone. Bez zapytań płatnych; poprawny
rzeczywisty raport nowej ręcznej analizy nadal wymaga potwierdzenia.

Późniejsza aktualizacja 9 listopada: kandydat selekcji w trakcie sesji,
OCENY_W_TRAKCIE_SESJI_20261109.md. 667 testów modułów Windows/WSL OK, po dwa
pominięcia zależne od systemu; wbudowane, panel 25, uruchamianie 5 i graf offline
OK. JavaScript OK na Windows; osiem testów instalatora OK na obu systemach.
Selekcja w trakcie sesji została wdrożona o 17:24 UTC, panel i trzy heartbeaty
potwierdzone. Naturalna poprawna ocena i wysyłka nadal wymagają potwierdzenia.

Aktualizacja 9 listopada: poprawka kontraktu cytatów i walidacji końcowych ocen.
658 testów modułów OK zarówno na Windows, jak i Ubuntu WSL2; po dwa pominięcia
dotyczą wyłącznie drugiego systemu. Testy wbudowane, panel 25, uruchamianie 5 OK;
JavaScript OK na Windows, graf TradingAgents skompilowany offline. Szczegóły
i granice w WALIDACJA_OCEN_20261109.md. Dodatkowe testy na VPS potwierdził
użytkownik: wszystkie pięć faz PASS, graf offline poprawny; wdrożenie około
16:26 UTC zakończone success/0, panel i trzy świeże heartbeaty potwierdzone.
Nie jest to jeszcze ocena jakości nowych odpowiedzi dostawcy.

Jedno polecenie dla bieżącego kodu:

```powershell
python -B -X utf8 .\run_regression.py
```

Na Linuxie: `python -B -X utf8 run_regression.py` z właściwego środowiska KI.
Wyniki i izolowana kopia kodu trafiają do nowego katalogu tymczasowego.
Można podać nowy katalog poza projektem przez `--output SCIEZKA`.

Skrypt uruchamia testy wbudowane, wszystkie główne pliki `test_*.py`, panel,
diagnostyczne uruchamianie i test JavaScript pełnego ekranu, jeśli dostępny jest Node.js.
Nie importuje testów z kopii Alchemika ani archiwów. Kopiuje dwa jawne pliki
JSON będące danymi testowymi, bez baz SQLite i konfiguracji usług.
Procesy testowe mają osobny katalog domowy i nie otrzymują odziedziczonych kluczy API.
Nie dziedziczą również zmiennych ścieżek KI2_, więc nie kierują się do danych roboczych.
Nie uruchamia sond płatnych dostawców, wysyłek próbnych ani skanera rynku.

`--list` wypisuje aktualne moduły bez wykonywania testów.
`--phase all-python-modules` pozwala powtórzyć wyłącznie wybraną fazę.
Testy częściowe nie oznaczają przejścia całego zestawu.
Raport JSON i oddzielne logi pokazują wyniki oraz pominięte fazy.

Potwierdzone 8 listopada na Windows po migracji lokalnych ścieżek i poprawce promptów:
- Wszystkie pliki Python: 648 testów, OK, 2 pominięte testy blokad Linux.
- Testy wbudowane: grupy 17 + 46 + 42 + 7 + 29 + 381, OK; 2 pominięcia Linux.
- Panel: 25 testów OK.
- Uruchamianie diagnostyczne: 5 testów OK.
- JavaScript pełnego ekranu: OK.

Liczby częściowo się pokrywają — nie należy sumować ich jako niezależnych przypadków.
Na VPS należy dodatkowo wykonać testy specyficzne dla Linuksa.
Wyniki offline nie potwierdzają jakości nowych odpowiedzi AI ani skuteczności inwestycyjnej.
Osiem nowych testów promptów obejmuje format osi, krytyczną decyzję PANEL_ONLY,
przekazywanie źródeł jako danych oraz komplet sesji bez zastępczego RVOL.
Realny graf TradingAgents skompilowano offline z nowym kontraktem; bez wywołań modeli.

### Linux — kontrola wykonana lokalnie w WSL

8 listopada: Ubuntu 24.04.4, WSL2, Python 3.12.3, osobny venv i izolowana kopia
tego samego kodu. 648 testów OK, w tym oba rzeczywiste testy blokad POSIX;
pominięto wyłącznie dwa testy migracji przeznaczone dla Windows. Testy wbudowane
OK, panel 25 OK, diagnostyka uruchamiania 5 OK. JavaScript nie był ponawiany
w WSL bez Node; jego test przeszedł wcześniej na Windows.

Raport: `ki2-linux-20261108/report.json` poza projektem w katalogu artefaktów
Codex, wraz z logami i listą zainstalowanych wersji. Kod, bazy i usługi VPS
nie były zmieniane. WSL z Pythonem 3.12 nie zastępuje kontroli przed wdrożeniem
w dokładnym środowisku VPS z Pythonem 3.14. Automatyczne SSH zostało odrzucone
przez serwer (`Permission denied (publickey)`); nie potwierdzono tam nowego kodu.

Późniejsze potwierdzenie użytkownika z VPS, 8 listopada około 17:38 UTC:
osiem testów instalatora OK, pełna regresja (self-test, wszystkie moduły,
panel, uruchamianie i JavaScript) PASS. Kompilacja grafu TradingAgents bez
modeli i narzędzi poprawna. Wdrożenie trzech plików zakończone success/0,
panel i świeże trzy heartbeaty potwierdzone. Szczegóły: PROMPTY_KI_20261108.md.

## Historyczne instrukcje E05/E06

Poniższe sumy kontrolne i liczby odnoszą się do dawnych wersji. Nie stanowią
aktualnego warunku uruchomienia regresji KI 2.

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
