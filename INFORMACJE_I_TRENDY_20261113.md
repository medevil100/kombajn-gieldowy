# KI — informacje emitenta, jednostka akcji i horyzonty trendu

Zmiana przygotowana 13 listopada 2026 r. Baza odniesienia kodu: commit
`3d589a5be075a76249c6755fb97aed7200394c75`.

## Kolejność i wspólny pakiet

Skaner dołącza `price_basis`, `corporate_actions`, `trend_context`, `news_watch`
i `official_notices` do zapisywanej migawki. Ten sam pakiet trafia do manifestu,
orkiestratora, katalogu dowodów AI, TOP 5, portfela i czytnika Asystenta/MCP.
Stare raporty pozostają zapisami historycznymi; wdrożenie ich nie przelicza
ani nie ponawia dawnych zadań dostawców.

## Operacje na akcjach

Yahoo history jest pobierane z `actions=True`, `auto_adjust=False`, `repair=False`.
Kolumna `Stock Splits` jest odczytywana z tego samego wyniku OHLC. Nie wykonujemy
osobnego zapytania o split dla każdego tickera. Nie stosujemy mnożnika splitu
ponownie do cen Yahoo, ponieważ historia OHLC może już uwzględniać tę operację.

Przy zgłoszonej operacji w ostatnich 10 dniach porównujemy zapisaną bazę dzienną
z zamkniętą świecą poprzedniej sesji zwróconą w nowym szeregu godzinowym.
Różne jednostki albo brak możliwości ich potwierdzenia blokują procentowy
sygnał, kwalifikację i nowy plan SL/TP. Skok ceny co najmniej 4× bez zgłoszonej
operacji oznacza niewyjaśnioną nieciągłość — sam skok nie potwierdza splitu.
W tym stanie można ponownie pobrać rzeczywistą historię dzienną, najwyżej raz
na 30 minut. Kontrola jest ponawiana przy kolejnym odczycie godzinowym.

Informacja o operacji może trafić do standardowej kolejki Telegram niezależnie
od TOP 5 i lokalnej oceny ruchu. Ma jednoznaczny identyfikator, źródło i datę.
Ręczne progi portfela nie są przeliczane. Alerty SL/TP są wstrzymane przy
niespójnej jednostce lub operacji nowszej niż świadome zapisanie zmienionych
progów. Po sprawdzeniu danych w XTB należy ustawić i zapisać właściwe SL/TP.

## Informacje przed kwalifikacją do AI

`issuer_watch_jobs` jest oddzielną kolejką. Powody uruchomienia:

- spółka w portfelu — odstęp co najmniej 6 godzin;
- punktacja `market_score` lub kierunkowa punktacja Automatu co najmniej 80/100 — odstęp co najmniej 6 godzin;
- ruch od bazy co najmniej równy ustawionemu progowi ceny — odstęp 1 godziny;
- operacja na akcjach lub podejrzenie różnej jednostki — odstęp 1 godziny.

Powód ma priorytet: operacja, portfel, wysoka punktacja, pozostały ruch.
Kolejka ma najwyżej 100 oczekujących pozycji. Zadanie oczekujące ponad 2 godziny
wygasa. Pracuje istniejący worker analizy z blokadą dostawców; skaner cen
nie czeka na Tavily. Obsługa tej kolejki jest sprawdzana co 30 sekund.

Limit wynosi **24 dodatkowe wywołania Search na dobę UTC**. To limit liczby
wywołań tej kolejki, a nie kredytów całego konta i nie wspólny limit wszystkich
funkcji KI. Brak klucza, limit, błąd i brak przyjętych źródeł mają różne stany.
Przerwane lub nieudane wywołanie nie jest automatycznie odtwarzane. Nowe,
późniejsze sprawdzenie podlega odstępowi i limitowi. Wyłączenie
`pipeline_enabled` albo ustawienie `issuer_watch_enabled=false` zatrzymuje
niezależne Search. Wyłączenie Telegrama zatrzymuje wysyłkę.

Wynik Search jest tropem informacyjnym. Nadal obowiązuje sprawdzenie emitenta,
domeny i daty. Nie oznacza on dowodu przyczyny zmiany ceny. Dotychczasowy etap
analizy może wykorzystać zapisane Search z ostatniej godziny, dostępne przed
granicą czasu analizy; pełna treść i cytaty przechodzą dotychczasową kontrolę.
Istotny tytuł o operacji kapitałowej może dostać osobne powiadomienie z linkiem,
bez zgadywania stosunku wymiany lub daty skuteczności na podstawie fragmentu.

## Oficjalny kanał Nasdaq

Jeden publiczny kanał Corporate Actions RSS jest sprawdzany najwyżej raz na
godzinę dla całej obserwowanej listy. Nie używa Tavily ani GPT. Wymaga dokładnego
tickera w nawiasach w tytule, daty publikacji i linku ECA na `nasdaqtrader.com`.
Ta domena została też dopisana do dozwolonych źródeł wyszukiwania USA.

