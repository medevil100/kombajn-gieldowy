# Ciągła selekcja i nowe oceny w trakcie sesji — 9 listopada 2026

Status: wdrożono na VPS 9 listopada 2026 o 17:24 UTC (18:24 CET).
Instalator zakończył się kodem 0; panel i trzy heartbeaty potwierdzone.
Wszystkie pięć etapów regresji VPS zakończono wynikiem 0, PASS; graf analizy
pogłębionej skompilowano bez modeli i narzędzi. Kopia kodu:
`/home/ubuntu/ki2/backup-intraday-20261109T172447003935Z`.
Raport testów: `/home/ubuntu/ki2-oceny-ciagle-vps-20261109/tests-20261109T172259383566Z`.
Pozostaje potwierdzenie naturalnego nowego zadania, poprawnej odpowiedzi AI
i rzeczywistego doręczenia końcowego zestawienia. Instalacja tego nie dowodzi.

## Powód zmiany i dowody

Audyt użytkownika z 16:39 UTC: skaner RUNNING, oba workery READY, analiza,
Telegram i końcowe oceny włączone. 28 końcowych zadań: 25 REVIEW_REQUIRED,
3 FAILED, zero DONE; wszystkie miały COMPLETE_TO_ASOF. Żadne nie używało
kontraktu KI-PROMPT-20261109-v2. Nie powstało końcowe zestawienie do wysłania.
Jeden alert PORTFOLIO_ALERT miał potwierdzenie DELIVERED; to osobny rodzaj alertu.
Zapisano użycie 428 298 tokenów w 25 odpowiedziach, nie jest to rozliczenie faktury.

Kod blokował dalszą pracę na dwóch poziomach:
- company_review_seen rezerwowało spółkę, sesję i kierunek na cały dzień,
  niezależnie od powodzenia jej oceny;
- SELECTED zatrzymywało opportunity przed kolejną kwalifikacją. Dla
  REVIEW_REQUIRED nie było stałej daty ukończenia w job_ts, a updated_at
  odnawiało się co cykl; czterogodzinne wygasanie mogło nigdy nie nastąpić.

Liczniki odrzuceń puli są liczbą przypadków w cyklach, nie unikalnych spółek.
Nie dowodzą, że po naprawie powinno wystąpić minimum trzech wyników.

## Bieżąca ocena zamiast blokady dziennej

W trybie końcowych ocen nowy, potwierdzony odczyt może wrócić z SELECTED do
kwalifikacji po zakończeniu poprzedniego zadania. Musi mieć późniejszy czas
pozyskania i nowy wolumen transakcji, a od danych poprzedniej oceny musi minąć
co najmniej 15 minut. Cytowany punkt odniesienia pochodzi z niezmiennego
snapshotu poprzedniego zdarzenia, nie z aktualizowanego co cykl opportunity.

Ponadto musi zajść co najmniej jeden warunek:
- zmiana ceny o co najmniej 1% względem ceny ostatniej ocenianej migawki;
- nowa pełna, zamknięta świeca 1h z obrotem, zamknięta po tamtej migawce;
- zmiana znaku relacji ceny do SMA, histogramu MACD, układu DI lub RSI do
  neutralnego poziomu, albo przejście RSI między stanami neutralnym/skrajnymi;
- narastający RVOL tej samej świecy osiągnął średnią pełnej godziny od dołu.

Samo odświeżenie czasu lub wzrost wolumenu bez istotnej zmiany nie uruchamia
nowej oceny. Trwające PENDING/BUSY nie są dublowane. Późniejszy odczyt musi
nadal przejść dotychczasowe bramki: sesja, poprawna stała baza, nowa aktywność,
potwierdzenie ruchu, komplet materiału/sesji, lokalna zgodność, preflight i walidacja.

Poprawiono także cycle_id po zwolnieniu SELECTED, aby nowy odczyt mógł zostać
zakwalifikowany w bieżącym cyklu. company_review_seen przechowuje ostatni
wskaźnik deduplikacji; wcześniejsze events, batches, analysis_jobs, research,
outbox oraz potwierdzenia doręczeń pozostają zachowane. Bez migracji schematu.

Każda dopuszczona aktualizacja tworzy nowe zdarzenie z nową migawką i własnym
identyfikatorem partii. Nie resetuje historycznego FAILED/REVIEW_REQUIRED/
UNCERTAIN i nie ponawia zapisanych żądań. Wcześniejsze raporty i ich błędy
pozostają zapisami własnych chwil. Bez wymuszenia nowych płatnych przebiegów w instalatorze.

## Koszty, selekcja i zakres oceny

Limit pozostaje do sześciu nowych ocen na przedział 15 minut i jedno zbiorcze
powiadomienie po cyklu. Nowa istotna sytuacja tej samej spółki może oznaczać
kolejne płatne Research/AI w ciągu dnia. Usunięcie limitu dziennego nie oznacza
zwiększenia limitu cyklu ani uruchamiania AI dla każdego odczytu.

Nie ma wymuszonego minimum trzech spółek. Wszystkie dane pozostają w KI.
Oceny są niezależne dla spółek; nie dodano porównawczego promptu między emitentami,
zmiany modelu, zleceń ani wyliczonego prawdopodobieństwa zysku.
Ocena opisuje stan do chwili danych i warunki techniczne. Cena następnego
otwarcia pozostaje nieznana; kolejna sesja wymaga nowych danych i potwierdzeń.

Panel pokazuje przyczyny braku aktualizacji, zamiast nowego komunikatu
„ten kierunek oceniono już w tej sesji”. Historyczny kod ALREADY_REVIEWED
pozostaje czytelny dla starych partii.

## Testy i wdrożenie

Dziewięć nowych testów przechodzi przez rzeczywiste detekcję, zapis obserwacji,
record_opportunity, rezerwację, kolejkę, finalizację i potwierdzenie doręczenia.
HTTP OpenAI i Telegram jest atrapą: zero rzeczywistych wywołań i wiadomości.
Potwierdzono nową ocenę po błędzie na nowym materiale, brak zmian starych zadań,
brak duplikacji trwającego zadania i niezmienionych danych, minimum czasu,
nową pełną godzinę, technikę i próg aktywności. Dotychczasowe testy limitu
sześciu i jednej wiadomości pozostają wymagane.

Pełne wyniki: ki2-oceny-ciagle-20261109 w katalogu artefaktów Codex poza projektem.
667 testów modułów Windows OK (dwa pominięcia POSIX), 667 testów Ubuntu WSL2 OK
(dwa pominięcia migracji Windows); testy wbudowane, panel 25 i uruchamianie 5 OK.
JavaScript OK na Windows; graf TradingAgents READY_OFFLINE. Osiem testów
instalatora na obu systemach OK, w tym rzeczywista podmiana i powrót plików
w katalogu tymczasowym, bez zarządzania prawdziwą usługą.
Instalacja wymaga testów na Pythonie VPS i kontrolowanej podmiany tylko KI.py
i final_company_review.py, z kopią kodu i powrotem po błędzie. Nie zmienia bazy,
kluczy ani ustawień i nie zwalnia starych zadań podczas instalacji.

Paczka ki2-oceny-ciagle-vps-20261109.tar.gz ma SHA-256
30d17aa02a281450ef72840dc36963e340f1078628f5b730ded1ee69d403f9f0.
Po wdrożeniu trzeba potwierdzić naturalny przepływ: nowa istotna migawka → nowe
zadanie z v2 → poprawna ocena → kwalifikujące się zestawienie → receipt doręczenia.
Samo active usług i testy na atrapach nie zamykają tego sprawdzenia.
