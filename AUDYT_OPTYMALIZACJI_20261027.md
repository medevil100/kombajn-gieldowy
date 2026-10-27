# KI 2 — audyt poprawności i optymalizacji, 27.10.2026

Projekt: C:\Users\szela\OneDrive\Desktop\KI\2 KI. Program: KI.py, adapter: tavily_cli_adapter.py. Audyt obejmuje skaner, zapis danych, panel, kompletowanie pakietu, AI i Telegram. Produkcja otwierana w mode=ro. Nie zmieniano kodu, schematu ani konfiguracji produkcji, nie restartowano usług, nie uruchamiano płatnych usług. Zapisano wyłącznie ten raport i pomiary. Test zachowania kolejki wykonano w tymczasowej, izolowanej SQLite bez HTTP.

## Podsumowanie

Program działa, lecz dalsze przyspieszanie należy poprzedzić poprawkami kolejki Telegram i ograniczania pracy sieciowej. Największe mierzalne rezerwy to duży plik SQLite z wolnymi stronami, powtarzanie historii w snapshotach, powielanie odpowiedzi Tavily i zapytania o najnowsze obserwacje. Nie stwierdzono podstaw do wymiany sprzętu ani zwiększania liczby równoległych żądań Yahoo.

## Pomiary

| Obszar | Wynik |
|---|---|
| Plik SQLite | 8 937 750 528 B, około 8,94 GB |
| Wolne strony wewnątrz pliku | 6 417 031 168 B, około 6,42 GB / 72% |
| Strony inne niż wolne | około 2,52 GB; nie jest to obietnica dokładnego rozmiaru po kompakcji |
| Obserwacje / zdarzenia / cykle | 26 409 / 3 748 / 650 w chwili odczytu; skaner nadal dopisuje dane |
| Zadania / Research / outbox | 132 / 132 / 75 |
| Ostatni zakończony nieprzerwany cykl | 27.10 12:15:22–12:20:10 UTC, około 4 min 48 s, OK |
| Próbka 50 najnowszych obserwacji | średnio 77 413 B JSON, maksymalnie 91 111 B |
| Największe pola przykładowej obserwacji | chart_history około 63 KB, carried_price_candles około 21 KB; pomiar pól innym formatowaniem JSON niż pomiar całych rekordów |
| Próbka 50 odpowiedzi Research | średnio 499 331 B, maksimum 6 561 364 B |
| Dwie ostatnie obserwacje STX.WA | mediana 8,06 ms z trzech odczytów |
| Dziesięć poprzednich według czasu | mediana 1,24 ms |
| Najnowsze odczyty wszystkich instrumentów | 453 rekordy, mediana 221,02 ms |
| RAM procesów | launcher około 66 MiB, skaner 170 MiB, panel 181 MiB; pojedynczy pomiar, nie test długotrwałego wycieku |
| Wątki | skaner 20, panel 23; brak pomiaru dowodzącego narastającego wycieku |

Pomiary SQL obejmują odbiór payloadów. Nie są benchmarkiem izolowanego dysku ani prognozą na większy zbiór. Wynik integralności i hash w AUDYT_OPTYMALIZACJI_20261027.json. Hash audytowanego KI.py odpowiada ostatniemu zapisowi wdrożenia: c00ecbc1668cce1408b602f050b6155db664b73793a6ac437f2b2d1650011c06.

Kontrola pliku: druga próba PRAGMA quick_check zakończyła się `ok` po 10,72 s. Pierwsza próba była przerwana limitem 25 s; nie była wynikiem błędów struktury. Na dysku C pozostawało około 488 GB wolnego miejsca w chwili pomiaru. Nie kompaktowano bazy.

## P1 — poprawność przed optymalizacją

### 0. Osierocona historyczna diagnostyka

foreign_key_check wykazał 81 rekordów analysis_rejections bez nadrzędnego events (84 rekordy odrzuceń ogółem). Dokładnie ten sam zestaw osieroconych identyfikatorów istnieje już w spójnej kopii z 25.10; nie powstał podczas tego audytu ani dzisiejszej zmiany pakietu. Nie oznacza to uszkodzenia fizycznego pliku, lecz niespójność relacji historycznych. Bieżące odczyty i workery działają.

Zalecenie: zabezpieczyć rekordy i sprawdzić możliwość odtworzenia nadrzędnych zdarzeń ze starszych kopii; ewentualnie wydzielić archiwalną diagnostykę z jawnym statusem braku zdarzenia. Nie usuwać ich zbiorczo i nie wyłączać FK. Kontrola quick_check nie zastępuje foreign_key_check. Pierwszą próbę quick_check przerwano po 25 sekundach; wynik dłuższej próby jest zapisany osobno w pomiarach JSON.

### 1. Ponowienia PORTFOLIO_ALERT ignorują next_attempt_at

