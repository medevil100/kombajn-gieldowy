# KI 2 — podsumowanie wykonanych prac

Data: 27 października 2026. Czasy podawane użytkownikowi: Europe/Berlin.

## 1. Właściwy projekt i zapis w Git

- Folder: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`.
- Program: `KI.py`.
- Baza lokalna: `KI.matrix.sqlite3`.
- Panel: `http://127.0.0.1:8501/`.
- Alchemik i samodzielny program `C:\Tavli\market-researcher` to oddzielne projekty.
- Gałąź Git: `ki-stage1-test`.
- Commit: `14493f33b9a6806ca83c248e746b1b7fdc76db95` (`14493f3`).
- Tytuł: „Usprawnij KI 2: analizy AI, rankingi kierunkowe i diagnostyka”.
- Commit obejmuje 40 plików kodu, testów i dokumentacji KI 2. Push nie został wykonany.
- Bazy, sekrety, logi, kopie robocze Alchemika i niezależna zmiana `_ai_review.py` nie weszły do tego commitu. Katalog roboczy nadal zawiera materiały spoza jego zakresu.
- Niniejsze podsumowanie powstało po commicie; jest osobnym plikiem lokalnym do ewentualnego dołączenia przed jutrzejszym pushem.

## 2. Skaner i dane rynkowe

- Uporządkowano pracę na właściwej bazie KI 2 i ochronę przed równoległym uruchomieniem drugiego skanera.
- Baza ruchu jest stałym zamknięciem poprzedniej zakończonej sesji. Cofnięcie ceny nie przesuwa bazy.
- Potwierdzenie wymaga trzech odczytów z nową aktywnością rynku w oknie godziny; samo ponowne pobranie tej samej informacji nie zwiększa potwierdzenia.
- Rozdzielono detekcję ruchu, zgodność wskazań i ryzyko wykonania transakcji.
- Dodano ograniczoną pulę zadań Yahoo, limity oczekiwania i ochronę przed uruchamianiem kolejnych identycznych zadań, gdy poprzednie pobranie nadal trwa.
- Zabezpieczono alerty portfelowe przed użyciem starej lub przeniesionej ceny, braku aktywności i danych spoza regularnej sesji.
- Zachowano rozróżnienie świec otwartych, zamkniętych i skróconych. Częściowy wolumen nie jest oceną całej zakończonej godziny.
- Usunięto wskazane 25 tickerów powyżej 5 USD z watchlisty i aktywnej matrycy, zachowując historię. Przy tej operacji lista zmniejszyła się z 452 do 427 spółek. Ostatni odczyt podczas tworzenia tego dokumentu pokazuje 428; lista jest później edytowalna i nie jest zamrożona przez commit.

## 3. Panel: TOP 10 wzrostów i TOP 10 spadków

- Zielona lista TOP 10 wzrostów i czerwona lista TOP 10 spadków mają niezależne limity wyświetlania.
- Punktacja jest symetryczna: ocenia zgodność techniki i aktywności z kierunkiem ruchu, zamiast premiować wyłącznie wzrosty.
- Nowe rekordy zawierają kierunek punktacji i wersję sposobu oceny. Nowe karty nie nazywają samego wykrytego ruchu „okazją”.
- Obie listy zachowują dane ceny i bazy, aktywność, ryzyko, wskaźniki, źródła i stan analizy.
- Dostępny jest zapisany wspólny wniosek AI oraz rozwijana pełna analiza z czasem oryginalnego odczytu. Jest rozróżnienie pomiędzy czasem zapisanej analizy a nowszą ceną i poziomami na karcie.
- Podział panelu nie uruchamia dodatkowych płatnych zapytań ani dodatkowych wysyłek.

## 4. Wsparcia, opory oraz SL/TP

