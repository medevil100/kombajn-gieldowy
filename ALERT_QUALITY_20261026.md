# KI 2 — wspólna jakość automatycznych alertów, 26.10.2026

Projekt: C:\Users\szela\OneDrive\Desktop\KI\2 KI. Zmieniono KI.py i testy; bez zmian w Alchemik-prace.

## Zachowanie dla wszystkich tickerów

- Nagłówek wskazuje POTWIERDZONY WZROST / POTWIERDZONY SPADEK zgodnie ze zmianą względem bazy. Przy braku znanej zmiany pozostaje neutralny POTWIERDZONY RUCH. Usunięto niejednoznaczne OKAZJA z wiadomości Telegram.
- Ostrzeżenia jakości są jedną krótką linią o częściowej analizie. Pełne quality_issues i surowa odpowiedź pozostają w SQLite i panelu.
- Telegram zawiera kilka kluczowych wartości i do trzech interpretacji AI zamiast całej listy wskaźników i tylko pierwszego komentarza. Pełne dane pozostają w panelu.
- Automatyczna publikacja wymaga co najmniej dwóch wskaźników reprezentujących różne obszary oraz interpretacji ceny, kierunku lub momentum. Samotny komentarz o ATR lub zestaw ADX+RVOL nie wystarczają. Ta sama bramka obowiązuje przy kończeniu zadania i tworzeniu krótkiej wiadomości. Braki dają REVIEW_REQUIRED, zapis wyniku i powodów bez utworzenia wiadomości do wysyłki.
- Walidator usuwa ocenę względnej zmienności z samego ATR oraz komentarz o silnym/słabym trendzie ADX bez rozróżnienia kierunku lub ograniczenia interpretacji. Są to dodatkowe, konkretne kontrole semantyczne; nie pełny dowód poprawności każdego zdania modelu.
- Prompt wspólnie dla wszystkich instrumentów wymaga różnych obszarów analizy, odniesienia do kierunku oraz unikania powtarzania cyfr. Zachowano model, zasady cytowania i brak automatycznych ponowień.

## Weryfikacja

298 testów plikowych, 322 self-testy, 24 testy panelu — OK. Nowe testy obejmują różne, arbitralne symbole GPW i USA, oba kierunki, odrzucanie jednej interpretacji / skorelowanych wskaźników, usunięcia ATR/ADX oraz rzeczywisty zapis REVIEW_REQUIRED bez outbox. Istniejące testy atomowości, deduplikacji i doręczeń zachowano; pozytywne próbki automatycznych analiz uzupełniono o wymagany drugi obszar.

Replay zapisanych odpowiedzi bez API: LET i VAR spełniają nową bramkę; EGO i MSW zostałyby zatrzymane do przeglądu. Podglądy i wynik replay w backup_20261026_alert_quality. Żadne historyczne analizy ani doręczone wiadomości nie zostały przepisane, ponowione lub ponownie wysłane. Nie wykonywano płatnych wywołań testowych.

Po kontrolowanym restarcie 26.10.2026 o 11:08 Europe/Berlin: launcher 14248, scanner 23204, panel 2284, RUNNING, oba workery READY, heartbeat poniżej pięciu sekund, panel HTTP 200. Stan i hash kodu zapisano w backup_20261026_alert_quality/deployment.json. Nowy naturalny alert wymaga jeszcze potwierdzenia podczas dalszego cyklu.
