# Wybrane okazje · TOP 5

Status: wdrożono na VPS 9 listopada 2026 o 19:21 UTC (20:21 CET).
Ponowiony instalator zakończył się success, kod 0; panel i trzy heartbeaty
potwierdzone. Kopia kodu:
`/home/ubuntu/ki2/backup-top5-20261109T192101974547Z`.
Jednostka: `ki2-top5-install-retry-20261109.service`.
Rzeczywisty widok na urządzeniach i kwalifikująca się nowa ocena nadal
pozostają do potwierdzenia. Bez płatnych testów i testowych wiadomości.
Próba VPS z 9 listopada po 19:16 UTC: dziewięć testów instalatora OK,
pięć etapów pełnej regresji PASS i graf TradingAgents offline OK.
Podmianę odłożono przed zmianą plików i zatrzymaniem KI: aktywna blokada
dostawcy lub nadzoru. Wystarczy ponowić sam instalator po zakończeniu operacji,
dopóki zapis walidacji jest ważny (sześć godzin).

Osobna zakładka obok Automatu, przeznaczona do przeglądania maksymalnie pięciu
świeżych, poprawnych, niezależnych ocen spółek. Nie tworzy nowych okazji,
nie wywołuje AI, Tavily ani Yahoo, nie zmienia selekcji i wysyłki Telegrama.
„Końcowe oceny AI” pozostają widokiem diagnostycznym, także błędów i odrzuceń.

## Warunki prezentacji

Zapis zadania musi być najnowszą końcową oceną danej spółki i mieć stan DONE.
Zestawienie musi być READY i zawierać ten identyfikator w included. Wymagane są
INFORM, lokalne ALIGNED, pełny przebieg sesji do chwili oceny i ponowna lokalna
walidacja odpowiedzi bez pominięć. Raport, snapshot i manifest muszą dotyczyć
tego samego instrumentu. Spółka pozostaje na liście obserwowanych.

Regularna sesja musi być otwarta, odczyt nie może być starszy niż piętnaście
minut ani pochodzić z przyszłości, a jego świeca nie może wygasnąć. Najnowszy
odczyt musi nadal potwierdzać ruch i tę samą bazę. Odtwarzana lokalnie ocena
najnowszego materiału musi pozostać ALIGNED i zachować komplet sesji. Poziomy
do tej kontroli wyznacza się na chwilę ich rzeczywistego pozyskania, bez API.

Nowsze PENDING, FAILED, REVIEW_REQUIRED lub PANEL_ONLY zastępuje dawny pozytywny
zapis; nie wraca się do starszej korzystniejszej oceny. Utrata aktualności,
dominujące ryzyko lub zmiana bazy usuwa kartę. Lista nie jest sztucznie
uzupełniana do pięciu. Kolejność: zapisana punktacja automatu, potem świeżość
danych; jest to porządek prezentacji, bez porównawczego promptu AI.

## Karty i pełny raport

Na karcie: ticker, nazwa, kierunek, cena i ruch od stałej bazy, czas odczytu,
czas ukończenia AI, granica aktualności, werdykt AI, ryzyko, warunki scenariusza,
SL/TP, wsparcie/opór, relacja potencjału do ryzyka, punktacja i opis aktywności.
Cena i wniosek AI pochodzą z tej samej migawki. Nowsza cena nie jest podmieniana
pod dawny opis. Braki poziomów są jawnie opisane, bez wymyślania zleceń krótkich.

„Pełna analiza” rozwija trzy osie AI, interpretacje i komplet wskaźników,
zdarzenia techniczne, pełne szczegóły planu, zapis scenariusza z datą,
osobne czasy bid/ask, świece i odczyty bieżącej sesji, przyjęte cytaty i linki,
ryzyka, braki, zapisane fundamenty oraz wyniki własnych sygnałów. Historyczny
scenariusz nie jest przedstawiany jako warunek bieżącej świecy. Widok nie
zmienia dotychczasowego sposobu prezentacji scenariuszy w innych zakładkach.

Filtry: Wszystkie / GPW / USA. Na telefonie jedna kolumna, na szerokim tablecie
dwie; sekcje rozwijane działają natywnie w przeglądarce, bez dodatkowego JS.
Przy aktywnym odświeżaniu panel czyta bazę i sprawdza aktualność co minutę;
rynek i AI nadal korzystają z cyklu skanera. Przy wyłączonym odświeżaniu dostępny
jest przycisk ręcznego odczytu. Żadnych zmian ustawień, kluczy, historii czy kolejek.

## Weryfikacja

Jedenaście nowych testów z rzeczywistym SQLite: limit, deterministyczny porządek,
rynki, brak wymuszonego minimum, wygasanie, zastąpienie starszej oceny nowszą,
pogorszenie bieżącego odczytu, odrzucona tożsamość i usunięty ticker, etap przed
finalizacją, nienaruszalność czasu/ceny raportu, bezpieczeństwo HTML/linków,
warunki scenariusza i przełączanie Streamlit bez API i zapisów do bazy.
Dodatkowy test panelu przechodzi przez nowe menu od pustej bazy i potwierdza,
że nie powstają zadania ani wiadomości.

Zweryfikowano układ w odizolowanym Edge na HTML z jawnych danych testowych:
390 px i 1024 px, szczegóły zamknięte i rozwinięte, bez przewijania całej strony
w poziomie. Zrzuty i pomiary znajdują się w artefaktach Codex:
`ki2-top5-20261109/layout-report.json`, `mobile.png`, `tablet.png`.
Nie są to rzeczywiste spółki wytypowane przez produkcję.

Pełna regresja: 691 testów modułów Windows i Linux OK (odpowiednio dwa i cztery
pominięcia zależne od systemu i Node.js), wbudowane 522, panel 26, uruchamianie 5.
Końcowa kontrola Windows obejmuje ostateczną wersję modułu; na Linux dodatkowo
powtórzono wszystkie jedenaście nowych testów po drobnych poprawkach podpisu
odświeżania i obsługi niepoprawnego linku. Dziewięć testów instalatora na obu
systemach OK, w tym wycofanie nowo dodanego modułu; graf READY_OFFLINE.
JavaScript pełnego ekranu sprawdzony na Windows. Wszystko bez płatnych wywołań.
Paczka VPS została wdrożona. Trzeba jeszcze sprawdzić
rzeczywisty widok na urządzeniach. Sam nowy widok nie potwierdza skuteczności
modelu v3 ani doręczenia rzeczywistego zestawienia na Telegram.