- Poziomy oblicza program lokalnie, przed wywołaniem AI. Model otrzymuje plan do oceny jego spójności i ograniczeń.
- Wykorzystywane są pełne zamknięte świece 1h z obrotem: co najmniej 20, maksymalnie ostatnie 60.
- Wsparcia i opory wynikają z lokalnych ekstremów potwierdzonych przez dwa sąsiednie słupki po obu stronach.
- Dla wzrostu plan LONG pokazuje cenę odniesienia wejścia, SL, TP1, TP2 i relację potencjalnego zysku do ryzyka.
- SL uwzględnia wsparcie i ATR; TP1 i TP2 to dwa odrębne opory. Brak danych lub poziomów daje jawny powód braku planu.
- Przy spadkach dostępne są wsparcia, opory i przestrzeń ruchu, jeżeli dane pozwalają je potwierdzić. Nie powstaje automatyczny plan kupna ani założenie dostępności krótkiej sprzedaży.
- Odległości procentowe do wsparcia i najbliższego oporu liczone są od ostatniej ceny.
- Kolory: SL czerwony, TP zielone, wsparcie niebieskie, opór fioletowy. Poziomy mają osobne kolumny i etykiety.
- Bez aktualnych ofert plan jest orientacyjny. Uwzględnienie dostępnego spreadu oraz ograniczenia kosztów są jawne; prowizje i poślizg nie są ujęte.
- Słaba relacja TP1 do ryzyka jest wyraźnie opisana. Poziomy nie potwierdzają wykonalności transakcji i nie składają zleceń.
- Wymagana jest świeża cena; zapisany plan po swoim okresie ważności jest oznaczany jako historyczny.

## 5. AI: pełny pakiet i kontrola kosztu

- Naprawiono błąd `NameError: snap is not defined` w ścieżce analizy. Historycznych płatnych pytań nie powtórzono automatycznie.
- Przed płatnym AI działa lokalny preflight: kontrola tożsamości, czasu, porównywalności, jakości materiału i istnienia pytania wymagającego modelu.
- Prosty opis ruchu bez wartościowego pytania może pozostać oceną lokalną, bez kosztu AI.
- Pakiet zawiera lokalną ocenę detekcji, wskaźników, aktywności, ryzyka, ofert, poprzedniego odczytu, źródeł i planu.
- Gotowe żądanie jest zapisywane przed wywołaniem dostawcy. Zbyt duży pakiet jest zatrzymywany zamiast potajemnie obcinany.
- Manifest v3 wymaga osobnych pól `movement`, `activity`, `risk`. Program składa z nich zwięzły wniosek, bez dopisywania za model brakujących zdań.
- Walidacja kontroluje liczby, metryki, dosłowność cytatów, wybrane sprzeczności i nieudokumentowane narracje o sentymencie, realizacji zysków i zachowaniu inwestorów.
- Dodano wymaganie jawnego ograniczenia oceny przy niepełnej aktywności, także przy brakującym RVOL.
- Niepełna analiza trafia do `REVIEW_REQUIRED`; nie jest publikowana ani automatycznie ponawiana jako kolejne płatne pytanie. Surowa odpowiedź pozostaje dostępna do kontroli.
- Starsze zapisane formaty pozostają obsługiwane.
- Kontrole tekstowe są zabezpieczeniami konkretnych przypadków, nie gwarancją poprawności każdego możliwego zdania modelu.

## 6. Tavily i materiał źródłowy

- Wyszukiwanie uwzględnia emitenta, dozwolone domeny, datę oraz okno dostępności materiału.
- Pełne przyjęte treści pozostają materiałem analizy; fragment Search nie jest traktowany jako pełny artykuł.
- Extract jest wykonywany tylko dla kwalifikujących się adresów wymagających pełnej treści, w jednej ograniczonej partii, bez automatycznych ponowień płatnych prób.
- Audyt 12 historycznych blokad wykazał 17 błędów pobrania strony i jeden błąd 404. Partie miały 1–4 adresów, więc limit 8 nie był przyczyną. Nie oznacza to odzyskania niedostępnych stron.
- Niepełne wyniki są teraz diagnostyką, a nie źródłami przekazywanymi modelowi. Bez pełnych źródeł możliwa jest wyłącznie uzasadniona interpretacja techniczna dopuszczona przez preflight; przyczyna ruchu może pozostać nieustalona.
- Nowy schemat umożliwia wybór dosłownych krótkich fragmentów zweryfikowanego źródła; nadal sprawdzane jest przypisanie cytatu do właściwego źródła.
- W nowych zadaniach pełna surowa odpowiedź jest zachowana w `research_requests.raw_response`; kontekst ma odnośnik zamiast dodatkowej pełnej kopii odpowiedzi. Nie zmigrowano historycznych kontekstów.

## 7. Telegram

- Wiadomość jest krótka: potwierdzony kierunek, cena i zmiana od bazy, ocena wskazań, aktywność, ryzyko, wspólny wniosek AI i warunkowy plan SL/TP.
- Usunięto listę wszystkich wskaźników z krótkiego komunikatu; pełny materiał pozostaje w panelu.
- Brak bid/ask oznacza brak oceny spreadu i warunków wykonania, a nie zapewnienie o małym ryzyku.
- Zachowano kontrolę aktualności ruchu, kolejkę, przypisanie odbiorcy i potwierdzenia API. Niepewne doręczenie nie powoduje automatycznego wysłania duplikatu.
- Podczas tych prac nie wykonywano dodatkowych ręcznych wysyłek ani ponownego wysyłania historycznych raportów.

