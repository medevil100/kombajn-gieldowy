# Koordynacja danych i końcowych ocen — 10 listopada 2026

Status: wdrożono na VPS 10 listopada 2026 około 14:56 UTC (15:56 CET). Pełna regresja VPS PASS, graf analizy pogłębionej sprawdzony offline, panel i trzy świeże heartbeaty potwierdzone. Rzeczywiste nowe oceny i dostarczenie Telegrama nadal wymagają potwierdzenia podczas naturalnych cykli.

Paczka `ki2-koordynator-vps-20261110.tar.gz`, SHA256 `bb23c3ccab58a4b8ebc289fa6d1144297fa69049dae961f3bfea9de5cc22d944`. Raport testów VPS: `/home/ubuntu/ki2-koordynator-vps-20261110/tests-20261110T145410256451Z`. Jednostka `ki2-coordinator-install-20261110.service` zakończona success/0; kopia kodu `/home/ubuntu/ki2/backup-coordinator-20261110T145601199858Z`. Baza, ustawienia, klucze i kolejki zachowane. Nie wykonano płatnych testów ani testowej wysyłki.

## Potwierdzone zgłoszenie

Odczyt VPS z 11:46 UTC: skaner RUNNING, oba workery READY. Piętnaście zadań zakończyło się DONE bez zarejestrowanych pominięć, każde z decyzją PANEL_ONLY. Wszystkie wyjaśnienia zaczynały się od „Dalszy kierunek pozostaje nieustalony”. Każde miało lokalne ALIGNED i oba dozwolone werdykty. Nie powstało żadne zestawienie Telegrama — brak wiadomości wynikał z decyzji, a nie błędu dostarczenia.

STX.WA miało MISSING_DAILY_REFERENCE od 08:00 do 08:45 UTC. Zatwierdzoną bazę z 9 listopada, 1,947999954 PLN, zapisano o 09:00 UTC. Później najwyższy pokazany odczyt 1,975999951 PLN stanowił 1,437% od tej bazy. Ustawiony próg to 2%; brak potwierdzeń i zadań AI dla STX w tym zakresie jest zgodny z zapisanymi cenami. Procent od otwarcia lub cena brokera mogą mieć inną podstawę. Nie odtworzono nieobserwowanego ruchu i nie utworzono retrospektywnego alertu.

## Koordynacja decyzji

### Kontrola naturalnych cykli: HUMA, 10 listopada

Odczyt właściciela z 15:33:26 UTC: dwa cykle OK i jeden RUNNING, dwa EMPTY zestawienia, zero nowych zadań AI; jeden PORTFOLIO_ALERT oznaczony DELIVERED. Działanie końcowego kontraktu V2 nie zostało w tych cyklach sprawdzone, ponieważ nie dotarł do niego kandydat.

Plik diagnostyczny właściciela `54aca963-6e96-4e54-ab41-3005c617d16e/Wklejony tekst.txt` potwierdza, że HUMA miało poprawną bazę 0,455000013 USD z 9 listopada. O 14:45:07 UTC (15:45 CET) zapisano cenę 0,549000025 USD, zmianę +20,6593%, wolumen 2 639 351 i licznik 1. Następny pokazany odczyt pochodzi z 15:15:07 UTC (16:15 CET): cena 0,582809985 USD, zmiana +28,0901%, wolumen 6 504 423 i ponownie licznik 1. W przedstawionej historii nie ma odczytu 15:00 UTC; przyczyny jego braku jeszcze nie ustalono.

Kod matrycy dopuszcza dla kolejnych dowodów odstęp do 20 minut przy cyklu 15-minutowym. Przerwa 30 minut zeruje serię przy następnym dowodzie aktywności, stąd nowy `candidate_started_at` 15:15:07 UTC. O 15:30:07 UTC nowa świeca 10:30 ET miała cenę 0,581900001 USD (+27,8901%), zapisany wolumen 0 i NO_NEW_ACTIVITY — nie dodano trzeciego ani drugiego dowodu. Zerowy zapis nowej świecy nie dowodzi braku handlu na rynku.

Matryca i opportunities pozostały CANDIDATE. TOP 10 wymaga potwierdzenia, a końcowa ścieżka AI pobiera dopiero potwierdzone opportunities. `queue_early_movement` celowo nie wysyła osobnego powiadomienia, kiedy włączony jest tryb końcowych ocen, zgodnie z wcześniejszym uzgodnieniem jednego zestawienia. To konflikt celu wczesnego wychwytywania z obecną bramką wejścia, a nie potwierdzony błąd wysyłki Telegrama lub nowego werdyktu AI.

Do ustalenia kolejnej zmiany: osobna, jawnie niepotwierdzona ścieżka oceny istotnego wczesnego ruchu z zapisanymi cenami i aktywnością, przy zachowaniu odrębnego statusu trzech potwierdzeń, limitu zestawienia, deduplikacji i kontroli źródła. Nie wdrożono takiej zmiany w paczce koordynatora z 14:56 UTC. Nie resetowano zadań i nie wysyłano historycznego alertu HUMA.

