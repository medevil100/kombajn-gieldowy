# Końcowy werdykt AI oparty na dowodach — 9 listopada 2026

Status: wdrożono na VPS 9 listopada 2026 o 21:34 UTC (22:34 CET).
Potwierdzenie użytkownika: instalator success, kod 0; panel i trzy heartbeaty
potwierdzone. Dziewięć testów instalatora i pięć etapów pełnej regresji VPS
zakończono poprawnie, PASS; graf TradingAgents sprawdzono bez modeli i narzędzi.
Kopia kodu: `/home/ubuntu/ki2/backup-evidence-review-20261109T213420416138Z`.
Raport: `/home/ubuntu/ki2-oceny-dowody-vps-20261109/tests-20261109T213228410879Z`.
Pierwsza rzeczywista nowa ocena i ewentualne doręczenie wymagają potwierdzenia
w kolejnej otwartej sesji. Instalacja nie wykonywała płatnych testów ani wysyłek.

## Decyzja użytkownika i przyczyna

Po wynikach LCTX i ONCO z 20:47 UTC użytkownik wybrał wariant:
„Werdykt AI oparty na dowodach”. Swobodny tekst v3 nadal przypisywał danym
sentyment, zachowanie inwestorów, przyszłą kontynuację i płynność. ONCO
pomijał zakres sesji i skróconej świecy. Format zdań był już poprawny,
lecz treść nie spełniała kontraktu danych. Walidacji tych twierdzeń nie poluzowano.

## Nowy podział odpowiedzialności

AI niezależnie wybiera `INFORM` albo `PANEL_ONLY`, konkretne dowody ceny
i momentum, argumenty za, ograniczenia, warunek obserwacji i ewentualny cytat.
Listy argumentów są uporządkowane przez model; pierwszy argument odpowiedniej
listy stanowi główne uzasadnienie jego decyzji. Lokalna zgodność nie wymusza INFORM.
Spółki nadal oceniane są oddzielnie, bez porównawczego promptu między emitentami.

Na wyjściu modelu dopuszczone są wyłącznie identyfikatory z katalogu danych
tej spółki. Nie ma swobodnego pola, w którym model mógłby dopisać sentyment,
spekulację, nową wartość RSI, narrację o wynikach lub nowe poziomy cenowe.
Katalog rozróżnia faktyczne stany RSI, znaki MACD i DI, relację ceny do średniej,
ruch od otwarcia i bazy, zakończone/otwarte/skrócone świece, wolumen godzinowy
i zapis całej sesji, status ofert, plan techniczny i dostępne dane finansowe.

KI składa polski opis z wybranych przesłanek i obowiązkowych faktów/ograniczeń.
Trzy osie pełnego raportu nie zależą od tego, czy model pamiętał o skróconej
świecy lub niepotwierdzonym czasie ofert. Nie nazywamy tej warstwy swobodnym
tekstem AI. Monitor końcowych ocen i TOP 5 wyjaśniają autorstwo: AI wybrało
werdykt i dowody, a KI złożyło opis. Wybrany warunek scenariusza ma własny opis.

Pełny pakiet danych nadal trafia do AI: przebieg sesji, wskaźniki, lokalne
oceny, scenariusze, plan, zapisane tło spółki i przyjęte źródła. Katalog jest
dodatkowym, kontrolowanym sposobem odnoszenia się do tych danych.
Nie zmieniono modelu GPT-4o mini, temperatury ani limitu odpowiedzi. Nie dodano
drugiego wywołania, naprawy tekstu przez model ani dodatkowego dostawcy.

## Zapis, walidacja i zgodność

Nowe końcowe żądania mają `review_contract=EVIDENCE_SELECTION_V1`, nazwę schematu
`ki_grounded_company_review` i wersję promptu `KI-PROMPT-20261109-v4`.
Odpowiedź jest sprawdzana lokalnie: dokładny zestaw pól, typy, dozwolone kody,
długości list i brak duplikatów. Identyfikatory są krótkie i nie zawierają cytatów.
Katalog odtwarza się z zapisanych danych i porównuje z zamrożonym żądaniem;
tożsamość, waluta, interwał oraz czasy muszą odpowiadać migawce.

Po złożeniu opisu nadal obowiązuje dotychczasowa walidacja wskaźników, źródeł,
trzech osi, klasyfikacji lokalnej, publikacji, aktualności i Telegrama.
Źródłowy cytat odtwarza się z mapy Q powiązanej z przyjętym źródłem.
Rzeczywista surowa odpowiedź modelu (identyfikatory), jej zużycie oraz wybrana
kolejność dowodów pozostają w `provider.raw_response` i `provider.evidence_review`.
Metadane zawierają odcisk katalogu oraz wybrany warunek. Bez migracji schematu bazy.

Zamrożone wcześniejsze żądanie nie jest przepisywane na nowy format. Dawne
wyniki i błędy pozostają czytelne; FAILED, REVIEW_REQUIRED i UNCERTAIN nie są
resetowane ani ponawiane. Nie zmieniono bramek selekcji, progów ryzyka,
limitu sześciu ocen na cykl ani maksymalnie pięciu kart TOP 5. Nie wymusza się
minimalnej liczby spółek. Zmiana dotyczy sposobu oceny przyszłego nowego materiału.

## Weryfikacja i granice

Testy obejmują pełną oraz skróconą sesję, rozbieżny ruch od otwarcia i bazy,
granice klasyfikacji RSI, rozróżnienie braku, niepełnych, niespójnych i dostępnych
ofert, obce identyfikatory, zmieniony katalog, tożsamość innej spółki i czasy,
brak swobodnej narracji, wybór PANEL_ONLY, zamrożone stare żądanie, cytaty Q,
pojedyncze wywołanie na atrapie, zachowanie surowej odpowiedzi i pochodzenia
opisu, TOP 5 i pełny przebieg aż do potwierdzenia Telegrama na atrapie HTTP.
Testy nie wywołują prawdziwego AI, Tavily, Yahoo ani testowych wiadomości.
Pełna regresja końcowa: 703 testy modułów Windows i Linux OK (dwa i cztery
pominięcia zależne od systemu i Node.js), testy wbudowane 522, panel 26,
uruchamianie 5. JavaScript pełnego ekranu sprawdzony na Windows. Raporty:
`ki2-evidence-review-20261109/release-windows` w artefaktach Codex oraz
`/home/szela/ki2-evidence-review-release-20261109/regression` w WSL.
Dziewięć testów instalatora przeszło na obu systemach, w tym powrót plików
i usunięcie nowego modułu po błędzie. Graf TradingAgents READY_OFFLINE.

Model nadal może źle zważyć prawdziwe przesłanki. Katalog nie gwarantuje
trafności inwestycyjnej ani ceny następnego otwarcia. Testy wykazują poprawność
kontraktu i przepływu; rzeczywista nowa ocena oraz doręczenie wymagają
obserwacji podczas kolejnej otwartej sesji.
