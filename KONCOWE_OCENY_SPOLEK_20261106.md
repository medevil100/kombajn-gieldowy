# Końcowe, niezależne oceny spółek — 6 listopada 2026

AI ocenia jedną spółkę w jednym żądaniu. Nie porównuje jej z innymi emitentami.
Zbiorcza jest wyłącznie wiadomość Telegram, wysyłana po cyklu co 15 minut,
jeżeli poprawne nowe oceny uzasadniają powiadomienie. Cel: trzy do sześciu
spółek, bez wymuszania minimum. Dopuszczalne są jedna, dwie albo cisza.

## Przebieg

1. Dotychczasowy skaner zapisuje wszystkie odczyty, kandydatów i potwierdzenia.
2. Lokalne sito wymaga poprawnej bazy, świeżego potwierdzenia i zgodnych wskazań.
   Niespójności, mieszane wskazania i dominujące ryzyko pozostają w KI bez
   płatnego wyszukiwania. Aktualne progi ruchu i pomiar aktywności pozostają.
3. Do sześciu nowych spółek na kwadrans przechodzi istniejącą ścieżkę Tavily
   i osobną analizę AI. Nie dodano dodatkowego wywołania modelu jako redaktora.
4. Końcowe AI opisuje ruch i technikę, aktywność oraz ryzyko: do sześciuset
   znaków na każdą oś, ponadto interpretacje wskaźników, cytaty źródłowe,
   hipotezy i braki. Rozstrzyga INFORM albo PANEL_ONLY z uzasadnieniem.
5. Publikacja wymaga prawidłowej odpowiedzi bez pominięć walidacji. Niepowodzenie
   jednej spółki nie blokuje poprawnych ocen innych. Pełne wyniki i surowa
   odpowiedź modelu pozostają w standardowych zapisach analizy.
6. Zestawienie czeka na zakończenie ocen, najwyżej dwanaście minut. Potem wybiera
   jedynie poprawne i nadal aktualne raporty. Pozostałe zadania nie uruchamiają
   nowych zapytań po zamknięciu zestawienia. Przed Telegramem ponownie kontroluje
   aktualność wszystkich zawartych spółek; nieaktualne zestawienie jest wstrzymane.

## Pełny materiał bez wielokrotnego płacenia za te same świece

W pakiecie pojedynczej spółki są wszystkie dostępne wskaźniki, detekcja, lokalna
ocena, aktywność, bid/ask wraz z ograniczeniami, techniczne SL/TP, zdarzenia
z zamkniętych świec i scenariusz bazowy, alternatywa oraz zanegowanie.

Dodatkowo odczytywane są wyłącznie zapisane dane tego emitenta: podsumowanie
historii dziennej z dostępnych 52 tygodni, fundamenty Alpha Vantage, gdy są
dostępne, i opisowe wyniki własnych sygnałów po 1/2/3/5 sesjach. Widoczne są
daty, zakres, liczby prób i braki. Nakładające się próby nie dowodzą skuteczności.
Nie pobieramy dodatkowych danych finansowych na potrzeby selekcji.

Surowe świece, źródła, pozostałe spółki i historia nadal są w KI. Do promptu
nie duplikujemy setek tych samych świec: wysyłamy wyliczone podsumowania oraz
zweryfikowane źródła. Brak danych finansowych nie jest traktowany jako dobra
kondycja. Brak potwierdzonej świeżości Yahoo bid/ask sam nie odrzuca ruchu.

## Wiadomości i historia

Nowy tryb wyłącza osobne automatyczne alerty wstępne i indywidualne raporty
ruchu na Telegramie. Wstępne obserwacje zostają w panelu. Ustawione przez
użytkownika alerty portfela i dotychczasowe raporty dzienne działają osobno.

Jedna spółka w jednym kierunku jest oceniana automatycznie najwyżej raz na
sesję. Zapis deduplikacji przetrwa restart, zmianę świecy i korektę bazy. W tej
wersji późniejszy ruch tej samej spółki w tym samym kierunku aktualizuje panel,
ale nie uruchamia kolejnej płatnej oceny ani kolejnego powiadomienia tego dnia.
Stany FAILED, REVIEW_REQUIRED i niepewne doręczenia nie są automatycznie ponawiane.

W Automacie dodano sekcję „Końcowe oceny spółek”: rozwijane raporty pojedynczych
emitentów, szczegóły poziomów, zdarzeń i wszystkich wskaźników oraz powody
odfiltrowania materiału. Układ pionowy z rozwijaniem nadaje się do telefonu
i tabletu. Testy interfejsu nie zastępują obserwacji w przeglądarce urządzenia.

## Wdrożenie

Nowa preferencja: final_company_review_enabled. Instalator aktywuje tylko tę
preferencję; zachowuje ustawienia pozostałych przełączników, portfela i progów.
Dodawane są dwie małe tabele historii zestawień i deduplikacji. Produkcyjna baza
nie jest wymieniana. Tworzona jest kopia kodu i poprzedniej wartości preferencji.
Przy błędzie startu instalator przywraca kod i poprzednią wartość preferencji.

Na lokalnym KI tryb można włączyć w pasku bocznym i zapisać ustawienia.
Po jego wyłączeniu wraca dotychczasowa ścieżka indywidualnych powiadomień.
Nie wykonano prawdziwych testów AI/Tavily ani testowej wiadomości Telegram.
