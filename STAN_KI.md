# KI — AKTUALNY STAN PROJEKTU

## Wersja odniesienia
Repozytorium: medevil100/kombajn-gieldowy
Galaz rozwojowa: ki-stage1-test
Wersja: E05, uruchomiona z rzeczywistymi uslugami 9.10.2026.
SHA-256 KI.py:
C6C045D37389B040117C0BB74D420B3BE2B895CE8B9D96D154FA9B9ED92AD74D

To jest punkt powrotu przed E06-E08.
Main pozostaje nietkniety. Nie tworzymy nowej galezi dla kazdej poprawki.

## Zasady wspolpracy
Wlasciciel jest architektem i decydentem.
Asystent analizuje, doradza, weryfikuje i pyta.
Brak implementacji, wdrozenia lub commita bez zatwierdzenia.
Jedna zmiana na raz. Testy, audyt, nastepnie decyzja.
Bez mockow maskujacych prawdziwy przeplyw.
Nie umieszczac kluczy API ani baz SQLite w repozytorium.

## Dzialanie KI
Rynki: GPW, NewConnect, USA.
Zrodlo danych: Yahoo Finance.
Tylko akcje. Bez automatycznych zlecen brokerskich.

Przy uruchomieniu 9.10.2026 lista miala 502 tickery.
Glowna swieca: 1H. Odczyty: co 15 minut.
Stala cena bazowa zachowywana w SQLite.

E05: trzy potwierdzenia wymagaja nowej aktywnosci rynku.
Powtorzone identyczne notowanie nie jest nowym potwierdzeniem.
Aktywnosc moze byc potwierdzona nowym wolumenem w tej samej
swiecy 1H albo dodatnim wolumenem kolejnej swiecy.
Brak aktywnosci nie usuwa spolki z obserwacji.

E01: tylko prawidlowe dane do kwalifikacji.
E02: kontrola swiezosci danych dla nowej analizy.
E03: wylaczone AI/Tavily wstrzymuje Telegram.
E04: usuniety staly limit trzech analiz na cykl.
E05: rzeczywiste dowody aktywnosci dla potwierdzen.

Tavily i GPT uruchamiane w automacie po potwierdzeniu ruchu.
Reczna analiza GPT/Tavily dziala niezaleznie, po kliknieciu.
Raport rozdziela detekcje, jakosc ruchu i ryzyko.

## Weryfikacja 9.10.2026
302 testy offline PASS wedlug wyniku uruchomienia na Windows.
Potwierdzono rzeczywiste polaczenia Yahoo, Tavily, GPT
i wysylke Telegrama oraz zapis danych w SQLite.
Nie potwierdzono poprawnosci kazdego wniosku GPT,
kazdego wyniku Tavily ani gotowosci VPS.

Lokalna kopia:
C:\Users\szela\OneDrive\Desktop\KI\KI_BAZA_DZIALAJACA_20261009_E05

Przechowuje oryginalny kod oraz obie zweryfikowane bazy SQLite.
Bazy pozostaja poza GitHubem.

## Otwarte problemy
E06 Tavily: sprawdzic wyszukiwanie, domeny emitentow,
fallback i powody odrzucania wynikow. API odpowiada,
ale nie wszystkie wyniki przechodza walidacje.

E07 GPT i Telegram: sprawdzic wynik GPT, walidacje liczb
oraz jego przekazywanie do wiadomosci.
Telefon/tablet: czytelny wniosek i uzasadnienie.
Rozwazane etykiety: KUP, TRZYMAJ, SPRZEDAJ, BRAK DECYZJI.
Zasady rekomendacji wymagaja osobnego zatwierdzenia.
Nie tworzyc rekomendacji bez wiarygodnych podstaw.

E08 TOP 20: zastapic powtarzalne zdanie o punktacji
rzeczywistym uzasadnieniem. Skladniki punktacji:
ruch 30, aktywnosc 30, technika 30, kontekst 10.
Pokazywac braki danych i ryzyka.

Dwa stare napisy panelu o limicie trzech analiz
nadal wystepuja w zamrozonym KI E05.
Nie poprawiac ich w commicie bazy.

## Dalsza kolejnosc
E06 Tavily, nastepnie E07 GPT/Telegram, nastepnie E08 TOP 20.
Po poprawkach pelna regresja i rzeczywisty test integracyjny.
Dopiero potem decyzja wlasciciela o VPS.

## Instrukcja dla kolejnego czatu
Najpierw przeczytaj STAN_KI.md, TESTY_KI.md i kod KI.py.
Sprawdz aktualny commit i Git status.
Nie przywracaj starego filtra dwoch swiec ani limitu 3 analiz.
Nie zakladaj, ze testy offline dowodza gotowosci produkcyjnej.

## E06 - KANDYDAT PO REGRESJI WINDOWS

Data: 09.10.2026.
Punkt powrotu E05:
a599b0ef3cfdbe161a227f0413a94a2e2dd708cb

SHA256 KI.py E06:
6CAF50D72D259E123C9C3F400CE501B72AE69CEC2B124499D6150B33BD8C3B72

Zakres E06:
- kwalifikowanie dodatkowych zrodel w fallback Tavily prefer;
- potwierdzenie pelnej nazwy emitenta;
- kontrola daty, tozsamosci emitenta i pochodzenia zrodla;
- diagnostyka wynikow przyjetych i odrzuconych;
- zachowany limit dwoch zapytan Tavily na zdarzenie.

Nie zmieniono detektora E05, rankingu ani kontraktu GPT.
Nie zmieniono Telegrama ani baz SQLite.

Regresja Windows: 311/311 PASS, 20/20 grup.
Testy offline nie wykonaly platnych wywolan API.

STATUS: E06 KANDYDAT.
Do zamkniecia E06 wymagany osobno zatwierdzony test
rzeczywistego API Tavily oraz kontrola jego wynikow.

Nastepne poprawki: E07 GPT/Telegram, E08 TOP 20.
Nie przywracac filtra dwoch swiec ani limitu 3 analiz.
