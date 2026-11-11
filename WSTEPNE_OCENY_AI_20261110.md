# Wstępna ocena AI przed trzema potwierdzeniami — 10 listopada 2026

Status: wdrożono na VPS 10 listopada około 16:17 UTC (17:17 CET). Dziewięć testów instalatora i pełna regresja VPS PASS; graf offline poprawny. Pierwsza próba zatrzymała się przed zmianami na blokadzie operacji dostawcy lub nadzoru. Ponowienie `ki2-early-review-install-retry-20261110.service` zakończono success/0, panel i trzy świeże heartbeaty potwierdzone. Kopia kodu: `/home/ubuntu/ki2/backup-early-review-20261110T161704678318Z`. Raport testów: `/home/ubuntu/ki2-wstepne-oceny-vps-20261110/tests-20261110T161104752723Z`. Baza, klucze, ustawienia i kolejki zachowane; brak płatnych testów i testowych wiadomości. Naturalne nowe oceny i ich doręczenia pozostają do potwierdzenia.

Zmiana zasad zaakceptowana przez właściciela: istotny wczesny ruch może wejść do końcowej selekcji AI ze statusem „wstępna ocena”, przy jednym wspólnym zestawieniu.

## Problem potwierdzony na HUMA

Zapis VPS pokazał +20,66% od bazy o 15:45 CET i +28,09% o 16:15 CET. Przerwa między odczytami uruchomiła licznik od jednego; o 16:30 nowa świeca miała zapisany wolumen zero. HUMA pozostała kandydatem, więc nie dotarła do końcowego AI, TOP 10 ani powiadomienia. Osobne wczesne wiadomości były wyłączone zgodnie z wcześniejszym uzgodnieniem jednego zestawienia. Poprawka koordynatora z 14:56 UTC nie zmieniała tej bramki.

## Nowe zasady wejścia

Nowy `early_company_review.py` dopuszcza bieżącego kandydata z jednym lub dwoma rzeczywistymi dowodami aktywności. Wymagane są: przekroczenie obecnego progu ceny, nowy dowód aktywności w tej migawce, RVOL co najmniej 1,5 (albo wyższe zapisane minimum), co najmniej 1000 sztuk wolumenu (albo wyższe zapisane minimum), spójne OHLCV, poprawna baza poprzedniej sesji, świeży odczyt regularnej sesji i komplet rzeczywiście zapisanych świec sesji do chwili odczytu. Cena przeniesiona, zerowy wolumen, przestarzałe dane i braki nie otrzymują zastępczych wartości.

Lokalne ryzyko i sprzeczne wskazania pozostają blokadami kwalifikacji do płatnej oceny. Wczesne i potwierdzone przypadki korzystają ze wspólnego limitu sześciu nowych niezależnych ocen na cykl, sortowania lokalnego oraz tego samego mechanizmu intraday i deduplikacji. AI ocenia każdą spółkę osobno. Wstępne oceny mogą zwiększyć liczbę naturalnych wyszukiwań i analiz, lecz nie dodano nowego dostawcy ani drugiego modelu i nie zwiększono wspólnego limitu.

## Jawny status w całym przepływie

Zdarzenie ma osobny rodzaj EARLY_COMPANY_REVIEW, `review_stage=PRELIMINARY`, faktyczny licznik oraz wymagane trzy potwierdzenia. Nie zmienia się licznika matrycy, nie dopisuje fikcyjnych signal_confirmations i nie nadaje statusu CONFIRMED. Wstępny raport mówi o niezakończonej serii; zniknięcie tego zastrzeżenia powoduje błąd walidacji. Identyfikatory dowodów i polskie opisy powstają w obecnym kontrakcie V2, z jawnym L_CONFIRMATION. Prompt nowych żądań: KI-PROMPT-20261110-v6.

Końcowa ocena, TOP 5 i zbiorczy Telegram pokazują „WSTĘPNA OCENA” oraz licznik z chwili oceny. TOP 10 automatu nadal oznacza potwierdzone ruchy — nie zmieniono tej definicji. Wczesne przypadki pozostają we wczesnym rankingu, a po pozytywnej ocenie AI mogą pojawić się w TOP 5. Nie przywrócono osobnych wstępnych wiadomości.

Przed pracą dostawców i publikacją sprawdzane są tożsamość, baza, bieżące dane i kierunek. Najnowszy zerowy lub niespójny odczyt nie jest zastępowany starszym pozytywnym raportem. Osobna kontrola aktualnej oceny lokalnej chroni wstępną publikację. Późniejsze trzy rzeczywiste potwierdzenia mogą uzasadnić nową ocenę, z nowym zdarzeniem i własną datą; stary raport zachowuje swój stan. Niezmieniona aktualizacja nie wywołuje ponownie AI.

Zamrożone stare żądania, historie, ustawienia, baza i kolejki pozostają bez zmian. Nie ponawia się zadań ani wiadomości historycznych. Wyłączenie trybu końcowych ocen zachowuje wcześniejsze działanie samodzielnych wczesnych alertów. Włączenie tej funkcji nie wymusza obecności spółek w zestawieniu i nie stanowi prognozy skuteczności.

## Sprawdzenie

Testy korzystają z tymczasowej SQLite i atrap dostawców. Obejmują przepływ skaner → rezerwacja → AI → TOP 5 → jeden Telegram, zachowanie faktycznego 1/3 przy przerwie HUMA, odrzucenie nowej świecy z wolumenem zero, pełną bramkę danych, rzeczywiste ryzyko, wspólny limit obu ścieżek, deduplikację, zmianę progu lub usunięcie tickera przed publikacją, jawny status w opisie oraz przejście do trzech potwierdzeń bez nadpisania poprzedniego zdarzenia. Dane OHLC scenariusza HUMA są syntetyczną spójną otoczką do testu; ceny i wolumeny pochodzą z przesłanego odczytu, a nie z nowego pobrania Yahoo.

Nie wykonano prawdziwych wywołań OpenAI, Tavily, Yahoo ani Telegrama. Skuteczność naturalnego przepływu po wdrożeniu wymaga osobnej obserwacji.

Pełna regresja Windows i Ubuntu WSL: 751 testów modułów, wbudowane 522, panel 26 i uruchamianie 5 OK (pominięcia zależne od platformy). JavaScript pełnego ekranu OK na Windows; Linux bez Node nie uruchamiał tej fazy. Po tej regresji dodano jeden test pojemności pojedynczego Telegrama z sześcioma wstępnymi ocenami; aktualny moduł 17 testów uruchomiono ponownie na obu systemach. Nie zmienił się przy tym kod wykonawczy. Dziewięć testów instalatora na Windows i Linux OK. Przed instalacją wymagane są pełne testy bieżącej paczki w środowisku VPS oraz graf offline.
