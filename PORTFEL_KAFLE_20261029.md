# Mój portfel — mniejsze kafle na telefon i tablet

Widok główny pokazuje do 10 kompaktowych kafli. Na telefonie jedna kolumna, na szerszym ekranie automatyczna siatka. Kafle zawierają ticker, ostatnią cenę, zmianę od otwarcia świecy 1h, czas odczytu, świeżość ceny oraz ręczne SL/TP ze statusami Ustawiony/Wyzwolony/Nie ustawiono. SL czerwony, TP zielony; brakujący odczyt nie usuwa zapisanych progów.

Ryzyko, powody, braki, OHLC, wolumen i spread są rozwijane. Dane ryzyka są wyraźnie określone jako zapis ostatniej analizy, z czasem jej snapshotu, jeżeli jest dostępny. Widok nie udaje potwierdzonej świeżości bid/ask.

Ręczne progi nie są wyliczeniami technicznymi, zleceniami giełdowymi ani gwarancją realizacji. Nie dodano nowych progów ani nie podmieniono użytkownikowi SL/TP. Zachowano dodawanie/usuwanie pozycji, limit 10 spółek, zapis progów, kierunek pozycji, historię wyzwolenia i dotychczasową obsługę alertów. Edycja i zarządzanie są w opisanych rozwijanych sekcjach; szczegółowe tabele nadal są dostępne.

Odczyt widoku nie pobiera danych, nie wywołuje AI/Tavily/Telegrama i nie zmienia bazy. Skorygowano mylący dawny opis „bez Telegrama”: podgląd nie wysyła, lecz ustawione alerty portfela nadal mogą być obsługiwane przez skaner.

Pliki: KI.py, portfolio_view.py, test_portfolio_cards_20261029.py. W KI.py zmieniły się wyłącznie render_portfolio i lista modułów testowych w main; funkcje skanera i alertów pozostają identyczne.

Weryfikacja lokalna: 390 testów plikowych OK; pełny --self-test kod 0 (ostatni zestaw 233 testy OK); 24 testy panelu OK. Sześć nowych testów obejmuje odczyt/odświeżenie bez zapisu i dostawców, zapis progów z zachowaniem historii alertów, dodawanie/usuwanie, widoczność ręcznych poziomów i czasu, braki oraz escapowanie tekstu. Zestawy częściowo się pokrywają.

Wygląd na fizycznych urządzeniach Android i test nowej wersji na Linux/Python 3.14 wymagają potwierdzenia po przesłaniu kandydata. Lokalna przeglądarka narzędzia nie jest dostępna do oględzin z powodu wcześniejszej odmowy uprawnień. Push nie wdraża zmian na VPS.

## Uzupełnienie — moje progi oraz poziomy z analizy

Kafel ma dwie odrębne sekcje. „Moje progi alertów” zawierają wyłącznie ręczne SL/TP ze statusami. „Poziomy z analizy KI” pokazują lokalne wsparcie, opór, SL, TP1 i TP2 z tego samego kalkulatora co automat i Śledzenie. Podstawą jest ostatni zapisany snapshot i kierunek zmiany od bazy matrycy, nie zmiana 1h ani ręczny próg. Wyliczone wartości nie są kopiowane do konfiguracji portfela ani do zleceń.

Analiza pokazuje osobny czas i etykietę aktualności. Przy niepotwierdzonej bazie, spadku lub braku ATR/historii SL/TP są nieustalone; dostępne poziomy wsparcia/oporu mogą pozostać widoczne. Przy kompletnym planie LONG widoczna jest relacja zysku do ryzyka TP1. Odtworzenie z dawnych danych jest jawnie historyczne. Brak nowych zapytań dostawców i dodatkowych tokenów.

Trzy dodatkowe regresje sprawdzają rozdzielenie wartości ręcznych i wyliczonych, historyczne/niepełne dane oraz zgodność kalkulatora z zachowaniem konfiguracji i całej bazy bez zapisów.

Weryfikacja uzupełnienia: 393 testy plikowe OK, 24 testy panelu OK. Testów fizycznego wyglądu Androida nie zastępują testy renderowania; aktualizacja VPS jest oddzielnym krokiem.
