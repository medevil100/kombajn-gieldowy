# KI — wersja testowa: dwie świece, GPT-4o mini, TradingAgents

Gałąź: `ki-stage1-test`. Plik aplikacji nadal nazywa się `KI.py`.
Nie wdrożono do main ani na VPS.

## Automat

- Wszystkie odczyty Yahoo nadal trafiają do SQLite. Zdarzenia zmian ceny/RVOL są lokalną diagnostyką i nie uruchamiają płatnych usług.
- Pierwszy odczyt tworzy odniesienie, bez alertu.
- Pierwsza świeca 1h musi być zamknięta: wzrost od własnego otwarcia co najmniej 2%, RVOL co najmniej 1,50.
- Bezpośrednio następna świeca musi otworzyć się **powyżej** zamknięcia pierwszej. Równe lub niższe otwarcie nie kwalifikuje się.
- W drugiej świecy aktualna cena musi być powyżej jej otwarcia, RVOL co najmniej 1,50, a wolumen dodatni.
- RVOL = wolumen badanej świecy / średnia wolumenu poprzednich 20 zamkniętych świec. Badana świeca jest wyłączona ze średniej. RVOL otwartej świecy jest niepełny, do chwili jej zamknięcia.
- RVOL drugiej świecy co najmniej 3,00 oraz dodatni histogram MACD, cena ponad SMA 10 i +DI > −DI pozwalają oznaczyć „Duża okazja”. To nie oznacza małego ryzyka.
- Kandydat wygasa na końcu drugiej świecy. Ten sam układ świec nie jest ponownie analizowany ani wysyłany.
- Po przebiegu wybierane są maksymalnie trzy nowe okazje według lokalnej oceny, następnie RVOL, następnie tickera. To limit, nie wymagana liczba wiadomości.
- Budżet dodatkowo ogranicza wybór do trzech sekwencji w każdym 15-minutowym przedziale UTC, także po restarcie.
- Lokalny ranking: ruch 30, aktywność 30, technika 30. Datowany fakt z gotowej analizy daje dalsze 10 punktów. Braki nie są przeliczane do pełnej skali.
- Dla wybranej sekwencji: jedno zapytanie Tavily i jedno GPT-4o mini; bez automatycznego ponawiania błędnych lub niepewnych zapytań. Stan i odpowiedź pozostają w SQLite.
- Jeden krótki Telegram łączy dane, ocenę, kontekst i ryzyko. Nie ma osobnego wstępnego alertu i późniejszego uzupełnienia AI.
- Przed zapytaniem oraz wysyłką sprawdzana jest aktualna obserwacja, ważność świecy i obecność tickera na aktywnej liście. Stare kolejki automatu są filtrowane.

## Ryzyko i spread

Spread = (ask − bid) / ((ask + bid) / 2) × 100%.
Bid/ask pobierane są z Yahoo tylko dla maksymalnie trzech wybranych okazji.
Cofnięcie od maksimum drugiej świecy co najmniej 2% lub spread co najmniej 2% oznacza ryzyko podwyższone. Taka okazja nadal może zostać wysłana z podaną przyczyną ryzyka.
Yahoo nie udostępnia potwierdzonego czasu aktualizacji bid/ask. `regularMarketTime` jest czasem transakcji, a nie spreadu. Brak danych lub niepotwierdzona świeżość uniemożliwia etykietę ograniczonego ryzyka. Nie ma minimalnej kwoty obrotu.

## Panel i ręczna analiza

TOP 20 ma czytelne karty, a źródła i pełne uzasadnienie są rozwijane.
Odświeżanie wyników automatu pozostaje co 15 minut. Nie uruchamia GPT.
Rozmowa z GPT i ręczne Tavily + GPT pozostają niezależne od automatu; płatne wywołania uruchamia przycisk.
Usunięcie tickera z zapisanej listy zatrzymuje jego dalsze przetwarzanie i nowe zapytania/wysyłki; nie usuwa historii z SQLite.

## Osobny TradingAgents

Wymaga Python 3.11+ i osobnego środowiska. Obok działającego KI.py umieść `Instaluj-TradingAgents.ps1` i `requirements-tradingagents.txt`, następnie uruchom instalator w PowerShell:

```powershell
& '.\Instaluj-TradingAgents.ps1'
```

