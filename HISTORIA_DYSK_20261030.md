# KI 2 — rozmiar historii, 30.10.2026

Projekt: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`; VPS: `/home/ubuntu/ki2`.
Dotyczy wyłącznie KI 2. Tavli i Alchemik pozostają poza zakresem.

## Diagnoza VPS (odczyty użytkownika)

- 38 GB dysk, 74% zajęte, około 11 GB wolne; baza 6,1 GB.
- `observations`: 4949,3 MB. Ostatnie 1000 wpisów: średnio 58,6 KB.
- Przykładowa `chart_history`: 55,4 KB, `carried_price_candles`: 5,9 KB.
- Codzienna kopia 30.10 zakończona poprawnie o 03:31:02 UTC; KI wznowione.
- Pozostałość nieudanej kopii 1,7 GB i baza sprzed wdrożenia około 4,5 GB.
- Dotychczas kod wyliczał datę retencji, ale nie usuwał starych obserwacji.

## Zmiana aplikacji

`observation_storage.py` kompresuje bezstratnie duże listy `chart_history`
i `carried_price_candles` w nowo zapisywanych obserwacjach. Zapis zawiera wersję,
rozmiar oryginalny i SHA-256. Odczyt odtwarza wszystkie świece i wartości.
Nie skraca historii do liczby świec wymaganej dla SL/TP. Reszta pól JSON,
w tym cena, czas, wskaźniki i matryca, pozostaje dostępna przez SQL json_extract.

`KI.load_payload` stanowi wspólny odczyt zapisów; zwykłe i stare JSON działają
bez migracji. Uszkodzona kompresja powoduje błąd, nie zastępcze dane.
Wykresy, SL/TP, wsparcie/opór, portfel i kontekst AI otrzymują pełną historię.
Nie zmieniono progów, promptu, liczby płatnych wywołań ani Telegrama.

Po zakończeniu cyklu stosowana jest istniejąca konfiguracja
`observation_retention_days` (domyślnie 90 dni): maksymalnie 1000 starych
obserwacji na partię. Ostatnie dwa odczyty każdego tickera/interwału pozostają,
nawet jeśli są starsze. Nie zmienia to zapisanych zdarzeń, analiz, rezerwacji
Research, wiadomości ani historii alertów. Gdy brak zaległości, kontrola raz
na dobę. Dla zaległości kolejna partia najwcześniej za 15 minut.
Nowy indeks daty wspiera retencję. Zwolnione strony SQLite są ponownie używane.

## Sprzątanie bez przerwy skanera

`cleanup_storage_20261030.py` domyślnie tylko pokazuje plan. `--apply` sprawdza
quick_check i obecność obserwacji w obu kopiach:

- `ki2-20261029T033003871502Z.sqlite3`
- `ki2-20261030T033003932846Z.sqlite3`

Dopiero po poprawnej kontroli usuwa dokładnie:

- `backups/ki2-20261028T210011227927Z.partial`
- `backups/ki2-20261028T210011227927Z.partial-journal`
- `backup-before-a792e31-20261029T120310Z/KI.matrix.sqlite3`

Nie usuwa rekursywnie katalogów ani przez glob. Inne pliki i kopie kodu zostają.
Przy działającym zadaniu backupu odmawia wykonania. Niezgodna lub brakująca
zachowywana kopia blokuje usuwanie. Po rotacji nazw kopii skrypt może odmówić
wykonania: nie należy obchodzić tego zabezpieczenia.

## Oddzielne zmniejszenie istniejącej bazy

Nowy zapis nie zmniejsza starych wpisów samoczynnie.
`compact_observations.py` domyślnie tylko czyta. `--apply` przeznaczono dla Linux,
po zatrzymaniu KI. Pobiera blokadę skanera i wymaga wolnego miejsca na dwa
rozmiary źródła plus 1 GiB. Cel musi być NOWYM plikiem.

Najpierw SQLite backup tworzy osobny plik z uwzględnieniem WAL. Następnie
kompresowane są tylko payloady obserwacji, partiami po 100, z weryfikacją pełnej
zgodności każdego odtworzonego odczytu. Nie usuwa żadnych obserwacji.
VACUUM dotyczy wyłącznie nowego pliku. Narzędzie sprawdza liczbę obserwacji,
quick_check, foreign_key_check i obustronne EXCEPT wszystkich pozostałych tabel.
Postęp wypisywany co 1000 rekordów; może to potrwać kilka minut.
Nie podmienia produkcyjnej bazy i nie usuwa oryginału.

Przed taką operacją należy wyłączyć timer backupu, zaczekać na koniec aktywnej
kopii, zatrzymać KI, a przy wyjściu zawsze wznowić wcześniej działające usługi
i timer. Nie uruchamiać ręcznej kopii równocześnie. Po weryfikacji cel można
podmienić podczas postoju, zachowując oryginał wraz z ewentualnymi WAL/SHM.
Wdrożyć najpierw czytnik zgodny z kompresją. Samo cofnięcie starego KI.py po
zapisie skompresowanych obserwacji nie wystarcza: starszy kod nie odczyta
nowego formatu. Cofnięcie wymaga odtworzenia dużych pól do zwykłych list
lub spójnego zestawu kodu i bazy. Nie przywracać starej bazy po nowych
wywołaniach płatnych usług bez zachowania rezerwacji i potwierdzeń wysyłki.

## Potwierdzony wynik wdrożenia na VPS

Użytkownik wykonał pakiet i przekazał wyniki 30.10.2026:

- 16 testów nowej warstwy storage na Linux/Python 3.14: OK.
- Sprzątanie po kontroli obu pozostawionych kopii odzyskało 6,12 GiB;
  zajętość spadła z 74% do 57% (17 GB wolnego).
- Nowy kod został wdrożony z kontrolą SHA-256 pakietu i oczekiwanej wersji KI.
  Log potwierdził gotowość panelu i skanera 20:01:51 UTC.
- Kompakcja objęła 71 386 obserwacji: źródło 6 541 127 680 bajtów,
  wynik 2 729 988 096 bajtów (2,54 GiB; około 58% mniej).
- Narzędzie zakończyło kontrole i produkcyjna baza została podmieniona.
- Oryginał pozostał w
  `/home/ubuntu/ki2/backup-db-storage-20261030T201503937265Z/KI.matrix.sqlite3`.
  Nie usuwać go przed kontrolą kolejnej automatycznej kopii i widoków.
- Po podmianie: `ki2` active, `ki2-backup.timer` active, health panelu `ok`.
  Dysk: 64% zajęte, 14 GB wolnego. Zachowany oryginał nadal zajmuje miejsce;
  zmniejszenie bazy nie oznacza jeszcze usunięcia jej starej kopii.

Świeżość heartbeatów po ostatnim restarcie i fizyczne wyświetlanie wykresów
oraz poziomów na tablecie nie zostały jeszcze potwierdzone w przesłanym wyniku.
Automatyczna nocna kopia nowej, skompresowanej bazy będzie dopiero kolejnym
sprawdzeniem operacyjnym; wcześniejsze poprawne kopie pochodzą sprzed zmiany.

## Sprawdzenia

Testy offline używają tymczasowych SQLite, pełnych historii oraz Streamlit
AppTest: zgodność po kompresji, brak zmiany źródła, wykonalność poziomów,
odczyt portfela bez API i bez zapisu, obsługa uszkodzeń, retencja i rollback
transakcji, kopia w osobnym pliku, przerwanie kompakcji, ścisły zakres
sprzątania i odmowa usunięcia przy błędnej kopii. Pełne wyniki w logach
artefaktów `ki2-storage-20261030`. Nie wykonano płatnych testów ani wysyłek.

Lokalnie: 409 testów plikowych, 24 panelu, 5 uruchamiania — OK. Wewnętrzny
self-test również zakończony kodem 0; po nim doszły dwa dodatkowe testy,
które przeszły w kompletnym zestawie 409. Zapis wdrożenia jest dołączony
do zmian kodu; identyfikator commita i stan publikacji należy sprawdzać w Git.

Rozmiar tabel events/research/analysis również trzeba nadal obserwować;
ta zmiana nie ustanawia automatycznej retencji tych zapisów.