## 8. Diagnostyka i baza

- Logi procesów mają czas UTC, poziom i PID oraz rotację: aktywny plik 20 MiB i pięć archiwów. Stary większy plik został zachowany w archiwum.
- Monitor pokazuje jakość według wersji formatu, powody odrzuceń i filtrów, dostępne zużycie tokenów oraz kredytów Tavily. Brak danych rozliczeniowych nie oznacza zerowego kosztu.
- Kosztowniejsze statystyki są odczytywane na żądanie, aby nie obciążać zwykłego odświeżania panelu.
- Dodano widok wyników ostatniego zakończonego cyklu, pomagający wyjaśnić brak alertu na wcześniejszych etapach.
- Dodano indeks najnowszych obserwacji i ograniczono zbędną pracę pustej kolejki.
- Zachowano osieroconą diagnostykę w archiwum. Wcześniejsze porządkowanie bazy i VACUUM odzyskało około 6,38 GB bez kasowania historii obserwacji.
- Sześć starych cykli z 13–15 października oznaczono jako przerwane, z kopią oryginalnych rekordów i adnotacją o porządkowaniu.
- Późniejszy audyt wskazał około 2,36 GB w obserwacjach i około 206 MB w kontekstach AI. To pomiar z chwili audytu, a nie stała wielkość bazy.
- Dużej deduplikacji historycznej bazy nie wykonano. Wymagałaby osobnej migracji i kontroli odtwarzania raportów.

## 9. Weryfikacja

- 350 testów plikowych przeszło również w czystym katalogu odtworzonym dokładnie z plików przygotowanych do commitu.
- Przy wdrożeniu przeszło także 348 testów wewnętrznych, 24 testy panelu i 5 testów uruchamiania.
- Po wdrożeniu potwierdzono działanie skanera, obu workerów i odpowiedź HTTP 200 panelu.
- Ostatni odczyt podczas tworzenia podsumowania: manifest v3 — 5 zadań `DONE`, 2 `REVIEW_REQUIRED`; w kolejce 142 wiadomości, wszystkie `DELIVERED`.
- Powyższe liczby dotyczą zapisanej historii. Nie oznaczają, że wszystkie 142 wiadomości używały najnowszego formatu ani że każdy nowy wariant został już potwierdzony w naturalnym cyklu.
- Ręcznych płatnych testów OpenAI/Tavily i dodatkowych wiadomości Telegram nie wykonywano. Normalna zatwierdzona praca skanera mogła korzystać z dostawców.

## 10. Ustalenia na jutro — 28 października

1. Użytkownik uruchamia lokalne KI 2 rano do dalszych testów.
2. Sprawdzamy naturalny przebieg, świeżość danych, jakość raportów, poziomy i brak duplikatów.
3. Po ocenie wyników wykonujemy push zapisanego commitu; niniejszy dokument można wcześniej dołączyć osobnym commitem.
4. Dopiero po testach wybieramy VPS i budżet.
5. Wspólnie przechodzimy od zakupu przez zabezpieczenie, instalację i konfigurację do próbnego uruchomienia, backupu oraz automatycznego startu.
6. Przy przeniesieniu produkcji pozostaje tylko jeden aktywny skaner, aby nie dublować analiz, kosztów i wiadomości.

Kalendarz świąt i skróconych sesji został świadomie odłożony poza obecny zakres. Nie zaplanowano dodatkowych funkcji. Priorytetem jest teraz obserwacja i stabilność działającego programu.

## 11. Gdzie szukać szczegółów

- `TOP10_WDROZENIE_20261027.md` — najnowszy podział rankingów, diagnostyka i audyt bazy.
- `AI_AXES_20261027.md` — trzyczęściowy kontrakt odpowiedzi AI.
- `SL_TP_20261027.md` — metoda obliczeń poziomów.
- `AI_PREFLIGHT_20261027.md`, `FULL_PACKAGE_20261027.md` — bramki i materiał przed AI.
- `OPTYMALIZACJA_WDROZENIE_20261027.md` — wcześniejsza optymalizacja i porządkowanie bazy.
- Lokalne katalogi `backup_20261027_*` — kopie i zapisy weryfikacji; nie są częścią repozytorium.
