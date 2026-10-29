# KI 2 — dane dzienne i stan wdrożenia, 29.10.2026

## Problem i wynik diagnozy

Na VPS 236 dzisiejszych matryc GPW korzystało z zamknięcia 27.10, a 86 z 28.10. Wszystkie 236 zapisanych diagnostyk wskazywały odrzucenie niepełnego dziennego OHLCV za 28.10. Późniejsze próbki STX.WA i 06N.WA zwracały poprawne dane zarówno z surowej odpowiedzi Yahoo, jak i przez yfinance; parser KI przyjmował obie świece. Nie potwierdzono przyczyny porannych pustych danych po stronie dostawcy lub biblioteki.

Poprzednio częściowo poprawny pakiet historii był traktowany jako ukończone odświeżenie całego dnia. Starsze zamknięcie mogło zostać użyte jako baza, a matryca nie przyjmowała nowszej bazy po rozpoczęciu sesji. Przypadek odtworzono bez sieci na sztucznych danych: zmiana 3% od starszej bazy wobec 0,98% od nowszej.

## Zmiana

- Jeśli brakuje wymaganej świecy poprzedniego dnia roboczego, częściowe udane pobranie jest ponawiane podczas regularnej sesji najwyżej raz na 15 minut. Dotychczasowe ograniczenia błędów, HTTP 429 i liczby aktywnych pobrań pozostają w mocy.
- Starsza baza pozostaje jawnie zapisana, ale matryca ma MISSING_DAILY_REFERENCE, reference_status=MISSING_PREVIOUS_SESSION i expected_reference_session. Zmiana procentowa jest nieustalona, potwierdzenia wyzerowane; nie ma awansu do rankingu i alertu.
- Nowsza lub skorygowana baza jest przyjmowana także w tej samej sesji. Potrzebne są trzy nowe dowody aktywności; nie przepisuje się historii obserwacji, zdarzeń, analiz ani doręczeń.
- Worker sprawdza bazę również przed rozpoczęciem researchu i AI. Zadanie ze zmienioną lub niepotwierdzoną bazą jest filtrowane bez nowego wywołania.
- Korekta bazy nie tworzy drugiej płatnej tożsamości spółki tego samego dnia, jeśli inne zdarzenie ma już rezerwację researchu. Istniejąca rezerwacja tego samego zdarzenia nie jest powielana. FAILED i REVIEW_REQUIRED nie są automatycznie ponawiane.
- Bez nowych kalendarzy giełdowych. Wymagana data wynika z dni poniedziałek–piątek w strefie giełdy. Po święcie bez świecy za poprzedni dzień roboczy kwalifikacja pozostanie wstrzymana; starsze zamknięcie nie jest automatycznie uznawane za potwierdzone.

## Testy

Regresje w test_daily_readiness_20261029.py obejmują ograniczenie ponowień, pełny i częściowy pakiet, restart, późne uzupełnienie, korektę istniejącej bazy, trzy nowe aktywności, brak płatnych wywołań ze złej bazy, ochronę rezerwacji, weekendy/strefy czasowe oraz starą świecę godzinową. Testy korzystają z tymczasowych baz SQLite i sztucznych danych; nie wywołują dostawców.

Weryfikacja lokalna: 376 testów plikowych OK, pełne --self-test zakończone kodem 0 (ostatni zestaw 219 testów OK), 24 testy panelu OK. Zestawy częściowo się pokrywają.

## Stan VPS i Git

Projekt lokalny: C:\Users\szela\OneDrive\Desktop\KI\2 KI. VPS: /home/ubuntu/ki2, usługa ki2.service. Przed tą poprawką zgodność ośmiu plików PC/VPS potwierdzono SHA-256. Ta poprawka powstaje lokalnie; commit i push same nie zmieniają działającego VPS.

VPS pracuje na Ubuntu 26.04 z osobnym środowiskiem Python 3.14; lokalne testy na Pythonie 3.13. Docelowy test poprawki na Linux/Python 3.14 nadal wymagany przed przełączeniem. Zależności na VPS i lokalnie różnią się wersjami; requirements.txt nie stanowi ścisłej blokady środowiska.

KI i Tavli są osobnymi usługami, Tavli ma osobny Python 3.13. Dostęp do paneli przez prywatną sieć Tailscale. SSH kluczem, logowanie hasłem i roota wyłączone, UFW aktywne. Backup codziennie 03:30 UTC z krótkim zatrzymaniem/wznowieniem KI i kontrolą SQLite; dwie poprawne kopie na VPS, jedna pobrana na PC. Pełny test odtworzenia, automatyczne kopie poza VPS i alarmy dysku/backupów nadal pozostają do wykonania. Konfiguracje usług i klucze na serwerze nie są częścią tego commitu.

W repozytorium pozostają niezależne zmiany _ai_review.py i lokalne materiały Alchemika. Nie należą do tego zakresu. Do Git nie trafiają sekrety, bazy, logi ani backupy. Nie używać git add .
