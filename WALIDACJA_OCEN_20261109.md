# Końcowe oceny — błędy produkcyjne i poprawka 9 listopada 2026

Stan: wdrożona na VPS 9 listopada 2026 około 16:26 UTC (17:26 CET),
potwierdzona kompletnym wynikiem instalatora przekazanym przez użytkownika.
Nie ponawiano historycznych zadań.

## Dowody z produkcji

Partia z 9 listopada, 15:24 UTC, zawierała sześć spółek. Wszystkie używały
KI-PROMPT-20261108-v1. Pięć zadań miało REVIEW_REQUIRED, IMMP — FAILED.
Nie był to wyłącznie historyczny widok ani brak działania skanera.

Surowe zapisane odpowiedzi MRKR, CGEN, OVID i CLNN potwierdziły:
- cyfry w opisach movement/activity mimo zakazu w instrukcji;
- porównanie wolumenu nazwanego sumą sesji ze średnią jednej godziny;
- wpis UNAVAILABLE jako cytat przy pustej liście dozwolonych fragmentów;
- brak związania dozwolonego cytatu z jego konkretnym source_id;
- RSI nazwane przewartościowaniem oraz twierdzenia o zachowaniu inwestorów;
- w CLNN przypisanie wzrostu badaniom klinicznym bez dowodu związku;
- fałszywy alarm reguły o inwestorach dla neutralnego „ryzyko dla inwestorów”.

IMMP otrzymało OpenAI HTTP 400, param=response_format: niedozwolony znak
cudzysłowu w wartości string literal schematu context.fact. To błąd żądania,
przed wygenerowaniem analizy; pozostałe przypadki miały zapisane odpowiedzi.

## Zmiana kontraktu żądania

KI-PROMPT-20261109-v2 zachowuje jakościowe opisy bez cyfr. Oprócz instrukcji
schemat ma statyczny pattern ^[^0-9]*$, odpowiednie długości i opisy pól.
Limity lokalne nadal obowiązują, łącznie z co najmniej dwoma zdaniami dla
końcowej oceny. Nie wprowadzono automatycznej korekty liczb ani dodatkowego
wywołania modelu. Nie należy przepisywać cyfr słownie w celu obchodzenia reguły.

W context.fact model wybiera krótki identyfikator Q. Każda gałąź schematu wiąże
go z jednym source_id. Faktyczny cytat pozostaje w materiale wejściowym i w
zapisanym katalogu dokładnego żądania. Po odpowiedzi program odtwarza dosłowny
fragment, ponownie sprawdza jego obecność w tym źródle, długość i zakazane
polecenia. Nie dopisuje, nie tłumaczy i nie parafrazuje cytatu.

Tekst źródłowy nie trafia już do enum wartości schematu. Przy braku dopuszczalnych
cytatów context ma maxItems=0; nie ma zastępczego faktu UNAVAILABLE. Dopasowanie
tożsamości emitenta i dotychczasowa kwalifikacja źródeł pozostają bez zmian.
Podział zdań zachowuje kropkę między cyframi, więc kwota $9.8 nie jest skracana
do $9. Katalog jest odtwarzany z zapisanego prepared_ai_request, aby późniejszy
odczyt raportu nie przypisywał numeru Q do innego fragmentu po zmianie algorytmu.

Zapisana surowa odpowiedź dostawcy pozostaje niezmieniona. Pełny raport KI
zawiera odtworzony tekst; identyfikatory są wyłącznie formatem transportowym.
Stare odpowiedzi z dosłownymi cytatami nadal są czytelne.

## Walidacja i widok błędów

Neutralne „ryzyko dla inwestorów” nie jest zachowaniem inwestorów. Usunięto
ten konkretny fałszywy alarm; narracje o ich zainteresowaniu i reakcjach nadal
są blokowane. Reguła przyczyn obejmuje również „wzrosła”, a nie tylko „wzrost”.
RSI jako wycena, zmyślone przyczyny, niezgodny status bid/ask i niepoprawne
porównania aktywności nadal wymagają odrzucenia. Ta poprawka nie uznaje
dzisiejszych błędnych raportów za poprawne i nie zmienia ich stanów.

Końcowe oceny pokazują teraz czas zdarzenia, ostatnią aktualizację, last_error
i konkretne quality_issues. FAILED ma polską nazwę. Diagnostyka jest ograniczona
i maskowana; widok nie uruchamia dostawców ani ponowień.

## Weryfikacja

Dziesięć nowych testów obejmuje przypadki produkcyjne, realny schemat JSON,
przypisanie źródło–cytat, kwoty dziesiętne, pusty kontekst, brak możliwości
podmiany faktu w katalogu, zgodność starych cytatów, pojedyncze wywołanie na
spółkę, zachowanie surowej odpowiedzi i odczyt błędu w rzeczywistym panelu.
28 testów celowanych OK. Pełne zestawy są zapisane poza projektem w
ki2-walidacja-20261109; nie sumować pokrywających się zestawów jako niezależnych.
Nie wykonywano płatnych prób ani testowych wiadomości Telegram.

Końcowe wyniki lokalne: 658 testów modułów na Windows OK (dwa pominięcia POSIX),
658 w Ubuntu WSL2 OK (dwa pominięcia migracji Windows); testy wbudowane, panel
25 i uruchamianie 5 — OK. JavaScript pełnego ekranu OK na Windows, nieponawiany
w WSL bez Node. Rzeczywisty graf TradingAgents: READY_OFFLINE.

Kontrola offline nie potwierdza akceptacji żądania przez dostawcę ani jakości
przyszłej odpowiedzi. Testy na Pythonie VPS wykonano przed podmianą; pozostaje
przegląd nowych naturalnych raportów. Nie zwalniać rezerwacji starych zadań FAILED,
REVIEW_REQUIRED i UNCERTAIN dla ponowienia. Model, limity odpowiedzi i selekcji
oraz ustawienia użytkownika pozostają zachowane.

[OpenAI Docs: Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)
opisuje obsługiwany podzbiór schematu, odrzucanie nieobsługiwanych żądań i fakt,
że poprawna struktura nie gwarantuje poprawności merytorycznej. Konkretny błąd
cudzysłowu pochodzi z produkcyjnego logu IMMP, nie z deklaracji dokumentacji.

## Potwierdzenie wdrożenia na VPS

Użytkownik przekazał wynik paczki ki2-walidacja-vps-20261109.tar.gz:
- kontrola sumy eb853f614c412d38b5a522bd5e9a89a6a083319acbcb081fdcb4139db72d5f98 — OK;
- osiem testów instalatora — OK; komunikaty /tmp są testami transakcji i powrotu;
- pełna regresja w środowisku VPS: wszystkie pięć faz 0, wynik PASS;
- rzeczywisty graf TradingAgents skompilowany offline, bez modeli i narzędzi;
- ki2-validation-install-20261109.service: success/0, czas około 4,542 s;
- panel oraz świeże scanner, worker_analysis, worker_telegram potwierdzone;
- kopia kodu: /home/ubuntu/ki2/backup-validation-20261109T162641451779Z.

Zmieniono KI.py, ai_assessment.py, prompt_policy.py i final_company_review.py.
Baza, klucze, ustawienia i kolejki zachowane. Bez płatnych prób i testowych
wiadomości Telegram. Nowy kontrakt dotyczy nowo przygotowanych żądań. Starsze
zapisane żądania i dzisiejsze błędne oceny zachowują własną wersję oraz status.
Commit/push nie były wykonywane w tym kroku.
