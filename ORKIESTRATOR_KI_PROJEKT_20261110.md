# Orkiestrator spółki w KI — wersja 1, 10 listopada 2026

Status: wdrożono na VPS 10 listopada około 17:04 UTC (18:04 CET). Dwanaście testów instalatora i wszystkie fazy regresji VPS PASS, graf TradingAgents sprawdzony offline; panel i trzy świeże heartbeaty potwierdzone. Właściciel zatwierdził: wzrosty do obserwacji, spadki jako osobne ostrzeżenia, TOP 5 wyłącznie z kompletnym technicznym planem SL/TP. Naturalne nowe decyzje i ich doręczenia nadal wymagają obserwacji.

Paczka `ki2-orkiestrator-vps-20261110.tar.gz`, SHA256 `36ce51c69122a27e9e86623dde0904570ea2199fe31e47b274034c573fe6a6b0`. Raport `/home/ubuntu/ki2-orkiestrator-vps-20261110/tests-20261110T170232454592Z`; jednostka `ki2-orchestrator-install-20261110.service`, success/0. Kopia poprzedniego kodu `/home/ubuntu/ki2/backup-orchestrator-20261110T170431420202Z`. Baza, klucze, ustawienia i kolejki zachowane. Nie wykonano płatnych testów ani testowych wiadomości.

## Implementacja

`company_orchestrator.py` dostarcza wspólną politykę oceny danych i ról. Jest wywoływana przez skaner przy każdym poprawnie pobranym odczycie, kwalifikację partii, kolejkę przed dostawcami, preflight AI, kontrolę publikacji i odczyt panelu. Łączy cenę od bazy i od otwarcia, aktywność, technikę, pełność sesji, plan, stan ofert i załadowane tło. W nowym pakiecie AI są również jawne powiązania i rola orkiestratora. Interpretację nadal wykonuje istniejący model dla każdej spółki oddzielnie; nie dodano kolejnego modelu ani dostawcy.

Stan obejmuje następną akcję i warunek, etap potwierdzenia, kierunek, rolę, fakty wspierające i sprzeczne, konkretne braki oraz odwołanie do poprzedniej oceny. Dane niezaładowane do oceny mają odrębny stan od potwierdzonego braku. Poprzednia ocena i brak istotnej zmiany zatrzymują nowe wywołanie; starszy wynik nie może nadpisać stanu nowszego odczytu. Błąd albo odrzucenie oceny pozostawia stan do sprawdzenia, bez zmiany zadania i bez ponowienia.

Ostatni stan każdej spółki jest zapisywany pod `runtime` → `orchestrator:TICKER`; nie tworzy to nowej historii dużych migawek. Panel „Końcowe oceny AI” ma rozwijany odczyt decyzji z pustym początkowym wyborem tickera. Również spółka niedopuszczona do AI ma widoczny powód oczekiwania. Audyt ma liczniki `orchestration.actions` i `orchestration.roles`; są to ostatnie stany spółek, nie liczba wszystkich przejść.

TOP 5 pokazuje tylko świeże wzrosty z poprawną oceną AI i kompletnym planem: spójna cena, SL, dwa odrębne TP, potwierdzone wsparcie i opory, ATR, poprawna relacja potencjału do ryzyka, zgodna waluta i czas oraz ważność planu. Aktualny odczyt musi podtrzymywać kwalifikację. Brak planu nie blokuje wcześniejszej analizy — kieruje wynik do odrębnych wzrostów do obserwacji. Spadki trafiają do osobnych ostrzeżeń. Wszystkie grupy zachowują pełne opisy; każda lista w panelu ma limit pięciu, pozostałe raporty są w końcowych ocenach.

Telegram pozostaje jednym zbiorczym zestawieniem do sześciu niezależnych ocen na cykl, bez minimum wyborów. Każda pozycja ma jednoznaczną rolę: wzrost z planem, wzrost do obserwacji albo ostrzeżenie spadkowe. Wstępny etap pozostaje dodatkowo jawnie oznaczony licznikiem potwierdzeń. Plan jest odniesieniem technicznym; nie potwierdza ceny wykonania, płynności ani przyszłej kontynuacji.

Zamrożone żądania V1/V2 bez metadanych orkiestratora zachowują pierwotne wejście. Nowe metadane nie są do nich dopisywane, a dawne raporty nie są przepisywane ani ponawiane. Nowy prompt ma wersję KI-PROMPT-20261110-v7. Baza, klucze, konfiguracja, kolejki i rzeczywiste liczniki potwierdzeń nie są podmieniane.

## Potwierdzona luka

`run_market_cycle` zbiera dane i zapisuje matrycę, `record_opportunity` i `reserve_opportunities` kwalifikują ruch, `early_company_review` dopuszcza kandydatów przed trzema potwierdzeniami, `final_company_review` tworzy partie i zbiorczą publikację, a TOP 5 ponownie filtruje gotowe raporty. Każda warstwa ma potrzebne kontrole, ale decyzja nie ma jednego wspólnego, czytelnego zapisu powiązań i następnego kroku dla instrumentu.

Obecne ALIGNED oznacza zgodność wskazań z wykrytym kierunkiem. Może opisywać spadek. Obecne INFORM oznacza materiał do obserwacji; nie wymaga kompletnego planu technicznego. TOP 5 sortuje takie raporty według punktacji, więc jego nazwa może być rozumiana szerzej niż rzeczywiste warunki kwalifikacji. Samo zwiększenie liczby raportów albo kolejne poluzowanie promptu nie ustala tej semantyki.