Nowy `review_coordinator.py` rozdziela informację do obserwacji w XTB od gotowego planu transakcji. Ogólna niepewność przyszłości, nieustalona przyczyna, częściowa godzina, niepotwierdzony czas ofert, brak fundamentów/kompletnego SL/TP i samo RSI w strefie skrajnej pozostają jawne, lecz nie mogą być główną przesłanką odmowy.

AI wybiera dowody przed decyzją i zapisuje jawne `decision.primary_reason`. PANEL_ONLY wymaga konkretnego ograniczenia z katalogu, np. odmiennego kierunku od otwarcia lub pełnego godzinowego pomiaru niskiej aktywności, albo faktu z datowanego, zweryfikowanego źródła. Ocena znaczenia faktu źródłowego pozostaje interpretacją modelu, nie dowodem przyczyny ruchu. Zestaw schematu dopuszcza wyłącznie decyzje mające podstawę w katalogu; brak konkretnych podstaw odmowy nie zamienia ogólnych zastrzeżeń w powód milczenia.

Twarde lokalne blokady danych i ryzyka pozostają: zmiana nie pozwala ominąć RISK_DOMINANT, POOR_RR, ADVERSE_RETRACE czy WIDE_SPREAD przez pozytywny werdykt modelu. Zachowano próg ceny, trzy odczyty aktywności, limit sześciu nowych ocen na cykl, pojedyncze zestawienie oraz brak minimalnej liczby spółek. Silnik/model i limit tokenów nie zostały zmienione; nie dodano drugiego modelu ani płatnego ponawiania.

Nowe żądania mają kontrakt EVIDENCE_SELECTION_V2 i prompt KI-PROMPT-20261110-v5. Zamrożone żądania V1 i starsze pozostają obsługiwane w swoim kontrakcie, bez zmiany werdyktów dawnych raportów, resetowania kolejki i ponownego wywoływania dostawcy. Prawidłowy schemat JSON nie gwarantuje trafności interpretacji AI; nowy kontrakt usuwa konkretną możliwość użycia ogólnej niepewności jako głównego weta. Jakość selekcji trzeba nadal ocenić na naturalnych nowych zadaniach.

## Gotowość bazy

Odtworzono błąd: częściowa odpowiedź zapisana 08:00:00,200 blokowała ponowienie o 08:15:00, przez co próby mogły przypadać na 08:00, 08:30 i 09:00. Harmonogram był liczony od końca pobrania zamiast jego początku.

Nowe pobrania zapisują `attempt_started_at`; odstęp jest liczony od początku próby z jednosekundową tolerancją startu cyklu. Dawne wpisy zachowują dotychczasowy odstęp. Nie wyłączono niezależnego backoffu błędów źródła ani kontroli poprawności OHLCV. Poprawka nie gwarantuje, że dostawca udostępni dane przed otwarciem; pełny mechanizm przygotowania danych przed sesją nie jest częścią tej zmiany.

Podstawa dzienna, status otwarcia i następna sesja korzystają z tych samych kalendarzy XWAR/XNYS co raporty i kontekst sesji, uwzględniając święta oraz skrócone sesje. Stary zapis z dnia niebędącego sesją nie może zostać bazą odniesienia; nie usuwa się przy tym danych historycznych.

## Sprawdzenie i granice

Nowe testy obejmują przypadek zgłoszonych ogólnych odmów, konkretną odmowę, niekorzystny datowany fakt źródłowy, granice schematu, zachowanie twardych blokad i starych zamrożonych kontraktów, pełny przepływ na atrapach do TOP 5 i jednego Telegrama, opóźnienie odpowiedzi dziennej, brak lawiny ponowień, backoff, dni bez sesji i skrócone zamknięcie USA. Testy nie wywołują rzeczywistych modeli, Search/Extract, Yahoo ani Telegrama.

Potwierdzona regresja Windows i Ubuntu WSL: 735 testów modułów, 522 wbudowane, 26 panelu i 5 uruchomienia; pominięcia zależne od platformy. JavaScript pełnego ekranu przeszedł na Windows; Linux bez Node nie uruchamiał tej fazy. Pierwsza regresja wykryła starszy test zakładający ogólne weto — zmieniono go w kontrolę zachowania zamrożonego kontraktu, a nową politykę sprawdzają odrębne testy. Windowsowy test startu panelu nie połączył się w piaskownicy; ponowienie tego samego kodu poza nią przeszło. Pozostałe końcowe fazy Windows i pełna regresja Linux przeszły po tej korekcie testu.

Dokumentacja kontraktów: [OpenAI Docs — Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat). Poprawny schemat obejmuje format; wymaga osobnych reguł poprawności decyzji. Decyzja V2 używa obiektu głównego oraz wspieranego zagnieżdżonego `anyOf`.
