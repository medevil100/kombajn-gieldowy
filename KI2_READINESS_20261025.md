# KI 2 — przygotowanie do sesji 26.10.2026

## Korekta 26.10.2026 — brak automatycznych wiadomości

Podczas porządkowania analyze_event 25.10 usunięto potrzebne przypisanie `snap=evidence['snapshot']`. Funkcja nadal przekazywała snap do parsera po odebraniu odpowiedzi AI. Błąd NameError zatrzymał siedem dzisiejszych zadań (PRA.WA, PGH.WA, SYG.WA, EGY.WA, OML.WA, MDT.WA, HYP.WA), zanim powstały wyniki i wpisy ANALYSIS w outbox. Poprzednie testy nie obejmowały tego błędu w funkcji wywołującej transport.

Przywrócono przypisanie; dodano regresję kontroli niezdefiniowanych nazw globalnych w analyze_event. Testy plikowe: 293/293 OK. Zapis siedmiu uszkodzonych zadań zabezpieczono w backup_20261025_readiness/snap-error-20261026.json. Nie ponawiano płatnych wywołań tych zadań — błąd występował już po odebraniu odpowiedzi dostawcy, a surowy wynik nie był zapisany przed wyjątkiem.

Kontrolowany restart 26.10 o 09:38 UTC: launcher 19496, scanner 15020, panel 16768. Potwierdzono RUNNING i oba workery READY ze świeżymi heartbeatami. Poprawka dotyczy nowych analiz; stare REVIEW_REQUIRED zachowano do jawnej decyzji o ponowieniu.