claim_delivery wybiera PENDING tego rodzaju bez warunku terminu. Ścieżka ANALYSIS taki warunek ma. Dowód w izolowanej bazie: wiadomość PORTFOLIO_ALERT z next_attempt_at=2050-01-01 została pobrana do wysyłki w 2026 roku. Nie wysłano żadnego HTTP. Po 429 może to zużyć kolejne próby przed upływem retry_after.

Poprawka: wspólna kwalifikacja terminu dla każdego rodzaju wiadomości; testy przed terminem / w terminie / po 429. Zachować receipt, deduplikację i blokadę ponawiania niepewnych doręczeń.

### 2. Alerty SL/TP nie sprawdzają wieku ceny

portfolio_check_alerts bierze ostatnią obserwację i porównuje cenę z progiem bez sprawdzenia acquired_at, sesji i źródła ceny. Nie dowodzi to wykonania transakcji ani bieżącego przekroczenia. Potencjalnie stary odczyt może wywołać nową wiadomość. Kod portfela jest niezależny od bramek analizy ruchu.

Poprawka: jawna świeżość ceny i czas obserwacji w alertach portfela; stara cena daje stan diagnostyczny, nie aktualny alarm. Testy: weekend, brak nowego odczytu, carried price, re-arm po rzeczywistym powrocie przez próg.

### 3. Timeout fetch_market nie zatrzymuje pracy w tle

future.result(timeout=30) ogranicza oczekiwanie wywołującego. executor.shutdown(wait=False) nie przerywa już uruchomionego zadania. Docstring o twardym timeoutcie jest zbyt mocny. Przy serii wolnych wywołań może pozostać kilka pracujących żądań i wątków; obecny pomiar nie potwierdza wycieku.

Poprawka: egzekwowane timeouty transportu wszystkich etapów, ograniczona liczba zadań in-flight i kwarantanna instrumentu po timeoutcie. Jeśli konieczne jest rzeczywiste przerwanie pracy, izolacja procesu. Nie zwiększać bez pomiaru równoległości Yahoo; obsługa 429 ma pozostać nadrzędna.

### 4. Niezgodność limitu Search/Extract z bramką kompletności

Search dopuszcza osiem wyników, Extract pobiera najwyżej pięć URL, a preflight blokuje pakiet, jeśli przyjęte źródło jest tylko snippetem. Przy ponad pięciu takich źródłach część nie zostanie pobrana wyłącznie z powodu limitu kodu. Dodatkowo Extract działa przed końcowym filtrowaniem emitenta/dat, więc może kosztować dla materiału, który później jest odrzucany.

Poprawka: najpierw tania kwalifikacja domeny i czasu oraz odrzucenie ewidentnie niepasujących adresów, następnie ograniczony budżetem Extract dla potrzebnych materiałów. Jawne rozstrzygnięcie doboru pełnych źródeł lub kontrolowanej kolejnej partii. Nie omijać bramki pełnego materiału przez nazywanie snippetu pełnym tekstem.

## P2 — główne oszczędności

### 5. Indeks nie odpowiada ORDER BY id

observation_lookup=(ticker,interval,acquired_at) dobrze obsługuje historię po czasie, ale zapytania ORDER BY id DESC tworzą TEMP B-TREE. Występują w rejestracji ruchu, rankingu, bramkach wysyłki i portfelu. W izolowanym SQLite z rzeczywistymi ID i kluczami indeks (ticker,interval,id DESC) usunął dodatkowe sortowanie z planu.

Zalecenie: dodać oddzielny indeks zamiast usuwać obecny; sprawdzić plan i czas przy tych samych wynikach. Dodatkowo sprawdzono wariant grupujący MAX(id) i dołączający wybrane rekordy: w jednej spójnej transakcji zwrócił identyczne 453 ID, lecz mediana czasu z pełnymi payloadami wyniosła 247,62 ms wobec 245,78 ms bieżącego zapytania. Brak potwierdzonego przyspieszenia — nie zaleca się przepisywania tego zapytania wyłącznie dla estetyki. Najpierw ograniczyć wielkość odczytywanych payloadów, a potem ponowić benchmark.

### 6. Historia jest powtarzana w każdej obserwacji

Większość próbki snapshotu to wykres i przedziały z przeniesioną ceną. Te same zamknięte świece są ponownie serializowane, zapisywane i czytane. To koszt I/O, JSON i kopii bazy.

Zalecenie: osobna, wersjonowana historia świec; obserwacja przechowuje nowy odczyt, identyfikator rewizji i odnośnik do historii. Zachować możliwość odtworzenia historycznego raportu. Nie usuwać historii i nie włączać mechanicznego DELETE tylko dlatego, że istnieje ustawienie retencji.

### 7. Wielokrotne kopie odpowiedzi Tavily

