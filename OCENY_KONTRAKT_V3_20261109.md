# Końcowe oceny — kontrakt v3 po odpowiedzi FBIO

Status: wdrożono na VPS 9 listopada 2026 o 18:29 UTC (19:29 CET).
Potwierdzenie użytkownika: instalator success, kod 0; panel i trzy heartbeaty
potwierdzone. Pięć etapów pełnej regresji VPS zakończono wynikiem 0, PASS;
graf TradingAgents skompilowano bez modeli i narzędzi. Kopia kodu:
`/home/ubuntu/ki2/backup-final-contract-20261109T182953775612Z`.
Raport: `/home/ubuntu/ki2-oceny-v3-vps-20261109/tests-20261109T182803560333Z`.
Nowa naturalna ocena z v3 i rzeczywiste doręczenie pozostają do potwierdzenia.
Bez płatnych testów, wiadomości testowych i ponawiania historycznych zadań.

## Rzeczywisty błąd

FBIO, zdarzenie 2026-11-09T17:17:03.443136+00:00, prompt v2:
`movement` i `activity` zawierały wielokrotnie powtarzane „łącznie”, bez
ukończonych zdań. Dołączono hipotezy o wynikach i spekulacji inwestorów bez
potwierdzenia. To nie jest wartościowy raport odrzucony tylko za długość.
Walidator słusznie zatrzymał publikację. Zapis pochodzi sprzed aktualizacji
ocen w trakcie sesji o 17:24 UTC, lecz używał już kontraktu v2.

Schemat v2 zabraniał cyfr i wymagał co najmniej stu znaków, ale liczba pełnych
zdań była jedynie instrukcją. Powtórzenia spełniały sam schemat. To dowód luki
formatu, nie dowód przyczyny wewnętrznego zachowania modelu. Syntaktycznie
poprawny JSON nie oznacza rzeczowej ani poprawnej finansowo odpowiedzi.

## Zmiana

- Każda oś końcowej oceny wymaga od dwóch do czterech zdań zakończonych
  interpunkcją; łącznie maksymalnie sześćset znaków. Zrezygnowano ze sztucznego
  minimum stu znaków, zachowując osobne uzasadnienia ruchu, aktywności i ryzyka.
  Reguła pełnych zdań jest w schemacie generowania i lokalnej walidacji.
- Wyraźny wniosek jakościowy zamiast niedokończonego „cena wzrosła o” albo
  „wolumen wynosi”, po którym model musiałby podać niedozwoloną liczbę.
- Dodatkowa lokalna blokada zapętleń, powtarzanych fraz i identycznych zdań.
  Odrzucona odpowiedź pozostaje do kontroli; nie usuwa się powtórzeń, aby
  zamienić ją w pozornie poprawny raport.
- `hypotheses` w nowych końcowych ocenach musi być pustą listą. Przyjęte,
  zweryfikowane cytaty i tło emitenta pozostają w `context` i pakiecie; warunki
  scenariuszy technicznych również pozostają. Nie generuje się dodatkowych
  domysłów o przyczynie ruchu czy zachowaniu inwestorów.
- Numeryczne znaki Unicode są jawnie wykluczone z opisów, tak jak w poprawce
  ręcznej Analizy GPT. Konkretne liczby pozostają w zweryfikowanych danych.

Nowy pakiet ma `assessment_contract=SENTENCES_V1`, `hypotheses_policy=EMPTY`
i wersję promptu `KI-PROMPT-20261109-v3`. Stare manifesty bez tych pól nadal
korzystają z dotychczasowych kontroli; nie zmienia się historii ani stanów zadań.
Nie zmienia się modelu, budżetu tokenów, bramek danych, selekcji, reguł ryzyka,
warunków sesji, wymogu rzeczywistej aktywności ani maksymalnej liczby spółek.
Nie wymusza się INFORM ani minimum trzech spółek. Poprawny raport może nadal
pozostać w panelu. Scenariusze wizualne czekają na osobny pomysł użytkownika.

## Testy i granice potwierdzenia

Osiem nowych testów obejmuje dosłowną odpowiedź FBIO, zgodność schematu
z JavaScript i Python, ukończone zdania bez wypełniania znaków, puste hipotezy,
powtórzenia, zachowanie starych kontroli i pojedynczy przebieg kolejki na
atrapie HTTP, kończący się DONE z niezmienionym surowym zapisem odpowiedzi.
Nadal blokowane są wymyślona przyczyna, liczby bez odwołania i zapewnienia
o płynności. Bez prawdziwych wywołań AI/Tavily i testowych wiadomości.

Raporty pełnej regresji znajdują się poza projektem w artefaktach Codex,
`ki2-fbio-contract-20261109`. Windows 680 testów modułów OK (dwa pominięcia
POSIX), Linux WSL2 680 OK (dwa pominięcia Windows i dwa zależne od Node.js).
Testy wbudowane 522, panel 25 i uruchamianie 5 OK na obu systemach;
JavaScript sprawdzony na Windows.
Osiem testów instalatora przeszło na obu systemach; graf TradingAgents
READY_OFFLINE, bez modeli i narzędzi.
Wynik testu z poprawną odpowiedzią z fixture nie
dowodzi, że model udzieli poprawnej odpowiedzi na każdy kolejny rzeczywisty
pakiet. Po wdrożeniu potrzebna jest nowa naturalna ocena z v3 i sprawdzenie
jej walidacji, decyzji publikacji oraz rzeczywistego doręczenia, jeśli się zakwalifikuje.
Żadne stare FAILED/REVIEW_REQUIRED/UNCERTAIN nie jest resetowane ani ponawiane.

Wspierany `pattern` i ograniczenia tablic opisuje
[OpenAI Docs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
Konkretną lukę potwierdza zapis użytkownika i regresja lokalna.