Przesłany raport oznaczony przez właściciela jako STNI ma dane do 17:11 CET, a wstępną ścieżkę wdrożono około 17:17 CET. Jest wcześniejszym zapisem. MACD/histogram są ujemne, −DI przewyższa +DI, a cena jest poniżej wskazanych średnich. Jest to przykład spadkowego układu, nie dowód zasadności pozycji kupna. Brakuje lokalnego wsparcia i kompletnego planu. Oferty pokazują szeroki spread, ale ich świeżość jest niepotwierdzona — nie wolno traktować go jako udowodnionego aktualnego kosztu wykonania. Nie zweryfikowano nazwy emitenta na podstawie zapisu tickera właściciela.

## Jedno wejście i jeden zapis decyzji

Sterownik powinien otrzymywać dane wyłącznie tej spółki: zaakceptowaną migawkę, poprzedni porównywalny odczyt, całą dostępną sesję do chwili oceny, poprawną bazę, wskaźniki, poziomy i scenariusze, zapisane fundamenty oraz wcześniejszą ocenę i historię własnych sygnałów. Każdy element zachowuje źródło, czas oraz kompletność. Dane późniejsze od migawki nie uzasadniają wcześniejszej decyzji.

Wspólny wynik powinien zawierać tożsamość i wersję danych, kierunek, etap potwierdzenia, rolę sygnału, gotowość poszczególnych warstw, fakty wspierające i sprzeczne, ograniczenia oraz jedną akcję następnego kroku. Brak danych, brak zdarzenia i negatywny fakt są odrębnymi stanami. RSI i MACD nie zastępują wyceny fundamentalnej; wolumen nie dowodzi płynności, a nieznana przyszłość jest zastrzeżeniem wspólnym dla wszystkich przypadków.

| Warstwa | Powiązanie do oceny |
| --- | --- |
| Cena i sesja | ruch od poprzedniego zamknięcia, od otwarcia i przebieg sesji |
| Aktywność | przyrost w tej samej świecy, pełna godzina versus godzina otwarta, bez wielokrotnego sumowania |
| Technika | zgodność i sprzeczności względem rzeczywiście wykrytego kierunku |
| Poziomy | potwierdzone wsparcia/opory, odległości, dostępność planu i warunek zanegowania |
| Informacje o emitencie | datowane fakty, brak wiadomości i niepotwierdzona przyczynowość oddzielnie |
| Historia i fundamenty | opisowe tło tej spółki z ujawnioną próbą, bez gwarancji dalszego ruchu |
| Wcześniejsza ocena | istotna zmiana dowodów, ukończenie potwierdzenia lub brak powodu do ponownego wywołania |

## Sterowanie przepływem

Jedna polityka powinna wybierać: czekać na określone dane, obserwować wstępny ruch, zlecić jedną ocenę, zachować tylko w panelu albo opublikować wybrany wynik. Przy decyzji czekania trzeba wskazać konkretny brak i warunek ponownego sprawdzenia. Zapis decyzji musi pokazywać również spółki niewysłane do AI; pusty Telegram nie może pozostawiać użytkownika bez wyjaśnienia.

Istniejący zbieracz danych i workery powinny wykonywać te akcje w normalnym cyklu. Sterownik nie może uruchamiać nieograniczonych zapytań ani samodzielnie zmieniać ustawień. Wspólny limit ocen, blokada dostawcy, deduplikacja, granice czasu i kontrola przed publikacją pozostają. Kontrole krytyczne nadal obowiązują w workerach jako ochrona przed zmianą danych między etapami.

TOP 5 i Telegram mają przedstawiać ten sam końcowy zapis decyzji wraz z jego datą, rolą sygnału i ograniczeniami. Wstępny sygnał, ostrzeżenie spadkowe i przypadek z pełnym planem nie powinny otrzymywać nierozróżnialnej etykiety. Nie należy jednak wypełniać listy na siłę ani usuwać danych pozostałych spółek.

## Weryfikacja i wdrożenie

Wymagane testy obejmują cały przepływ i powiązania: silny wczesny ruch HUMA, sygnał spadkowy zgodny technicznie, brak planu, brak świeżego bid/ask, rzeczywistą sprzeczność, zmianę danych w trakcie analizy, puste zestawienie z konkretnymi przyczynami, deduplikację i przejście etapu bez przepisywania historii. Następnie pełna regresja Windows/Linux i kontrolowany pakiet VPS. Bez płatnych testów, historycznych powiadomień i nadpisywania bazy.

Potwierdzono 17 nowych testów orkiestratora oraz pełną regresję Windows i Ubuntu WSL: 769 testów modułów, 522 wbudowane, panel 26 i uruchamianie 5 OK (pominięcia zależne od platformy). JavaScript OK na Windows; Linux bez Node nie uruchamiał tej fazy. Dwanaście testów instalatora przeszło na obu systemach, w tym brak albo dokładna znana wersja dwóch opcjonalnych plików testowych i odrzucenie nieznanej treści. Kod wykonawczy wymaga jednej dokładnej wersji bazowej. Pierwsza regresja wykryła nieaktualne oczekiwanie komunikatu pustego TOP 5 w teście panelu; oczekiwanie dostosowano do nowego wymagania planu, bez usuwania kontroli widoku. Oddzielnie naprawiono zachowanie zamrożonych kontraktów, aby nie dopisywać im nowych metadanych.

Przed podmianą wymagane są pełne testy aktualnej paczki na VPS oraz kompilacja grafu TradingAgents offline. Naturalne działanie po wdrożeniu nadal wymaga obserwacji; testy nie potwierdzają skuteczności inwestycyjnej selekcji.
