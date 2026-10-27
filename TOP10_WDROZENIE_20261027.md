# KI 2 — dwa rankingi i diagnostyka, 27.10.2026

Projekt: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`. VPS odłożony do zakończenia testów. Commit i push pozostają po ocenie wyników o 23:00.

## Panel i punktacja

Panel pokazuje zielone TOP 10 wzrostów i czerwone TOP 10 spadków. Limity są niezależne; nadwyżka jednego kierunku nie wypiera drugiego. Obie listy korzystają z takiego samego wzoru: zgodność świecy z kierunkiem od bazy, położenie w odpowiednich skrajnych 20% zakresu, wolumen, przyrost aktywności, MACD, SMA i DI oraz osobny kontekst. Nowe rankingi mają `score_version=2` i `score_direction`. Punktacja nie potwierdza możliwości realizacji transakcji. Usunięto etykietę „Okazja” z nowych rekordów rankingu. Starsze dane pozostają w historii.

Karty zachowują wskaźniki, ryzyko, źródła i kolorowe poziomy. Dodatkowo pokazują zapisany wniosek AI i pełny raport z oryginalnego odczytu; czas tego odczytu jest jawny. Bieżący plan może pochodzić z nowszego odczytu. Wzrosty mają dotychczasowy warunkowy plan LONG. Przy spadkach liczone są wsparcia, opory i przestrzeń, bez tworzenia planu kupna lub założenia dostępności shorta. Brak poziomów jest jawny.

Podział panelu jest odczytem, nie uruchamia dodatkowych analiz ani wysyłek. Audyt wykazał, że poprzedni opis „3 analizy na 15 minut” nie odpowiadał aktualnemu kodowi rezerwującemu wszystkie kwalifikujące się rekordy. Usunięto nieprawdziwy opis; nie dodano ani nie zwiększono limitów kosztowych. Pozostają istniejące bramki i pojedyncze płatne wywołania na zdarzenie.

## AI i źródła

W 12 historycznych blokadach niepełnej treści Extract zapisał 17 błędów „Failed to fetch url” i jeden 404. W jednej partii było 1–4 adresów: limit 8 nie był przyczyną. Nie wykonano ponownych zapytań. Nie jest to dowód odzyskania tych stron.

Niepełne fragmenty trafiają teraz do diagnostyki, a nie do listy źródeł dla modelu. Jeżeli pozostaną pełne zweryfikowane źródła, mogą być użyte. Bez nich AI może interpretować wyłącznie poprawne dane techniczne i tylko przy sensownym pytaniu dopuszczonym przez preflight. Nie wolno przypisywać przyczyny nieprzeczytanej publikacji. Bez pytania zadanie pozostaje lokalne. Bramka nadal odrzuca niepełne źródło, gdy takie znalazłoby się w pakiecie.

Nowy ścisły schemat cytatów pozwala wybierać dosłowne krótkie fragmenty pełnego źródła; lokalna walidacja nadal sprawdza ich przypisanie i dosłowność. Pełne treści nie są obcinane. Kontrola aktywności wymaga ograniczenia oceny przy niepełnych danych — również przy brakującym RVOL, co ujawnił rzeczywisty pierwszy raport v3. Historycznych raportów i wysyłek nie wznowiono.

Stary prompt wydzielono do osobnej funkcji używanej tylko w ścieżce zgodności. W nowej ścieżce nie jest budowany; usunięto też ponowne budowanie filtrów snapshotu i danych zdarzenia. Dla nowych zadań pełna odpowiedź Tavily pozostaje w `research_requests.raw_response`, a kontekst zawiera odnośnik zamiast drugiej kopii. To zmiana zapisu przyszłych zdarzeń, bez migracji dotychczasowych payloadów.

## Diagnostyka i baza

Logi procesów przechodzą przez czytniki potoków do standardowego `RotatingFileHandler`: plik aktywny 20 MiB, pięć archiwów, czas UTC, poziom i PID procesu. Początkowy stary duży plik jest zachowany w archiwum, więc przez pierwszy obrót może być większy niż nowy limit. Rotacja jest ograniczona liczbą plików. Błędy parsowania historii spreadu zawierają teraz identyfikator zdarzenia i ticker.

Monitor ma statystyki jakości według wersji formatu, faktycznie zapisane tokeny i kredyty, wyniki Extract i powody filtrów. Koszt bez rozliczenia pozostaje nieznany. Cięższe podsumowanie wymaga zaznaczenia pola odczytu statystyk, aby nie przeliczać setek MB kontekstów przy zwykłym odświeżeniu. Osobny widok pokazuje wyniki ostatniego zakończonego cyklu, w tym odrzucenia wcześniejsze niż rezerwacja alertu.

Audyt wielkości payloadów: obserwacje 2,36 GB, zdarzenia 282 MB, cykle 209 MB, odpowiedzi Tavily 200 MB, konteksty analizy 206 MB. Szczegóły w `backup_20261027_top10/storage-audit.json`. Nie wykonano kasowania obserwacji, deduplikacji historycznej ani VACUUM. Sześć starych cykli RUNNING oznaczono INTERRUPTED z metadanymi odzyskania; pełne rekordy sprzed zmiany zapisano w `old-cycles-before.json`.

## Weryfikacja i pozostała praca

Logi testów: `top10-*-20261027.log`. Weryfikacja obejmuje symetrię punktów, 10 pozycji na kierunek na rzeczywistej matrycy SQLite, poziomy przy spadku, rozdzielenie niepełnych źródeł, rotację i Unicode, zachowanie aktywnych cykli, statystyki jakości, ograniczenie aktywności, dosłowne cytaty i brak kopii surowej odpowiedzi w nowym kontekście. Stan wdrożenia i hasze w `backup_20261027_top10/deployment.json`.

Pozostaje obserwacja naturalnych cykli i ocena nowych odpowiedzi. Historyczna deduplikacja wymaga osobnej migracji z kontrolą odtwarzania raportów; nie została wykonana. Żadne ręczne płatne testy ani dodatkowe wiadomości Telegram nie zostały uruchomione.
