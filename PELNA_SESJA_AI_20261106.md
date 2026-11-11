# Pełny przebieg sesji w końcowej ocenie AI

Problem ujawniony 6 listopada dla SVRA, TENX, LXRX, PDSB i ONCY: odczyty były
świeże (około minuty), ale ostatnia świeca USA obejmowała 15:30–16:00 czasu
Nowego Jorku, czyli 21:30–22:00 czasu Berlina. Godzinowy RVOL był celowo pusty,
a sito błędnie traktowało ten oczekiwany brak jak niekompletny materiał.

Ocenę uzupełnia teraz pełny pakiet bieżącej sesji, nie tylko dwie ostatnie świece.
Zapisana historia chart_history daje OHLCV każdej świecy dnia do chwili odczytu.
Kalendarium giełdy ujawnia brakujące przedziały. Bieżąca skrócona świeca pozostaje
rzeczywistym krótszym przedziałem, z rvol=null. Nie wprowadzono ekstrapolacji.

Pakiet zawiera otwarcie sesji, zakres cen, zmianę od otwarcia i osobno od stałej
bazy poprzedniej sesji, wolumen oraz kolejne zapisane odczyty ceny i wolumenu.
Każda świeca w sumie wolumenu występuje raz. Powtórne odczyty w jej obrębie są
narastającym licznikiem, a nie dodatkowymi transakcjami do zsumowania.

Do danych nie wchodzą inne spółki, inne dni ani odczyty późniejsze od chwili
analizowanego zdarzenia. Konfliktujące, przeniesione i brakujące świece nie są
uzupełniane zmyśloną ceną. Niepełne pokrycie sesji blokuje końcową ocenę AI
z dokładnym opisem braków. Surowe dane nadal pozostają w KI.

Wyjątek dotyczący RVOL wymaga zgodnego z kalendarzem krótszego końca sesji,
dodatniego rzeczywistego wolumenu, poprawnej średniej oraz pełnego zapisu
dostępnej sesji z przynajmniej jedną zakończoną pełną godziną. Zwykły brak
RVOL w pełnej godzinie, NaN, ujemna wartość lub dowolna flaga partial_interval
nie obchodzą kontroli. Potwierdzenie ruchu nadal wymaga trzech dowodów aktywności.

Prompt i kontrola odpowiedzi wymagają omówienia przebiegu sesji oraz osobnego
rozpoznania skróconego przedziału. Cena bazowa nie jest przesuwana na otwarcie.
Zachowano technikę, scenariusze, poziomy, źródła i zapisane tło finansowe oraz
własne wyniki historyczne spółki. Nie ma porównań między emitentami.

Panel pokazuje nową sekcję „Przebieg bieżącej sesji”, zakres danych oraz
szczegółowe powody odrzucenia z czasem odczytu i selekcji. Końcowe oceny nadal
mają limit sześciu nowych spółek na cykl i nie wymuszają minimum trzech.

Nie ponawiamy historycznych DONE/FAILED/REVIEW_REQUIRED ani niepewnych żądań.
Świeże, niezakończone zadanie może otrzymać lokalnie pakiet z już zapisanego
materiału z jego pierwotnej chwili, bez przepisywania zdarzenia i bez dodatkowego
pobierania danych. Zmiana dotyczy kolejnych naturalnych analiz skanera.

Testy korzystają z tymczasowych baz, pełnej sesji USA z sześcioma zamkniętymi
godzinami i rzeczywistą skróconą końcówką, powtórnych odczytów, braków, konfliktów
i przyszłych danych. Nie wykonano rzeczywistych testów AI/Tavily ani wysyłek.
