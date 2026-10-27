# Audyt spójności AI, bramek i raportów KI 2 — 27.10.2026

Zakres: odczyt bieżącego KI.py i produkcyjnej SQLite w mode=ro, bez nowych wywołań dostawców i bez zmian kodu/ustawień. Projekt: C:\Users\szela\OneDrive\Desktop\KI\2 KI.

## Najważniejszy wniosek

Potwierdzenie ruchu, materiał do interpretacji AI oraz ocena okazji nie mają wspólnego kontraktu decyzyjnego. Potwierdzony wzrost lub spadek bywa nazywany okazją, choć ocena ryzyka jest niepełna, a wskazania sprzeczne. Sam prompt tego nie naprawi.

## Potwierdzone ustalenia

1. opportunity_quality zawsze zwraca Okazja albo Duża okazja. Brak neutralnej klasyfikacji i oceny wykonalności w tej funkcji. Panel nadal pokazuje TOP 20 potwierdzonych okazji.
2. opportunity_local_rank premiuje cenę powyżej otwarcia, górną część zakresu, dodatni histogram, cenę powyżej średniej i +DI ponad -DI. To punktacja wspierająca wzrost, nie symetryczna jakość wzrostów i spadków. Mimo tego opportunity_message podpisuje ją Jakość sygnału. W potwierdzeniach błędny format znaku tworzy np. +-4.34%.
3. automatic_ai_preflight celowo uznaje sprzeczność ruchu z bieżącymi wskazaniami za pytanie dla AI. To uzasadnia interpretację rozbieżności, nie etykietę okazji. Brak bid/ask nie blokuje takiej interpretacji; zakres wyklucza wykonalność transakcji.
4. Przed AI gromadzone są: zapisany snapshot i baza, zakończone Search i filtrowanie źródeł, poprzednia obserwacja, historyczne spready oraz lokalna decyzja preflight. Pozyskanie poprzedniego odczytu/historii jest objęte szerokim except Exception: pass; nie ma jawnego manifestu powodzenia każdej części.
5. W nowym promptcie jest snapshot, poprzedni porównywalny odczyt, lokalne zgodności/sprzeczności, ryzyko, ograniczenia, pytania oraz przyjęte źródła. Po kompresji nie ma pełnego rankingu ani jego szczegółowych części i list confirms/weakens/missing. Są wskaźniki, ale nie wszystkie lokalne oceny z panelu. Źródła dla AI to najwyżej pięć treści przyciętych do 1800 znaków; pełna odpowiedź transportowa jest diagnostyką poza promptem. Materiał jest filtrowany, nie kompletnym dossier emitenta.
6. Bramka publikacji sprawdza co najmniej dwa wskaźniki z różnych kategorii i obecność ceny/kierunku/momentum. Nie potwierdza pełnej poprawności znaczenia zdań. Walidacja cyfr i cytatów nie wystarcza do wychwycenia błędnej interpretacji bez cyfr. Wyrażenia regularne dla ATR/ADX mają luki w sformułowaniach.

## Dowody z zapisanych raportów 26.10

- SLDB: RSI 32.713557; model napisał stan wykupienia. Zapisano DONE i DELIVERED. Snapshot: 2026-10-26T19:16:25.526052Z.
- INO: RSI 39.769181; model napisał stan wyprzedania. Bid 0.7328, ask 0.9827, spread 29.134363%, świeżość niepotwierdzona. Klasyfikacja rankingu: Okazja, 30 punktów; zmiana od bazy -4.344444%.
- ENTX: brak bid/ask (Timeout Yahoo); model użył RSI jako argumentu niedowartościowania, którego sam wskaźnik nie dowodzi. Wynik DONE i DELIVERED. Również ocena zmienności na podstawie samego ATR przeszła filtr.

Raporty te pochodzą sprzed wdrożenia preflight. W chwili audytu brak nowych analysis_jobs ze zdarzeniami utworzonymi 27.10, więc nie ma produkcyjnego dowodu nowego promptu na żywym wywołaniu. Bieżący launcher z 27.10 12:15:22 UTC i skaner działają; ostatni cykl OK. Nie ponawiano historycznych wyników.

## Zalecany wspólny kontrakt do następnej naprawy

- Przed AI utrwalić jeden manifest: tożsamość/czas, detekcja, jakość techniczna, aktywność, ryzyko/kwotowania, historia porównawcza, źródła i stan gotowości każdego modułu. AI, panel i Telegram korzystają z tej samej wersji manifestu.
- Rozdzielić etykiety: potwierdzony ruch, obraz zgodny lub sprzeczny, ryzyko i dane niepełne. Nie używać samego słowa okazja jako wyniku detekcji.
- Wskaźniki i lokalne predykaty są faktami z programu. AI wyjaśnia relacje, a nie samodzielnie klasyfikuje RSI/DI, siłę lub zmienność bez sprawdzonej podstawy.
- Wprowadzić kontrolę zgodności wniosków z lokalnymi predykatami oraz ogólny wynik spójności raportu przed publikacją, zamiast polegać wyłącznie na liczbach, cytatach i liczbie wskaźników.
- Uczciwie rozdzielić filtrację źródła, dostępny fragment treści i niepotwierdzoną przyczynowość. Kompletność ma oznaczać jawny stan wszystkich wymaganych części, nie ukrywanie braków.
