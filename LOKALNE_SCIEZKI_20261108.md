# Wykonana migracja lokalnych ścieżek KI 2 — 8 listopada 2026

Kod: `C:\Users\szela\OneDrive\Desktop\KI\2 KI`.
Lokalne dane aktywne: `C:\Users\szela\KI2-local`:

- `data\KI.matrix.sqlite3` — zweryfikowana kopia lokalnej bazy z 28 października;
- `config\secrets.toml` — aktywna lokalna konfiguracja usług;
- `config\previous-project-secrets.toml` i `previous-project.env` — kopie powrotne;
- `logs` — docelowe logi panelu, skanera i launchera;
- `backups` — przygotowane miejsce na przyszłe lokalne kopie;
- `migration-report.json` — wynik porównania liczby rekordów wszystkich tabel.

To nie jest aktualna baza VPS. Portfel i bieżące dane produkcyjne pozostają na
OVH. Na PC do bieżącej pracy nadal służy skrót **KI - VPS**. Podczas migracji
nie uruchamiano lokalnego skanera, płatnych analiz ani wiadomości Telegram.

## Wykonane zmiany

1. Wydzielono `ki2_paths.py`: domyślna baza, plik kluczy i logi. `KI.py`
   zachowuje dotychczasową funkcję `load_service_keys` jako zgodny interfejs.
2. Profilem jest ignorowany przez Git `.ki2-local-paths.json`. Zawiera wyłącznie
   ścieżki, bez wartości kluczy. Jest stosowany automatycznie wyłącznie na Windows.
   Na Linuxie domyślna baza i konfiguracja pozostają w obecnych lokalizacjach.
3. Zachowano priorytet kluczy: środowisko > wybrany plik projektu > konfiguracja
   domowa. Zewnętrzny plik zastępuje plik projektu; jego brak jest błędem,
   bez cichego powrotu do starej konfiguracji. Jawne `--db` nadal ma pierwszeństwo.
4. `Start-KI2.ps1` odczytuje te same ścieżki co KI i nie uruchamia drugiego
   skanera, gdy ten sam projekt działa z inną bazą.
5. Kopia SQLite wykonana z odczytu, pod blokadami skanera i launchera;
   `quick_check=ok`, zgodne liczby rekordów wszystkich 28 tabel.
   Oryginalna baza pozostaje w projekcie jako kopia powrotna, nie została usunięta.
6. Po weryfikacji identycznych wartości usług usunięto z aktywnego katalogu
   projektu `.streamlit\secrets.toml` oraz `.env`; kopie są poza OneDrive.
   Nie zmieniano globalnej konfiguracji domowej ani klucza Alpha Vantage.
7. Katalog danych ma uprawnienia dla właściciela, SYSTEM i administratorów;
   wartości kluczy nie były wypisywane.

Windows przekierował początkowy cel AppData do LocalCache aplikacji Codex.
Kontrola wykryła to i dane relokowano do powyższego stabilnego katalogu użytkownika.
Skrypt migracji odrzuca teraz takie przekierowanie przed kopiowaniem sekretów.

## Testy i sposób uruchamiania

- 640 testów plikowych OK, 2 pominięte blokady Linux na Windows.
- Testy wbudowane OK, 25 panelowych OK, 5 uruchamiania OK, pełny ekran JS OK.
- 6 testów ścieżek i 6 migracji, w tym rzeczywista mała SQLite, zachowanie
  oryginału, brak nadpisania, aktywacja i powrót po wymuszonym błędzie.
- `Start-KI2.ps1 -CheckOnly`: READY_TO_START z nową bazą; nie uruchamia procesów.
- `_ai_review.py` pozostawiono bez zmian. To osobne narzędzie z własnym domyślnym
  plikiem bazy; dla odczytu nowej bazy wymaga jawnego `--db`.

Do lokalnego KI, jeśli będzie celowo potrzebne, używać `Start-KI2.ps1` albo
`python -B KI.py --start` bez dawnego względnego `--db KI.matrix.sqlite3`.
Względny `--db` jest świadomym wskazaniem starej bazy w katalogu roboczym.
Nie startować lokalnej kopii zamiast działającej produkcji tylko w celu sprawdzenia panelu.

## Powrót i dalsze prace

Przed ewentualnym powrotem zatrzymać lokalne procesy. Jeśli nowa baza nie była
używana do pracy, oryginalna nadal pozwala wrócić: wyłączyć lokalny profil
i odtworzyć pliki konfiguracji z kopii w `config`. Jeśli w nowej bazie przybyły
dane, najpierw zachować jej aktualną kopię — nie zastępować jej starą bazą.
Archiwa uporządkowano w kolejnym etapie: 35 katalogów i 134 luźne kopie kodu
przeniesiono do `C:\Users\szela\KI2-local\archives\20261108`, z porównaniem
SHA-256 każdego pliku. Zachowano całość danych. Mapa: `ARCHIWA_LOKALNE_20261108.md`.

Sama migracja lokalnych danych nie zmieniała ani nie restartowała VPS.
W odrębnym kroku około 17:38 UTC wdrożono tam KI.py wraz z ki2_paths.py
i prompt_policy.py. Pełne testy na VPS i kontrola po restarcie przeszły;
szczegóły w PROMPTY_KI_20261108.md. Sam plik KI.py nie wystarczy do tego wydania.
Nie kopiować na VPS profilu Windows ani plików kluczy z tej migracji.
Commit/push pozostaje po poniedziałkowej obserwacji naturalnych raportów.

Logi regresji i kopia kodu sprzed tej zmiany:
`C:\Users\szela\.codex\visualizations\2026\10\24\01a16d6f-31ac-7bf2-86e3-26fcecc5967f\ki2-przeniesienie-lokalne-20261108`.
