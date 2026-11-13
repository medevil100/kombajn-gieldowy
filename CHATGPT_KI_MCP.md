# ChatGPT — prywatny odczyt KI przez MCP

Serwer `ki_mcp_server.py` udostępnia siedem odczytów z istniejącej bazy KI:
`ki_company`, `ki_reviews`, `ki_saved_news`, `ki_daily_history`, `ki_portfolio`,
`ki_top5`, `ki_system_status`. Korzysta z tego samego Reader co Asystent KI.
Nie uruchamia skanowania, płatnej analizy, wyszukiwania ani Telegrama.
Wyniki są zapisami z datą odczytu, nie gwarantowanymi notowaniami na żywo.

Obsługuje stdio JSON-RPC, starsze initialize i MCP 2026-07-28: server/discover,
metadane wersji per żądanie oraz resultType. Dane SQLite odczytuje przez mode=ro
i query_only. Nie udostępnia dowolnego SQL, powłoki ani kluczy. Log protokołu
zawiera tylko wersję, nazwę metody i kategorię wyniku, bez treści danych.

## Rozmieszczenie na VPS

- Projekt KI i baza: `/home/ubuntu/ki2`.
- Czytnik, launcher, oficjalny klient OpenAI: `/home/ubuntu/ki2-chatgpt-mcp`.
- `tunnel.json`: lokalny obiekt JSON z rzeczywistym `tunnel_id` utworzonym na Platform.
  Nie jest częścią repozytorium; nie wpisywać do niego klucza API.
- Usługa: `ki2-chatgpt-tunnel.service`, użytkownik ubuntu, autostart systemowy.
- Diagnostyka: wyłącznie `127.0.0.1:8788`; nie koliduje z KI 8501 i Tavli 8080.

Launcher używa klucza OpenAI z istniejącej konfiguracji KI albo opcjonalnego
pliku `.runtime-key` w katalogu klienta. Plik z osobnym kluczem musi mieć tryb
0600. Klucz przekazywany jest w środowisku procesu, nigdy w argv ani manifestach.
Wymagane są uprawnienia runtime Tunnels Read/Use. Nie używać klucza administratora.

Oficjalny klient: https://github.com/openai/tunnel-client/releases/latest
Na produkcji sprawdzono 0.0.20 linux-amd64. Przy instalacji weryfikować sumę
artefaktu z oficjalnego wydania; nie polegać na niezweryfikowanym binarnym pliku.
Polecenie klienta i flagi można odczytać z `launch_parameters` w launcherze.

Repozytorium zawiera odtwarzalny plik usługi i drop-in:

```bash
sudo install -o root -g root -m 0644 ki2-chatgpt-tunnel.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/ki2-chatgpt-tunnel.service.d
sudo install -o root -g root -m 0644 ki2-chatgpt-sqlite-access.conf \
  /etc/systemd/system/ki2-chatgpt-tunnel.service.d/sqlite-access.conf
sudo systemctl daemon-reload
sudo systemctl enable --now ki2-chatgpt-tunnel.service
```

Te polecenia wymagają wcześniejszego przygotowania katalogu klienta, plików,
prywatnego tunnel.json, prawidłowego środowiska Python i klucza. Nie stanowią
samodzielnego instalatora. Nie nadpisywać istniejącej konfiguracji bez porównania.
Zmiany plików repozytorium nie aktualizują automatycznie kopii na VPS.

Drop-in jest potrzebny: sam ProtectHome=read-only blokował SQLite błędem
SQLITE_CANTOPEN. Porównanie w zwykłej powłoce i w przestrzeni montowań usługi
potwierdziło przyczynę. Dostęp do katalogu dla plików pomocniczych nie zmienia
trybu tylko do odczytu ustawionego przez czytnik.

## Kontrola połączenia

```bash
systemctl is-active ki2-chatgpt-tunnel
curl --noproxy '*' --fail http://127.0.0.1:8788/readyz
curl --noproxy '*' --fail http://127.0.0.1:8788/health/mcp
```

Samo readyz=200 nie dowodzi wykrycia ani działania narzędzi. Po skonfigurowaniu
prywatnej wtyczki ChatGPT z właściwym tunelem i obszarem Business trzeba wykonać
rzeczywiste ki_system_status({}) i ki_company({"ticker":"HUMA"}).
Te dwa odczyty potwierdzono na VPS 12.11.2026 i ponownie stan modułów 13.11.2026.
Użytkownik zgłosił także działanie rozmowy głosowej; zgodność wszystkich narzędzi,
urządzeń i trybów głosowych nie była osobno zweryfikowana.

Połączenie nie przenosi automatycznie historii rozmowy ChatGPT do Asystenta API
w panelu KI. Czytnik nie daje dostępu do systemd, nocnych kopii ani wolnego dysku.
MCP nie wywołuje własnego modelu API; odpowiedź powstaje w czacie korzystającym
z narzędzi. Nie jest to deklaracja cennika ani bezpłatności usług OpenAI.

Testy: `python -B -m unittest test_ki_mcp_20261112`. Używają tymczasowych baz,
sprawdzają prawdziwy stdio subprocess, obie wersje protokołu, blokady argumentów,
brak zmian danych oraz niewypisywanie kluczy i treści odczytów do logów.
