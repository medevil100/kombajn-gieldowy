# TradingAgents — instrukcja obsługi

## Co to jest

TradingAgents v0.6.0 (TauricResearch) — framework multi-agent LLM do analizy finansowej.
Pipeline: Market Analyst → News Analyst → Bull/Bear debate → Trader → Risk → Portfolio.
Każdy agent to osobne wywołanie GPT z własnym promptem.

## Lokalizacja

- **Pakiet:** zainstalowany w conda env `tradingagents` (Python 3.11)
- **CLI:** `tradingagents` (entry point)
- **Raporty:** `C:\Users\szela\.tradingagents\logs\<TICKER>\<DATA>\reports\`
- **Cache danych:** `C:\Users\szela\.tradingagents\cache\`
- **Preferencje CLI:** `C:\Users\szela\.tradingagents\cli_prefs.json`

## Uruchomienie

### Krok 1 — aktywuj środowisko

    conda activate tradingagents

### Krok 2 — przejdź do katalogu z `.env`

    cd "C:\Users\szela\OneDrive\Desktop\KI\KI_KLON_2026-10-13"

**Ważne:** TradingAgents czyta `.env` z bieżącego katalogu. `.env` musi zawierać:

    OPENAI_API_KEY=sk-proj-...
    TRADINGAGENTS_LLM_PROVIDER=openai

### Krok 3 — odpal CLI

**Najprościej (ticker + data + analitycy):**

    tradingagents --ticker NVDA --date 2026-10-16 --analysts market,news --no-checkpoint

**Z pełną listą analityków:**

    tradingagents --ticker NVDA --date 2026-10-16 --analysts market,news,fundamentals,social --no-checkpoint

**Dla GPW (spółki z .WA):**

    tradingagents --ticker KGH.WA --date 2026-10-16 --analysts market,news --no-checkpoint

**Z zapisem raportu HTML:**

    tradingagents --ticker NVDA --date 2026-10-16 --analysts market,news --no-checkpoint --save --html

## Parametry CLI

| Parametr | Opis |
|---|---|
| `--ticker <SYM>` | Symbol (NVDA, KGH.WA, 0700.HK) — pomija prompt |
| `--date <YYYY-MM-DD>` | Data analizy — pomija prompt |
| `--analysts <lista>` | Analitycy: market,news,fundamentals,social (comma-separated) |
| `--no-checkpoint` | Bez zapisu stanu (prostsze, do testów) |
| `--checkpoint` | Włącz checkpoint-resume (dla długich przebiegów) |
| `--clear-checkpoints` | Usuń checkpointy przed startem |
| `--save` / `--no-save` | Zapis raportu bez pytania |
| `--show` / `--no-show` | Pokaż raport na końcu bez pytania |
| `--html` / `--no-html` | Zapisz HTML (domyślnie: yes) |
| `--portfolio <plik.json>` | JSON z Twoimi pozycjami — agenci sizing'ują pod realny portfel |

## Tryb interaktywny (bez parametrów)

    tradingagents

CLI zapyta o:
1. **Output Language** — wybierz `Custom language` → wpisz `Polish`
2. **Ticker** — np. `NVDA`
3. **Data** — np. `2026-10-16`
4. **Research Depth** — `Shallow` (szybko, tanio), `Medium` (środek), `Deep` (dokładnie, drogo)
5. **Analitycy** — `market,news` (szybko), pełny zestaw (wolniej)
6. **LLM Provider** — `OpenAI-compatible`
7. **Base URL** — `https://api.openai.com/v1`
8. **Quick model** — `gpt-4o-mini`
9. **Deep model** — `gpt-4o-mini`

**CLI zapamiętuje wybory w `cli_prefs.json`.** Przy następnym uruchomieniu nie pyta o to samo.

## Koszt

| Konfiguracja | Koszt/przebieg |
|---|---|
| Shallow + gpt-4o-mini + 2 analityków | ~$0.03–0.08 |
| Medium + gpt-4o-mini + 4 analityków | ~$0.15–0.30 |
| Deep + gpt-4o + 4 analityków | ~$1.50–3.00 |

