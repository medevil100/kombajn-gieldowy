# KI 2 — audyt przed push i VPS, 28.10.2026

Projekt: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`. Zakres: aktualny kod i jego lokalna kopia testowa, SQLite, kolejki, zapisane odpowiedzi dostawców, Git i statyczna gotowość do Linux. Bez push, zakupu, logowania do Hetznera i ręcznych płatnych wywołań. Pomiary są zapisami z chwili audytu, nie stałymi licznikami.

## Ocena

**Push kodu: możliwy po świadomym przygotowaniu nowego commitu i końcowej kontroli indeksu.** Ostatni commit to `14493f3`; późniejsze zmiany nie są w nim zapisane. Nie należy wykonać `git add .`: w katalogu pozostają niezależna zmiana `_ai_review.py`, Alchemik i lokalne materiały robocze. Push nie jest wdrożeniem aplikacji.

**Produkcja na VPS: jeszcze warunkowa.** Lokalna weryfikacja jest poprawna, ale nie wykonano instalacji ani testu uruchamiania na docelowym Linux. Przed przełączeniem trzeba sprawdzić odtwarzanie środowiska, usługę startową, uprawnienia, backup z harmonogramem, dostęp do panelu i działanie jednego skanera. To warunki wdrożenia, nie nowe funkcje skanera.

## Wyniki techniczne

| Kontrola | Wynik |
|---|---|
| Testy plikowe kandydata z bid/ask | 364, OK |
| Testy wewnętrzne | 348, OK |
| Testy panelu | 24, OK |
| Testy uruchamiania | 5, OK |
| SQLite quick_check | ok |
| Naruszenia kluczy obcych | 0 |
| Doręczone wiadomości w odczycie | 156 |
| Doręczone bez delivery_receipt | 0 |
| Oczekujące/niepewne wysyłki w odczycie | 0 |
| Watchlista w odczycie | 428 |
| Śledzone w Git ścieżki sekretów/baz/logów | 0 |
| Wzorce kluczy w bieżących śledzonych plikach | 0 |
| Wzorce kluczy w sprawdzonych nowych modułach i danych testowych | 0 |

Testy częściowo się pokrywają; ich liczby nie są liczbą niezależnych scenariuszy łącznie. Skan wzorców sekretów jest kontrolą heurystyczną, nie matematycznym dowodem braku wszystkich poufnych danych. Wynik dodatkowego skanu zawartości historii Git jest dopisywany przy finalizacji audytu.

## Zapisane zadania i rzeczywista jakość

W odczycie bazy: 147 DONE, 51 FAILED, 30 FILTERED i 42 REVIEW_REQUIRED. To historia wielu wersji, w tym dawnych problemów i usuniętego DeepSeek; nie jest bieżącym wskaźnikiem awarii workerów. Ręczne raporty: 24 DONE i 15 REVIEW_REQUIRED. Starych zadań nie wznowiono.

Po poprawce cytatów i diagnostyki z 28.10, 15:17 UTC: 4 DONE, 1 FILTERED i 2 REVIEW_REQUIRED, bez nowego HTTP 400 w zbadanej próbie. Dwa zatrzymane wyniki pomijały ograniczenie częściowego wolumenu. Walidator działa, ale model nadal popełnia błędy. Także w publikowanych analizach występują miękkie usunięcia niepoprawnych zdań. Nie należy luzować bramek tylko po to, aby wynik uzyskał DONE.

Szczegółu wcześniejszych HTTP 400 nie zapisano; ich dokładna przyczyna pozostaje niepotwierdzona. Nowy transport zapisuje bezpieczne dane odmowy. Brak nowego błędu w małej próbie jest dobrym sygnałem, a nie dowodem trwałego usunięcia problemu.

## Bid/ask — uzupełnienie w tym audycie

Dodano wspólną linię ofert w Telegramie, pełnej analizie automatycznej, karcie rankingu i statusie zapisanej analizy ręcznej: bid, ask, wyliczony spread, świeżość oraz czas pobrania. Korzysta ona z zapisanego materiału; nie pobiera dodatkowych ofert i nie wywołuje AI.

Spread jest liczony z prawidłowej pary bid <= ask względem środka kwotowania. Braki i niespójna para nie są uzupełniane ceną ostatniej transakcji. Widoczny czas pobrania nie potwierdza czasu aktualizacji ofert. Potwierdzenie świeżości wymaga osobnego czasu oferty, potwierdzenia źródła i wieku do 60 sekund. Sam znacznik czasu pobrania lub flaga bez czasu oferty nie wystarcza.

W próbce aktualnych zdarzeń większość ofert była dostępna liczbowo, ale ich świeżość pozostawała niepotwierdzona. Wystąpiła też para bid > ask i przypadek brakujących obu wartości. To uzasadnia jawne prezentowanie braków. Yahoo nie zapewnia w tej konfiguracji potwierdzonego czasu aktualizacji bid/ask, więc aplikacja nie gwarantuje wykonalności transakcji. Nie zmieniono dostawcy ani warunków detekcji.

## Baza i sprawdzona kopia

Plik główny miał około 4,19 GB. Utworzono pełną kopię przez mechanizm SQLite backup ze spójnego odczytu, obejmującą także dane zatwierdzone w WAL. Kopia ma 4 203 253 760 bajtów; jej quick_check = ok, naruszenia FK = 0.

Porównano dokładne liczby rekordów źródła i kopii: watchlist 428, observations 43 652, events 3 888, analysis_jobs 270, research_requests 270, outbox 156, delivery_receipts 156, cycles 720. Wszystkie się zgadzają. Nie kasowano danych i nie wykonywano VACUUM ani migracji historycznej.

Lokalna kopia audytowa:
`C:\Users\szela\.codex\visualizations\2026\10\24\01a16d6f-31ac-7bf2-86e3-26fcecc5967f\ki2-prepush-audit-20261028\KI.audit-backup.sqlite3`

To zweryfikowana kopia danych. Nie jest dowodem odtworzenia całej usługi, sekretów i środowiska na VPS. Wielkość historii rośnie, a pełne snapshoty obserwacji są głównym składnikiem bazy. Przed doborem dysku trzeba uwzględnić bieżącą bazę, WAL, kopie i retencję; nie dobierać pojemności wyłącznie do kodu aplikacji.

## Wywołania i koszty

W zapisanych rozliczeniach automatu: 1 440 999 tokenów wejścia, 44 850 wyjścia, razem 1 485 849 w 180 odpowiedziach z usage. Ręczne raporty mają 685 709 tokenów w 35 zapisach z usage. Nie są to pełne koszty konta ani koszt wyłącznie dzisiejszego dnia. Brak usage nie oznacza zerowego kosztu, a historyczne odpowiedzi mogą pochodzić z różnych dostawców.

Z zapisanych odpowiedzi Tavily: 466 kredytów Search (233 odpowiedzi z rozliczeniem) i 15 Extract (52 odpowiedzi z rozliczeniem). Nie przeliczano tego na walutę ani fakturę. Bramka OpenAI działa po zebraniu kontekstu; odrzucenie AI nie oznacza, że poprzedzający Search był bezpłatny. Zasady pojedynczych wywołań i braku automatycznych ponowień pozostają zachowane.

## Co sprawdzić przed Hetznerem

1. Po audycie przygotować commit obejmujący rzeczywiście potrzebne zmiany KI 2, nowe moduły, testy i niezbędne dane testowe. Zweryfikować czysty eksport tego commitu przed push. Nie dodawać bazy, sekretów, logów, kopii audytu ani Alchemika.
2. Na docelowym Linux odtworzyć środowisko w osobnym venv. Obecne requirements zawierają minimalne wersje, a nie pełny lock. Zapis zmierzonych wersji jest w danych audytu; nie przenosić windowsowego środowiska Conda jako gotowego środowiska serwera.
3. Wykonać testy offline, diagnostyczny start i zatrzymanie bez płatnych usług. Kod ma gałęzie POSIX, ale w tym audycie wykonano testy Windows. PowerShell `Start-KI2.ps1` służy lokalnemu Windows; Linux powinien korzystać z uruchomienia Python CLI i nadzorowanej usługi.
4. Skonfigurować użytkownika usługi, prywatne sekrety poza Git, zapisywalny katalog danych, strefy czasowe i uprawnienia. Panel pozostawić na loopback i udostępniać kontrolowanym kanałem, zamiast otwierać niezabezpieczony port publiczny.
5. Ustawić start po restarcie, monitoring i regularne kopie z retencją, następnie wykonać próbę odtworzenia usługi z kopii. Przed planowanym restartem poczekać na zakończenie aktywnej analizy i wysyłki; nie wymuszać ponowień zadań o niepewnym wyniku.
6. Oddzielnie potwierdzić środowisko opcjonalnej analizy pogłębionej TradingAgents, jeśli ma działać na serwerze. Zwykły automat korzysta z zewnętrznych API; ten audyt nie testował płatnego działania TradingAgents na Linux.
7. Dopiero po próbie przełączyć normalną pracę: zatrzymać lokalny skaner przed uruchomieniem produkcyjnego na VPS. Nie wykonywać równoległych analiz i wiadomości z dwóch hostów.

Kalendarz pozostaje poza zakresem zgodnie z ustaleniem. Audyt nie dodaje nowych strategii, automatycznych transakcji ani dostawców danych. Najważniejszy następny etap to kontrolowane wdrożenie i obserwacja, nie dokładanie funkcji.

## Skan historii Git przy finalizacji

Sprawdzono tekstowych obiektów Git: 803. Flagi wzorców sekretów: 0. Pominięte duże obiekty: 0. Binarne obiekty nie były skanowane tekstowo. Przy flagach lub pominiętych obiektach potrzebna jest osobna kontrola przed push. Skan nie jest gwarancją braku wszystkich danych poufnych.
