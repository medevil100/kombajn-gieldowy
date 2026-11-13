# Asystent KI — przyjmowanie końcowej odpowiedzi

Wynik użytkownika z VPS: tura 2026-11-11T22:15:26.388122+00:00, trzy zapisane
pakiety danych, cztery wywołania OpenAI. Tokeny wyjściowe: 15, 16, 16, 472.
Ostatnie wywołanie nie wyczerpało limitu 2000 tokenów. Pierwsze wydanie nie
zapisywało finish_reason, dlatego nie można odzyskać dokładnej postaci tej
odrzuconej odpowiedzi ani stwierdzić konkretnego statusu jej zakończenia.

Zidentyfikowana wada odbiornika: uznawał za poprawne wyłącznie finish_reason
tool_calls, również w końcowym kroku syntezy. Poprawka:

- Końcowy krok nie wymusza wywołania funkcji answer. Żąda zwykłej odpowiedzi
  JSON Schema z polami paragraphs/limitations; poprawnym zakończeniem jest stop.
- Wcześniejsza kompletna funkcja answer ze statusem stop jest również sprawdzana
  przez ten sam walidator. Nie przyjmujemy dowolnego tekstu bez wymaganej struktury.
- Nadal odrzucamy ucięte odpowiedzi, odmowy, błędny JSON i nieistniejące odwołania
  do dowodów. Nie ma automatycznych powtórek ani zmiany limitów kosztów.
- Nowa tabela assistant_call_diagnostics przechowuje tylko metadane protokołu:
  przyczynę zakończenia, liczbę wyborów/funkcji, obecność odmowy, liczbę znaków
  treści, limit wyjścia i wersję kontraktu. Nie zapisuje surowej treści ani argumentów.
- Komunikaty rozróżniają limit długości, odmowę i błąd formatu.
- Prompt zaleca 3–5 zwięzłych akapitów zamiast kopiowania całych tabel.

Zapisane nieudane pytanie nie jest ponawiane ani przerabiane na sukces. Po
wdrożeniu użytkownik może wysłać nowe pytanie. Wątki, dowody i rozliczenie poprzednich
wywołań pozostają w bazie. Odczyty danych, automat, Telegram, TOP 5 i kolory bez zmian.

Testy obejmują prawdziwy adapter HTTP KI z zamockowanym requests.post: trzy odczyty
narzędzi i czwarta odpowiedź JSON stop, oraz answer ze statusem stop. Dodatkowe
przypadki obejmują odmowę, length, błędny JSON, brakujące dowody i brak ponowień.
Nie wykonano płatnych testów; konkretna odrzucona odpowiedź z VPS nie była zapisana.
