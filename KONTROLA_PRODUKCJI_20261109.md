# Kontrola KI 2 po naturalnej sesji — poniedziałek 9 listopada 2026

Produkcja: `/home/ubuntu/ki2` na OVH. Nie zastępować jej lokalną bazą z PC.
Nie uruchamiać drugiego skanera ani ręcznych płatnych testów.

## Przygotowanie narzędzia odczytu — PowerShell na PC

Jedyny wysyłany plik to samodzielny skrypt odczytu, bez kluczy i bazy:

```powershell
scp -i "$env:USERPROFILE\.ssh\ki2_ovh_ed25519" "C:\Users\szela\OneDrive\Desktop\KI\2 KI\ki2_readonly_audit.py" ubuntu@149.56.211.128:~/ki2_readonly_audit.py
ssh -i "$env:USERPROFILE\.ssh\ki2_ovh_ed25519" ubuntu@149.56.211.128
```

Hasło do klucza wpisywać wyłącznie w terminalu. Powyższy skrypt nie jest
wdrożeniem nowej wersji KI. Nie wymaga zatrzymania ani restartu usług.

## Kontrole po zalogowaniu — Ubuntu na VPS

```bash
date -u
systemctl is-active ki2 ki2-guardian.timer ki2-backup.timer
sudo journalctl -u ki2-backup.service --since '2026-11-09 00:00:00 UTC' -n 25 --no-pager
systemctl show ki2-backup.service -p Result -p ExecMainStatus
systemctl list-timers ki2-backup.timer --no-pager
df -h /
curl --max-time 10 http://127.0.0.1:8501/_stcore/health
python3 -B ~/ki2_readonly_audit.py --db ~/ki2/KI.matrix.sqlite3 --since 2026-11-09T00:00:00+00:00
```

Raport odczytu pokazuje liczniki i heartbeaty, bez surowych odpowiedzi, promptów
czy sekretów. Zadania są wybierane według daty utworzenia zdarzenia. Nie jest to
rozliczenie faktury dostawcy ani samodzielny dowód jakości analiz.

## Ocena kilku nowych raportów w panelu i Telegramie

Sprawdzić dla każdej wybranej spółki niezależnie:
- zgodność czasu odczytu, selekcji i opisywanej sesji;
- przebieg sesji od jej otwarcia, nie tylko dwie ostatnie świece;
- rozróżnienie zmiany od otwarcia i od stałej ceny bazowej poprzedniej sesji;
- wolumen każdej świecy liczony raz, bez sumowania kolejnych odczytów narastających;
- rzeczywiste braki i skrócone przedziały opisane bez zmyślonego godzinowego RVOL;
- zgodność techniki, aktywności, ryzyka, scenariuszy i dostępności SL/TP;
- bid/ask jako informacja z jawną niepotwierdzoną świeżością;
- przyczyny i cytaty oparte na przyjętych źródłach, bez domyślnego wyjaśniania ruchu;
- jeden zbiorczy Telegram i brak ponownych wysyłek tej samej oceny.

Do 16:00 można ocenić tylko dane dostępne do tej chwili. Ocena końcowej świecy
sesji USA wymaga jej późniejszego wystąpienia; nie wyciągać tego wniosku z wcześniejszej próby.

Brak sześciu lub nawet trzech spółek nie jest sam w sobie błędem. Odrzucenie
materiału z rzeczywistą luką w sesji jest oczekiwane. Błędy przygotowania lub
niespójny opis świeżych, kompletnych danych wymagają sprawdzenia konkretnego zapisu.
Nie ponawiać historycznych FAILED/REVIEW_REQUIRED/UNCERTAIN i nie luzować bramek
tylko w celu uzyskania DONE.

## Finalizacja Git i ewentualne wdrożenie

Po ocenie raportów sprawdzić jeszcze raz wybrane pliki i staging, pozostawiając
osobno wcześniejszą zmianę użytkownika w `_ai_review.py`. Następnie commit/push
zgodnie z ustaleniem. Nie używać `git add .`.

8 listopada około 17:38 UTC wdrożono na VPS `KI.py`, `ki2_paths.py` i
`prompt_policy.py`, po pełnej regresji w jego środowisku. Instalator zakończył
się success/0 i potwierdził panel oraz świeże trzy heartbeaty. Kopia kodu:
`/home/ubuntu/ki2/backup-prompts-20261108T173849719593Z`.
Nie przesyłano profilu Windows ani lokalnych sekretów. Kontrola naturalnych
odpowiedzi pozostaje do wykonania. Zasady promptów: `PROMPTY_KI_20261108.md`.

Kontrola naturalnych odpowiedzi 9 listopada ujawniła błędy opisane w
WALIDACJA_OCEN_20261109.md. Poprawkę wdrożono o około 16:26 UTC; pełne testy
na VPS PASS, instalacja success/0, panel i trzy heartbeaty świeże. Kopia kodu:
`/home/ubuntu/ki2/backup-validation-20261109T162641451779Z`.
Do oceny tej poprawki wybierać nowo przygotowane żądania z kontraktem
KI-PROMPT-20261109-v2. Wczorajsze i wcześniejsze dzisiejsze raporty mają własną
wersję; nie używać ich do oceniania nowego kontraktu. Odczyt zbiorczy można
ograniczyć przez `--since 2026-11-09T16:26:41+00:00`; data utworzenia zdarzenia
nie zastępuje jednak sprawdzenia rzeczywistej wersji zapisanego żądania.