Instalator pobiera dokładnie TradingAgents 0.6.0 z zatwierdzonego commitu `1394a3f72aa4393e1a98f51b382434c4b4c2d972`. Zależności pozostają poza środowiskiem skanera. Używa istniejącego `OPENAI_API_KEY`; nie wymaga klucza DeepSeek.

Widok „Analiza pogłębiona” uruchamia osobny proces wyłącznie przyciskiem. Oba poziomy modeli korzystają z GPT-4o mini. Dane rynkowe, fundamenty i wiadomości są skonfigurowane na Yahoo, bez innych dostawców. Trzech analityków: technika, wiadomości, fundamenty; po jednej rundzie debaty i ryzyka. Raporty po polsku są zapisywane w SQLite. To analiza dzienna, niezależna od potwierdzania dwóch świec 1h. Nie wysyła Telegrama ani zleceń. Każde uruchomienie obejmuje wiele płatnych wywołań API; limit automatu go nie obejmuje. Odświeżenie widoku czyta zapisany wynik. Proces ma limit czasu 20 minut; po niepewnym wyniku nie ponawia się sam.

## Weryfikacja przed main / VPS

```powershell
foreach ($testKI in @('--self-test', '--panel-test', '--launch-test')) {
    python .\KI.py $testKI
    if ($LASTEXITCODE -ne 0) { throw "Test $testKI nie przeszedl." }
}
```

Testy wykorzystują rzeczywiste transakcje SQLite, procesy uruchomieniowe i Streamlit AppTest; brak mocków usług. Dane scenariuszy są jawnie zdefiniowanymi wejściami do testów reguł, nie wynikami połączeń z Yahoo.
Testy lokalne nie dowodzą odpowiedzi płatnych usług. W środowisku wykonawcy brak kluczy Tavily, OpenAI i Telegram. Do sprawdzenia na komputerze właściciela: rzeczywiste wyszukiwanie Tavily, odpowiedź GPT-4o mini, raport TradingAgents, doręczenie jednej wiadomości Telegram i brak jej powtórzenia w następnych odczytach.

Przy ponad 1700 tickerach sprawdź w monitorze czas pełnego przebiegu i pominięte sloty. Jeśli pobranie wszystkich danych trwa dłużej niż 15 minut, skaner nie nakłada cykli i raportuje przekroczenie; nie ma gwarancji odczytania całej listy w każdym slocie. Wygasłe okazje nie trafiają do płatnej kolejki.

Przeniesienie do main i uruchomienie na VPS dopiero po testach właściciela i jego decyzji.

## Poprawka narzędzi TradingAgents — 05.10.2026

TradingAgents 0.6.0 udostępniał narzędzia makro i prognoz mimo wyłączonych dostawców. Napraw-TradingAgents.py jawnie usuwa je oraz ich instrukcje z agenta wiadomości w osobnym środowisku. Sprawdza wersję i hash źródła, zachowuje kopię, weryfikuje wspólny zestaw narzędzi modelu i grafu. Instalator stosuje poprawkę przed weryfikacją. Istniejące środowisko: uruchom skrypt jego interpreterem, następnie uruchom nową analizę ręcznie. Skrypt nie wywołuje API.

## Czyszczenie błędów i późniejszy reset SQLite

Każdy widok ma przycisk „Wyczyść zapisane błędy”. Ukrywa dokładne wersje zapisanych błędów w normalnej historii, bez usuwania audytu, udanych raportów, odczytów, deduplikacji i aktywnych zadań. Nowy błąd pozostaje widoczny. Przycisk nie naprawia błędów DOM przeglądarki; tam wyłącz tłumaczenie i odśwież stronę.

Reset-Spolki.py uruchamiaj osobno po zatrzymaniu programu, dopiero gdy chcesz rozpocząć od pustej listy. Usuwa dane spółek, portfolio, alerty, rozmowy, analizy i kolejki z obu baz (automatycznej i ręcznej). Zachowuje ustawienia, klucze poza bazą i metadane migracji. Przed resetem blokuje procesy i tworzy sprawdzone kopie obu baz. Nie wywołuje API.

Test resetu: python .\Reset-Spolki.py --self-test

Polecenie resetu do późniejszego użycia: python .\Reset-Spolki.py --confirm "WYCZYSC DANE SPOLEK"

Po resecie uruchom program i dodaj wyłącznie wybrane spółki. Pierwszy odczyt tworzy punkt odniesienia. Reset nie przenosi projektu na main i nie wdraża VPS.
