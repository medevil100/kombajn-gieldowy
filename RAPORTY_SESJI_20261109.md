# Harmonogram raportów po sesji — 9 listopada 2026

Status: wdrożono na VPS 9 listopada 2026 o 22:02 UTC (23:02 CET). Naturalna godzina kolejnego raportu wymaga potwierdzenia.

Użytkownik potwierdził SHA256 paczki, dziewięć testów instalatora, pełną regresję VPS PASS i kompilację grafu offline. Usługa `ki2-report-schedule-install-20261109.service` zakończyła się success/0; panel i trzy świeże heartbeaty potwierdzone. Kopia kodu: `/home/ubuntu/ki2/backup-report-schedule-20261109T220209778456Z`. Raport testów: `/home/ubuntu/ki2-raporty-sesji-vps-20261109/tests-20261109T220012329552Z`. Nie wykonano płatnych testów ani testowych wiadomości.

Raport GPW akceptował oba okna UTC, letnie i zimowe, niezależnie od daty. W listopadzie pierwsze okno wysyłało raport około 16:00 czasu polskiego. Nie sprawdzano także dni sesyjnych. USA miało stałą godzinę 23:05 czasu polskiego.

Zapis VPS potwierdza dostarczenie raportu GPW 9 listopada o 16:09 CET oraz raporty w sobotę i niedzielę. Ostatnie pokazane raporty USA z 5 i 6 listopada wysłano o 23:15 CET. Te rekordy nie potwierdzają zgłoszonej godziny 21:00.

Nowy moduł `report_schedule.py` używa istniejącego kalendarza sesji XWAR/XNYS. Raport może powstać od pięciu do dziewięćdziesięciu minut po właściwym zamknięciu. Uwzględnia święta, weekendy, skrócone sesje USA oraz różne terminy zmian czasu w USA i Europie. Godzina faktycznej wysyłki zależy od zakończenia cyklu i kolejki Telegrama. Przy obecnym układzie zimowym pierwsza możliwość przypada o 17:05 dla GPW i 22:05 dla USA czasu polskiego.

Dotychczasowe identyfikatory i znaczniki wysłanej sesji pozostają ważne: poprawka nie ponowi już utworzonego raportu. Nie zmienia treści zestawień, progów selekcji, planów SL/TP ani historycznych zadań.

## Tavily: wynik diagnostyki

Odczyt przekazany przez użytkownika zawiera sześć zakończonych wyszukiwań automatu z 9 listopada około 20:47 UTC. Zapisane odpowiedzi dostawcy wykazują po dwa kredyty, łącznie dwanaście. KI przyjęło: NTHI 7, FBIO 2, CRIS 4, PDSB 2, ONCO 5, LCTX 0 źródeł. Ręczna analiza TScan również ma zakończone wyszukiwanie i trzy przyjęte źródła.

Nie potwierdzono awarii połączenia ani braku wykonywania wyszukiwań. Brak przyjętych materiałów dla konkretnej spółki nie dowodzi braku informacji na rynku. Nie rozluźniono filtrów emitenta, domen i czasu; nie wykonano dodatkowych zapytań. Zapis `usage` nie jest niezależnym potwierdzeniem rozliczenia konta dostawcy.

Późniejszy odczyt `GET /usage` dla dotychczasowego klucza: Researcher, limit planu 1000, zużycie 1273, pay-as-you-go 273. Użytkownik potwierdził, że wskazane 4000 obejmuje 1000 kredytów planu oraz dodatkowe 3000. Pierwszy pomocniczy skrypt błędnie wymagał `plan_limit=4000` i zatrzymał się przed zapisem; warunek usunięto. Nowy klucz KIdev został zaakceptowany przez API (Researcher, limit planu 1000) i zapisany o 22:30 UTC, co użytkownik potwierdził. Kopia konfiguracji: `/home/ubuntu/ki2/.streamlit/secrets.toml.before-tavily-20261109T223059959909Z.bak`. Pozostałe wartości konfiguracji zachowano. Bez restartu oraz testowego Search, Extract lub GPT. `service_worker` wczytuje klucze przed nowym zadaniem. Naturalne wyszukiwanie nowym kluczem i aktualizacja licznika wymagają potwierdzenia. Materiał klucza nie został przekazany do czatu ani zapisany w repozytorium.

## Weryfikacja

`test_report_schedule_20261109`: osiem testów kalendarza i rzeczywistej kolejki w tymczasowym SQLite. Obejmują zmianę czasu, święta i weekendy, skróconą sesję, ograniczony czas opóźnienia, deduplikację i zachowanie starych znaczników wysyłki. Pełne wyniki regresji i instalatora są dołączane do nowej paczki wydania. Bez płatnych wywołań i testowych wiadomości.

Pełna regresja Windows i Ubuntu WSL: 711 testów modułów (odpowiednio dwa i cztery pominięcia zależne od platformy), 522 testy wbudowane, 26 testów panelu i pięć testów uruchamiania OK. JavaScript OK na Windows; Linux bez Node.js. Dziewięć testów instalatora przeszło na obu systemach. Przygotowanie wydania na VPS dodatkowo wymaga powtórzenia regresji i rzeczywistej kompilacji grafu analizy pogłębionej offline.
