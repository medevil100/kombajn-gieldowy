# KI 2 — uzgodnione reguły źródeł, 28.10.2026

Projekt: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`. Pozostaje wyłącznie OpenAI; wcześniejszego usunięcia DeepSeek nie cofnięto.

## Wdrożone zasady

- Wyszukiwanie wymaga potwierdzonej nazwy emitenta. Brak nazwy nie powoduje zapytania po samym tickerze. Dane uzupełnione z już pobranego zgodnego profilu Yahoo pozostają dopuszczone; nie dopisano zgadywanych nazw ani domen.
- Materiał z samą datą, bez godziny, jest odrzucany także dla wcześniejszych dni. Nie jest tworzona sztuczna godzina 23:59:59. Nadal wymagane są strefa czasowa, właściwy emitent, dopuszczona domena i dostępność materiału przed granicą odczytu.
- Extract pozostaje jawnym etapem pobrania pełnej treści. Partia większa niż osiem unikalnych URL otrzymuje LIMIT_EXCEEDED, z liczbą wymaganych adresów i zerem prób. Nie jest obcinana ani wysyłana do dostawcy. Taki wynik zatrzymuje nową analizę przed AI.
- Deduplikacja rozpoznaje ten sam adres po usunięciu znanych parametrów śledzących i fragmentu URL oraz identyczne pełne treści z tej samej domeny i z tą samą datą publikacji. Pełna treść zastępuje fragment w duplikacie tego samego adresu. Oryginalna odpowiedź i odrzucenia pozostają w diagnostyce.
- Sam tytuł nie jest podstawą łączenia raportów. Nie zgadujemy, czy różnojęzyczne teksty są tą samą publikacją. Usunięcie duplikatu po odpowiedzi nie odzyskuje automatycznie slotów Search i nie uruchamia kolejnego wyszukiwania.

## Zachowane zasady

- Fragmenty Search nie są materiałem dla AI; pełne źródła pozostają przyjęte niezależnie od innych niepełnych wyników. W aktualnych automatycznych i ręcznych wywołaniach wymagane są dopuszczone domeny.
- Nie wprowadzono zbiorczej blokady PDF, static-files lub PAP. Format/adres nie zastępuje oceny zawartości i czasu.
- Bez źródeł zewnętrznych AI może wyjaśnić zweryfikowaną technikę tylko przy wartościowym pytaniu dopuszczonym przez preflight. Przyczyna ruchu pozostaje nieustalona. Prosty opis może pozostać lokalny.
- Obowiązuje limit całego żądania 160 000 znaków. Nie obcina się źródeł i nie dodano osobnego limitu artykułu.
- Zachowano odczyt historycznych raportów i zgodność potrzebną do ich wyświetlania. Nie zmieniono starych wyników, nie wznowiono historycznych zadań i nie wysłano ponownie wiadomości.

## Weryfikacja

Dodano regresje braku nazwy, wcześniejszej daty bez godziny, zbyt dużej partii bez wywołania API, identycznych treści, tego samego tytułu przy różnych treściach, parametrów śledzących oraz dopuszczalnego PDF. Dotychczasowe przypadki dodatnie mają jawne znaczniki czasu; przypadki odrzuceń nadal weryfikują brak godziny i strefy.

Testy wykonywano na kopii kodu i tymczasowych bazach, bez ręcznych płatnych wywołań i Telegrama. Kopie zmienionych plików oraz wyniki wdrożenia: `backup_20261027_top10/source-rules-20261028/`. Commit i push nie są wykonywane automatycznie.
