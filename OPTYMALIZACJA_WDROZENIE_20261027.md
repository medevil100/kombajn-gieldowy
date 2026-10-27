# KI 2 — wdrożenie poprawek z audytu, 27.10.2026

Projekt: C:\Users\szela\OneDrive\Desktop\KI\2 KI. Pliki: KI.py, tavily_cli_adapter.py, migrate_optimization_20261027.py i testy. Bez zmian w Alchemiku, bez płatnych testów, bez ponawiania starych analiz lub wiadomości.

## Kod

- claim_delivery respektuje next_attempt_at również dla PORTFOLIO_ALERT, także przy wyborze konkretnego ID. Przed terminem nie rezerwuje wiadomości ani nie zwiększa attempts.
- Alarmy SL/TP sprawdzają regularną sesję, wiek odczytu do piętnastu minut, prawidłowy przedział świecy, dodatnią cenę i wolumen oraz brak ceny przeniesionej. Nieświeża cena nie wyzwala ani nie uzbraja ponownie progu. Stan READY/BLOCKED i powód są zapisane w runtime. Wiadomość podaje czas odczytu i rozróżnia alarm ceny od realizacji zlecenia. Kalendarz jest nadal kalendarzem regularnych sesji, nie pełnym kalendarzem świąt.
- Yahoo korzysta z jednej puli najwyżej dwóch aktywnych zadań w każdym procesie. Po timeoutcie nadal pracujące zadanie zajmuje limit; ten sam ticker/interwał nie uruchamia duplikatu. Nasycenie puli przerywa bieżący cykl z CAPACITY_LIMITED zamiast oznaczać kolejne tickery jako uszkodzone źródła. Pobieranie bid/ask także korzysta z limitu. Nie jest to przymusowe zabijanie wątku; dla takiej gwarancji potrzebna byłaby izolacja procesu. Pozostają timeouty transportu i jawny stan ograniczenia pracy.
- Search/Extract: wstępne filtrowanie emitenta, domeny i dat przed dodatkowym pobraniem treści; jedna partia do ośmiu unikalnych potrzebnych URL. Diagnostyka rozróżnia liczbę żądanych i faktycznie podjętych pobrań; brak klucza nie oznacza wykonanego requestu. Większa partia może kosztować więcej kredytów niż pięć URL — zachowane jest usage dostawcy. Nie wykonywano testowego wywołania.
- Indeks observation_latest(ticker,interval,id DESC) usuwa dodatkowe sortowanie ostatnich odczytów. Zachowano observation_lookup dla historii według czasu. Nie przepisywano grupowania najnowszych obserwacji, ponieważ audyt nie potwierdził przyspieszenia alternatywnego zapytania.
- Pusty worker wykonuje tani test kolejki bez blokady zapisu i bez odczytywania plików sekretów. Nie cache'uje kluczy ani przełączników w sposób opóźniający zmianę konfiguracji. Heartbeaty pozostają aktywne.

## Dane i kopie

Kopia kodu i początkowy backup są w backup_20261027_optimization. Próba odświeżenia istniejącego pliku kopii została przerwana w fazie kopiowania, przed zmianą produkcyjnych danych, i oznaczona LATEST_REFRESH_INCOMPLETE.txt. Właściwą kopią sprzed konserwacji jest nowy KI.pre-maintenance.sqlite3, wykonany przez SQLite Backup API z przypiętym snapshotem i potwierdzonym quick_check.

Osierocona diagnostyka jest przenoszona do archived_analysis_rejections z oryginalnym ID, event_id, powodem, pełnym payloadem i datą. Nie tworzy się fikcyjnych zdarzeń nadrzędnych. migrate_optimization_20261027.py jest idempotentny i odmawia usunięcia źródła przy niezgodnej istniejącej kopii archiwalnej. Panel udostępnia listę archiwum w monitorze usług. Obserwacje, zdarzenia, zadania, źródła, doręczenia i świece nie są usuwane.

Konserwacja odbywa się po łagodnym zatrzymaniu i potwierdzeniu braku procesów skanera/panelu. Skrypt porównuje liczności kluczowych tabel, weryfikuje quick_check i foreign_key_check oraz odtwarza WAL. Dokładne wyniki i rozmiary po VACUUM: backup_20261027_optimization/database-maintenance.json.

Wynik wykonanej konserwacji: 8 937 750 528 → 2 561 384 448 B, odzyskano 6 376 366 080 B (około 6,38 GB). VACUUM trwał 148,25 s. quick_check=ok, naruszenia FK=0. Zachowano 26 946 obserwacji, 3 751 zdarzeń, 652 cykle, 135 zadań AI, 135 zapisów Research, 76 wiadomości, 76 pokwitowań, 31 381 świec dziennych i 452 tickery. Diagnostyka: 3 rekordy w aktywnej tabeli + 81 w archiwum, łącznie niezmienione 84. Wszystkie liczniki porównano przed/po.

Plan zapytania o dwa ostatnie odczyty korzysta z observation_latest bez TEMP B-TREE. Po wdrożeniu trzy czasy tego odczytu: 3,377 / 0,589 / 0,318 ms, mediana 0,589 ms, wobec mediany 8,06 ms w audycie. To mała próbka po indeksowaniu i kompakcji, z innym stanem cache; nie jest obietnicą proporcjonalnego przyspieszenia całego cyklu.

## Weryfikacja

317 testów plikowych, 341 self-testów, 24 testy panelu, 5 testów uruchamiania — OK. Zestawy częściowo się pokrywają. Osiem nowych regresji sprawdza: termin retry i attempts, świeżość portfela, brak stale-trigger/re-arm, realny limit pracy wątków i kwarantannę, wybór potrzebnych źródeł bez API, odczyt pustej kolejki, plan indeksu oraz pełną archiwizację i idempotencję.

Hashe kodu i wyniki testów: backup_20261027_optimization/code-verification.json. Stan po uruchomieniu w widocznym oknie zostanie zapisany w deployment.json.

## Pozostały etap strukturalny

Nie przebudowywano modelu historii świec ani nie przenoszono istniejących surowych odpowiedzi dostawców do magazynu odnośników. Taka deduplikacja wymaga osobnej migracji i testów odtwarzania historycznych raportów. VACUUM odzyskuje już wolne miejsce, ale nie rozwiązuje przyszłego wzrostu powielanych payloadów. Nie deklaruje się, że wszystkie propozycje architektoniczne audytu zostały wykonane.
