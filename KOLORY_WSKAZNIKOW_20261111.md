# Kolory wskaźników — 11 listopada 2026

Status: wdrożono na VPS 11 listopada 2026 o 16:43 UTC (17:43 CET).
Instalator zakończył się success/0 po 12 testach instalatora, pięciu fazach
regresji VPS i kompilacji grafu analizy pogłębionej offline. Panel i trzy
heartbeaty potwierdzone. Sprawdzenie wyglądu na urządzeniu właściciela pozostaje.
Kopia kodu: `/home/ubuntu/ki2/backup-indicator-colors-20261111T164300098502Z`.
Raport VPS: `/home/ubuntu/ki2-wskazniki-kolory-vps-20261111/tests-20261111T164056625080Z`.

Jeden moduł `indicator_view.py` wyświetla zapisane wskaźniki w raportach
Automatu i ręcznego tickera, analizie GPT (zapisane dane rynku), końcowych
ocenach, pełnym raporcie TOP 5 i rozwijanych szczegółach portfela.
Istniejące kolorowe progi SL/TP i poziomy w portfelu oraz śledzeniu pozostają.
Tabele administracyjne i liczniki diagnostyczne nie otrzymują arbitralnej
interpretacji wzrost/spadek.

- Wartości i dotychczasowe opisy są zachowane. Kolor ma tekstowe uzasadnienie.
- Cena względem SMA, VWMA, VWAP, pasma BB i Fibonacci: powyżej, poniżej lub na
  poziomie wraz z różnicą procentową względem poziomu.
- Bollinger: pasek ceny, środkowej i obu skrajnych wstęg; cena poza pasmem
  ma jawny opis i rzeczywistą pozycję procentową, znacznik na brzegu.
- RSI, Stochastic i Stoch RSI: skala 0–100, skrajne strefy bursztynowe.
  Nie oznaczają automatycznego kupna ani sprzedaży.
- MACD: relacja do sygnału; DI: relacja +DI do −DI. Nie wymyśla przecięcia
  z jednej migawki. ROC ma kolor znaku, OBV neutralny bez pomiaru zmiany.
- ADX i ATR opisują siłę/zmienność, nie kierunek. RVOL opisuje aktywność
  i zachowuje informację o częściowej lub skróconej świecy.
- Bez aktualnej daty lub po 20 minutach od odczytu: neutralne kolory,
  jawny zapis historyczny i opisy odnoszące się tylko do zapisanych wartości.
- Telefon do 600 px: nazwa i wartość obok siebie, opis pod spodem.
  Pozostałe szerokości: trzy elastyczne kolumny. Bez dodatkowego poziomego
  przewijania. Kolory i symbole nie zastępują werdyktu orkiestratora.

Zmiana jest tylko prezentacyjna. Nie zmienia pól wskaźników, scoringu,
manifestów AI, selekcji, progów, planów, baz, kolejek ani powiadomień.
Otwarcie widoku nie wywołuje dostawców.

Nowe testy: brak i niepoprawne dane, granice BB, strefy oscylatorów,
neutralne miary, częściowa aktywność, historyczne i przyszłe daty,
HTML escaping, niezmienność danych i uruchomienie widoku Streamlit.
Artefakty regresji i podglądy 360/768/1440 px: `ki2-indicator-colors-20261111`
w katalogu artefaktów sesji. Wyniki pełnych testów w raporcie paczki.

Commit i push pozostają osobnym, niezakończonym krokiem.