Projekt: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`.
Program: `KI.py`; baza: `KI.matrix.sqlite3`; panel: http://127.0.0.1:8501/.
`Alchemik-prace` jest osobnym stosem. W tej naprawie nie zmieniano jego plików.

## Wykonane poprawki

- Ręczny pełny raport GPT: limit odpowiedzi 2600 → 5000 tokenów, zwięzłe sekcje w instrukcji. Model pozostaje gpt-4o-mini. Ucięcie (`finish_reason=length`) i odmowa mają odrębne komunikaty, bez automatycznego ponawiania. Nie gwarantuje to kompletności każdej przyszłej odpowiedzi; wynik nadal musi przejść walidację.
- Potwierdzona przyczyna błędu raportu HUMA `0c08a298c4c44867b6594e2a6e3aaae2`: 2600 completion_tokens i `finish_reason=length`. Zachowano stary wynik i jego diagnostykę, nie uruchamiano płatnego powtórzenia.
- Outbox: UPSERT zamiast DELETE+INSERT przez REPLACE. Istniejące doręczone, oczekujące, wysyłane i niepewne wiadomości pozostają nienaruszone. Aktualizacja podglądu/filtrowanego wpisu wymaga braku pokwitowania. Regresja sprawdza prawdziwe FK SQLite.
- Tavily: jawny backend SEARCH, timeout Search 60 s i Extract 30 s. Jedno dodatkowe Extract maksymalnie pięciu unikalnych adresów tylko bez pełnego raw_content. Diagnostyka rozróżnia NOT_NEEDED/FAILED/EMPTY/PARTIAL/COMPLETED; zachowuje usage i liczbę adresów. Bez automatycznych ponowień.
- Diagnostyka Extract przechodzi przez zapis research_requests do kontekstu i monitora, nie trafia do promptu GPT.
- Poprawiono nieaktualny tekst filtra Telegram i opis źródła ceny bazowej w panelu. Tekst potwierdzenia rozróżnia trzy odczyty matrycy i ścieżkę dwóch świec.
- Panel deklaruje język polski i translate=no/notranslate, również w tabelach raportu. W przeglądarce potwierdzono te atrybuty. Wklejony raport zawierał ślady tłumaczenia nazw (OBV → „OCZYWIŚCIE”). Nie odtworzono pierwotnego błędu removeChild; zabezpieczenie ogranicza ingerencję translatora, nie jest dowodem wyeliminowania wszystkich możliwych błędów React.
- Zaktualizowano niezgodne historyczne testy do bieżącego kontraktu Search, okna 30 dni i miękkiej walidacji. Zachowano testy trwałości i bezpieczeństwa starego transportu Research. Oryginały wszystkich testów są w kopii bezpieczeństwa. Nie przywracano usuniętych płatnych fallbacków ani cache.
- --self-test obejmuje teraz również sześć wcześniej rozjechanych modułów Tavily i nowe regresje gotowości.
- Dodano Start-KI2.ps1: bezwzględne ścieżki do programu i bazy wyprowadzane z folderu skryptu, interpreter miniconda3, ukryty launcher, sprawdzenie procesów i panelu. Powtórne wywołanie nie tworzy drugiego skanera. -CheckOnly niczego nie uruchamia.

## Weryfikacja

- `python -B -X utf8 -m unittest discover -s . -p 'test*.py'`: 292/292 OK.
- `python -B -X utf8 KI.py --self-test`: 316/316 OK (17+46+42+7+29+175).
- `python -B -X utf8 KI.py --panel-test`: 24/24 OK.
- `python -B -X utf8 KI.py --launch-test`: 5/5 OK; rzeczywisty panel i skaner diagnostyczny na bazach tymczasowych.
- `git diff --check`: OK.
- Kopia kodu, oryginalnych testów, zrzuty stanów zadań i doręczeń, spójna kopia bazy: `backup_20261025_readiness`. `PRAGMA quick_check=ok`; hashe w manifest.json.
- Nie wykonywano nowych płatnych testów Tavily/OpenAI ani dodatkowych testowych wiadomości Telegram.

## Stan po kontrolowanym restarcie

25.10.2026 18:36 UTC (19:36 Europe/Berlin): launcher 24596, skaner 25716, panel 24948. Potwierdzono RUNNING, pierwszy cykl OK, oba workery READY ze świeżymi heartbeatami i poprawnymi PID. Lista obserwacji: 452.
Stan zapisany w `backup_20261025_readiness/after-restart.json`.
Pipeline i Telegram pozostają włączone zgodnie z dotychczasowymi ustawieniami.
Nie czyszczono 35 FAILED, jednego REVIEW_REQUIRED ani 22 SELECTED. Brak produkcyjnego DONE dla automatycznej analizy pozostaje faktem historycznym, nie potwierdzeniem niesprawności po tej naprawie.

## Jutro 26.10.2026 o 08:00 Europe/Berlin

Utworzono jednorazową automatyzację w tym czacie: `ki-2-kontrola-startu-26-pa-dziernika-o-08-00`.
Ma uruchomić Start-KI2.ps1 tylko w razie potrzeby i sprawdzić panel oraz heartbeat skanera i obu workerów. Przy poprawnym działaniu nie restartuje. Nie ponawia historycznych zadań i nie wykonuje ręcznych płatnych testów.
Lokalna automatyzacja wymaga działającego komputera i aplikacji Codex; nie jest mechanizmem włączania komputera.
Ręczny start: `powershell -NoProfile -File "C:\Users\szela\OneDrive\Desktop\KI\2 KI\Start-KI2.ps1"`.

## Zachowane decyzje i granice

Raport o 17:05, także pusty w dni bez sesji, pozostaje zgodnie z decyzją użytkownika. Nie zmieniano progów kwalifikacji ani bramek świeżości/sesji. Nie kopiowano modułów Alchemika, nie zmieniano sekretów. Nie wykonywano commitu ani push.
Pełna naturalna ścieżka nowej okazji w otwartej sesji → Tavily → AI → Telegram wymaga obserwacji podczas sesji. Pełny kalendarz świąt i skróconych sesji, rozdzielenie rodzajów raportów w outbox oraz operatorskie porządkowanie historycznych SELECTED pozostają osobnymi zadaniami.
Przejście do prac nad Alchemikiem przed 09:00 wymaga osobnego etapu z użytkownikiem; automatyzacja poranna nie edytuje Alchemika.