Kanał RSS zawiera ostatnie komunikaty, **nie pełne archiwum**. Nie obejmuje
wszystkich giełd ani wszystkich rodzajów zdarzeń. Błąd źródła pozostaje błędem,
a brak dopasowania nie jest dowodem braku operacji. Stan znajduje się w
Monitorze Tavily + AI. Nie ma obietnicy wykrycia każdej informacji ani braku
opóźnień dostawców.

## Horyzonty

Wszystkie klasyfikacje korzystają wyłącznie z zamkniętych świec dostępnych
w chwili migawki. Nie korzystają z przyszłych notowań ani wypełniania luk.

| Horyzont | Dane i metoda | Minimum |
|---|---|---|
| Śródsesyjny | pełne 1h bieżącej sesji, SMA 2/3 i zmiana SMA 3 | 4 świece |
| Krótki, około 1–4 tygodni | dzienne SMA 5/20 i zmiana SMA 20 przez 5 sesji | 25 sesji |
| Średni, około 1–3 miesięcy | dzienne SMA 20/50 i zmiana SMA 50 przez 10 sesji | 60 sesji |
| Długi, około 3–12 miesięcy | dzienne SMA 50/200 i zmiana SMA 200 przez 10 sesji | 210 sesji |

Cena ponad szybką i wolną średnią, szybka ponad wolną i dodatnie nachylenie
wolnej średniej powyżej 0,1% oznaczają układ wzrostowy. Odwrotne relacje oraz
nachylenie poniżej −0,1% oznaczają spadkowy. Pozostałe układy są mieszane.
Za mało danych oznacza brak oceny. Otwarta lub skrócona końcowa świeca nie
jest pełną zamkniętą godziną. Na początku sesji brak tej klasyfikacji jest
oczekiwany; nie blokuje samodzielnie informacji o wczesnym ruchu.

Historia dzienna jest od razu pobierana dla roku. Po splitach używany jest
pełny szereg jednego nowego pobrania zamiast sklejenia starych i nowych jednostek.
Dane dzienne starsze niż 7 dni nie służą nowej klasyfikacji. Około 52 tygodni
nie wystarczy dla spółki notowanej krócej — nie dopisujemy nieistniejących sesji.

Krótki wzrost i długi spadek są opisane jako odbicie wewnątrz trendu spadkowego,
bez potwierdzenia odwrócenia. Klasyfikacja nie jest prognozą długości przyszłego
ruchu. Brak długiej historii pozostaje ograniczeniem, nie automatyczną odmową AI.

## Prezentacja i kontrola

Kolorowe kafle zawierają tekst kierunku oraz liczbę dostępnych/wymaganych świec.
Wskaźniki, TOP 5, końcowe oceny i portfel pokazują ten sam zapis. W Telegramie
dochodzi krótki opis trzech dziennych horyzontów. Pełne opisy i źródła zostają
w KI. Otwarcie widoku nie uruchamia nowych zapytań.

Testy działają na tymczasowych bazach i atrapach dostawców, m.in. przypadek
COSM 1:20, brak podwójnej korekty, limity, przerwanie, ponowne użycie Search,
źródło Nasdaq, look-ahead, trend mieszany i cały cykl skanera. Płatne testy
i testowe wiadomości nie są wykonywane. Instalacja jest kontrolowaną podmianą
kodu z kopią i wycofaniem przy braku panelu/heartbeatów. Nowe tabele są addytywne;
zawartość portfela, klucze i historyczne wyniki nie są zastępowane.


## Pełne opisy i historia — wdrożenia z 13 listopada

Trwałe scenariusze dużego potencjału są oceniane niezależnie od bieżącego
rankingu. Pełny opis AI wykorzystuje liczby i źródła z zamrożonego pakietu;
niepoprawne odwołania są oznaczane, bez płatnego ponawiania. Starsze opisy
pozostają historyczne. Model i dotychczasowe limity wywołań nie zostały zwiększone.

Trend i ocena dużego potencjału używają wspólnego wyboru historii dziennej.
Krótki cache nie przesłania dłuższej zgodnej historii SQLite. Sprawdzane są
OHLC, granica czasu, data pozyskania, zgodność jednostek po operacjach na akcjach
i cena odniesienia. Nie wykonuje się syntetycznego przeliczania cen.

Automatyczne uzupełnianie historii obejmuje wszystkie zapisane tickery:
`uzupelnij_52_tyg_20261113.py`, `ki2-history52.service` i timer. Jednostka systemd
odwzorowuje wdrożoną lokalizację paczki na VPS; samo pobranie repozytorium nie
instaluje jej. Limit: 3 tickery na uruchomienie, 48 prób na dobę UTC, odstęp
24 godzin dla tickera. Krótsza historia źródła nie jest oznaczana jako pełny rok.

Potwierdzona ostatnia podmiana VPS: 2026-11-13 21:16:35 UTC.
Kopia kodu: `/home/ubuntu/ki2/backup-history-series-20261113T211635754927Z`.
Przed zapisem Git 14 listopada: 148 testów Linux PASS (bez sieci i płatnych wywołań).
