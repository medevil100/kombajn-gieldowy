# Śledzenie spółek — poziomy i widok mobilny

Zmiana dotyczy wyłącznie prezentacji. W Śledzeniu potwierdzonych spółek karty pokazują ostatnią zapisaną cenę, wsparcie, opór, SL, TP1, TP2, przestrzeń do wsparcia/oporu i czas danych. Wsparcie jest niebieskie, opór fioletowy, SL czerwony, TP zielone. Układ kart dopasowuje się do szerokości; poziomy wewnątrz karty są w dwóch kolumnach. Filtr spółki i strony po 10 wpisów ograniczają długość widoku na telefonie/tablecie. Pełna tabela pozostaje w rozwijanej sekcji.

Poziomy wylicza istniejący sl_tp.build_plan z najnowszego zapisanego snapshotu, bez dodatkowego pobierania lub AI. Stara lub zamknięta świeca jest oznaczana jako historyczna; poziomy odtwarza się na czas danego odczytu i nie prezentuje jako obecnie aktualnego planu. Czas ceny i danych poziomów jest widoczny ze strefą CET/CEST. Gdy brak obserwacji, używa się zapisanego historycznego snapshotu spółki i jego prawdziwego czasu.

SL/TP są pokazywane wyłącznie dla kompletnego orientacyjnego planu LONG. Przy spadku, brakującym ATR, niepotwierdzonej bazie lub niepełnej historii nie są wymyślane poziomy. Dostępne wsparcie/opór mogą pozostać widoczne przy braku planu; powód jest jawny. Nie dodano zleceń, nowych powiadomień ani zmian w skanerze, kolejce, kwalifikacji lub historii.

Pliki: KI.py, tracking_view.py, test_tracking_levels_20261029.py.

Weryfikacja: 384 testy plikowe OK, pełny self-test kod 0 (ostatni zestaw 227 testów OK), 24 testy panelu OK. Osiem nowych testów sprawdza poziomy, dane historyczne, spadek, braki, przyszły czas, odczyt bez zapisu i API, escapowanie HTML oraz renderowanie i filtr panelu Streamlit. Zestawy częściowo się pokrywają.

Nie wykonano oględzin w przeglądarce: dostęp narzędzia do lokalnego podglądu został odrzucony przez mechanizm uprawnień. Fizyczny wygląd telefonu i tabletu wymaga potwierdzenia użytkownika po wdrożeniu. Testy nie wykonują płatnych zapytań. VPS jest aktualizowany osobno od push.