**Uwaga:** pierwszy przebieg NVDA (16.10) kosztował więcej, bo Deep był ustawiony na `gpt-6-sol`.
Po fixie `cli_prefs.json` oba modele to `gpt-4o-mini`.

## Gdzie szukać raportów

Po zakończeniu:

    Get-ChildItem "C:\Users\szela\.tradingagents\logs\NVDA\2026-10-16\reports\"

Pliki:
- `market_report.md` — analiza techniczna
- `news_report.md` — analiza newsów i sentymentu
- `investment_plan.md` — plan inwestycyjny (decyzja)
- `trader_investment_plan.md` — plan tradera
- `final_trade_decision.md` — finalna rekomendacja

## Uruchomienie w tle (automatyzacja)

    cd "C:\Users\szela\OneDrive\Desktop\KI\KI_KLON_2026-10-13"
    conda run -n tradingagents tradingagents --ticker NVDA --date 2026-10-16 --analysts market,news --no-checkpoint --save

**Uwaga:** `conda run` może nie widzieć `.env` — użyj `cmd /c "conda activate tradingagents && tradingagents ..."` jeśli problem.

## Integracja z KI (plan na później)

### Opcja A — ręcznie
KI robi swoje, TradingAgents uruchamiany ręcznie dla wybranych tickerów.

### Opcja B — z pipeline KI
Po wykryciu okazji KI woła `tradingagents --ticker X` i dorzuca raport do `analysis_jobs`.

### Opcja C — AI na logach
TradingAgents czyta `alert_decisions` z KI i sugeruje zmiany progów (etap C z planu).

## Troubleshooting

### `401 EMPTY` / `token_invalidated`
- Sprawdź `.env`: `OPENAI_API_KEY=sk-proj-...` bez cudzysłowów
- Sprawdź czy nie ma `$env:OPENAI_API_KEY` w sesji (env wygrywa z .env):
  
      Remove-Item Env:\OPENAI_API_KEY -ErrorAction SilentlyContinue

- Sprawdź czy klucz na dashboardzie OpenAI ma status `Active`

### `ModuleNotFoundError: No module named 'tradingagents'`
- Aktywuj env: `conda activate tradingagents`
- Sprawdź: `python -c "import tradingagents; print(tradingagents.__file__)"`

### Raport po niemiecku zamiast po polsku
- Sprawdź `cli_prefs.json`: `"output_language": "Polish"`
- Zmień ręcznie jeśli trzeba:
  
      $prefs = "$env:USERPROFILE\.tradingagents\cli_prefs.json"
      $c = Get-Content $prefs -Raw
      $c = $c -replace '"output_language":\s*"[^"]*"', '"output_language": "Polish"'
      [System.IO.File]::WriteAllText($prefs, $c, [System.Text.UTF8Encoding]::new($false))

### yfinance rate limit
- Yahoo czasem blokuje — poczekaj 5–10 min i spróbuj ponownie
- Cache w `~/.tradingagents/cache/` może pomóc — usuń jeśli dane są stare

### Za drogo
- Ustaw Deep na `gpt-4o-mini` w `cli_prefs.json`
- Używaj `Shallow` zamiast `Medium`/`Deep`
- Ogranicz analityków do `market,news`

## Przykład pełnego przebiegu

    conda activate tradingagents
    cd "C:\Users\szela\OneDrive\Desktop\KI\KI_KLON_2026-10-13"
    tradingagents --ticker KGH.WA --date 2026-10-17 --analysts market,news --no-checkpoint
    Get-Content "$env:USERPROFILE\.tradingagents\logs\KGH.WA\2026-10-17\reports\final_trade_decision.md"

## Backup klucza

**Nigdy nie commituj `.env` do repo.** Sprawdź:

    Get-Content .gitignore | Select-String "\.env"

Jeśli nie ma — dopisz:

    Add-Content .gitignore "`n.env"
