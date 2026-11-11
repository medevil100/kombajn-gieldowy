# Wczesny sygnał KI 2 — 6 listopada 2026

KI służy do informacji o ruchu. Decyzja i kontrola aktualnych ofert pozostają w XTB.

## Nowy etap

Pierwszy zaakceptowany odczyt przekraczający zapisany próg ceny, zawierający nową
aktywność wolumenu, może wysłać krótki komunikat „WSTĘPNY WZROST/SPADEK”.
Nie uruchamia AI, Tavily ani osobnego pobierania ofert. Potwierdzenie nadal wymaga
trzech odczytów; powiadomienie potwierdzonego ruchu korzysta z dotychczasowej ścieżki.
Przy bezpośredniej zmianie kierunku potwierdzenia są liczone od nowa.

Wstępny alert jest zapisywany najwyżej raz na spółkę, kierunek i sesję. Klucz
deduplikacji przetrwa restart, nową świecę i korektę ceny bazowej. Włączenie usług
lub wdrożenie nie odtwarza wcześniejszych kandydatów. Obowiązują istniejące
przełączniki skanera/pipeline i Telegrama oraz aktualna lista obserwowanych spółek.

Przed wysłaniem ponownie sprawdzane są: otwarta sesja, świeżość odczytu, poprawna
baza i cena, najnowszy stan oraz kierunek ruchu. Alert, który zdążył się potwierdzić,
zmienił kierunek lub wygasł, jest odfiltrowany. Niepewne doręczenie po przerwaniu
procesu nie jest automatycznie ponawiane.

## Bid/ask i poziomy

Niezweryfikowany spread Yahoo jest informacją pomocniczą, bez samodzielnego
podnoszenia oceny ryzyka sygnału. Nadal widoczne są same oferty, ich niespójność
i brak czasu aktualizacji. Rzeczywiste cofnięcie ceny nadal może podnosić ryzyko.

Nowe SL/TP i relacja potencjału do ryzyka są poziomami technicznymi od odczytanej
ceny: spread nie przesuwa wejścia ani nie odbiera podstaw do poziomów. Ocena
realizacji, prowizje i poślizg nie są w nich potwierdzone. Brak wymaganych świec,
ATR, wsparcia lub oporów nadal oznacza brak podstaw do wyliczenia.
Zapisanych dawniej raportów i planów nie przeliczamy wstecz.

## Granice

Nie zmieniono częstotliwości skanowania ani istniejącego progu ceny. Wstępny alert
przy obecnym cyklu może dotrzeć około dwóch odczytów wcześniej niż potwierdzenie,
lecz nie gwarantuje notowania w czasie rzeczywistym. Yahoo może być opóźnione.
Wstępny sygnał może zostać zanegowany; nie jest poleceniem transakcji.

## Weryfikacja

Testy używają tymczasowych baz SQLite i atrap transportu. Sprawdzają nową ścieżkę
w rzeczywistym cyklu skanera, doręczenie niezależne od analizy, deduplikację,
zmianę kierunku, wygasanie oraz brak wpływu ofert na techniczne SL/TP.
Nie wykonywano płatnych testów ani prawdziwych wiadomości Telegram.

Paczka VPS zmienia wyłącznie wskazane pliki kodu, testy i ten opis. Instalator
sprawdza wersję i sumy, koordynuje się z nadzorem i backupem, zapisuje kopię kodu,
restartuje usługę i weryfikuje panel oraz świeży heartbeat skanera. Przy błędzie
przywraca poprzedni kod. Nie zastępuje produkcyjnej bazy ani ustawień.
