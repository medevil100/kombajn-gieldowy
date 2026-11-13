# Asystent KI — odpowiedź końcowa i internet OpenAI

Użytkownik wybrał wyszukiwanie OpenAI bez Tavily. Nowe narzędzie web_search
wywołuje Responses API z modelem już stosowanym w Asystencie (gpt-4o-mini),
narzędziem web_search, max_tool_calls=1 i store=false. Używa OPENAI_API_KEY
z konfiguracji KI; nie odczytuje klucza Tavily i nie łączy się z aplikacją Tavli.

Model wybiera narzędzie po pytaniu wymagającym aktualnych informacji. Przekazuje
krótki publiczny temat (do 400 znaków), nie cały portfel ani historię rozmowy.
Prompt zabrania przesyłania prywatnych danych; wykrywalne klucze są blokowane.
Brak nowych pobrań Yahoo i zmian skanera, portfela, progów czy powiadomień.

Limity: maksymalnie 4 kroki głównego AI i 1 dodatkowe wywołanie wyszukiwania
na pytanie; maksymalnie 20 wyszukiwań dziennie UTC. Wyszukiwanie wlicza się
do istniejących 100 wywołań i 1 USD orientacyjnego kosztu dziennie. Rezerwacja
jest atomowa, przed siecią. Nieznane rozliczenie zachowuje rezerwację.
Stawka lokalna: 0,01 USD za standardowe web_search plus tokeny; dla gpt-4o-mini
doliczany konserwatywnie blok 8000 tokenów wyszukania. Jeśli dostawca uwzględnia
już ten blok w usage, lokalny licznik zawyży koszt. To limit szacunkowy, nie faktura.

Nowa tabela assistant_web_calls wiąże jedno wyszukiwanie z turą i istniejącym
assistant_calls. Wynik i dowody zapisują się w rozmowie. Ponowne wejście,
odświeżenie i ponowne żądanie narzędzia w tej turze nie powtarzają wywołania.
Przy braku klucza, limicie, błędzie lub niepełnej odpowiedzi model otrzymuje jawny
status UNAVAILABLE; może wyjaśnić ograniczenie i odpowiedzieć z zapisów KI.

Przyjmujemy tylko zakończone wyszukiwanie i kompletne fragmenty z cytowaniami
URL. Linki są sprawdzane pod kątem protokołu i prywatnych adresów. Nie pobieramy
stron lokalnie. Cytowania dostawcy są wyświetlane jako klikalne linki; przy
akapitach końcowych odwołujących się do wyniku web pokazujemy źródła tego wyniku.
Oryginalne powiązanie cytowań z tekstem znajduje się w rozwijanych dowodach.
To streszczenie wyszukiwarki, nie automatycznie zweryfikowany raport emitenta.
Data wyszukania jest osobna; datę publikacji/zdarzenia model podaje tylko ze źródła.

Pakiet zawiera również poprawkę końcowej syntezy opisaną w
ASYSTENT_ODPOWIEDZ_POPRAWKA_20261111.md: trzy narzędzia i ostatni krok JSON Schema
ze statusem stop. Dotychczasowe pytanie FAILED pozostaje w historii i nie jest
ponawiane. Tabele dodawane są przez ensure, bez kasowania dotychczasowych zapisów.

Testy wyłącznie offline: prawdziwy adapter HTTP KI z zamockowanym requests.post,
lokalne bazy testowe, kontrola pełnej sekwencji KI/web/oceny/odpowiedź,
atomowych limitów, braków źródeł, błędów dostawcy, cytowań i odświeżenia panelu.
Dostępność narzędzia na koncie i jakość realnych wyników wymagają próby użytkownika
po wdrożeniu; nie wykonano płatnego testu.

Źródła kontraktu (sprawdzone 11.11.2026):
- https://developers.openai.com/api/docs/guides/tools-web-search
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://developers.openai.com/api/docs/models/gpt-4o-mini
- https://developers.openai.com/api/docs/pricing
