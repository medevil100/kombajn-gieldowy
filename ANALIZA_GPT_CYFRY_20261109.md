# Analiza GPT — cyfry Unicode i odwołania do progów, 9 listopada 2026

Status: wdrożono na VPS 9 listopada 2026 o 17:54 UTC (18:54 CET).
Potwierdzenie użytkownika: instalator success, kod 0; panel i trzy heartbeaty
potwierdzone. Wszystkie pięć etapów regresji VPS zakończono wynikiem 0, PASS.
Graf TradingAgents skompilowano bez modeli i narzędzi. Kopia kodu:
`/home/ubuntu/ki2/backup-manual-numeric-20261109T175407208500Z`.
Raport: `/home/ubuntu/ki2-gpt-cyfry-vps-20261109/tests-20261109T175220417476Z`.
Nie wykonano płatnej analizy ani wiadomości testowej; wynik rzeczywistej nowej
ręcznej analizy pozostaje do sprawdzenia. Błąd końcowej oceny FBIO jest osobny.

## Zgłoszenie i przyczyna

Ręczny raport odrzucono w `risks[0]` z powodu tekstu
`Cofnięcie od maksimum bieżącej świecy ≥ ٢%`. Znak `٢` oznacza cyfrę 2.
Walidator Python słusznie odrzucił liczbę bez odwołania do danych. Schemat
generowania używał `\d`, którego znaczenie w JavaScript/JSON Schema i Python
różni się dla cyfr Unicode. Dodatkowo lokalny opis ryzyka zawierał dosłowne
`2%`, bez dostępnego wcześniej osobnego odwołania do progu cofnięcia.

## Zmiana

- Schemat jawnie wyklucza znaki dziesiętne Unicode poza dozwolonymi odwołaniami.
  Nie polega na różnym znaczeniu `\d`. W JavaScript bez flagi Unicode pary
  surogatów cyfr z dalszych płaszczyzn mogą ograniczać dodatkowe znaki spoza BMP;
  polski tekst i odwołania do zapisanych nazw emitentów przechodzą.
- Dodano osobny stały próg `threshold:retrace_risk_pct` oraz zmierzony
  `metric:adverse_retrace_pct`. Wartość progu nie zastępuje pomiaru.
- Lokalne opisy cofnięcia, odbicia i spreadu są przekazywane z odwołaniami
  także wewnątrz list ryzyka. Pomiar w `local_analysis.risk.pullback_pct`
  jest powiązany z katalogiem liczbowym.
- Zachowano walidację jednostek, dostępności pola, tożsamości emitenta oraz
  oryginalne odrzucone odpowiedzi. Nie przepisuje się cyfr w zapisanym raporcie,
  nie usuwa zdań i nie ponawia zadań automatycznie.

Dotyczy ręcznych widoków korzystających z kontraktu raportu v3, w tym
„Analiza GPT”. Nie zmienia reguł kwalifikacji automatu, scenariuszy,
parametrów modelu ani liczby wywołań. Po wdrożeniu poprawiony kontrakt dotyczy
nowych analiz; dotychczasowy błąd pozostaje zapisem poprzedniej próby.

## Weryfikacja

Pięć nowych testów: reprodukcja błędu i nienaruszalność odpowiedzi;
zgodność Python i JavaScript z flagą Unicode i bez niej dla wszystkich cyfr
dziesiętnych rozpoznawanych przez lokalny Python; symbole i polski tekst;
rzeczywisty pakiet żądania dla cofnięcia i odbicia; rozdzielenie pomiaru od
progu i odrzucanie niezgodnych jednostek. 44 testy ręcznej analizy OK.
Pełna regresja: Windows 672 testy modułów OK (dwa pominięcia POSIX),
Linux WSL2 672 testy OK (dwa pominięcia Windows i brak Node.js w teście
silnika JavaScript); testy wbudowane 522, panel 25 i uruchamianie 5 OK na obu.
JavaScript pełnego ekranu i kontrakt cyfr sprawdzone na Windows.
Raporty w `ki2-manual-unicode-20261109/regression-windows` w artefaktach Codex
oraz `/home/szela/ki2-manual-unicode-check-20261109/regression` w WSL.
Bez zapytań AI, Tavily i bez testowych wiadomości.

Schemat `pattern` jest wspieranym ograniczeniem Structured Outputs:
[OpenAI Docs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
Różnicę silników i konkretny błąd potwierdzają lokalne testy, a nie ta strona.
