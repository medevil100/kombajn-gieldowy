# KI 2 — nadzór techniczny, 31.10.2026

Projekt: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`.
VPS: `/home/ubuntu/ki2`. Nie dotyczy Tavli ani Alchemika.

Stan końcowy: nadzór wdrożony i sprawdzony na VPS. Odczyt delegowany do
jednostki systemd jako ubuntu ma status HEALTHY, timer nadzoru wznowiony,
40 testów Linux zakończonych poprawnie. Szczegóły wdrożenia i wcześniejszych
prób diagnostycznych znajdują się poniżej.

## Potwierdzony punkt wyjścia

Odczyt użytkownika z 31.10.2026, 18:10:42 UTC:

- `ki2`, `tavli-backend`, `ki2-backup.timer`: active.
- Backup nowej, skompresowanej bazy zakończył się poprawnie 03:30:24 UTC;
  trwał 21,664 s. Nazwa `ki2-20261031T033003608886Z.sqlite3`.
- KI wznowione po kopii. Skaner: 59 cykli, brak opuszczonych slotów,
  ostatni cykl OK; scanner heartbeat 18:10:37, analysis 18:10:39,
  Telegram 18:10:41 UTC, ten sam PID 45728.
- Dysk 60% zajęty, 16 GB wolnego.

Nie zmieniamy oceny inwestycyjnej, promptów, cen, źródeł, progów, limitów
kosztowych ani zachowania FAILED/REVIEW_REQUIRED. Autonomiczna ocena analiz
jest następnym etapem.

## Zakres pierwszej wersji

Niezależny `ki2_guardian.py` używa wyłącznie standardowej biblioteki Pythona.
Timer systemd sprawdza stan co około 2 minuty. Sprawdzenia obejmują:

- prawidłową odpowiedź `ok` lokalnego panelu (bez proxy i przekierowań);
- wiek heartbeatów, statusy i zgodność PID modułów;
- postęp cyklu niezależnie od osobnego wątku heartbeat;
- wynik zadania backupu, aktywność timera i wiek najnowszego pliku kopii;
- wolne miejsce z uwzględnieniem rozmiaru bazy i zapasu na następną kopię;
- trzy zakończone cykle z błędem dostawcy lub jego limitem.

Audyt nie odczytuje payloadów obserwacji, odpowiedzi Research ani promptów.
Odczyt SQLite ma `mode=ro` i `query_only=ON`. Root zleca systemd krótką,
odrębną jednostkę odczytu z `User=ubuntu`, `Group=ubuntu` i `NoNewPrivileges=yes`,
w izolowanym skrypcie, aby ewentualne pliki
WAL/SHM nie zmieniły właściciela. Nie importuje KI jako root.
Audyt kopii sprawdza świeżość pliku i wynik istniejącego zadania backupu;
nie robi pełnego quick_check co dwie minuty i nie zastępuje testu odtworzenia.

## Kontrolowane przywracanie

Restart tylko po 3 kolejnych potwierdzeniach tego samego problemu technicznego,
po 5-minutowym okresie startowym. Co najmniej 30 minut przerwy pomiędzy
próbami, najwyżej dwie próby w ostatnich 24 godzinach, także po restarcie VPS.
Budżet zapisuje się atomowo przed wykonaniem komendy. Tylko stała komenda
`systemctl try-restart ki2.service`: ręcznie zatrzymana usługa pozostaje zatrzymana.

Zwykła przerwa między cyklami nie jest zawieszeniem. Cykl może trwać do
45 minut przed zgłoszeniem braku postępu; brak zakończonego/aktywnego cyklu
przez godzinę także jest sygnałem. Wstrzymanie skanowania w ustawieniach
wyłącza ocenę postępu cyklu. Zamknięty rynek ani stare ceny w sobotę
nie stanowią awarii. DISABLED modułów usług jest poprawnym stanem.

Backup, rozruch i ręczne zatrzymanie mają osobne stany bez restartów.
Zbyt mało miejsca lub nieprawidłowy zegar blokują restart i wymagają
interwencji. Błąd backupu i błąd źródła danych powodują powiadomienie,
bez restartowania programu w pętli ani dodatkowych żądań do dostawcy.
Nadzór nie usuwa plików i nie ponawia historycznych zadań.

## Współpraca z płatnymi wywołaniami

`ki2_ops_guard.py` obejmuje pełne operacje analizy, wysyłki, ręcznych pytań,
wznawiania i uruchamiania TradingAgents wspólną blokadą odczytu na Linuxie. Blokada trwa
od wejścia do funkcji przed rezerwacją po zapis wyniku i potwierdzeń.
Nadzór wymaga wyłącznej blokady przed restartem. W tym czasie nowa operacja
automatu odkłada się przed claimem, a ręczna pokazuje przerwę techniczną.
Trwająca operacja uniemożliwia restart. Proces TradingAgents jest chroniony
trwałym stanem QUEUED/RUNNING utworzonym przed zwolnieniem blokady procesu
uruchamiającego; dzięki temu nowy proces nie traci zadania przy krótkiej
kolizji z kontrolą nadzoru. Sprawdzane są dodatkowo zajęte wpisy
analysis/outbox/manual/deep_reports po zamknięciu bramki.

Na Windows i bez zainstalowanego nadzoru zachowanie jest dotychczasowe.
Uszkodzona istniejąca blokada zatrzymuje wywołanie przed API i zgłasza błąd.
Niepewnych operacji nie wolno automatycznie resetować. Zawieszone wywołanie
trzymające blokadę powoduje alarm i wymaga kontroli, nie jest zabijane.

## Backup i kolejność usług

Dodatek `ki2-backup-guardian.conf` ustawia backup po już aktywnym zadaniu
nadzoru. Chroni to przed startem kontrolowanej kopii w środku restartu.
Jeśli backup działa wcześniej, nadzór widzi MAINTENANCE i kończy kontrolę.
ExecStart, wrapper backupu, jego retencja i godzina 03:30 UTC są zachowane.
Guardian nie ma zależności After od KI, bo sam może synchronizować jego restart.

## Powiadomienia

Pierwszy potwierdzony incydent wysyła jedną wiadomość Telegram.
Powrót zgłaszany po dwóch poprawnych kontrolach. Zdrowy stan jest cichy;
nie wysyłamy wiadomości testowych. Każda próba powiadomienia jest zapisana
przed HTTP. Nieznane doręczenie nie jest ponawiane automatycznie.
Adres bota, tokeny i odpowiedzi błędów nie trafiają do logu.
Nie wykonuje się żadnego zapytania OpenAI/Tavily.

## Instalacja i ochrona plików

Instalacja odbywa się z pakietu zawierającego manifest sum kontrolnych.
Instalator root sprawdza manifest i oczekiwaną wersję KI przed zmianami.
Nie rozpoczyna instalacji przy kopii, aktywnych zadaniach lub już działającym
drugim nadzorze. Podczas pierwszego wdrożenia nie uruchamiać ręcznych analiz
z innego urządzenia: stary kod nie ma jeszcze wspólnej blokady.
Instalacja krótko zatrzymuje KI i zachowuje kopię kodu. Błąd kopiowania,
walidacji systemd lub startu panelu przywraca poprzedni kod i wznawia KI.
Nie podmienia bazy ani pliku sekretów.

Uprzywilejowany skrypt jest kopiowany jako root do `/usr/local/lib/ki2-guardian`,
poza zapisywalnym przez aplikację kodem. Uruchamia go `/usr/bin/python3 -I`.
Własny stan jest w `/var/lib/ki2-guardian`, blokada w `/run/ki2-guardian`.
Jednostka ma ograniczenia systemd i nie otwiera publicznego portu.
Instalator najlepiej uruchomić przez przejściową usługę systemd-run, aby
zerwanie SSH nie przerwało kopiowania i przywracania usługi.

`ki2-guardian.service` jest oneshot: po kontroli może być inactive/success.
To poprawne. `ki2-guardian.timer` ma być active. Wynik ostatniej kontroli:
`sudo journalctl -u ki2-guardian.service -n 5 --no-pager`.
Zatrzymanie nadzoru: `sudo systemctl disable --now ki2-guardian.timer`.
Nie zatrzymuje to KI i nie usuwa danych.

## Testy i ograniczenia

Testy offline obejmują stan zdrowy w weekend, świadomą pauzę, backup,
grace period, świeżość/PID, postęp cyklu, limity restartów, zajęte kolejki,
powiadomienia bez ponowień, brak ujawnienia sekretów i odczyt prawdziwego
SQLite bez zmiany danych. Dwa testy prawdziwego flock/procesu wymagają
Linuxa i są pomijane na Windows. Muszą przejść na VPS przed włączeniem.
Dotychczasowe testy aplikacji, panelu i uruchamiania należy także zachować.

Bez działania VPS, sieci lub samego Telegrama alarm nie ma gwarantowanego
doręczenia. Zewnętrzny monitor, pełny test odtwarzania i automatyczne kopie
poza VPS pozostają osobnymi zadaniami. Nadzór nie ocenia jeszcze trafności AI.

## Wyniki przygotowania i wdrożenia

- Lokalnie: 445 testów plikowych (2 testy Linux pominięte), self-test
  zakończony kodem 0 (ostatni zestaw: 288), 24 testy panelu i 5 testów
  prawdziwego uruchamiania — OK. Test startu wymagał wyjścia poza ograniczenia
  sieciowe piaskownicy Windows; po tym przeszedł bez zmiany kodu testów.
- Pakiet: `ki2-guardian-20261031.tar.gz`, SHA-256
  `52668a43a4a52a17bf4afb895132f52cd203ead548009840d88f3de74831578d`.
- Użytkownik potwierdził poprawną instalację na VPS 31.10.2026,
  18:50:46 UTC. Aktywne: KI, timer nadzoru, timer kopii.
- Kopia poprzedniego kodu:
  `/home/ubuntu/ki2/backup-guardian-code-20261031T185040626125Z`.
- Pierwsza kontrola: GRACE, brak problemów, brak akcji. KI działało od
  około 5 sekund, więc jest to oczekiwany okres ochronny po starcie.
- Pierwsza kontrola w okresie ochronnym nie potwierdzała jeszcze pełnego
  odczytu bazy. Późniejsze próby i końcowe HEALTHY opisano poniżej.
  Nie wykonywano wymuszonego restartu ani próbnej wysyłki.
- Identyfikator commita i stan publikacji należy sprawdzać w Git.
  `_ai_review.py` pozostaje niezależną zmianą użytkownika, poza tym zakresem.

## Korekta uruchamiania odczytu jako ubuntu

Pierwsza pełna kontrola 18:56:59 UTC wykazała AUDIT_UNAVAILABLE. W logu PAM
pojawił się błąd tymczasowej zmiany UID podczas odczytu uruchamianego przez
runuser jako proces potomny monitora. Action NONE: KI nie było restartowane.
Nadzór wysłał jeden alarm o własnej niedostępności. Timer zatrzymano na czas
diagnostyki. Samodzielna próba odczytu przez runuser w odtworzonych ograniczeniach
systemd zakończyła się poprawnie około 19:03 UTC: skaner i workery świeże,
busy_jobs=0, ostatnie trzy cykle OK. To nie dowodzi pełnej przyczyny błędu PAM;
wykazało różnicę pomiędzy samodzielnym a zagnieżdżonym uruchomieniem odczytu.

Poprawka używa parametrów subprocess `user='ubuntu'`, `group='ubuntu'`,
`extra_groups=()`, jawnego cwd `/` i minimalnego środowiska. Nie potrzebuje
PAM i nie wyłącza ograniczeń usługi. Odrzucone odpowiedzi dziecka mają teraz
ograniczoną diagnozę (kod i nazwa typu błędu), bez stderr, kluczy i odpowiedzi
dostawców. Zgodność parametrów:
https://docs.python.org/3/library/subprocess.html#subprocess.Popen

Lokalne testy nadzoru: 39, w tym 2 pomijane na Windows testy Linux. Przed
podmianą produkcyjnego skryptu instalator poprawki odtworzy wszystkie ograniczenia
systemd, włącznie z UMask, StateDirectory i RuntimeDirectory, i uruchomi nowy
kod wyłącznie w trybie odczytu. Wymagany status HEALTHY. Przy innym wyniku
kod zostaje bez zmian, a timer nadzoru pozostaje zatrzymany. KI, jego baza i timer
kopii pozostają aktywne. Stan incydentu i budżet restartów są zachowane.

Wynik tej przygotowanej próby opisano w kolejnym punkcie; tego wariantu
nie wdrożono, ponieważ nie przeszedł kontroli w środowisku usługi.

### Wynik prób i odrębna jednostka odczytu

Próba bezpośredniego obniżenia UID/GID w pełnym monitorze także zakończyła się
CHILD_START_FAILED/PermissionError o 19:26 UTC. Instalator odmówił podmiany;
KI i kopie pozostały aktywne, timer nadzoru zatrzymany. Dodatkowa próba o około
19:31 UTC wykazała, że sam proces ma CAP_SETUID/CAP_SETGID, a proste przypadki
zmiany UID, GID i grup działają. Nie ustalono więc pełnej przyczyny zależnej od
kontekstu błędu; nie należy opisywać jej jako globalnego braku uprawnień UID.

Ta sama próba potwierdziła poprawny odczyt rzeczywistej bazy przez odrębną
jednostkę systemd z User=ubuntu: świeże heartbeat'y, busy_jobs=0, trzy cykle OK.
Aktualna wersja stosuje tę potwierdzoną ścieżkę. Proces główny nie zmienia UID
potomka; zarządca usług tworzy odrębną jednostkę z tożsamością ubuntu.
Jednostki mają unikalne nazwy, timeout 20 s, --collect, --wait i --pipe.
Ograniczenia systemd są zachowane także dla odczytu. Do jednostki nie są
przekazywane sekrety, a polecenie jest stałym izolowanym skryptem odczytu.

Testy nadzoru: 40 (2 testy Linux pomijane na Windows). Podmiana produkcyjnego
monitora nadal jest warunkowana statusem HEALTHY w całym środowisku usługi.
Potwierdzenie wdrożenia tej wersji znajduje się w kolejnym punkcie.

### Potwierdzone wdrożenie odrębnego odczytu

Użytkownik przekazał wynik 31.10.2026, około 20:10 UTC:

- Wszystkie 40 testów nadzoru na VPS: OK, bez pominięcia testów Linux.
- Odczyt w kompletnym odtworzonym środowisku systemd: HEALTHY.
- Instalator podmienił monitor i sprawdził rzeczywistą usługę: warunek
  `last_status == HEALTHY` został spełniony przed wznowieniem timera.
- Timer nadzoru został wznowiony. KI nie było restartowane.
- Kopia poprzedniego monitora:
  `/home/ubuntu/ki2/backup-guardian-owner-20261031T201015555329Z`.
- Stan incydentu i budżet restartów zachowane. Kolejny poprawny cykl może
  wysłać naturalne powiadomienie o przywróceniu działania; bez wiadomości testowej.
- Pakiet poprawki `ki2-guardian-reader-fix-20261031.tar.gz`, SHA-256:
  `83c9dcba8fbcb0a50552d3ecf9af45e9f51bceb2a3b36d710eaa42d4fe99df53`.
- Lokalny kompletny zestaw po poprawce: 449 testów, 2 testy Linux pominięte
  na Windows, następnie potwierdzone na VPS w zestawie 40.

Pełna przyczyna wcześniejszej różnicy pomiędzy prostym testem UID a działaniem
wewnątrz monitora pozostaje nieustalona. Zastosowany i sprawdzony wariant
deleguje odczyt zarządcy usług, bez wyłączania zabezpieczeń.
Nocna kopia po integracji nadzoru i obserwacja kolejnych okresowych kontroli
pozostają kolejnymi sprawdzeniami operacyjnymi. Nie wymuszano awarii ani
restartu produkcyjnego KI w celu testowania automatycznej naprawy.

Sprawdzony instalator korekty `apply_owner_fix.py` i `OWNER_FIX_METADATA.json`
są zachowane w repozytorium. Sprawdzają sumy starej i nowej wersji monitora,
wymagają HEALTHY przed podmianą i po uruchomieniu rzeczywistej usługi,
nie restartują KI i pozostawiają timer zatrzymany przy nieudanej kontroli.
Są przeznaczone do tej konkretnej aktualizacji, nie do nadpisywania późniejszych
wersji monitora.
