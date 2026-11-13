# Asystent KI — pierwsze wydanie, 11.11.2026

Ten dokument opisuje pierwotną wersję. Aktualne rozszerzenie internetowe opisuje
ASYSTENT_INTERNET_20261111.md, a połączenie ChatGPT — CHATGPT_KI_MCP.md.
Obecny formularz zachowuje wpisane pytanie po wysłaniu. Przycisk „Wyczyść pytanie
i historię” anonimizuje treści i dowody bieżącego wątku oraz zapisane wyniki
wyszukiwania, wyłącza je z pamięci i widoku, ale zachowuje rozliczenie API.
Nie działa podczas trwającego zadania. Wcześniejsze treści mogą pozostać w kopiach
SQLite do czasu ich rotacji. Głos wewnątrz panelu KI nie został dodany.

## Zakres

Nowa zakładka `Asystent KI`, osobna od automatu i dotychczasowej rozmowy. Użytkownik
tworzy wątek i wysyła pytanie. Model może wybierać odczyty danych KI, a następnie
udziela odpowiedzi po polsku z identyfikatorami dowodów. Na telefonie i tablecie
rozmowa ma jedną kolumnę; szczegóły danych są rozwijane.

Narzędzia: ostatnie dwa odczyty spółki i decyzja orkiestratora, trzy ostatnie analizy
automatu (w tym SL/TP i scenariusze), zapisane przyjęte źródła tych analiz, świece
dzienne 30/90/364 dni, do 20 pozycji portfela, bieżący widok TOP 5 ze wspólnymi
bramkami publikacji, heartbeaty/cykle/liczniki Telegrama zapisane w bazie.

Pierwsze wydanie nie wyszukuje nowych wiadomości, nie pobiera Yahoo i nie czyta
ręcznych raportów GPT ani raportów TradingAgents. Brak danych jest jawny. Stan
systemu oznacza zapisy KI, nie kontrolę systemd, dysku czy sprawdzenie kopii.

## Pamięć i wykonanie

- Wątki, tury, dowody i użycie API zapisują się w nowych tabelach `assistant_*`
  istniejącej bazy. Obejmuje je zwykła kopia SQLite. Nie migrujemy starych rozmów.
- Model otrzymuje ostatnie sześć zakończonych tur tego samego wątku. Pełny zapis
  pozostaje w bazie; UI pokazuje ostatnie 30 tur i 50 najnowszych wątków.
- Nowe dane narzędzi są pobierane w danej turze. Historia nie jest dowodem
  aktualności. Każdy pakiet ma czas odczytu bazy oraz własne czasy źródłowe.
- Zadanie wykonuje wątek backendu panelu; odświeżenie/zmiana zakładki nie uruchamia
  go ponownie. Jest to praca w tle, nie streaming tokenów.
- Po przerwaniu procesu nie ma automatycznej powtórki. Po 10 minutach osierocony
  zapis RUNNING oznaczany jest INTERRUPTED przy otwarciu zakładki.

## Ograniczenia i budżet

- Obecny model KI `gpt-4o-mini`, ten sam klucz OpenAI, transport KI i lease nadzoru.
  Dostęp konta do modelu wymaga próby użytkownika; testy nie wywołują płatnego API.
- Maksymalnie 4 zapytania modelu, 2000 tokenów odpowiedzi na zapytanie, 64 KB
  żądania. Ostatnie zapytanie musi zakończyć odpowiedź. W praktyce do trzech odczytów
  danych i odpowiedzi na jedną turę (funkcje wywoływane pojedynczo).
- Dziennie UTC: maksymalnie 100 wywołań i 1 USD orientacyjnego kosztu tego modułu.
  Rezerwacja kosztu następuje atomowo przed każdym wywołaniem, ze znacznie
  zawyżonym oszacowaniem tokenów wejściowych. Po odpowiedzi używane są tokeny
  raportowane przez API. Nieznane wywołania zachowują pełną rezerwację.
- Stawki standardowe sprawdzone 11.11.2026: input 0.15 USD / milion tokenów,
  output 0.60 USD / milion. To limit aplikacji według zapisanych stawek, nie limit
  rozliczeniowy konta OpenAI. Nie obejmuje automatu, Tavily ani innych aplikacji.
- Model ma funkcje o zamkniętych argumentach. Nie dostaje SQL, powłoki, dowolnych
  plików, ustawień usług czy narzędzi mutujących portfel/Telegram.
- Narzędzia używają osobnych połączeń SQLite mode=ro + query_only. Mutacje dotyczą
  tylko tabel asystenta. Sekrety i surowe odpowiedzi dostawców są wyłączone z danych.
- Kontrola odpowiedzi weryfikuje strukturę i istnienie cytowanych dowodów; nie
  stanowi matematycznego dowodu prawdziwości każdego zdania AI. Użytkownik widzi
  tę informację i może rozwinąć źródła.
- Brak ponawiania po timeout, odmowie, błędzie formatu lub limicie. Ręczne nowe
  pytanie jest nową operacją i może ponownie kosztować.

## Dostęp i wdrożenie

Zakładka dziedziczy dostęp do panelu KI; nie wprowadza logowania ani rozdziału
użytkowników. Wątki są wspólne dla osób mających dostęp do tego panelu. Korzystać
przez obecny prywatny dostęp, nie wystawiać dodatkowego portu dla asystenta.

Kod asystenta nie wymaga nowych zależności ani nowego środowiska Linux. Wdrożenie
korzysta ze sprawdzonej paczki: hash, pełna regresja na VPS, lease, kopia kodu,
kontrolowany restart i health + trzy heartbeaty. Paczka obejmuje też wcześniej
przetestowaną korektę prezentacji kolorów zapisów historycznych oraz bezpośredni
zapis kolorów w komórkach matrycy i wartościach wskaźników. Bramki świeżości analiz
pozostają bez zmian. Przyczyny zaniku kolorów matrycy na urządzeniu użytkownika
nie potwierdzono zdalnie; należy sprawdzić po wdrożeniu i ponownym otwarciu strony.

## Próba po wdrożeniu (ręczna, płatna)

1. Otwórz Asystent KI, utwórz wątek.
2. Zapytaj: „Dlaczego HUMA nie jest w TOP 5? Sprawdź decyzję i ostatnią ocenę”.
3. Sprawdź daty i dowody, porównaj z panelem.
4. W tym samym wątku: „A co z wolumenem?”.
5. Odśwież panel — nie powinno przybyć wywołań bez nowego pytania.

Testy offline sprawdzają przepływ z symulowanymi odpowiedziami, odczyty SQLite,
brak mutacji danych rynkowych, pamięć i izolację wątków, limity, awarie, rzeczywiste
bramki TOP 5 i widok Streamlit. Nie zastępują oceny jakości rzeczywistego modelu.

Dokumentacja integracji:
https://developers.openai.com/api/docs/guides/function-calling
https://developers.openai.com/api/docs/guides/conversation-state
https://developers.openai.com/api/docs/models/gpt-4o-mini
