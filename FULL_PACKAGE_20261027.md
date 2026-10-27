# KI 2 — pełne lokalne oceny przed AI, krótki Telegram

Projekt C:\Users\szela\OneDrive\Desktop\KI\2 KI; KI.py. Zmiany wspólne dla tickerów GPW i USA, bez zmian w Alchemiku i bez ponawiania historycznych wiadomości.

## Kolejność

1. Zakończone odczyty ceny i wskaźników, kontekstu Tavily oraz próba zebrania poprzedniego porównywalnego odczytu i spreadów.
2. build_analysis_manifest zapisuje lokalne oceny: tożsamość i czasy, detekcja i baza, wszystkie wskaźniki i ich zgodność z kierunkiem, lokalna klasyfikacja RSI, punktacja wskazań wzrostowych wraz z częściami i uzasadnieniami, aktywność, ryzyko, bid/ask, stan danych porównawczych i źródeł. Brak danych pozostaje brakiem, nie oceną bezpieczeństwa ani okazji.
3. Kontrola spójności i zasadności wywołania AI. Błąd zbierania danych porównawczych nie jest już wyciszany: zapisuje collection_error i blokuje AI. Odczyt bez dostępnej historii jest jawnym UNAVAILABLE, nie awarią. Brak ofert nadal ogranicza zakres interpretacji zgodnie z poprzednim uzgodnieniem.
4. Przed AI zapis kontekstu zawierającego analysis_manifest, ai_preflight oraz prepared_ai_request. OpenAI korzysta z przygotowanego requestu; DeepSeek stosuje dotychczasową adaptację modelu/schematu. W pakiecie dla AI są wszystkie lokalne oceny, bieżące wskaźniki i porównywalny odczyt, bez podwójnego kopiowania tych samych wartości.
5. Walidacja odpowiedzi i bramka publikacji; dopiero potem zwięzły Telegram.

## Kompletność źródeł

Treści przyjętych źródeł nie są już obcinane do 1800 znaków. Walidacja przyjmuje do ośmiu źródeł (maksymalny zakres bieżącego Search), zachowując kontrolę emitenta, domen i dat. Surowe odpowiedzi i odrzucone wyniki pozostają diagnostyką. Nie oznacza to kompletnej wiedzy o emitencie ani niezależnego potwierdzenia prawdziwości każdego zdania źródła.

Pełny przygotowany request powyżej 160000 znaków jest zatrzymywany lokalnie z powodem, bez cichego skracania źródeł i bez płatnego AI. Starych zapisów już przyciętych w poprzedniej wersji nie rekonstruowano przez nowe płatne zapytania.

## Spójność ocen i prezentacji

Prompt wymaga pierwszego krótkiego wniosku łączącego cenę, aktywność i ograniczenia, a nie definicji pojedynczego wskaźnika. Nie wolno zmieniać lokalnej klasyfikacji RSI lub traktować RSI jako wyceny. Dodano walidację sprzecznych określeń RSI i szersze wykrywanie nieuzasadnionej względnej zmienności ATR. Pozostaje to zestawem konkretnych kontroli, nie dowodem poprawności każdego możliwego zdania modelu.

Panel nazywa listę potwierdzonymi ruchami. Punktację opisano jako wskazania wzrostowe, a nie symetryczną jakość każdego kierunku. Nie zmieniano progów ani arytmetyki rankingu. Poprawiono błędny podwójny znak przy ujemnej zmianie od bazy.

Telegram: nagłówek kierunku, ruch/procent i cena, ocena zgodności wskazań, aktywność, ryzyko/oferty, jeden krótki komentarz AI, stan przyczyny i odsyłacz do pełnego raportu w panelu. Bez punktacji, listy wskaźników, listy cytatów/URL i technicznej listy odrzuceń. Pełna diagnostyka i raport pozostają zapisane.

## Weryfikacja i wdrożenie

309 testów plikowych, 333 self-testy, 24 testy panelu — OK. Nowe testy potwierdzają komplet sekcji manifestu, dostępność wszystkich wskaźników bez duplikacji w promptcie, brak obcięcia końca źródła przekraczającego 1800 znaków, krótki Telegram i blokowanie wskazanych błędów RSI/ATR. Istniejące testy dostosowano do żądanego krótkiego formatu; testy atomowości i deduplikacji zachowano.

Kontrolowany restart po sprawdzeniu braku BUSY_AI/BUSY_CONTEXT i SENDING. Nowy launcher uruchomiony w widocznym oknie zgodnie z preferencją użytkownika. Kopia wcześniejszego kodu i testów oraz stan usług po wdrożeniu: backup_20261027_full_package. Nie wykonywano płatnych testów ani dodatkowych wiadomości Telegram. Kolejny naturalny przebieg jest potrzebny do potwierdzenia wyniku na żywo.

Dodatkowa kontrola: nowy fragment Search bez pełnej treści (content_complete=false) blokuje wywołanie AI. Pochodzenie treści jest zapisywane jako raw_content/extract/search_snippet; starsze zapisy bez tej informacji oznaczono legacy_unknown. Ostateczny stan wdrożenia i hash kodu w deployment.json.
