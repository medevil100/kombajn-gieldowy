# KI 2 — spójny pakiet i decyzja przed AI

Projekt: C:\Users\szela\OneDrive\Desktop\KI\2 KI; plik KI.py. Reguły wspólne dla wszystkich automatycznych zdarzeń CONFIRMED_OPPORTUNITY, obu silników AI i wszystkich tickerów. Nie zmieniono Alchemik-prace ani ręcznych narzędzi analizy.

## Pakiet

Jedna tożsamość emitenta i interwał, jeden odczyt, baza i kierunek ruchu, dane ceny/wolumenu/wskaźników, poprzedni porównywalny odczyt, jawne czasy i ograniczenia bid/ask, lokalne zgodności i sprzeczności, lokalna ocena ryzyka oraz konkretne pytania. Przyjęte źródła pozostają oddzielone, ze wspólną granicą czasu zdarzenia.

Kontrola blokuje niespójność identyfikacji, rankingu, granicy czasu źródeł, przyszłą bazę/świecę/publikację oraz nieporównywalny poprzedni odczyt. Porównanie rozróżnia rewizję tej samej świecy i wcześniejszą świecę. Później pobrane oferty nie są historycznymi ofertami z chwili odczytu świecy. Czas pobrania nie potwierdza czasu aktualizacji notowania.

## Decyzja przed płatnym wywołaniem

automatic_ai_preflight działa w rzeczywistym workerze po przygotowaniu kontekstu i przed analyze_event/OpenAI/DeepSeek. Wymaga dostatecznych danych technicznych i aktywności oraz pytania wynikającego ze sprzecznych wskazań, zmiany znaku histogramu między odczytami lub przyjętych źródeł emitenta. Sam pomiar wzrostu/spadku i braków jest podsumowaniem lokalnym, nie zadaniem dla AI.

Brak lub błędne bid/ask pozostaje jawnym ograniczeniem. Jeżeli istnieje wartościowy materiał techniczny/źródłowy, AI może interpretować ruch w zakresie wykluczającym ocenę wykonalności transakcji. Poprawne, lecz niedatowane lub niepotwierdzone oferty także nie dają podstaw do oceny aktualnej płynności. Błędne oferty nie są przepisywane do pakietu jako poprawne ceny.

Odmowa wywołania: FILTERED, zapis lokalnej decyzji, danych porównawczych i powodów, provider.not_called=true; bez wiadomości ANALYSIS. Poprzedni podgląd/oczekująca wiadomość tego zdarzenia zostaje zablokowana. Nie usuwa się audytu ani doręczeń. Panel wyraźnie pokazuje ocenę lokalną bez wywołania AI. Bramka nie ponawia zadań historycznych.

Pakiet dla AI ma krótszą instrukcję, usunięte pola operacyjne, brak zduplikowanego rankingu/snapshotu i pełnych historii. Zostają dane potrzebne do konkretnego pytania i walidacji. Dotychczasowe kontrole po odpowiedzi i przed wysyłką pozostają aktywne.

## Weryfikacja i ograniczenia

7 nowych testów bez usług sieciowych: zgodny prosty ruch z ofertami i bez nich, wartościowa sprzeczność bez ofert, błędna tożsamość/czas/źródło, jawna relacja czasów, rzeczywisty worker bez kluczy API zapisujący wynik lokalny, kompaktowy pakiet bez mutacji oraz blokada starego podglądu.

305 testów plikowych i 329 self-testów — OK. Panel: 24/24 OK. Regresję etapu diagnostycznego zmieniono z AI_REQUEST na AI_PREFLIGHT, ponieważ uszkodzony JSON kontekstu jest wykrywany przed żądaniem do dostawcy.

Replay 30 zapisanych zdarzeń bez API: 2 odrzucone przed AI. Łączny rozmiar tekstu messages przed/po: 461789 / 367328 znaków (około 20% mniej). Jest to pomiar znaków, nie rozliczenie tokenów ani gwarancja kosztów. Replay bez rekonstrukcji poprzednich obserwacji; produkcyjny worker dodatkowo ładuje poprzedni porównywalny odczyt.

Kopia wcześniejszego kodu, wynik replay i stan wdrożenia: backup_20261027_ai_preflight. Nie wykonywano płatnych testów ani testowych wiadomości Telegram. Ta bramka oszczędza wywołanie AI; Search Tavily na etapie budowania kontekstu może już być wykonany. Wdrożenie nie potwierdza jeszcze jakości następnej naturalnej odpowiedzi modelu.