Surowa odpowiedź jest kopiowana do adaptera, rekordu Research i kontekstu; równolegle istnieją results, content.materials, przyjęte sources i przygotowany prompt. Te same treści mogą wystąpić w kilku zagnieżdżeniach. Brak diagnostyki w promptcie oszczędza tokeny, ale nie usuwa kosztu zapisu i deserializacji.

Zalecenie: jeden niezmienny surowy rekord dostawcy, odnośniki w kontekście, osobny zaakceptowany pakiet i dokładny request. Hash treści zamiast powielania całych drzew. Nie usuwać raw_response potrzebnego do audytu i odtwarzania błędów.

### 8. Dużo małych odczytów i zapisów stanu

Service workery co sekundę odczytują ustawienia i pliki sekretów, również gdy kolejka jest pusta. Skaner wielokrotnie odczytuje listę tickerów w cyklu i ustawienia podczas oczekiwania. Heartbeaty trzech zadań zapisują bazę co około pięć sekund. Każda operacja otwiera połączenie.

Zalecenie: budzenie na zadaniu, krótki cache ustawień z rewizją i cache sekretów z kontrolą mtime; połączenia przypisane do wątku lub ograniczona pula. Zachować szybkie wyłączenie usług, zmianę konfiguracji i usuwanie tickera w trakcie cyklu. Nie przyspieszać przez wyłączenie trwałości SQLite.

### 9. Kompakcja pliku bazy

Około 6,42 GB jest już wolne wewnątrz pliku; nie oznacza to 6,42 GB aktywnych obserwacji ani uszkodzenia bazy. VACUUM może odzyskać znaczną część miejsca, ale nie naprawi modelu danych i nie jest operacją na produkcji do wykonania w ciemno.

Procedura: spójna kopia, potwierdzona ilość miejsca roboczego, okno postoju wszystkich piszących procesów, kompakcja, quick_check/foreign_key_check i porównanie liczności, kontrolowany start. Podczas audytu nie wykonywano VACUUM ani kasowania danych.

## P3 — utrzymanie i obserwowalność

- Raporty dzienne/USA mają ten sam kind PORTFOLIO_ALERT co SL/TP. Rozdzielenie uprości retry, statystyki i audyt. Zachować zatwierdzone puste raporty w dni bez sesji.
- Raporty są wyzwalane dopiero przy końcu pełnego skanu, więc rzeczywista godzina zależy od jego długości. Oddzielny harmonogram poprawi punktualność bez zwiększania zapytań rynkowych.
- Kolejne etapy rynku/Yahoo nie mają osobnych czasów i liczników żądań. Dodać metryki: czas pobrania, liczba requestów, timeouty, 429, czas SQLite, bajty JSON, rozmiar pakietu, usage dostawcy i powody zatrzymania przed AI. Pomiar znaków nie zastępuje usage tokenów.
- Ręczny i automatyczny przepływ mają odmienne prompty. Wspólny manifest jakości danych ograniczy rozjazdy, zachowując odrębne uprawnienia i bramki ręcznych narzędzi.
- Format RSI/ATR/ADX ma nowe kontrole, lecz walidacja semantyczna nadal nie jest pełnym dowodem poprawności każdego zdania. Testować nowe błędne sformułowania na zapisanych odpowiedziach bez płacenia za powtórzenia.
- Lokalny start powinien zapisywać hash kodu i wersję manifestu w runtime, żeby kolejny audyt potwierdzał wersję procesu, nie tylko wersję pliku na dysku.
- Uporządkować testy i helpery poza monolitem; nie traktować sumy zestawów testów jako liczby unikalnych przypadków, ponieważ zestawy częściowo się pokrywają.

## Kolejność prac

1. Zabezpieczenie osieroconej historii, retry Telegram i świeżość alertów portfela.
2. Rzeczywiste ograniczenie pracy sieciowej; zgranie Search/Extract i pełnego pakietu.
3. Indeks i zapytania najnowszych obserwacji z porównaniem wyników.
4. Deduplikacja surowych źródeł i historii; metryki per etap.
5. Kompakcja w uzgodnionym oknie postoju.
6. Cache z rewizją, harmonogram raportów i porządki modułów.

## Granice tego audytu

Sprawdzono aktualny kod i bieżący stan lokalny, plany i czasy SQL, próbki wielkości payloadów, procesy, stany kolejek i izolowane zachowanie retry. Użyto wyników ostatnich testów tej samej wersji kodu: 309 testów plikowych, 333 self-testy, 24 panelowe — OK; audyt wykazał jednak lukę w pokryciu retry PORTFOLIO_ALERT. Nie wykonano live-call dostawców ani nowego testowego Telegrama. W chwili pomiaru brak nowych analysis_jobs ze zdarzeniami 27.10; następny naturalny przebieg pełnego manifestu nadal wymaga obserwacji. Nie deklaruje się uniwersalnego przyspieszenia na podstawie pojedynczej próbki.
